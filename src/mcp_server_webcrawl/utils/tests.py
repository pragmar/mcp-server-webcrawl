import unittest
from mcp_server_webcrawl.utils.search import SearchQueryParser, SearchSubquery

class TestSearchQueryParser(unittest.TestCase):

    def setUp(self):
        """
        Set up a parser instance for each test
        """
        self.parser = SearchQueryParser()

    def test_simple_term(self):
        """
        Simple single term search
        """
        query = "hello"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].field, None)
        self.assertEqual(result[0].value, "hello")
        self.assertEqual(result[0].type, "term")
        self.assertEqual(result[0].operator, None)

    def test_quoted_phrase(self):
        """
        Quoted phrase search
        """
        query = '"hello world"'
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].field, None)
        self.assertEqual(result[0].value, "hello world")
        self.assertEqual(result[0].type, "phrase")

    def test_wildcard_term(self):
        """
        Wildcard term search
        """
        query = "search*"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].field, None)
        self.assertEqual(result[0].value, "search")
        self.assertEqual(result[0].type, "wildcard")

    def test_field_term(self):
        """
        Field-specific term search
        """
        query = "url:example.com"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].field, "url")
        self.assertEqual(result[0].value, "example.com")
        self.assertEqual(result[0].type, "term")

    def test_field_numeric(self):
        """
        Field with numeric value
        """
        query = "status:404"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].field, "status")
        self.assertEqual(result[0].value, 404)
        self.assertEqual(result[0].type, "term")

    def test_field_quoted(self):
        """
        Field with quoted value
        """
        query = 'content:"hello world"'
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].field, "content")
        self.assertEqual(result[0].value, "hello world")
        self.assertEqual(result[0].type, "phrase")

    def test_field_wildcard(self):
        """
        Field with wildcard value
        """
        query = "url:example*"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].field, "url")
        self.assertEqual(result[0].value, "example")
        self.assertEqual(result[0].type, "wildcard")

    def test_simple_and(self):
        """
        Simple AND query
        """
        query = "hello AND world"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, "hello")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].value, "world")
        self.assertEqual(result[1].operator, None)

    def test_simple_or(self):
        """
        Simple OR query
        """
        query = "hello OR world"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, "hello")
        self.assertEqual(result[0].operator, "OR")
        self.assertEqual(result[1].value, "world")
        self.assertEqual(result[1].operator, None)

    def test_simple_not(self):
        """
        Simple NOT query
        """
        query = "NOT hello"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].value, "hello")
        self.assertTrue('NOT' in result[0].modifiers)

    def test_and_with_fields(self):
        """
        AND with field specifiers
        """
        query = "content:hello AND url:example.com"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].field, "content")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].field, "url")

    def test_or_with_fields(self):
        """
        OR with field specifiers
        """
        query = "status:404 OR status:500"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].field, "status")
        self.assertEqual(result[0].value, 404)
        self.assertEqual(result[0].operator, "OR")
        self.assertEqual(result[1].field, "status")
        self.assertEqual(result[1].value, 500)

    def test_not_with_field(self):
        """
        NOT with field specifier
        """
        query = "NOT status:404"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].field, "status")
        self.assertEqual(result[0].value, 404)
        self.assertTrue('NOT' in result[0].modifiers)

    def test_simple_parentheses(self):
        """
        Simple expression with parentheses
        """
        query = "(hello AND world)"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].value, "hello")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].value, "world")

    def test_complex_parentheses(self):
        """
        Complex expression with nested parentheses
        """
        query = "(hello AND (world OR planet))"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].value, "hello")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].value, "world")
        self.assertEqual(result[1].operator, "OR")
        self.assertEqual(result[2].value, "planet")

    def test_mixed_operators(self):
        """
        Query with mixed operators
        """
        query = "hello AND world OR planet"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].value, "hello")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].value, "world")
        self.assertEqual(result[1].operator, "OR")
        self.assertEqual(result[2].value, "planet")

    def test_mixed_with_parentheses(self):
        """
        Mixed operators with parentheses for precedence
        """
        query = "hello AND (world OR planet)"
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].value, "hello")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].value, "world")
        self.assertEqual(result[1].operator, "OR")
        self.assertEqual(result[2].value, "planet")

    def test_complex_nested_query(self):
        """
        Complex nested query with multiple operators
        """
        query = '(content:"error message" AND (status:404 OR status:500)) AND NOT url:example.com'
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0].field, "content")
        self.assertEqual(result[0].value, "error message")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].field, "status")
        self.assertEqual(result[1].value, 404)
        self.assertEqual(result[1].operator, "OR")
        self.assertEqual(result[2].field, "status")
        self.assertEqual(result[2].value, 500)
        self.assertEqual(result[2].operator, "NOT")
        self.assertEqual(result[3].field, "url")
        self.assertEqual(result[3].value, "example.com")

    def test_all_features_combined(self):
        """
        Comprehensive test with all features combined
        """
        query = 'content:"critical error" AND (status:500 OR type:html) AND NOT url:example* AND size:1024'
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 5)

        # subquery (content:"critical error")
        self.assertEqual(result[0].field, "content")
        self.assertEqual(result[0].value, "critical error")
        self.assertEqual(result[0].type, "phrase")
        self.assertEqual(result[0].operator, "AND")

        # subquery (status:500)
        self.assertEqual(result[1].field, "status")
        self.assertEqual(result[1].value, 500)
        self.assertEqual(result[1].operator, "OR")

        # subquery (type:html)
        self.assertEqual(result[2].field, "type")
        self.assertEqual(result[2].value, "html")
        self.assertEqual(result[2].operator, "AND")

        # subquery (NOT url:example*)
        self.assertEqual(result[3].field, "url")
        self.assertEqual(result[3].value, "example")
        self.assertEqual(result[3].type, "wildcard")
        self.assertTrue('NOT' in result[3].modifiers)
        self.assertEqual(result[3].operator, "AND")

        # subquery (size:1024)
        self.assertEqual(result[4].field, "size")
        self.assertEqual(result[4].value, 1024)
        self.assertEqual(result[4].operator, None)

    def test_to_sqlite_fts(self):
        """
        Test conversion to SQLite FTS format
        """
        query = 'content:"error" AND status:404'
        result: SearchSubquery= self.parser.parse(query)

        query_parts, params = self.parser.to_sqlite_fts(result)

        self.assertEqual(len(query_parts), 3)
        self.assertEqual(query_parts[0], "ResourcesFullText.Content MATCH :query0")
        self.assertEqual(query_parts[1], "AND")
        self.assertEqual(query_parts[2], "Resources.Status = :query1")

        self.assertEqual(len(params), 2)
        self.assertEqual(params["query0"], '"error"')
        self.assertEqual(params["query1"], 404)
