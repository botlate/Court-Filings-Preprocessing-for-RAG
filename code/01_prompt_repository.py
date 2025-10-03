"""
Centralized Legal Document Processing Prompts Repository
All prompts used throughout the pipeline are defined here with proper categorization.
"""

# ============================================================================
# DOCUMENT CLASSIFICATION PROMPTS
# ============================================================================

CLASSIFICATION_PROMPT = (
    "You are an expert at identifying types of legal document pages in scanned court filings.\n"
    "Categories (choose exactly one):\n"
    "1. Form (example: judicial council forms like SUM-100, POS-010, FRCP forms like AO 88, or local court form)\n"
    "2. Pleading first page (typically shows case caption info)\n"
    "3. Pleading table of contents\n"
    "4. Pleading table of authorities\n"
    "5. Exhibit cover page\n"
    "6. Proof of service page\n"
    "7. Pleading body \n"
    "Important notes:\n"
    "- If the page is a document on pleading paper, it is 'Pleading first page' or 'Pleading body page,' not 'Form.'\n"
    "- Forms are pre-printed judicial council, FRCP, or local forms with form numbers.\n"
    "- Exhibit cover pages typically have 'Exhibit' and a letter/number prominently displayed.\n"
    "Answer with ONLY the category name from the list above. Do not add any explanation.\n"
    "Which category does this page fall in?"
)

FORM_TYPE_PROMPT = (
    "This page has been identified as a form. Please identify the specific form type.\n"
    "Common forms include: {}\n"
    "Look for the form number (usually in the header or footer).\n"
    "Answer with ONLY the form number (e.g., 'SUM-100') or 'Unknown' if you cannot determine it."
)

# ============================================================================
# EXHIBIT PROCESSING PROMPTS
# ============================================================================

EXHIBIT_LABEL_PROMPT = (
    "Since this is an exhibit cover page, identify the exhibit letter or number this cover page is indicating.\n"
    "(The page should be mostly blank but otherwise say 'Exhibit A', 'Exhibit 1', 'Exhibit B-1', etc.)\n"
    "Answer with ONLY the exhibit label (e.g., 'A', '1', 'B-1') without the word 'Exhibit'."
)

EXHIBIT_TITLE_PROMPT = (
    "This is the first page of an exhibit (following an exhibit cover page).\n"
    "Describe what this document is or provide its title in 10-30 words.\n"
    "Be specific and descriptive (e.g., 'Employment Agreement dated January 15, 2024' or 'Email correspondence regarding contract dispute').\n"
    "Answer with ONLY the description/title, no additional text."
)

EXHIBIT_CONTINUATION_PROMPT = (
    "The previous page was Exhibit {} cover page.\n"
    "Is this current page:\n"
    "1. A continuation of Exhibit {} (any document that is part of this exhibit - could be emails, "
    "contracts, letters, forms, receipts, photos, complaints, or any other evidence)\n"
    "2. A new exhibit cover page (a page clearly marked with 'Exhibit' followed by a letter/number)\n\n"
    "IMPORTANT: Most pages after an exhibit cover are continuations. Exhibits often contain "
    "multi-page documents. If you don't see 'Exhibit' with a letter/number prominently displayed, "
    "it's almost certainly a continuation.\n"
    "Answer with ONLY one of: 'continuation' or 'new exhibit'"
)

# ============================================================================
# DOCUMENT STRUCTURE EXTRACTION PROMPTS
# ============================================================================

TOC_EXTRACTION_PROMPT = (
    "Extract the Table of Contents verbatim but with structured markdown hierarchy (H1/H2/H3...), "
    "removing the page number any dots preceeding them (e.g. ......5). Do not change any content "
    "of heading itself and do not remove or modify a letter or number assigned to that heading."
)

