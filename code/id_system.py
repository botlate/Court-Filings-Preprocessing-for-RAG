#!/usr/bin/env python3
"""
Document ID Management System

Manages document IDs and chunk IDs across the pipeline.
- Document IDs are 4-digit numbers assigned to each document folder
- Chunk IDs are 3-digit numbers assigned to chunks within each document
- ID mappings are stored in document_id_mapping.json in the doc_files directory
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Optional, Tuple


class DocumentIDManager:
    """Manages document ID assignments and mappings."""
    
    def __init__(self, base_dir: Path):
        """
        Initialize the document ID manager.
        
        Args:
            base_dir: Base directory containing doc_files
        """
        self.base_dir = Path(base_dir)
        self.doc_files_dir = self.base_dir / "doc_files"
        self.mapping_file = self.doc_files_dir / "document_id_mapping.json"
        self.mappings = self._load_mappings()
        
    def _load_mappings(self) -> Dict[str, int]:
        """Load existing document ID mappings from JSON file."""
        if self.mapping_file.exists():
            try:
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('document_mappings', {})
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return {}
    
    def _save_mappings(self):
        """Save document ID mappings to JSON file."""
        self.doc_files_dir.mkdir(exist_ok=True)
        
        # Create comprehensive mapping data
        mapping_data = {
            "format_info": {
                "document_id_format": "4-digit number (e.g., 0054)",
                "chunk_id_format": "3-digit number (e.g., 014)",
                "filename_format": "documentID_chunkID.txt (e.g., 0054_014.txt)",
                "description": "Document ID mappings for pipeline processing"
            },
            "document_mappings": self.mappings,
            "metadata": {
                "total_documents": len(self.mappings),
                "next_available_id": max(self.mappings.values(), default=0) + 1 if self.mappings else 1
            }
        }
        
        with open(self.mapping_file, 'w', encoding='utf-8') as f:
            json.dump(mapping_data, f, ensure_ascii=False, indent=2)
    
    def _generate_document_hash(self, folder_name: str) -> str:
        """Generate a stable hash for a document folder name."""
        return hashlib.md5(folder_name.encode('utf-8')).hexdigest()[:8]
    
    def get_document_id(self, folder_name: str) -> int:
        """
        Get or assign a document ID for a folder name.
        
        Args:
            folder_name: Name of the document folder
            
        Returns:
            Document ID as integer
        """
        # Normalize folder name (handle potential renaming)
        normalized_name = folder_name.strip()
        
        # Check if we already have this folder mapped
        if normalized_name in self.mappings:
            return self.mappings[normalized_name]
        
        # Check if this might be a renamed version of an existing folder
        # Look for similar names or hash matches
        document_hash = self._generate_document_hash(normalized_name)
        for existing_name, existing_id in self.mappings.items():
            existing_hash = self._generate_document_hash(existing_name)
            if existing_hash == document_hash:
                # This is likely the same document, update mapping
                self.mappings[normalized_name] = existing_id
                self._save_mappings()
                return existing_id
        
        # Assign new ID
        next_id = max(self.mappings.values(), default=0) + 1
        self.mappings[normalized_name] = next_id
        self._save_mappings()
        
        return next_id
    
    def get_folder_name_by_id(self, document_id: int) -> Optional[str]:
        """Get folder name by document ID."""
        for folder_name, doc_id in self.mappings.items():
            if doc_id == document_id:
                return folder_name
        return None
    
    def list_all_mappings(self) -> Dict[str, int]:
        """Get all current document mappings."""
        return self.mappings.copy()
    
    def format_ids(self, document_id: int, chunk_id: int) -> Tuple[str, str]:
        """
        Format document and chunk IDs as 4-digit and 3-digit strings.
        
        Args:
            document_id: Document ID number
            chunk_id: Chunk ID number
            
        Returns:
            Tuple of (formatted_document_id, formatted_chunk_id)
        """
        return f"{document_id:04d}", f"{chunk_id:03d}"
    
    def update_folder_name(self, old_name: str, new_name: str):
        """
        Update folder name mapping (for handling renames).
        
        Args:
            old_name: Previous folder name
            new_name: New folder name
        """
        if old_name in self.mappings:
            document_id = self.mappings.pop(old_name)
            self.mappings[new_name] = document_id
            self._save_mappings()


class ChunkIDGenerator:
    """Generates sequential chunk IDs within a document."""
    
    def __init__(self):
        """Initialize chunk ID generator."""
        self.current_id = 0
    
    def next_id(self) -> int:
        """Get next sequential chunk ID."""
        self.current_id += 1
        return self.current_id
    
    def reset(self):
        """Reset chunk ID counter (for new document)."""
        self.current_id = 0
    
    def get_current_id(self) -> int:
        """Get current chunk ID without incrementing."""
        return self.current_id


def create_document_mapping_csv(doc_files_dir: Path) -> Path:
    """
    Create a CSV file listing all documents and their IDs.
    
    Args:
        doc_files_dir: Path to doc_files directory
        
    Returns:
        Path to created CSV file
    """
    manager = DocumentIDManager(doc_files_dir.parent)
    csv_file = doc_files_dir / "document_registry.csv"
    
    # Create CSV with document information
    import csv
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['document_id', 'folder_name', 'document_id_formatted', 'status'])
        
        for folder_name, doc_id in manager.list_all_mappings().items():
            formatted_id = f"{doc_id:04d}"
            folder_path = doc_files_dir / folder_name
            status = "exists" if folder_path.exists() else "missing"
            writer.writerow([doc_id, folder_name, formatted_id, status])
    
    return csv_file


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        base_dir = Path(sys.argv[1])
    else:
        base_dir = Path(".")
    
    print("=== Document ID Management System ===")
    manager = DocumentIDManager(base_dir)
    
    print(f"Mapping file: {manager.mapping_file}")
    print(f"Current mappings:")
    
    for folder_name, doc_id in manager.list_all_mappings().items():
        print(f"  {doc_id:04d}: {folder_name}")
    
    # Create registry CSV
    if manager.doc_files_dir.exists():
        csv_file = create_document_mapping_csv(manager.doc_files_dir)
        print(f"\nDocument registry CSV created: {csv_file}")