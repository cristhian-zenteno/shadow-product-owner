"""Quick test to verify privacy module imports correctly"""

try:
    from shadow_po import privacy
    print("✓ Privacy module imported successfully")
    
    # Initialize
    privacy.initialize(custom_codenames=["Test Project"])
    print("✓ Privacy scrubber initialized")
    
    # Basic test
    text = "Contact me at test@example.com or at 192.168.1.1"
    scrubbed = privacy.scrub(text)
    print(f"✓ Scrub function works")
    print(f"  Original: {text}")
    print(f"  Scrubbed: {scrubbed}")
    
    # Verify replacements
    assert "test@example.com" not in scrubbed, "Email should be scrubbed"
    assert "192.168.1.1" not in scrubbed, "IP should be scrubbed"
    assert "[EMAIL]" in scrubbed, "EMAIL placeholder should exist"
    assert "[IP_ADDRESS]" in scrubbed, "IP_ADDRESS placeholder should exist"
    print("✓ All basic assertions passed")
    
    print("\n✅ Privacy module is working correctly!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
