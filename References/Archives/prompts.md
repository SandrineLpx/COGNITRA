# Prompt Library

Proven prompt patterns for different types of automotive market intelligence content. Use these as templates and customize based on specific needs.

## Article Summarization Prompts

### General News Article

```
You are an automotive industry analyst specializing in competitive intelligence. Analyze the following article and create a structured intelligence summary.

Region tagging rules (Kiekert footprint):
- Always extract `country_mentions` (any countries explicitly mentioned).
- Always extract `regions_mentioned` and `regions_relevant_to_kiekert`.
- Footprint regions: India, China, Europe (including Russia), Africa, US, Mexico, Thailand.
- Europe roll-up includes: UK and Turkey and Russia; broad mentions like Europe, EU, European, EMEA map to Europe (including Russia).
- Africa roll-up is primarily driven by production footprint: Morocco and South Africa (also tag Africa if broadly mentioned).


Article: [PASTE ARTICLE TEXT OR URL]

Extract and structure the following information:

1. KEY DEVELOPMENTS (3-5 bullet points)
   - Focus on factual, new information
   - Include specific dates, numbers, locations when available
   - Each bullet should be 1-2 sentences

2. COMPANIES MENTIONED
   - List all companies referenced
   - Note their role (announcer, partner, competitor, supplier, etc.)

3. TOPIC CATEGORIZATION
   - Primary topic (from: Battery Tech, Partnerships, Regulatory, Supply Chain, Manufacturing, Tech Innovation, Market Competition, Financial, Executive/Organizational)
   - Secondary topics if applicable

4. PRIORITY ASSESSMENT
   - High, Medium, or Low
   - Briefly justify the priority level (1 sentence)

5. STRATEGIC IMPLICATIONS (2-4 sentences)
   - What does this mean for competitors?
   - How might this impact the supply chain?
   - What strategic responses might we expect?
   - Who stands to benefit or lose?

6. RECOMMENDED ACTIONS (1-2 specific next steps)
   - What should be monitored?
   - Who should be contacted or consulted?

Format your response as a structured intelligence brief suitable for SharePoint storage and executive review.
```

### Battery Technology Focus

```
You are a battery technology expert analyzing automotive battery developments. Review this article about battery technology and provide technical intelligence.

Article: [PASTE ARTICLE TEXT OR URL]

Analyze and extract:

1. TECHNICAL SPECIFICATIONS
   - Cell chemistry (NMC, NCA, LFP, solid-state, sodium-ion, etc.)
   - Form factor (cylindrical, prismatic, pouch; if specified, dimensions)
   - Energy density (Wh/kg, Wh/L)
   - Power characteristics (C-rate for charging/discharging)
   - Cycle life or warranty (if mentioned)
   - Operating temperature range
   - Cost metrics ($/kWh if mentioned)

2. TECHNOLOGY READINESS ASSESSMENT
   - Development stage (R&D, pilot, pre-production, mass production)
   - Timeline to commercialization
   - Production capacity targets
   - Technical risks or challenges mentioned

3. COMPETITIVE POSITIONING
   - How does this compare to current market leaders?
   - What advantages does this technology offer?
   - What are the trade-offs vs. established solutions?

4. STRATEGIC IMPLICATIONS
   - Impact on OEM battery strategy
   - Supplier ecosystem effects
   - Raw material supply chain impacts

Provide your analysis in structured format suitable for battery technology tracking.
```

### Partnership & Deal Analysis

```
You are a corporate strategy analyst specializing in automotive partnerships. Analyze this partnership/deal announcement.

Article: [PASTE ARTICLE TEXT OR URL]

Extract and analyze:

1. DEAL STRUCTURE
   - Type (JV, supply agreement, licensing, M&A, R&D collaboration, equity investment)
   - Parties involved (full legal names)
   - Financial terms (deal size, payment structure, equity stakes)
   - Duration or timeline
   - Geographic scope

2. STRATEGIC RATIONALE
   - What does each party gain?
   - What capabilities or assets are being combined?
   - What market positions are being strengthened?

3. COMPETITIVE IMPLICATIONS
   - Who is excluded or disadvantaged by this partnership?
   - How does this shift the competitive landscape?
   - Are there potential antitrust concerns?

4. SUPPLY CHAIN IMPACTS
   - How does this affect existing supplier relationships?
   - Does this create new dependencies or reduce vulnerabilities?
   - What does this signal about future sourcing strategies?

5. RISK ASSESSMENT
   - What could go wrong with this partnership?
   - Historical precedent for similar deals
   - Key execution challenges

Provide a structured partnership intelligence brief.
```

