import os
import re
import glob

def fix_toc_headers(file_path):
    """
    Remove 'TABLE OF CONTENTS' header and promote all other headers one level up.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Split content into lines
        lines = content.split('\n')
        fixed_lines = []
        
        for line in lines:
            if not line.strip():
                fixed_lines.append(line)
                continue
                
            if line.startswith('#'):
                header_text = line.lstrip('#').strip().upper()
                
                # Skip TABLE OF CONTENTS line entirely
                if header_text == "TABLE OF CONTENTS":
                    continue
                
                # Count the number of # symbols
                hash_count = len(line) - len(line.lstrip('#'))
                
                # Promote header by removing one #
                if hash_count > 1:
                    new_line = '#' * (hash_count - 1) + line[hash_count:]
                    fixed_lines.append(new_line)
                else:
                    # Already at h1 level, keep as h1
                    fixed_lines.append(line)
            else:
                # Non-header lines remain unchanged
                fixed_lines.append(line)
        
        # Join lines back together
        fixed_content = '\n'.join(fixed_lines)
        
        # Write back to file
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(fixed_content)
        
        print(f"Fixed: {file_path}")
        return True
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def find_and_fix_toc_files(base_directory):
    """
    Find all TOC files matching the pattern and fix them.
    """
    # Pattern to match page_###_TOC.txt files
    pattern = os.path.join(base_directory, "**", "page_*_TOC.txt")
    
    # Find all matching files recursively
    toc_files = glob.glob(pattern, recursive=True)
    
    if not toc_files:
        print(f"No TOC files found matching pattern in {base_directory}")
        return
    
    print(f"Found {len(toc_files)} TOC files to process:")
    
    success_count = 0
    for file_path in toc_files:
        print(f"Processing: {file_path}")
        if fix_toc_headers(file_path):
            success_count += 1
    
    print(f"\nCompleted: {success_count}/{len(toc_files)} files processed successfully")

# Main execution
if __name__ == "__main__":
    import sys
    
    # Use command line argument if provided, otherwise use default
    if len(sys.argv) > 1:
        base_dir = sys.argv[1]
    else:
        base_dir = (r"C:\PDF_raw\doc_files")
    
    # Verify directory exists
    if not os.path.exists(base_dir):
        print(f"Directory not found: {base_dir}")
        print("Please update the base_dir variable with the correct path.")
    else:
        print(f"Starting TOC header fix in: {base_dir}")
        find_and_fix_toc_files(base_dir)
        print("Processing complete!")
