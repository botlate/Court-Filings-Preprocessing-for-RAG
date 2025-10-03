# TOC_integrator_app_v7.py  (v7.1) - FINAL FIX
# Python 3.9+ | Stdlib only.
# Features:
# - TOC->body alignment with stable JSONL schema
# - Annotated pages with [PDF_page_X] headers and brace paths
# - Caption metadata extraction (title, filing party, filing date)
# - Leaf-section chunking: no overlap, sentence-safe, token-limited
# - Per-chunk .txt files + chunks.jsonl
# - Deterministic ordering and basic logging

from __future__ import annotations
import argparse, csv, difflib, json, re, sys, unicodedata, logging, time, hashlib, math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from bisect import bisect_right

# Import new ID system and metadata extraction
from id_system import DocumentIDManager, ChunkIDGenerator
from metadata_extractor import MetadataExtractor

APP_VERSION = "7.1"
SCHEMA_VERSION = "1.2"

# ---------- Regex / heuristics ----------
PAGE_TXT_RE = re.compile(r"^page_(\d{4})\.txt$", re.IGNORECASE)
PNG_FILENAME_RE = re.compile(r"^page_(\d{4})\.png$", re.IGNORECASE)
DOT_LEADER_TAIL_STRIP_RE = re.compile(r"\.{2,}\s*\d+\s*$")

HEAD_PREFIX_RE = re.compile(
    r"^("
    r"(?:[IVXLCDM]+\.?)|"        # I., II., ...
    r"(?:\d+(?:\.\d+)*\.?)|"     # 1., 1.2., ...
    r"(?:[A-Z]\.)|"              # A., B., ...
    r"(?:\(?\d+\))|"             # (1)
    r"(?:\(?[A-Z]\))"            # (A)
    r")\s+"
)

MONTHS = "(January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"{MONTHS}\s+\d{{1,2}},\s+\d{{4}}", re.IGNORECASE)
ATTY_FOR_RE = re.compile(r"Attorneys?\s+for\s+(.+)", re.IGNORECASE)
TITLE_RE = re.compile(r"(MEMORANDUM|OPPOSITION|REPLY|COMPLAINT|ANSWER|DEMURRER|NOTICE OF MOTION)[^\n]*", re.IGNORECASE)

TOP_TITLES = {
    "introduction","background","argument","conclusion",
    "table of contents","table of authorities"
}
ALLOWED_HEADING_PAGE_CATEGORIES = {"Pleading body","Pleading first page"}

# ---------- Data ----------
@dataclass
class PageOffset:
    page_index: int
    char_start: int
    char_end: int
    filename: str
    category: Optional[str] = None
    sha256: Optional[str] = None

@dataclass
class TocEntry:
    order: int
    level: int
    title: str
    label: str
    norm: str

@dataclass
class HeadingCandidate:
    char_start: int
    line_text: str
    norm_text: str
    page_index: int
    label: str

# ---------- Utils ----------
def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u2013","-").replace("\u2014","-")
    s = re.sub(r"\s+", " ", s.strip()).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def strip_dot_leader_tail(s: str) -> str:
    return DOT_LEADER_TAIL_STRIP_RE.sub("", s).rstrip()

def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1<<16), b""):
            h.update(chunk)
    return h.hexdigest()

def read_text_pages(text_dir: Path) -> List[Tuple[int, str, str, str]]:
    pages = []
    for p in sorted(text_dir.iterdir()):
        m = PAGE_TXT_RE.match(p.name)
        if not m:
            continue
        idx = int(m.group(1))
        sha = file_sha256(p)
        pages.append((idx, p.name, p.read_text(encoding="utf-8", errors="replace"), sha))
    pages.sort(key=lambda x: x[0])
    return pages

def concat_pages_with_offsets(pages: List[Tuple[int, str, str, str]]) -> Tuple[str, List[PageOffset]]:
    combined_parts = []
    offsets: List[PageOffset] = []
    cursor = 0
    for idx, fname, text, sha in pages:
        start = cursor
        combined_parts.append(text)
        cursor += len(text)
        if not text.endswith("\n"):
            combined_parts.append("\n"); cursor += 1
        end = cursor
        offsets.append(PageOffset(page_index=idx, char_start=start, char_end=end, filename=fname, sha256=sha))
    return "".join(combined_parts), offsets

def load_classification_categories(csv_path: Path) -> Dict[int, str]:
    if not csv_path.exists():
        return {}
    out: Dict[int, str] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fn = row.get("filename","")
            m = PNG_FILENAME_RE.match(fn)
            if not m:
                continue
            out[int(m.group(1))] = row.get("category","") or ""
    return out

def charpos_to_page(char_pos: int, offsets: List[PageOffset]) -> int:
    if not offsets:
        return 0
    starts = [o.char_start for o in offsets]
    i = bisect_right(starts, char_pos) - 1
    if i < 0: i = 0
    if i >= len(offsets): i = len(offsets)-1
    return offsets[i].page_index

