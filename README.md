# Legal Document Pipeline (Visual Walkthrough)

bunch of text here
</p>
</p>
<p align="center">
  <img src="images/pdf_split.png" width="80%">
  <br>
  <i>1. A PDF is decomposed into individual pages.</i>
</p>
</p>
bunch of text here
</p>
</p>


<p align="center">
  <img src="images/classification_basic3.png" width="80%">
  <br>
  <i>2. Each page image is sent to the AI for classification.</i>
</p>

<p align="center">
  <img src="images/classification_map.png" width="80%">
  <br>
  <i>3. The AI maps page numbers to document types.</i>
</p>

<p align="center">
  <i>4. A structured spreadsheet output is generated.</i>
</p>

| Filename | Category | Exhibit Label | Exhibit Title | Notes | Footnote | Block Quote |
|----------|----------|---------------|---------------|-------|----------|-------------|
| page_0001.png | Pleading first page | | | page_0001_caption.txt | | |
| page_0002.png | Table of Contents | | | page_0002_TOC.txt | | |
| page_0003.png | Pleading body | | | | Y | |
| page_0004.png | Pleading body | | | | | Y |
| page_0005.png | Exhibit cover page | A | Dismissal Letter | | | |
| page_0007.png | Exhibit content | A | | | | |
| page_0008.png | Proof of service page | | | | | |

<p align="center">
  <em>Classification results showing document structure and metadata extraction</em>
</p>

<p align="center">
  <img src="images/workflow.png" width="80%">
  <br>
  <i>5. The pipeline continues: TOC parsing, indexing, retrieval.</i>
</p>

---

### Swap in your actual images

Replace each file in `/images` with your real screenshots/diagrams, keeping the same names:
- `images/pdf_split.png`
- `images/classification_basic3.png` (export from your SVG to PNG for reliability)
- `images/classification_map.png` (export your .drawio to PNG)
- `images/spreadsheets.png`
- `images/workflow.png`

(*GitHub renders PNGs more consistently than SVGs*.)

