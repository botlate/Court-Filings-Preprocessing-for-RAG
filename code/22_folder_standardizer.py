#!/usr/bin/env python3
"""
Simple folder renamer that processes CSV data directly without PDF conversion.
Creates clean, readable folder names for legal documents.
"""

import argparse
import csv
import os
import sys
import shutil
import time
import re
from pathlib import Path
from typing import List, Dict, Tuple
from openai import OpenAI

def detect_standardized_name(folder_name: str) -> bool:
    """Detect if folder name is already in standardized format."""
    # Pattern: YYYY MM DD [Party] [Doc Type] - [Description]
    pattern = r'^\d{4}\s+\d{2}\s+\d{2}\s+\w+.*\s+-\s+.+$'
    return bool(re.match(pattern, folder_name))

def analyze_folder_naming_state(doc_files_path: Path) -> dict:
    """Analyze current state of folder naming."""
    if not doc_files_path.exists():
        return {"total": 0, "standardized": 0, "needs_rename": 0, "percentage_standardized": 0}
    
    total = 0
    standardized = 0
    
    for item in doc_files_path.iterdir():
        if item.is_dir():
            total += 1
            if detect_standardized_name(item.name):
                standardized += 1
    
    percentage = (standardized / total * 100) if total > 0 else 0
    
    return {
        "total": total,
        "standardized": standardized, 
        "needs_rename": total - standardized,
        "percentage_standardized": percentage
    }

def check_csv_for_standardized_names(csv_content: str) -> bool:
    """Check if CSV already contains StandardName column with data."""
    import csv
    from io import StringIO
    
    reader = csv.DictReader(StringIO(csv_content))
    
    # Check if StandardName column exists and has data
    first_row = next(reader, None)
    if not first_row or 'StandardName' not in first_row:
        return False
    
    # Check if StandardName column has actual standardized data
    if first_row['StandardName'] and detect_standardized_name(first_row['StandardName']):
        return True
    
    return False

def create_simple_prompt() -> str:
    """Create a simple, effective naming prompt."""
    return """You create clean folder names for legal documents using standard legal acronyms.

RULES:
1. Format: YYYY MM DD [Party] [Document Type] - [Description if needed]
2. Date format: YYYY MM DD (no hyphens, space-separated)
3. Standard legal acronyms:
   - Complaints: FAC (First Amended Complaint), SAC (Second Amended Complaint), FAP (First Amended Petition), TAC (Third Amended Complaint), 4AP (Fourth Amended Petition), 5AC, 6AP, and so forth
   - Motions: Mtn (Motion), MSJ (Motion for Summary Judgment), MIL (Motion in Limine), Demurrer (Demurrer)
   - Responses: Oppo (Opposition), Reply, Answer (use "iso" (in support of) or "to" if space permits)
   - Other: POS (Proof of Service), Decl (Declaration), RJN (Request for Judicial Notice), Order
4. Party abbreviations: Pltf/s (Plaintiff), Def/s (Defendant), Petnr/s (Petitioner), Resp/s (Respondent)
5. Use only letters, numbers, spaces, and hyphens
6. Maximum 60 characters total
7. If date is missing, use the folder name as-is
8. Do not title in all caps, even if original was.

EXAMPLES:
- Input: "Plaintiff's First Amended Complaint for Declaratory and Injunctive Relief", filing_party: plaintiff, filing_date: 2024-03-15
- Output: "2024 03 15 FAC First Amended Complaint"

- Input: "Opposition to Motion for Summary Judgment", filing_party: defendant, filing_date: APR 20 2024  
- Output: "2024 04 20 Def Oppo to MSJ"

- Input: "Motion in Limine No. 1", filing_party: plaintiff, filing_date: May 10, 2024
- Output: "2024 05 10 Pltf MIL 01"

FURTHER EXAMPLES:
- "2019 05 28 Acme Notice & Mtn MSJ"
- "2019 05 29 Acme Memo iso MSJ"
- "2020 01 15 Doe Notice & Mtn Compel re Smith Spec Rogs Set 01"
- "2021 03 02 Global & Future Joint Demurrer to FAC" [If Global and Future were two separate defendants, among more than two]
- "2022 07 19 Decl Atty Roe iso Def MSJ Oppo"
- "2017 03 04 SAP Second Amended Petition"
- "2017 04 12 Amended Answer to SAP"
- "2017 04 12 POS Def subpoena re business docs"
- "2023 04 11 Reply to MegaCorp Mtn Strike Portions of Compl"
- "2024 09 30 Ex Parte Appl - OST re Brown Depo Mtn"
- "2024 06 05 Notice & Mtn Leave to File SAC"
- "2025 02 20 Doe & Smith Oppo to Big MSA re Causes 01 03 - ECF #117"
- "2025 05 12 RJN iso Def MJP"
- "2025 07 01 Pltf MIL 01 - Exclude Evid of Subsq Remdl Measures"
"""

