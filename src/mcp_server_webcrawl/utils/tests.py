import random
import sqlite3
import unittest

from contextlib import closing

from mcp_server_webcrawl.crawlers.base.indexed import IndexedManager
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
        self.assertEqual(result[1].operator, None)

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
        self.assertEqual(result[2].operator, None)

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
        self.assertEqual(result[2].operator, None)

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
        self.assertEqual(result[2].operator, None)

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
        self.assertEqual(result[3].operator, None)

    def test_all_features_combined(self):
        """
        Comprehensive test with all features combined
        """
        query = 'content:"critical error" AND (status:500 OR type:html) AND NOT url:example* AND size:1024'
        result: SearchSubquery= self.parser.parse(query)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0].field, "content")
        self.assertEqual(result[0].value, "critical error")
        self.assertEqual(result[0].type, "phrase")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].field, "status")
        self.assertEqual(result[1].value, 500)
        self.assertEqual(result[1].operator, "OR")
        self.assertEqual(result[2].field, "type")
        self.assertEqual(result[2].value, "html")
        # AND NOT url converts to the binary form, type NOT url
        self.assertEqual(result[2].operator, "NOT")
        self.assertEqual(result[3].field, "url")
        self.assertEqual(result[3].value, "example")
        self.assertEqual(result[3].type, "wildcard")
        self.assertFalse('NOT' in result[3].modifiers)
        self.assertEqual(result[3].operator, "AND")
        self.assertEqual(result[4].field, "size")
        self.assertEqual(result[4].value, 1024)
        self.assertEqual(result[4].operator, None)
        # prefix NOT takes one operand, it used to take url AND size
        self.assertFalse('NOT' in result[4].modifiers)

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

    def test_operator_assignment_bug(self):
        """
        Test that exposes the double operator assignment bug.
        Query: "term1 AND term2 OR term3" should create:
        [term1(op=AND), term2(op=OR), term3(op=None)]

        Were the bug present, term3 would incorrectly get operator == OR
        """
        from mcp_server_webcrawl.utils.parser import SearchLexer, SearchParser

        lexer = SearchLexer()
        parser = SearchParser(lexer)
        query = "term1 AND term2 OR term3"
        result = parser.parser.parse(query, lexer=lexer.lexer)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].value, "term1")
        self.assertEqual(result[0].operator, "AND")
        self.assertEqual(result[1].value, "term2")
        self.assertEqual(result[1].operator, "OR")
        self.assertEqual(result[2].value, "term3")
        self.assertEqual(result[2].operator, None)

    def test_chained_operator_last_term(self):
        """
        A left-associative chain (A OR B OR C) must leave the last term with no operator.
        A dangling OR there joins whatever clause follows, the default status >= 100
        included, and the query returns every resource on the site.
        """
        for query, operator in [
            ("id: 1 OR id: 2 OR id: 3", "OR"),
            ("id: 1 OR id: 2 OR id: 3 OR id: 4", "OR"),
            ("hello OR world OR planet", "OR"),
            ("hello AND world AND planet", "AND"),
            ("url: a OR url: b OR url: c", "OR"),
        ]:
            result = self.parser.parse(query)
            self.assertEqual([subquery.operator for subquery in result[:-1]], [operator] * (len(result) - 1), query)
            self.assertEqual(result[-1].operator, None, f"dangling operator on last term: {query}")

    def test_chained_or_to_sqlite_fts(self):
        """
        Chained non-fts ORs end on a condition, never an operator.
        """
        result = self.parser.parse("id: 1 OR id: 2 OR id: 3 OR id: 4")
        query_parts, params = self.parser.to_sqlite_fts(result)
        self.assertEqual(query_parts, [
            "ResourcesFullText.Id = :query0", "OR",
            "ResourcesFullText.Id = :query1", "OR",
            "ResourcesFullText.Id = :query2", "OR",
            "ResourcesFullText.Id = :query3",
        ])
        self.assertEqual(params, {"query0": 1, "query1": 2, "query2": 3, "query3": 4})

    def test_group_ids_unique(self):
        """
        Each parentheses group gets its own id. ply reuses one production object per
        parse, so id(production) handed every group in a query the same one.
        """
        result = self.parser.parse("(hello OR world) AND (planet OR moon)")
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0].groups, result[1].groups)
        self.assertEqual(result[2].groups, result[3].groups)
        self.assertNotEqual(result[1].groups, result[2].groups)
        self.assertEqual(len(result[0].groups), 1)
        self.assertEqual(len(result[2].groups), 1)

    def test_group_paths_nested(self):
        """
        Group paths run outermost first, and group stays the outermost.
        """
        result = self.parser.parse("(hello AND (world OR planet)) OR moon")
        self.assertEqual(len(result), 4)
        self.assertEqual(len(result[0].groups), 1)
        self.assertEqual(len(result[1].groups), 2)
        self.assertEqual(result[1].groups, result[2].groups)
        self.assertEqual(result[1].groups[0], result[0].groups[0])
        self.assertEqual(result[1].group, result[0].group)
        self.assertEqual(result[3].groups, ())
        self.assertEqual(result[3].group, None)

    def test_group_paths_survive_copy(self):
        """
        Operators copy subqueries (__create_subquery), the group path must come along.
        """
        result = self.parser.parse("(id: 1 OR id: 2) AND id: 3")
        self.assertEqual(result[0].groups, result[1].groups)
        self.assertEqual(len(result[0].groups), 1)
        self.assertEqual(result[2].groups, ())
        self.assertEqual(result[0].to_dict()["groups"], list(result[0].groups))

    def test_grouped_sql_parentheses(self):
        """
        Groups over non-fts fields are parenthesized in SQL. Without them SQL's own
        AND-over-OR precedence regroups the clauses, and a MATCH lands under an OR,
        which sqlite refuses ("unable to use function MATCH in the requested context").
        """
        result = self.parser.parse("(url: a/cli* OR url: a/co* OR url: a/ao*) AND (trial OR community OR pro)")
        query_parts, params = self.parser.to_sqlite_fts(result)
        self.assertEqual(query_parts, [
            "(ResourcesFullText.Url LIKE :query0", "OR",
            "ResourcesFullText.Url LIKE :query1", "OR",
            "ResourcesFullText.Url LIKE :query2)", "AND",
            "ResourcesFullText MATCH :query3",
        ])
        self.assertEqual(params["query3"], "trial OR community OR pro")

    def test_grouped_sql_adjacent(self):
        """
        Adjacent groups over the same field stay two groups.
        """
        result = self.parser.parse("(id: 1 OR id: 2) AND (id: 3 OR id: 4)")
        query_parts, _ = self.parser.to_sqlite_fts(result)
        self.assertEqual(query_parts, [
            "(ResourcesFullText.Id = :query0", "OR",
            "ResourcesFullText.Id = :query1)", "AND",
            "(ResourcesFullText.Id = :query2", "OR",
            "ResourcesFullText.Id = :query3)",
        ])

    def test_grouped_sql_not(self):
        """
        A binary NOT after a group applies to the whole group.
        """
        result = self.parser.parse("(url: a OR url: b) NOT url: c")
        query_parts, _ = self.parser.to_sqlite_fts(result)
        self.assertEqual(query_parts, [
            "(ResourcesFullText.Url LIKE :query0", "OR",
            "ResourcesFullText.Url LIKE :query1)", "AND",
            "NOT ResourcesFullText.Url LIKE :query2",
        ])

    def test_grouped_sql_nested(self):
        """
        Nested groups across non-fts fields keep every level.
        """
        result = self.parser.parse("((id: 1 OR id: 2) AND status: 200) OR id: 3")
        query_parts, _ = self.parser.to_sqlite_fts(result)
        self.assertEqual(query_parts, [
            "((ResourcesFullText.Id = :query0", "OR",
            "ResourcesFullText.Id = :query1)", "AND",
            "Resources.Status = :query2)", "OR",
            "ResourcesFullText.Id = :query3",
        ])

    def test_fts_querystring_groups(self):
        """
        An all-fulltext query packs into one fts5 querystring, where AND also outranks
        OR. Compound operands are parenthesized, so the string keeps the query's
        structure whatever fts5's own precedence would have done with it.
        """
        cases = [
            ("hello OR world OR planet", "hello OR world OR planet"),
            ("(hello OR world) AND (planet OR moon)", "(hello OR world) AND (planet OR moon)"),
            ("(hello AND (world OR planet))", "hello AND (world OR planet)"),
            ("((hello OR world) AND planet) OR moon", "((hello OR world) AND planet) OR moon"),
            ("hello AND (world OR planet)", "hello AND (world OR planet)"),
            ("hello AND world OR planet", "(hello AND world) OR planet"),
            ("hello OR world AND planet", "hello OR (world AND planet)"),
            ("(crawler OR privacy) AND collaborations", "(crawler OR privacy) AND collaborations"),
            ("(crawler OR privacy OR moffitor)", "crawler OR privacy OR moffitor"),
        ]
        for query, querystring in cases:
            result = self.parser.parse(query)
            query_parts, params = self.parser.to_sqlite_fts(result)
            self.assertEqual(query_parts, ["ResourcesFullText MATCH :query0"], query)
            self.assertEqual(params["query0"], querystring, query)

    def test_parentheses_balanced(self):
        """
        Whatever the mix of fields, groups and operators, SQL and fts parentheses balance.
        """
        queries = [
            "(a OR b) AND (c OR d) AND (e OR f)",
            "((a OR b) AND (c OR (d AND e))) OR f",
            "(url: a OR (b AND status: 200)) AND (id: 1 OR c)",
            "((url: a) AND (url: b OR (url: c AND id: 2)))",
            "(type: html OR type: img) AND (url: a OR url: b) NOT (c OR d)",
            "(a) AND ((b)) AND (((c)))",
            '(content:"error message" AND (status:404 OR status:500)) AND NOT url:example.com',
            "(headers: text OR headers: json) AND (status: 200 OR status: 304)",
        ]
        for query in queries:
            result = self.parser.parse(query)
            query_parts, params = self.parser.to_sqlite_fts(result)
            sql: str = " ".join(query_parts)
            for text in [sql] + [value for value in params.values() if isinstance(value, str)]:
                depth: int = 0
                for character in text:
                    depth += 1 if character == "(" else -1 if character == ")" else 0
                    self.assertGreaterEqual(depth, 0, f"closed before opened in {text!r} ({query})")
                self.assertEqual(depth, 0, f"unbalanced {text!r} ({query})")

    def test_prefix_not_reach(self):
        """
        Prefix NOT takes one operand. It had the lowest precedence, so NOT a AND b
        parsed as NOT (a AND b), then negated a and b separately.
        """
        result = self.parser.parse("NOT url: x AND size: 1024")
        self.assertEqual(len(result), 2)
        self.assertIn("NOT", result[0].modifiers)
        self.assertNotIn("NOT", result[1].modifiers)
        self.assertEqual(result[1].negated_groups, frozenset())
        query_parts, _ = self.parser.to_sqlite_fts(result)
        self.assertEqual(query_parts, ["NOT ResourcesFullText.Url LIKE :query0", "AND", "Resources.Size = :query1"])

        result = self.parser.parse("NOT hello AND world")
        query_parts, params = self.parser.to_sqlite_fts(result)
        self.assertEqual(query_parts, ["ResourcesFullText MATCH :query0"])
        self.assertEqual(params["query0"], "world NOT hello")

    def test_not_group_de_morgan(self):
        """
        NOT over a group negates the group, NOT (A OR B), never NOT A OR NOT B.
        """
        result = self.parser.parse("NOT (url: a OR url: b)")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].negated_groups, result[1].negated_groups)
        self.assertEqual(len(result[0].negated_groups), 1)
        self.assertNotIn("NOT", result[0].modifiers)
        self.assertNotIn("NOT", result[1].modifiers)
        self.assertEqual(result[0].to_dict()["negated_groups"], sorted(result[0].negated_groups))
        query_parts, _ = self.parser.to_sqlite_fts(result)
        self.assertEqual(query_parts, [
            "NOT (ResourcesFullText.Url LIKE :query0", "OR",
            "ResourcesFullText.Url LIKE :query1)",
        ])

        # an all-fulltext negated group is one exclusion, not one per term
        query_parts, params = self.parser.to_sqlite_fts(self.parser.parse("NOT (hello OR world)"))
        self.assertEqual(query_parts, [
            "ResourcesFullText.Id NOT IN (SELECT Id FROM ResourcesFullText WHERE ResourcesFullText MATCH :query0)"
        ])
        self.assertEqual(params["query0"], "hello OR world")

    def test_double_negation(self):
        """
        NOT NOT a is a, however it is spelled.
        """
        for query in ["NOT (NOT hello)", "NOT NOT hello"]:
            query_parts, params = self.parser.to_sqlite_fts(self.parser.parse(query))
            self.assertEqual(query_parts, ["ResourcesFullText MATCH :query0"], query)
            self.assertEqual(params["query0"], "hello", query)
        query_parts, params = self.parser.to_sqlite_fts(self.parser.parse("hello NOT (NOT world)"))
        self.assertEqual(params["query0"], "hello AND world")

    def test_binary_not_on_group(self):
        """
        A NOT (B OR C) excludes the whole group, natively in fts5 when it can.
        """
        query_parts, params = self.parser.to_sqlite_fts(self.parser.parse("hello NOT (world OR planet)"))
        self.assertEqual(query_parts, ["ResourcesFullText MATCH :query0"])
        self.assertEqual(params["query0"], "hello NOT (world OR planet)")

        query_parts, _ = self.parser.to_sqlite_fts(self.parser.parse("url: a NOT (url: b OR url: c)"))
        self.assertEqual(query_parts, [
            "ResourcesFullText.Url LIKE :query0", "AND",
            "NOT (ResourcesFullText.Url LIKE :query1", "OR",
            "ResourcesFullText.Url LIKE :query2)",
        ])

    def test_fts_or_field(self):
        """
        A MATCH under an OR runs as a subquery, sqlite refuses a bare one there. The
        OR itself used to be quietly rewritten to AND so sqlite would take it.
        """
        in_match = "ResourcesFullText.Id IN (SELECT Id FROM ResourcesFullText WHERE {} MATCH :{})"
        query_parts, _ = self.parser.to_sqlite_fts(self.parser.parse("hello OR url: x"))
        self.assertEqual(query_parts, [in_match.format("ResourcesFullText", "query0"), "OR", "ResourcesFullText.Url LIKE :query1"])

        query_parts, _ = self.parser.to_sqlite_fts(self.parser.parse("url: x OR hello"))
        self.assertEqual(query_parts, ["ResourcesFullText.Url LIKE :query0", "OR", in_match.format("ResourcesFullText", "query1")])

        query_parts, _ = self.parser.to_sqlite_fts(self.parser.parse("hello OR status: 404"))
        self.assertEqual(query_parts, [in_match.format("ResourcesFullText", "query0"), "OR", "Resources.Status = :query1"])

        # two columns can't share a MATCH, each goes its own way under the OR
        query_parts, params = self.parser.to_sqlite_fts(self.parser.parse("hello OR type: img"), {"type": {"img": 6}})
        self.assertEqual(query_parts, [
            in_match.format("ResourcesFullText", "query0"), "OR",
            in_match.format("ResourcesFullText.Type", "query1"),
        ])
        self.assertEqual(params, {"query0": "hello", "query1": "6"})

    def test_fts_or_not(self):
        """
        fts5 has no unary NOT, so a OR NOT b can't be one querystring (fts5 syntax
        error). It used to drop the NOT, it now splits into SQL.
        """
        in_match = "ResourcesFullText.Id IN (SELECT Id FROM ResourcesFullText WHERE ResourcesFullText MATCH :{})"
        not_in_match = "ResourcesFullText.Id NOT IN (SELECT Id FROM ResourcesFullText WHERE ResourcesFullText MATCH :{})"
        query_parts, params = self.parser.to_sqlite_fts(self.parser.parse("hello OR NOT world"))
        self.assertEqual(query_parts, [in_match.format("query0"), "OR", not_in_match.format("query1")])
        self.assertEqual(params, {"query0": "hello", "query1": "world"})

        query_parts, _ = self.parser.to_sqlite_fts(self.parser.parse("NOT hello OR world"))
        self.assertEqual(query_parts, [not_in_match.format("query0"), "OR", in_match.format("query1")])

    def test_direct_match_kept(self):
        """
        The fast path stays: a MATCH that is a top-level AND constraint runs bare, and
        same-column fulltext ANDed across other clauses merges into one MATCH.
        """
        cases = [
            ("hello", ["ResourcesFullText MATCH :query0"]),
            ("hello AND url: x", ["ResourcesFullText MATCH :query0", "AND", "ResourcesFullText.Url LIKE :query1"]),
            ("hello AND url: x AND world", ["ResourcesFullText MATCH :query0", "AND", "ResourcesFullText.Url LIKE :query1"]),
            ("type: html AND hello AND content: world", [
                "ResourcesFullText.Type MATCH :query0", "AND",
                "ResourcesFullText MATCH :query1", "AND",
                "ResourcesFullText.Content MATCH :query2",
            ]),
            ("(url: a OR url: b) AND (hello OR world)", [
                "(ResourcesFullText.Url LIKE :query0", "OR",
                "ResourcesFullText.Url LIKE :query1)", "AND",
                "ResourcesFullText MATCH :query2",
            ]),
            ("hello NOT headers: json", [
                "ResourcesFullText MATCH :query0", "AND",
                "ResourcesFullText.Id NOT IN (SELECT Id FROM ResourcesFullText WHERE ResourcesFullText.Headers MATCH :query1)",
            ]),
        ]
        for query, expected in cases:
            query_parts, _ = self.parser.to_sqlite_fts(self.parser.parse(query))
            self.assertEqual(query_parts, expected, query)

    def test_mixed_field_precedence(self):
        """
        Standard precedence across fields too. type: html AND a OR b used to run as
        html AND (a OR b), because neighboring fulltext terms packed together.
        """
        query_parts, params = self.parser.to_sqlite_fts(self.parser.parse("type: html AND hello OR world"), {"type": {"html": 1}})
        sql: str = " ".join(query_parts)
        self.assertTrue(sql.startswith("(ResourcesFullText.Id IN"), sql)
        self.assertIn(") OR ResourcesFullText.Id IN", sql)
        self.assertEqual(params, {"query0": "1", "query1": "hello", "query2": "world"})

    def test_fts_querystring_grammar(self):
        """
        Whatever the query, no fts5 querystring leans on something fts5 lacks: a leading
        NOT, NOT after another operator or a paren (unary NOT), or two columns.
        """
        queries = [
            "NOT a", "a OR NOT b", "NOT a OR b", "NOT a AND NOT b", "a AND NOT b OR c",
            "NOT (a OR b) AND c", "(NOT a) AND b", "a AND (NOT b OR c)", "NOT (a AND NOT (b OR c))",
            "a NOT NOT b", "(a OR b) NOT (c OR d)", "NOT (NOT (NOT a))", "a OR (b NOT c)",
            "type: html OR NOT type: img", "content: a AND NOT content: b", "a AND content: b OR c",
        ]
        for query in queries:
            _, params = self.parser.to_sqlite_fts(self.parser.parse(query), {"type": {"html": 1, "img": 6}})
            for querystring in (value for value in params.values() if isinstance(value, str)):
                normalized: str = f" {querystring.replace('(', ' ( ')} "
                self.assertFalse(normalized.strip().startswith("NOT"), f"leading NOT {querystring!r} ({query})")
                for unary in (" AND NOT ", " OR NOT ", " ( NOT ", " NOT NOT "):
                    self.assertNotIn(unary, normalized, f"unary NOT {querystring!r} ({query})")

    def test_malformed_query_raises(self):
        """
        Malformed queries raise. Recovering dropped terms, and an empty parse read as
        no query at all, returning the whole site as matching.
        """
        for query in ["(a OR b", "a AND", "a OR", "a )", "title: a", "a \"b", "status: >=", "NOT"]:
            with self.assertRaises(ValueError, msg=query):
                self.parser.parse(query)

    def test_unicode_and_punctuated_terms(self):
        """
        Terms outside ascii alphanumerics parse whole, where they were once skipped a
        character at a time (café searched caf, 東京 searched nothing, so everything)
        """
        cases = {
            "café": ("café", "term"),
            "東京": ("東京", "term"),
            "example.com": ("example.com", "term"),
            "c++": ("c++", "term"),
            "AT&T": ("AT&T", "term"),
            "don't": ("don't", "term"),
            "straße*": ("straße", "wildcard"),
            "example.com*": ("example.com", "wildcard"),
        }
        for query, (value, value_type) in cases.items():
            result: list[SearchSubquery] = self.parser.parse(query)
            self.assertEqual(len(result), 1, query)
            self.assertEqual((result[0].value, result[0].type), (value, value_type), query)

    def test_fts5_quoting(self):
        """
        fts5 barewords pass through, anything else is quoted (one syntax error was an
        empty result, reported as no matches), and runs against a real fts5 table.
        """
        cases = {
            "hello": "hello",
            "café": "café",
            "hel*": "hel*",
            "example.com": '"example.com"',
            "example.com*": '"example.com"*',
            "c++": '"c++"',
            "don't": "\"don't\"",
            "one-click": '"one-click"',
        }
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.execute("CREATE VIRTUAL TABLE t USING fts5(c, tokenize=\"unicode61 remove_diacritics 0 tokenchars '-_'\")")
            connection.execute("INSERT INTO t VALUES ('visit example.com with c++ and don''t one-click, café hello')")
            for query, expected in cases.items():
                _, params = self.parser.to_sqlite_fts(self.parser.parse(query))
                self.assertEqual(params["query0"], expected, query)
                matches = connection.execute("SELECT count(*) FROM t WHERE t MATCH ?", (params["query0"],)).fetchone()[0]
                self.assertEqual(matches, 1, f"{query} -> {expected}")

