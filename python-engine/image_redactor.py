import cv2
import numpy as np
import easyocr
import base64
from text_scrubber import PIIEngine


class ImageRedactor:
    """
    Extracts text from images using EasyOCR, scrubs PII, and returns:
      - The original extracted text
      - The sanitized text (with placeholders)
      - The redacted image (PII regions blacked out) as base64
      - A summary of detected entities
    """

    # Class-level EasyOCR reader — loaded once, shared across instances
    _reader = None

    @classmethod
    def _load_reader(cls):
        if cls._reader is None:
            print("[*] Loading EasyOCR model...")
            cls._reader = easyocr.Reader(['en'], gpu=False)
            print("[+] EasyOCR model loaded.")
        return cls._reader

    def __init__(self):
        self.reader = self._load_reader()

    def redact_image(self, image_bytes: bytes, pii_engine: PIIEngine) -> dict:
        """
        Process an image:
        1. Decode image from bytes
        2. Run OCR to extract all text regions
        3. Scrub each text region through the PII engine
        4. Black-out regions where PII was found
        5. Return original text, safe text, redacted image, and entity summary
        """
        # Decode image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image. Ensure the file is a valid image.")

        # Create a copy for redaction (keep original for before/after)
        redacted_img = img.copy()

        # Run OCR
        results = self.reader.readtext(img)

        original_lines = []
        sanitized_lines = []

        for bbox, text, confidence in results:
            # Skip very low confidence OCR results (likely noise)
            if confidence < 0.2:
                continue

            original_lines.append(text)

            # Scrub this text chunk
            scrubbed = pii_engine.scrub(text)
            sanitized_lines.append(scrubbed)

            # If PII was found (text changed), draw a black box over this region
            if scrubbed != text:
                pts = np.array(bbox, dtype=np.int32)
                # Use fillPoly for rotated bounding boxes (more accurate than rectangle)
                cv2.fillPoly(redacted_img, [pts], color=(0, 0, 0))

        # Encode the original image to PNG base64 (for before/after comparison)
        is_success_orig, buffer_orig = cv2.imencode(".png", img)
        if not is_success_orig:
            raise ValueError("Failed to encode original image.")
        original_base64 = base64.b64encode(buffer_orig).decode('utf-8')

        # Encode the redacted image to PNG base64
        is_success, buffer = cv2.imencode(".png", redacted_img)
        if not is_success:
            raise ValueError("Failed to encode redacted image.")
        redacted_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "original_text": "\n".join(original_lines),
            "sanitized_text": "\n".join(sanitized_lines),
            "original_image_base64": f"data:image/png;base64,{original_base64}",
            "redacted_image_base64": f"data:image/png;base64,{redacted_base64}",
            "entities": pii_engine.get_summary(),
        }

    def redact_image_from_numpy(self, img: np.ndarray, pii_engine: PIIEngine) -> dict:
        """
        Same as redact_image but accepts a NumPy array directly.
        Used by the PDF handler for processing page images.
        """
        if img is None:
            raise ValueError("Received empty image array.")

        redacted_img = img.copy()
        results = self.reader.readtext(img)

        original_lines = []
        sanitized_lines = []

        for bbox, text, confidence in results:
            if confidence < 0.2:
                continue

            original_lines.append(text)
            scrubbed = pii_engine.scrub(text)
            sanitized_lines.append(scrubbed)

            if scrubbed != text:
                pts = np.array(bbox, dtype=np.int32)
                cv2.fillPoly(redacted_img, [pts], color=(0, 0, 0))

        # Encode original image
        is_success_orig, buffer_orig = cv2.imencode(".png", img)
        if not is_success_orig:
            raise ValueError("Failed to encode original image.")
        original_base64 = base64.b64encode(buffer_orig).decode('utf-8')

        # Encode redacted image
        is_success, buffer = cv2.imencode(".png", redacted_img)
        if not is_success:
            raise ValueError("Failed to encode redacted image.")
        redacted_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "original_text": "\n".join(original_lines),
            "sanitized_text": "\n".join(sanitized_lines),
            "original_image_base64": f"data:image/png;base64,{original_base64}",
            "redacted_image_base64": f"data:image/png;base64,{redacted_base64}",
        }