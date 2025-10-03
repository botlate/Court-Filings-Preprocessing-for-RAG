#!/usr/bin/env python3
"""
Metadata Extraction System

Extracts metadata from various sources:
- Caption files (document-level metadata)
- Classification CSV files (page-level metadata)
- Document folder structures
"""

import json
import csv
import re
from pathlib import Path
from typing import Dict, Optional, Any, List


class MetadataExtractor:
    """Extracts and processes metadata from various sources."""
    
    def __init__(self):
        """Initialize metadata extractor."""
        pass
    
    def extract_caption_metadata(self, caption_file: Optional[Path]) -> Dict[str, Any]:
        """
        Extract document-level metadata from caption file.
        
        Args:
            caption_file: Path to caption file (page_0001_caption.txt)
            
        Returns:
            Dictionary with document metadata
        """
        if not caption_file or not caption_file.exists():
            return self.get_default_metadata()
        
        try:
            content = caption_file.read_text(encoding='utf-8', errors='replace')
            
            # Try to parse as JSON first (if it's wrapped in ```json blocks)
            json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    return self._normalize_caption_data(data)
                except json.JSONDecodeError:
                    pass
            
            # Try to parse as direct JSON
            try:
                data = json.loads(content)
                return self._normalize_caption_data(data)
            except json.JSONDecodeError:
                pass
            
            # Fall back to text parsing
            return self._parse_caption_text(content)
            
        except Exception as e:
            print(f"Error reading caption file {caption_file}: {e}")
            return self.get_default_metadata()
    
    def _normalize_caption_data(self, data: Dict) -> Dict[str, Any]:
        """Normalize caption data from JSON to standard format."""
        return {
            "document_title": data.get("document_title", ""),
            "filing_party": data.get("filing_party", ""),
            "filing_date": data.get("filing_date", ""),
            "case_number": data.get("case_number", ""),
            "court": data.get("court", ""),
            "named_plaintiffs": data.get("named_plaintiff(s)", []),
            "named_defendants": data.get("named_defendant(s)", [])
        }
    
    def _parse_caption_text(self, content: str) -> Dict[str, Any]:
        """Parse caption metadata from plain text using regex patterns."""
        metadata = self.get_default_metadata()
        
        # Common patterns for legal documents
        patterns = {
            "document_title": [
                r"(MEMORANDUM|OPPOSITION|REPLY|COMPLAINT|ANSWER|DEMURRER|NOTICE OF MOTION)[^\n]*",
                r"(FIRST AMENDED COMPLAINT|SECOND AMENDED COMPLAINT)[^\n]*",
                r"(MOTION|BRIEF|DECLARATION)[^\n]*"
            ],
            "filing_date": [
                r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
                r"\d{1,2}/\d{1,2}/\d{4}",
                r"\d{4}-\d{2}-\d{2}"
            ],
            "filing_party": [
                r"Attorneys?\s+for\s+(.+?)(?:\n|$)",
                r"By:\s+(.+?)(?:\n|Attorney|$)"
            ],
            "case_number": [
                r"Case\s+No\.?\s*:?\s*([A-Z0-9-]+)",
                r"Civil\s+Case\s+No\.?\s*:?\s*([A-Z0-9-]+)"
            ]
        }
        
        for field, pattern_list in patterns.items():
            for pattern in pattern_list:
                match = re.search(pattern, content, re.IGNORECASE | re.MULTILINE)
                if match:
                    if field == "filing_party":
                        metadata[field] = match.group(1).strip().rstrip(".")
                    else:
                        metadata[field] = match.group(0).strip() if field != "case_number" else match.group(1).strip()
                    break
        
        return metadata
    
    def get_default_metadata(self) -> Dict[str, Any]:
        """Get default metadata structure."""
        return {
            "document_title": "",
            "filing_party": "", 
            "filing_date": "",
            "case_number": "",
            "court": "",
            "named_plaintiffs": [],
            "named_defendants": []
        }
    
    def extract_classification_metadata(self, csv_file: Optional[Path], 
                                      filename: str) -> Dict[str, Any]:
        """
        Extract page-level metadata from classification CSV.
        
        Args:
            csv_file: Path to classification CSV file
            filename: Filename to look up (e.g., "page_0001.png")
            
        Returns:
            Dictionary with page metadata
        """
        if not csv_file or not csv_file.exists():
            return self._get_default_page_metadata()
        
        try:
            with open(csv_file, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get('filename', '') == filename:
                        return self._normalize_page_metadata(row)
        except Exception as e:
            print(f"Error reading classification CSV {csv_file}: {e}")
        
        return self._get_default_page_metadata()
    
    def _normalize_page_metadata(self, row: Dict[str, str]) -> Dict[str, Any]:
        """Normalize page metadata from CSV row."""
        # Handle various possible column names
        category = row.get('category', row.get('Category', ''))
        subtype = row.get('subtype', row.get('Subtype', ''))
        exhibit_label = row.get('exhibit_label', row.get('Exhibit_Label', ''))
        exhibit_title = row.get('exhibit_title', row.get('Exhibit_Title', ''))
        notes = row.get('notes', row.get('Notes', ''))
        
        # Determine page type
        page_type = self._determine_page_type(category, subtype, notes)
        
        # Clean up exhibit information
        if exhibit_label and str(exhibit_label).strip() and str(exhibit_label) != 'nan':
            exhibit_label = str(exhibit_label).strip()
        else:
            exhibit_label = None
            
        if exhibit_title and str(exhibit_title).strip() and str(exhibit_title) != 'nan':
            exhibit_title = str(exhibit_title).strip()
        else:
            exhibit_title = None
        
        return {
            "page_type": page_type,
            "category": category,
            "subtype": subtype,
            "exhibit_label": exhibit_label,
            "exhibit_title": exhibit_title,
            "notes": notes
        }
    
    def _determine_page_type(self, category: str, subtype: str, notes: str) -> str:
        """Determine standardized page type from classification data."""
        category_lower = category.lower() if category else ""
        subtype_lower = subtype.lower() if subtype else ""
        notes_lower = notes.lower() if notes else ""
        
        # Map classification categories to standard page types
        if "pleading" in category_lower and "first" in category_lower:
            return "pleading_first_page"
        elif "pleading" in category_lower:
            return "pleading_body"
        elif "exhibit" in category_lower:
            if "cover" in category_lower or "cover" in notes_lower:
                return "exhibit_cover"
            else:
                return "exhibit_content"
        elif "proof of service" in category_lower:
            return "proof_of_service"
        elif "signature" in category_lower:
            return "signature_page"
        elif "caption" in category_lower or "header" in category_lower:
            return "case_caption"
        else:
            return "pleading_body"  # Default fallback
    
    def _get_default_page_metadata(self) -> Dict[str, Any]:
        """Get default page metadata structure."""
        return {
            "page_type": "pleading_body",
            "category": "",
            "subtype": "", 
            "exhibit_label": None,
            "exhibit_title": None,
            "notes": ""
        }
    
    def extract_folder_metadata(self, folder_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from document folder structure.
        
        Args:
            folder_path: Path to document folder
            
        Returns:
            Dictionary with folder-level metadata
        """
        metadata = {
            "folder_name": folder_path.name,
            "has_toc": False,
            "has_caption": False,
            "has_classification": False,
            "page_count": 0,
            "files": {
                "png_files": [],
                "text_files": [],
                "metadata_files": []
            }
        }
        
        # Check for standard subdirectories
        png_dir = folder_path / "PNG"
        text_dir = folder_path / "text_pages" 
        meta_dir = folder_path / "metadata"
        
        if png_dir.exists():
            png_files = list(png_dir.glob("page_*.png"))
            metadata["files"]["png_files"] = [f.name for f in png_files]
            metadata["page_count"] = len(png_files)
        
        if text_dir.exists():
            text_files = list(text_dir.glob("page_*.txt"))
            metadata["files"]["text_files"] = [f.name for f in text_files]
        
        if meta_dir.exists():
            meta_files = list(meta_dir.glob("*"))
            metadata["files"]["metadata_files"] = [f.name for f in meta_files]
            
            # Check for specific metadata types
            metadata["has_toc"] = any("TOC" in f.name for f in meta_files)
            metadata["has_caption"] = any("caption" in f.name for f in meta_files)
            metadata["has_classification"] = any("classification" in f.name for f in meta_files)
        
        return metadata
    
    def get_all_documents_metadata(self, doc_files_dir: Path) -> List[Dict[str, Any]]:
        """
        Get metadata for all documents in doc_files directory.
        
        Args:
            doc_files_dir: Path to doc_files directory
            
        Returns:
            List of metadata dictionaries for each document
        """
        documents = []
        
        for folder in doc_files_dir.iterdir():
            if folder.is_dir() and folder.name != "__pycache__":
                folder_meta = self.extract_folder_metadata(folder)
                
                # Try to get caption metadata
                caption_file = folder / "metadata" / "page_0001_caption.txt"
                if not caption_file.exists():
                    # Look for any caption file
                    meta_dir = folder / "metadata"
                    if meta_dir.exists():
                        caption_files = list(meta_dir.glob("*caption*.txt"))
                        caption_file = caption_files[0] if caption_files else None
                
                caption_meta = self.extract_caption_metadata(caption_file)
                
                # Combine metadata
                combined_meta = {
                    **folder_meta,
                    **caption_meta,
                    "folder_path": str(folder)
                }
                
                documents.append(combined_meta)
        
        return documents


if __name__ == "__main__":
    # Example usage
    import sys
    
    extractor = MetadataExtractor()
    
    if len(sys.argv) > 1:
        doc_files_dir = Path(sys.argv[1])
        if doc_files_dir.exists():
            print("=== Document Metadata Extraction ===")
            documents = extractor.get_all_documents_metadata(doc_files_dir)
            
            for i, doc in enumerate(documents, 1):
                print(f"\nDocument {i}: {doc['folder_name']}")
                print(f"  Title: {doc.get('document_title', 'N/A')}")
                print(f"  Filing Party: {doc.get('filing_party', 'N/A')}")
                print(f"  Filing Date: {doc.get('filing_date', 'N/A')}")
                print(f"  Pages: {doc.get('page_count', 0)}")
                print(f"  Has TOC: {doc.get('has_toc', False)}")
                print(f"  Has Classification: {doc.get('has_classification', False)}")
        else:
            print(f"Directory not found: {doc_files_dir}")
    else:
        print("Usage: python metadata_extractor.py <doc_files_directory>")