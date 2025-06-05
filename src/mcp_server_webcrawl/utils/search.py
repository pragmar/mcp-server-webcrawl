from logging import Logger

from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.utils.parser import SearchLexer, SearchParser, SearchSubquery

# url is technically fts but handled differently, uses LIKE
FTS5_MATCH_FIELDS = ["type", "headers", "content"]

logger: Logger = get_logger()

class ParameterManager:
    """
    Helper class to manage SQL parameter naming and counting.
    """
    def __init__(self) -> None:
        self.params: dict[str, str | int | float] = {}
        self.counter: int = 0

    def add_param(self, value: str | int | float) -> str:
        """
        Add a parameter and return its name.
        """
        assert isinstance(value, (str, int, float)), f"Parameter value must be str, int, or float."
        param_name = f"query{self.counter}"
        self.params[param_name] = value
        self.counter += 1
        return param_name

    def get_params(self) -> dict[str, str | int | float]:
        """
        Get all accumulated parameters.
        """
        return self.params

class SearchQueryParser:
    """
    Implementation of ply lexer to capture field-expanded boolean queries.
    """

    def __init__(self) -> None:
        self.lexer = SearchLexer()
        self.parser = SearchParser(self.lexer)

    def get_fulltext_terms(self, query: str) -> list[str]:
        """
        Extract fulltext search terms from a query string.
        Returns list of search terms suitable for snippet extraction.
        """
        parsed_query = self.parse(query)
        search_terms = []
        fulltext_fields = ("content", "headers", "fulltext", "", None)

        # prepare for match, lowercase, and eliminate wildcards
        for subquery in parsed_query:
            if subquery.field in fulltext_fields:
                term = str(subquery.value).lower().strip("*")
                if term:
                    search_terms.append(term)

        return search_terms

    def parse(self, query_string: str) -> list[SearchSubquery]:
        """
        Parse a query string into a list of SearchSubquery instances
        """
        result = self.parser.parser.parse(query_string, lexer=self.lexer.lexer)

        if isinstance(result, SearchSubquery):
            return [result]

        return result

    def to_sqlite_fts(
        self,
        parsed_query: list[SearchSubquery],
        swap_values: dict[str, dict[str, str | int]] = {}
    ) -> tuple[list[str], dict[str, str | int]]:
        """
        Convert the parsed query to SQLite FTS5 compatible WHERE clause components.
        Returns a tuple of (query_parts, params) where query_parts is a list of SQL
        conditions and params is a dictionary of parameter values with named parameters.
        """
        query_parts = []
        param_manager = ParameterManager()
        current_index = 0

        while current_index < len(parsed_query):
            subquery: SearchSubquery = parsed_query[current_index]

            if not subquery.field or subquery.field in FTS5_MATCH_FIELDS:
                # group consecutive fulltext terms with their operators
                fts_field_query = self.__build_fts_field_subquery(parsed_query, subquery.field, current_index, swap_values)
                if fts_field_query["querystring"]:
                    param_name = param_manager.add_param(fts_field_query["querystring"])
                    field_name: str = "fulltext" if subquery.field is None else subquery.field
                    safe_sql_field: str = subquery.get_safe_sql_field(field_name)
                    query_parts.append(f"{safe_sql_field} MATCH :{param_name}")
                    current_index = fts_field_query["next_index"]
            else:
                # handle field searches
                sql_part = ""
                field = subquery.field
                processed_value = self.__process_field_value(field, subquery.value, swap_values)
                value_type = subquery.type
                modifiers = subquery.modifiers

                # NOT modifier if present
                if "NOT" in modifiers:
                    sql_part += "NOT "

                safe_sql_field = subquery.get_safe_sql_field(field)
                if field in self.parser.numeric_fields:
                    param_name = param_manager.add_param(processed_value)
                    sql_part += f"{safe_sql_field} {subquery.comparator} :{param_name}"
                else:
                    if field == "url" or field == "headers":
                        # Use LIKE for certain field searches instead of MATCH, maximize the hits
                        # with %LIKE%. Think of https://example.com/logo.png?cache=20250112
                        # and a search of url: *.png and the 10s of ways broader match is better
                        # fit for intention
                        sql_part += f"{safe_sql_field} LIKE :"
                        # strip wildcards whether wildcard or not
                        unwildcarded_value = str(processed_value).strip("*")
                        param_name = param_manager.add_param(f"%{unwildcarded_value}%")
                        sql_part += param_name
                    # type currently handled FTS5_MATCH_FIELDS handler
                    # elif field == "type":
                    #     param_name = param_manager.add_param(processed_value)
                    #     sql_part += f"{safe_sql_field} = :{param_name}"
                    elif value_type == "phrase":
                        formatted_term = self.__format_search_term(processed_value, value_type)
                        param_name = param_manager.add_param(formatted_term)
                        sql_part += f"{safe_sql_field} MATCH :{param_name}"
                    else:
                        # default fts query
                        param_name = param_manager.add_param(processed_value)
                        safe_sql_field = subquery.get_safe_sql_field("fulltext")
                        sql_part += f"{safe_sql_field} MATCH :{param_name}"

                query_parts.append(sql_part)
                current_index += 1

            # add operator between clauses
            if current_index < len(parsed_query):
                # look at the previous subquery's operator to determine how to connect
                previous_subquery = parsed_query[current_index - 1] if current_index > 0 else None
                if previous_subquery and previous_subquery.operator:
                    op = previous_subquery.operator
                else:
                    op = "AND" # default
                query_parts.append(op)

        return query_parts, param_manager.get_params()

    def __build_fts_field_subquery(
        self,
        parsed_query: list[SearchSubquery],
        field: str | None,
        start_index: int,
        swap_values: dict[str, dict[str, str | int]] = {}
    ) -> dict[str, str | int]:
        """
        The rule is one MATCH per column for fts5, so multiple pure booleans are compressed
        into thier own little querystring, attempting to preserve the Boolean intent of the
        original SearchSubquery substructure. There are complexity limits here. Group IDs
        preserve the parenthetical home of each SearchSubquery, None if not in parens.
        """

        current_index = start_index

        # this modifies subqueries in place, prevents fts conversion leaking
        parsed_query = self.__normalize_fts_match_operators(parsed_query)

        # determine the condition for continuing the loop based on field type
        def continue_sequencing(subquery_field: str | None) -> bool:
            return subquery_field is None if field is None else subquery_field == field

        # group consecutive, group is None unless parenthetical (A OR B)
        groups = []
        current_group = []
        current_group_id = None

        while current_index < len(parsed_query) and continue_sequencing(parsed_query[current_index].field):
            subquery: SearchSubquery = parsed_query[current_index]

            # new group
            if subquery.group != current_group_id:
                if current_group:
                    groups.append((current_group_id, current_group))
                current_group = []
                current_group_id = subquery.group

            processed_value = self.__process_field_value(field, subquery.value, swap_values)
            formatted_term = self.__format_search_term(processed_value, subquery.type, subquery.modifiers)
            current_group.append((formatted_term, subquery.operator))
            current_index += 1

        # last group
        if current_group:
            groups.append((current_group_id, current_group))

        # build query string with parentheses for grouped terms
        query_parts = []
        for group_id, group_terms in groups:
            if group_id is not None and len(group_terms) > 1:
                # multiple terms in a group, add parentheses
                group_str = ""
                for i, (term, operator) in enumerate(group_terms):
                    group_str += term
                    if operator and i < len(group_terms) - 1:
                        group_str += f" {operator} "
                query_parts.append(f"({group_str})")
            else:
                # single term or ungrouped, no parentheses
                for i, (term, operator) in enumerate(group_terms):
                    query_parts.append(term)
                    if operator and i < len(group_terms) - 1:
                        query_parts.append(operator)

            # add inter-group operator (from last term in previous group)
            if groups.index((group_id, group_terms)) < len(groups) - 1:
                last_term = group_terms[-1]
                if last_term[1]:  # operator exists
                    query_parts.append(last_term[1])

        querystring = " ".join(query_parts)
        return {
            "querystring": querystring,
            "next_index": current_index
        }

    def __format_search_term(
        self,
        value: str | int | float,
        value_type: str,
        modifiers: list[str] | None = None
    ) -> str:
        """
        Format a fulltext search term based on type and modifiers. This takes some
        of the sharp edges of the secondary fts5 parser in conversion.

        Args:
            value: The search value
            value_type: Type of value ('term', 'phrase', 'wildcard')
            modifiers: List of modifiers (e.g., ['NOT'])

        Returns:
            Formatted search term string
        """
        modifiers = modifiers or []
        value_string = str(value)

        if value_type == "phrase":
            return f'"{value_string}"'
        elif value_type == "wildcard":
            # for wildcards, only quote if contains hyphens/spaces require it
            if "-" in value_string or " " in value_string:
                return f'"{value_string}"*'
            else:
                return f"{value_string}*"
        else:
            # for terms like one-click etc.
            # avoid confusing the secondary fts parser
            # where hyphens in unquoted matches can be confused for
            # fts negation (-term)
            if '-' in value_string:
                return f'"{value_string}"'
            else:
                return value_string

    def __normalize_fts_match_operators(self, parsed_query: list[SearchSubquery]) -> list[SearchSubquery]:
        """
        Clean up operators on fulltext sequences so they don't leak into interclause SQL
        Why? ONE MATCH per column. the SearchSubquery sharing a fts field must be compressed
        into a single MATCH. If the next clause does not share the same field as current, it
        requires an operator set to None so as not to leak into the next field. Basically,
        this firewalls boolean logic for combined fts subqueries. The flagship error of not
        doing this is to have "this OR that OR there" return unfiltered or 0 results instead
        of the appropriate number. (unfiltered in the case of a leaky OR status: >=100, which
        instead of defining the result should limit it)
        """
        for i in range(len(parsed_query) - 1):
            current = parsed_query[i]
            next_item = parsed_query[i + 1]

            # transitioning from fulltext to field search, clear the operator
            if not current.field and next_item.field:
                current.operator = None
            # transitioning from fts field to another field
            if (current.field in FTS5_MATCH_FIELDS and next_item.field != current.field):
                current.operator = None

        return parsed_query

    def __process_field_value(
        self,
        field: str | None,
        value_dict: dict[str, str] | str | int,
        swap_values: dict[str, dict[str, str | int]] | None = None
    ) -> str | int | float:
        """
        Process and validate a field value with type conversion and swapping.

        Args:
            field: The field name (or None for fulltext)
            value_dict: Dictionary with 'value' and 'type' keys, or raw value
            swap_values: Optional dictionary for value replacement

        Returns:
            Processed value (string, int, or float)
        """
        if isinstance(value_dict, dict):
            value = value_dict["value"]
        else:
            value = value_dict # raw value

        if swap_values:
            swap_key = field if field else ""
            if swap_key in swap_values and value in swap_values[swap_key]:
                value = swap_values[swap_key][value]

        if field and field in self.parser.numeric_fields:
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    raise ValueError(f"Field {field} requires a numeric value, got: {value}")

        return value