def sanitize_folder_name(name: str) -> str:
    """Sanitize folder name to be filesystem-safe."""
    # Replace problematic characters
    name = name.replace('/', '-').replace('\\', '-').replace(':', '-')
    name = name.replace('<', '').replace('>', '').replace('|', '-')
    name = name.replace('"', '').replace('?', '').replace('*', '')
    
    # Remove extra spaces and limit length
    name = ' '.join(name.split())  # Normalize whitespace
    if len(name) > 80:  # Windows has ~260 char path limit, be conservative
        name = name[:80].strip()
    
    return name

def rename_folders(csv_content: str, doc_files_path: str) -> List[Tuple[str, str, bool]]:
    """
    Rename folders based on the CSV mapping.
    Returns list of (old_name, new_name, success) tuples.
    """
    from io import StringIO
    
    csv_reader = csv.DictReader(StringIO(csv_content))
    rename_results = []
    
    for row in csv_reader:
        old_name = row.get('FolderName', '').strip()
        new_name = row.get('StandardName', '').strip()
        
        if not old_name or not new_name or old_name == new_name:
            continue
            
        # Sanitize the new name
        new_name = sanitize_folder_name(new_name)
        
        old_path = Path(doc_files_path) / old_name
        new_path = Path(doc_files_path) / new_name
        
        success = False
        try:
            if old_path.exists() and old_path.is_dir():
                if new_path.exists():
                    print(f"Warning: Target folder already exists: {new_name}")
                    rename_results.append((old_name, new_name, False))
                    continue
                
                # Perform the rename
                old_path.rename(new_path)
                print(f"Renamed: {old_name} → {new_name}")
                success = True
            else:
                print(f"Warning: Source folder not found: {old_name}")
                
        except Exception as e:
            print(f"Error renaming {old_name} to {new_name}: {e}")
            
        rename_results.append((old_name, new_name, success))
    
    return rename_results