def is_candidate_heading(line: str) -> bool:
    s = line.strip()
    if len(s) < 4 or len(s) > 200:
        return False
    if s.endswith(":"):
        return False
    if HEAD_PREFIX_RE.match(s):
        return True
    n_upper = sum(1 for c in s if c.isalpha() and c.isupper())
    n_alpha = sum(1 for c in s if c.isalpha())
    if n_alpha > 0 and n_upper / n_alpha >= 0.6:
        return True
    ns = normalize_text(s)
    if any(k in ns for k in ("introduction","background","argument","conclusion","standard","facts","procedural history")):
        return True
    return False

def extract_label_from_line(line: str) -> str:
    m = HEAD_PREFIX_RE.match(line.strip())
    return (m.group(1).strip().rstrip(".") + ".") if m else ""

def enumerate_heading_candidates(combined: str, offsets: List[PageOffset], allowed_pages: set[int]) -> List[HeadingCandidate]:
    cands: List[HeadingCandidate] = []
    pos = 0
    for line in combined.splitlines(keepends=True):
        stripped = line[:-1] if line.endswith("\n") else line
        pg = charpos_to_page(pos, offsets)
        if pg in allowed_pages and is_candidate_heading(stripped):
            cands.append(
                HeadingCandidate(
                    char_start=pos,
                    line_text=stripped,
                    norm_text=normalize_text(HEAD_PREFIX_RE.sub("", stripped)),
                    page_index=pg,
                    label=extract_label_from_line(stripped),
                )
            )
        pos += len(line)
    cands.sort(key=lambda c: (c.page_index, c.char_start))
    return cands

# ---------- TOC parsing ----------
def read_toc_lines(metadata_dir: Path) -> List[str]:
    files = sorted(metadata_dir.glob("page_*_TOC.txt"))
    if not files:
        return []
    raw: List[str] = []
    for f in files:
        raw += [ln.rstrip("\n") for ln in f.read_text(encoding="utf-8", errors="replace").splitlines()]
    # markup mode
    if any(re.match(r"^\s*#+\s+\S", ln) for ln in raw):
        return [ln.strip() for ln in raw if re.match(r"^\s*#+\s+\S", ln)]
    # OCR mode
    out: List[str] = []; buf: List[str] = []
    def flush():
        if buf:
            out.append(" ".join(x.strip() for x in buf if x.strip())); buf.clear()
    for ln in raw:
        if not ln.strip():
            flush(); continue
        buf.append(ln)
        if re.search(r"\d+\s*$", ln):
            flush()
    flush()
    return out

def level_and_label(raw: str) -> Tuple[int, str, str]:
    s = strip_dot_leader_tail(raw)
    mhash = re.match(r"^\s*(#+)\s+(.*)$", s)
    hash_level = None
    if mhash:
        hash_level = len(mhash.group(1))
        s = mhash.group(2).strip()
    m = HEAD_PREFIX_RE.match(s)
    if m:
        label = m.group(1).strip().rstrip(".") + "."
        body  = s[m.end():].strip()
    else:
        label, body = "", s
    if hash_level is not None:
        lvl = hash_level
    elif normalize_text(s) in TOP_TITLES:
        lvl = 1; label=""; body=s.strip()
    elif label and re.match(r"^[IVXLCDM]+\.$", label):
        lvl = 2
    elif label and re.match(r"^[A-Z]\.$", label):
        lvl = 3
    elif label and re.match(r"^\d", label):
        lvl = 4
    else:
        lvl = 1 if body.isupper() and len(body.split())<=3 else 3
    return lvl, label, body

def parse_toc(metadata_dir: Path) -> List[TocEntry]:
    lines = read_toc_lines(metadata_dir)
    entries: List[TocEntry] = []
    order = 0
    for ln in lines:
        lvl, label, body = level_and_label(ln)
        order += 1
        entries.append(
            TocEntry(
                order=order, level=lvl, title=body, label=label,
                norm=normalize_text(re.sub(r"^#+\s*", "", body)),
            )
        )
    return entries

# ---------- Alignment ----------
def best_match(
    toc_norm: str, toc_label: str, candidates: List[HeadingCandidate], min_pos: int,
    combined_norm: str, ratio_threshold: float, score_threshold: float = 0.80
) -> Tuple[Optional[int], float, Optional[HeadingCandidate]]:
    best = None; best_ratio = -1.0; best_score = -1.0
    for c in candidates:
        if c.char_start < min_pos:
            continue
        ratio = difflib.SequenceMatcher(None, toc_norm, c.norm_text).ratio()
        label_bonus = 1.0 if toc_label and c.label == toc_label else 0.0
        score = 0.72*ratio + 0.28*label_bonus
        if score > best_score:
            best_score, best_ratio, best = score, ratio, c
    if best and (best_score >= score_threshold or best_ratio >= ratio_threshold):
        return best.char_start, max(best_score, best_ratio), best
    if toc_label:
        for c in candidates:
            if c.char_start < min_pos:
                continue
            if c.label == toc_label:
                ratio = difflib.SequenceMatcher(None, toc_norm, c.norm_text).ratio()
                if ratio >= 0.60:
                    return c.char_start, ratio, c
    toks = toc_norm.split()
    if toks:
        probe = " ".join(toks[:min(6, len(toks))])
        for c in candidates:
            if c.char_start >= min_pos and probe in c.norm_text:
                return c.char_start, 0.66, c
    return None, 0.0, None

