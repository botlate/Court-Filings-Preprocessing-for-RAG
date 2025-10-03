import os
import sys
import csv
import logging
import base64
from pathlib import Path
from typing import List, Dict, Optional
from PIL import Image
import openai

# Import all prompts from separate file
from prompts import (
    CLASSIFICATION_PROMPT,
    FORM_TYPE_PROMPT,
    EXHIBIT_LABEL_PROMPT,
    EXHIBIT_TITLE_PROMPT,
    EXHIBIT_CONTINUATION_PROMPT,
    TOC_EXTRACTION_PROMPT,
    CAPTION_EXTRACTION_PROMPT
)

# Note: Requires: pip install openai pillow

# Instead of using a hardcoded base directory, use the first command-line argument if provided.
if len(sys.argv) > 1:
    BASE_DIR = Path(sys.argv[1])
else:
    BASE_DIR = Path(__file__).parent / "doc_files"

# OpenAI API Configuration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("Please set the OPENAI_API_KEY environment variable")

MODEL_NAME = "gpt-5-mini"

# Document classification categories
CATEGORIES = [
    "Form",
    "Pleading first page",
    "Pleading table of contents",
    "Pleading table of authorities",
    "Exhibit cover page",
    "Proof of service page",
    "Pleading body",
    "Proof of service"
]

# Common form types
COMMON_FORMS = ["SUM-100", "POS-010", "MC-025", "FL-100", "FL-110", "FL-115"]

# === SETUP ===
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configure OpenAI
openai.api_key = OPENAI_API_KEY

# === UTILITY FUNCTIONS ===
def encode_image_to_base64(image_path: Path) -> str:
    """Convert image to base64 string for OpenAI API."""
    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode == 'RGBA':
                rgb_img = Image.new('RGB', img.size, (255, 255, 255))
                rgb_img.paste(img, mask=img.split()[3])
                img = rgb_img
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize if image is too large (OpenAI has size limits)
            max_size = 2048
            if img.width > max_size or img.height > max_size:
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # Save to bytes and encode to base64
            import io
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=85)
            img_bytes = buffered.getvalue()
            return base64.b64encode(img_bytes).decode('utf-8')
    except Exception as e:
        logging.error(f"Error encoding image {image_path}: {str(e)}")
        return None

def call_vision_llm(image_path: Path, prompt: str, max_completion_tokens: int = 1500, retry_count: int = 3) -> Optional[str]:
    """Call OpenAI vision API with retry logic. Returns None if all retries fail."""
    for attempt in range(retry_count):
        try:
            # Encode image to base64
            base64_image = encode_image_to_base64(image_path)
            if base64_image is None:
                logging.error(f"Failed to encode image {image_path} - Attempt {attempt + 1}/{retry_count}")
                if attempt < retry_count - 1:
                    continue
                return None
            
            # Prepare the message for OpenAI
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ]
            
            # Make the API call
            response = openai.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                max_completion_tokens=max_completion_tokens,
            )
            
            # Extract text from response
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
            else:
                logging.error(f"No text in OpenAI response for {image_path} - Attempt {attempt + 1}/{retry_count}")
                if attempt < retry_count - 2:
                    continue
                return None
            
        except Exception as e:
            logging.error(f"Error calling OpenAI vision API for {image_path}: {str(e)} - Attempt {attempt + 1}/{retry_count}")
            if attempt < retry_count - 2:
                continue
            return None
        
        logging.info(f"API Response status: {response}")
        logging.info(f"Response choices length: {len(response.choices) if response.choices else 0}")
        if response.choices:
            logging.info(f"Message content exists: {response.choices[0].message.content is not None}")
        
    return None

def get_image_files(directory: Path) -> List[Path]:
    """Get all PNG files from the directory in sorted order."""
    image_extensions = ['.png', '.jpg', '.jpeg', '.tif', '.tiff']
    files = []
    for ext in image_extensions:
        files.extend(directory.glob(f"*{ext}"))
    return sorted(files, key=lambda x: x.stem)

# Footnote detection functions removed - not needed for core pipeline functionality