### Regulatory & Policy Analysis

```
You are a regulatory affairs expert tracking automotive policy developments. Analyze this regulatory announcement or policy change.

Article/Document: [PASTE TEXT OR URL]

Extract and analyze:

1. REGULATORY DETAILS
   - Issuing authority (agency, level of government)
   - Geographic scope (federal, state/province, EU, China, etc.)
   - Effective date and compliance timeline
   - Penalty structure for non-compliance

2. SPECIFIC REQUIREMENTS
   - What must companies do to comply?
   - Are there phase-in periods or exemptions?
   - What metrics or standards must be met?

3. AFFECTED PARTIES
   - Which companies/sectors are impacted?
   - Are there differential impacts (by size, region, technology)?
   - Who requested or lobbied for this regulation?

4. COMPLIANCE COMPLEXITY
   - How difficult is compliance?
   - What investments or changes are required?
   - Are there technical barriers?

5. COMPETITIVE IMPLICATIONS
   - Who has competitive advantage under these rules?
   - Who faces challenges?
   - Does this favor certain technologies or business models?

6. BROADER REGULATORY CONTEXT
   - How does this fit with other regulations (domestic and international)?
   - Is this part of a broader regulatory trend?
   - What future regulations might follow?

Provide a regulatory intelligence brief suitable for compliance and strategy teams.
```

### Patent Analysis

```
You are a patent analyst specializing in automotive technology IP. Analyze this patent filing or patent-related development.

Patent: [PATENT NUMBER, LINK, OR SUMMARY]

Extract and analyze:

1. PATENT DETAILS
   - Patent number(s) and/or application numbers
   - Filing date, publication date, grant date (as applicable)
   - Inventors and assignee (company)
   - Patent classification codes
   - Geographic coverage (US, EP, China, PCT, etc.)

2. TECHNICAL INNOVATION
   - What problem does this patent solve?
   - What is the core technical approach or invention?
   - How is this different from prior art?
   - What are the key claims?

3. STRATEGIC INTENT
   - Offensive IP (blocking competitors) or defensive (freedom to operate)?
   - Is this protecting a core technology or a peripheral innovation?
   - Does this appear to be part of a patent portfolio strategy?

4. COMPETITIVE IMPLICATIONS
   - Which competitors might be affected?
   - Does this create IP barriers in specific technology areas?
   - Are there workaround possibilities?

5. RELATED IP
   - Are there related patents in this family?
   - Has the same company filed other recent patents in this area?
   - Have competitors filed patents addressing similar problems?

6. COMMERCIALIZATION ASSESSMENT
   - How close is this technology to commercial deployment?
   - What products or applications might use this?
   - Timeline to market based on patent maturity

Provide a patent intelligence brief for IP strategy and technology planning.
```

## Executive Brief Generation Prompts

### Weekly Brief Synthesis

```
You are synthesizing a week's worth of automotive market intelligence into an executive brief. You have been provided with [X] individual intelligence summaries covering [date range].

Summaries:
[PASTE ALL INDIVIDUAL SUMMARIES]

Create a comprehensive weekly executive brief following this structure:

1. EXECUTIVE SUMMARY (2-3 sentences)
   - Highlight 1-2 most strategic developments
   - Note any emerging patterns or trends

2. HIGH PRIORITY DEVELOPMENTS (3-5 items)
   - Include only items marked "High Priority"
   - For each: title, 2-3 sentence summary, strategic implication, link

3. KEY DEVELOPMENTS BY TOPIC
   - Group remaining items by primary topic
   - Use bullet format (company - brief description)
   - Focus on Medium priority items; skip Low unless newsworthy

4. EMERGING TRENDS (2-3 trends)
   - Identify patterns across multiple items
   - Provide evidence (3+ supporting data points per trend)
   - Explain strategic significance

5. RECOMMENDED ACTIONS (3-5 specific actions)
   - Be specific about who should do what
   - Include rationale and timeline

Use the executive brief template format. Ensure the brief is:
- Concise yet comprehensive
- Strategic, not just factual recitation
- Actionable with clear next steps
- Professional in tone and formatting
```

