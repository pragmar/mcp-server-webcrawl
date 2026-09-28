import re

from logging import Logger

from mcp_server_webcrawl.models.resources import RESOURCES_DEFAULT_FIELD_MAPPING
from mcp_server_webcrawl.utils.logger import get_logger
from mcp_server_webcrawl.utils.parser import SearchLexer, SearchParser, SearchSubquery

# url is technically fts but handled differently, uses LIKE; without type in
# fts field mode, the "A long chained OR should not return all results" fails
FTS5_MATCH_FIELDS: list[str] = ["type", "headers", "content"]

# fts5 bareword, per the fts5 docs: ascii alphanumerics, _, any non-ascii, and \x1a.
# the keywords AND/OR/NOT never get here, the lexer takes them first
FTS5_BAREWORD: re.Pattern = re.compile(r"^[A-Za-z0-9_\x1a\u0080-\U0010FFFF]+$")

logger: Logger = get_logger()

class ParameterManager:
    """
    Helper class to manage SQL parameter naming and counting.
    """
    def __init__(self):
        self.params: dict[str, str | int | float] = {}
        self.counter: int = 0

    def add_param(self, value: str | int | float) -> str:
        """
        Add a parameter and return its name.
        """
        assert isinstance(value, (str, int, float)), f"Parameter value must be str, int, or float."
        param_name: str = f"query{self.counter}"
        self.params[param_name] = value
        self.counter += 1
        return param_name

    def get_params(self) -> dict[str, str | int | float]:
        """
        Get all accumulated parameters.
        """
        return self.params

class QueryNode:
    """
    Boolean tree node, rebuilt from the flat SearchSubquery list by to_sqlite_fts.
    kind is term, not, and, or. A term carries its subquery, the rest carry children.
    """
    def __init__(self, kind: str, subquery: SearchSubquery | None = None, children: list["QueryNode"] | None = None):
        self.kind: str = kind
        self.subquery: SearchSubquery | None = subquery
        self.children: list[QueryNode] = children or []

