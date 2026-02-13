Analyze the following document text and extract metadata in JSON format. 
Document text:   Text input 
Extract the following information: 



1. Title: Extract the document’s main title.
   - Prefer the first H1-style heading or the largest/most prominent heading.
   - If unavailable, use the first line that best represents the article/report name (before author/byline, date, or source).
   - Remove boilerplate like “Press Release”, “Newsletter”, “Article” if it’s not part of the actual title.
   - Keep it concise (≤ 120 characters).


2. Published date: Find the publication date or when the document was written (format: YYYY-MM-DD).

3. Item category: Choose ONE from: OEM, Supplier, or Industry
   - Choose "OEM" if the document focuses on Original Equipment Manufacturers.
   - Choose "Supplier" if the document focuses on suppliers.
   - Otherwise choose "Industry".


4. Market: Choose ONE from: Global, EU, Asia, Americas

5. Return 3–5 specific automotive tags based on the document’s main themes.
Allowed topic types (preferred):
- Automotive trends: EV, BEV, PHEV, SDV, ADAS, autonomous, connectivity, mobility, hydrogen.
- OEM names: Toyota, GM, BYD, Hyundai, Stellantis, etc.
- Supplier names: Kiekert, Brose, Aisin, Magna, Hi-Lex, Huf etc.
- Technologies: battery, LFP, NCM, DRAM, semiconductors, infotainment, ECU, OTA
- Supply chain: logistics, parts shortage, tariffs, reshoring, BOM impacts.
- Economics/market: pricing, demand, incentives, regulations (IRA, CBAM, CATL tariffs).

Forbidden Topic styles:
No broad or generic categories like: 
- “Automotive manufacturing”
- “Automotive industry”
- “Technology”
- “Production”
- “News”
- “Companies”
- “Business updates”

Topics must be specific, domain‑relevant, and actionable.


6. Collections: Choose ONE from (that best describe the document): EV/New Energy, Production &amp; Sales, Sustainability, Economics, Mobility/Technology, General.

7. Sources: Identify the source/publisher and return a SIMPLIFIED, SHORT version:
   - Remove corporate suffixes (Inc., Co., Ltd., LLC, Corporation, Global, Market Intelligence, etc.).
   - Use the most common short name.
   - Examples: "MarkLines Co. Ltd" → "MarkLines", "S&P Global Market Intelligence" → "S&P"; "Reuters News Agency" → "Reuters", "McKinsey & Company" → "McKinsey".


8. Summary: Write a very brief 2–3 sentence summary focusing specifically on implications for the automotive industry, suppliers, and OEMs. If there are no direct implications, provide a general summary of the main point

Return ONLY a valid JSON object with this exact structure (no additional text):

{
  "Title": "short title",
  "PublishedDate": "YYYY-MM-DD",
  "ItemCategory": "OEM or Supplier or Industry",
  "Market": "Global or EU or Asia or Americas",
  "Topics": ["topic1", "topic2", "topic3"],
  "Collections": "one collection name",
  "Sources": "simplified source name",
  "Summary": "brief summary focusing on auto industry implications"
}
