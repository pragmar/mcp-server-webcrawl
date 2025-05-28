import re

from ply import lex
from ply import yacc
from logging import Logger

from mcp_server_webcrawl.models.resources import RESOURCES_DEFAULT_FIELD_MAPPING
from mcp_server_webcrawl.utils.logger import get_logger

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

class SearchSubquery:
    """
    Subquery component in a structured search expression.

    These are grouped into an ordered list, and are the basis the SQL query.
    """

    def __init__(
        self,
        field: str | None,
        value: str | int,
        type: str,
        modifiers: list[str] | None,
        operator: str | None,
        comparator: str = "="
    ) -> None:
        """
        Initialize a SearchSubquery instance.

        Args:
            field: field to search, or None for fulltext search
            value: search value (string or integer)
            type: value type (term, phrase, wildcard, etc.)
            modifiers: list of modifiers applied to the query (e.g., 'NOT')
            operator: boolean operator connecting to the next subquery ('AND', 'OR', or None)
            comparator: comparison operator for numerics ('=', '>', '>=', '<', '<=', '!=')
        """
        self.field: str | None = field
        self.value: str | int = value
        self.type: str = type
        self.modifiers: list[str] = modifiers or []
        self.operator: str | None = operator or None
        self.comparator: str = comparator

    def to_dict(self) -> dict[str, str | int | list[str] | None]:
        """
        Convert SearchSubquery to dictionary representation.

        Args:
            field: Field name to use in the dictionary (overrides self.field)

        Returns:
            Dictionary containing all SearchSubquery attributes
        """
        return {
            "field": self.field,
            "value": self.value,
            "type": self.type,
            "modifiers": self.modifiers,
            "operator": self.operator,
            "comparator": self.comparator
        }

    def get_safe_sql_field(self, field: str) -> str:
        if field in RESOURCES_DEFAULT_FIELD_MAPPING:
            return RESOURCES_DEFAULT_FIELD_MAPPING[field]
        else:
            logger.error(f"Field {self.field} failed to validate.")
            raise Exception(f"Unknown database field {self.field}")

