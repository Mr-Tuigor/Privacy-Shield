from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from text_scrubber import PIIEngine
from image_redactor import ImageRedactor
from pdf_handler import PDFHandler

# ── App initialization ──────────────────────────────────────────────
app = FastAPI(
    title="Privacy Shield API",
    description=(
        "API for detecting and redacting Personally Identifiable Information (PII) "
        "from text, images, and PDF documents. Supports 15+ PII types including "
        "names, emails, phone numbers, Aadhaar, PAN, SSN, passport numbers, and more."
    ),
    version="1.0.0",
)

# ── CORS — allow React dev server and Electron to call the API ──────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Pre-load heavy ML models at startup (not per-request) ───────────
# These are class-level singletons — loading them here warms the cache
# so the first request doesn't have a cold start.
PIIEngine._load_nlp()
ImageRedactor._load_reader()

# ── Instantiate handlers that hold the loaded models ────────────────
image_redactor = ImageRedactor()
pdf_handler = PDFHandler()


# ── Request/Response models ─────────────────────────────────────────
class TextPayload(BaseModel):
    text: str

class RestorePayload(BaseModel):
    text: str
    pii_map: dict[str, str]


# ── Health check ────────────────────────────────────────────────────
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Privacy Shield API",
        "models_loaded": {
            "spacy": PIIEngine._nlp is not None,
            "easyocr": ImageRedactor._reader is not None,
        },
    }


# ── Text scrubbing ──────────────────────────────────────────────────
@app.post("/api/scrub-text")
def scrub_text(payload: TextPayload):
    """
    Scrub PII from plain text.
    
    Creates a fresh PIIEngine per request to avoid cross-request data leaks.
    Returns the original text, sanitized text, the token-to-original mapping,
    and a summary of all detected entities.
    """
    engine = PIIEngine()  # Fresh instance per request
    sanitized = engine.scrub(payload.text)
    
    return {
        "original": payload.text,
        "sanitized": sanitized,
        "pii_map": engine.pii_map,
        "entities": engine.get_summary(),
    }


# ── Text restoration ───────────────────────────────────────────────
@app.post("/api/restore-text")
def restore_text(payload: RestorePayload):
    """
    Restore previously scrubbed text back to its original form.
    
    Requires the sanitized text AND the pii_map that was returned from
    the scrub-text endpoint. Without the map, restoration is impossible.
    """
    engine = PIIEngine()
    engine.pii_map = payload.pii_map
    restored = engine.restore(payload.text)
    return {"restored": restored}


# ── Image redaction ─────────────────────────────────────────────────
@app.post("/api/redact-image")
async def redact_image(file: UploadFile = File(...)):
    """
    Redact PII from an uploaded image.
    
    Performs OCR on the image, detects PII in the extracted text, and returns:
    - The original extracted text
    - The sanitized text with placeholders
    - The redacted image (PII regions blacked out) as a base64 data URI
    - A summary of detected entities
    
    Supported formats: PNG, JPG, JPEG, BMP, TIFF, WebP
    """
    # Validate file type
    allowed_types = {
        "image/png", "image/jpeg", "image/jpg", "image/bmp",
        "image/tiff", "image/webp",
    }
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {file.content_type}. "
                   f"Allowed: {', '.join(allowed_types)}"
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    engine = PIIEngine()  # Fresh instance per request
    
    try:
        result = image_redactor.redact_image(image_bytes, engine)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "status": "success",
        "original_text": result["original_text"],
        "sanitized_text": result["sanitized_text"],
        "redacted_image_base64": result["redacted_image_base64"],
        "pii_map": engine.pii_map,
        "entities": result["entities"],
    }


# ── PDF redaction ───────────────────────────────────────────────────
@app.post("/api/redact-pdf")
async def redact_pdf(file: UploadFile = File(...)):
    """
    Redact PII from an uploaded PDF document.
    
    Handles both digital PDFs (direct text extraction) and scanned PDFs
    (page rendering + OCR). Returns per-page results including:
    - Original text per page
    - Sanitized text per page  
    - For scanned pages: redacted page images as base64
    - Combined text across all pages
    - Entity summary
    """
    if file.content_type and file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail=f"Expected a PDF file, got: {file.content_type}"
        )

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    engine = PIIEngine()  # Fresh instance per request

    try:
        result = pdf_handler.process_pdf(pdf_bytes, engine)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF processing error: {str(e)}")

    return {
        "status": "success",
        "total_pages": result["total_pages"],
        "pages": result["pages"],
        "combined_original_text": result["combined_original_text"],
        "combined_sanitized_text": result["combined_sanitized_text"],
        "pii_map": engine.pii_map,
        "entities": result["entities"],
    }