### Monthly Brief Synthesis

```
You are creating a monthly strategic intelligence report for automotive industry executives. You have been provided with [X] weekly briefs and [Y] individual summaries covering [month year].

Weekly Briefs:
[PASTE ALL WEEKLY BRIEFS]

Additional Items:
[PASTE ANY INDIVIDUAL SUMMARIES NOT IN WEEKLY BRIEFS]

Create a comprehensive monthly executive brief following this structure:

1. EXECUTIVE SUMMARY (3-4 sentences)
   - Synthesize the month's most significant strategic developments
   - Highlight macro trends and competitive positioning shifts

2. MONTH IN REVIEW: TOP 5 STRATEGIC DEVELOPMENTS
   - Focus on highest-impact developments
   - Provide context and strategic assessment for each

3. MAJOR THEMES (3-5 themes)
   - Identify overarching patterns from the month's intelligence
   - For each theme: overview, supporting evidence (4+ items), implications
   - Analyze winners/losers and future trajectory

4. COMPETITIVE POSITIONING: MONTHLY SHIFTS
   - Track how the competitive landscape evolved
   - Note leadership changes by dimension (technology, scale, partnerships)

5. PARTNERSHIP ECOSYSTEM: MONTHLY MAP
   - Summarize new, expanded, and at-risk partnerships
   - Analyze network effects and strategic clustering

6. REGULATORY LANDSCAPE: MONTHLY UPDATE
   - New regulations, incentive changes, compliance deadlines
   - Analyze regional divergence and strategic implications

7. TECHNOLOGY READINESS TRACKING
   - For key emerging technologies, assess progress toward commercialization
   - Update timelines based on month's developments

8. RISK WATCH
   - Identify emerging risks (supply chain, geopolitical, technology, regulatory)

9. LOOKING AHEAD: NEXT MONTH & QUARTER
   - Key events to monitor
   - Strategic questions to answer

10. STRATEGIC RECOMMENDATIONS (5-7 recommendations)
    - High-level, strategic guidance
    - Prioritized with rationale and timeline

Use the monthly executive brief template. The brief should be:
- Strategic and synthesized (not just a compilation)
- Forward-looking with clear recommendations
- Supported by data and evidence
- Appropriate for C-suite audience (15-20 pages)
```

## Specialized Analysis Prompts

### Competitive Positioning Analysis

```
Analyze competitive positioning in [SPECIFIC AREA: e.g., solid-state battery development] based on recent intelligence.

Intelligence items:
[PASTE RELEVANT SUMMARIES]

Provide:

1. CURRENT LEADERS
   - Rank top 3-5 players
   - Justify rankings with specific evidence

2. FAST MOVERS
   - Identify companies making rapid progress
   - What strategies are enabling their progress?

3. LAGGARDS OR AT-RISK PLAYERS
   - Who is falling behind?
   - What are their vulnerabilities?

4. COMPETITIVE DYNAMICS
   - How is the landscape shifting?
   - What strategic moves might we expect next?

5. STRATEGIC IMPLICATIONS
   - What does this mean for overall market structure?
   - Who should we watch most closely?

Format as a competitive intelligence briefing.
```

### Trend Identification

```
Identify emerging trends from this collection of intelligence items.

Intelligence items:
[PASTE SUMMARIES FROM TIME PERIOD]

For each trend you identify:

1. TREND DEFINITION
   - Clear, concise name for the trend
   - 2-3 sentence description

2. EVIDENCE BASE
   - List 3+ supporting data points from the intelligence
   - Show breadth (multiple companies/regions/sources)

3. MOMENTUM ASSESSMENT
   - Is this accelerating, steady, or decelerating?
   - Timeline: short-term (< 1 year), medium (1-3 years), long-term (3+ years)

4. STRATEGIC SIGNIFICANCE
   - Why does this trend matter?
   - What might this enable or disrupt?

5. KEY PLAYERS
   - Which companies are driving or benefiting from this trend?

6. RISKS & UNCERTAINTIES
   - What could slow or reverse this trend?
   - What assumptions underlie this trend?

Focus on trends that have strategic implications, not just interesting observations.
```

### Gap Analysis