def align(entries: List[TocEntry], combined: str, offsets: List[PageOffset], page_categories: Dict[int, str], ratio_threshold: float) -> List[Dict]:
    allowed = {i for i,c in page_categories.items() if c in ALLOWED_HEADING_PAGE_CATEGORIES} if page_categories else {o.page_index for o in offsets}
    if not allowed:
        allowed = {o.page_index for o in offsets}
    candidates = enumerate_heading_candidates(combined, offsets, allowed)
    comb_norm = normalize_text(combined)

    prev = 0
    out: List[Dict] = []
    for e in entries:
        pos, conf, chosen = best_match(e.norm, e.label, candidates, prev, comb_norm, ratio_threshold)
        rec = {
            "order": e.order, "level": e.level, "title": e.title, "label": e.label,
            "start_char": int(pos) if pos is not None else None,
            "start_page": charpos_to_page(pos, offsets) if pos is not None else None,
            "confidence": round(conf, 3),
            "matched_line": chosen.line_text if chosen else None,
            "matched_page": chosen.page_index if chosen else None,
        }
        out.append(rec)
        if pos is not None:
            prev = pos

    eof = len(combined)
    for i, r in enumerate(out):
        if r["start_char"] is None:
            r["end_char"]=None; r["end_page"]=None; continue
        nxt = min([x["start_char"] for x in out[i+1:] if x["start_char"] is not None], default=eof)
        r["end_char"]=nxt
        r["end_page"]=charpos_to_page(nxt-1 if nxt>0 else 0, offsets)
    return out

def build_paths(entries: List[TocEntry]) -> Dict[int, Dict]:
    def parent_key(stack):
        return tuple((lvl, lab, tit) for lvl, lab, tit in stack[:-1])
    siblings: Dict[Tuple, int] = {}
    tmp_stack: List[Tuple[int, str, str]] = []
    for e in entries:
        while tmp_stack and tmp_stack[-1][0] >= e.level:
            tmp_stack.pop()
        tmp_stack.append((e.level, e.label, e.title))
        key = parent_key(tmp_stack)
        siblings[key] = siblings.get(key, 0) + 1

    tmp_stack = []
    counters: Dict[Tuple, int] = {}
    by_order: Dict[int, Dict] = {}
    for e in entries:
        while tmp_stack and tmp_stack[-1][0] >= e.level:
            tmp_stack.pop()
        tmp_stack.append((e.level, e.label, e.title))
        short_parts = []; long_parts = []
        for L, lab, tit in tmp_stack:
            if L == 1:
                short_parts.append(tit.upper()); long_parts.append(tit.upper())
            elif lab:
                short_parts.append(lab); long_parts.append((lab + " " + tit).strip())
            else:
                short_parts.append(tit); long_parts.append(tit)

        def pkey(stack):
            return tuple((L, lb, tt) for L, lb, tt in stack[:-1])

        key_parent = pkey(tmp_stack)
        total_sibs = siblings.get(key_parent, 1)
        counters[key_parent] = counters.get(key_parent, 0) + 1
        idx = counters[key_parent]

        by_order[e.order] = {
            "path_short": " / ".join(short_parts),
            "path_long":  " / ".join(long_parts),
            "idx": idx,
            "total": total_sibs,
        }
    return by_order

def annotate_page_text(page_text: str, injections: List[Tuple[int, str]]) -> str:
    if not injections:
        return page_text
    lines = page_text.splitlines(keepends=True)
    starts=[]; pos=0
    for ln in lines:
        starts.append(pos); pos+=len(ln)
    def line_index_at(rel:int)->int:
        lo,hi=0,len(starts)-1
        if rel<=0: return 0
        while lo<=hi:
            mid=(lo+hi)//2
            if starts[mid]<=rel: lo=mid+1
            else: hi=mid-1
        return max(0, lo-1)
    for rel,suffix in sorted(injections, key=lambda x:x[0], reverse=True):
        li=line_index_at(rel)
        ln=lines[li]
        if ln.endswith("\r\n"): core,nl=ln[:-2],"\r\n"
        elif ln.endswith("\n"): core,nl=ln[:-1],"\n"
        else: core,nl=ln,""
        if suffix and suffix not in core:
            lines[li]=core+" "+suffix+nl
    return "".join(lines)

