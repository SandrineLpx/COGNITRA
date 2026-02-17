# Company Watchlist (Closure Systems / Car Entry Focus)

Use this watchlist to:
- detect companies in source text (cheap pre-filter before LLM calls)
- normalize names in outputs (use the canonical name)
- support relevance and priority scoring

Keep aliases minimal (0–2). Add an alias only if it commonly appears in sources.

---

## Our company

- Kiekert AG (Kiekert)

---

## Direct competitors (examples)

- Brose SE (Brose, Brose Group)
- Inteva Products (Inteva)
- Magna International (Magna)
- AISIN Corporation (Aisin)
- Valeo SA (Valeo)
- Continental AG (Continental)
- ZF Friedrichshafen AG (ZF)

---

## Indirect competitors / adjacent

- Bosch (Robert Bosch GmbH, Bosch)
- Denso Corporation (Denso)
- LG Electronics (LG)
- Panasonic (Panasonic)
- Samsung (Samsung)

---

## OEMs (examples)

- Volkswagen Group (Volkswagen, VW, Audi, Skoda, SEAT)
- Stellantis (Stellantis)
- BMW Group (BMW)
- Mercedes-Benz Group (Mercedes-Benz)
- Ford Motor Company (Ford)
- General Motors (GM)
- Toyota Motor Corporation (Toyota)
- Hyundai Motor Group (Hyundai, Kia)
- Tesla (Tesla)

---

## Tech partners / components (examples)

- NXP Semiconductors (NXP)
- Infineon Technologies (Infineon)
- Qualcomm (Qualcomm)
- Nvidia (NVIDIA)
- TSMC (TSMC)
- Arm (ARM)

---

## Government and regulators (optional)

Add only if you frequently ingest official releases and want consistent naming.

- European Commission (EU)
- UNECE (UNECE)
- NHTSA (NHTSA)
- USTR (USTR)
- US Department of Commerce (Department of Commerce)
- MIIT (China MIIT)

---

## Footprint regions (Kiekert relevance)

Use these regions to elevate relevance even when an item is not explicitly about closure systems.

- India
- China
- Europe (including Russia) — includes UK and Turkey; broad mentions like Europe, EU, European, EMEA map here
- Africa — primarily Morocco and South Africa production footprint
- US
- Mexico
- Thailand

Notes:
- Always populate `country_mentions` with any countries explicitly mentioned in the source.
- Russia mentions must roll up to Europe (including Russia).
- Morocco and South Africa mentions must roll up to Africa.
