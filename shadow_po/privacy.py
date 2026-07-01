"""
Privacy Scrubber - Component B

Zero-Trust edge perimeter: all text passes through scrubbing before network calls.
Uses Microsoft Presidio for PII detection + custom regex for project codenames.

This is a HARD GATE component - nothing proceeds until tests pass.
Failure mode: fail loudly, never silently return unscrubbed text.
"""

from typing import List, Optional
import re
import logging

from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

# Configure logger
logger = logging.getLogger(__name__)


class PrivacyScrubber:
    """
    Wraps Presidio analyzer + anonymizer for one-call text scrubbing.
    
    Detects and replaces:
    - Emails → [EMAIL]
    - IP addresses → [IP_ADDRESS]
    - Credit cards → [CREDIT_CARD]
    - Phone numbers → [PHONE_NUMBER]
    - Person names → [PERSON]
    - Locations → [LOCATION]
    - Custom codenames (from settings) → [CODENAME]
    """
    
    def __init__(self, custom_codenames: Optional[List[str]] = None):
        """
        Initialize Presidio engines and custom codename patterns.
        
        Args:
            custom_codenames: List of project codenames to redact (case-insensitive)
        """
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self.custom_codenames = custom_codenames or []
        
        # Compile regex patterns for custom codenames (case-insensitive)
        self.codename_patterns = [
            re.compile(re.escape(codename), re.IGNORECASE)
            for codename in self.custom_codenames
        ]
        
        # Add custom recognizers for patterns Presidio doesn't catch by default
        self._add_custom_recognizers()
    
    def _add_custom_recognizers(self) -> None:
        """
        Add custom pattern recognizers to Presidio for patterns not covered by default.
        
        This includes:
        - API keys (OpenAI-style, generic keys)
        - Secret tokens
        - Private keys
        """
        # API Key patterns (OpenAI-style, AWS, generic)
        api_key_patterns = [
            Pattern(
                name="openai_api_key",
                regex=r"sk-[a-zA-Z0-9\-_]{20,}",
                score=0.9
            ),
            Pattern(
                name="generic_api_key",
                regex=r"(?i)(api[_\-]?key|apikey|api[_\-]?token|access[_\-]?token)['\"\s:=]+[a-zA-Z0-9\-_]{16,}",
                score=0.7
            ),
            Pattern(
                name="bearer_token",
                regex=r"Bearer\s+[a-zA-Z0-9\-_.~+/]+=*",
                score=0.8
            ),
        ]
        
        api_key_recognizer = PatternRecognizer(
            supported_entity="API_KEY",
            patterns=api_key_patterns
        )
        self.analyzer.registry.add_recognizer(api_key_recognizer)
        
        # Secret/Private Key patterns
        secret_patterns = [
            Pattern(
                name="private_key",
                regex=r"-----BEGIN [A-Z\s]+ PRIVATE KEY-----[^-]+-----END [A-Z\s]+ PRIVATE KEY-----",
                score=0.95
            ),
            Pattern(
                name="secret_key",
                regex=r"(?i)(secret[_\-]?key|secretkey)['\"\s:=]+[a-zA-Z0-9\-_]{16,}",
                score=0.8
            ),
        ]
        
        secret_recognizer = PatternRecognizer(
            supported_entity="SECRET",
            patterns=secret_patterns
        )
        self.analyzer.registry.add_recognizer(secret_recognizer)
    
    def scrub(self, text: str) -> str:
        """
        Scrub sensitive information from text.
        
        This is the single entry point for all text before network calls.
        
        Args:
            text: Input text containing potential PII or sensitive information
            
        Returns:
            Scrubbed text with clear placeholder tags
            
        Raises:
            Exception: If scrubbing fails (fail loudly, never return unscrubbed text)
        """
        if not text or not text.strip():
            return text
        
        try:
            # Step 1: Apply custom codename scrubbing first
            scrubbed_text = self._scrub_codenames(text)
            
            # Step 2: Run Presidio analyzer to detect PII entities
            analyzer_results = self.analyzer.analyze(
                text=scrubbed_text,
                language='en',
                entities=[
                    "EMAIL_ADDRESS",
                    "IP_ADDRESS", 
                    "CREDIT_CARD",
                    "PHONE_NUMBER",
                    "PERSON",
                    "LOCATION",
                    "US_SSN",
                    "US_PASSPORT",
                    "CRYPTO",
                    "IBAN_CODE",
                    "API_KEY",      # Custom recognizer
                    "SECRET",       # Custom recognizer
                ]
            )
            
            # Step 3: Anonymize detected entities with clear placeholder tags
            # Define replacement operators for each entity type
            operators = {
                "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
                "IP_ADDRESS": OperatorConfig("replace", {"new_value": "[IP_ADDRESS]"}),
                "CREDIT_CARD": OperatorConfig("replace", {"new_value": "[CREDIT_CARD]"}),
                "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE_NUMBER]"}),
                "PERSON": OperatorConfig("replace", {"new_value": "[PERSON]"}),
                "LOCATION": OperatorConfig("replace", {"new_value": "[LOCATION]"}),
                "US_SSN": OperatorConfig("replace", {"new_value": "[SSN]"}),
                "US_PASSPORT": OperatorConfig("replace", {"new_value": "[PASSPORT]"}),
                "CRYPTO": OperatorConfig("replace", {"new_value": "[CRYPTO_ADDRESS]"}),
                "IBAN_CODE": OperatorConfig("replace", {"new_value": "[IBAN]"}),
                "API_KEY": OperatorConfig("replace", {"new_value": "[API_KEY]"}),
                "SECRET": OperatorConfig("replace", {"new_value": "[SECRET]"}),
            }
            
            anonymized_result = self.anonymizer.anonymize(
                text=scrubbed_text,
                analyzer_results=analyzer_results,
                operators=operators
            )
            
            return anonymized_result.text
            
        except Exception as e:
            # Fail loudly - never silently return unscrubbed text
            raise RuntimeError(
                f"Privacy scrubbing failed: {str(e)}. "
                "Pipeline stopped to prevent data leakage."
            ) from e
    
    def _scrub_codenames(self, text: str) -> str:
        """
        Replace custom project codenames with [CODENAME] placeholder.
        
        Args:
            text: Input text
            
        Returns:
            Text with codenames replaced
        """
        scrubbed = text
        for pattern in self.codename_patterns:
            scrubbed = pattern.sub("[CODENAME]", scrubbed)
        return scrubbed