# ---------- Caption metadata ----------
MONTHS = "(January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_RE = re.compile(rf"{MONTHS}\s+\d{{1,2}},\s+\d{{4}}", re.IGNORECASE)
ATTY_FOR_RE = re.compile(r"Attorneys?\s+for\s+(.+)", re.IGNORECASE)
TITLE_RE = re.compile(r"(MEMORANDUM|OPPOSITION|REPLY|COMPLAINT|ANSWER|DEMURRER|NOTICE OF MOTION)[^\n]*", re.IGNORECASE)

def extract_caption_fields(caption_text: str) -> Dict[str,str]:
    title = ""
    m = TITLE_RE.search(caption_text)
    if m: title = m.group(0).strip()
    party = ""
    m = ATTY_FOR_RE.search(caption_text)
    if m: party = m.group(1).strip().rstrip(".")
    date = ""
    ms = list(DATE_RE.finditer(caption_text))
    if ms: date = ms[-1].group(0).strip()
    return {"document_title": title, "filing_party": party, "filing_date": date}

# ---------- Chunking ----------
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\(\)\"'])")

def approx_token_count(text: str, chars_per_token: float) -> int:
    return max(1, math.ceil(len(text) / max(1e-6, chars_per_token)))

def split_into_sentences(text: str) -> List[str]:
    # Preserve formatting by not collapsing whitespace
    text = text.strip()
    if not text: return []
    # Split on sentence boundaries but preserve paragraph structure
    sentences = SENT_SPLIT_RE.split(text)
    return sentences

def is_heading_fragment(text: str) -> bool:
    """Detect if text appears to be a heading that should stay with following content."""
    text = text.strip()
    if not text:
        return False
    
    # Check for common heading patterns
    heading_patterns = [
        r'^[IVXLCDM]+\.?\s*$',           # Roman numerals: I., II., III.
        r'^\d+\.?\s*$',                  # Numbers: 1., 2., 3.
        r'^[A-Z]\.?\s*$',                # Letters: A., B., C.
        r'^\([IVXLCDM]+\)\s*$',          # Parenthetical roman: (I), (II)
        r'^\(\d+\)\s*$',                 # Parenthetical numbers: (1), (2)
        r'^\([A-Z]\)\s*$',               # Parenthetical letters: (A), (B)
        r'^[A-Z\s]{2,20}$',              # Short ALL CAPS text (likely section headers)
    ]
    
    for pattern in heading_patterns:
        if re.match(pattern, text):
            return True
    
    # Check if it's a short line that's all caps or title case
    if len(text) < 100 and (text.isupper() or text.istitle()):
        return True
    
    return False

def find_page_breaks_in_text(text: str, offsets: List[PageOffset]) -> List[Tuple[int, int]]:
    """Find positions where PDF page breaks occur within text.
    Returns list of (char_pos_in_text, page_number) tuples."""
    page_breaks = []
    for i, offset in enumerate(offsets[1:], 1):  # Skip first page
        page_breaks.append((offset.char_start, offset.page_index))
    return page_breaks