```
Based on recent intelligence, identify information gaps that should be prioritized for additional research.

Recent intelligence:
[PASTE SUMMARIES FROM RECENT PERIOD]

For each gap:

1. INFORMATION GAP DESCRIPTION
   - What specific information is missing?
   - Why did this gap become apparent?

2. STRATEGIC IMPORTANCE
   - Why does this information matter?
   - What decisions depend on filling this gap?

3. POTENTIAL SOURCES
   - Where might we find this information?
   - How difficult will it be to obtain?

4. RECOMMENDED RESEARCH APPROACH
   - Specific next steps
   - Resources required
   - Timeline

Prioritize gaps by strategic importance and feasibility of filling.
```

## Quality Control Prompts

### Summary Review & Enhancement

```
Review this intelligence summary for quality and completeness. Suggest improvements.

Original Summary:
[PASTE SUMMARY]

Evaluate across these dimensions:

1. FACTUAL ACCURACY
   - Are claims verifiable?
   - Are sources properly cited?
   - Are numbers/dates/names accurate?

2. COMPLETENESS
   - Are key facts (who, what, when, where, how much) present?
   - Is topic categorization appropriate?
   - Is priority assessment justified?

3. STRATEGIC INSIGHT
   - Do strategic implications go beyond obvious observations?
   - Are competitive dynamics well-analyzed?
   - Are recommendations specific and actionable?

4. CLARITY & CONCISENESS
   - Is language clear and jargon-free (or jargon explained)?
   - Are there redundancies?
   - Is formatting consistent?

5. PROFESSIONAL QUALITY
   - Is tone appropriate for executive audience?
   - Is structure logical?
   - Are there grammatical or stylistic issues?

Provide:
- Overall quality rating (Excellent, Good, Needs Work)
- Specific improvement suggestions
- Enhanced version if significant changes needed
```

## Prompt Customization Guidelines

### Tailoring for Your Organization

**Add company-specific context:**
```
Context: [Your company] is a tier-1 automotive supplier specializing in [domain]. We primarily serve [OEM customers] and compete with [competitors].

[Then insert standard prompt]
```

**Focus on specific stakeholder needs:**
```
Audience: This analysis is for [specific team/executive]. They care most about [specific concerns].

[Then insert standard prompt]
```

**Adjust technical depth:**
- **For technical teams**: "Provide detailed technical analysis suitable for engineers/scientists"
- **For executives**: "Provide high-level strategic analysis; avoid technical jargon"
- **For sales/business development**: "Focus on market opportunities and customer implications"

### Prompt Chain Patterns

**Multi-stage analysis:**

Stage 1: Extract facts
```
Extract all factual information from this article. List only objective facts with dates, numbers, and specific details. Do not provide analysis yet.
```

Stage 2: Analyze implications
```
Based on these facts: [PASTE STAGE 1 OUTPUT]
Now provide strategic analysis: What are the competitive implications? Who wins and loses? What might happen next?
```

Stage 3: Generate recommendations
```
Based on this analysis: [PASTE STAGE 2 OUTPUT]
Generate 3-5 specific, actionable recommendations with rationale and timeline.
```

**Iterative refinement:**

Iteration 1: Draft
```
Create an initial draft of [intelligence product]
```

Iteration 2: Critique
```
Critique this draft: [PASTE DRAFT]
Identify weaknesses, gaps, unclear sections, and areas for improvement.
```

Iteration 3: Refine
```
Based on this critique: [PASTE CRITIQUE]
Revise the draft addressing all identified issues.
```

## Best Practices

1. **Be specific**: Vague prompts yield vague results. Specify format, length, audience, focus.

2. **Provide context**: Include relevant background, company focus, stakeholder needs.

3. **Use examples**: Show the AI what good looks like with example outputs.

4. **Iterate**: First drafts are rarely perfect. Refine prompts based on results.

5. **Chain prompts**: Break complex tasks into steps for better quality.

6. **Quality check**: Always review AI outputs for accuracy, especially facts and numbers.

7. **Maintain consistency**: Use the same prompt patterns for similar content to ensure consistency.

8. **Update regularly**: As the AI improves or your needs change, refine your prompts.

## Prompt Version Control

Track which prompts work best for different scenarios:

```
Prompt: [NAME]
Version: [X.X]
Last Updated: [DATE]
Success Rate: [High/Medium/Low]
Best For: [Use case description]
Weaknesses: [Known limitations]
```

Maintain a living document of your most effective prompts and continuously refine them.

Last updated: February 2026
