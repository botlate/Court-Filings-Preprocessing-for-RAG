"""
RAG Preprocessing Pipeline GUI

Tkinter GUI for the document processing pipeline with support for:
- Toggling individual pipeline steps on/off
- External OCR text import (from PaddleOCR GUI or other tools)
- Real-time log output
- Background threaded processing
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path

BASE_DIR = Path(__file__).parent
PROJECT_DIR = BASE_DIR.parent

# Default paths
DEFAULT_PDF_DIR = PROJECT_DIR / "PDFs"
DEFAULT_OUTPUT_DIR = PROJECT_DIR / "doc_files"


def get_script_path(script_id):
    """Resolve script path by ID."""
    script_map = {
        "pdf_extractor": "10_pdf_extractor.py",
        "document_classifier": "11_document_classifier.py",
        "ocr_text_importer": "12_ocr_text_importer.py",
        "toc_formatter": "20_toc_formatter.py",
        "metadata_aggregator": "21_metadata_aggregator.py",
        "toc_chunker": "30_toc_chunker.py",
        "semantic_chunker": "31_semantic_chunker.py",
    }
    if script_id in script_map:
        p = BASE_DIR / script_map[script_id]
        if p.exists():
            return str(p)
    return str(BASE_DIR / f"{script_id}.py")


class PipelineGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("RAG Preprocessing Pipeline")
        self.root.geometry("780x720")
        self.root.minsize(600, 550)

        self.processing = False
        self._build_env()
        self._create_widgets()

    def _build_env(self):
        """Build subprocess environment with PYTHONPATH."""
        self.env = os.environ.copy()
        self.env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + self.env.get("PYTHONPATH", "")

    # ------------------------------------------------------------------ UI
    def _create_widgets(self):
        # ---- Path section ----
        path_frame = ttk.LabelFrame(self.root, text="Paths", padding=10)
        path_frame.pack(fill="x", padx=10, pady=(10, 5))

        self.pdf_dir_var = tk.StringVar(value=str(DEFAULT_PDF_DIR))
        self.output_dir_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.ocr_dir_var = tk.StringVar(value="")

        self._add_path_row(path_frame, "PDF Input Folder:", self.pdf_dir_var, 0)
        self._add_path_row(path_frame, "Output Folder:", self.output_dir_var, 1)
        self._add_path_row(path_frame, "External OCR Folder (optional):", self.ocr_dir_var, 2)

        # ---- Pipeline steps ----
        steps_frame = ttk.LabelFrame(self.root, text="Pipeline Steps", padding=10)
        steps_frame.pack(fill="x", padx=10, pady=5)

        self.step_extract_png = tk.BooleanVar(value=True)
        self.step_extract_text = tk.BooleanVar(value=True)
        self.step_import_ocr = tk.BooleanVar(value=False)
        self.step_classify = tk.BooleanVar(value=True)
        self.step_toc_format = tk.BooleanVar(value=True)
        self.step_metadata = tk.BooleanVar(value=True)
        self.step_chunk = tk.BooleanVar(value=True)

        self.cb_png = ttk.Checkbutton(steps_frame, text="Extract PNGs from PDFs",
                                       variable=self.step_extract_png)
        self.cb_png.grid(row=0, column=0, sticky="w", pady=2)

        self.cb_text = ttk.Checkbutton(steps_frame, text="Extract text with PyMuPDF",
                                        variable=self.step_extract_text,
                                        command=self._on_text_toggle)
        self.cb_text.grid(row=1, column=0, sticky="w", pady=2)

        self.cb_ocr = ttk.Checkbutton(steps_frame, text="Import external OCR text",
                                       variable=self.step_import_ocr,
                                       command=self._on_ocr_toggle)
        self.cb_ocr.grid(row=2, column=0, sticky="w", pady=2)

        self.cb_classify = ttk.Checkbutton(steps_frame, text="Classify pages (OpenAI vision)",
                                            variable=self.step_classify)
        self.cb_classify.grid(row=3, column=0, sticky="w", pady=2)

        self.cb_toc = ttk.Checkbutton(steps_frame, text="Format TOC files",
                                       variable=self.step_toc_format)
        self.cb_toc.grid(row=4, column=0, sticky="w", pady=2)

        self.cb_meta = ttk.Checkbutton(steps_frame, text="Aggregate metadata (create output.csv)",
                                        variable=self.step_metadata)
        self.cb_meta.grid(row=5, column=0, sticky="w", pady=2)

        self.cb_chunk = ttk.Checkbutton(steps_frame, text="Chunk documents (TOC + semantic)",
                                         variable=self.step_chunk)
        self.cb_chunk.grid(row=6, column=0, sticky="w", pady=2)

        # ---- Run button ----
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.run_btn = ttk.Button(btn_frame, text="Run Pipeline",
                                   command=self._start_pipeline)
        self.run_btn.pack(side="left", padx=(0, 10))

        self.stop_btn = ttk.Button(btn_frame, text="Stop", state="disabled",
                                    command=self._request_stop)
        self.stop_btn.pack(side="left")

        ttk.Button(btn_frame, text="Open Output Folder",
                   command=self._open_output).pack(side="right")

        # ---- Log ----
        log_frame = ttk.LabelFrame(self.root, text="Log", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 5))

        self.log_text = scrolledtext.ScrolledText(log_frame, height=14,
                                                   state="disabled", wrap="word")
        self.log_text.pack(fill="both", expand=True)

        # ---- Status bar ----
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                               relief="sunken", anchor="w")
        status_bar.pack(fill="x", padx=10, pady=(0, 10))

    def _add_path_row(self, parent, label_text, var, row):
        ttk.Label(parent, text=label_text).grid(row=row, column=0, sticky="w", pady=2)
        entry = ttk.Entry(parent, textvariable=var, width=60)
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=2)
        ttk.Button(parent, text="Browse...",
                   command=lambda v=var: self._browse_folder(v)).grid(
            row=row, column=2, pady=2)
        parent.columnconfigure(1, weight=1)

    def _browse_folder(self, var):
        d = filedialog.askdirectory(initialdir=var.get() or str(PROJECT_DIR))
        if d:
            var.set(d)

    # ---- Checkbox interlock logic ----
    def _on_ocr_toggle(self):
        if self.step_import_ocr.get():
            self.step_extract_text.set(False)
            if not self.ocr_dir_var.get():
                self._browse_folder(self.ocr_dir_var)
                if not self.ocr_dir_var.get():
                    self.step_import_ocr.set(False)

    def _on_text_toggle(self):
        if self.step_extract_text.get():
            self.step_import_ocr.set(False)

    # ---- Logging helpers ----
    def log(self, msg):
        """Thread-safe log append."""
        self.root.after(0, self._log_append, msg)

    def _log_append(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def set_status(self, msg):
        self.root.after(0, self.status_var.set, msg)

    # ---- Open output folder ----
    def _open_output(self):
        d = self.output_dir_var.get()
        if os.path.isdir(d):
            os.startfile(d)
        else:
            messagebox.showinfo("Info", f"Output folder does not exist yet:\n{d}")

    # ---- Pipeline execution ----
    def _request_stop(self):
        self._stop_requested = True
        self.log("\n--- Stop requested. Will halt after current step. ---\n")

    def _start_pipeline(self):
        # Validation
        pdf_dir = self.pdf_dir_var.get().strip()
        output_dir = self.output_dir_var.get().strip()
        ocr_dir = self.ocr_dir_var.get().strip()

        if self.step_extract_png.get() or self.step_extract_text.get():
            if not os.path.isdir(pdf_dir):
                messagebox.showerror("Error", f"PDF input folder not found:\n{pdf_dir}")
                return

        if self.step_import_ocr.get():
            if not ocr_dir or not os.path.isdir(ocr_dir):
                messagebox.showerror("Error",
                    "External OCR folder is required when 'Import external OCR text' is checked.")
                return

        self.processing = True
        self._stop_requested = False
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        thread = threading.Thread(target=self._run_pipeline,
                                  args=(pdf_dir, output_dir, ocr_dir),
                                  daemon=True)
        thread.start()

    def _run_pipeline(self, pdf_dir, output_dir, ocr_dir):
        """Execute the pipeline steps sequentially in a background thread."""
        try:
            self._pipeline_impl(pdf_dir, output_dir, ocr_dir)
        except Exception as e:
            self.log(f"\nFATAL ERROR: {e}\n")
            self.set_status(f"Error: {e}")
        finally:
            self.root.after(0, self._pipeline_finished)

    def _pipeline_finished(self):
        self.processing = False
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    def _stopped(self):
        if self._stop_requested:
            self.log("Pipeline stopped by user.\n")
            self.set_status("Stopped")
            return True
        return False

    def _run_step(self, cmd, label, timeout=600):
        """Run a subprocess step. Returns True on success."""
        self.log(f"\n{'='*60}\n{label}\n{'='*60}\n")
        self.set_status(label)
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=self.env, bufsize=1
            )
            for line in proc.stdout:
                self.log(line)
            proc.wait(timeout=timeout)
            if proc.returncode != 0:
                self.log(f"\nStep failed with return code {proc.returncode}\n")
                return False
            self.log(f"\n{label} - DONE\n")
            return True
        except subprocess.TimeoutExpired:
            proc.kill()
            self.log(f"\n{label} timed out after {timeout}s\n")
            return False
        except Exception as e:
            self.log(f"\nError running step: {e}\n")
            return False

    def _pipeline_impl(self, pdf_dir, output_dir, ocr_dir):
        self.log("Starting pipeline...\n")
        self.set_status("Running pipeline...")

        # ---- Step 1: PDF Extraction (PNG + optionally text) ----
        if self.step_extract_png.get() or self.step_extract_text.get():
            if self._stopped():
                return
            png_only = self.step_extract_png.get() and not self.step_extract_text.get()
            cmd = ["python", get_script_path("pdf_extractor"), pdf_dir, output_dir]
            if png_only:
                cmd.append("--png-only")
            label = "Extracting PNGs from PDFs" if png_only else "Extracting PNGs and text from PDFs"
            if not self._run_step(cmd, label, timeout=600):
                self.log("PDF extraction failed. Stopping.\n")
                self.set_status("Failed at PDF extraction")
                return

        # ---- Step 2: Import external OCR text ----
        if self.step_import_ocr.get() and ocr_dir:
            if self._stopped():
                return
            cmd = ["python", get_script_path("ocr_text_importer"), ocr_dir, output_dir]
            if not self._run_step(cmd, "Importing external OCR text", timeout=300):
                self.log("OCR text import failed. Stopping.\n")
                self.set_status("Failed at OCR text import")
                return

        # Validate output folder exists
        if not os.path.isdir(output_dir) or not os.listdir(output_dir):
            self.log(f"Output folder is empty or missing: {output_dir}\n")
            self.set_status("No documents to process")
            return

        # ---- Step 3: Classify pages ----
        if self.step_classify.get():
            if self._stopped():
                return
            cmd = ["python", get_script_path("document_classifier"), output_dir]
            if not self._run_step(cmd, "Classifying pages (OpenAI vision)", timeout=3600):
                self.log("Classification failed. Stopping.\n")
                self.set_status("Failed at classification")
                return

        # ---- Step 4: Format TOC files ----
        if self.step_toc_format.get():
            if self._stopped():
                return
            cmd = ["python", get_script_path("toc_formatter"), output_dir]
            if not self._run_step(cmd, "Formatting TOC files", timeout=300):
                self.log("TOC formatting failed. Stopping.\n")
                self.set_status("Failed at TOC formatting")
                return

        # ---- Step 5: Aggregate metadata ----
        if self.step_metadata.get():
            if self._stopped():
                return
            cmd = ["python", get_script_path("metadata_aggregator"), output_dir]
            if not self._run_step(cmd, "Aggregating metadata (output.csv)", timeout=600):
                self.log("Metadata aggregation failed. Stopping.\n")
                self.set_status("Failed at metadata aggregation")
                return

        # ---- Step 6: Chunking ----
        if self.step_chunk.get():
            if self._stopped():
                return
            # TOC chunker
            cmd = [
                "python", get_script_path("toc_chunker"),
                "--in-root", output_dir,
                "--out-root", output_dir,
                "--write-chunk-files"
            ]
            if not self._run_step(cmd, "Chunking documents (TOC-based)", timeout=1800):
                self.log("TOC chunking failed. Continuing with semantic chunker...\n")

            if self._stopped():
                return

            # Semantic chunker for non-TOC documents
            self._run_semantic_chunker(output_dir)

        self.log("\n" + "=" * 60 + "\n")
        self.log("Pipeline completed successfully!\n")
        self.set_status("Pipeline completed")
        self.root.after(0, lambda: messagebox.showinfo(
            "Complete", "Pipeline finished successfully."))

    def _run_semantic_chunker(self, output_dir):
        """Run semantic chunker on non-TOC documents individually."""
        self.log(f"\n{'='*60}\nChunking documents (semantic)\n{'='*60}\n")
        self.set_status("Chunking documents (semantic)")

        for item in sorted(os.listdir(output_dir)):
            if self._stopped():
                return
            item_path = os.path.join(output_dir, item)
            if not os.path.isdir(item_path):
                continue

            metadata_dir = os.path.join(item_path, "metadata")
            if not os.path.isdir(metadata_dir):
                continue

            # Skip docs that have TOC (handled by TOC chunker)
            toc_files = [f for f in os.listdir(metadata_dir) if f.endswith('_TOC.txt')]
            if toc_files:
                continue

            chunks_dir = os.path.join(item_path, "chunks")
            if os.path.isdir(chunks_dir) and os.listdir(chunks_dir):
                self.log(f"  {item}: chunks already exist, skipping\n")
                continue

            text_dir = os.path.join(item_path, "text_pages")
            csv_files = [f for f in os.listdir(metadata_dir) if f.endswith('_classification.csv')]
            caption_files = [f for f in os.listdir(metadata_dir) if f.endswith('_caption.txt')]

            if not csv_files or not caption_files:
                self.log(f"  {item}: missing classification/caption files, skipping\n")
                continue

            csv_path = os.path.join(metadata_dir, csv_files[0])
            caption_path = os.path.join(metadata_dir, caption_files[0])

            # Build inline script to call the semantic chunker
            script_content = (
                f'import sys, importlib.util\n'
                f'sys.path.insert(0, r"{BASE_DIR}")\n'
                f'spec = importlib.util.spec_from_file_location("m", r"{get_script_path("semantic_chunker")}")\n'
                f'mod = importlib.util.module_from_spec(spec)\n'
                f'spec.loader.exec_module(mod)\n'
                f'c = mod.LegalDocumentChunker(max_tokens=800, min_tokens=100)\n'
                f'chunks = c.process_directory(\n'
                f'    text_dir=r"{text_dir}",\n'
                f'    csv_path=r"{csv_path}",\n'
                f'    caption_path=r"{caption_path}",\n'
                f'    output_dir=r"{chunks_dir}"\n'
                f')\n'
                f'print(f"Created {{len(chunks)}} chunks")\n'
            )

            cmd = ["python", "-c", script_content]
            self.log(f"  Processing: {item}\n")
            try:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, env=self.env, bufsize=1
                )
                for line in proc.stdout:
                    self.log(f"    {line}")
                proc.wait(timeout=300)
                if proc.returncode != 0:
                    self.log(f"    Failed (rc={proc.returncode})\n")
            except subprocess.TimeoutExpired:
                proc.kill()
                self.log(f"    Timed out\n")
            except Exception as e:
                self.log(f"    Error: {e}\n")

        self.log("Semantic chunking - DONE\n")


def main():
    root = tk.Tk()
    app = PipelineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
