---
title: Executive Brief Export to .docx
description: Feature documentation for markdown-to-docx conversion of executive briefs
author: COGNITRA Platform
date: 2026-03-03
version: 1.0
status: active
tags: [brief, export, docx, feature]
---

# Executive Brief Export to .docx

## Overview

The COGNITRA platform now supports exporting executive briefs directly to Microsoft Word format (.docx), in addition to the existing Markdown export.

## Implementation

### New Module: `src/brief_to_docx.py`

A dedicated markdown-to-docx converter that:
- Parses markdown syntax and converts it to Word document formatting
- Preserves all markdown elements:
  - **Headings** (levels 1-3) → Word heading styles
  - **Bold text** (`**text**`) → Bold formatting
  - **Italics** (`*text*`) → Italic formatting
  - **Lists** (`- item`) → Bulleted lists with proper indentation
  - **Blockquotes** (`> text`) → Styled blockquotes with gray background and left border
  - **Code blocks** (triple backticks) → Monospace formatted blocks with background
  - **Inline code** (backticks) → Courier New formatting
  - **Links** (`[text](url)`) → Blue underlined text

### Features

- **Professional formatting**: Documents use standard Word styles (Heading 1, Heading 2, etc.)
- **Styling**: Blockquotes have gray backgrounds, code blocks are visually distinct
- **Title section**: Each document includes a centered title
- **Spacing**: Appropriate paragraph spacing for readability

### Integration Points

The .docx download buttons are provided in three locations within the Brief page:

1. **Saved Brief Downloads** - Download previously saved briefs
2. **Regenerated Brief Downloads** - Download newly regenerated brief versions
3. **Live Brief Downloads** - Download freshly generated briefs before saving

Each location provides both `.md` and `.docx` download options side-by-side.

## Usage

### In the Streamlit UI

1. Navigate to the **Brief** page
2. Generate or select a brief
3. Look for download buttons:
   - "Download saved brief (.md)" / "Download saved brief (.docx)"
   - "Download regenerated .md" / "Download regenerated .docx"
   - "Download .md" / "Download .docx"

4. Click the desired format to download

### Programmatic Usage

```python
from src.brief_to_docx import markdown_to_docx
from io import BytesIO

# Convert markdown to DOCX
markdown_content = "# My Brief\n\n## Section 1\nContent here..."
docx_bytes = markdown_to_docx(markdown_content, title="Executive Brief")

# Save to file
with open("output.docx", "wb") as f:
    f.write(docx_bytes.getvalue())

# Or use directly in Streamlit
st.download_button(
    "Download DOCX",
    data=docx_bytes.getvalue(),
    file_name="brief.docx",
    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
```

## Dependencies

- **python-docx** (≥ 0.8.11): Python library for creating and manipulating Word documents

Updated in:
- `requirements.txt`
- `pyproject.toml`

Install with: `pip install python-docx`

## Technical Notes

- The converter handles complex markdown structures including nested formatting
- All converted documents are valid Word 2007+ format (.docx)
- Documents maintain the citation formatting and source references from the original markdown
- Blockquote styling (gray background, left border) is applied via OpenXML directly
- Code blocks receive monospace formatting and visual distinction

## Future Enhancements

Potential improvements could include:
- Support for markdown tables
- Custom styling/branding (company logo, header/footer)
- Page numbers and table of contents
- Different document templates for different brief types
- PDF export option