CAPTION_EXTRACTION_PROMPT = (
    "This page has been identified as the first page of a state court pleading and we need you to accurately extract the relevant information from it. "
    "For all available information, extract the important caption details in this order: "
    "document title (include subtitle if any), filing date (often a court stamp or text added "
    "by the e-filing process), filing party (plaintiff/s, defendant/s, intervenor, etc. - specify briefly, e.g., typically listing 'plaintiff,' 'defendant', 'intervenor', 'court' - unless only one within a group is filing (e.g., 'Plaintiff Smith' in a suit where there are three plaintiffs)), "
    "named plaintiff(s), named defendant(s), filing attorneys (individual(s) and firm) and addresses, "
    "court, case number, judge, department, hearing time (if any), and hearing date (if any) in JSON."
)

# ============================================================================
# VISION MODEL PROMPTS
# ============================================================================

VISION_HEADING_DETECTION_PROMPT = (
    "You are an expert at analyzing legal documents to identify section headings and structural elements.\n\n"
    "TASK: Identify all section headings, subheadings, and major structural elements on this page.\n\n"
    "Look for:\n"
    "1. Major section headings (often in ALL CAPS or bold)\n"
    "2. Numbered/lettered subsections (I., II., A., B., 1., 2., etc.)\n"
    "3. Argument headings and sub-arguments\n"
    "4. Any text that appears to be formatted as a heading\n\n"
    "For each heading found, provide:\n"
    "- The exact text of the heading\n"
    "- Its apparent hierarchy level (1=major section, 2=subsection, 3=sub-subsection, etc.)\n"
    "- Any numbering/lettering prefix (I., A., 1., etc.)\n"
    "- Approximate position on page (top, middle, bottom)\n\n"
    "Format as JSON array: [{\"text\": \"heading text\", \"level\": 1, \"prefix\": \"I.\", \"position\": \"top\"}]\n\n"
    "If no clear headings are found, return empty array: []"
)

# ============================================================================
# FOLDER STANDARDIZATION PROMPTS
# ============================================================================

FOLDER_STANDARDIZATION_PROMPT = (
    "Transform this legal document folder name into a standardized format.\n\n"
    "REQUIRED FORMAT: YYYY MM DD [Party] [Document Type] - [Description]\n\n"
    "LEGAL ABBREVIATIONS TO USE:\n"
    "Document Types:\n"
    "- Complaints: FAC (First Amended), SAC (Second Amended), TAC (Third Amended)\n"
    "- Motions: Mtn, MSJ (Motion for Summary Judgment), MIL (Motion in Limine)\n"
    "- Responses: Oppo (Opposition), Reply, Answer\n"
    "- Other: Demurrer, POS (Proof of Service), Decl (Declaration), RJN (Request for Judicial Notice)\n\n"
    "Party Abbreviations:\n"
    "- Pltf/s (Plaintiff/s), Def/s (Defendant/s), Petnr/s (Petitioner/s), Resp/s (Respondent/s)\n\n"
    "RULES:\n"
    "- Maximum 60 characters total\n"
    "- Use consistent spacing and formatting\n"
    "- Include case-relevant details in description\n"
    "- Preserve important dates and case identifiers\n\n"
    "INPUT: {folder_name}\n"
    "DATE: {filing_date}\n"
    "PARTY: {filing_party}\n"
    "TITLE: {document_title}\n\n"
    "Return ONLY the standardized name, no explanation."
)

# ============================================================================
# FUTURE OCR ENHANCEMENT PROMPTS
# ============================================================================

# Placeholder prompts for future PaddleOCR integration
OCR_TEXT_CORRECTION_PROMPT = (
    "You are an expert at correcting OCR errors in legal documents.\n\n"
    "TASK: Review this OCR-extracted text and correct obvious errors while preserving legal terminology.\n\n"
    "COMMON LEGAL OCR ERRORS TO FIX:\n"
    "- 'Califomia' → 'California'\n"
    "- 'Civi1' → 'Civil'\n"
    "- 'p1aintiff' → 'plaintiff'\n"
    "- 'defendaI1t' → 'defendant'\n"
    "- 'C0urt' → 'Court'\n"
    "- Number/letter confusion: '0' vs 'O', '1' vs 'l' vs 'I'\n\n"
    "PRESERVE:\n"
    "- Case citations and legal references exactly as written\n"
    "- Proper names and technical terms\n"
    "- Line numbers and legal formatting\n\n"
    "Return the corrected text maintaining original formatting and structure."
)

