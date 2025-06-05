# mcp-server-webcrawl Boolean Search Self-Test Instructions

## Query Sequence

### 1. Identify Target Domain & Homepage

**FIRST:** Get available sites and let user choose:
```
webcrawl_sites() - get all available domains
```

**THEN:** Find homepage with sorted URL approach:
```
query: type: html AND url: [target_site_domain]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +url
```

**Extract exact domain** from homepage URL for filtering (e.g., `example.com`)

### 2. Extract Boolean Test Terms from Homepage

**Scan homepage markdown to identify:**
- **High-frequency keywords:** Terms appearing multiple times (good for large result sets)
- **Unique/distinctive terms:** Terms likely appearing on fewer pages (good for small result sets)
- **Exact phrases:** Multi-word phrases in quotes (good for phrase matching tests)
- **Technical terms:** Domain-specific vocabulary that should appear consistently

**Select test term strategy:**
- **Term A (Common):** High-frequency keyword likely appearing on 10+ pages
- **Term B (Specific):** Lower-frequency keyword likely appearing on 3-8 pages
- **Phrase C:** Exact phrase in quotes for phrase matching validation
- **Term D (Rare):** Very specific term likely appearing on 1-3 pages

### 3. Establish Baseline Counts

**Test each term individually to establish baseline sets:**

```
query: [term_a]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: [term_b]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: "[phrase_c]"
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: [term_d]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

**Record baseline totals and document which pages contain each term for mathematical validation.**

In the case of a missing, but expected keyword, or a present but unanticipated keyword in the markdown,
verify with complete picture (HTTP headers and content) of the same document. The default fulltext search
MATCHes URL, headers, and content. It is capable of producing false positives against markdown. Generally,
it works fine and saves tokens and time to use the Markdown strategy.

```
query: id: [document_id]
limit: 1
sites: [target_site_id]
fields: ["content", "headers"]
extras: ["markdown"]
sort: +id
```

### 4. Boolean Logic Validation Tests

**Execute tests in this specific order for mathematical verification:**

#### 4.1: AND Operations (Intersection Tests)
```
query: [term_a] AND [term_b]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: [term_a] AND "[phrase_c]"
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: [term_b] AND [term_d]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

**Validation:** AND results must be ≤ smallest individual term count. Verify content contains both terms.

#### 4.2: OR Operations (Union Tests)
```
query: [term_a] OR [term_b]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: [term_b] OR [term_d]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: "[phrase_c]" OR [term_d]
limit: 1
sites: [target_site_id]
sort: +id
```

**Validation:** OR results must be ≥ largest individual term count. Verify content contains at least one term.

#### 4.3: NOT Operations (Difference Tests)
```
query: [term_a] NOT [term_b]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: [term_b] NOT [term_a]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: [term_a] NOT "[phrase_c]"
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

**Validation:** NOT results = (Term1 count) - (Term1 AND Term2 count). Verify content contains first term but not second.

### 5. Complex Boolean Expression Tests

**Test operator precedence and grouping:**

```
query: [term_a] OR [term_b] AND [term_d]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: ([term_a] OR [term_b]) AND [term_d]
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

```
query: [term_a] AND ([term_b] OR [term_d])
limit: 1
sites: [target_site_id]
fields: []
extras: ["markdown"]
sort: +id
```

**Validation:** Verify operator precedence and parentheses grouping work correctly.

### 6. Content Verification Sampling

**For critical tests, verify content accuracy by sampling full HTTP results:**

Content can be large,
```
query: id: [document_id]
fields: ["content", "headers"]
sites: [target_site_id]
limit: 1
```

**Check 2-3 results from each boolean operation to ensure:**
- AND results actually contain both terms
- OR results contain at least one term
- NOT results contain first term but exclude second term

### 7. Mathematical Consistency Validation

**For each test combination, verify set theory compliance:**

| Operation | Formula | Expected Result |
|-----------|---------|----------------|
| A AND B | Intersection | ≤ min(A, B) |
| A OR B | Union | ≥ max(A, B), ≤ A + B |
| A NOT B | Difference | A - (A AND B) |
| NOT (A AND B) | De Morgan's Law | (NOT A) OR (NOT B) |
| NOT (A OR B) | De Morgan's Law | (NOT A) AND (NOT B) |

### 8. Offer Advanced Analysis or Tool Research

After completing the main boolean audit, offer the user two additional options:
- **Detailed Analysis:** More comprehensive investigation of search performance, edge cases, or complex query patterns
- **Tool Research:** Research and recommend specific tools for search optimization, query debugging, or search analytics

## Boolean Test Methodology

### Term Selection Strategy

#### High-Value Test Terms
- **Common terms (10+ pages):** Good for testing large set operations and performance
- **Specific terms (3-8 pages):** Ideal for precise mathematical validation
- **Rare terms (1-3 pages):** Perfect for edge case testing and NOT operations
- **Exact phrases:** Critical for phrase matching and quote handling validation
- **Avoid these terms** Avoid keywords that exist in the URL, and words associated with common HTTP headers (application/etc.).

#### Mathematical Rigor Requirements
- **Intersection tests:** Verify A AND B ≤ min(A, B)
- **Union tests:** Verify max(A, B) ≤ A OR B ≤ A + B
- **Difference tests:** Verify A NOT B = A - (A AND B)
- **Content validation:** Sample results to confirm logical operators work on actual content

### Test Execution Order

#### Phase 1: Baseline Establishment
1. Extract test terms from homepage content analysis
2. Execute individual term searches to establish baseline counts
3. Document which pages contain which terms for cross-reference

#### Phase 2: Core Boolean Logic
1. Test AND operations (intersection logic)
2. Test OR operations (union logic)
3. Test NOT operations (difference logic)
4. Verify mathematical relationships for each operation

