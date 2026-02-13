## **MSIS 549 AI/ML Project Proposal**

Note: This project is scoped to an automotive Tier-1 supplier (OEM, competitor monitoring, industry trend monitoring), but the underlying workflow—prioritized extraction \+ evidence-backed summaries—generalizes to any industry.

1. ### **Project owner information**

Sandrine Lepesqueux \- [slepes@uw.edu](mailto:slepes@uw.edu)

2. ### **Elevator Pitch**

A lot of organizations pay for premium market information, but still miss key signals because no one has time to turn it into usable intelligence. **Cognitra** is an AI workflow that converts content into prioritized, structured insights using relevance scoring, metadata extraction, and executive-style summaries with implications. Unlike noisy monitoring tools, Cognitra produces source-attributed, searchable outputs that become a reusable intelligence knowledge base.

**Targets:** cut monitoring/synthesis time **50–70%**, process **2–3×** more items, achieve **≥80% precision** on high-priority flags, and standardize **100%** of outputs with required fields.

3. ### **Project Description**

**How AI technologies will address this problem**

**In Phase 1 (MVP),** Cognitra will use generative AI to convert clean subscription articles into prioritized, structured intelligence. The system will score relevance (1–10) and assign priority based on organization-specific themes, extract standardized metadata into a schema-validated JSON record (entities such as companies/OEMs, topics, regions, dates, key facts, and notable metrics), and generate consistent executive-style outputs (“Key Developments” and “Strategic Implications”). To increase trust and reduce hallucinations, each key claim will include short evidence snippets with paragraph or section references. 

**In Phase 2** (stretch/roadmap), the same approach will be extended to complex PDFs (e.g., earnings decks and table-heavy reports) using more robust layout-aware extraction and table parsing before applying the same JSON \+ evidence method.

**Target users**  
Primary users are market/competitive intelligence analysts (starting with one user, scalable to a small team). 

Secondary users are strategy/product/sales/program teams and executives who need consistent, high-signal updates and searchable history.

**Data sources**  
Phase 1 focuses on clean subscription articles (e.g., S\&P Global, MarkLines, Bloomberg, Automotive News) plus optional public articles for demo data. Inputs are text/HTML or clean PDFs.

**Anticipated challenges**  
Ensuring outputs stay grounded (evidence for key claims), keeping JSON reliable and complete, tuning priority to minimize false “high priority” alerts, controlling cost/tokens, and managing SharePoint/Teams/Power Automate permissions.

4. ### **Implementation Plan**

**Type of solution**  
A lightweight **AI workflow/agent** with a **searchable repository** and optional dashboard: process new content, store structured intelligence records, and distribute high-priority alerts \+ a daily digest.

**Specific generative AI technologies**  
A lightweight AI workflow/agent with a searchable repository and optional dashboard: process new content, store structured intelligence records, and distribute high-priority alerts \+ a daily digest.

**Technical approach and methodology**  
Users add articles to an “Incoming” SharePoint library (or demo dataset). Automation extracts text, calls the LLM with a strict schema, validates JSON/evidence, stores results in an “Auto Intelligence” library (with metadata columns), and posts high-priority alerts and a daily digest to Teams (optional Power BI trends).

**Demo concept (GenAI & Agentic Fair)**  
The demo will show an end-to-end flow focused on business value and reliability. I will add a clean article into the “Incoming” library, show the workflow trigger and AI processing, and open the resulting intelligence record with structured metadata, “Key Developments,” “Strategic Implications,” and evidence snippets. I will then show a Teams high-priority alert and/or daily digest (may change based on results), and finish with a simple trend view (top companies/topics and recent high-priority items) to demonstrate that outputs are searchable and reusable over time.