def process_csv_row_by_row(csv_content: str, client: OpenAI) -> str:
    """Process CSV by sending each row individually to avoid alignment issues."""
    from io import StringIO
    
    # Read the CSV
    csv_reader = csv.DictReader(StringIO(csv_content))
    fieldnames = csv_reader.fieldnames
    
    if not fieldnames:
        return csv_content
    
    # Ensure StandardName column exists
    if 'StandardName' not in fieldnames:
        fieldnames = list(fieldnames) + ['StandardName']
    
    # Process each row
    output_rows = []
    prompt = create_simple_prompt()
    
    for row in csv_reader:
        # Extract key information
        folder_name = row.get('FolderName', '')
        filing_date = row.get('FilingDate', '')
        document_title = row.get('DocumentTitle', '')
        filing_party = row.get('FilingParty', '')
        
        # Create input text for the model
        input_text = f"""
Current folder name: {folder_name}
Filing date: {filing_date}
Document title: {document_title}
Filing party: {filing_party}

Create a standardized folder name following the rules above. Output only the folder name, nothing else:
"""
        
        # Retry logic for API calls
        max_retries = 3
        standard_name = folder_name  # Default fallback
        
        for attempt in range(max_retries):
            try:
                print(f"  Processing: {folder_name} (attempt {attempt + 1}/{max_retries})...")
                
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": input_text}
                    ],
                    temperature=0,
                    max_tokens=150
                )
                
                standard_name = response.choices[0].message.content.strip()
                print(f"    Raw response: '{standard_name}'")
                
                # Clean up the response (remove quotes, extra whitespace)
                standard_name = standard_name.replace('"', '').replace("'", '').strip()
                
                # Validate the response
                if not standard_name:
                    print(f"    Warning: Empty response for {folder_name}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    standard_name = folder_name
                elif len(standard_name) > 120:
                    print(f"    Warning: Response too long ({len(standard_name)} chars) for {folder_name}")
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    standard_name = folder_name
                elif standard_name.lower() == folder_name.lower():
                    print(f"    Warning: Response unchanged for {folder_name}")
                    # This might be valid, so don't retry
                    break
                else:
                    print(f"    Success: {folder_name} → {standard_name}")
                    break  # Success, exit retry loop
                    
            except Exception as e:
                print(f"    Error processing {folder_name} (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print(f"    Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    print(f"    Final fallback to original name: {folder_name}")
                    print(f"    Input text was: {input_text[:200]}...")
                    standard_name = folder_name
        
        # Add the standard name to the row
        row['StandardName'] = standard_name
        output_rows.append(row)
    
    # Write back to CSV format
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator='\n')
    writer.writeheader()
    writer.writerows(output_rows)
    
    return output.getvalue()

def main():
    parser = argparse.ArgumentParser(description="Legal document folder standardizer with re-renaming prevention")
    parser.add_argument("--csv", required=True, help="Input CSV file")
    parser.add_argument("--out", required=True, help="Output CSV file")
    parser.add_argument("--model", default="gpt-4o-mini", help="OpenAI model to use")
    parser.add_argument("--rename-folders", action="store_true", help="Actually rename the folders in doc_files")
    parser.add_argument("--doc-files-path", help="Path to doc_files directory (auto-detected if not provided)")
    parser.add_argument("--auto-confirm", action="store_true", help="Skip confirmation prompt for folder renaming")
    parser.add_argument("--force-rename", action="store_true", help="Force renaming even if folders appear already standardized")
    parser.add_argument("--analysis-only", action="store_true", help="Only analyze current naming state without making changes")
    
    args = parser.parse_args()
    
    # Auto-detect doc_files path if not provided
    if args.doc_files_path:
        doc_files_path = Path(args.doc_files_path)
    else:
        # Assume doc_files is in the same directory as the CSV
        csv_dir = Path(args.csv).parent
        doc_files_path = csv_dir / "doc_files"
        if not doc_files_path.exists():
            doc_files_path = csv_dir
    
    # Analyze current naming state
    naming_analysis = analyze_folder_naming_state(doc_files_path)
    
    print(f"\n=== Folder Naming Analysis ===")
    print(f"Total folders: {naming_analysis['total']}")
    print(f"Already standardized: {naming_analysis['standardized']}")
    print(f"Need renaming: {naming_analysis['needs_rename']}")
    print(f"Standardized percentage: {naming_analysis['percentage_standardized']:.1f}%")
    
    # Check if analysis-only mode
    if args.analysis_only:
        print("\nAnalysis complete. No changes made (--analysis-only flag)")
        return
    
    # Re-renaming prevention check
    if naming_analysis['percentage_standardized'] > 70 and not args.force_rename:
        print(f"\n[WARNING] {naming_analysis['percentage_standardized']:.1f}% of folders appear to already be standardized.")
        print("This suggests they may have been renamed before.")
        print("Use --force-rename to override this safety check.")
        print("Use --analysis-only to just check status without making changes.")
        return
    
    # Read and check input CSV
    with open(args.csv, 'r', encoding='utf-8') as f:
        csv_content = f.read()
    
    # Check if CSV already has standardized names
    if check_csv_for_standardized_names(csv_content) and not args.force_rename:
        print("\n[WARNING] Input CSV already contains standardized names.")
        print("This suggests renaming may have been done before.")
        print("Use --force-rename to override this safety check.")
        return
    
    # Initialize OpenAI client
    client = OpenAI()
    
    # Process the CSV
    print("\nGenerating standardized folder names...")
    result = process_csv_row_by_row(csv_content, client)
    
    # Write output CSV
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(result)
    
    print(f"\nStandardized names written to: {args.out}")
    
    # Optionally rename the actual folders
    if args.rename_folders:
        print(f"\nPreparing to rename folders in: {doc_files_path}")
        
        # Final confirmation (skip if auto-confirm is set)
        if args.auto_confirm:
            confirm = 'y'
        elif args.force_rename:
            confirm = input("FORCE MODE: This will rename folders that may already be standardized. Continue? [y/N]: ").strip().lower()
        else:
            confirm = input("This will rename actual folders. Continue? [y/N]: ").strip().lower()
        
        if confirm in ['y', 'yes']:
            rename_results = rename_folders(result, str(doc_files_path))
            
            # Summary
            successful = sum(1 for _, _, success in rename_results if success)
            total = len(rename_results)
            print(f"\nRenaming complete: {successful}/{total} folders renamed successfully")
            
            # Show any failures
            failures = [(old, new) for old, new, success in rename_results if not success]
            if failures:
                print("\nFailed renames:")
                for old, new in failures:
                    print(f"  {old} → {new}")
                    
            # Updated analysis
            post_analysis = analyze_folder_naming_state(doc_files_path)
            print(f"\nPost-rename analysis:")
            print(f"Standardized: {post_analysis['standardized']}/{post_analysis['total']} ({post_analysis['percentage_standardized']:.1f}%)")
        else:
            print("Folder renaming cancelled.")
    else:
        print("\nTo actually rename folders, run again with --rename-folders flag")
        print("To check current status, use --analysis-only flag")

if __name__ == "__main__":
    main()