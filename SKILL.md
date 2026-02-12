---
name: "automotive-market-intel"
description: "Generate structured competitive intelligence summaries and executive briefs for automotive closure systems and car entry markets. Use when working with automotive news articles, press releases, patents, or regulatory documents about door modules, window regulators, latches, smart entry systems, access technologies, or related closure applications. Also critical for tracking OEM strategy shifts (EV slowdowns, hybrid resurgence, powertrain diversification) as these impact closure system requirements and demand forecasts. Categorize by company/topic/priority, analyze strategic implications, compile into executive briefs, or format for SharePoint/Teams integration."

---

# Automotive Market Intelligence Skill - Closure Systems & Car Entry Focus

Generate high-quality competitive intelligence summaries and executive briefs for automotive closure systems and car entry markets, with structured metadata extraction and strategic analysis.

**PRIMARY FOCUS:** Door modules, window regulators, latches, smart entry systems, and closure applications.

**CRITICAL INTELLIGENCE:** OEM strategy shifts (EV slowdowns, hybrid resurgence, powertrain diversification) as leading indicators for closure system demand.

## Quick Start

### Summarize a Single Article

```
Input: Article text or URL
Output: Structured summary with metadata
```

Use the standard summarization workflow (see below) to extract:
- Key developments (3-5 bullets)
- Companies mentioned
- Topics covered
- Strategic implications
- Priority assessment

### Generate Executive Brief

```
Input: Multiple summaries from a time period
Output: Synthesized weekly/monthly brief
```

Use the executive brief template in `references/executive-brief-template.md`.

## Core Workflows

### 1. Article Summarization Workflow

**Input:** Automotive industry article (news, press release, patent, regulatory filing)

**Process:**
1. **Extract factual information**
   - What happened? (announcement, partnership, regulatory change, technology development)
   - Who is involved? (companies, executives, entities)
   - When? (date, timeline, milestones)
   - Where? (region, facility, market)

2. **Categorize using taxonomy** (see `references/topic-taxonomy.md`)
   - Primary topic (OEM Strategy Shifts, Closure Technology, OEM Programs, Partnerships, Regulatory, Supply Chain, Manufacturing, Financial, Other)
   - Secondary topics if applicable
   - Companies mentioned (see `references/company-watchlist.md`)

3. **Assess priority** (see Priority Assessment Criteria below)
   - **High**: Game-changing developments, major partnerships, significant regulatory shifts
   - **Medium**: Incremental improvements, minor partnerships, routine announcements
   - **Low**: Background information, historical context, general industry trends

4. **Extract strategic implications**
   - What does this mean for competitors?
   - How might this impact the supply chain?
   - What strategic moves might follow?
   - Which companies are positioned to benefit/lose?

5. **Format output** using `scripts/format_summary.py` or manual structure:
   ```
   TITLE: [Concise description - Company + Development]
   
   SOURCE: [Publication name, Date]
   URL: [Original link]
   
   KEY DEVELOPMENTS:
   • [3-5 bullet points, each 1-2 sentences]
   
   COMPANIES MENTIONED: [Comma-separated list]
   TOPICS: [Comma-separated list]
   PRIORITY: [High/Medium/Low]
   
   STRATEGIC IMPLICATIONS:
   [2-4 sentences analyzing competitive impact]
   
   RECOMMENDED ACTIONS:
   [Optional: 1-2 specific follow-up actions]
   ```

### 2. Executive Brief Generation

**Input:** Collection of summaries from a specific time period (week/month)

**Process:**
1. **Load template** from `references/executive-brief-template.md`
2. **Synthesize summaries** by topic area
3. **Identify emerging trends** (3+ related developments)
4. **Highlight high-priority items** (mention count, strategic significance)
5. **Format using standard structure** (see template)

Use `scripts/generate_brief.py` for automated compilation or follow template manually.

### 3. Daily Digest Creation

**Input:** All summaries from previous day

**Process:**
1. **Group by topic** (Battery Tech, Partnerships, etc.)
2. **Prioritize** (High priority items first)
3. **Format for Teams** (concise, scannable)
4. **Include links** to full summaries in SharePoint

