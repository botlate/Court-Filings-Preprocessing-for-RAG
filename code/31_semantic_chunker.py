#!/usr/bin/env python3

import csv
import json
import re
import os
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import tiktoken  # For accurate token counting

from id_system import DocumentIDManager, ChunkIDGenerator  
from metadata_extractor import MetadataExtractor

class LegalDocumentChunker:
    def __init__(self, max_tokens=500, min_tokens=50):
        """
        Initialize the chunker with configurable token limits.
        
        Args:
            max_tokens: Maximum tokens per chunk
            min_tokens: Minimum tokens to consider combining with adjacent pages
        """
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Add ID management
        self.id_manager = None
        self.chunk_generator = ChunkIDGenerator()
        self.metadata_extractor = MetadataExtractor()
        
    def count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken."""
        return len(self.tokenizer.encode(text))
    
    def read_csv_metadata(self, csv_path: str) -> Dict[str, Dict]:
        """
        Read the classification CSV file and return metadata by filename.
        Expected columns: filename, category, subtype, exhibit_label, exhibit_title, notes
        """
        metadata_by_file = {}
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                filename = row.get('filename', '')
                if filename:
                    # Extract page number from filename (e.g., "page_0003.txt" -> 3)
                    page_match = re.search(r'page_(\d+)', filename)
                    page_num = int(page_match.group(1)) if page_match else None
                    
                    # Check if this is an exhibit cover
                    category = row.get('category', '')
                    notes = row.get('notes', '')
                    is_exhibit_cover = (
                        'exhibit' in category.lower() and 
                        ('cover' in category.lower() or 'cover' in notes.lower())
                    )
                    
                    metadata_by_file[filename] = {
                        'page_number': page_num,
                        'category': category,
                        'subtype': row.get('subtype', ''),
                        'exhibit_label': row.get('exhibit_label', ''),
                        'exhibit_title': row.get('exhibit_title', ''),
                        'notes': notes,
                        'is_exhibit_cover': is_exhibit_cover
                    }
        return metadata_by_file
    
    def read_caption_metadata(self, caption_path: str) -> Dict:
        """
        Read the caption JSON file containing document metadata.
        """
        with open(caption_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract JSON from the caption file (it might be wrapped in ```json blocks)
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            json_str = content
            
        try:
            data = json.loads(json_str)
            return {
                'document_title': data.get('document_title', ''),
                'filing_date': data.get('filing_date', ''),
                'filing_party': data.get('filing_party', ''),
                'case_number': data.get('case_number', ''),
                'court': data.get('court', ''),
                'named_plaintiffs': data.get('named_plaintiff(s)', []),
                'named_defendants': data.get('named_defendant(s)', [])
            }
        except json.JSONDecodeError as e:
            print(f"Error parsing caption JSON: {e}")
            return {}
    
    def read_page_texts(self, text_dir: str) -> List[Tuple[int, str, str]]:
        """
        Read all page text files from a directory.
        Returns list of (page_number, filename, text_content) tuples.
        """
        page_texts = []
        text_files = sorted(Path(text_dir).glob('page_*.txt'))
        
        for file_path in text_files:
            filename = file_path.name
            # Skip caption files
            if 'caption' in filename:
                continue
                
            # Extract page number
            page_match = re.search(r'page_(\d+)', filename)
            if page_match:
                page_num = int(page_match.group(1))
                with open(file_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                page_texts.append((page_num, filename, text))
                
        return sorted(page_texts, key=lambda x: x[0])
    
    def should_combine_pages(self, current_text: str, next_text: str, 
                           current_tokens: int, next_tokens: int) -> bool:
        """
        Determine if pages should be combined based on token count and content.
        """
        # Check token thresholds
        if current_tokens >= self.min_tokens and next_tokens >= self.min_tokens:
            return False
            
        # Check if combined would exceed max
        if current_tokens + next_tokens > self.max_tokens:
            return False
            
        # Check for semantic continuity (simple heuristic)
        # Look for incomplete sentences at end of current page
        current_stripped = current_text.strip()
        incomplete_indicators = [
            not current_stripped.endswith(('.', '!', '?', '"')),
            current_stripped.endswith(','),
            current_stripped.endswith(';'),
            re.search(r'\b(and|or|but|however|therefore|thus)$', current_stripped, re.I)
        ]
        
        # Look for continuation at start of next page
        next_stripped = next_text.strip()
        continuation_indicators = [
            next_stripped and next_stripped[0].islower(),
            next_stripped.startswith(('and ', 'or ', 'but ', 'however, ', 'therefore, '))
        ]
        
        return any(incomplete_indicators) or any(continuation_indicators)
    
    def detect_exhibit_marker(self, text: str) -> Optional[str]:
        """
        Detect if text ends with an exhibit marker like 'EXHIBIT A' or 'EXHIBIT 1'.
        Returns the exhibit label if found, None otherwise.
        """
        # Look for exhibit markers at the end of the text
        text_end = text.strip()[-100:] if len(text.strip()) > 100 else text.strip()
        
        # Pattern for exhibit markers
        exhibit_pattern = r'\bEXHIBIT\s+([A-Z0-9]+)\s*$'
        match = re.search(exhibit_pattern, text_end, re.IGNORECASE)
        
        if match:
            return f"Exhibit {match.group(1)}"
        return None
    
    def format_metadata_block(self, pages: List[int], filenames: List[str],
                            csv_metadata: Dict, caption_metadata: Dict) -> str:
        """
        Format the metadata block for a chunk.
        """
        lines = []
        
        # Document-level metadata from caption
        lines.append(f"[DOCUMENT METADATA]")
        lines.append(f"Document Title: {caption_metadata.get('document_title', 'N/A')}")
        lines.append(f"Filing Party: {caption_metadata.get('filing_party', 'N/A')}")
        lines.append(f"Filing Date: {caption_metadata.get('filing_date', 'N/A')}")
        # Case Number commented out per request
        # lines.append(f"Case Number: {caption_metadata.get('case_number', 'N/A')}")
        
        # Page range
        if len(pages) == 1:
            lines.append(f"Page: {pages[0]}")
        else:
            lines.append(f"Pages: {pages[0]}-{pages[-1]}")
        
        # CSV metadata for each page
        lines.append("")  # Blank line
        lines.append("[PAGE CLASSIFICATION]")
        
        # Build page type descriptions
        page_types = []
        categories_shown = set()
        
        for i, filename in enumerate(filenames):
            page_num = pages[i] if i < len(pages) else 'N/A'
            
            if filename in csv_metadata:
                meta = csv_metadata[filename]
                category = meta.get('category', 'Document')
                
                # Determine page type description
                if meta.get('is_exhibit_cover'):
                    # Look for the exhibit it covers
                    if i + 1 < len(filenames):
                        next_page_num = pages[i + 1] if i + 1 < len(pages) else page_num + 1
                        page_types.append(f"Exhibit Cover (Page {page_num}); Exhibit Content (Page {next_page_num})")
                    else:
                        page_types.append(f"Exhibit Cover (Page {page_num})")
                elif meta.get('exhibit_label'):
                    page_types.append(f"{category} - {meta.get('exhibit_label')} (Page {page_num})")
                else:
                    page_types.append(f"{category} (Page {page_num})")
                
                # Track categories for additional details
                if category and category not in categories_shown:
                    categories_shown.add(category)
                    # Add detailed classification info for first occurrence
                    if meta.get('category'):
                        lines.append(f"Category: {meta.get('category')}")
                    if meta.get('subtype') and str(meta.get('subtype')).strip() and str(meta.get('subtype')) != 'nan':
                        lines.append(f"Subtype: {meta.get('subtype')}")
                    if meta.get('exhibit_label'):
                        exhibit_info = f"Exhibit: {meta.get('exhibit_label')}"
                        if meta.get('exhibit_title'):
                            exhibit_info += f" - {meta.get('exhibit_title')}"
                        lines.append(exhibit_info)
                    if meta.get('notes') and str(meta.get('notes')).strip() and str(meta.get('notes')) != 'nan':
                        lines.append(f"Notes: {meta.get('notes')}")
            else:
                page_types.append(f"Document Content (Page {page_num})")
        
        # Add page types right after [PAGE CLASSIFICATION]
        if page_types:
            # Find the index of [PAGE CLASSIFICATION] and insert after it
            classification_index = lines.index("[PAGE CLASSIFICATION]")
            lines.insert(classification_index + 1, f"Page Type: {'; '.join(page_types)}")
        
        return '\n'.join(lines)
    
    def chunk_documents(self, page_texts: List[Tuple[int, str, str]], 
                       csv_metadata: Dict, caption_metadata: Dict) -> List[Dict]:
        """
        Main chunking logic with intelligent page combining.
        """
        chunks = []
        i = 0
        
        while i < len(page_texts):
            page_num, filename, text = page_texts[i]
            current_pages = [page_num]
            current_filenames = [filename]
            current_text = text
            current_tokens = self.count_tokens(text)
            
            # Check if this is an exhibit cover from CSV metadata
            is_exhibit_cover = False
            if filename in csv_metadata:
                is_exhibit_cover = csv_metadata[filename].get('is_exhibit_cover', False)
            
            # Also check if text ends with exhibit marker (like "EXHIBIT D")
            ends_with_exhibit = self.detect_exhibit_marker(text)
            if ends_with_exhibit and not is_exhibit_cover:
                # This page ends with an exhibit marker, treat next page as exhibit start
                print(f"Warning: Page {page_num} ends with '{ends_with_exhibit}' but not marked as exhibit in CSV")
            
            # Look ahead for potential page combining
            while i + 1 < len(page_texts):
                next_page_num, next_filename, next_text = page_texts[i + 1]
                next_tokens = self.count_tokens(next_text)
                
                # Special handling for exhibit covers - combine ONLY with the immediate next page
                should_combine = False
                if is_exhibit_cover and len(current_pages) == 1:
                    # Exhibit cover: combine with next page then stop
                    should_combine = True
                elif ends_with_exhibit and len(current_pages) == 1:
                    # Page ends with exhibit marker: might want to start new chunk
                    # Don't combine if this ends with exhibit marker
                    should_combine = False
                    break  # Start new chunk with the exhibit
                elif not is_exhibit_cover:  # Only check for other combining if NOT exhibit cover
                    if current_tokens < self.min_tokens or next_tokens < self.min_tokens:
                        should_combine = self.should_combine_pages(
                            current_text, next_text, current_tokens, next_tokens
                        )
                
                if should_combine and (current_tokens + next_tokens <= self.max_tokens):
                    # Add page boundary marker
                    boundary_marker = f"\n{{PDF_page_{page_num}_end}} {{PDF_page_{next_page_num}_begin}}\n"
                    current_text += boundary_marker + next_text
                    current_pages.append(next_page_num)
                    current_filenames.append(next_filename)
                    current_tokens += next_tokens
                    i += 1
                    page_num = next_page_num
                    
                    # If this was an exhibit cover, stop combining after adding one page
                    if is_exhibit_cover:
                        break
                else:
                    break
            
            # Create chunk with metadata
            metadata_block = self.format_metadata_block(
                current_pages, current_filenames, csv_metadata, caption_metadata
            )
            
            chunks.append({
                'pages': current_pages,
                'filenames': current_filenames,
                'metadata': metadata_block,
                'text': current_text,
                'full_content': f"{metadata_block}\n\n{'='*50}\n\n{current_text}",
                'token_count': self.count_tokens(current_text),
                'has_exhibit_cover': is_exhibit_cover,
                'ends_with_exhibit': ends_with_exhibit
            })
            
            i += 1
        
        return chunks
    
    def process_directory(self, text_dir: str, csv_path: str, caption_path: str, output_dir: str) -> List[Dict]:
        """
        Process documents with standardized ID system and output format.
        """
        text_dir = Path(text_dir)
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)
        
        # Initialize ID management for this document
        base_dir = text_dir.parent  # Assume text_dir is inside document folder
        document_folder_name = base_dir.name
        self.id_manager = DocumentIDManager(base_dir.parent.parent)  # Pipeline base
        document_id = self.id_manager.get_document_id(document_folder_name)
        self.chunk_generator.reset()
        
        # Extract document-level metadata
        caption_file = Path(caption_path) if caption_path else None
        doc_metadata = self.metadata_extractor.extract_caption_metadata(caption_file) if caption_file else self.metadata_extractor.get_default_metadata()
        
        # Read page texts and CSV metadata
        page_texts = self.read_page_texts(str(text_dir))
        csv_metadata = self.read_csv_metadata(csv_path) if csv_path else {}
        
        # Process chunks with new format
        chunks = self.chunk_documents(page_texts, csv_metadata, {})
        standardized_chunks = []
        
        for chunk in chunks:
            chunk_id = self.chunk_generator.next_id()
            doc_id_str, chunk_id_str = self.id_manager.format_ids(document_id, chunk_id)
            
            # Get page-level metadata from first page
            first_page = chunk['pages'][0] if chunk['pages'] else 1
            first_page_filename = f"page_{first_page:04d}.png"
            page_metadata = self.metadata_extractor.extract_classification_metadata(
                Path(csv_path), first_page_filename
            ) if csv_path else {}
            
            # Create standardized chunk
            standardized_chunk = {
                "document_title": doc_metadata["document_title"],
                "filing_party": doc_metadata["filing_party"],
                "filing_date": doc_metadata["filing_date"],
                "section_path": self.generate_section_path(chunk, page_metadata),
                "chunk_ID": int(chunk_id_str),
                "document_ID": int(doc_id_str),
                "page_numbers": chunk['pages'],
                "exhibit_label": page_metadata.get("exhibit_label"),
                "exhibit_title": page_metadata.get("exhibit_title"), 
                "page_type": page_metadata.get("page_type", "pleading_body"),
                "text": chunk['text'],
                
                # Additional semantic chunker specific fields
                "token_count": chunk['token_count'],
                "has_exhibit_cover": chunk.get('has_exhibit_cover', False),
                "ends_with_exhibit": chunk.get('ends_with_exhibit')
            }
            
            standardized_chunks.append(standardized_chunk)
        
        # Save standardized output
        self.save_standardized_output(standardized_chunks, output_dir, document_id)
        return standardized_chunks

    def generate_section_path(self, chunk: Dict, page_metadata: Dict) -> str:
        """Generate section path for non-TOC documents."""
        if page_metadata.get("exhibit_label"):
            return f"EXHIBITS / {page_metadata['exhibit_label']}"
        elif page_metadata.get("page_type") == "Pleading first page":
            return "HEADER / Case Caption"
        elif page_metadata.get("page_type") == "Proof of service":
            return "FOOTER / Proof of Service"
        else:
            # Generate semantic section based on page numbers
            page_range = chunk['pages']
            if len(page_range) == 1:
                return f"CONTENT / Page {page_range[0]}"
            else:
                return f"CONTENT / Pages {page_range[0]}-{page_range[-1]}"

    def save_standardized_output(self, chunks: List[Dict], output_dir: Path, document_id: int):
        """Save chunks in standardized format."""
        # Save as chunks.json
        chunks_file = output_dir / "chunks.json"
        with open(chunks_file, 'w', encoding='utf-8') as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)
        
        # Save individual chunk files
        for chunk in chunks:
            filename = f"{chunk['document_ID']:04d}_{chunk['chunk_ID']:03d}.txt"
            
            meta_lines = [
                f"Document ID: {chunk['document_ID']:04d}",
                f"Chunk ID: {chunk['chunk_ID']:03d}",
                f"Document Title: {chunk['document_title']}",
                f"Filing Party: {chunk['filing_party']}",
                f"Filing Date: {chunk['filing_date']}",
                f"Section Path: {chunk['section_path']}",
                f"Pages: {'-'.join(map(str, chunk['page_numbers']))}",
                f"Page Type: {chunk['page_type']}",
                f"Token Count: {chunk['token_count']}",
                "=" * 50,
                ""
            ]
            
            if chunk.get('exhibit_label'):
                meta_lines.insert(-2, f"Exhibit: {chunk['exhibit_label']}")
            
            full_content = "\n".join(meta_lines) + chunk['text']
            (output_dir / filename).write_text(full_content, encoding="utf-8")
        
        print(f"Saved {len(chunks)} chunks to {output_dir}")
        print(f"Document ID: {document_id:04d}")


def main():
    """Example usage of the chunking system."""
    
 
    # Configure paths
    text_directory = "./text_pages"  # Directory containing page_XXXX.txt files
    csv_file = "./metadata/2019 05 28 FAC First Amended Complaint_classification.csv"
    caption_file = "./metadata/page_0001_caption.txt"
    output_directory = "./chunks"
    
    # Initialize chunker with custom token limits
    chunker = LegalDocumentChunker(max_tokens=800, min_tokens=100)
    
    # Process documents
    chunks = chunker.process_directory(
        text_dir=text_directory,
        csv_path=csv_file,
        caption_path=caption_file,
        output_dir=output_directory
    )
    
    # Print summary
    print(f"\nCreated {len(chunks)} chunks:")
    for i, chunk in enumerate(chunks, 1):
        pages_str = f"{chunk['pages'][0]}" if len(chunk['pages']) == 1 else \
                   f"{chunk['pages'][0]}-{chunk['pages'][-1]}"
        exhibit_note = " [EXHIBIT COVER]" if chunk['has_exhibit_cover'] else ""
        if chunk.get('ends_with_exhibit'):
            exhibit_note += f" [ENDS WITH {chunk['ends_with_exhibit']}]"
        print(f"  Chunk {i}: Pages {pages_str}, {chunk['token_count']} tokens{exhibit_note}")


if __name__ == "__main__":
    main()