def classify_page(image_path: Path) -> Optional[Dict[str, str]]:
    """Classify a single page and return classification details. Returns None if classification fails."""
    classification = call_vision_llm(image_path, CLASSIFICATION_PROMPT)
    
    if classification is None:
        logging.error(f"Failed to classify {image_path.name} after retries. Skipping.")
        return None
    
    # Normalize classification to match expected categories
    classification = classification.strip()
    if classification not in CATEGORIES:
        logging.warning(f"Unexpected classification '{classification}' for {image_path.name}. Defaulting to 'Pleading body'")
        classification = "Pleading body"
    
    result = {
        "filename": image_path.name,
        "category": classification,
        "subtype": "",
        "exhibit_label": "",
        "exhibit_title": "",
        "notes": ""
    }
    
    # Handle form classification
    if classification == "Form":
        form_type = call_vision_llm(image_path, FORM_TYPE_PROMPT.format(", ".join(COMMON_FORMS)), max_completion_tokens=2000)
        result["subtype"] = form_type if form_type else "Unknown"
        logging.info(f"  Form type: {result['subtype']}")
    
    # Handle exhibit cover page
    elif classification == "Exhibit cover page":
        exhibit_label = call_vision_llm(image_path, EXHIBIT_LABEL_PROMPT)
        result["exhibit_label"] = exhibit_label if exhibit_label else "Unknown"
        logging.info(f"  Exhibit label: {result['exhibit_label']}")
    
    return result

def process_exhibit_continuation(
    images: List[Path], 
    start_index: int, 
    exhibit_label: str,
    csv_data: List[Dict]
) -> int:
    """
    Process pages following an exhibit cover to determine continuation.
    Returns the index of the next page to process in main loop.
    """
    current_index = start_index
    is_first_page = True  # Track if this is the first page after exhibit cover
    
    while current_index < len(images):
        image_path = images[current_index]
        
        # If this is the first page after exhibit cover, get title/description
        if is_first_page:
            exhibit_title = call_vision_llm(image_path, EXHIBIT_TITLE_PROMPT)
            if exhibit_title:
                logging.info(f"  Exhibit {exhibit_label} title: {exhibit_title}")
            else:
                exhibit_title = ""
            is_first_page = False
        else:
            exhibit_title = ""
        
        prompt = EXHIBIT_CONTINUATION_PROMPT.format(exhibit_label, exhibit_label)
        response = call_vision_llm(image_path, prompt)
        
        if response is None:
            # If we can't determine, assume it's a continuation
            response = "continuation"
            logging.warning(f"  Could not determine continuation status for {image_path.name}. Assuming continuation.")
        
        logging.info(f"  Page {image_path.name}: {response}")
        
        if response.lower() == "continuation":
            csv_data.append({
                "filename": image_path.name,
                "category": "Exhibit content",
                "subtype": "",
                "exhibit_label": exhibit_label,
                "exhibit_title": exhibit_title,  # Only filled for first page
                "notes": f"Part of Exhibit {exhibit_label}"
            })
            current_index += 1
            
        elif response.lower() == "new exhibit":
            # This is a new exhibit cover - classify it properly
            result = classify_page(image_path)
            if result and result["category"] == "Exhibit cover page":
                csv_data.append(result)
                # Continue with new exhibit label
                exhibit_label = result["exhibit_label"]
                current_index += 1
                is_first_page = True  # Reset for new exhibit
            elif result is None:
                # Classification failed - use last entry from csv_data
                if csv_data:
                    last_entry = csv_data[-1].copy()
                    last_entry['filename'] = image_path.name
                    last_entry['notes'] = f"Classification failed - using previous: {last_entry['category']}"
                    csv_data.append(last_entry)
                else:
                    # No previous entry, default to Exhibit content
                    csv_data.append({
                        "filename": image_path.name,
                        "category": "Exhibit content",
                        "subtype": "",
                        "exhibit_label": exhibit_label,
                        "exhibit_title": "",
                        "notes": f"Classification failed - defaulted to Exhibit content"
                    })
                current_index += 1
            else:
                # If it's not actually an exhibit cover, it might still be exhibit content
                logging.info(f"  Page marked as new exhibit but not classified as exhibit cover. Re-checking...")
                csv_data.append({
                    "filename": image_path.name,
                    "category": "Exhibit content",
                    "subtype": "",
                    "exhibit_label": exhibit_label,
                    "exhibit_title": "",
                    "notes": f"Part of Exhibit {exhibit_label} (verified after new exhibit check)"
                })
                current_index += 1
        else:
            # Break if we get an unexpected response
            break
        
    return current_index

