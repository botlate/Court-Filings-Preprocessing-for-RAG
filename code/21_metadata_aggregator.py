#
# This script scans subdirectories for caption files, extracts data,
# and compiles it into a single CSV file. It will search recursively
# within each folder to find the caption file.
#
# To use:
# 1. Save this file as a Python script (e.g., `create_csv.py`).
# 2. Place it in the parent directory that contains all the folders you want to process.
#    - Example structure:
#      - /YourMainFolder/
#        - create_csv.py  <-- SCRIPT GOES HERE
#        - /Folder_A/
#          - /some_subfolder/
#            - page_0001_caption.txt
#        - /Folder_B/
#          - page_0025_caption.txt
# 3. Run the script from your terminal: python create_csv.py
# 4. A file named `output.csv` will be created in /YourMainFolder/.
#

import os
import csv
import re
import json
from datetime import datetime
from dateutil import parser as date_parser
import calendar

def parse_flexible_date(date_string):
    """
    Attempts to parse a date string using multiple strategies.
    Returns the date in YYYY-MM-DD format or the original string if parsing fails.
    
    Args:
        date_string (str): The date string to parse.
    
    Returns:
        str: Normalized date in YYYY-MM-DD format or original string if parsing fails.
    """
    if not date_string or date_string in ['N/A', 'Not available', 'None', 'null', '']:
        return 'N/A'
    
    # Clean up the string
    date_string = date_string.strip()
    
    # Remove common suffixes and ordinals (1st, 2nd, 3rd, 4th, etc.)
    date_string = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_string)
    
    # List of date formats to try explicitly (most common in legal documents)
    date_formats = [
        '%m/%d/%Y',           # 12/31/2023
        '%m-%d-%Y',           # 12-31-2023
        '%m.%d.%Y',           # 12.31.2023
        '%m/%d/%y',           # 12/31/23
        '%m-%d-%y',           # 12-31-23
        '%Y-%m-%d',           # 2023-12-31 (ISO format)
        '%Y/%m/%d',           # 2023/12/31
        '%d/%m/%Y',           # 31/12/2023 (European)
        '%d-%m-%Y',           # 31-12-2023
        '%d.%m.%Y',           # 31.12.2023
        '%B %d, %Y',          # December 31, 2023
        '%b %d, %Y',          # Dec 31, 2023
        '%B %d %Y',           # December 31 2023
        '%b %d %Y',           # Dec 31 2023
        '%d %B %Y',           # 31 December 2023
        '%d %b %Y',           # 31 Dec 2023
        '%d %B, %Y',          # 31 December, 2023
        '%d %b, %Y',          # 31 Dec, 2023
        '%Y%m%d',             # 20231231
        '%m/%Y',              # 12/2023 (month/year only)
        '%B %Y',              # December 2023
        '%b %Y',              # Dec 2023
        '%m-%Y',              # 12-2023
        '%Y-%m',              # 2023-12
        '%d-%b-%Y',           # 31-Dec-2023
        '%d/%b/%Y',           # 31/Dec/2023
        '%d-%b-%y',           # 31-Dec-23
        '%d/%b/%y',           # 31/Dec/23
        '%b. %d, %Y',         # Dec. 31, 2023
        '%B. %d, %Y',         # December. 31, 2023
    ]
    
    # Try each explicit format
    for fmt in date_formats:
        try:
            date_obj = datetime.strptime(date_string, fmt)
            # If only month/year, default to first day of month
            if fmt in ['%m/%Y', '%B %Y', '%b %Y', '%m-%Y', '%Y-%m']:
                return date_obj.strftime('%Y-%m-01')
            return date_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            continue
    
    # Try dateutil parser as a fallback (very flexible but sometimes too permissive)
    try:
        # First try with dayfirst=False (American format)
        date_obj = date_parser.parse(date_string, dayfirst=False, fuzzy=True)
        return date_obj.strftime('%Y-%m-%d')
    except (ValueError, TypeError, date_parser.ParserError):
        pass
    
    # Try with dayfirst=True (European format)
    try:
        date_obj = date_parser.parse(date_string, dayfirst=True, fuzzy=True)
        return date_obj.strftime('%Y-%m-%d')
    except (ValueError, TypeError, date_parser.ParserError):
        pass
    
    # Handle special cases with regex
    # Format: "the 31st day of December, 2023" or similar
    pattern1 = re.search(r'(\d{1,2})\w*\s+day\s+of\s+(\w+),?\s+(\d{4})', date_string, re.IGNORECASE)
    if pattern1:
        try:
            day = int(pattern1.group(1))
            month_name = pattern1.group(2)
            year = int(pattern1.group(3))
            # Convert month name to number
            month_num = None
            for i, month in enumerate(calendar.month_name[1:], 1):
                if month.lower().startswith(month_name.lower()[:3]):
                    month_num = i
                    break
            if month_num:
                date_obj = datetime(year, month_num, day)
                return date_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    
    # Format: "December 31st, 2023" with ordinals
    pattern2 = re.search(r'(\w+)\s+(\d{1,2})\w*,?\s+(\d{4})', date_string, re.IGNORECASE)
    if pattern2:
        try:
            month_name = pattern2.group(1)
            day = int(pattern2.group(2))
            year = int(pattern2.group(3))
            # Convert month name to number
            month_num = None
            for i, month in enumerate(calendar.month_name[1:], 1):
                if month.lower().startswith(month_name.lower()[:3]):
                    month_num = i
                    break
            if month_num:
                date_obj = datetime(year, month_num, day)
                return date_obj.strftime('%Y-%m-%d')
        except (ValueError, TypeError):
            pass
    
    # If all parsing attempts fail, return the original string
    print(f"    -> INFO: Could not parse date '{date_string}'. Using original value.")
    return date_string

