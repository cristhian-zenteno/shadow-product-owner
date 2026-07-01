"""
Tests for Privacy Scrubber (Component B)

This is a HARD GATE - nothing proceeds until these tests pass.
"""

import pytest
import logging
from shadow_po import privacy


class TestPrivacyScrubber:
    """Test suite for the privacy scrubber component."""
    
    def setup_method(self):
        """Initialize scrubber before each test."""
        # Initialize with some test codenames
        privacy.initialize(custom_codenames=["Project Titan", "Project Alpha"])
    
    def test_scrub_basic(self):
        """
        Basic scrubbing test: feed a string containing a fake email and fake IP,
        assert neither appears in the output.
        
        This is the required acceptance test from the task.
        """
        # Input with fake email and IP
        text = "Please contact john.doe@example.com or reach the server at 192.168.1.100"
        
        # Scrub the text
        scrubbed = privacy.scrub(text)
        
        # Assert original PII does not appear in output
        assert "john.doe@example.com" not in scrubbed
        assert "192.168.1.100" not in scrubbed
        
        # Assert placeholder tags are present
        assert "[EMAIL]" in scrubbed
        assert "[IP_ADDRESS]" in scrubbed
    
    def test_scrub_email(self):
        """Test email address detection and replacement."""
        text = "Send reports to admin@company.com and backup@test.org"
        scrubbed = privacy.scrub(text)
        
        assert "admin@company.com" not in scrubbed
        assert "backup@test.org" not in scrubbed
        assert "[EMAIL]" in scrubbed
    
    def test_scrub_ip_address(self):
        """Test IP address detection and replacement."""
        text = "Connect to 10.0.0.1 or fallback to 172.16.0.50"
        scrubbed = privacy.scrub(text)
        
        assert "10.0.0.1" not in scrubbed
        assert "172.16.0.50" not in scrubbed
        assert "[IP_ADDRESS]" in scrubbed
    
    def test_scrub_credit_card(self):
        """Test credit card number detection and replacement."""
        text = "Card number is 4532-1488-0343-6467 for testing"
        scrubbed = privacy.scrub(text)
        
        # Credit card should be scrubbed
        assert "4532-1488-0343-6467" not in scrubbed
        assert "[CREDIT_CARD]" in scrubbed
    
    def test_scrub_phone_number(self):
        """Test phone number detection and replacement."""
        text = "Call us at +1-555-123-4567 or 555.987.6543"
        scrubbed = privacy.scrub(text)
        
        # Phone numbers should be scrubbed
        assert "555-123-4567" not in scrubbed
        assert "[PHONE_NUMBER]" in scrubbed
    
    def test_scrub_custom_codenames(self):
        """Test custom project codename scrubbing."""
        text = "Project Titan is our flagship initiative, while Project Alpha is in beta"
        scrubbed = privacy.scrub(text)
        
        # Codenames should be replaced
        assert "Project Titan" not in scrubbed
        assert "Project Alpha" not in scrubbed
        assert "[CODENAME]" in scrubbed
    
    def test_scrub_codenames_case_insensitive(self):
        """Test that codename scrubbing is case-insensitive."""
        text = "The PROJECT TITAN and project alpha teams are collaborating"
        scrubbed = privacy.scrub(text)
        
        # Codenames in any case should be replaced
        assert "PROJECT TITAN" not in scrubbed
        assert "project alpha" not in scrubbed
        assert "[CODENAME]" in scrubbed
    
    def test_scrub_multiple_pii_types(self):
        """Test scrubbing multiple PII types in one text."""
        text = """
        Contact Jane Smith at jane@example.com or call 555-0123.
        Server is at 192.168.1.50. 
        Payment card: 4532148803436467
        This is for Project Titan development.
        """
        scrubbed = privacy.scrub(text)
        
        # All PII should be scrubbed
        assert "jane@example.com" not in scrubbed
        assert "555-0123" not in scrubbed
        assert "192.168.1.50" not in scrubbed
        assert "4532148803436467" not in scrubbed
        assert "Project Titan" not in scrubbed
        
        # Placeholders should be present
        assert "[EMAIL]" in scrubbed
        assert "[PHONE_NUMBER]" in scrubbed
        assert "[IP_ADDRESS]" in scrubbed
        assert "[CREDIT_CARD]" in scrubbed
        assert "[CODENAME]" in scrubbed
    
    def test_scrub_empty_text(self):
        """Test scrubbing empty or whitespace-only text."""
        assert privacy.scrub("") == ""
        assert privacy.scrub("   ") == "   "
        assert privacy.scrub("\n\t") == "\n\t"
    
    def test_scrub_text_without_pii(self):
        """Test that clean text passes through unchanged."""
        text = "This is a clean text with no sensitive information."
        scrubbed = privacy.scrub(text)
        
        # Text should remain the same
        assert scrubbed == text
    
    def test_scrubber_not_initialized(self):
        """Test that calling scrub() without initialization raises error."""
        # Reset the global scrubber
        privacy._scrubber = None
        
        with pytest.raises(RuntimeError, match="Privacy scrubber not initialized"):
            privacy.scrub("some text")
        
        # Re-initialize for other tests
        privacy.initialize(custom_codenames=["Project Titan", "Project Alpha"])
    
    def test_scrub_preserves_sentence_structure(self):
        """Test that scrubbing preserves overall text structure."""
        text = "Please email admin@test.com before connecting to 10.0.0.1 for access."
        scrubbed = privacy.scrub(text)
        
        # The sentence structure should be preserved
        assert scrubbed.startswith("Please email")
        assert "before connecting to" in scrubbed
        assert "for access." in scrubbed
    
    def test_initialize_with_empty_codenames(self):
        """Test initialization with empty codename list."""
        privacy.initialize(custom_codenames=[])
        
        text = "This has an email: test@example.com"
        scrubbed = privacy.scrub(text)
        
        assert "test@example.com" not in scrubbed
        assert "[EMAIL]" in scrubbed
    
    def test_initialize_with_none_codenames(self):
        """Test initialization with None codenames (defaults to empty list)."""
        privacy.initialize(custom_codenames=None)
        
        text = "IP address: 192.168.1.1"
        scrubbed = privacy.scrub(text)
        
        assert "192.168.1.1" not in scrubbed
        assert "[IP_ADDRESS]" in scrubbed
    
    def test_codename_redaction(self, caplog):
        """
        Test custom codename redaction and startup warning (PLAN.md Risk R1).
        
        This is the required verification test from the task:
        - Configure a fake codename, confirm it's redacted
        - Confirm an empty list logs a startup warning
        """
        # Part 1: Test that configured codenames are redacted
        with caplog.at_level(logging.WARNING):
            privacy.initialize(custom_codenames=["Project Titan", "SecretProject"])
        
        text = "The Project Titan team is working with SecretProject developers"
        scrubbed = privacy.scrub(text)
        
        # Verify codenames are redacted
        assert "Project Titan" not in scrubbed
        assert "SecretProject" not in scrubbed
        assert "[CODENAME]" in scrubbed
        
        # Verify no warning was logged when codenames are configured
        warning_messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
        assert not any("No custom codenames configured" in msg for msg in warning_messages)
        
        # Part 2: Test that empty list logs a startup warning
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            privacy.initialize(custom_codenames=[])
        
        # Verify warning was logged for empty codename list
        warning_messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
        assert len(warning_messages) > 0, "Expected startup warning when codenames list is empty"
        assert any("No custom codenames configured" in msg for msg in warning_messages), \
            "Warning message should mention 'No custom codenames configured'"
        assert any("privacy.codenames" in msg for msg in warning_messages), \
            "Warning message should mention 'privacy.codenames' setting"
        
        # Part 3: Test that None (unset) also logs a startup warning
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            privacy.initialize(custom_codenames=None)
        
        # Verify warning was logged for None (unset) codename list
        warning_messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
        assert len(warning_messages) > 0, "Expected startup warning when codenames is None"
        assert any("No custom codenames configured" in msg for msg in warning_messages), \
            "Warning message should mention 'No custom codenames configured' for None value"
    
    def test_initialize_from_settings_with_codenames(self, caplog, tmp_path):
        """
        Test initialization from settings.yaml with custom codenames configured.
        
        Verifies that privacy.initialize_from_settings() correctly loads codenames
        from the settings file and applies them during scrubbing.
        """
        # Create a temporary settings file with custom codenames
        settings_content = """
workspaces_root: "workspaces/"
model:
  name: "nvidia/nemotron-3-ultra-550b-a55b"
  temperature: 0.2
searxng_url: "http://localhost:8080"
whisper:
  model_size: "base"
  device: "cpu"
  compute_type: "int8"
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
privacy:
  codenames: ["Project Titan", "Operation Neptune"]
"""
        settings_file = tmp_path / "settings_with_codenames.yaml"
        settings_file.write_text(settings_content)
        
        # Initialize from settings
        with caplog.at_level(logging.WARNING):
            privacy.initialize_from_settings(str(settings_file))
        
        # Test that the configured codenames are redacted
        text = "Project Titan and Operation Neptune are confidential initiatives"
        scrubbed = privacy.scrub(text)
        
        assert "Project Titan" not in scrubbed
        assert "Operation Neptune" not in scrubbed
        assert "[CODENAME]" in scrubbed
        
        # No warning should be logged when codenames are configured
        warning_messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
        assert not any("No custom codenames configured" in msg for msg in warning_messages)
    
    def test_initialize_from_settings_with_empty_codenames(self, caplog, tmp_path):
        """
        Test initialization from settings.yaml with empty codenames list.
        
        Verifies that the startup warning is logged when privacy.codenames is
        present but empty, per PLAN.md Risk R1 mitigation requirements.
        """
        # Create a temporary settings file with empty codenames
        settings_content = """
workspaces_root: "workspaces/"
model:
  name: "nvidia/nemotron-3-ultra-550b-a55b"
  temperature: 0.2
searxng_url: "http://localhost:8080"
whisper:
  model_size: "base"
  device: "cpu"
  compute_type: "int8"
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
privacy:
  codenames: []
"""
        settings_file = tmp_path / "settings_empty_codenames.yaml"
        settings_file.write_text(settings_content)
        
        # Initialize from settings
        with caplog.at_level(logging.WARNING):
            privacy.initialize_from_settings(str(settings_file))
        
        # Verify startup warning was logged
        warning_messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
        assert len(warning_messages) > 0, "Expected startup warning when codenames list is empty"
        assert any("No custom codenames configured" in msg for msg in warning_messages)
        assert any("privacy.codenames" in msg for msg in warning_messages)
        
        # Standard PII detection should still work
        text = "Contact admin@example.com at 192.168.1.1"
        scrubbed = privacy.scrub(text)
        
        assert "admin@example.com" not in scrubbed
        assert "192.168.1.1" not in scrubbed
        assert "[EMAIL]" in scrubbed
        assert "[IP_ADDRESS]" in scrubbed
    
    def test_initialize_from_settings_without_privacy_section(self, caplog, tmp_path):
        """
        Test initialization from settings.yaml without privacy section.
        
        Verifies that when privacy section is missing (None), the startup warning
        is logged per PLAN.md Risk R1 mitigation requirements.
        """
        # Create a temporary settings file without privacy section
        settings_content = """
workspaces_root: "workspaces/"
model:
  name: "nvidia/nemotron-3-ultra-550b-a55b"
  temperature: 0.2
searxng_url: "http://localhost:8080"
whisper:
  model_size: "base"
  device: "cpu"
  compute_type: "int8"
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
"""
        settings_file = tmp_path / "settings_no_privacy.yaml"
        settings_file.write_text(settings_content)
        
        # Initialize from settings
        with caplog.at_level(logging.WARNING):
            privacy.initialize_from_settings(str(settings_file))
        
        # Verify startup warning was logged
        warning_messages = [record.message for record in caplog.records if record.levelname == "WARNING"]
        assert len(warning_messages) > 0, "Expected startup warning when privacy section is missing"
        assert any("No custom codenames configured" in msg for msg in warning_messages)
        
        # Standard PII detection should still work
        text = "Call 555-1234 or email test@example.com"
        scrubbed = privacy.scrub(text)
        
        assert "555-1234" not in scrubbed
        assert "test@example.com" not in scrubbed
    
    def test_full_fixture_redaction(self):
        """
        HARD GATE TEST - Non-negotiable fixture test from SPECIFY.md §2 / PLAN.md §5
        
        This is the Component B checkpoint - nothing proceeds until this passes.
        
        Tests that a realistic transcript containing multiple types of sensitive
        information (API key, internal IPs, project codename, email) is fully
        scrubbed with none of the original values surviving.
        """
        # Initialize with the Project Titan codename
        privacy.initialize(custom_codenames=["Project Titan"])
        
        # Load the fixture transcript
        import os
        fixture_path = os.path.join(
            os.path.dirname(__file__), 
            "fixtures", 
            "sensitive_transcript.txt"
        )
        with open(fixture_path, "r", encoding="utf-8") as f:
            transcript = f.read()
        
        # Scrub the transcript
        scrubbed = privacy.scrub(transcript)
        
        # CRITICAL ASSERTIONS - None of these must survive scrubbing
        # Fake API key pattern
        assert "sk-proj-abc123xyz789-FAKE_KEY_DO_NOT_USE" not in scrubbed
        assert "abc123xyz789" not in scrubbed
        
        # Internal IP addresses
        assert "192.168.1.100" not in scrubbed
        assert "10.0.0.50" not in scrubbed
        
        # Project codename
        assert "Project Titan" not in scrubbed
        
        # Email address
        assert "john.doe@example.com" not in scrubbed
        
        # Verify placeholder tags ARE present
        assert "[IP_ADDRESS]" in scrubbed
        assert "[CODENAME]" in scrubbed
        assert "[EMAIL]" in scrubbed
        
        # Verify non-sensitive content is preserved
        assert "Meeting Transcript" in scrubbed
        assert "Action items:" in scrubbed
        assert "End of transcript" in scrubbed
    
    def test_scrub_failure_hard_stops(self):
        """
        HARD GATE TEST - Fail-loud behavior from SPECIFY.md §2
        
        Tests that if Presidio or any underlying scrubbing mechanism throws an
        exception, scrub() propagates it as a RuntimeError rather than silently
        returning unscrubbed text.
        
        This ensures the "never silently degrade" boundary is enforced.
        """
        privacy.initialize(custom_codenames=[])
        
        # Create a scrubber instance to directly test the fail-loud behavior
        scrubber = privacy.PrivacyScrubber(custom_codenames=[])
        
        # Mock the Presidio analyzer to throw an exception
        import unittest.mock as mock
        
        with mock.patch.object(
            scrubber.analyzer, 
            'analyze', 
            side_effect=Exception("Simulated Presidio failure")
        ):
            # Attempt to scrub text - should raise RuntimeError, not return unscrubbed
            with pytest.raises(RuntimeError) as exc_info:
                scrubber.scrub("This text contains sensitive data that must not leak")
            
            # Verify the error message is clear about privacy failure
            assert "Privacy scrubbing failed" in str(exc_info.value)
            assert "prevent data leakage" in str(exc_info.value)
            
            # Verify the original exception is chained
            assert "Simulated Presidio failure" in str(exc_info.value.__cause__)