class SearchQueryParser:
    """
    Implementation of ply lexer to capture field-expanded boolean queries.
    """

    # ply tokens
    tokens = (
        "FIELD",         # e.g. url:, content:
        "QUOTED_STRING", # "hello world"
        "TERM",          # standard search term
        "WILDCARD",      # wildcards terms, e.g. search*
        "AND",
        "OR",
        "NOT",
        "LPAREN",        # (
        "RPAREN",        # )
        "COLON",         # :
        "COMPARATOR",    # :>=, :>, :<, etc.
        "COMP_OP",       # >=
        "URL_FIELD"
    )

    precedence = (
        ('right', 'NOT'),
        ('left', 'AND'),
        ('left', 'OR'),
    )

    valid_fields: list[str] = ["id", "url", "status", "type", "size", "headers", "content", "time"]
    numeric_fields: list[str] = ["id", "status", "size", "time"]

    t_LPAREN = r"\("
    t_RPAREN = r"\)"
    t_ignore = " \t\n"

    def __init__(self) -> None:
        self.lexer: lex.LexToken | None = None
        self.parser: yacc.LRParser | None = None

    def build_lexer(self, **kwargs) -> None:
        self.lexer = lex.lex(module=self, **kwargs)

    def t_COMPARATOR(self, token: lex.LexToken) -> lex.LexToken:
        r":(?:>=|>|<=|<|!=|=)"
        token.value = token.value[1:]  # strip colon
        return token

    def t_COLON(self, token: lex.LexToken) -> lex.LexToken:
        r":"
        return token

    def t_QUOTED_STRING(self, token: lex.LexToken) -> lex.LexToken:
        r'"[^"]*"'
        token.value = token.value[1:-1]
        return token

    # precedence matters
    def t_URL_FIELD(self, token: lex.LexToken) -> lex.LexToken:
        r"url\s*:\s*((?:https?://)?[^\s]+)"
        token.type = "URL_FIELD"
        url_value = token.value[token.value.find(':')+1:].strip()
        token.value = ("url", url_value)
        return token

    # precedence matters
    def t_FIELD(self, token: lex.LexToken) -> lex.LexToken:
        r"[a-zA-Z_][a-zA-Z0-9_]*(?=\s*:)"
        if token.value not in self.valid_fields:
            raise ValueError(f"Invalid field: {token.value}. Valid fields are: {', '.join(self.valid_fields)}")
        return token

    def t_AND(self, token: lex.LexToken) -> lex.LexToken:
        r"AND\b"
        return token

    def t_OR(self, token: lex.LexToken) -> lex.LexToken:
        r"OR\b"
        return token

    def t_NOT(self, token: lex.LexToken) -> lex.LexToken:
        r"NOT\b"
        return token

    def t_WILDCARD(self, token: lex.LexToken) -> lex.LexToken:
        r"[a-zA-Z0-9_\.\-\/\+]+\*"
        token.value = token.value[:-1]
        return token

    def t_TERM(self, token: lex.LexToken) -> lex.LexToken:
        r"[a-zA-Z0-9_\.\-\/\+]+"
        if token.value == "AND" or token.value == "OR" or token.value == "NOT":
            token.type = token.value
        elif re.match(r"^[\w]+[\-_][\-_\w]+$", token.value, re.UNICODE):
            token.type = "QUOTED_STRING"
        return token

    def t_COMP_OP(self, token: lex.LexToken) -> lex.LexToken:
        r">=|>|<=|<|!=|="
        return token

    def t_error(self, token: lex.LexToken) -> None:
        logger.error(f"Illegal character '{token.value[0]}'")
        token.lexer.skip(1)

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

        # Convert numeric values for numeric fields
        if field and field in self.numeric_fields:
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    raise ValueError(f"Field {field} requires a numeric value, got: {value}")

        return value

    def __format_search_term(
        self,
        value: str | int | float,
        value_type: str,
        modifiers: list[str] | None = None
    ) -> str:
        """
        Format a search term based on its type and modifiers.

        Args:
            value: The search value
            value_type: Type of value ('term', 'phrase', 'wildcard')
            modifiers: List of modifiers (e.g., ['NOT'])
            for_sql: Whether this is for SQL parameter (affects formatting)

        Returns:
            Formatted search term string
        """
        modifiers = modifiers or []

        # based on subquery type
        if value_type == "phrase":
            return f'"{value.replace("*", " ").strip()}"'
        elif value_type == "wildcard":
            return f'"{value.replace("-", " ")}*"'
        else:  # term
            return str(value)

    def __validate_comparator_for_field(self, field: str, comparator: str) -> None:
        """
        Validate that a comparator is appropriate for the given field.

        Args:
            field: The field name
            comparator: The comparison operator

        Raises:
            ValueError: If comparator is invalid for the field type
        """
        if comparator != "=" and field not in self.numeric_fields:
            raise ValueError(f"Comparison operator '{comparator}' can only be used with numeric fields")

    def p_query(self, production: yacc.YaccProduction) -> None:
        """
        query : expression
        """
        production[0] = production[1]

    def p_expression_binary(self, production: yacc.YaccProduction) -> None:
        """
        expression : expression AND expression
                    | expression OR expression
                    | expression NOT expression
        """
        operator = production[2]
        left = production[1]
        right = production[3]

        # special handling for AND NOT pattern
        # A AND (NOT B), treat it like A NOT B
        if (operator == "AND" and isinstance(right, list) and
                len(right) == 1 and "NOT" in right[0].modifiers):
            # convert AND (NOT B) to binary NOT
            # remove NOT modifiers
            right[0].modifiers = [m for m in right[0].modifiers if m != "NOT"]
            operator = "NOT"

        if operator == "NOT":
            # NOT handled as set difference, left EXCEPT right
            # mark this as a special NOT relationship
            if isinstance(left, list) and isinstance(right, list):
                if left:
                    left[-1].operator = "NOT"
                production[0] = left + right
            elif isinstance(left, list):
                if left:
                    left[-1].operator = "NOT"
                production[0] = left + [self._create_subquery(right, None)]
            elif isinstance(right, list):
                production[0] = [self._create_subquery(left, "NOT")] + right
            else:
                # both terms, subqueries for both
                production[0] = [
                    self._create_subquery(left, "NOT"),
                    self._create_subquery(right, None)
                ]
        else:
            # handle AND and OR as before
            if isinstance(left, list) and isinstance(right, list):
                if left:
                    left[-1].operator = operator
                production[0] = left + right
            elif isinstance(left, list):
                if left:
                    left[-1].operator = operator
                production[0] = left + [self._create_subquery(right, operator)]
            elif isinstance(right, list):
                production[0] = [self._create_subquery(left, operator)] + right
            else:
                production[0] = [
                    self._create_subquery(left, operator),
                    self._create_subquery(right, None)
                ]

    def p_expression_not(self, production: yacc.YaccProduction) -> None:
        """
        expression : NOT expression
        """
        # Handle unary NOT (prefix NOT)
        expr = production[2]
        if isinstance(expr, list):
            for item in expr:
                item.modifiers.append("NOT")
            production[0] = expr
        else:
            subquery = self._create_subquery(expr, None)
            subquery.modifiers.append("NOT")
            production[0] = [subquery]

    def p_expression_group(self, production: yacc.YaccProduction) -> None:
        """
        expression : LPAREN expression RPAREN
        """
        production[0] = production[2]

    def p_expression_url_field(self, production: yacc.YaccProduction) -> None:
        """
        expression : URL_FIELD
        """
        field, value = production[1]  # Unpack the tuple (field, value)

        # check if URL ends with * for wildcard matching
        value_type = "term"
        if value.endswith('*'):
            value = value[:-1]  # remove wildcard
            value_type = "wildcard"

        production[0] = SearchSubquery(
            field=field,
            value=value,
            type=value_type,
            modifiers=[],
            operator=None
        )

    def p_value(self, production: yacc.YaccProduction) -> None:
        """
        value : TERM
              | WILDCARD
              | QUOTED_STRING
        """
        value = production[1]
        value_type = "term"

        if production.slice[1].type == "WILDCARD":
            value_type = "wildcard"
        elif production.slice[1].type == "QUOTED_STRING":
            value_type = "phrase"

        production[0] = {"value": value, "type": value_type}

    def p_expression_term(self, production: yacc.YaccProduction) -> None:
        """
        expression : value
        """
        term = production[1]
        production[0] = SearchSubquery(
            field=None,  # no field means fulltext search
            value=term["value"],
            type=term["type"],
            modifiers=[],
            operator=None
        )

    def p_expression_field_search(self, production: yacc.YaccProduction) -> None:
        """
        expression : FIELD COLON COMP_OP value
                | FIELD COLON value
                | FIELD COMPARATOR value
        """
        field = production[1]

        # determine comparator and value based on pattern
        if len(production) == 5:  # FIELD COLON COMP_OP value
            comparator = production[3]
            value = production[4]
        elif len(production) == 4:
            # check second token, COLON or COMPARATOR
            if production[2] == ":":  # FIELD COLON value
                comparator = "="  # default equals
                value = production[3]
            else:
                comparator = production[2]
                value = production[3]

        production[0] = self.__create_field_subquery(field, value, comparator)

    def __create_field_subquery(self, field: str, value_dict: dict[str, str], comparator: str = "=") -> SearchSubquery:
        """
        Helper method to create SearchSubquery for field searches.
        Consolidates all the validation and conversion logic.
        """
        self.__validate_comparator_for_field(field, comparator)
        processed_value = self.__process_field_value(field, value_dict)
        value_type = value_dict.get("type", "term") if isinstance(value_dict, dict) else "term"

        return SearchSubquery(
            field=field,
            value=processed_value,
            type=value_type,
            modifiers=[],
            operator=None,
            comparator=comparator
        )

    def p_error(self, production: yacc.YaccProduction | None) -> None:
        if production:
            logger.info(f"Syntax error at '{production.value}'")
        else:
            logger.info("Syntax error at EOF")

    def _create_subquery(self, term: SearchSubquery, operator: str | None) -> SearchSubquery:
        """
        Helper to create a SearchSubquery instance
        """
        if isinstance(term, SearchSubquery):
            subquery = SearchSubquery(
                field=term.field,
                value=term.value,
                type=term.type,
                modifiers=term.modifiers.copy(),
                operator=operator,
                comparator=term.comparator
            )
            return subquery
        else:
            raise ValueError(f"Unexpected term type: {type(term)}")

    def build_parser(self) -> None:
        """
        Build the parser
        """
        # the automatic parser.out debug generation, turn off explicitly
        self.parser = yacc.yacc(module=self, debug=False)

    def parse(self, query_string: str) -> list[SearchSubquery]:
        """
        Parse a query string into a list of SearchSubquery instances
        """
        if not hasattr(self, "lexer") or self.lexer is None:
            self.build_lexer()
        if not hasattr(self, "parser") or self.parser is None:
            self.build_parser()

        result = self.parser.parse(query_string, lexer=self.lexer)

        if isinstance(result, SearchSubquery):
            return [result]
        return result

    def __build_fulltext_expression(
        self,
        parsed_query: list[SearchSubquery],
        start_index: int,
        swap_values: dict[str, dict[str, str | int]] = {}
    ) -> dict[str, str | int]:
        """
        Build a single FTS expression from many fulltext queries with their booleans.

        Args:
            parsed_query: List of SearchSubquery objects
            start_index: Starting position in the list
            swap_values: Dictionary for value replacement

        Returns:
            dict with 'expression', 'next_index' keys
        """
        terms = []
        current_index = start_index

        while current_index < len(parsed_query) and not parsed_query[current_index].field:
            subquery = parsed_query[current_index]
            processed_value = self.__process_field_value(None, subquery.value, swap_values)
            formatted_term = self.__format_search_term(processed_value, subquery.type, subquery.modifiers)
            terms.append(formatted_term)

            # add operator if not the last term and there's a next term
            if (current_index < len(parsed_query) - 1 and subquery.operator and current_index + 1 <
                    len(parsed_query) and not parsed_query[current_index + 1].field):
                terms.append(subquery.operator)

            current_index += 1

            # stop if next item is a field search or we've reached the end
            if current_index >= len(parsed_query) or parsed_query[current_index].field:
                break

        return {
            "expression": " ".join(terms) if terms else "",
            "next_index": current_index
        }

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

            if not subquery.field:  # fulltext section
                # group consecutive fulltext terms with their operators
                fulltext_expr = self.__build_fulltext_expression(parsed_query, current_index, swap_values)
                if fulltext_expr["expression"]:
                    param_name = param_manager.add_param(fulltext_expr["expression"])
                    safe_sql_fulltext = subquery.get_safe_sql_field("fulltext")
                    query_parts.append(f"{safe_sql_fulltext} MATCH :{param_name}")
                    current_index = fulltext_expr["next_index"]
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
                if field in self.numeric_fields:
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
                    elif field == "type":
                        # type needs exact match
                        param_name = param_manager.add_param(processed_value)
                        sql_part += f"{safe_sql_field} = :{param_name}"
                    elif value_type == "phrase":
                        formatted_term = self.__format_search_term(processed_value, value_type)
                        param_name = param_manager.add_param(formatted_term)
                        sql_part += f"{safe_sql_field} MATCH :{param_name}"
                    else:
                        # standard fts query
                        param_name = param_manager.add_param(processed_value)
                        safe_sql_fulltext = subquery.get_safe_sql_field("fulltext")
                        sql_part += f"{safe_sql_fulltext} MATCH :{param_name}"

                query_parts.append(sql_part)
                current_index += 1

            # add operator between clauses
            if current_index < len(parsed_query):
                # look at the previous subquery's operator to determine how to connect
                previous_subquery = parsed_query[current_index - 1] if current_index > 0 else None
                if previous_subquery and previous_subquery.operator:
                    op = previous_subquery.operator
                else:
                    op = "AND"  # default
                query_parts.append(op)

        return query_parts, param_manager.get_params()

    def get_fulltext_terms(self, query: str) -> list[str]:
        """
        Extract fulltext search terms from a query string.
        Returns list of search terms suitable for snippet extraction.
        """
        parsed_query = self.parse(query)
        search_terms = []
        fulltext_fields = ("content", "headers", "fulltext", "", None)

        # prepare for match, lowercase and eliminate wildcards
        for subquery in parsed_query:
            if subquery.field in fulltext_fields:
                term = str(subquery.value).lower().strip("*")
                if term:
                    search_terms.append(term)

        return search_terms