Format:
```
 Yesterday's Market Intelligence

HIGH PRIORITY:
• [Company]: [Brief description] → [Link]

BATTERY TECHNOLOGY:
• [Development 1]
• [Development 2]

PARTNERSHIPS:
• [Development 1]

[Total items: X | High priority: Y]
```

## Priority Assessment Criteria

**High Priority (Immediate attention required):**
- **OEM strategy shifts:** EV slowdowns/delays, hybrid pivots, ICE investment resumption, powertrain diversification
- **Financial writedowns:** Multi-billion dollar charges related to EV programs (signals fundamental strategy changes)
- **Major closure system awards:** New platform wins, multi-year supply agreements, design wins at key OEMs
- **Technology breakthroughs:** New latch designs, smart entry systems, sensor integration innovations
- **Significant regulatory changes:** Safety standards, cybersecurity requirements affecting closure/entry systems
- **M&A activity:** Consolidation in closure systems space, vertical integration moves
- **Executive leadership changes** at key OEM customers or closure system competitors

**Medium Priority (Monitor closely):**
- **Incremental OEM target adjustments:** Minor timeline shifts, market-specific strategy changes
- **Regional platform launches:** New vehicle programs, SOP dates for closure-relevant platforms
- **Technology partnerships:** Component supplier agreements (sensors, actuators, semiconductors)
- **Capacity expansions:** Competitor facility announcements, regional manufacturing investments
- **Product launches:** New vehicle models with notable closure features
- **Quarterly earnings:** OEM or competitor financial results with closure-specific guidance

**Low Priority (Background context):**
- **General industry commentary** without specific closure implications
- **Historical retrospectives** or market analyses
- **Trade show participation** without technology announcements
- **Routine business updates** from competitors
- **Non-closure supplier developments**

## Quality Standards

**Good Summary Characteristics:**
-  Factual, specific, verifiable
-  Focuses on new information
-  Clear company attribution
-  Quantified when possible (dates, amounts, capacities)
-  Strategic implications beyond the obvious
-  Concise (avoid verbosity)

**Avoid:**
-  Marketing language or hype
-  Speculation without basis
-  Overly technical jargon (explain when needed)
-  Redundant information
-  Missing key facts (who, what, when, where)

## File Naming Conventions

Follow the project architecture standards:

**Raw Intelligence:**
`[Source]_[Company]_[Topic]_[YYYYMMDD].[ext]`
Example: `AutoNews_Ford_Strategy_20251218.pdf`

**AI Summaries:**
`Summary_[Company]_[Topic]_[YYYYMMDD].docx`
Example: `Summary_Ford_Strategy_20251218.docx`

**Executive Briefs:**
- Weekly: `Week_[##]_[MonDD-MonDD].docx` → `Week_03_Jan13-19.docx`
- Monthly: `[Month]_[YYYY]_Summary.docx` → `January_2026_Summary.docx`

## Metadata Schema

When creating summaries, always extract and structure this metadata:

**Required Fields:**
- Title
- Source (Bloomberg, Automotive News, Reuters, Patent, Press Release, Other)
- Date Published
- Companies Mentioned (comma-separated)
- Topics (Battery Tech, Partnerships, Regulatory, Supply Chain, Manufacturing, Other)
- Priority (High, Medium, Low)
- Original URL

**Analysis Fields:**
- Key Insights (3-5 bullet points)
- Strategic Implications (2-4 sentences)
- Recommended Actions (1-2 specific next steps)

**Tracking Fields:**
- Summary Date (when generated)
- Review Status (Not Reviewed, Reviewed, Approved)

## Advanced Features

### Patent Analysis

When summarizing patents from Google Patents or USPTO:
1. Extract: Patent number, filing date, inventors, assignee
2. Summarize: Core innovation, technical approach, potential applications
3. Assess: Strategic implications (defensive vs. offensive IP, technology direction)
4. Compare: Prior art or related patents from competitors

### Regulatory Deep Dives

When analyzing regulatory changes:
1. Identify: Which regulations, which regions, effective dates
2. Analyze: Who is affected (OEMs, suppliers, specific segments)
3. Assess: Compliance requirements, timeline pressure
4. Strategize: Winners/losers, potential business impacts

