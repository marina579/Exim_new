#!/usr/bin/env python3
"""
Test script to demonstrate Serper.dev fallback functionality.
This script shows how SerpAPI enricher automatically falls back to Serper.dev.
"""

import os
from dotenv import load_dotenv
from serpapi_enricher import SerpApiEnricher

# Load environment variables
load_dotenv()

def test_fallback():
    """Test the fallback mechanism."""
    print("\n" + "="*70)
    print("Testing SerpAPI → Serper.dev Fallback")
    print("="*70 + "\n")
    
    # Check which API keys are available
    has_serpapi = bool(os.getenv('SERPAPI_API_KEY'))
    has_serper = bool(os.getenv('SERPER_API_KEY'))
    
    print(f"✅ SerpAPI key available: {has_serpapi}")
    print(f"✅ Serper.dev key available: {has_serper}")
    print()
    
    if not has_serpapi and not has_serper:
        print("❌ No API keys found!")
        print("\nPlease set at least one of:")
        print("  - SERPAPI_API_KEY (get from https://serpapi.com/)")
        print("  - SERPER_API_KEY (get from https://serper.dev/)")
        return
    
    # Initialize enricher (will automatically detect available keys)
    try:
        enricher = SerpApiEnricher()
        print("✅ Enricher initialized successfully!\n")
    except Exception as e:
        print(f"❌ Error initializing enricher: {e}")
        return
    
    # Test with a sample company
    test_company = "Marineco Private Limited"
    test_address = "Hyderabad"
    
    print(f"🔍 Testing with: {test_company}, {test_address}")
    print("-" * 70)
    
    try:
        contacts = enricher.find_all_contacts(test_company, test_address)
        
        print(f"\n✅ Found {len(contacts)} contacts")
        
        for idx, contact in enumerate(contacts, 1):
            print(f"\n📞 Contact #{idx}:")
            if contact.get('phone'):
                print(f"   Phone: {contact['phone']}")
            if contact.get('email'):
                print(f"   Email: {contact['email']}")
            if contact.get('contact_name'):
                print(f"   Name: {contact['contact_name']}")
            if contact.get('source_url'):
                print(f"   Source: {contact['source_url']}")
            print(f"   Method: {contact.get('method', 'unknown')}")
        
        print("\n" + "="*70)
        print("✅ Test completed successfully!")
        print("="*70 + "\n")
        
        # Check which provider was used (visible in logs above)
        if has_serpapi and has_serper:
            print("💡 Tip: Check the logs above to see which provider was used.")
            print("   If SerpAPI failed, you'll see 'Falling back to Serper.dev...'")
        
    except Exception as e:
        print(f"\n❌ Error during search: {e}")
        import traceback
        traceback.print_exc()


def test_serper_only():
    """Test using ONLY Serper.dev (bypass SerpAPI)."""
    print("\n" + "="*70)
    print("Testing Serper.dev ONLY (no SerpAPI)")
    print("="*70 + "\n")
    
    serper_key = os.getenv('SERPER_API_KEY')
    if not serper_key:
        print("❌ SERPER_API_KEY not found!")
        print("   Get one from: https://serper.dev/")
        return
    
    # Initialize with ONLY Serper key
    try:
        enricher = SerpApiEnricher(serper_api_key=serper_key)
        print("✅ Enricher initialized with Serper.dev only!\n")
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Quick test
    print("🔍 Testing quick search...")
    contacts = enricher.find_all_contacts("Marineco", "Hyderabad")
    print(f"✅ Found {len(contacts)} contacts using Serper.dev\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--serper-only':
        test_serper_only()
    else:
        test_fallback()
        
        # Optionally test Serper-only mode
        if os.getenv('SERPER_API_KEY'):
            print("\n" + "-"*70)
            print("💡 Want to test Serper-only mode?")
            print("   Run: python test_serper_fallback.py --serper-only")
            print("-"*70 + "\n")

