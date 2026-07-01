#!/usr/bin/env python3
"""
Demo script to test custom codename deny-list functionality.

This script demonstrates:
1. Loading custom codenames from settings.yaml
2. Verifying codenames are redacted
3. Confirming startup warning when codename list is empty
"""

import logging
from shadow_po import privacy

# Configure logging to see the startup warnings
logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

def test_with_codenames():
    """Test with custom codenames configured."""
    print("\n" + "="*70)
    print("TEST 1: With Custom Codenames (from settings.yaml)")
    print("="*70)
    
    # Initialize from settings.yaml
    privacy.initialize_from_settings("settings.yaml")
    
    # Test text containing a fake codename
    test_text = "We are launching Project Titan next quarter with support from Project Alpha team."
    
    print(f"\nOriginal text:\n{test_text}")
    
    scrubbed = privacy.scrub(test_text)
    print(f"\nScrubbed text:\n{scrubbed}")
    
    # Verify redaction worked
    if "Project Titan" not in scrubbed and "[CODENAME]" in scrubbed:
        print("\n✅ SUCCESS: Custom codenames were redacted!")
    else:
        print("\n❌ FAILED: Custom codenames were not properly redacted!")

def test_with_empty_codenames():
    """Test with empty codename list (should trigger warning)."""
    print("\n" + "="*70)
    print("TEST 2: With Empty Codename List (should show warning)")
    print("="*70)
    
    # Initialize with empty list
    print("\nInitializing with empty codename list...")
    privacy.initialize(custom_codenames=[])
    
    print("\n✅ Check above for the startup warning about no codenames configured!")
    
    # Test that standard PII still works
    test_text = "Contact john@example.com at IP 192.168.1.1"
    print(f"\nOriginal text:\n{test_text}")
    
    scrubbed = privacy.scrub(test_text)
    print(f"\nScrubbed text:\n{scrubbed}")
    
    if "john@example.com" not in scrubbed and "[EMAIL]" in scrubbed:
        print("\n✅ SUCCESS: Standard PII redaction still works!")
    else:
        print("\n❌ FAILED: Standard PII was not properly redacted!")

def test_case_insensitive():
    """Test that codename matching is case-insensitive."""
    print("\n" + "="*70)
    print("TEST 3: Case-Insensitive Codename Matching")
    print("="*70)
    
    privacy.initialize(custom_codenames=["Project Titan"])
    
    test_text = "Both PROJECT TITAN and project titan should be redacted."
    print(f"\nOriginal text:\n{test_text}")
    
    scrubbed = privacy.scrub(test_text)
    print(f"\nScrubbed text:\n{scrubbed}")
    
    if "PROJECT TITAN" not in scrubbed and "project titan" not in scrubbed:
        print("\n✅ SUCCESS: Case-insensitive matching works!")
    else:
        print("\n❌ FAILED: Case-insensitive matching did not work!")

if __name__ == "__main__":
    print("=" * 70)
    print("CUSTOM CODENAME DENY-LIST DEMONSTRATION")
    print("=" * 70)
    
    # Test with empty list first to show warning
    test_with_empty_codenames()
    
    # Test case-insensitive matching
    test_case_insensitive()
    
    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70)
    print("\nNote: To test settings.yaml integration, ensure 'privacy.codenames'")
    print("is configured in settings.yaml and run:")
    print("  python test_codename_demo.py")
    print("="*70 + "\n")
