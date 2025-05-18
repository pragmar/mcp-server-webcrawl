from ply import lex
from ply import yacc
from logging import Logger

from mcp_server_webcrawl.models.resources import RESOURCES_DEFAULT_FIELD_MAPPING
from mcp_server_webcrawl.settings import DEBUG, DATA_DIRECTORY
from mcp_server_webcrawl.utils.logger import get_logger

logger: Logger = get_logger()

class SearchSubquery:

    """
    Subquery component in a structured search expression.

    These are grouped into an ordered list, and are the basis the SQL query.
    """

    def __init__(self,
            field: str, value: str | int, type: str,
            modifiers: list[str], operator: str,
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

        self.field: str = field
        self.value: str | int = value
        self.type: str = type
        self.modifiers: list[str] = modifiers or []
        self.operator: str | None = operator or None
        self.comparator: str = comparator

    def get_safe_sql_field(self, field: str):
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

    valid_fields = ["id", "url", "status", "type", "size", "headers", "content", "time"]
    numeric_fields = ["id", "status", "size", "time"]
    operators = {
        "AND": {"precedence": 2, "associativity": "left"},
        "OR": {"precedence": 1, "associativity": "left"},
        "NOT": {"precedence": 3, "associativity": "right"},
    }

    t_LPAREN = r"\("
    t_RPAREN = r"\)"

    def build_lexer(self, **kwargs):
        self.lexer = lex.lex(module=self, **kwargs)

    def t_COMPARATOR(self, t):
        r":(?:>=|>|<=|<|!=|=)"
        t.value = t.value[1:]  # strip colon
        return t

    def t_COLON(self, t):
        r":"
        return t

    def t_QUOTED_STRING(self, t):
        r'"[^"]*"'
        t.value = t.value[1:-1]
        return t

    # precedence matters
    def t_URL_FIELD(self, t):
        r"url\s*:\s*((?:https?://)?[^\s]+)"
        t.type = "URL_FIELD"
        url_value = t.value[t.value.find(':')+1:].strip()
        t.value = ("url", url_value)
        return t

    # precedence matters
    def t_FIELD(self, t):
        r"[a-zA-Z_][a-zA-Z0-9_]*(?=\s*:)"
        if t.value not in self.valid_fields:
            raise ValueError(f"Invalid field: {t.value}. Valid fields are: {', '.join(self.valid_fields)}")
        return t

    def t_AND(self, t):
        r"AND\b"
        return t

    def t_OR(self, t):
        r"OR\b"
        return t

    def t_NOT(self, t):
        r"NOT\b"
        return t

    def t_WILDCARD(self, t):
        r"[a-zA-Z0-9_\.\-\/\+]+\*"
        t.value = t.value[:-1]
        return t

    def t_TERM(self, t):
        r"[a-zA-Z0-9_\.\-\/\+]+"
        if t.value == "AND" or t.value == "OR" or t.value == "NOT":
            t.type = t.value
        return t

    def t_COMP_OP(self, t):
        r">=|>|<=|<|!=|="
        return t

    def t_error(self, t):
        logger.error(f"Illegal character '{t.value[0]}'")
        t.lexer.skip(1)

    t_ignore = " \t\n"



    def p_query(self, p):
        """
        query : expression
        """
        p[0] = p[1]

    def p_expression_binary(self, p):
        """
        expression : expression AND expression
                    | expression OR expression
        """
        operator = p[2]
        left = p[1]
        right = p[3]

        if isinstance(left, list) and isinstance(right, list):
            if left:
                left[-1].operator = operator
            p[0] = left + right
        elif isinstance(left, list):
            if left:
                left[-1].operator = operator
            p[0] = left + [self._create_subquery(right, operator)]
        elif isinstance(right, list):
            p[0] = [self._create_subquery(left, operator)] + right
        else:
            # both terms, create subqueries for both
            p[0] = [
                self._create_subquery(left, operator),
                self._create_subquery(right, None)  # Last term has no operator
            ]

    def p_expression_not(self, p):
        """
        expression : NOT expression
        """
        # handle NOT by applying NOT to each subquery
        expr = p[2]
        if isinstance(expr, list):
            for item in expr:
                item.modifiers.append("NOT")
            p[0] = expr
        else:
            subquery = self._create_subquery(expr, None)
            subquery.modifiers.append("NOT")
            p[0] = [subquery]

    def p_expression_group(self, p):
        """
        expression : LPAREN expression RPAREN
        """
        p[0] = p[2]

    def p_expression_url_field(self, p):
        """
        expression : URL_FIELD
        """
        field, value = p[1]  # Unpack the tuple (field, value)

        # Check if the URL ends with * for wildcard matching
        value_type = "term"
        if value.endswith('*'):
            value = value[:-1]  # Remove the wildcard
            value_type = "wildcard"

        p[0] = SearchSubquery(
            field=field,
            value=value,
            type=value_type,
            modifiers=[],
            operator=None
        )

    def p_expression_field_spaced_comparison(self, p):
        """
        expression : FIELD COLON COMP_OP value
                    | FIELD COLON value
        """
        field = p[1]

        if len(p) == 5:  # FIELD COLON COMP_OP value
            comparator = p[3]
            value = p[4]
        else:  # FIELD COLON value
            comparator = "="  # Default to equals
            value = p[3]

        value_data = value["value"]
        value_type = value["type"]

        if comparator != "=" and field not in self.numeric_fields:
            raise ValueError(f"Comparison operator '{comparator}' can only be used with numeric fields")

        if field in self.numeric_fields:
            try:
                value_data = int(value_data)
            except ValueError:
                try:
                    value_data = float(value_data)
                except ValueError:
                    raise ValueError(f"Field {field} requires a numeric value, got: {value_data}")

        p[0] = SearchSubquery(
            field=field,
            value=value_data,
            type=value_type,
            modifiers=[],
            operator=None,
            comparator=comparator
        )

    def p_value(self, p):
        """
        value : TERM
              | WILDCARD
              | QUOTED_STRING
        """
        value = p[1]
        value_type = "term"

        if p.slice[1].type == "WILDCARD":
            value_type = "wildcard"
        elif p.slice[1].type == "QUOTED_STRING":
            value_type = "phrase"

        p[0] = {"value": value, "type": value_type}

    def p_expression_term(self, p):
        """
        expression : value
        """
        term = p[1]
        p[0] = SearchSubquery(
            field=None,  # no field means fulltext search
            value=term["value"],
            type=term["type"],
            modifiers=[],
            operator=None
        )

    def p_expression_field_comparison(self, p):
        """
        expression : FIELD COMPARATOR value
        """
        field = p[1]
        comparator = p[2]
        value = p[3]

        value_data = value["value"]
        value_type = value["type"]

        if comparator != "=" and field not in self.numeric_fields:
            raise ValueError(f"Comparison operator '{comparator}' can only be used with numeric fields")

        if field in self.numeric_fields:
            try:
                value_data = int(value_data)
            except ValueError:
                try:
                    value_data = float(value_data)
                except ValueError:
                    raise ValueError(f"Field {field} requires a numeric value, got: {value_data}")

        p[0] = SearchSubquery(
            field=field,
            value=value_data,
            type=value_type,
            modifiers=[],
            operator=None,
            comparator=comparator
        )

    def p_error(self, p):
        if p:
            logger.info(f"Syntax error at '{p.value}'")
        else:
            logger.info("Syntax error at EOF")

    def _create_subquery(self, term, operator):
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

    def build_parser(self):
        """
        Build the parser
        """

        # the automatic parser.out debug generation feels unpredictable, turn off explicitly
        self.parser = yacc.yacc(module=self, debug=False)

    def parse(self, query_string):
        """
        Parse a query string into a list of SearchSubquery instances
        """
        if not hasattr(self, "lexer"):
            self.build_lexer()
        if not hasattr(self, "parser"):
            self.build_parser()

        result = self.parser.parse(query_string, lexer=self.lexer)

        if isinstance(result, SearchSubquery):
            return [result]
        return result

    def to_sqlite_fts(self, parsed_query: list[SearchSubquery], swap_values: dict={}):
        """
        Convert the parsed query to SQLite FTS5 compatible WHERE clause components.
        Returns a tuple of (query_parts, params) where query_parts is a list of SQL
        conditions and params is a dictionary of parameter values with named parameters.
        """
        query_parts = []
        params = {}
        param_counter = 0

        subquery: SearchSubquery
        # for subquery in parsed_query:
        for i, subquery in enumerate(parsed_query):

            sql_part = ""
            field = subquery.field
            value = subquery.value

            # replace value if requested
            if field in swap_values and value in swap_values[field]:
                value = swap_values[field][value]

            value_type = subquery.type
            modifiers = subquery.modifiers
            operator = subquery.operator

            # unique parameter names for parameterized query
            param_name = f"query{param_counter}"
            param_counter += 1

            # NOT modifier if present
            if "NOT" in modifiers:
                sql_part += "NOT "

            if field:
                safe_sql_field = subquery.get_safe_sql_field(field)
                if field in self.numeric_fields:
                    sql_part += f"{safe_sql_field} {subquery.comparator} :{param_name}"
                    params[param_name] = value
                else:

                    if field == "url" or field == "headers":
                        # Use LIKE for certain field searches instead of MATCH, maximize the hits
                        # with %LIKE%. Think of https://example.com/logo.png?cache=20250112
                        # and a search of url: *.png and the 10s of ways broader match is better
                        # fit for intention
                        safe_sql_field = subquery.get_safe_sql_field(field)
                        sql_part += f"{safe_sql_field} LIKE :{param_name}"
                        # strip wildcards whether wildcard or not
                        unwildcarded_value = value.strip("*")
                        params[param_name] = f"%{unwildcarded_value}%"
                    elif field == "type":
                        # type needs exact match
                        sql_part += f"{safe_sql_field} = :{param_name}"
                        params[param_name] = value
                    elif value_type == "phrase":
                        sql_part += f"{safe_sql_field} MATCH :{param_name}"
                        params[param_name] = f'"{value}"'
                    else:
                        # standard fts query
                        safe_sql_fulltext = subquery.get_safe_sql_field("fulltext")
                        sql_part += f"{safe_sql_fulltext} MATCH :{param_name}"
                        params[param_name] = value
            else:
                # default fulltext search across all searchable fields
                safe_sql_fulltext = subquery.get_safe_sql_field("fulltext")
                if value_type == "wildcard":
                    sql_part += f"{safe_sql_fulltext} MATCH :{param_name}"
                    params[param_name] = f"{value}*"
                elif value_type == "phrase":
                    sql_part += f"{safe_sql_fulltext} MATCH :{param_name}"
                    params[param_name] = f'"{value}"'
                else:
                    sql_part += f"{safe_sql_fulltext} MATCH :{param_name}"
                    params[param_name] = value

            query_parts.append(sql_part)

            # only operator if it's not the last element
            if operator and i < len(parsed_query) - 1:
                query_parts.append(operator)

        return query_parts, params
