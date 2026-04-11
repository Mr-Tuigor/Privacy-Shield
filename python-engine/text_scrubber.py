import spacy
import re
from typing import Optional


class PIIEngine:
    """
    Detects and replaces Personally Identifiable Information (PII) in text.
    
    Each instance maintains its own mapping of tokens → original values, making it
    safe to create one instance per request to avoid cross-request data leaks.
    
    Supported PII types:
        - PERSON  — Names (via spaCy NER)
        - ORG     — Organization names (via spaCy NER)
        - LOCATION — Cities, countries, addresses (via spaCy NER: GPE, LOC, FAC)
        - EMAIL   — Email addresses (OCR-tolerant regex)
        - PHONE   — Phone numbers (Indian, US, international formats)
        - AADHAAR — Indian Aadhaar numbers (XXXX XXXX XXXX)
        - PAN     — Indian PAN card numbers (ABCDE1234F)
        - DOB     — Dates that likely represent dates of birth
        - DATE    — General date patterns
        - SSN     — US Social Security Numbers (XXX-XX-XXXX)
        - PASSPORT— Passport number patterns
        - PIN     — Standalone 6-digit PIN/zip codes
        - URL     — URLs that may contain personal identifiers
        - IP      — IP addresses
        - CREDIT_CARD — Credit/debit card numbers
    """

    # Class-level NLP model — loaded once, shared across all instances
    _nlp = None

    @classmethod
    def _load_nlp(cls):
        if cls._nlp is None:
            print("[*] Loading spaCy NLP model (en_core_web_lg)...")
            try:
                cls._nlp = spacy.load("en_core_web_lg")
                print("[+] spaCy model loaded successfully.")
            except OSError:
                print("[!] en_core_web_lg not found, falling back to en_core_web_sm")
                cls._nlp = spacy.load("en_core_web_sm")
                print("[+] spaCy model (sm) loaded successfully.")

        return cls._nlp

    def __init__(self):
        self.nlp = self._load_nlp()
        self.pii_map: dict[str, str] = {}
        self.counters: dict[str, int] = {
            "PERSON": 1, "ORG": 1, "LOCATION": 1,
            "EMAIL": 1, "PHONE": 1, "AADHAAR": 1, "PAN": 1,
            "DOB": 1, "DATE": 1, "SSN": 1, "PASSPORT": 1,
            "PIN": 1, "URL": 1, "IP": 1, "CREDIT_CARD": 1,
        }
        self.entities_found: list[dict] = []  # Track what was detected for reporting

        # ---------- Allowlist: terms that should NEVER be flagged ----------
        # Common resume section headers, tech skills, programming languages,
        # frameworks, and generic labels that spaCy often misclassifies.
        self.ignore_list = {term.lower() for term in [
            # Section headers & labels
            "Email", "Address", "Github", "Contact", "Phone", "About Me",
            "Skills", "Language", "Languages", "Education", "Experience",
            "Projects", "Certifications", "Objective", "Summary", "References",
            "Hobbies", "Interests", "Declaration", "Profile", "Resume", "CV",
            # Programming & tech
            "MERN", "MERN stack", "Web", "Javascript", "TypeScript",
            "Python", "C++", "C#", "Java", "Go", "Rust", "Ruby", "PHP", "Swift",
            "Kotlin", "Dart", "Scala", "R", "MATLAB", "SQL", "NoSQL",
            "React", "Angular", "Vue", "Svelte", "Next.js", "Nuxt",
            "Node.js", "Express.js", "Django", "Flask", "FastAPI", "Spring",
            "MongoDB", "PostgreSQL", "MySQL", "Redis", "Firebase",
            "Docker", "Kubernetes", "AWS", "Azure", "GCP",
            "HTML", "CSS", "Tailwind", "Bootstrap", "EJS",
            "Git", "GitHub", "GitLab", "Bitbucket", "VS Code",
            "Numpy", "Pandas", "TensorFlow", "PyTorch", "scikit-learn",
            "Data Analytics", "Machine Learning", "AI", "Deep Learning",
            "REST", "GraphQL", "API", "CI/CD", "DevOps", "Agile", "Scrum",
            # Languages (spoken)
            "Hindi", "English", "French", "Spanish", "German", "Marathi",
            "Tamil", "Telugu", "Kannada", "Bengali", "Gujarati", "Urdu",
            "Punjabi", "Malayalam", "Odia",
            # Common false positives
            "LinkedIn", "Twitter", "Facebook", "Instagram", "Portfolio",
            "Bachelor", "Master", "PhD", "B.Tech", "M.Tech", "B.E.", "M.E.",
            "MBA", "BCA", "MCA", "B.Sc", "M.Sc", "B.Com", "M.Com",
            "CGPA", "GPA", "Percentage",
        ]}

        # ---------- Regex patterns — ORDER MATTERS ----------
        # Patterns are checked in this order. More specific patterns first to
        # prevent partial matches (e.g., Aadhaar before PIN).
        self.regex_patterns = [
            # Email: OCR-tolerant (allows brackets, spaces around @ and .)
            (
                r'[A-Za-z0-9._%+\-\[\]]+\s*@\s*[A-Za-z0-9.\-]+\s*\.\s*[A-Za-z]{2,}',
                "EMAIL"
            ),
            # URL: http(s) URLs and www. URLs
            (
                r'https?://[^\s<>\"\']+|www\.[^\s<>\"\']+',
                "URL"
            ),
            # IP Address: IPv4
            (
                r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
                "IP"
            ),
            # Credit Card: 13-19 digit numbers with optional spaces/dashes
            (
                r'\b(?:\d[ \-]?){13,19}\b',
                "CREDIT_CARD"
            ),
            # Aadhaar: XXXX XXXX XXXX or XXXX-XXXX-XXXX (Indian 12-digit ID)
            (
                r'\b\d{4}[\s\-]\d{4}[\s\-]\d{4}\b',
                "AADHAAR"
            ),
            # PAN Card: ABCDE1234F (Indian tax ID — 5 letters, 4 digits, 1 letter)
            (
                r'\b[A-Z]{5}\d{4}[A-Z]\b',
                "PAN"
            ),
            # SSN: XXX-XX-XXXX (US Social Security Number)
            (
                r'\b\d{3}-\d{2}-\d{4}\b',
                "SSN"
            ),
            # Passport: Letter followed by 7-8 digits (Indian + many international formats)
            (
                r'\b[A-Z][0-9]{7,8}\b',
                "PASSPORT"
            ),
            # Phone: International formats — must come before PIN
            # Supports: +91-XXXXX-XXXXX, (XXX) XXX-XXXX, +1-XXX-XXX-XXXX, etc.
            (
                r'(?:\+?\d{1,3}[\s\-]?)?\(?\d{2,5}\)?[\s\-]?\d{3,5}[\s\-]?\d{3,5}\b',
                "PHONE"
            ),
            # Date / DOB: DD/MM/YYYY, MM-DD-YYYY, YYYY-MM-DD, DD.MM.YYYY
            (
                r'\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b|\b\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}\b',
                "DATE"
            ),
            # PIN / Zip Code: Standalone 6-digit code (Indian PIN) — word boundaries prevent
            # matching inside phone numbers or Aadhaar numbers
            (
                r'(?<!\d[\s\-])\b\d{6}\b(?![\s\-]\d)',
                "PIN"
            ),
        ]

    def _is_ignored(self, text: str) -> bool:
        """Check if the text matches any term in the allowlist."""
        text_lower = text.lower().strip()
        # Exact match
        if text_lower in self.ignore_list:
            return True
        # Check if the entity is a substring of any ignored term or vice versa
        for ignored in self.ignore_list:
            if text_lower == ignored:
                return True
        return False

    def _get_existing_token(self, text: str, label_type: str) -> Optional[str]:
        """
        Check if this PII value (or something very similar) was already assigned a token.
        This prevents the same name from getting [PERSON_1] and [PERSON_2].
        """
        text_clean = text.strip().lower()
        for token, original_value in self.pii_map.items():
            if not token.startswith(f"[{label_type}"):
                continue
            original_clean = original_value.strip().lower()
            # Exact match (case-insensitive)
            if text_clean == original_clean:
                return token
            # Substring containment (e.g., "Amit" inside "Amit Sharma")
            if len(text_clean) >= 3 and len(original_clean) >= 3:
                if text_clean in original_clean or original_clean in text_clean:
                    return token
        return None

    def _create_token(self, original_text: str, label_type: str) -> str:
        """Create a new placeholder token and register it in the PII map."""
        token = f"[{label_type}_{self.counters[label_type]}]"
        self.pii_map[token] = original_text
        self.counters[label_type] += 1
        self.entities_found.append({
            "type": label_type,
            "original": original_text,
            "replacement": token,
        })
        return token

    def _replace_in_text(self, text: str, original: str, label_type: str) -> str:
        """Replace a PII match in the text, reusing existing tokens if possible."""
        existing_token = self._get_existing_token(original, label_type)
        if existing_token:
            return text.replace(original, existing_token)
        else:
            token = self._create_token(original, label_type)
            return text.replace(original, token)

    def scrub(self, text: str) -> str:
        """
        Main scrubbing pipeline. Processes text in two phases:
        
        Phase 1 — Regex patterns (high precision):
            Catches structured PII like emails, phones, Aadhaar, PAN, dates, etc.
            These are replaced first so that NLP doesn't misinterpret them.
        
        Phase 2 — NLP entity extraction (names, orgs, locations):
            Uses spaCy NER to find unstructured PII like person names and addresses.
            Applies allowlist filtering and confidence thresholds.
        
        Returns the sanitized text with all PII replaced by placeholders.
        """
        sanitized = text

        # ── Phase 1: Regex-based detection ──────────────────────────────
        # Process regex patterns first. This is important because:
        #   1. Regex is deterministic and precise for structured data
        #   2. It prevents spaCy from mislabeling emails/phones as names
        #   3. We replace matches before NLP sees the text

        for pattern, label_type in self.regex_patterns:
            matches = re.findall(pattern, sanitized)
            for match in matches:
                match = match.strip()
                if not match or len(match) < 3:
                    continue
                    
                # For PIN codes, skip if it looks like it's part of a year (e.g., "2024")
                if label_type == "PIN":
                    if re.match(r'^(19|20)\d{4}$', match):
                        continue
                
                # For PHONE, require minimum 7 meaningful digits
                if label_type == "PHONE":
                    digits_only = re.sub(r'\D', '', match)
                    if len(digits_only) < 7 or len(digits_only) > 15:
                        continue

                # For CREDIT_CARD, require 13-19 digits and pass Luhn check
                if label_type == "CREDIT_CARD":
                    digits_only = re.sub(r'\D', '', match)
                    if len(digits_only) < 13 or len(digits_only) > 19:
                        continue
                    if not self._luhn_check(digits_only):
                        continue

                # For PASSPORT, skip if it looks like a common abbreviation
                if label_type == "PASSPORT":
                    if match[0] in ('V', 'v') and len(match) <= 6:
                        continue

                sanitized = self._replace_in_text(sanitized, match, label_type)

        # ── Phase 2: NLP entity extraction ──────────────────────────────
        # Run spaCy on the ALREADY-SANITIZED text. Since regex tokens like
        # [EMAIL_1] won't be recognized as entities, this is safe.
        
        doc = self.nlp(sanitized)

        for ent in doc.ents:
            target_label = None

            if ent.label_ == "PERSON":
                target_label = "PERSON"
            elif ent.label_ == "ORG":
                target_label = "ORG"
            elif ent.label_ in ("GPE", "LOC", "FAC"):
                target_label = "LOCATION"

            if not target_label:
                continue

            # Skip allowlisted terms (tech skills, section headers, etc.)
            if self._is_ignored(ent.text):
                continue

            # Skip very short entities — usually OCR noise
            if len(ent.text.strip()) <= 2:
                continue

            # Skip entities that are just numbers or already-replaced tokens
            if re.match(r'^[\d\s\[\]_]+$', ent.text):
                continue

            # Skip if the entity looks like it's inside an already-replaced token
            if '[' in ent.text and ']' in ent.text:
                continue

            sanitized = self._replace_in_text(sanitized, ent.text, target_label)

        return sanitized

    def restore(self, text: str) -> str:
        """
        Reverse the scrubbing — replace all placeholder tokens with original values.
        Sorts by token length (longest first) to prevent partial replacements
        (e.g., replacing [PERSON_1] before [PERSON_10]).
        """
        restored = text
        for token in sorted(self.pii_map.keys(), key=len, reverse=True):
            restored = restored.replace(token, self.pii_map[token])
        return restored

    def get_summary(self) -> dict:
        """Return a summary of all PII entities detected."""
        type_counts: dict[str, int] = {}
        for entity in self.entities_found:
            t = entity["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_entities": len(self.entities_found),
            "by_type": type_counts,
            "details": self.entities_found,
        }

    @staticmethod
    def _luhn_check(card_number: str) -> bool:
        """Validate a credit card number using the Luhn algorithm."""
        digits = [int(d) for d in card_number]
        digits.reverse()
        total = 0
        for i, d in enumerate(digits):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        return total % 10 == 0