### Multi-Source Synthesis

When multiple sources cover the same development:
1. Verify consistency across sources
2. Extract unique details from each source
3. Note any conflicting information
4. Synthesize into single comprehensive summary

## References

For detailed information, see:
- **Company Watchlist**: `references/company-watchlist.md` - Key companies being tracked
- **Topic Taxonomy**: `references/topic-taxonomy.md` - Intelligence categories and keywords
- **Executive Brief Template**: `references/executive-brief-template.md` - Standard report format
- **Prompt Library**: `references/prompts.md` - Proven prompt patterns for different content types

## Scripts

Automation helpers available:
- **format_summary.py**: Structure summaries with proper metadata (use when Claude needs deterministic formatting)
- **generate_brief.py**: Compile weekly briefs from multiple summaries (use for automated brief generation)

## Assets

Templates for document generation:
- **summary-template.docx**: Word document template for AI summaries
- **brief-template.docx**: Executive brief template with formatting

## Tips for Success

1. **Start with the source** - Always link back to original content
2. **Quantify when possible** - Dates, amounts, capacities, timelines
3. **Focus on the "so what"** - Strategic implications matter more than restating facts
4. **Be consistent** - Use the same taxonomy and priority criteria across all summaries
5. **Update regularly** - As new information emerges, flag for updates
6. **Cross-reference** - Link related summaries (e.g., partnership announcement → follow-up progress)

## Example Summary

```
TITLE: Ford Delays EV Expansion, Pivots to Hybrid Strategy - Impacts Closure Systems Roadmap

SOURCE: Automotive News, December 18, 2025
URL: https://www.reuters.com/business/autos-transportation/ford-retreats-evs-takes-195-billion-charge-trump-policies-take-hold-2025-12-15/

KEY DEVELOPMENTS:
• Ford announced $19.5 billion write-down on EV investments, canceling next-generation electric F-150 Lightning and three-row EV SUV programs originally scheduled for 2026-2027 launch.
• Company pivoting to hybrid emphasis with increased PHEV production at Kentucky and Michigan plants, targeting 40% of light-duty vehicles as hybrid/PHEV by 2028 (up from 15% current).
• ICE truck and SUV production increasing at multiple plants, with $13 billion reinvestment in traditional powertrain capacity through 2030.
• CFO stated "policies, not consumers" were driving EV push; expects hybrid demand to remain strong as consumers seek "bridge technology."

COMPANIES MENTIONED: Ford
TOPICS: OEM Strategy Shifts, OEM Programs & Platforms
PRIORITY: High

STRATEGIC IMPLICATIONS:
This represents a fundamental shift in Ford's powertrain strategy with direct implications for closure systems suppliers. The cancellation of dedicated EV platforms (which typically require lightweight, frameless, and electric-specific closure designs) reduces demand for premium EV closure technologies. Simultaneously, the hybrid pivot creates opportunities for cost-optimized closure systems that balance weight reduction with traditional design requirements. The ICE reinvestment extends the life of proven closure architectures, potentially increasing volumes of existing designs. Suppliers heavily invested in EV-specific closure technologies may face margin pressure, while those with flexible platform capabilities are better positioned. This also signals potential OEM cost reduction pressure across the supply base as Ford seeks to improve profitability.

RECOMMENDED ACTIONS:
1. Assess current and pipeline Ford programs for closure content - identify which EV programs are affected and volume impact to closure systems
2. Evaluate closure design requirements for hybrid platforms vs. EV vs. ICE - adjust technology roadmap and R&D investments
3. Monitor competitor (GM, Stellantis, Hyundai) strategy announcements - assess if this is industry-wide trend or Ford-specific
```

## Integration Points

This skill is designed to work seamlessly with:
- **SharePoint**: Summaries and briefs saved to appropriate libraries with metadata
- **Power Automate**: Triggered workflows for automated processing
- **Microsoft Teams**: Daily digests and high-priority alerts
- (**Azure OpenAI**: Batch processing of multiple articles) --> if possible
