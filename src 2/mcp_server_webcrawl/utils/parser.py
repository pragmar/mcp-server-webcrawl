import re

from ply import lex
from ply import yacc
from logging import Logger

from mcp_server_webcrawl.models.resources import RESOURCES_DEFAULT_FIELD_MAPPING
from mcp_server_webcrawl.utils.logger import get_logger

logger: Logger = get_logger()

class SearchSubquery:
    """
    Subquery component in a structured search.

    These are grouped into an ordered list, and are the basis the SQL query.
    """

    def __init__(
        self,
        field: str | None,
        value: str | int,
        type: str,
        modifiers: list[str] | None,
        operator: str | None,
        comparator: str = "=",
        group: int | None = None,
    ):
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
        self.group: int | None = group

    def get_safe_sql_field(self, field: str) -> str:
        if field in RESOURCES_DEFAULT_FIELD_MAPPING:
            return RESOURCES_DEFAULT_FIELD_MAPPING[field]
        else:
            logger.error(f"Field {field} failed to validate.")
            raise Exception(f"Unknown database field {field}")

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
            "comparator": self.comparator,
            "group": self.group,
        }

class SearchLexer:
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

    valid_fields: list[str] = ["id", "url", "status", "type", "size", "headers", "content", "time"]

    t_LPAREN = r"\("
    t_RPAREN = r"\)"
    t_ignore = " \t\n"

    def __init__(self):
        self.lexer = lex.lex(module=self)

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
        # dedicated t_AND, t_OR, t_NOT to handle those
        # this is fts5 workaround, -_ are tokenizer preserves
        if re.match(r"^[\w]+[\-_][\-_\w]+$", token.value, re.UNICODE):
            token.type = "QUOTED_STRING"
        return token

    def t_COMP_OP(self, token: lex.LexToken) -> lex.LexToken:
        r">=|>|<=|<|!=|="
        return token

    def t_error(self, token: lex.LexToken) -> None:
        logger.error(f"Illegal character '{token.value[0]}'")
        token.lexer.skip(1)

class SearchParser:
    tokens = SearchLexer.tokens

    precedence = (
        ('right', 'NOT'),
        ('left', 'AND'),
        ('left', 'OR'),
    )

    numeric_fields: list[str] = ["id", "status", "size", "time"]

    def __init__(self, lexer):
        self.lexer = lexer
        self.parser = yacc.yacc(module=self, debug=False)

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
                production[0] = left + [self.__create_subquery(right, None)]
            elif isinstance(right, list):
                production[0] = [self.__create_subquery(left, "NOT")] + right
            else:
                # both terms, subqueries for both
                production[0] = [
                    self.__create_subquery(left, "NOT"),
                    self.__create_subquery(right, None)
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
                production[0] = left + [self.__create_subquery(right, operator)]
            elif isinstance(right, list):
                production[0] = [self.__create_subquery(left, operator)] + right
            else:
                production[0] = [
                    self.__create_subquery(left, operator),
                    self.__create_subquery(right, None)
                ]

    def p_expression_not(self, production: yacc.YaccProduction) -> None:
        """
        expression : NOT expression
        """
        # handle unary NOT (prefix NOT)
        expr = production[2]
        if isinstance(expr, list):
            for item in expr:
                item.modifiers.append("NOT")
            production[0] = expr
        else:
            subquery = self.__create_subquery(expr, None)
            subquery.modifiers.append("NOT")
            production[0] = [subquery]

    def p_expression_group(self, production: yacc.YaccProduction) -> None:
        """
        expression : LPAREN expression RPAREN
        """
        # production[0] = production[2]
        expr = production[2]
        group_id = id(production)  # Unique ID for this parentheses group

        # Mark all subqueries in this expression with the group
        if isinstance(expr, list):
            for subquery in expr:
                subquery.group = group_id
        else:
            expr.group = group_id

        production[0] = expr

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

    def __create_field_subquery(self, field: str, value_dict: dict[str, str] | str | int, comparator: str = "=") -> SearchSubquery:
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

    def __create_subquery(self, term, operator: str | None):
        """
        Helper to create a SearchSubquery instance.
        """
        assert isinstance(term, SearchSubquery), "__create_subquery expected a SearchSubquery instance"
        return SearchSubquery(
            field=term.field,
            value=term.value,
            type=term.type,
            modifiers=term.modifiers.copy(),
            operator=operator,
            comparator=term.comparator,
            group=term.group,
        )

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

        if field and field in self.numeric_fields:
            try:
                return int(value)
            except ValueError:
                try:
                    return float(value)
                except ValueError:
                    raise ValueError(f"Field {field} requires a numeric value, got: {value}")

        return value

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

    def p_error(self, production: yacc.YaccProduction | None) -> None:
        if production:
            logger.info(f"Syntax error at '{production.value}'")
        else:
            logger.info("Syntax error at EOF")