# Global scrubber instance (initialized with settings at app startup)
_scrubber: Optional[PrivacyScrubber] = None


def initialize(custom_codenames: Optional[List[str]] = None) -> None:
    """
    Initialize the global privacy scrubber instance.
    
    Must be called once at application startup before any scrub() calls.
    
    IMPORTANT: Per PLAN.md Risk R1, this function warns loudly when no custom
    codenames are configured, ensuring the gap is visible rather than silent.
    
    Args:
        custom_codenames: List of project codenames to redact
    """
    global _scrubber
    _scrubber = PrivacyScrubber(custom_codenames=custom_codenames)
    
    # Risk R1 mitigation: Warn loudly if no custom codenames are configured
    # This ensures operators are aware that organization-specific codenames
    # won't be scrubbed unless explicitly configured in settings.yaml
    if not custom_codenames:
        logger.warning(
            "⚠️  PRIVACY WARNING: No custom codenames configured! "
            "Organization-specific project codenames will NOT be redacted. "
            "Configure 'privacy.codenames' in settings.yaml to enable custom codename scrubbing. "
            "(Presidio still detects standard PII: emails, IPs, phone numbers, credit cards, etc.)"
        )


def initialize_from_settings(settings_path: str = "settings.yaml") -> None:
    """
    Initialize the global privacy scrubber from settings.yaml configuration.
    
    This is the recommended initialization method for application startup.
    Loads custom codenames from the 'privacy.codenames' field in settings.yaml.
    
    Args:
        settings_path: Path to settings.yaml file (default: "settings.yaml")
        
    Raises:
        FileNotFoundError: If settings.yaml does not exist
        ValueError: If settings.yaml is invalid
    """
    from shadow_po.config import load_settings
    
    settings = load_settings(settings_path)
    
    # Extract custom codenames from privacy config
    codenames = []
    if settings.privacy and settings.privacy.codenames:
        codenames = settings.privacy.codenames
    
    initialize(custom_codenames=codenames)


def scrub(text: str) -> str:
    """
    One-call text scrubbing function - the public API.
    
    Runs Presidio's analyzer + anonymizer and returns text with detected
    emails, IPs, credit cards, and credential-shaped strings replaced by
    clear placeholder tags (e.g. [EMAIL], [IP_ADDRESS]).
    
    This is the HARD GATE before any network calls.
    
    Args:
        text: Input text containing potential PII
        
    Returns:
        Scrubbed text with placeholder tags
        
    Raises:
        RuntimeError: If scrubber not initialized or scrubbing fails
    """
    if _scrubber is None:
        raise RuntimeError(
            "Privacy scrubber not initialized. "
            "Call privacy.initialize() or privacy.initialize_from_settings() at app startup."
        )
    
    return _scrubber.scrub(text)
