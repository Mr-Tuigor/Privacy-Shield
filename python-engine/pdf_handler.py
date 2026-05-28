import fitz  # PyMuPDF
import numpy as np
import cv2
from text_scrubber import PIIEngine
from image_redactor import ImageRedactor


class PDFHandler:
    """
    Handles PDF documents for PII detection and redaction.
    
    Supports two types of PDFs:
      1. Digital PDFs — text is extracted directly (fast, accurate)
      2. Scanned PDFs — pages are rendered as images and processed with OCR
    
    Returns per-page original text, sanitized text, and a combined summary.
    """

    def __init__(self):
        self.image_redactor = ImageRedactor()

    def process_pdf(self, pdf_bytes: bytes, pii_engine: PIIEngine) -> dict:
        """
        Process a PDF file:
        1. Open the PDF from bytes
        2. For each page, try to extract text directly  
        3. If a page has no text (scanned), render it as an image and OCR it
        4. Scrub all extracted text through the PII engine
        5. Return per-page results with original and sanitized content
        """
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_result = []
        all_original_text = []
        all_sanitized_text = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text("text").strip()

            page_data = {
                "page_number": page_num + 1,
                "extraction_method": None,
                "original_text": "",
                "sanitized_text": "",
                "original_image_base64": None,  # Added to send original image base64
                "redacted_image_base64": None,
            }

            if page_text and len(page_text) > 20:
                # ── Digital PDF page: extract text + render image ──
                page_data["extraction_method"] = "digital"
                page_data["original_text"] = page_text
                page_data["sanitized_text"] = pii_engine.scrub(page_text)

                    # --- NEW: render image for visualization ---
                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)

                img_data = pix.tobytes("png")
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    ocr_result = self.image_redactor.redact_image_from_numpy(
                        img, pii_engine
                    )

                    page_data["original_image_base64"] = ocr_result["original_image_base64"]
                    page_data["redacted_image_base64"] = ocr_result["redacted_image_base64"]
            else:
                # ── Scanned PDF page: render as image → OCR ──
                page_data["extraction_method"] = "ocr"

                mat = fitz.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=mat)

                img_data = pix.tobytes("png")
                nparr = np.frombuffer(img_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if img is not None:
                    ocr_result = self.image_redactor.redact_image_from_numpy(
                        img, pii_engine
                    )
                    page_data["original_text"] = ocr_result["original_text"]
                    page_data["sanitized_text"] = ocr_result["sanitized_text"]
                    page_data["original_image_base64"] = ocr_result["original_image_base64"]
                    page_data["redacted_image_base64"] = ocr_result["redacted_image_base64"]
                else:
                    page_data["original_text"] = "[Could not render page]"
                    page_data["sanitized_text"] = "[Could not render page]"

            all_original_text.append(page_data["original_text"])
            all_sanitized_text.append(page_data["sanitized_text"])
            pages_result.append(page_data)

        doc.close()

        return {
            "total_pages": len(pages_result),
            "pages": pages_result,
            "combined_original_text": "\n\n--- Page Break ---\n\n".join(all_original_text),
            "combined_sanitized_text": "\n\n--- Page Break ---\n\n".join(all_sanitized_text),
            "entities": pii_engine.get_summary(),
        }
