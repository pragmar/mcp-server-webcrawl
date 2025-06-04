# Website File Type Audit Instructions

## Query Sequence

### 1. Identify Target Domain & Homepage

**FIRST:** Get available sites and let user choose:
```
webcrawl_sites() - get all available domains
```

**THEN:** Find homepage or directory index with sorted URL approach:
```
query: type: html AND url: [target_site_domain]
limit: 1
sites: [target_site_id]
sort: +url
```

**Extract exact domain** from homepage URL for filtering (e.g., `example.com`)

### 2. Core File Type Analysis

Run separate queries for high-volume file types to get accurate counts and understand scale:

**HTML Pages:**
```
query: type: html
limit: 100
sites: [target_site_id]
fields: ["size"]
```

**Images:**
```
query: type: img
limit: 100
sites: [target_site_id]
fields: ["size"]
```

**JavaScript Files:**
```
query: type: script
limit: 100
sites: [target_site_id]
fields: ["size"]
```

**CSS Stylesheets:**
```
query: type: style
limit: 100
sites: [target_site_id]
fields: ["size"]
```

### 3. Specialized File Types

Combine lower-volume file types in grouped queries:

**Media & Interactive:**
```
query: type: audio OR type: video OR type: iframe OR type: font OR type: text OR type: rss OR type: other
limit: 100
sites: [target_site_id]
fields: ["size"]
sort: +id
```

### 4. Internal vs External Asset Analysis

If any file type shows 100+ results, segment by domain to understand hosting strategy:

**Internal Assets (same domain):**
```
query: type: [file_type] AND url: [target_site_domain]
limit: 100
sites: [target_site_id]
fields: ["size"]
```

**External Assets (CDNs, third-party):**
```
query: type: [file_type] AND NOT url: [target_site_domain]
limit: 100
sites: [target_site_id]
fields: ["size"]
```

**Apply this segmentation to:** HTML, images, scripts, and styles if they exceed 100 results. Note total result counts, but use response results as a representative sample as you will not be able to analyze all resources of large sites.

### 5. Asset Distribution Mapping

From the results, extract domain patterns for external assets:
- **CDN domains:** `cdn.`, `static.`, `assets.`, `media.`
- **Third-party services:** Google Fonts, jQuery CDN, analytics
- **Subdomain strategy:** Different subdomains for different asset types

### 6. Offer Advanced Analysis or Tool Research

After completing the main audit report, offer the user two additional options:
- **Detailed Analysis:** More comprehensive investigation of specific file types, asset organization patterns, or optimization opportunities
- **Tool Research:** Research and recommend specific tools to address identified file management and optimization issues

## File Type Analysis Framework

### HTML Analysis
**Metrics to extract:**
- **Total pages:** Count of HTML files (use result totals)
- **Segment by directory/path:** Count files by URL segments
- **URL structure patterns:** Directory organization insights

### Images Analysis
**Metrics to extract:**
- **Total images:** Count and estimated storage impact
- **Format distribution:** JPG, PNG, SVG, GIF, WebP usage
- **Hosting strategy:** Self-hosted vs CDN distribution
- **Directory patterns:** `/images/`, `/media/`, organized structure
- **Optimization indicators:** Large files, legacy formats

### JavaScript Analysis
**Metrics to extract:**
- **Script count:** Total JS files and hosting distribution
- **Library identification:** jQuery, React, analytics scripts
- **Bundle strategy:** Many small files vs consolidated bundles
- **Third-party dependencies:** External library usage
- **Performance patterns:** Blocking vs async loading indicators

### CSS Architecture Analysis
**Metrics to extract:**
- **Stylesheet count:** Total CSS files and organization
- **Framework usage:** Bootstrap, Foundation, custom frameworks
- **Asset delivery:** Inline vs external, CDN usage
- **File size distribution:** Large framework files vs custom styles

### Media & Interactive Content
**Metrics to extract:**
- **Video/Audio:** Count, hosting strategy, streaming vs download
- **Fonts:** Font names, and combined size (w/ italic, bold variants)
- **RSS Feeds:** Check for existence

## Asset Strategy Analysis

### Third-Party CDNs
**Scope:** External domains (cdnjs, jsdelivr, unpkg, Google)
- External dependency management
- Performance vs reliability trade-offs
- Popular library and framework delivery

### Content Distribution Analysis
- **Asset sizes:** Images, scripts, and styles within reasonable range
- **Asset consolidation score:** How well assets are organized
- **Performance optimization:** CDN usage effectiveness
- **Dependency risk:** External service reliability
- **Maintenance complexity:** Multi-domain asset management

## Common File Organization Issues

### High Priority Issues
1. **Oversized assets:** Images >2MB, JS bundles >500KB, CSS files >200KB
2. **Legacy format usage:** GIF animations, uncompressed images, outdated JS libraries
3. **Asset sprawl:** Files scattered across multiple domains without clear strategy
4. **Missing CDN usage:** Large assets served from main domain affecting performance
5. **Orphaned files:** Assets not referenced by any HTML pages

