# Legal Document RAG Pipeline

## Objective
Pre-processes litigation filings into contextually tagged chunks for attorney use in a RAG repository.

## Purpose
Standard RAG systems don't work well for legal documents because they ignore context. The same text means different things depending on whether it's in a complaint vs. a motion, the main argument vs. an exhibit, or plaintiff's allegation vs. defendant's characterization. When it was filed and by whom matters.

This system extracts and embeds in each chunk the minimum background knowledge a litigator would need to make sense of that chunk independently: what document it's from, which part, who filed it and when, and what argument section it belongs to. Each chunk becomes a self-contained unit with enough context for useful legal retrieval.

[→ More on the thinking behind the app is below](#why-standard-rag-fails-for-legal-work)

---

## Pipeline Overview

![Pipeline Beginnging to End Diagram](./images/chunk_page_image.png)




### Key Steps:
1. **Extract**: PDF → (PNG images + .txt); remove line numbers
2. **Classify**: Each page typed (pleading body, exhibit, TOC, etc.) via GPT-5-mini vision
3. **Structure**: Extract doc and case info from caption page; TOC and section headings; exhibit labels
4. **Clean up** *(under construction)*: Minor formatting, move footnotes inline and tag, tag block quotes
5. **Chunk**: Smart splitting respecting document structure and token limits
6. **Output**: Organized and named files/folders + JSONL with searchable chunks

---

## Pipeline Mechanics

### 1. PDF Decomposition

<img src="./images/pdf_split_2.png" width="600" alt="Step 1: PDF decomposition showing creation of text files, metadata, and PNG folders">

- **Input**: PDF litigation filings
- **Process**: PyMuPDF extraction at 300 DPI (or other local PDF tools like Acrobat, ABBYY)
- **Output**: 
  - `PNG/page_XXXX.png` - High-quality page images
  - `text_pages/page_XXXX.txt` - OCR'd text with line numbers removed
  - `metadata/` - (empty until classification step)

### 2. Page Classification (Critical Step)

<img src="./images/classification_first_part_bigger.png" width="400" alt="Step 1: PDF decomposition showing creation of text files, metadata, and PNG folders">

Using GPT-5-mini vision model, each page is classified:

| Category | Description |
|----------|-------------|
| Pleading first page | Identifies document metadata |
| Table of contents | Used for chunking |
| Table of authorities |  
| Pleading body | Main legal arguments |
| Exhibit cover/content | Labelled and titled |
| Court form |
| Proof of service |

### 3. Metadata Extraction
From classified pages, extract:
- **Document title** - From caption page
- **Filing date** - From court stamps
- **Filing party** - Simplified (plaintiff, defendant, etc.)
- **Exhibit labels** - A, B, 1, 2, etc.
- **TOC structure** - Section headings and hierarchy

#### Example: TOC Extraction and Processing
<img src="./images/TOC_map_bigger.png" width="700" alt="Extraction of structured TOC">

The TOC is converted from visual layout to structured markdown. This hashtag hierarhy is later mapped onto headers in the pleading body pages, which allows them to be chunked by argument section instead of page or tokens. 

### 4. Text Cleanup *(under construction)*
- Footnotes are tagged [FN(3)]...footnote text...[FN(3)_end] and moved into the body of the text. This prevents 
- Block quotes are tagged [Block_quote] because formatting losses make them difficult to spot.  
- Additional formatting cleanup

### 5. Chunking

#### For Documents WITH Table of Contents:
- Match TOC entries to body headings
- Map TOC structure to markdown hierarchy
- Inject hierarchy (###) markers in headings in OCR'd .txt files
- Organize chunks by section with TOC metadata
- Purpose: attribute pieces of text to argument organization

#### For Documents WITHOUT Table of Contents:
- Smart page combining based on:
  - Token limits (500-800 default)
  - Sentence boundaries
  - Exhibit boundaries
  - Structural markers
 
#### 6. Final Chunk Format
The app is designed to take this input and convert it into the chunks below.

<img src="./images/chunking.png" width="600" alt="Step 1: PDF decomposition showing creation of text files, metadata, and PNG folders">

Chunks are outputted in JSON contains:
```json
{
  "document_title": "DEFENDANTS' MEMORANDUM OF POINTS AND AUTHORITIES IN SUPPORT OF DEMURRER TO FIRST AMENDED COMPLAINT",
  "filing_party": "Defendants",
  "filing_date": "2024-03-15",
  "section_path": "BACKGROUND / A. Plaintiffs’ Factual Allegations",
  "chunk_ID": 14,
  "document_ID": 54,
  "page_numbers": [8, 9],
  "exhibit_label": null,
  "exhibit_title": null,
  "page_type": "pleading_body",
  "text": "
[PDF_page_8_cont.] A. Plaintiffs’ Factual Allegations.
Plaintiffs challenge recent changes to the TAJP implemented by Defendants, the Judicial
Council of California and Chief Justice Tani G. Cantil-Sakauye. FAC ¶ 1.
Article VI, section 6(e) of the California Constitution provides that the Chief Justice "shall
seek to expedite judicial business and to equalize the work of judges," and "may provide for the
assignment of any judge to another court … with the judge’s consent." FAC ¶ 3 (quoting Cal.
Const. art. VI, § 6(e)). Section 6(e) provides that "[a] retired judge who consents may be
assigned to any court." Id.
According to the FAC, the TAJP establishes the structure by which the Chief Justice
"temporarily assigns retired judges to fill judicial vacancies and to cover for vacations, illnesses,
disqualification and other absences." FAC ¶ 2. To be eligible to participate in the TAJP, a retired
judge must not have been defeated in an election for office, must not have been removed from
 [PDF_page_9] MEM. OF P. & A. IN SUPP. OF DEMURRER
office by the Commission on Judicial Performance, and must have met minimum age and years-
of-service requirements. Id. ¶ 4 (citing Gov’t Code § 75025). To remain in the program, a retired
judge must, at a minimum, "serve at least 25 days each fiscal year." Id. ¶ 5. Plaintiffs allege that
until May 21, 2018, there was no maximum limit on the number of days a retired judge could
participate in the TAJP. Id. ¶ 7.
     "

}

///////////////////

```json
{
  "document_title": "DEFENDANTS' MEMORANDUM OF POINTS AND AUTHORITIES IN SUPPORT OF DEMURRER TO FIRST AMENDED COMPLAINT",
  "filing_party": "Defendants",
  "filing_date": "2024-03-15",
  "section_path": "BACKGROUND / A. Plaintiffs’ Factual Allegations",
  "chunk_ID": 15,
  "document_ID": 54,
  "page_numbers": [9],
  "exhibit_label": null,
  "exhibit_title": null,
  "page_type": "pleading_body",
  "text": "
[PDF_page_9_cont] On May 21, 2018, Defendants limited the number of days a retired judge can participate in
the TAJP to 1,320-service days. FAC ¶ 7. The FAC alleges that all plaintiffs have already
accumulated over 1,320-service days in the program. Id. ¶¶ 8-16.
According to Plaintiffs, the 1,320-day service limit prevents them from participating in the
TAJP under the same terms and conditions “as are applicable to younger judges." FAC ¶ 16.
They allege that the 1,320-day service limit “has a disparate impact on plaintiffs and other
persons of their age" because they "will no longer be given assignments unless they receive an
'exception' to the policy." Id. ¶ 24. Plaintiffs summarily allege the 1,320-day service limit “does
not apply to younger, more recently retired judges." Id. ¶ 26.
The FAC states two causes of action. Count One alleges unlawful disparate impact age
discrimination in violation of the FEHA. FAC ¶ 30. Count Two alleges "Violation of the
California Constitution," claiming that the 1,320-day service limit violates sections 6(d) and 6(e)
of article VI of the California Constitution. Id. ¶¶ 33-34. Plaintiffs seek "back pay, front pay,
and other monetary relief," as well as declaratory and injunctive relief. See FAC at Prayer for
Relief."
}
'''


### 5. Output Structure
```
[Document_Name]/
├── PNG/                 # Page images
├── text_pages/          # Extracted text
├── metadata/            
│   ├── [doc]_classification.csv    # Page types
│   ├── page_XXXX_caption.txt       # Document metadata
│   └── page_XXXX_TOC.txt           # Table of contents
└── chunks/              
    ├── chunks.jsonl     # All chunks with metadata
    └── chunk_XXXX.txt   # Individual chunk files
```


```

---

## Usage

### Requirements
- Python 3.9+
- OpenAI API key (set as `OPENAI_API_KEY` environment variable)

### Installation
```bash
git clone [repository]
cd legal-rag-pipeline
pip install -r requirements.txt
```

### Basic Usage
```bash
# Place PDFs in the PDFs/ folder, then:
python pipeline.py

# For CSV updates only:
python pipeline.py --update-mode --csv-type output
```

### Scripts

| Script | Purpose | Notes |
|--------|---------|-------|
| `pipeline.py` | Main orchestrator - runs entire pipeline | Entry point |
| `prompts.py` | All prompts for classification and vision models | Required by classifier |
| `01_pdf_extractor-001.py` | PDF → PNG + text extraction | First step |
| `02_openai_classifier_03_gpt_5.py` | Page classification via GPT-5 vision | **Most critical** |
| `03_toc_fix_script- USEFUL.py` | Clean/structure TOC for chunking | Essential for TOC docs |
| `04_doc_title_extraction_mk_csv_app.py` | Extract document metadata to CSV | Creates output.csv |
| `05_simple_folder_rename.py` | Standardize folder names | Creates standardized.csv |
| `06_sync_csv_changes.py` | Sync CSV edits back to source files | Bidirectional sync |
| `07_TOC_text_integrator_and_chunker.py` | Chunk documents with TOC | Uses cleaned TOC |
| `08_chunker_non-TOC_docs.py` | Chunk documents without TOC | Fallback chunking |

---

## Known Limitations

- **Classification errors**: Misidentified exhibits can cascade. Manual review recommended.
- **Cross-page content**: Headers/text breaking across pages may be split
- **Nested exhibits**: Exhibits containing other exhibits need manual handling
- **No error recovery**: Currently no automated correction after misclassification

---

## Status: Beta
This pipeline is functional but actively being refined. Contributions and bug reports welcome.

---

## Why Standard RAG Fails for Legal Work

<details>
<summary>Click to expand philosophical discussion</summary>

### The Index Card Analogy
Think of a RAG database as a big box of index cards. Each card is a chunk of text, and a robot—a retrieval algorithm, not an AI—compiles a small stack of cards most similar to the user's query and passes those to the AI. The robot itself is not an AI; it's dumb. It doesn't make sense of each chunk in relation to every other chunk. In fact, it doesn't even know whether two chunks are from the same document.

### Why Context Is Everything
Legal arguments are nested and referential. Two chunks can look nearly identical in meaning but differ entirely in significance depending on their location in the corpus, the arguments parties have advanced, and the litigation's trajectory.

Consider: Defendant's motion summarizes plaintiff's fifth cause of action as alleged in the third amended complaint. This should not be used to understand what the fifth cause of action actually asserts, only what the defendant claims it asserts (or fails to). 

### The Negligence vs. Mandate Problem
Without contextual tagging, the statement "defendant was required to timely process plaintiff's tax information" could be:
1. An allegation of duty in a negligence claim (relief: monetary damages)
2. An allegation of ministerial duty (relief: writ of mandate ordering action)

If it's negligence against a government entity, there may be immunity. If plaintiff isn't also making a mandate claim for that same act, and the government is immune for negligence, the argument might be dead. The same text, completely different legal significance.

### Design Principles
- Use AI for non-discretionary classification only
- No AI for sophisticated thinking or variable outputs  
- Traditional OCR over AI (AI overcorrects and gets lazy)
- Minimum viable context: just what a litigator needs

One could never draft a brief with a box of document snippets and a robot that can only identify thematic similarity. In working with legal documents, retrieval unmoored from context will return flotsam. Each chunk must carry the background knowledge an attorney would already have when drafting.

</details>

---

## Classification Examples
[Add classification examples]

## License
[Add license information]