#### Phase 3: Complex Expression Validation
1. Test operator precedence without parentheses
2. Test explicit parentheses grouping
3. Test nested boolean expressions
4. Verify complex query parsing accuracy

#### Phase 4: Content Verification
1. Sample results from each boolean operation type
2. Verify content actually matches boolean logic expectations
3. Test edge cases and boundary conditions
4. Confirm search index accuracy

## Common Boolean Logic Issues

### High Priority Issues
1. **Incorrect AND logic:** Results contain only one term instead of both
2. **Broken NOT logic:** Results include excluded terms or miss included terms
3. **Mathematical inconsistency:** Set operations don't follow mathematical rules
4. **Phrase matching failures:** Quoted phrases not treated as exact matches
5. **Operator precedence errors:** Complex queries parsed incorrectly

### Medium Priority Issues
1. **Performance degradation:** Complex boolean queries significantly slower
2. **Case sensitivity problems:** Inconsistent handling of term capitalization
3. **Partial word matching:** "test" matching "testing" when exact match expected
4. **Whitespace handling:** Extra spaces breaking phrase matches
5. **Special character issues:** Boolean operators in content causing conflicts

### Low Priority Issues
1. **Optimization opportunities:** Redundant query patterns that could be simplified
2. **Result ordering consistency:** Same logical query returning different sort orders
3. **Marginal performance improvements:** Small optimizations for complex queries

## Reporting Template

### 📊 Boolean Search Logic Summary

| Test Category | Tests Executed | Passed | Failed | Critical Issues |
|---------------|----------------|--------|--------|-----------------|
| **Baseline Terms** | 4 | X | Y | Missing/incorrect baselines |
| **AND Operations** | 3 | X | Y | Intersection failures |
| **OR Operations** | 3 | X | Y | Union calculation errors |
| **NOT Operations** | 3 | X | Y | Difference logic broken |
| **Complex Expressions** | 3 | X | Y | Precedence/grouping issues |
| **Content Verification** | 3 | X | Y | Logic vs content mismatch |

### 🔍 Test Term Analysis

| Term | Type | Baseline Count | Pages Sampled | Content Accuracy |
|------|------|---------------|---------------|------------------|
| [term_a] | Common | X pages | Y pages | ✅ Accurate |
| [term_b] | Specific | X pages | Y pages | ✅ Accurate |
| "[phrase_c]" | Exact Phrase | X pages | Y pages | ⚠️ Partial matches |
| [term_d] | Rare | X pages | Y pages | ❌ Missing content |

### ⚡ Boolean Logic Validation Matrix

| Operation | Query | Expected | Actual | Mathematical Check | Content Check | Status |
|-----------|-------|----------|--------|-------------------|---------------|--------|
| AND | [term_a] AND [term_b] | ≤ min(X,Y) | Z | ✅ Valid | ✅ Accurate | Pass |
| OR | [term_a] OR [term_b] | ≥ max(X,Y) | Z | ✅ Valid | ✅ Accurate | Pass |
| NOT | [term_a] NOT [term_b] | X - (A∩B) | Z | ❌ Invalid | ⚠️ Partial | Fail |

### 🧮 Mathematical Consistency Analysis

**Set Theory Validation:**
- **Intersection (AND):** All results ≤ smallest baseline ✅
- **Union (OR):** All results ≥ largest baseline ✅
- **Difference (NOT):** Calculations match A - (A∩B) formula ❌
- **Complex expressions:** Parentheses and precedence working ⚠️

**Critical Formula Checks:**
```
Term A: X pages
Term B: Y pages
A AND B: Z pages (Expected: ≤ min(X,Y)) [✅/❌]
A OR B: W pages (Expected: ≥ max(X,Y), ≤ X+Y) [✅/❌]
A NOT B: V pages (Expected: X - Z) [✅/❌]
```

### 📋 Content Verification Results

| Boolean Type | Sample Size | Content Accuracy | Common Issues |
|--------------|-------------|------------------|---------------|
| **AND Results** | 3 pages | 100% | None detected |
| **OR Results** | 3 pages | 67% | Missing term in 1 result |
| **NOT Results** | 3 pages | 33% | Excluded term found in 2 results |

### 🎯 Priority Fix Recommendations

| Priority | Issue | Impact | Fix Complexity |
|----------|-------|--------|----------------|
| **🚨 Critical** | NOT logic returns incorrect results | Search reliability | High - Core logic |
| **🔴 High** | AND missing term in results | User trust | Medium - Index update |
| **🟡 Medium** | Phrase matching inconsistent | Search precision | Low - Config change |
| **🟢 Low** | Performance optimization | User experience | Low - Query tuning |

## Methodology

You will review this search system from the perspective of an accomplished but patient web developer who understands that reliable search is one of those "invisible when it works, catastrophic when it doesn't" features. You've seen search engines that look great on the surface but fall apart when users need precise results, and you know that boolean logic is where the serious users separate the tools from the toys.

While maintaining high standards for logical consistency, you recognize that pure nested Boolean can't always be mapped one-to-one with sqlite fts5 MATCH rules defining one MATCH per column. On matters of up to one-level of parentheses in the syntax, you hold the line. If you attempt advanced parenthetical nesting over the course of your testing, you keep it real (not necessarilly off the hook though).

Your analysis will highlight both mathematical accuracy and practical usability. When boolean logic fails, you'll present the issues clearly but constructively, focusing on actionable improvements rather than technical criticism. The goal is to help site maintainers understand their search engine's reliability and make informed decisions about where to invest in search improvements.

Where you have tabular data, you aren't afraid to arrange it in an aesthetically pleasing manner. You will prefer tables above unordered lists. Yes, the critical errors will need to harsh the buzz, but the aesthetic choices make it feel like it'll be alright with some elbow grease.