def extract_value_regex(key_name, text):
    """
    Uses a flexible regex to find a value for a given key. This is a fallback
    for when the file content is not valid JSON.
    
    This pattern handles:
    - Values that are in double quotes.
    - Multi-line values within double quotes.
    - Unquoted values (e.g., "key": Not available).
    
    Args:
        key_name (str): The key to search for (e.g., "document_title").
        text (str): The text content of the file.

    Returns:
        str: The extracted value, or 'N/A' if not found.
    """
    # This pattern looks for the key in quotes, a colon, and then captures the value.
    # The value can be:
    # 1. "(.*?)"     : A non-greedy match for anything inside double quotes.
    # 2. ([^,}\n]+) : A sequence of characters that are not a comma, closing brace, or newline.
    # re.DOTALL allows '.' to match newlines, crucial for multi-line values in quotes.
    pattern = re.compile(
        f'"{key_name}"'       # Match the key, e.g., "document_title"
        r'\s*:\s*'           # Match the colon with optional whitespace
        r'(?:"(.*?)"|([^,}\n]+))', # Capture group 1 (quoted) or 2 (unquoted)
        re.DOTALL
    )
    match = re.search(pattern, text)
    if match:
        # The result will be in group 1 (quoted) or group 2 (unquoted).
        # One of them will be None, so we take the one that found a match.
        value = match.group(1) if match.group(1) is not None else match.group(2)
        if value:
            # Clean up the extracted value by stripping whitespace.
            return value.strip()
    return 'N/A'