def reclassify_last_pages(images: List[Path], csv_data: List[Dict], last_n_pages: int = 2):
    """
    Re-classify the last N pages of the document using the initial classification prompt.
    This helps catch any misclassifications at the end of the document.
    """
    if len(images) < last_n_pages:
        return
        
    logging.info(f"\nRe-classifying last {last_n_pages} pages...")
    # Determine range for reclassification
    start_index = max(0, len(images) - last_n_pages)
    
    for i in range(start_index, len(images)):
        image_path = images[i]
        logging.info(f"  Re-classifying {image_path.name}")
        # Get new classification
        result = classify_page(image_path)
        
        if result is None:
            logging.warning(f"    Failed to reclassify {image_path.name}. Keeping original classification: {csv_data[i]['category']}")
            continue
        
        # Compare with original classification
        if csv_data[i]["category"] != result["category"]:
            logging.info(f"    Changed from '{csv_data[i]['category']}' to '{result['category']}'")
            # Update the CSV entry with new classification but preserve exhibit title if it exists
            old_exhibit_title = csv_data[i].get("exhibit_title", "")
            csv_data[i] = result
            if old_exhibit_title and result["category"] == "Exhibit content":
                csv_data[i]["exhibit_title"] = old_exhibit_title
        else:
            logging.info(f"    Classification unchanged: {result['category']}")

def export_footnotes_to_json(footnotes_data: Dict[str, List[Dict]], metadata_dir: Path, doc_id: str):
    """Export footnote data to JSON files in a footnotes folder."""
    if not footnotes_data:
        logging.info(f"No footnotes found in document {doc_id}")
        return
    
    # Create footnotes directory
    footnotes_dir = metadata_dir / "footnotes"
    footnotes_dir.mkdir(exist_ok=True)
    
    footnotes_count = 0
    for page_name, footnotes_list in footnotes_data.items():
        if footnotes_list:
            # Extract page number from filename (e.g., "0003.png" -> "0003")
            page_num = page_name.split('.')[0]
            json_filename = f"page_{page_num}_footnotes.json"
            json_path = footnotes_dir / json_filename
            
            # Format footnotes for export
            export_footnotes = []
            for fn in footnotes_list:
                export_footnotes.append({
                    "footnote_number": fn.get("marker", ""),
                    "context_phrase": fn.get("context", ""),
                    "footnote_text": fn.get("text", "")
                })
            
            # Write JSON file
            import json
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(export_footnotes, f, indent=2, ensure_ascii=False)
            
            footnotes_count += len(export_footnotes)
            logging.info(f"  → Exported {len(export_footnotes)} footnotes to {json_filename}")
    
    logging.info(f"Total footnotes exported for {doc_id}: {footnotes_count}")

