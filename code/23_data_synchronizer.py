#!/usr/bin/env python3
"""
CSV Sync Script - Bidirectional synchronization between CSV files and source data.

This script detects changes in CSV files and propagates them back to:
1. caption.txt files (for document_title, filing_date, filing_party changes)
2. Folder names (when standardized names change)
3. Regenerates CSV if source files were modified

Usage:
python 06_sync_csv_changes.py --doc-files-path doc_files [--dry-run] [--force]
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import shutil

def load_csv_data(csv_path: str) -> Dict[str, Dict]:
    """Load CSV data indexed by folder name."""
    data = {}
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                folder_name = row.get('FolderName', '').strip()
                if folder_name:
                    data[folder_name] = row
    except FileNotFoundError:
        print(f"CSV file not found: {csv_path}")
    return data

def find_caption_file(folder_path: Path) -> Optional[Path]:
    """Find the caption file in a folder."""
    metadata_dir = folder_path / "metadata"
    if not metadata_dir.exists():
        return None
    
    # Look for caption files
    caption_files = list(metadata_dir.glob("*_caption.txt"))
    return caption_files[0] if caption_files else None

def read_caption_data(caption_path: Path) -> Dict:
    """Read and parse caption file data."""
    try:
        with open(caption_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try JSON first
        try:
            return json.loads(content.strip())
        except json.JSONDecodeError:
            # Fallback to regex extraction
            import re
            data = {}
            patterns = {
                'document_title': r'"document_title":\s*"([^"]*)"',
                'filing_date': r'"filing_date":\s*"([^"]*)"',
                'filing_party': r'"filing_party":\s*"([^"]*)"'
            }
            
            for key, pattern in patterns.items():
                match = re.search(pattern, content)
                data[key] = match.group(1) if match else 'N/A'
            
            return data
    except Exception as e:
        print(f"Error reading caption file {caption_path}: {e}")
        return {}

def write_caption_data(caption_path: Path, data: Dict, dry_run: bool = False):
    """Write data back to caption file in JSON format."""
    json_content = json.dumps(data, indent=2, ensure_ascii=False)
    
    if dry_run:
        print(f"  [DRY RUN] Would update {caption_path}")
        print(f"  New content: {json_content}")
    else:
        # Backup original file
        backup_path = caption_path.with_suffix('.txt.backup')
        shutil.copy2(caption_path, backup_path)
        
        with open(caption_path, 'w', encoding='utf-8') as f:
            f.write(json_content)
        print(f"  Updated {caption_path}")

def compare_and_sync(old_csv: Dict, new_csv: Dict, doc_files_path: Path, dry_run: bool = False) -> Dict:
    """Compare CSV data and sync changes back to source files."""
    changes_made = {
        'caption_updates': [],
        'folder_renames': [],
        'errors': []
    }
    
    # Check for changes in existing folders
    for folder_name, new_data in new_csv.items():
        old_data = old_csv.get(folder_name, {})
        folder_path = doc_files_path / folder_name
        
        if not folder_path.exists():
            changes_made['errors'].append(f"Folder not found: {folder_name}")
            continue
        
        # Check for caption file changes
        caption_changes = {}
        for field in ['DocumentTitle', 'FilingDate', 'FilingParty']:
            old_val = old_data.get(field, '').strip()
            new_val = new_data.get(field, '').strip()
            
            if old_val != new_val and new_val:
                # Map CSV field names to caption field names
                caption_field = {
                    'DocumentTitle': 'document_title',
                    'FilingDate': 'filing_date', 
                    'FilingParty': 'filing_party'
                }[field]
                caption_changes[caption_field] = new_val
        
        # Update caption file if there are changes
        if caption_changes:
            caption_path = find_caption_file(folder_path)
            if caption_path:
                try:
                    current_caption = read_caption_data(caption_path)
                    current_caption.update(caption_changes)
                    write_caption_data(caption_path, current_caption, dry_run)
                    changes_made['caption_updates'].append({
                        'folder': folder_name,
                        'file': str(caption_path),
                        'changes': caption_changes
                    })
                except Exception as e:
                    changes_made['errors'].append(f"Error updating {folder_name}: {e}")
            else:
                changes_made['errors'].append(f"No caption file found for {folder_name}")
    
    # Check for folder renames (based on StandardName changes)
    for folder_name, new_data in new_csv.items():
        old_data = old_csv.get(folder_name, {})
        old_standard = old_data.get('StandardName', '').strip()
        new_standard = new_data.get('StandardName', '').strip()
        
        if old_standard and new_standard and old_standard != new_standard:
            old_path = doc_files_path / folder_name
            new_folder_name = new_standard.replace('/', '-').replace('\\', '-')  # Sanitize
            new_path = doc_files_path / new_folder_name
            
            if old_path.exists() and not new_path.exists():
                if dry_run:
                    print(f"  [DRY RUN] Would rename folder: {folder_name} → {new_folder_name}")
                else:
                    try:
                        old_path.rename(new_path)
                        print(f"  Renamed folder: {folder_name} → {new_folder_name}")
                        changes_made['folder_renames'].append({
                            'old_name': folder_name,
                            'new_name': new_folder_name
                        })
                    except Exception as e:
                        changes_made['errors'].append(f"Error renaming {folder_name}: {e}")
    
    return changes_made

def create_backup(file_path: Path) -> Path:
    """Create a timestamped backup of a file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.with_suffix(f'.{timestamp}.backup')
    shutil.copy2(file_path, backup_path)
    return backup_path

