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

    def _mask_box_partially(self, img: np.ndarray, bbox: list, text: str, pii_values: list):
        text_lower = text.lower().strip()
        
        import re
        contained_pii = []
        for pv in pii_values:
            if pv in text_lower:
                contained_pii.append(pv)
            # Handle case where the box is a smaller piece of a large cross-line PII
            elif len(text_lower) >= 4 and text_lower in pv:
                contained_pii.append(text_lower)
            # Handle intersecting cases (e.g. box="Email: john", pv="john\n@gmail.com")
            else:
                for part in re.split(r'[\s\n]+', pv):
                    if len(part) >= 4 and part in text_lower:
                        contained_pii.append(part)
                
        if not contained_pii:
            return
            
        pts = np.array(bbox, dtype=np.int32)
        
        # If the exact text is a PII, mask the whole box
        if any(text_lower == pv for pv in contained_pii):
            cv2.fillPoly(img, [pts], color=(0, 0, 0))
            return
            
        # Otherwise, partial match. Use character-level approximation
        x_coords = pts[:, 0]
        y_coords = pts[:, 1]
        x_min, x_max = x_coords.min(), x_coords.max()
        y_min, y_max = y_coords.min(), y_coords.max()
        
        box_width = x_max - x_min
        text_len = max(1, len(text))
        
        for pv in contained_pii:
            start_idx = text_lower.find(pv)
            if start_idx == -1: continue
            
            end_idx = start_idx + len(pv)
            
            mask_x_min = x_min + int((start_idx / text_len) * box_width)
            mask_x_max = x_min + int((end_idx / text_len) * box_width)
            
            mask_x_min = max(x_min, mask_x_min - 3)
            mask_x_max = min(x_max, mask_x_max + 3)
            
            cv2.rectangle(img, (mask_x_min, y_min), (mask_x_max, y_max), (0, 0, 0), -1)

    def redact_image(self, image_bytes: bytes, pii_engine: PIIEngine) -> dict:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image. Ensure the file is a valid image.")

        redacted_img = img.copy()

        # By default, readtext returns reasonable phrase/line level boxes
        results = self.reader.readtext(img)

        original_lines = []
        for bbox, text, confidence in results:
            if confidence >= 0.2:
                original_lines.append(text)

        # 1. Join all text to give the NLP model full context!
        full_original_text = "\n".join(original_lines)
        
        # 2. Scrub the full text at once for MAXIMUM text accuracy
        full_sanitized_text = pii_engine.scrub(full_original_text)
        
        # 3. Get exactly what was flagged as PII to selectively mask the image
        pii_values = [v.lower().strip() for v in pii_engine.pii_map.values() if len(v.strip()) >= 2]

        # 4. Mask only the precise locations that match PII
        for bbox, text, confidence in results:
            if confidence < 0.2:
                continue
            self._mask_box_partially(redacted_img, bbox, text, pii_values)

        is_success_orig, buffer_orig = cv2.imencode(".png", img)
        if not is_success_orig:
            raise ValueError("Failed to encode original image.")
        original_base64 = base64.b64encode(buffer_orig).decode('utf-8')

        is_success, buffer = cv2.imencode(".png", redacted_img)
        if not is_success:
            raise ValueError("Failed to encode redacted image.")
        redacted_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "original_text": full_original_text,
            "sanitized_text": full_sanitized_text,
            "original_image_base64": f"data:image/png;base64,{original_base64}",
            "redacted_image_base64": f"data:image/png;base64,{redacted_base64}",
            "entities": pii_engine.get_summary(),
        }

    def redact_image_from_numpy(self, img: np.ndarray, pii_engine: PIIEngine) -> dict:
        if img is None:
            raise ValueError("Received empty image array.")

        redacted_img = img.copy()
        results = self.reader.readtext(img)

        original_lines = []
        for bbox, text, confidence in results:
            if confidence >= 0.2:
                original_lines.append(text)

        full_original_text = "\n".join(original_lines)
        full_sanitized_text = pii_engine.scrub(full_original_text)
        
        pii_values = [v.lower().strip() for v in pii_engine.pii_map.values() if len(v.strip()) >= 2]

        for bbox, text, confidence in results:
            if confidence < 0.2:
                continue
            self._mask_box_partially(redacted_img, bbox, text, pii_values)

        is_success_orig, buffer_orig = cv2.imencode(".png", img)
        if not is_success_orig:
            raise ValueError("Failed to encode original image.")
        original_base64 = base64.b64encode(buffer_orig).decode('utf-8')

        is_success, buffer = cv2.imencode(".png", redacted_img)
        if not is_success:
            raise ValueError("Failed to encode redacted image.")
        redacted_base64 = base64.b64encode(buffer).decode('utf-8')

        return {
            "original_text": full_original_text,
            "sanitized_text": full_sanitized_text,
            "original_image_base64": f"data:image/png;base64,{original_base64}",
            "redacted_image_base64": f"data:image/png;base64,{redacted_base64}",
        }