class TestSearchQueryOracle(unittest.TestCase):
    """
    Random queries through the real SQL path, on an in-memory copy of the indexed
    schema, checked against Python evaluating the same query string. Python's not,
    and, or rank exactly NOT > AND > OR, so the oracle shares nothing with the parser
    or the SQL emitter. sqlite refusing a query fails here too, not just a wrong set.
    """

    SWAP_VALUES = {"type": {"html": 1, "img": 6}}
    WORDS = ("alpha", "beta", "gamma", "delta")

    def setUp(self):
        self.parser = SearchQueryParser()
        self.connection = sqlite3.connect(":memory:")
        IndexedManager()._setup_database(self.connection)
        self.documents: list[dict] = []
        for resource_id in range(1, 25):
            document = {
                "id": resource_id,
                "words": {word for bit, word in enumerate(self.WORDS) if resource_id & (1 << bit)},
                "url": f"https://site.test/{('north', 'south', 'east')[resource_id % 3]}/page{resource_id}",
                "type": "html" if resource_id % 4 else "img",
                "status": 404 if resource_id % 5 == 0 else 200,
            }
            self.documents.append(document)
            self.connection.execute(
                "INSERT INTO ResourcesFullText (Id, Project, Url, Type, Headers, Content) VALUES (?, 1, ?, ?, '', ?)",
                (resource_id, document["url"], self.SWAP_VALUES["type"][document["type"]], " ".join(sorted(document["words"]))),
            )
            self.connection.execute(
                "INSERT INTO Resources (Id, Project, Status, Size, Time) VALUES (?, 1, ?, 0, 0)",
                (resource_id, document["status"]),
            )
        # (query term, oracle row test)
        self.terms = [(word, lambda d, w=word: w in d["words"]) for word in self.WORDS] + [
            ("gam*", lambda d: any(w.startswith("gam") for w in d["words"])),
            ("content: beta", lambda d: "beta" in d["words"]),
            ("url: north", lambda d: "north" in d["url"]),
            ("url: south", lambda d: "south" in d["url"]),
            ("type: html", lambda d: d["type"] == "html"),
            ("type: img", lambda d: d["type"] == "img"),
            ("id: 3", lambda d: d["id"] == 3),
            ("id: 12", lambda d: d["id"] == 12),
            ("status: 404", lambda d: d["status"] == 404),
        ]

    def tearDown(self):
        self.connection.close()

    def __search_ids(self, query: str) -> set[int]:
        parsed = self.parser.parse(query)
        self.assertTrue(parsed, f"did not parse: {query}")
        query_parts, params = self.parser.to_sqlite_fts(parsed, self.SWAP_VALUES)
        # joined as the base adapter joins them
        where: str = "".join(f" {part} " if part in ("AND", "OR", "NOT") else part for part in query_parts)
        statement: str = f"SELECT ResourcesFullText.Id FROM ResourcesFullText LEFT JOIN Resources ON ResourcesFullText.Id = Resources.Id WHERE ({where})"
        try:
            with closing(self.connection.cursor()) as cursor:
                return {int(row[0]) for row in cursor.execute(statement, params).fetchall()}
        except sqlite3.Error as ex:
            self.fail(f"sqlite refused {query!r}: {ex}\n{statement}\n{params}")

    def __oracle_ids(self, expression: str, term_indexes: list[int]) -> set[int]:
        ids: set[int] = set()
        for document in self.documents:
            variables = {f"t{i}": self.terms[i][1](document) for i in term_indexes}
            if eval(expression, {"__builtins__": {}}, variables):
                ids.add(document["id"])
        return ids

    def __generate(self, rng: random.Random, depth: int, term_indexes: list[int]) -> tuple[str, str]:
        """
        A grammatical query and its Python twin: AND/OR/NOT between operands, prefix
        NOT, parens. Binary a NOT b is a and not b.
        """
        query_parts: list[str] = []
        oracle_parts: list[str] = []
        for i in range(rng.randint(1, 4)):
            if i > 0:
                operator: str = rng.choice(["AND", "OR", "NOT"])
                query_parts.append(operator)
                oracle_parts.append({"AND": "and", "OR": "or", "NOT": "and not"}[operator])
            if depth > 0 and rng.random() < 0.35:
                query, oracle = self.__generate(rng, depth - 1, term_indexes)
                query, oracle = f"({query})", f"({oracle})"
            else:
                index: int = rng.randrange(len(self.terms))
                term_indexes.append(index)
                query, oracle = self.terms[index][0], f"t{index}"
            if rng.random() < 0.25:
                query, oracle = f"NOT {query}", f"not {oracle}"
            query_parts.append(query)
            oracle_parts.append(oracle)
        return " ".join(query_parts), " ".join(oracle_parts)

    def test_oracle_fixed(self):
        """
        The shapes this work was about, checked by name so no seed can skip them.
        """
        cases = [
            ("NOT (url: north OR url: south)", "not (t6 or t7)"),
            ("NOT url: north AND type: html", "not t6 and t8"),
            ("alpha OR url: north", "t0 or t6"),
            ("url: north OR alpha", "t6 or t0"),
            ("alpha OR type: img", "t0 or t9"),
            ("alpha OR status: 404", "t0 or t12"),
            ("alpha OR NOT beta", "t0 or not t1"),
            ("NOT alpha OR beta", "not t0 or t1"),
            ("type: html AND alpha OR beta", "t8 and t0 or t1"),
            ("alpha OR beta AND type: html", "t0 or t1 and t8"),
            ("alpha NOT (beta OR gamma)", "t0 and not (t1 or t2)"),
            ("NOT (NOT alpha)", "not (not t0)"),
            ("alpha NOT (NOT beta)", "t0 and not (not t1)"),
            ("NOT alpha AND NOT beta", "not t0 and not t1"),
            ("NOT (alpha AND NOT (beta OR url: north))", "not (t0 and not (t1 or t6))"),
            ("(url: north OR url: south) AND (alpha OR beta)", "(t6 or t7) and (t0 or t1)"),
            ("(id: 3 OR id: 12) NOT id: 3", "(t10 or t11) and not t10"),
            ("gam* OR NOT content: beta", "t4 or not t5"),
        ]
        for query, oracle in cases:
            self.assertEqual(self.__search_ids(query), self.__oracle_ids(oracle, list(range(len(self.terms)))), query)

    def test_oracle_random(self):
        rng: random.Random = random.Random(20260925)
        for _ in range(600):
            term_indexes: list[int] = []
            query, oracle = self.__generate(rng, 2, term_indexes)
            self.assertEqual(self.__search_ids(query), self.__oracle_ids(oracle, term_indexes), f"{query}  ~  {oracle}")