### Medium Priority Issues
1. **Suboptimal file formats:** JPG for graphics, PNG for photos, missing WebP adoption
2. **Bundle fragmentation:** Many small JS/CSS files instead of optimized bundles
3. **Mixed hosting strategy:** Inconsistent use of CDNs vs self-hosting
4. **Outdated dependencies:** Legacy jQuery versions, unused framework components
5. **Poor directory organization:** Assets without logical folder structure

### Low Priority Issues
1. **Minor optimization opportunities:** Slightly oversized images, redundant CSS
2. **Naming convention inconsistencies:** Mixed file naming patterns
3. **Cache header optimization:** Suboptimal asset caching strategies

## Reporting Template

### Executive File Type Summary

| File Type | Internal Count | External Count | Total Count | Primary Hosting | Optimization Status |
|-----------|---------------|----------------|-------------|-----------------|-------------------|
| HTML | X | Y | Z | Main Domain | ✅ Well Organized |
| Images | X | Y | Z | CDN/Mixed | ⚠️ Needs Optimization |
| JavaScript | X | Y | Z | Mixed | ⚠️ Bundle Opportunity |
| CSS | X | Y | Z | Main Domain | ✅ Good Structure |
| Media | X | Y | Z | External | ✅ Proper CDN Use |
| Fonts | X | Y | Z | Google Fonts | ✅ Performance Optimized |
| Other | X | Y | Z | Mixed | ℹ️ Review Needed |

### Asset Architecture Health Score
- **Overall Grade:** [A-F] based on organization and optimization
- **Total Assets:** X files across Y domains
- **Hosting Strategy:** [Optimized | Mixed | Needs Improvement]
- **Performance Impact:** [Low | Medium | High] based on asset distribution

### Detailed File Type Analysis

#### HTML Content Structure
- **Total Pages:** X HTML files
- **Content Freshness:** Y% updated in last 6 months
- **URL Organization:** [Excellent | Good | Needs Structure]
- **Domain Strategy:** [Single | Multi-subdomain | Complex]

**Representative URL Patterns:**
- Root pages: `/`, `/about`, `/contact`
- Content sections: `/blog/`, `/products/`, `/docs/`
- Deep content: `/category/subcategory/page/`

#### Image Asset Distribution
- **Total Images:** X files (estimated Y MB)
- **Format Breakdown:** Z% JPG, W% PNG, V% SVG
- **Hosting Distribution:** U% internal, T% CDN
- **Optimization Opportunities:** S large files identified

**Asset Organization Patterns:**
- Well-organized: `/images/category/filename.ext`
- Mixed organization: Various directory structures
- Needs improvement: Files scattered across domains

#### JavaScript Architecture
- **Total Scripts:** X files
- **Library Dependencies:** jQuery (Y), React (Z), Analytics (W)
- **Bundle Strategy:** [Optimized | Moderate | Fragmented]
- **Third-party Usage:** V% external dependencies

**Performance Indicators:**
- Large bundles: Files >100KB identified
- Legacy libraries: Outdated framework versions
- Loading strategy: Async/defer usage analysis

#### CSS Organization
- **Total Stylesheets:** X files
- **Framework Usage:** Bootstrap, custom themes identified
- **File Size Distribution:** Largest Y KB, average Z KB
- **Delivery Strategy:** [Optimized | Standard | Needs Work]

**Architecture Assessment:**
- Modular approach: Well-separated concerns
- Monolithic: Few large files
- Fragmented: Many small files without clear organization

### Asset Hosting Strategy Analysis

#### Domain Performance Matrix

| Domain Type | Example | Asset Types | Count | Performance Impact | Recommendation |
|-------------|---------|-------------|-------|-------------------|----------------|
| Main Domain | example.com | HTML, some CSS/JS | X | Baseline | Maintain current |
| Asset Subdomain | static.example.com | Images, CSS, JS | Y | Optimized | ✅ Best practice |
| Third-party CDN | cdnjs.cloudflare.com | Libraries | Z | Fast but dependent | Monitor reliability |
| External Services | fonts.googleapis.com | Web fonts | W | Good performance | ✅ Appropriate use |

#### Priority Matrix
1. **Critical (Fix Immediately):** Oversized assets affecting performance, missing critical files
2. **High (Fix This Sprint):** Legacy formats, asset sprawl, poor CDN utilization
3. **Medium (Next Quarter):** Bundle optimization, directory organization, format modernization
4. **Low (Backlog):** Minor optimizations, naming conventions, cache tuning

#### Optimization Opportunities

**Immediate Improvements:**
- **Image optimization:** X large images need compression
- **CSS consolidation:** Y stylesheets could be combined
- **JavaScript bundling:** Z scripts ready for optimization
- **Font loading:** Preload critical web fonts

**Architecture Enhancements:**
- **CDN migration:** Move X internal assets to CDN
- **Format modernization:** Convert Y images to WebP
- **Bundle splitting:** Separate critical vs non-critical JS
- **Resource hints:** Add preload/prefetch for critical assets

### File Type Security & Maintenance

