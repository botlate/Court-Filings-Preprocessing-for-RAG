import subprocess
import sys
import os
import argparse
import glob

def get_script_path(script_id: str, base_dir: str) -> str:
    """
    Central mapping for script names. Supports both old and new naming.
    """
    script_map = {
        # New naming convention
        "pdf_extractor": "10_pdf_extractor.py",
        "document_classifier": "11_document_classifier.py", 
        "toc_formatter": "20_toc_formatter.py",
        "metadata_aggregator": "21_metadata_aggregator.py",
        "folder_standardizer": "22_folder_standardizer.py",
        "data_synchronizer": "23_data_synchronizer.py",
        "toc_chunker": "30_toc_chunker.py",
        "semantic_chunker": "31_semantic_chunker.py",
        "vision_enhancer": "40_vision_enhancer.py",
        
        # Backward compatibility (deprecated) - will remove after transition
        "01_pdf_extractor-001": "01_pdf_extractor-001.py",
        "02_openai_classifier_03_gpt_5": "02_openai_classifier_03_gpt_5.py",
        "03_toc_fix_script- USEFUL": "03_toc_fix_script- USEFUL.py",
        "04_doc_title_extraction_mk_csv_app": "04_doc_title_extraction_mk_csv_app.py",
        "05_simple_folder_rename": "05_simple_folder_rename.py",
        "06_sync_csv_changes": "06_sync_csv_changes.py",
        "07_TOC_text_integrator_and_chunker": "07_TOC_text_integrator_and_chunker.py",
        "08_chunker_non-TOC_docs": "08_chunker_non-TOC_docs.py",
        "07a_vision_heading_detector_complete": "07a_vision_heading_detector_complete.py",
    }
    
    # Check if using new naming convention
    if script_id in script_map:
        script_name = script_map[script_id]
        # Check if new file exists, otherwise fall back to old name
        new_path = os.path.join(base_dir, script_name)
        if os.path.exists(new_path):
            return new_path
        # Try old name if new doesn't exist
        if script_id.startswith("0"):  # Old naming
            old_path = os.path.join(base_dir, script_map[script_id])
            if os.path.exists(old_path):
                return old_path
    
    # Default: assume it's a direct filename
    return os.path.join(base_dir, f"{script_id}.py" if not script_id.endswith('.py') else script_id)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Document processing pipeline")
    parser.add_argument("--update-mode", action="store_true", 
                       help="Run in update mode to sync CSV changes")
    parser.add_argument("--csv-type", choices=["output", "standardized"], default="output",
                       help="CSV file to update (for update mode)")
    
    # Folder renaming control arguments
    parser.add_argument("--skip-folder-rename", action="store_true", 
                       help="Skip folder renaming step entirely")
    parser.add_argument("--force-folder-rename", action="store_true",
                       help="Force folder renaming even if already completed")
    parser.add_argument("--rename-confirmation", choices=["auto", "prompt", "skip"],
                       default="prompt", help="How to handle folder rename confirmation")
    
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # If in update mode, run the update pipeline instead
    if args.update_mode:
        update_script = os.path.join(base_dir, "update_pipeline.py")
        update_args = [
            "--doc-files-path", os.path.join(base_dir, "doc_files"),
            "--csv-type", args.csv_type
        ]
        
        try:
            result = subprocess.run(["python", update_script] + update_args)
            sys.exit(result.returncode)
        except Exception as e:
            print(f"Error running update pipeline: {e}")
            sys.exit(1)

    # Configuration for the pipeline.
    extractor_config = {
        "input_folder": os.path.join(base_dir, "PDFs"),
        "output_folder": os.path.join(base_dir, "doc_files"),
        "script": get_script_path("pdf_extractor", base_dir),
        "timeout": 600  # seconds for the extractor script
    }
    classifier_config = {
        "script": get_script_path("document_classifier", base_dir),
        "input_folder": extractor_config["output_folder"],
        "timeout": 3600  # increased timeout for the classifier script (1 hour)
    }
    toc_fix_config = {
        "script": get_script_path("toc_formatter", base_dir),
        "input_folder": extractor_config["output_folder"],
        "timeout": 300  # timeout for the TOC fix script (5 minutes)
    }
    csv_creation_config = {
        "script": get_script_path("metadata_aggregator", base_dir),
        "input_folder": extractor_config["output_folder"],
        "timeout": 600  # timeout for the CSV creation script (10 minutes)
    }
    folder_rename_config = {
        "script": get_script_path("folder_standardizer", base_dir),
        "input_csv": os.path.join(extractor_config["output_folder"], "output.csv"),
        "output_csv": os.path.join(extractor_config["output_folder"], "output_standardized.csv"),
        "timeout": 600  # timeout for the folder rename script (10 minutes)
    }
    
    # Chunking configurations
    toc_chunker_config = {
        "script": get_script_path("toc_chunker", base_dir),
        "input_folder": extractor_config["output_folder"],
        "timeout": 1800  # timeout for the TOC chunker script (30 minutes)
    }
    non_toc_chunker_config = {
        "script": get_script_path("semantic_chunker", base_dir),
        "input_folder": extractor_config["output_folder"],
        "timeout": 1800  # timeout for the non-TOC chunker script (30 minutes)
    }
    
    # OCR enhancement configuration (future capability)
    ocr_enhancer_config = {
        "script": get_script_path("ocr_enhancer", base_dir),  # 50_ocr_enhancer.py
        "timeout": 3600,  # 1 hour for OCR processing
        "enabled": False,  # Disabled by default until PaddleOCR is installed
        "use_gpu": False,
        "language": "en"
    }

    # Run the extractor only if output folder doesn't exist or is empty.
    output_folder = extractor_config["output_folder"]
    if not os.path.exists(output_folder) or not os.listdir(output_folder):
        print("Running PDF extractor script...")
        result1 = subprocess.run(
            ["python", extractor_config["script"], extractor_config["input_folder"], extractor_config["output_folder"]],
            timeout=extractor_config["timeout"]
        )
        if result1.returncode != 0:
            print("Error in PDF extractor script:")
            print(result1.stderr)
            sys.exit(1)
        print("PDF extractor script finished.")
    else:
        print("Extraction already completed. Skipping PDF extractor step.")

    # Validate output folder.
    if not os.path.exists(output_folder):
        print(f"Expected output folder does not exist: {output_folder}")
        sys.exit(1)
    if not os.listdir(output_folder):
        print(f"Output folder is empty: {output_folder}")
        sys.exit(1)
    print("Output folder verification passed.")

    # Determine if classification needs to run by checking for a metadata folder in each document's output.
    run_classifier = False
    for item in os.listdir(output_folder):
        item_path = os.path.join(output_folder, item)
        if os.path.isdir(item_path):
            metadata_dir = os.path.join(item_path, "metadata")
            if not os.path.exists(metadata_dir):
                run_classifier = True
                # Continue checking other documents without breaking
                continue
            
            # Check if metadata_dir contains a CSV file and a caption.txt file
            metadata_files = os.listdir(metadata_dir)
            csv_present = any(fname.lower().endswith('.csv') for fname in metadata_files)
            caption_present = any(fname.lower().endswith('_caption.txt') for fname in metadata_files)
            
            if not (csv_present and caption_present):
                run_classifier = True
                # Continue checking other documents without breaking
                continue

    if run_classifier:
        print("Running OpenAI classifier script...")
        try:
            result2 = subprocess.run(
                ["python", classifier_config["script"], classifier_config["input_folder"]],
                timeout=classifier_config["timeout"]
            )
            if result2.returncode != 0:
                print("Error in OpenAI classifier script:")
                print(result2.stderr)
                sys.exit(1)
            print("OpenAI classifier script finished.")
        except subprocess.TimeoutExpired:
            print("OpenAI classifier script timed out.")
            sys.exit(1)
    else:
        print("Classification already completed for all documents. Skipping classifier step.")

    # Check if TOC fix needs to run by looking for unprocessed TOC files
    run_toc_fix = False
    toc_pattern = os.path.join(output_folder, "**", "page_*_TOC.txt")
    toc_files = glob.glob(toc_pattern, recursive=True)
    
    if toc_files:
        # Check if any TOC files still contain "TABLE OF CONTENTS" header (indicating they need processing)
        for toc_file in toc_files:
            try:
                with open(toc_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if "# TABLE OF CONTENTS" in content or "TABLE OF CONTENTS" in content:
                        run_toc_fix = True
                        break
            except Exception:
                # If we can't read the file, assume it needs processing
                run_toc_fix = True
                break

    if run_toc_fix:
        print("Running TOC fix script...")
        try:
            result3 = subprocess.run(
                ["python", toc_fix_config["script"], toc_fix_config["input_folder"]],
                timeout=toc_fix_config["timeout"]
            )
            if result3.returncode != 0:
                print("Error in TOC fix script:")
                print(result3.stderr)
                sys.exit(1)
            print("TOC fix script finished.")
        except subprocess.TimeoutExpired:
            print("TOC fix script timed out.")
            sys.exit(1)
    else:
        print("TOC fix already completed for all files. Skipping TOC fix step.")

    # Check if CSV creation needs to run
    csv_output_path = os.path.join(output_folder, "output.csv")
    run_csv_creation = True
    
    if os.path.exists(csv_output_path):
        print(f"CSV file already exists: {csv_output_path}")
        while True:
            choice = input("Do you want to (u)se existing CSV, (o)verride it, or (q)uit? [u/o/q]: ").lower().strip()
            if choice in ['u', 'use']:
                run_csv_creation = False
                print("Using existing CSV file.")
                break
            elif choice in ['o', 'override']:
                run_csv_creation = True
                print("Will override existing CSV file.")
                break
            elif choice in ['q', 'quit']:
                print("Exiting pipeline.")
                sys.exit(0)
            else:
                print("Please enter 'u' for use existing, 'o' for override, or 'q' to quit.")

    if run_csv_creation:
        print("Running CSV creation script...")
        try:
            result4 = subprocess.run(
                ["python", csv_creation_config["script"], csv_creation_config["input_folder"]],
                timeout=csv_creation_config["timeout"]
            )
            if result4.returncode != 0:
                print("Error in CSV creation script:")
                print(result4.stderr)
                sys.exit(1)
            print("CSV creation script finished.")
        except subprocess.TimeoutExpired:
            print("CSV creation script timed out.")
            sys.exit(1)
    else:
        print("Skipping CSV creation step - using existing file.")

    # ---- Folder Rename Step (Optional) ----
    import re
    
    def should_run_folder_rename(args, folder_rename_config):
        """Determine if folder renaming should run based on arguments and state."""
        
        # Skip if explicitly requested
        if args.skip_folder_rename:
            print("Folder renaming skipped by user request (--skip-folder-rename)")
            return False
        
        # Force if explicitly requested
        if args.force_folder_rename:
            print("Folder renaming forced by user request (--force-folder-rename)")
            return True
        
        # Check if input CSV exists
        if not os.path.exists(folder_rename_config["input_csv"]):
            print("Input CSV not found. Skipping folder rename step.")
            return False
        
        # Check if already completed (re-renaming prevention)
        if os.path.exists(folder_rename_config["output_csv"]):
            # Check if input CSV is newer than output CSV
            input_mtime = os.path.getmtime(folder_rename_config["input_csv"])
            output_mtime = os.path.getmtime(folder_rename_config["output_csv"])
            
            if input_mtime <= output_mtime:
                # Check for already-renamed folders to prevent re-renaming
                if detect_already_renamed_folders(extractor_config["output_folder"]):
                    print("Folders appear to already be renamed. Skipping to prevent re-renaming.")
                    print("Use --force-folder-rename to override this safety check.")
                    return False
                else:
                    print("Output CSV exists and is current, but folders not renamed. Proceeding.")
                    return True
            else:
                print("Input CSV is newer than output CSV. Folder renaming needed.")
                return True
        
        # Default: run if output doesn't exist
        return True

    def detect_already_renamed_folders(doc_files_path):
        """Detect if folders have already been renamed using standardized naming."""
        if not os.path.exists(doc_files_path):
            return False
        
        renamed_pattern = re.compile(r'^\d{4}\s+\d{2}\s+\d{2}\s+.+')  # YYYY MM DD pattern
        total_folders = 0
        renamed_folders = 0
        
        for item in os.listdir(doc_files_path):
            item_path = os.path.join(doc_files_path, item)
            if os.path.isdir(item_path):
                total_folders += 1
                if renamed_pattern.match(item):
                    renamed_folders += 1
        
        # If more than 70% of folders follow standardized naming, assume already renamed
        if total_folders > 0:
            rename_percentage = renamed_folders / total_folders
            return rename_percentage > 0.7
        
        return False

    def get_folder_rename_command(args, folder_rename_config, extractor_config):
        """Build folder rename command based on arguments."""
        cmd = [
            "python", folder_rename_config["script"],
            "--csv", folder_rename_config["input_csv"],
            "--out", folder_rename_config["output_csv"],
            "--doc-files-path", extractor_config["output_folder"]
        ]
        
        # Add rename confirmation handling
        if args.rename_confirmation == "auto":
            cmd.extend(["--auto-confirm"])
        elif args.rename_confirmation == "skip":
            # Don't add --rename-folders flag, just generate CSV
            pass
        else:  # prompt
            cmd.extend(["--rename-folders"])
        
        return cmd

    # Apply the new logic
    run_folder_rename = should_run_folder_rename(args, folder_rename_config)

    if run_folder_rename:
        print("Running folder rename script...")
        try:
            cmd = get_folder_rename_command(args, folder_rename_config, extractor_config)
            result5 = subprocess.run(cmd, timeout=folder_rename_config["timeout"])
            
            if result5.returncode != 0:
                print("Error in folder rename script:")
                print(result5.stderr)
                if not args.force_folder_rename:
                    sys.exit(1)
                else:
                    print("Continuing despite error due to --force-folder-rename")
            else:
                print("Folder rename script finished.")
        except subprocess.TimeoutExpired:
            print("Folder rename script timed out.")
            if not args.force_folder_rename:
                sys.exit(1)
            else:
                print("Continuing despite timeout due to --force-folder-rename")
    else:
        print("Folder rename step skipped.")



    # ---- OCR Enhancement Step (Optional/Future) ----
    if ocr_enhancer_config.get("enabled", False):
        print("Running OCR enhancement (experimental)...")
        try:
            result_ocr = subprocess.run(
                ["python", ocr_enhancer_config["script"],
                 "--input-dir", extractor_config["output_folder"],
                 "--output-dir", os.path.join(extractor_config["output_folder"], "ocr_enhanced"),
                 "--language", ocr_enhancer_config["language"]],
                timeout=ocr_enhancer_config["timeout"]
            )
            if result_ocr.returncode == 0:
                print("OCR enhancement completed.")
            else:
                print("OCR enhancement failed, continuing with standard processing.")
        except subprocess.TimeoutExpired:
            print("OCR enhancement timed out, continuing with standard processing.")
    else:
        print("OCR enhancement disabled. Enable in config to use PaddleOCR features.")

    # ---- Document/Chunk ID System Information ----
    print("\n=== Document Processing with ID System ===")
    print("Format: document_ID (4-digit) + chunk_ID (3-digit)")
    print("Example: Document 0054, Chunk 014 → File: 0054_014.txt")
    print("ID mappings stored in: document_id_mapping.json")
    print()

    # ---- Chunking Step ----
    # Separate documents with TOCs from those without
    output_folder = extractor_config["output_folder"]
    toc_docs = []
    non_toc_docs = []
    
    for item in os.listdir(output_folder):
        item_path = os.path.join(output_folder, item)
        if os.path.isdir(item_path):
            metadata_dir = os.path.join(item_path, "metadata")
            if os.path.exists(metadata_dir):
                # Check for TOC files
                toc_files = [f for f in os.listdir(metadata_dir) if f.endswith('_TOC.txt')]
                if toc_files:
                    toc_docs.append(item)
                else:
                    non_toc_docs.append(item)
    
    print(f"Found {len(toc_docs)} documents with TOCs and {len(non_toc_docs)} documents without TOCs")
    
    # Process TOC documents with script 07
    if toc_docs:
        print(f"Running TOC chunker on {len(toc_docs)} documents...")
        try:
            result_toc = subprocess.run(
                ["python", toc_chunker_config["script"], 
                 "--in-root", toc_chunker_config["input_folder"],
                 "--out-root", toc_chunker_config["input_folder"],
                 "--write-chunk-files"],
                timeout=toc_chunker_config["timeout"]
            )
            if result_toc.returncode != 0:
                print("Error in TOC chunker script:")
                print(result_toc.stderr)
                sys.exit(1)
            print("TOC chunker script finished.")
        except subprocess.TimeoutExpired:
            print("TOC chunker script timed out.")
            sys.exit(1)
    else:
        print("No documents with TOCs found. Skipping TOC chunker step.")
    
    # Process non-TOC documents with script 08
    if non_toc_docs:
        print(f"Running non-TOC chunker on {len(non_toc_docs)} documents...")
        
        # For non-TOC chunker, we need to process each document individually
        for doc in non_toc_docs:
            doc_path = os.path.join(output_folder, doc)
            text_dir = os.path.join(doc_path, "text_pages")
            metadata_dir = os.path.join(doc_path, "metadata")
            output_dir = os.path.join(doc_path, "chunks")
            
            # Find the classification CSV file
            csv_files = [f for f in os.listdir(metadata_dir) if f.endswith('_classification.csv')]
            if not csv_files:
                print(f"Warning: No classification CSV found for {doc}, skipping...")
                continue
            csv_path = os.path.join(metadata_dir, csv_files[0])
            
            # Find the caption file
            caption_files = [f for f in os.listdir(metadata_dir) if f.endswith('_caption.txt')]
            if not caption_files:
                print(f"Warning: No caption file found for {doc}, skipping...")
                continue
            caption_path = os.path.join(metadata_dir, caption_files[0])
            
            # Check if chunking already completed
            if os.path.exists(output_dir) and os.listdir(output_dir):
                print(f"Chunks already exist for {doc}, skipping...")
                continue
            
            print(f"Processing {doc}...")
            try:
                # We'll need to modify the non-TOC chunker to be callable programmatically
                # For now, let's create a temporary script that calls the chunker with these params
                temp_script_content = f'''
import sys
import os
import importlib.util
sys.path.insert(0, r"{base_dir}")

# Load the module with special filename handling
spec = importlib.util.spec_from_file_location("chunker_module", r"{non_toc_chunker_config["script"]}")
chunker_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chunker_module)

chunker = chunker_module.LegalDocumentChunker(max_tokens=800, min_tokens=100)
chunks = chunker.process_directory(
    text_dir=r"{text_dir}",
    csv_path=r"{csv_path}",
    caption_path=r"{caption_path}",
    output_dir=r"{output_dir}"
)
print(f"Created {{len(chunks)}} chunks for {doc}")
'''
                temp_script_path = os.path.join(base_dir, "temp_chunk_doc.py")
                with open(temp_script_path, 'w') as f:
                    f.write(temp_script_content)
                
                result_non_toc = subprocess.run(
                    ["python", temp_script_path],
                    timeout=300  # 5 minutes per document
                )
                
                # Clean up temp script
                if os.path.exists(temp_script_path):
                    os.remove(temp_script_path)
                
                if result_non_toc.returncode != 0:
                    print(f"Error processing {doc} with non-TOC chunker")
                    continue
                    
            except subprocess.TimeoutExpired:
                print(f"Non-TOC chunker timed out on document: {doc}")
                continue
            except Exception as e:
                print(f"Error processing {doc}: {e}")
                continue
        
        print("Non-TOC chunker processing completed.")
    else:
        print("No documents without TOCs found. Skipping non-TOC chunker step.")

    print("All pipeline steps completed successfully!")

if __name__ == '__main__':
    main()