def main():
    parser = argparse.ArgumentParser(description="Sync CSV changes back to source files")
    parser.add_argument("--doc-files-path", required=True, help="Path to doc_files directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without making changes")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--csv-file", help="Specific CSV file to sync (default: output.csv)")
    
    args = parser.parse_args()
    
    doc_files_path = Path(args.doc_files_path)
    if not doc_files_path.exists():
        print(f"Error: doc_files path does not exist: {doc_files_path}")
        sys.exit(1)
    
    # Determine CSV files to work with
    current_csv = doc_files_path / (args.csv_file or "output.csv")
    backup_csv = None
    
    # Look for backup files to compare against
    backup_files = list(doc_files_path.glob("output.*.backup"))
    if backup_files:
        # Use the most recent backup
        backup_csv = max(backup_files, key=lambda x: x.stat().st_mtime)
        print(f"Found backup file: {backup_csv}")
    
    if not current_csv.exists():
        print(f"Error: CSV file does not exist: {current_csv}")
        sys.exit(1)
    
    # Load CSV data
    print(f"Loading current CSV: {current_csv}")
    new_data = load_csv_data(str(current_csv))
    
    old_data = {}
    if backup_csv:
        print(f"Loading backup CSV: {backup_csv}")
        old_data = load_csv_data(str(backup_csv))
    else:
        print("No backup file found - will treat all data as new")
    
    if not new_data:
        print("No data found in CSV file")
        sys.exit(1)
    
    # Create backup of current CSV before making changes
    if not args.dry_run:
        backup_path = create_backup(current_csv)
        print(f"Created backup: {backup_path}")
    
    # Compare and sync
    print(f"\nAnalyzing changes...")
    changes = compare_and_sync(old_data, new_data, doc_files_path, args.dry_run)
    
    # Report results
    print(f"\n{'=== DRY RUN RESULTS ===' if args.dry_run else '=== SYNC RESULTS ==='}")
    print(f"Caption file updates: {len(changes['caption_updates'])}")
    print(f"Folder renames: {len(changes['folder_renames'])}")
    print(f"Errors: {len(changes['errors'])}")
    
    if changes['caption_updates']:
        print("\nCaption file updates:")
        for update in changes['caption_updates']:
            print(f"  {update['folder']}: {update['changes']}")
    
    if changes['folder_renames']:
        print("\nFolder renames:")
        for rename in changes['folder_renames']:
            print(f"  {rename['old_name']} → {rename['new_name']}")
    
    if changes['errors']:
        print("\nErrors:")
        for error in changes['errors']:
            print(f"  {error}")
    
    if args.dry_run:
        print("\nTo apply these changes, run without --dry-run")
    elif not args.force and (changes['caption_updates'] or changes['folder_renames']):
        confirm = input("\nProceed with these changes? [y/N]: ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("Changes cancelled.")
            sys.exit(0)

if __name__ == "__main__":
    main()