OCR_TABLE_EXTRACTION_PROMPT = (
    "Extract table data from this OCR'd legal document page.\n\n"
    "TASK: Identify and structure any tabular data (schedules, exhibits, financial data, etc.)\n\n"
    "LEGAL TABLE TYPES:\n"
    "- Financial schedules and damages calculations\n"
    "- Exhibit lists and document indices\n"
    "- Timeline or chronology tables\n"
    "- Legal citation tables\n\n"
    "FORMAT: Return as structured JSON with clear column headers and row data.\n"
    "If no tables found, return: {\"tables\": []}"
)

OCR_FORM_FIELD_EXTRACTION_PROMPT = (
    "Extract form field data from this legal form.\n\n"
    "TASK: Identify filled-in fields, checkboxes, and form data.\n\n"
    "COMMON LEGAL FORM ELEMENTS:\n"
    "- Case information (case number, court, parties)\n"
    "- Checked boxes and selected options\n"
    "- Handwritten or typed entries\n"
    "- Signature blocks and dates\n\n"
    "Return structured data preserving field names and values."
)

# ============================================================================
# PROMPT CATEGORIES AND METADATA
# ============================================================================

PROMPT_CATEGORIES = {
    "classification": [
        "CLASSIFICATION_PROMPT",
        "FORM_TYPE_PROMPT"
    ],
    "exhibit_processing": [
        "EXHIBIT_LABEL_PROMPT", 
        "EXHIBIT_TITLE_PROMPT",
        "EXHIBIT_CONTINUATION_PROMPT"
    ],
    "structure_extraction": [
        "TOC_EXTRACTION_PROMPT",
        "CAPTION_EXTRACTION_PROMPT"
    ],
    "vision_analysis": [
        "VISION_HEADING_DETECTION_PROMPT"
    ],
    "folder_management": [
        "FOLDER_STANDARDIZATION_PROMPT"
    ],
    "ocr_enhancement": [
        "OCR_TEXT_CORRECTION_PROMPT",
        "OCR_TABLE_EXTRACTION_PROMPT", 
        "OCR_FORM_FIELD_EXTRACTION_PROMPT"
    ]
}

def get_prompts_by_category(category: str) -> dict:
    """Get all prompts in a specific category."""
    if category not in PROMPT_CATEGORIES:
        raise ValueError(f"Unknown category: {category}")
    
    result = {}
    for prompt_name in PROMPT_CATEGORIES[category]:
        result[prompt_name] = globals()[prompt_name]
    return result

def list_available_categories() -> list:
    """List all available prompt categories."""
    return list(PROMPT_CATEGORIES.keys())

# Backward compatibility exports
__all__ = [
    # Core classification
    "CLASSIFICATION_PROMPT", "FORM_TYPE_PROMPT",
    # Exhibit processing  
    "EXHIBIT_LABEL_PROMPT", "EXHIBIT_TITLE_PROMPT", "EXHIBIT_CONTINUATION_PROMPT",
    # Structure extraction
    "TOC_EXTRACTION_PROMPT", "CAPTION_EXTRACTION_PROMPT", 
    # Vision analysis
    "VISION_HEADING_DETECTION_PROMPT",
    # Folder management
    "FOLDER_STANDARDIZATION_PROMPT",
    # OCR enhancement (future)
    "OCR_TEXT_CORRECTION_PROMPT", "OCR_TABLE_EXTRACTION_PROMPT", "OCR_FORM_FIELD_EXTRACTION_PROMPT",
    # Utility functions
    "get_prompts_by_category", "list_available_categories", "PROMPT_CATEGORIES"
]