class SearchQueryParser:
    """
    Implementation of ply lexer to capture field-expanded boolean queries.
    """

    def __init__(self):
        self.lexer: SearchLexer = SearchLexer()
        self.parser: SearchParser = SearchParser(self.lexer)

    def get_fulltext_terms(self, query: str) -> list[str]:
        """
        Extract fulltext search terms from a query string.
        Returns list of search terms suitable for snippet extraction.
        """
        parsed_query: list[SearchSubquery] = self.parse(query)
        search_terms: list[str] = []
        fulltext_fields: tuple[str | None, ...] = ("content", "headers", "fulltext", "", None)

        # prepare for match, lowercase, and eliminate wildcards
        for subquery in parsed_query:
            if subquery.field in fulltext_fields:
                term: str = str(subquery.value).lower().strip("*")
                if term:
                    search_terms.append(term)

        return search_terms

    def parse(self, query_string: str) -> list[SearchSubquery]:
        """
        Parse a query string into a list of SearchSubquery instances
        """
        result: SearchSubquery | list[SearchSubquery] = self.parser.parser.parse(query_string, lexer=self.lexer.lexer)

        if isinstance(result, SearchSubquery):
            return [result]
        elif isinstance(result, list) and all(isinstance(item, SearchSubquery) for item in result):
            return result
        else:
            return []

    def to_sqlite_fts(
        self,
        parsed_query: list[SearchSubquery],
        swap_values: dict[str, dict[str, str | int]] = {}
    ) -> tuple[list[str], dict[str, str | int]]:
        """
        Convert the parsed query to SQLite FTS5 compatible WHERE clause components.
        Returns a tuple of (query_parts, params) where query_parts is a list of SQL
        conditions and params is a dictionary of parameter values with named parameters.

        The flat list is rebuilt into a tree first, standard precedence (NOT > AND > OR)
        plus the user's parentheses, so a query means what it says as written. fts5
        packing happens on whole subtrees only. Packing runs of neighboring terms is what
        used to change meaning, a run knows nothing of the precedence around it, so
        type: html AND a OR b ran as html AND (a OR b).
        """
        if not parsed_query:
            return [], {}

        tokens: list[tuple[str, SearchSubquery | str | bool | None]] = self.__get_query_tokens(parsed_query)
        root, position = self.__parse_or(tokens, 0)
        if position != len(tokens):
            raise ValueError(f"Unable to rebuild query at token {position} of {len(tokens)}")

        param_manager: ParameterManager = ParameterManager()
        sql_tokens: list[str] = []
        self.__emit_sql(root, sql_tokens, param_manager, swap_values, direct=True)

        # glue parentheses onto their conditions, so parts alternate condition, operator
        query_parts: list[str] = []
        opening: str = ""
        for token in sql_tokens:
            if token in ("(", "NOT ("):
                opening += token
            elif token == ")":
                query_parts[-1] += ")"
            elif token in ("AND", "OR"):
                query_parts.append(token)
            else:
                query_parts.append(f"{opening}{token}")
                opening = ""

        return query_parts, param_manager.get_params()

    def __get_query_tokens(self, parsed_query: list[SearchSubquery]) -> list[tuple[str, SearchSubquery | str | bool | None]]:
        """
        The flat list back to infix, as written. Parentheses come from the group paths
        (OPEN carries whether the group is negated), operators from the subqueries.
        """
        tokens: list[tuple[str, SearchSubquery | str | bool | None]] = []
        previous_path: tuple[int, ...] = ()
        for i, subquery in enumerate(parsed_query):
            path: tuple[int, ...] = subquery.groups
            common: int = 0
            while common < min(len(previous_path), len(path)) and previous_path[common] == path[common]:
                common += 1
            tokens.extend([("CLOSE", None)] * (len(previous_path) - common))
            if i > 0:
                tokens.append(("OP", parsed_query[i - 1].operator or "AND"))
            for group_id in path[common:]:
                tokens.append(("OPEN", group_id in subquery.negated_groups))
            tokens.append(("TERM", subquery))
            previous_path = path
        tokens.extend([("CLOSE", None)] * len(previous_path))
        return tokens

    def __parse_or(self, tokens: list[tuple[str, SearchSubquery | str | bool | None]], position: int) -> tuple["QueryNode", int]:
        node, position = self.__parse_and(tokens, position)
        children: list[QueryNode] = [node]
        while position < len(tokens) and tokens[position] == ("OP", "OR"):
            node, position = self.__parse_and(tokens, position + 1)
            children.append(node)
        return self.__join_nodes("or", children), position

    def __parse_and(self, tokens: list[tuple[str, SearchSubquery | str | bool | None]], position: int) -> tuple["QueryNode", int]:
        # binary NOT outranks AND, but a AND b NOT c is a AND b AND (NOT c) either way,
        # so it rides the AND chain as a negated operand
        node, position = self.__parse_primary(tokens, position)
        children: list[QueryNode] = [node]
        while position < len(tokens) and tokens[position][0] == "OP" and tokens[position][1] in ("AND", "NOT"):
            operator: str = tokens[position][1]
            node, position = self.__parse_primary(tokens, position + 1)
            children.append(self.__negate_node(node) if operator == "NOT" else node)
        return self.__join_nodes("and", children), position

    def __parse_primary(self, tokens: list[tuple[str, SearchSubquery | str | bool | None]], position: int) -> tuple["QueryNode", int]:
        kind, value = tokens[position]
        if kind == "OPEN":
            node, position = self.__parse_or(tokens, position + 1)
            if position >= len(tokens) or tokens[position][0] != "CLOSE":
                raise ValueError(f"Unbalanced group at token {position}")
            return (self.__negate_node(node) if value else node), position + 1
        if kind != "TERM":
            raise ValueError(f"Expected a term at token {position}, got {kind}")
        node: QueryNode = QueryNode("term", subquery=value)
        return (self.__negate_node(node) if "NOT" in value.modifiers else node), position + 1

    def __negate_node(self, node: "QueryNode") -> "QueryNode":
        # NOT NOT a is a
        return node.children[0] if node.kind == "not" else QueryNode("not", children=[node])

    def __join_nodes(self, kind: str, children: list["QueryNode"]) -> "QueryNode":
        if len(children) == 1:
            return children[0]
        flattened: list[QueryNode] = []
        for child in children:
            flattened.extend(child.children if child.kind == kind else [child])
        return QueryNode(kind, children=flattened)

    def __get_fts_column(self, node: "QueryNode") -> str | None:
        """
        The column a subtree can run on as one fts5 MATCH, None if it can't. The
        limits are fts5's: one column per MATCH, and NOT is binary only (a NOT b),
        so a bare NOT, NOT a AND NOT b, or a OR NOT b stay in SQL.
        """
        if node.kind == "term":
            field: str | None = node.subquery.field
            if field is None:
                return "fulltext"
            return field if field in FTS5_MATCH_FIELDS else None
        if node.kind == "not":
            return None
        positives: list[QueryNode] = [child for child in node.children if child.kind != "not"]
        negatives: list[QueryNode] = [child.children[0] for child in node.children if child.kind == "not"]
        if not positives or (negatives and node.kind == "or"):
            return None
        columns: set[str | None] = {self.__get_fts_column(child) for child in positives + negatives}
        return next(iter(columns)) if len(columns) == 1 else None

    def __get_fts_querystring(self, node: "QueryNode", swap_values: dict[str, dict[str, str | int]]) -> str:
        """
        fts5 querystring for a subtree __get_fts_column accepted. Compound operands are
        always parenthesized, fts5 ranks NOT > AND > OR like SQL, but spelling it out
        costs nothing and cannot be misread.
        """
        if node.kind == "term":
            subquery: SearchSubquery = node.subquery
            processed_value: str | int | float = self.__process_field_value(subquery.field, subquery.value, swap_values)
            return self.__format_search_term(processed_value, subquery.type)

        def operand(child: QueryNode) -> str:
            querystring: str = self.__get_fts_querystring(child, swap_values)
            return f"({querystring})" if child.kind in ("and", "or") else querystring

        if node.kind == "or":
            return " OR ".join(operand(child) for child in node.children)

        positives: list[QueryNode] = [child for child in node.children if child.kind != "not"]
        negatives: list[QueryNode] = [child.children[0] for child in node.children if child.kind == "not"]
        querystring: str = " AND ".join(operand(child) for child in positives)
        if negatives and len(positives) > 1:
            querystring = f"({querystring})"
        for negative in negatives:
            querystring += f" NOT {operand(negative)}"
        return querystring

    def __merge_fts_children(self, node: "QueryNode") -> list["QueryNode"]:
        """
        Children of an and/or, with same-column fts children merged into one MATCH at
        the position of the first (AND and OR commute). Fewer MATCHes, and fewer that
        must run as subqueries. A negated child can only join an AND bucket, and only
        if the bucket ends up with a positive for fts5's binary NOT to hang off.
        """
        buckets: dict[str, list[QueryNode]] = {}
        order: list[str | QueryNode] = []
        for child in node.children:
            column: str | None = self.__get_fts_column(child)
            if column is None and node.kind == "and" and child.kind == "not":
                column = self.__get_fts_column(child.children[0])
            if column is None:
                order.append(child)
                continue
            if column not in buckets:
                buckets[column] = []
                order.append(column)
            buckets[column].append(child)

        merged: list[QueryNode] = []
        for entry in order:
            if isinstance(entry, QueryNode):
                merged.append(entry)
                continue
            members: list[QueryNode] = buckets[entry]
            candidate: QueryNode = members[0] if len(members) == 1 else QueryNode(node.kind, children=members)
            if len(members) > 1 and self.__get_fts_column(candidate) is None:
                merged.extend(members)
            else:
                merged.append(candidate)
        return merged

    def __emit_sql(
        self,
        node: "QueryNode",
        tokens: list[str],
        param_manager: ParameterManager,
        swap_values: dict[str, dict[str, str | int]],
        direct: bool,
    ) -> None:
        """
        SQL tokens for a subtree. direct means a top-level AND constraint, the only
        place sqlite accepts a bare MATCH.
        """
        column: str | None = self.__get_fts_column(node)
        if column is not None:
            tokens.append(self.__get_match_condition(node, column, param_manager, swap_values, direct, negate=False))
            return

        if node.kind == "term":
            tokens.append(self.__get_field_condition(node.subquery, param_manager, swap_values))
            return

        if node.kind == "not":
            inner: QueryNode = node.children[0]
            inner_column: str | None = self.__get_fts_column(inner)
            if inner_column is not None:
                tokens.append(self.__get_match_condition(inner, inner_column, param_manager, swap_values, False, negate=True))
            elif inner.kind == "term":
                tokens.append(f"NOT {self.__get_field_condition(inner.subquery, param_manager, swap_values)}")
            else:
                tokens.append("NOT (")
                self.__emit_sql(inner, tokens, param_manager, swap_values, direct=False)
                tokens.append(")")
            return

        operator: str = node.kind.upper()
        for i, child in enumerate(self.__merge_fts_children(node)):
            if i > 0:
                tokens.append(operator)
            wrapped: bool = child.kind in ("and", "or") and self.__get_fts_column(child) is None
            if wrapped:
                tokens.append("(")
            self.__emit_sql(child, tokens, param_manager, swap_values, direct=direct and node.kind == "and")
            if wrapped:
                tokens.append(")")

    def __get_match_condition(
        self,
        node: "QueryNode",
        column: str,
        param_manager: ParameterManager,
        swap_values: dict[str, dict[str, str | int]],
        direct: bool,
        negate: bool,
    ) -> str:
        param_name: str = param_manager.add_param(self.__get_fts_querystring(node, swap_values))
        safe_sql_field: str = RESOURCES_DEFAULT_FIELD_MAPPING[column]
        match: str = f"{safe_sql_field} MATCH :{param_name}"
        if negate:
            # generate subquery exclusion pattern to avoid JOIN + NOT (MATCH) issues
            return f"ResourcesFullText.Id NOT IN (SELECT Id FROM ResourcesFullText WHERE {match})"
        if direct:
            return match
        # sqlite refuses MATCH anywhere but a top-level AND ("unable to use function
        # MATCH in the requested context"), under an OR or inside NOT (...) it runs as
        # a subquery, same as the NOT exclusion above
        return f"ResourcesFullText.Id IN (SELECT Id FROM ResourcesFullText WHERE {match})"

    def __get_field_condition(
        self,
        subquery: SearchSubquery,
        param_manager: ParameterManager,
        swap_values: dict[str, dict[str, str | int]],
    ) -> str:
        """
        SQL for a non-fts field term, negation is the caller's.
        """
        field: str = subquery.field
        processed_value: str | int | float = self.__process_field_value(field, subquery.value, swap_values)
        value_type: str = subquery.type
        safe_sql_field: str = subquery.get_safe_sql_field(field)

        if field in self.parser.numeric_fields:
            param_name: str = param_manager.add_param(processed_value)
            return f"{safe_sql_field} {subquery.comparator} :{param_name}"

        # headers currently handled FTS5_MATCH_FIELDS handler
        if field == "url":
            # Use LIKE for certain field searches instead of MATCH, maximize the hits
            # with %LIKE%. Think of https://example.com/logo.png?cache=20250112
            # and a search of url: *.png and the 10s of ways broader match is better
            # fit for intention
            trimmed_url: str = str(processed_value).strip("*\"'`")
            param_name: str = param_manager.add_param(f"%{trimmed_url}%")
            return f"{safe_sql_field} LIKE :{param_name}"
        elif value_type == "phrase":
            formatted_term: str = self.__format_search_term(processed_value, value_type)
            param_name: str = param_manager.add_param(formatted_term)
            return f"{safe_sql_field} MATCH :{param_name}"
        else:
            # default fts query
            param_name: str = param_manager.add_param(processed_value)
            safe_sql_field: str = subquery.get_safe_sql_field("fulltext")
            return f"{safe_sql_field} MATCH :{param_name}"

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
        modifiers: list[str] = modifiers or []
        value_string: str = str(value)

        # fts5 only takes barewords unquoted, anything else (example.com, c++,
        # one-click, where hyphen reads as negation) is a syntax error unless
        # quoted as a string. quoting a bareword changes nothing, but leave them be
        if FTS5_BAREWORD.match(value_string) and value_type != "phrase":
            return f"{value_string}*" if value_type == "wildcard" else value_string

        quoted: str = '"{}"'.format(value_string.replace('"', '""'))
        return f"{quoted}*" if value_type == "wildcard" else quoted

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
            value: str | int = value_dict["value"]
        else:
            value: str | int = value_dict # raw value

        if swap_values:
            swap_key: str = field if field else ""
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
