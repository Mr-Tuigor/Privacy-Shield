"""
text_scrubber.py
~~~~~~~~~~~~~~~~
Presidio-powered PII detection and replacement engine for Privacy Shield.

Key improvements over the previous spaCy-only approach:
  • Microsoft Presidio provides per-entity CONFIDENCE SCORES — borderline
    predictions are filtered out rather than blindly redacted.
  • Context-aware boosting: if "email" appears near an email-like pattern,
    the confidence rises automatically.
  • phonenumbers library (backed by Google's libphonenumber) replaces the
    fragile digit-counting regex for phone numbers.
  • Overlapping / duplicate spans are deduplicated before replacement.
  • ORG detection uses a strict 0.80 threshold to eliminate tech-stack FPs.
  • Custom PatternRecognizers for Indian Aadhaar, PAN, PIN, and Passport.
  • Same public API (scrub / restore / get_summary) — no frontend changes.
"""

import re
import os
from typing import Optional

import phonenumbers

from presidio_analyzer import (
    AnalyzerEngine,
    PatternRecognizer,
    Pattern,
    RecognizerRegistry,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider


# ── Entity-type mapping: Presidio name → our internal label ────────────────
PRESIDIO_TO_LABEL: dict[str, str] = {
    "PERSON":           "PERSON",
    "ORGANIZATION":     "ORG",
    "LOCATION":         "LOCATION",
    "EMAIL_ADDRESS":    "EMAIL",
    "PHONE_NUMBER":     "PHONE",
    "IN_AADHAAR":       "AADHAAR",
    "IN_PAN":           "PAN",
    "US_SSN":           "SSN",
    "DATE_TIME":        "DATE",
    "IP_ADDRESS":       "IP",
    "URL":              "URL",
    "CREDIT_CARD":      "CREDIT_CARD",
    "IN_PIN":           "PIN",
    "IN_PASSPORT":      "PASSPORT",
}

# ── Per-entity confidence thresholds ───────────────────────────────────────
# Higher → fewer false positives.  Lower → fewer missed detections.
# Tuned so that common tech-term false positives (ORG) are strongly filtered
# while structured patterns (EMAIL, CREDIT_CARD) pass easily.
THRESHOLDS: dict[str, float] = {
    "PERSON":        0.70,   # Reasonable — NER is fairly reliable for names
    "ORGANIZATION":  0.80,   # Strict — biggest FP source (tech stacks, tools)
    "LOCATION":      0.65,   # Slightly permissive — location names are distinctive
    "EMAIL_ADDRESS": 0.50,   # Presidio email recogniser is very precise
    "PHONE_NUMBER":  0.40,   # Presidio scores phones at 0.4; phonenumbers validates correctness
    "IN_AADHAAR":    0.85,
    "IN_PAN":        0.85,
    "US_SSN":        0.85,
    "DATE_TIME":     0.55,   # Presidio dates score at 0.6 — keep threshold below that
    "IP_ADDRESS":    0.85,
    "URL":           0.50,   # URLs are structurally clear
    "CREDIT_CARD":   0.85,   # Presidio applies Luhn check internally
    "IN_PIN":        0.75,
    "IN_PASSPORT":   0.80,
}

# Entities Presidio should look for (all keys of the mapping above)
_ENTITIES_TO_DETECT = list(PRESIDIO_TO_LABEL.keys())


class PIIEngine:
    """
    Detects and replaces Personally Identifiable Information (PII) in text.

    Each instance maintains its own mapping of tokens → original values, making
    it safe to create one instance per request to avoid cross-request data leaks.

    Supported PII types:
        PERSON, ORG, LOCATION, EMAIL, PHONE, AADHAAR, PAN, SSN, PASSPORT,
        DATE, IP, URL, CREDIT_CARD, PIN
    """

    # ── Class-level singleton — loaded once at startup ─────────────────────
    _analyzer: Optional[AnalyzerEngine] = None

    # Legacy alias used by main.py startup warm-up
    _nlp = True  # Signals "loaded" without exposing internals

    @classmethod
    def _build_analyzer(cls) -> AnalyzerEngine:
        """Build and cache the Presidio AnalyzerEngine (called once)."""
        if cls._analyzer is not None:
            return cls._analyzer

        print("[*] Loading Presidio PII engine with spaCy (en_core_web_lg)...")

        # ── Configure spaCy NLP backend ────────────────────────────────────
        spacy_config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
        }
        try:
            provider = NlpEngineProvider(nlp_configuration=spacy_config)
            nlp_engine = provider.create_engine()
            print("[+] spaCy en_core_web_lg loaded.")
        except Exception:
            print("[!] en_core_web_lg not found, falling back to en_core_web_sm")
            spacy_config["models"] = [{"lang_code": "en", "model_name": "en_core_web_sm"}]
            provider = NlpEngineProvider(nlp_configuration=spacy_config)
            nlp_engine = provider.create_engine()
            print("[+] spaCy en_core_web_sm loaded.")

        # ── Build recogniser registry ──────────────────────────────────────
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=nlp_engine)

        # Indian Aadhaar: XXXX XXXX XXXX or XXXX-XXXX-XXXX
        registry.add_recognizer(PatternRecognizer(
            supported_entity="IN_AADHAAR",
            patterns=[Pattern("aadhaar", r"\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b", 0.85)],
            context=["aadhaar", "uid", "unique identification", "uidai"],
        ))

        # Indian PAN card: ABCDE1234F
        registry.add_recognizer(PatternRecognizer(
            supported_entity="IN_PAN",
            patterns=[Pattern("pan", r"\b[A-Z]{5}\d{4}[A-Z]\b", 0.85)],
            context=["pan", "permanent account", "income tax", "tax"],
        ))

        # Indian 6-digit PIN / postal code (with context requirement)
        registry.add_recognizer(PatternRecognizer(
            supported_entity="IN_PIN",
            patterns=[
                Pattern("pin_with_context", r"(?<!\d[\s\-])\b\d{6}\b(?![\s\-]\d)", 0.50)
            ],
            context=["pin", "pincode", "postal", "zip", "area code", "code"],
        ))

        # Indian / generic passport: Letter + 7-8 digits
        registry.add_recognizer(PatternRecognizer(
            supported_entity="IN_PASSPORT",
            patterns=[Pattern("passport", r"\b[A-Z][0-9]{7,8}\b", 0.60)],
            context=["passport", "travel document", "passport no", "passport number"],
        ))

        # US Social Security Number: XXX-XX-XXXX (custom to catch without context)
        registry.add_recognizer(PatternRecognizer(
            supported_entity="US_SSN",
            patterns=[Pattern("ssn_pattern", r"\b\d{3}-\d{2}-\d{4}\b", 0.85)],
            context=["ssn", "social security", "social security number"],
        ))

        cls._analyzer = AnalyzerEngine(
            registry=registry,
            nlp_engine=nlp_engine,
            supported_languages=["en"],
        )
        print("[+] Presidio AnalyzerEngine ready.")
        return cls._analyzer

    # Legacy warm-up method called from main.py
    @classmethod
    def _load_nlp(cls):
        cls._build_analyzer()

    # ── Instance ───────────────────────────────────────────────────────────

    def __init__(self):
        self.analyzer = self._build_analyzer()
        self.pii_map:         dict[str, str]  = {}
        self.counters:        dict[str, int]  = {
            label: 1 for label in set(PRESIDIO_TO_LABEL.values())
        }
        self.entities_found:  list[dict]      = []

        # Load allowlist (terms that must NEVER be redacted)
        self.ignore_set: set[str] = self._load_ignore_set()

    # ── Allowlist loading ──────────────────────────────────────────────────

    def _load_ignore_set(self) -> set[str]:
        """Return a set of lower-cased terms that must never be flagged."""
        defaults = {
            # Section headers & labels
            "email", "address", "github", "contact", "phone", "about me",
            "skills", "language", "languages", "education", "experience",
            "projects", "certifications", "objective", "summary", "references",
            "hobbies", "interests", "declaration", "profile", "resume", "cv",
            # Programming & tech
            "mern", "mern stack", "web", "javascript", "typescript",
            "python", "c++", "c#", "java", "go", "rust", "ruby", "php", "swift",
            "kotlin", "dart", "scala", "r", "matlab", "sql", "nosql",
            "react", "angular", "vue", "svelte", "next.js", "nuxt",
            "node.js", "express.js", "django", "flask", "fastapi", "spring",
            "mongodb", "postgresql", "mysql", "redis", "firebase",
            "docker", "kubernetes", "aws", "azure", "gcp",
            "html", "css", "tailwind", "bootstrap", "ejs",
            "git", "github", "gitlab", "bitbucket", "vs code",
            "numpy", "pandas", "tensorflow", "pytorch", "scikit-learn",
            "data analytics", "machine learning", "ai", "deep learning",
            "rest", "graphql", "api", "ci/cd", "devops", "agile", "scrum",
            # Spoken languages
            "hindi", "english", "french", "spanish", "german", "marathi",
            "tamil", "telugu", "kannada", "bengali", "gujarati", "urdu",
            "punjabi", "malayalam", "odia",
            # Common résumé false positives
            "linkedin", "twitter", "facebook", "instagram", "portfolio",
            "bachelor", "master", "phd", "b.tech", "m.tech", "b.e.", "m.e.",
            "mba", "bca", "mca", "b.sc", "m.sc", "b.com", "m.com",
            "cgpa", "gpa", "percentage", "internship", "nptel",
        }

        # Merge in ignore_list.txt
        try:
            path = os.path.join(os.path.dirname(__file__), "ignore_list.txt")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as fh:
                    for line in fh:
                        term = line.strip()
                        if term and not term.startswith("#"):
                            defaults.add(term.lower())
        except Exception as e:
            print(f"[!] Warning: Could not load ignore_list.txt: {e}")

        return defaults

    def _is_ignored(self, text: str) -> bool:
        """Return True if the span matches any allowlist term."""
        text_lower = text.lower().strip()
        if text_lower in self.ignore_set:
            return True
        # Substring check — but ONLY for non-numeric terms.
        # Numeric entries (port numbers, versions, etc.) from ignore_list.txt
        # must match EXACTLY to avoid blocking phone numbers, credit cards, etc.
        if len(text_lower) >= 4:
            for ignored in self.ignore_set:
                if len(ignored) >= 4 and not ignored.isdigit() and ignored in text_lower:
                    return True
        return False


    # ── Token management ───────────────────────────────────────────────────

    def _get_or_create_token(self, original_text: str, label_type: str) -> str:
        """Return an existing token for this value, or create a new one."""
        original_clean = original_text.strip().lower()

        for token, stored_val in self.pii_map.items():
            if not token.startswith(f"[{label_type}_"):
                continue
            stored_clean = stored_val.strip().lower()
            if original_clean == stored_clean:
                return token
            # Partial name matching (e.g. "Amit" ↔ "Amit Sharma")
            if len(original_clean) >= 3 and len(stored_clean) >= 3:
                if original_clean in stored_clean or stored_clean in original_clean:
                    return token

        # New token
        token = f"[{label_type}_{self.counters[label_type]}]"
        self.pii_map[token] = original_text
        self.counters[label_type] += 1
        self.entities_found.append({
            "type":        label_type,
            "original":    original_text,
            "replacement": token,
        })
        return token

    # ── Phone validation ───────────────────────────────────────────────────

    @staticmethod
    def _validate_phone(text: str) -> bool:
        """
        Validate a phone candidate using Google's phonenumbers library.
        Falls back to a digit-count check for OCR-noisy text.
        """
        # Try parsing with region hints: international → India → US
        for region in [None, "IN", "US"]:
            try:
                parsed = phonenumbers.parse(text, region)
                if phonenumbers.is_valid_number(parsed):
                    return True
            except phonenumbers.NumberParseException:
                pass
        # Fallback: require 7–15 digits (international range)
        digits = re.sub(r"\D", "", text)
        return 7 <= len(digits) <= 15

    # ── Main scrubbing pipeline ─────────────────────────────────────────────

    def scrub(self, text: str) -> str:
        """
        Detect and replace all PII in *text*.

        Pipeline:
          1. Run Presidio AnalyzerEngine to get candidate spans with scores.
          2. Filter by per-entity confidence threshold.
          3. Apply allowlist to remove known non-PII terms.
          4. Additional phone validation via phonenumbers library.
          5. Deduplicate overlapping spans (keep highest-scoring).
          6. Replace spans right-to-left to preserve character offsets.

        Returns sanitized text with PII replaced by [TYPE_N] tokens.
        """
        if not text or not text.strip():
            return text

        # Step 1 — Presidio analysis
        results = self.analyzer.analyze(
            text=text,
            entities=_ENTITIES_TO_DETECT,
            language="en",
        )

        # Step 2 & 3 & 4 — Filter
        candidates = []
        for r in results:
            # Threshold filter
            threshold = THRESHOLDS.get(r.entity_type, 0.70)
            if r.score < threshold:
                continue

            span_text = text[r.start:r.end]

            # Allowlist filter
            if self._is_ignored(span_text):
                continue

            # Skip tiny spans (usually OCR noise or stray initials)
            if len(span_text.strip()) <= 2:
                continue

            # Skip already-replaced tokens like [PERSON_1]
            if re.match(r"^\[[\w_]+\]$", span_text.strip()):
                continue

            # Skip DATE spans that are purely 10-digit numbers (likely phones)
            if r.entity_type == "DATE_TIME":
                digits_only = re.sub(r"\D", "", span_text)
                if len(digits_only) == 10 and len(span_text.strip()) == 10:
                    continue

            # Phone-specific validation
            if r.entity_type == "PHONE_NUMBER" and not self._validate_phone(span_text):
                continue

            candidates.append(r)

        # Step 5 — Deduplicate overlapping spans (greedy, prefer higher score)
        candidates.sort(key=lambda x: x.score, reverse=True)
        kept: list = []
        covered: list[tuple[int, int]] = []

        for r in candidates:
            # Check for overlap with already-kept spans
            overlaps = any(
                not (r.end <= s or r.start >= e) for s, e in covered
            )
            if not overlaps:
                kept.append(r)
                covered.append((r.start, r.end))

        # Step 6 — Replace right-to-left to keep offsets valid
        kept.sort(key=lambda x: x.start, reverse=True)

        sanitized = text
        for r in kept:
            label_type = PRESIDIO_TO_LABEL.get(r.entity_type, r.entity_type)
            # Use the original text positions (right-to-left guarantees validity)
            original_span = text[r.start:r.end]
            token = self._get_or_create_token(original_span, label_type)
            sanitized = sanitized[: r.start] + token + sanitized[r.end :]

        return sanitized

    # ── Restoration ────────────────────────────────────────────────────────

    def restore(self, text: str) -> str:
        """
        Reverse the scrubbing — replace all [TYPE_N] tokens with originals.
        Sorts by token length (longest first) to prevent partial replacements
        (e.g., replacing [PERSON_1] before [PERSON_10]).
        """
        restored = text
        for token in sorted(self.pii_map.keys(), key=len, reverse=True):
            restored = restored.replace(token, self.pii_map[token])
        return restored

    # ── Summary ────────────────────────────────────────────────────────────

    def get_summary(self) -> dict:
        """Return a summary of all PII entities detected."""
        type_counts: dict[str, int] = {}
        for entity in self.entities_found:
            t = entity["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_entities": len(self.entities_found),
            "by_type":        type_counts,
            "details":        self.entities_found,
        }