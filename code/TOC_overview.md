# TOC Pipeline Flow

## Step 1: Classification (`11_document_classifier.py`)

The OpenAI vision API (GPT-4o-mini) looks at each page image and classifies it into categories. When a page is identified as `"Pleading table of contents"`, a second vision call extracts the structured TOC content. The result is saved as `metadata/page_XXXX_TOC.txt` in markdown heading format:

```
# TABLE OF CONTENTS
## INTRODUCTION
## ARGUMENT
### Point One
#### Subpoint A
#### Subpoint B
### Point Two
## CONCLUSION
```

## Step 2: Formatting (`20_toc_formatter.py`)

Strips the "TABLE OF CONTENTS" header line and promotes all remaining headings up one level (removes one `#`). Simple cleanup.

## Step 3: TOC Chunking (`30_toc_chunker.py`) — the core

This is where the heavy lifting happens:

1. **Parse TOC** into structured entries (`TocEntry` dataclass with order, level, title, label, normalized text)
2. **Align each TOC entry to the document body** using fuzzy matching (`difflib.SequenceMatcher` at 72% weight + 28% label matching). Threshold: 0.80 confidence score
3. **Build hierarchical paths** for each entry (e.g., `"ARGUMENT / Point One / Subpoint A"`)
4. **Identify leaf sections** — only the lowest-level sections (those with no children) become chunk boundaries
5. **Chunk leaf sections** respecting token limits (min 150, max 700), splitting on sentence boundaries when needed

## Step 4: Non-TOC Fallback (`31_semantic_chunker.py`)

Documents without TOC get page-level grouping instead — combines adjacent pages based on token count, semantic continuity signals (sentence endings, conjunctions), and exhibit boundaries. Less precise section paths like `"CONTENT / Pages 5-7"`.

## The Decision Point (orchestrator, line ~430)

The orchestrator checks each document's `metadata/` folder for `*_TOC.txt` files. If found -> TOC chunker. If not -> semantic chunker.

## Key characteristics

- **TOC extraction is vision-based** — it reads the page image, not the text
- **Body alignment is fuzzy** — handles OCR imperfections and formatting differences
- **Leaf-only chunking** means parent sections don't create their own chunks; only terminal sections do
- **Exhibits** are largely ignored by the TOC chunker but handled specially by the semantic chunker