def process_document(png_dir: Path, metadata_dir: Path):
    """Process a single document's PNG directory and write metadata to the metadata directory."""
    images = get_image_files(png_dir)
    if not images:
        logging.warning(f"No image files found in {png_dir}")
        return

    # Get document ID from parent folder name
    doc_id = png_dir.parent.name
    logging.info(f"\n===== Processing document: {doc_id} - {len(images)} pages =====")
    
    csv_rows = []
    last_successful_row = None  # Track the last successful classification
    i = 0
    while i < len(images):
        img = images[i]
        logging.info(f"\n===== Processing page {i+1}/{len(images)}: {img.name}")
        
        row = classify_page(img)
        if row is None:
            # If classification fails, use the last successful classification
            if last_successful_row is not None:
                # Create a copy of the last successful row with updated filename
                row = last_successful_row.copy()
                row['filename'] = img.name
                row['notes'] = f"Classification failed - using previous: {row['category']}"
                logging.warning(f"Classification failed for {img.name}. Using previous classification: {row['category']}")
            else:
                # If no previous classification exists, default to "Pleading body"
                row = {
                    "filename": img.name,
                    "category": "Pleading body",
                    "subtype": "",
                    "exhibit_label": "",
                    "exhibit_title": "",
                    "notes": "Classification failed - defaulted to Pleading body"
                }
                logging.warning(f"Classification failed for {img.name}. No previous classification available. Defaulting to 'Pleading body'")
        else:
            # Update last successful classification
            last_successful_row = row.copy()
            
        logging.info(f"Classification: {row['category']}")
        
        # --- TOC extraction ---
        if row['category'] == 'Pleading table of contents':
            toc = call_vision_llm(img, TOC_EXTRACTION_PROMPT, max_completion_tokens=3000)
            if toc:
                toc_file = metadata_dir / f"{img.stem}_TOC.txt"
                toc_file.write_text(toc, encoding='utf-8')
                row['notes'] = str(toc_file.name)  # Store just filename, not full path
                logging.info(f"  TOC extracted → {toc_file.name}")
        
        # --- Caption extraction ---
        elif row['category'] == 'Pleading first page':
            cap = call_vision_llm(img, CAPTION_EXTRACTION_PROMPT, max_completion_tokens=3500)
            if cap:
                cap_file = metadata_dir / f"{img.stem}_caption.txt"
                cap_file.write_text(cap, encoding='utf-8')
                row['notes'] = str(cap_file.name)  # Store just filename, not full path
                logging.info(f"  Caption details extracted → {cap_file.name}")
        
        csv_rows.append(row)
        
        # exhibit continuation logic
        if row['category'] == 'Exhibit cover page' and row['exhibit_label']:
            nxt = i + 1
            if nxt < len(images):
                logging.info(f"  Entering exhibit continuation engine for Exhibit {row['exhibit_label']}")
                i = process_exhibit_continuation(images, nxt, row['exhibit_label'], csv_rows)
            else:
                i += 1
        else:
            i += 1
    
    if len(images) > 0:
        reclassify_last_pages(images, csv_rows)
        
    csv_out = metadata_dir / f"{doc_id}_classification.csv"
    with csv_out.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['filename','category','subtype','exhibit_label','exhibit_title','notes'])
        writer.writeheader()
        writer.writerows(csv_rows)
    logging.info(f"\nFinished document {doc_id}. CSV written to {csv_out}")
    
    # Footnotes are already saved as individual TXT files during processing

def is_document_already_processed(metadata_dir: Path, doc_name: str) -> bool:
    """Check if a document has already been processed by looking for required output files."""
    if not metadata_dir.exists():
        return False
    
    # Check for CSV file
    csv_files = list(metadata_dir.glob("*.csv"))
    if not csv_files:
        return False
    
    # Check for caption file
    caption_files = list(metadata_dir.glob("*_caption.txt"))
    if not caption_files:
        return False
    
    logging.info(f"Document {doc_name} already processed - found {len(csv_files)} CSV file(s) and {len(caption_files)} caption file(s)")
    return True

def process_all_documents(base_dir: Path):
    """Process all documents in the base directory."""
    # Get all subdirectories in the base directory
    doc_dirs = [d for d in base_dir.iterdir() if d.is_dir()]
    
    if not doc_dirs:
        logging.warning(f"No document directories found in {base_dir}")
        return
    
    logging.info(f"Found {len(doc_dirs)} document directories to process")
    
    processed_count = 0
    skipped_count = 0
    
    for doc_dir in doc_dirs:
        png_dir = doc_dir / "PNG"
        
        # Check if PNG directory exists
        if not png_dir.exists():
            logging.warning(f"No PNG directory found in {doc_dir.name}, skipping...")
            skipped_count += 1
            continue
        
        # Create metadata directory at the same level as PNG
        metadata_dir = doc_dir / "metadata"
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if document is already processed
        if is_document_already_processed(metadata_dir, doc_dir.name):
            logging.info(f"Skipping already processed document: {doc_dir.name}")
            skipped_count += 1
            continue
        
        try:
            process_document(png_dir, metadata_dir)
            processed_count += 1
        except Exception as e:
            logging.error(f"Error processing document {doc_dir.name}: {str(e)}")
            skipped_count += 1
    
    logging.info(f"\n===== Processing Complete =====")
    logging.info(f"Documents processed: {processed_count}")
    logging.info(f"Documents skipped: {skipped_count}")

# === MAIN WORKFLOW ===
def main():
    logging.info("Starting document classification with OpenAI...")
    logging.info(f"Base directory: {BASE_DIR}")
    logging.info(f"Using OpenAI model: {MODEL_NAME}")
    
    if not BASE_DIR.exists():
        logging.error(f"Base directory does not exist: {BASE_DIR}")
        return
    
    process_all_documents(BASE_DIR)
    logging.info("Document classification completed.")

if __name__ == "__main__":
    main()