def simplify_filing_party(filing_party):
    """
    Simplifies filing party to 1-2 words (defendant, plaintiff, petitioner, appellant, etc.)
    """
    if not filing_party or filing_party == 'N/A':
        return 'N/A'
    
    filing_party_lower = filing_party.lower()
    
    # Check for specific party types
    if 'defendant' in filing_party_lower:
        # If multiple defendants, try to extract specific name
        if 'defendants' in filing_party_lower or 'defendant ' in filing_party_lower:
            # Look for pattern like "defendant smith" or "defendants including smith"
            words = filing_party.split()
            for i, word in enumerate(words):
                if word.lower() == 'defendant' and i + 1 < len(words):
                    next_word = words[i + 1]
                    if next_word.lower() not in ['and', 'or', 'including', 'et', 'al']:
                        return f"defendant {next_word.lower()}"
        return 'defendant'
    elif 'plaintiff' in filing_party_lower:
        return 'plaintiff'
    elif 'petitioner' in filing_party_lower:
        return 'petitioner'
    elif 'appellant' in filing_party_lower:
        return 'appellant'
    elif 'respondent' in filing_party_lower:
        return 'respondent'
    elif 'applicant' in filing_party_lower:
        return 'applicant'
    else:
        # If no standard party type found, return first 1-2 words
        words = filing_party.split()
        if len(words) >= 2:
            return f"{words[0].lower()} {words[1].lower()}"
        elif len(words) == 1:
            return words[0].lower()
        else:
            return 'N/A'

def create_summary_csv(target_directory=None):
    """
    Scans subdirectories for caption files, extracts specified data,
    and writes it to a CSV file in the target directory.
    """
    current_directory = target_directory if target_directory else os.getcwd()
    print(f"Scanning for folders in: {current_directory}\n")

    output_csv_filename = 'output.csv'
    csv_rows = [['FolderName', 'FilingDate', 'DocumentTitle', 'FilingParty']]

    for item_name in os.listdir(current_directory):
        item_path = os.path.join(current_directory, item_name)

        if os.path.isdir(item_path):
            folder_name = item_name
            print(f"Processing folder: '{folder_name}'...")

            caption_file_path = None
            caption_file_pattern = re.compile(r'page_00\d{2}_caption\.txt')

            for root, dirs, files in os.walk(item_path):
                for filename in files:
                    if caption_file_pattern.match(filename):
                        caption_file_path = os.path.join(root, filename)
                        break
                if caption_file_path:
                    break

            if caption_file_path:
                try:
                    with open(caption_file_path, 'r', encoding='utf-8') as f:
                        file_content = f.read()

                    # Initialize variables
                    document_title, filing_date, filing_party = 'N/A', 'N/A', 'N/A'

                    # --- ROBUST PARSING LOGIC ---
                    # 1. First, try to parse the file as a whole JSON object.
                    try:
                        # Strip whitespace/newlines from start/end of file
                        data = json.loads(file_content.strip())
                        document_title = data.get('document_title', 'N/A')
                        filing_date = data.get('filing_date', 'N/A')
                        filing_party = data.get('filing_party', 'N/A')
                    # 2. If JSON parsing fails, fall back to the robust regex extractor.
                    except json.JSONDecodeError:
                        print(f"  -> Info: Not valid JSON. Falling back to regex extraction.")
                        document_title = extract_value_regex('document_title', file_content)
                        filing_date = extract_value_regex('filing_date', file_content)
                        filing_party = extract_value_regex('filing_party', file_content)

                    # --- Date Normalization with Enhanced Parser ---
                    normalized_filing_date = parse_flexible_date(filing_date)
                    
                    # --- Simplify Filing Party ---
                    simplified_filing_party = simplify_filing_party(filing_party)

                    csv_rows.append([folder_name, normalized_filing_date, document_title, simplified_filing_party])
                    print(f"  -> Success: Extracted data from '{os.path.basename(caption_file_path)}'.")

                except Exception as e:
                    print(f"  -> ERROR: An unexpected error occurred while processing '{os.path.basename(caption_file_path)}': {e}")
            else:
                print(f"  -> WARNING: No caption file found in this folder.")

    output_csv_path = os.path.join(current_directory, output_csv_filename)
    try:
        with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerows(csv_rows)
        print(f"\n✅ Successfully created CSV file: {output_csv_path}")
    except IOError as e:
        print(f"\n❌ ERROR: Could not write to CSV file. Please check permissions. Error: {e}")

if __name__ == "__main__":
    import sys
    
    # Use command line argument if provided, otherwise use current directory
    target_dir = sys.argv[1] if len(sys.argv) > 1 else None
    create_summary_csv(target_dir)