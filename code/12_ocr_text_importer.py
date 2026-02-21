"""
External OCR Text Importer

Distributes externally OCR'd text files (e.g. from PaddleOCR GUI) into the
doc_files/ directory structure expected by the RAG pipeline.

Supported naming patterns in the OCR folder:
  {pdf_stem}_{N}.txt        e.g. "MyDocument_1.txt" .. "_20.txt"
  {pdf_stem}_page{N}.txt    e.g. "MyDocument_page1.txt"

Output mapping:
  doc_files/{sanitized_stem}/text_pages/page_XXXX.txt

Usage:
  python 12_ocr_text_importer.py <ocr_folder> <doc_files_folder>
"""
import os
import re
import shutil
import sys
from pathlib import Path


def sanitize_folder_name(name):
    """Match the sanitization used in 10_pdf_extractor.py."""
    name = re.sub(r'\.{3,}', '_', name)
    name = name.rstrip('. ')
    return name


def discover_doc_stems(doc_files_folder):
    """
    Return a dict mapping sanitized folder name -> folder path
    for every document folder in doc_files/.
    """
    stems = {}
    doc_root = Path(doc_files_folder)
    if not doc_root.exists():
        return stems
    for item in doc_root.iterdir():
        if item.is_dir() and item.name not in ('__pycache__',):
            stems[item.name] = item
    return stems


def match_files_to_docs(ocr_folder, doc_stems, log=print):
    """
    Match OCR text files to document folders.

    Strategy: for each .txt file, try to find the longest doc stem that is a
    prefix of the filename (after stripping extension). Then extract the page
    number from the remaining suffix.

    Returns:
      matched: list of (src_path, dest_path, doc_name, page_num)
      unmatched: list of (src_path, reason)
    """
    matched = []
    unmatched = []

    # Sort stems longest-first so we greedily match the longest prefix
    sorted_stems = sorted(doc_stems.keys(), key=len, reverse=True)

    ocr_path = Path(ocr_folder)
    txt_files = sorted(ocr_path.glob("*.txt"))

    if not txt_files:
        log(f"No .txt files found in {ocr_folder}")
        return matched, unmatched

    for txt_file in txt_files:
        fname = txt_file.stem  # filename without .txt

        found = False
        for stem in sorted_stems:
            if not fname.startswith(stem):
                continue

            suffix = fname[len(stem):]

            # Try patterns: _N, _pageN, _page_N
            m = (re.match(r'^_page_?(\d+)$', suffix) or
                 re.match(r'^_(\d+)$', suffix))

            if m:
                page_num = int(m.group(1))
                dest_dir = doc_stems[stem] / "text_pages"
                dest_file = dest_dir / f"page_{page_num:04d}.txt"
                matched.append((txt_file, dest_file, stem, page_num))
                found = True
                break

        if not found:
            unmatched.append((txt_file, "no matching document folder"))

    return matched, unmatched


def import_ocr_texts(ocr_folder, doc_files_folder, log=print, dry_run=False):
    """
    Main entry point. Discovers documents, matches OCR files, copies them.

    Returns (copied_count, error_count, unmatched_count).
    """
    log(f"OCR text import: {ocr_folder} -> {doc_files_folder}")

    doc_stems = discover_doc_stems(doc_files_folder)
    if not doc_stems:
        log(f"ERROR: No document folders found in {doc_files_folder}")
        return 0, 0, 0

    log(f"Found {len(doc_stems)} document folder(s)")

    matched, unmatched = match_files_to_docs(ocr_folder, doc_stems, log)

    log(f"Matched: {len(matched)} files, Unmatched: {len(unmatched)} files")

    # Report unmatched
    for src, reason in unmatched:
        log(f"  SKIP: {src.name} ({reason})")

    # Group by document for summary
    by_doc = {}
    for src, dest, doc_name, page_num in matched:
        by_doc.setdefault(doc_name, []).append((src, dest, page_num))

    copied = 0
    errors = 0

    for doc_name in sorted(by_doc.keys()):
        pages = by_doc[doc_name]
        pages.sort(key=lambda x: x[2])  # sort by page number
        page_nums = [p[2] for p in pages]

        log(f"\n{doc_name}: {len(pages)} pages (range {min(page_nums)}-{max(page_nums)})")

        # Check for gaps
        expected = set(range(min(page_nums), max(page_nums) + 1))
        missing = expected - set(page_nums)
        if missing:
            log(f"  WARNING: missing pages: {sorted(missing)}")

        # Check for page count mismatch with PNG folder
        png_dir = Path(doc_files_folder) / doc_name / "PNG"
        if png_dir.exists():
            png_count = len(list(png_dir.glob("*.png")))
            if png_count != len(pages):
                log(f"  WARNING: {png_count} PNGs but {len(pages)} text files")

        for src, dest, page_num in pages:
            if dry_run:
                log(f"  [DRY RUN] {src.name} -> {dest}")
            else:
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    copied += 1
                except Exception as e:
                    log(f"  ERROR copying {src.name}: {e}")
                    errors += 1

    log(f"\nImport complete: {copied} copied, {errors} errors, {len(unmatched)} unmatched")
    return copied, errors, len(unmatched)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Import external OCR text files into doc_files structure"
    )
    parser.add_argument("ocr_folder", help="Folder containing OCR text files")
    parser.add_argument("doc_files_folder", help="doc_files output folder")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be done without copying")
    args = parser.parse_args()

    if not os.path.isdir(args.ocr_folder):
        print(f"Error: OCR folder not found: {args.ocr_folder}")
        sys.exit(1)
    if not os.path.isdir(args.doc_files_folder):
        print(f"Error: doc_files folder not found: {args.doc_files_folder}")
        sys.exit(1)

    copied, errors, unmatched = import_ocr_texts(
        args.ocr_folder, args.doc_files_folder, dry_run=args.dry_run
    )

    if errors > 0:
        sys.exit(1)
