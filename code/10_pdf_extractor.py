import os
import re
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image
import io
import concurrent.futures

def remove_line_numbers(text):
    """
    Remove line numbers from legal pleading text.
    Handles various patterns where line numbers (1-28) appear.
    """
    # Split into lines for processing
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Skip lines that are only line numbers (possibly with spaces)
        if re.match(r'^\s*\d{1,2}\s*$', line):
            continue
            
        # Remove line numbers at the beginning of lines
        # Pattern: start of line, optional spaces, 1-2 digits, optional spaces
        line = re.sub(r'^\s*\d{1,2}\s+', '', line)
        
        # Remove isolated line numbers in the middle of text
        # Look for patterns like "text 5 more text" where 5 is likely a line number
        # This is more conservative to avoid removing legitimate numbers
        line = re.sub(r'\s+\d{1,2}\s+(?=[A-Z])', ' ', line)
        
        # Remove line numbers that appear after periods/paragraph breaks
        line = re.sub(r'\.\s*\d{1,2}\s+', '. ', line)
        
        # Clean up multiple spaces
        line = re.sub(r'\s+', ' ', line)
        
        # Only add non-empty lines
        if line.strip():
            cleaned_lines.append(line.strip())
    
    return '\n'.join(cleaned_lines)

def extract_pdf_pages(pdf_path, output_base_dir):
    """
    Extract each page of a PDF as both PNG image and cleaned text.
    """
    # Get PDF filename without extension for folder name
    pdf_name = Path(pdf_path).stem
    
    # Create output directories
    pdf_output_dir = Path(output_base_dir) / pdf_name
    png_dir = pdf_output_dir / "PNG"
    text_dir = pdf_output_dir / "text_pages"
    
    png_dir.mkdir(parents=True, exist_ok=True)
    text_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Processing: {pdf_name}", flush=True)
    
    try:
        # Open PDF
        doc = fitz.open(pdf_path)
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Generate page filename (0001, 0002, etc.)
            page_filename = f"page_{page_num + 1:04d}"
            
            # Extract and save image
            try:
                # Render page as image (300 DPI for good quality)
                mat = fitz.Matrix(300/72, 300/72)  # 300 DPI scaling
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                
                # Save PNG
                png_path = png_dir / f"{page_filename}.png"
                with open(png_path, "wb") as f:
                    f.write(img_data)
                
                print(f"  Saved image: {page_filename}.png", flush=True)
                
            except Exception as e:
                print(f"  Error saving image for page {page_num + 1}: {e}")
            
            # Extract and clean text
            try:
                # Extract text
                text = page.get_text()
                
                # Remove line numbers
                cleaned_text = remove_line_numbers(text)
                
                # Save text file
                text_path = text_dir / f"{page_filename}.txt"
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(cleaned_text)
                
                print(f"  Saved text: {page_filename}.txt", flush=True)
                
            except Exception as e:
                print(f"  Error saving text for page {page_num + 1}: {e}")
        
        doc.close()
        print(f"Completed: {pdf_name} ({len(doc)} pages)", flush=True)
        
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}", flush=True)

def process_pdf_folder(input_folder, output_folder):
    """
    Process all PDFs in the input folder.
    """
    input_path = Path(input_folder)
    output_path = Path(output_folder)
    print(f"Processing PDF folder: {input_folder}", flush=True)
    
    if not input_path.exists():
        print(f"Input folder does not exist: {input_folder}")
        return
    
    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Find all PDF files
    pdf_files = list(input_path.glob("*.pdf"))
    
    if not pdf_files:
        print(f"No PDF files found in: {input_folder}")
        return
    
    print(f"Found {len(pdf_files)} PDF files", flush=True)
    print("-" * 50, flush=True)
    
    for pdf_file in pdf_files:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(extract_pdf_pages, pdf_file, output_path)
            try:
                future.result(timeout=300)
            except concurrent.futures.TimeoutError:
                print(f"Timeout processing {pdf_file}", flush=True)
        print("-" * 50, flush=True)
    
    print("All PDFs processed!", flush=True)

if __name__ == "__main__":
    import os
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    INPUT_FOLDER = os.path.join(BASE_DIR, "PDFs")
    OUTPUT_FOLDER = os.path.join(BASE_DIR, "doc_files")
    process_pdf_folder(INPUT_FOLDER, OUTPUT_FOLDER)