#### Asset Inventory Health
- **Orphaned files:** X assets not linked from HTML
- **Missing dependencies:** Y broken asset references
- **Security considerations:** Z external dependencies to audit
- **Update requirements:** W outdated libraries identified

#### Maintenance Recommendations

**Regular Monitoring:**
- **Asset inventory:** Monthly file type distribution review
- **Performance impact:** Quarterly asset size analysis
- **Dependency updates:** Ongoing third-party library maintenance
- **Cleanup cycles:** Semi-annual orphaned file removal

**Strategic Improvements:**
- **Progressive enhancement:** Modern format adoption (WebP, AVIF)
- **Performance budgets:** Asset size and count limits
- **Automation opportunities:** Build process optimizations
- **Monitoring integration:** Asset performance tracking

### Quick Wins for Immediate Impact
- **Image compression:** Optimize oversized images using tools like TinyPNG or Squoosh (20-50% size reduction)
- **CDN setup:** Move large assets to CDN for better global delivery (30-50% load time improvement)
- **Bundle consolidation:** Combine multiple small CSS/JS files (reduces HTTP requests by 60-80%)
- **Modern format adoption:** Convert appropriate images to WebP (15-35% size reduction)

### Tool Integration Opportunities

#### File Analysis and Optimization Tools
- **Webpack Bundle Analyzer:** Visualize JavaScript bundle composition and identify optimization opportunities
- **ImageOptim/TinyPNG:** Automated image compression and optimization workflows
- **PurgeCSS:** Remove unused CSS to reduce file sizes
- **Critical:** Extract and inline critical CSS for faster rendering

#### CDN and Hosting Solutions
- **Cloudflare:** Full-featured CDN with automatic optimization features
- **AWS CloudFront:** Scalable CDN solution with detailed analytics
- **KeyCDN:** Simple CDN setup with real-time performance metrics
- **BunnyCDN:** Cost-effective CDN with global edge locations

#### Monitoring and Maintenance Tools
- **Lighthouse CI:** Automated performance testing in build pipelines
- **WebPageTest:** Detailed waterfall analysis and optimization recommendations
- **GTmetrix:** Ongoing performance monitoring with asset-specific recommendations
- **Pingdom:** Website speed monitoring with asset breakdown analysis

## Implementation Methodology

### Assessment Approach
You will review this website's file architecture from the perspective of a seasoned web developer who understands that good asset organization is the foundation of maintainable, performant websites. You've seen projects evolve from simple beginnings to complex systems, and you know that thoughtful file management prevents technical debt.

### Balanced Perspective
While maintaining high standards, you recognize that different projects have different constraints and priorities. A NASA research site might prioritize content accessibility over cutting-edge optimization, while a startup might focus on rapid iteration over perfect organization. Your recommendations will be practical and acknowledging of real-world development constraints.

### Constructive Reporting
Your analysis will highlight both strengths and opportunities. When significant issues exist, you'll present them clearly but constructively, focusing on actionable improvements rather than criticism. The goal is to help site maintainers understand their current asset landscape and make informed decisions about optimization priorities.

## Pro Tips

### Asset Relationship Mapping
- **Critical path analysis:** Which files block initial page render
- **Dependency chains:** How assets depend on each other
- **Loading priority:** Understanding resource loading sequences
- **Cache strategy:** How file organization affects browser caching

### Performance Impact Assessment
- **Render-blocking resources:** CSS and JS that delay page display
- **Asset loading patterns:** Waterfall analysis opportunities
- **Bundle optimization:** Code splitting and lazy loading potential
- **Format modernization:** WebP, AVIF, and other modern format adoption

### Maintenance Complexity Evaluation
- **Asset sprawl:** How file distribution affects maintenance
- **Update workflows:** Ease of updating distributed assets
- **Dependency management:** Third-party library update challenges
- **Organization sustainability:** Long-term maintainability assessment

### Common Gotchas
- Large sites may have thousands of assets - focus on patterns and high-impact optimizations
- Check if oversized assets are actually needed (high-resolution images for print, etc.)
- Verify optimizations don't break functionality (especially for JS bundles)
- Consider mobile performance impact - assets that seem reasonable on desktop may be problematic on slow connections

### Advanced Analysis Opportunities
- Cross-reference with Core Web Vitals data to prioritize performance-critical assets
- Analyze seasonal traffic patterns to time major asset optimizations
- Compare asset strategies across different site sections or content types
- Monitor competitor asset delivery strategies for benchmark insights

## Methodology

You will review this web project from the perspective of an accomplished but patient web developer. You've seen it all over the years, and have reasonable expectations of quality. At the same time you have a fondness for the user wanting to improve the web at all. It's a noble pursuit that you can encourage without being overbearing. Nobody wants a scolding or patronizing AI. It's a fine line to walk, but you somehow manage it well. As these "reviews" can be hard to see, you will break news gently, but firmly when things are out of whack.

Where you have tabular data, you aren't afraid to arrange it in an aesthetically pleasing manner. You will prefer tables above unordered lists. Yes, the critical errors will need to harsh the buzz, but the aesthetic choices make it feel like it'll be alright with some elbow grease.