def chunk_section_text(text: str, max_tokens: int, min_tokens: int, chars_per_token: float, 
                      section_start_char: int, offsets: List[PageOffset]) -> List[Tuple[int,int,str,List[Tuple[int,int]]]]:
    """Returns list of (start_char_in_section, end_char_in_section, chunk_text, page_breaks_in_chunk).
    page_breaks_in_chunk is a list of (relative_char_in_chunk, page_number) tuples."""
    
    # Find page breaks within this section
    section_page_breaks = []
    for offset in offsets:
        absolute_page_start = offset.char_start
        if section_start_char <= absolute_page_start < section_start_char + len(text):
            relative_pos = absolute_page_start - section_start_char
            section_page_breaks.append((relative_pos, offset.page_index))
    
    sents = split_into_sentences(text)
    chunks=[]; cur=[]; cur_len=0; cur_start=0; pos=0
    
    def flush(force=False):
        nonlocal chunks, cur, cur_len, cur_start
        if not cur: return
        if force or cur_len >= min_tokens or not chunks:
            # Preserve original formatting by joining content as-is
            seg = "".join(cur).strip()
            end = cur_start + len("".join(cur))
            start = cur_start
            
            # Find page breaks within this chunk
            chunk_page_breaks = []
            for page_pos, page_num in section_page_breaks:
                if start <= page_pos < end:
                    chunk_relative_pos = page_pos - start
                    chunk_page_breaks.append((chunk_relative_pos, page_num))
            
            chunks.append((start, end, seg, chunk_page_breaks))
            cur=[]; cur_len=0
    
    # Process text while preserving original formatting
    # Instead of sentence-by-sentence, work with the original text and find good break points
    pos = 0
    while pos < len(text):
        if not cur:
            cur_start = pos
        
        # Find a good breaking point within token limits
        remaining_text = text[pos:]
        if not remaining_text.strip():
            break
            
        # Start with the sentence splitting approach but preserve formatting
        remaining_sents = split_into_sentences(remaining_text)
        if not remaining_sents:
            break
            
        # Add sentences until we hit the token limit
        chunk_end = pos
        temp_content = []
        temp_tokens = 0
        
        for i, sent in enumerate(remaining_sents):
            sent_tokens = approx_token_count(sent, chars_per_token)
            
            # Check if this is a heading fragment that should stay with next content
            is_heading = is_heading_fragment(sent)
            next_sent_exists = i + 1 < len(remaining_sents)
            
            # If current sentence would exceed token limit
            would_exceed = temp_tokens + sent_tokens > max_tokens and temp_content
            
            if not would_exceed or not temp_content:
                # Always add if we have room or this is the first sentence
                sent_start = text.find(sent, chunk_end)
                if sent_start >= chunk_end:
                    # Include any spacing/formatting before the sentence
                    temp_content.append(text[chunk_end:sent_start + len(sent)])
                    chunk_end = sent_start + len(sent)
                    temp_tokens += sent_tokens
                else:
                    # Fallback if we can't find the sentence
                    temp_content.append(sent)
                    chunk_end += len(sent)
                    temp_tokens += sent_tokens
            elif is_heading and next_sent_exists:
                # This is a heading and we have a next sentence - force include both
                # to prevent splitting heading from its content
                sent_start = text.find(sent, chunk_end)
                if sent_start >= chunk_end:
                    temp_content.append(text[chunk_end:sent_start + len(sent)])
                    chunk_end = sent_start + len(sent)
                    temp_tokens += sent_tokens
                else:
                    temp_content.append(sent)
                    chunk_end += len(sent)
                    temp_tokens += sent_tokens
                
                # Also add the next sentence to keep heading with content
                if i + 1 < len(remaining_sents):
                    next_sent = remaining_sents[i + 1]
                    next_sent_tokens = approx_token_count(next_sent, chars_per_token)
                    next_sent_start = text.find(next_sent, chunk_end)
                    if next_sent_start >= chunk_end:
                        temp_content.append(text[chunk_end:next_sent_start + len(next_sent)])
                        chunk_end = next_sent_start + len(next_sent)
                        temp_tokens += next_sent_tokens
                    else:
                        temp_content.append(next_sent)
                        chunk_end += len(next_sent)
                        temp_tokens += next_sent_tokens
                    # Skip the next sentence in the loop since we just processed it
                    remaining_sents = remaining_sents[:i+1] + remaining_sents[i+2:]
                break
            else:
                break
        
        if temp_content:
            # Create the chunk with preserved formatting
            chunk_text = "".join(temp_content)
            end_pos = min(pos + len(chunk_text), len(text))
            
            # Find page breaks within this chunk
            chunk_page_breaks = []
            for page_pos, page_num in section_page_breaks:
                if pos <= page_pos < end_pos:
                    chunk_relative_pos = page_pos - pos
                    chunk_page_breaks.append((chunk_relative_pos, page_num))
            
            cur.append(chunk_text)
            cur_len = temp_tokens
            pos = end_pos
            
            if cur_len >= min_tokens or pos >= len(text):
                flush(force=True)
        else:
            # No content found, move forward to avoid infinite loop
            pos += 1
    
    flush(force=True)
    
    # Filter out very small chunks (but keep if it's the only chunk)
    if len(chunks) > 1:
        chunks = [(a,b,t,pb) for (a,b,t,pb) in chunks if approx_token_count(t, chars_per_token) >= max(5, min_tokens//3)]
    
    # Fix overlaps
    fixed=[]; prev_end=0
    for a,b,t,pb in chunks:
        if a < prev_end: a = prev_end
        if b <= a: b = a + len(t)
        fixed.append((a,b,t,pb)); prev_end=b
    
    return fixed

def _slug(s: str, maxlen: int = 80) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\w\s.-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return (s[:maxlen]).rstrip("_") or "section"

# ---------- Main per-doc ----------
def process_doc(
    doc_in: Path, doc_out: Path, ratio_threshold: float, path_mode: str, with_counts: bool,
    write_candidates: bool, dry_run: bool, log: logging.Logger,
    max_tokens:int, min_tokens:int, chars_per_token:float, write_chunk_files:bool
) -> Dict:
    t0 = time.time()
    
    # Initialize ID management systems
    id_manager = DocumentIDManager(doc_in.parent.parent)  # Base directory
    chunk_generator = ChunkIDGenerator()
    metadata_extractor = MetadataExtractor()
    
    # Get document ID
    document_folder_name = doc_in.name
    document_id = id_manager.get_document_id(document_folder_name)
    
    meta_in = doc_in / "metadata"
    text_in = doc_in / "text_pages"
    if not meta_in.is_dir() or not text_in.is_dir():
        log.warning("[skip] %s missing metadata/ or text_pages/", doc_in); return {"status":"skip"}
    toc_entries = parse_toc(meta_in)
    if not toc_entries:
        log.warning("[skip] %s no TOC", doc_in); return {"status":"skip"}
    pages = read_text_pages(text_in)
    if not pages:
        log.warning("[warn] %s has no page_*.txt", doc_in); return {"status":"warn"}

    combined, offsets = concat_pages_with_offsets(pages)
    csv_paths = list(meta_in.glob("*_classification.csv"))
    page_categories: Dict[int, str] = load_classification_categories(csv_paths[0]) if csv_paths else {}
    for off in offsets:
        if off.page_index in page_categories:
            off.category = page_categories[off.page_index]

    aligned = align(toc_entries, combined, offsets, page_categories, ratio_threshold)
    paths = build_paths(toc_entries)

    meta_out = doc_out / "metadata"
    text_out = doc_out / "text_pages_annotated"
    chunks_out = doc_out / "chunks"
    if not dry_run:
        meta_out.mkdir(parents=True, exist_ok=True)
        text_out.mkdir(parents=True, exist_ok=True)
        if write_chunk_files: chunks_out.mkdir(parents=True, exist_ok=True)

    # Build injections and write annotated pages with [PDF_page_X]
    per_page_rel: Dict[int, List[Dict]] = {}
    for rec in aligned:
        if rec["start_char"] is None:
            continue
        pg = rec["start_page"]
        base = next(o.char_start for o in offsets if o.page_index==pg)
        rel = rec["start_char"] - base
        per_page_rel.setdefault(pg, []).append({"rel_char": rel, "order": rec["order"]})
    for pg in per_page_rel:
        per_page_rel[pg].sort(key=lambda x: x["rel_char"])

    def suffix_for(order: int) -> str:
        p = paths.get(order, {})
        seg = p.get("path_long" if path_mode=="long" else "path_short","")
        return "{"+seg+"}" if seg else ""

    inj_by_page: Dict[int, List[Tuple[int, str]]] = {
        pg: [(it["rel_char"], suffix_for(it["order"])) for it in items]
        for pg, items in per_page_rel.items()
    }

    if not dry_run:
        for idx, fname, text, _sha in pages:
            header = f" [PDF_page_{idx}] \n"
            annotated = annotate_page_text(text, inj_by_page.get(idx, []))
            (text_out/fname).write_text(header + annotated, encoding="utf-8")

        # Skip creating combined_annotated.txt and page_offsets_annotated.json (unnecessary for RAG)

    # Skip creating sections.jsonl (unnecessary for RAG - section paths are in chunk metadata)
    doc_id = doc_in.name

    # ---- Chunking on leaf sections ----
    leaves = []
    for s in aligned:
        a,b = s["start_char"], s.get("end_char")
        if a is None or b is None:
            continue
        has_child = any((t["start_char"] is not None and a < t["start_char"] < b) for t in aligned if t is not s)
        if not has_child:
            leaves.append(s)
    leaves.sort(key=lambda r: r["start_char"])

    # Extract document-level metadata using new system
    caption_path = next(iter(sorted(meta_in.glob("page_*_caption.txt"))), None)
    doc_metadata = metadata_extractor.extract_caption_metadata(caption_path)
    
    # Get classification CSV for page-level metadata
    classification_csv = csv_paths[0] if csv_paths else None
    
    # Legacy compatibility - maintain old caption extraction for backward compatibility
    caption_text = caption_path.read_text(encoding="utf-8", errors="replace") if caption_path else ""
    cap = extract_caption_fields(caption_text)

    def find_safe_insertion_point(text: str, target_pos: int, search_radius: int = 50) -> int:
        """Find a safe position near target_pos to insert page marker without breaking words."""
        if target_pos <= 0:
            return 0
        if target_pos >= len(text):
            return len(text)
        
        # Check if we're already at a good position (whitespace or start)
        if target_pos == 0 or text[target_pos - 1].isspace() or text[target_pos].isspace():
            return target_pos
        
        # Search backwards for whitespace or newline within radius
        for i in range(min(search_radius, target_pos)):
            check_pos = target_pos - i
            if check_pos > 0 and (text[check_pos - 1].isspace() or text[check_pos - 1] == '\n'):
                return check_pos
        
        # Search forwards for whitespace or newline within radius  
        for i in range(1, min(search_radius, len(text) - target_pos)):
            check_pos = target_pos + i
            if check_pos < len(text) and (text[check_pos].isspace() or text[check_pos] == '\n'):
                return check_pos
        
        # Fallback: look for any word boundary character
        for i in range(min(search_radius, target_pos)):
            check_pos = target_pos - i
            if check_pos > 0 and text[check_pos - 1] in ' \t\n\r.,;:!?-()[]{}"\'':
                return check_pos
                
        # Last resort: return original position (shouldn't happen often)
        return target_pos

    def create_chunk_text_with_pagination(chunk_text: str, page_breaks_in_chunk: List[Tuple[int,int]], 
                                         chunk_start_page: int) -> str:
        """Create chunk text with proper PDF page markers, avoiding duplicates."""
        import re
        page_marker_pattern = r'\[PDF_page_(\d+)(?:_cont\.)?\]'

        # If text already has page markers, just clean it up a bit
        if re.search(page_marker_pattern, chunk_text):
            return re.sub(r'\n{3,}', '\n\n', chunk_text).strip()

        # Build the full text with page break markers inserted at safe points
        parts = []
        last_pos = 0
        sorted_breaks = sorted(page_breaks_in_chunk, key=lambda x: x[0])
        for pos, page_num in sorted_breaks:
            safe_pos = find_safe_insertion_point(chunk_text, pos)
            parts.append(chunk_text[last_pos:safe_pos])
            parts.append(f"\n[PDF_page_{page_num}]\n")
            last_pos = safe_pos
        parts.append(chunk_text[last_pos:])
        
        paginated_text = "".join(parts)
        lines = paginated_text.split('\n')
        
        # Add the initial continuation marker intelligently
        first_content_line_idx = -1
        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if stripped_line and not re.match(page_marker_pattern, stripped_line):
                first_content_line_idx = i
                break
        
        # Only add a continuation marker if no other marker precedes the first line of text
        if first_content_line_idx != -1:
            already_marked = any(re.search(page_marker_pattern, l.strip()) for l in lines[:first_content_line_idx])
            if not already_marked:
                lines.insert(first_content_line_idx, f"[PDF_page_{chunk_start_page}_cont.]")
        elif not any(re.search(page_marker_pattern, l) for l in lines):
             lines.insert(0, f"[PDF_page_{chunk_start_page}_cont.]")

        final_text = "\n".join(lines)
        return re.sub(r'\n{3,}', '\n\n', final_text).strip()

    # --- MERGE-FIRST FIX ---
    # 1. Generate initial raw chunks without pagination
    raw_chunks_data = []
    if not dry_run:
        for sec in leaves:
            sa, sb = sec["start_char"], sec["end_char"]
            sec_text = combined[sa:sb]
            pieces = chunk_section_text(sec_text, max_tokens=max_tokens, min_tokens=min_tokens, 
                                      chars_per_token=chars_per_token, section_start_char=sa, offsets=offsets)
            
            for i,(ra, rb, txt, page_breaks) in enumerate(pieces, start=1):
                global_start = sa + ra
                chunk_start_page = charpos_to_page(global_start, offsets)
                chunk_end_page = charpos_to_page(sa + rb, offsets)
                
                page_numbers = sorted(set([chunk_start_page, chunk_end_page] + [p[1] for p in page_breaks]))

                raw_chunks_data.append({
                    "raw_text": txt,
                    "page_breaks": page_breaks,
                    "chunk_start_page": chunk_start_page,
                    "page_numbers": page_numbers,
                    "token_count": approx_token_count(txt, chars_per_token),
                    "section_order": sec.get("order", 0)
                })

    # 2. Merge tiny raw chunks
    merged_raw_chunks = []
    i = 0
    while i < len(raw_chunks_data):
        current_chunk = raw_chunks_data[i]
        
        if (current_chunk.get("token_count", 0) < 20 and i + 1 < len(raw_chunks_data)):
            next_chunk = raw_chunks_data[i + 1]
            
            merged_text = current_chunk["raw_text"] + "\n\n" + next_chunk["raw_text"]
            merged_pages = sorted(set(current_chunk["page_numbers"] + next_chunk["page_numbers"]))
            offset_for_next_breaks = len(current_chunk["raw_text"]) + 2
            merged_breaks = current_chunk["page_breaks"] + [(pos + offset_for_next_breaks, pg) for pos, pg in next_chunk["page_breaks"]]

            next_chunk.update({
                "raw_text": merged_text,
                "page_numbers": merged_pages,
                "page_breaks": sorted(merged_breaks),
                "token_count": current_chunk["token_count"] + next_chunk["token_count"],
                "chunk_start_page": current_chunk["chunk_start_page"]
            })
            i += 1
            continue
        
        merged_raw_chunks.append(current_chunk)
        i += 1

    # 3. Apply pagination and create final chunks
    chunks_data = []
    chunks_written = 0
    chunk_generator.reset()

    for raw_chunk in merged_raw_chunks:
        chunk_id = chunk_generator.next_id()
        doc_id_str, chunk_id_str = id_manager.format_ids(document_id, chunk_id)

        paginated_text = create_chunk_text_with_pagination(
            raw_chunk["raw_text"], raw_chunk["page_breaks"], raw_chunk["chunk_start_page"]
        )
        
        first_page_filename = f"page_{raw_chunk['page_numbers'][0]:04d}.png"
        page_metadata = metadata_extractor.extract_classification_metadata(
            classification_csv, first_page_filename
        ) if classification_csv else {}
        
        section_path = paths.get(raw_chunk['section_order'], {}).get('path_long', 'Unknown Section')

        chunks_data.append({
            "document_title": doc_metadata["document_title"],
            "filing_party": doc_metadata["filing_party"],
            "filing_date": doc_metadata["filing_date"], 
            "section_path": section_path,
            "chunk_ID": int(chunk_id_str),
            "document_ID": int(doc_id_str),
            "page_numbers": raw_chunk["page_numbers"],
            "exhibit_label": page_metadata.get("exhibit_label"),
            "exhibit_title": page_metadata.get("exhibit_title"),
            "page_type": page_metadata.get("page_type", "pleading_body"),
            "text": paginated_text.strip()
        })
        chunks_written += 1

    # 4. Final writing with pagination formatting fix
    if not dry_run:
        chunks_output_file = meta_out / "chunks.json"
        with chunks_output_file.open("w", encoding="utf-8") as f:
            json.dump(chunks_data, f, ensure_ascii=False, indent=2)

        if write_chunk_files:
            for chunk in chunks_data:
                filename = f"{chunk['document_ID']:04d}_{chunk['chunk_ID']:03d}.txt"
                
                # PAGINATION FORMATTING FIX
                page_numbers_str = json.dumps(chunk['page_numbers'])
                
                # Use a copy of the chunk to avoid modifying the list we are iterating over
                json_chunk_to_write = chunk.copy()
                json_chunk_to_write['page_numbers'] = "__PAGE_NUMBERS_PLACEHOLDER__"

                json_str = json.dumps(json_chunk_to_write, ensure_ascii=False, indent=2)
                json_str = json_str.replace('"__PAGE_NUMBERS_PLACEHOLDER__"', page_numbers_str)
                json_str = json_str.replace('\\n', '\n')
                
                (chunks_out / filename).write_text(json_str, encoding="utf-8")

    matched = sum(1 for r in aligned if r["start_char"] is not None)
    if not dry_run:
        # Skip creating annotation_report.md (unnecessary for RAG - just logging output)
        logging.info("TOC entries: %d, Matched headings: %d, Leaf sections: %d, Chunks: %d", 
                    len(toc_entries), matched, len(leaves), chunks_written)

    logging.info("[ok] %s -> %s: annotated, aligned, chunked (%d chunks).", doc_in.name, doc_out, chunks_written)
    return {"status":"ok","matched":matched,"leaves":len(leaves),"chunks":chunks_written}


# ---------- Discovery ----------
def find_docs_with_toc(root: Path) -> List[Path]:
    out=[]
    for d in root.iterdir():
        if not d.is_dir():
            continue
        if (d/"metadata").is_dir() and list((d/"metadata").glob("page_*_TOC.txt")):
            out.append(d)
    return sorted(out)

# ---------- CLI ----------
def main():
    ap = argparse.ArgumentParser(description="Align TOC->body; annotate; chunk leaf sections; caption metadata; per-chunk files.")
    ap.add_argument("--in-root", type=Path, required=True)
    ap.add_argument("--out-root", type=Path)
    ap.add_argument("--doc", type=str, help="Optional subfolder under --in-root")
    ap.add_argument("--threshold", type=float, default=0.80)
    ap.add_argument("--path-mode", choices=["short","long"], default="short")
    ap.add_argument("--with-counts", action="store_true")
    ap.add_argument("--write-candidates", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log-level", default="INFO", choices=["DEBUG","INFO","WARNING","ERROR"])
    # chunking knobs
    ap.add_argument("--max-tokens", type=int, default=700, help="Max tokens per chunk")
    ap.add_argument("--min-tokens", type=int, default=150, help="Target minimum tokens per chunk")
    ap.add_argument("--chars-per-token", type=float, default=4.0, help="Approx chars per token")
    ap.add_argument("--write-chunk-files", action="store_true", help="Write per-chunk .txt files under chunks/")
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s %(message)s", stream=sys.stderr)
    log = logging.getLogger("toc_integrator_v7")

    in_root: Path = args.in_root
    out_root: Path = args.out_root or in_root
    if not in_root.is_dir():
        log.error("Input root not found"); sys.exit(2)
    if not out_root.exists():
        out_root.mkdir(parents=True, exist_ok=True)

    if args.doc:
        docs_in = [in_root / args.doc]
    else:
        docs_in = find_docs_with_toc(in_root)
    if not docs_in:
        log.error("No documents with TOC found in input root"); sys.exit(1)

    rc = 0
    for d_in in docs_in:
        d_out = out_root / d_in.name
        res = process_doc(
            d_in, d_out,
            ratio_threshold=args.threshold, path_mode=args.path_mode,
            with_counts=args.with_counts, write_candidates=args.write_candidates,
            dry_run=args.dry_run, log=log,
            max_tokens=args.max_tokens, min_tokens=args.min_tokens,
            chars_per_token=args.chars_per_token, write_chunk_files=args.write_chunk_files
        )
        if res.get("status") != "ok":
            rc = max(rc, 1)
    sys.exit(rc)

if __name__ == "__main__":
    main()