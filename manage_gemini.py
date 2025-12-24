#!/usr/bin/env python3
"""
Gemini API Manager - Easy control for Gemini integration.
"""

import os
import sys

def check_quota():
    """Check current Gemini quota status."""
    print("\n🔍 Checking Gemini quota...")
    os.system('python check_gemini_quota.py')

def enable_gemini():
    """Enable Gemini in app.py"""
    print("\n✅ Enabling Gemini...")
    
    # Read app.py
    with open('app.py', 'r') as f:
        content = f.read()
    
    # Replace USE_GEMINI = False with True
    if 'USE_GEMINI = False' in content:
        content = content.replace('USE_GEMINI = False', 'USE_GEMINI = True')
        with open('app.py', 'w') as f:
            f.write(content)
        print("✅ Gemini ENABLED in app.py")
        print("   Restart app to apply changes:")
        print("   python restart_app.sh")
    else:
        print("⚠️  Gemini already enabled or setting not found")

def disable_gemini():
    """Disable Gemini in app.py"""
    print("\n❌ Disabling Gemini...")
    
    # Read app.py
    with open('app.py', 'r') as f:
        content = f.read()
    
    # Replace USE_GEMINI = True with False
    if 'USE_GEMINI = True' in content:
        content = content.replace('USE_GEMINI = True', 'USE_GEMINI = False')
        with open('app.py', 'w') as f:
            f.write(content)
        print("❌ Gemini DISABLED in app.py")
        print("   Restart app to apply changes:")
        print("   python restart_app.sh")
    else:
        print("⚠️  Gemini already disabled or setting not found")

def show_status():
    """Show current Gemini status."""
    print("\n" + "="*70)
    print("GEMINI STATUS")
    print("="*70)
    
    # Check app.py setting
    with open('app.py', 'r') as f:
        content = f.read()
        if 'USE_GEMINI = True' in content:
            print("   App Setting: ✅ ENABLED")
        elif 'USE_GEMINI = False' in content:
            print("   App Setting: ❌ DISABLED")
        else:
            print("   App Setting: ⚠️  UNKNOWN")
    
    # Check API key
    api_key = os.getenv('GEMINI_API_KEY')
    if api_key:
        print(f"   API Key: ✅ SET ({api_key[:20]}...)")
    else:
        print("   API Key: ❌ NOT SET")
    
    print("="*70)

def show_menu():
    """Show interactive menu."""
    print("\n" + "="*70)
    print("GEMINI API MANAGER")
    print("="*70)
    print("\n1. Check Quota Status")
    print("2. Enable Gemini")
    print("3. Disable Gemini")
    print("4. Show Current Status")
    print("5. Upgrade to Paid Tier (instructions)")
    print("6. Exit")
    print("\n" + "="*70)

def show_upgrade_instructions():
    """Show instructions for upgrading to paid tier."""
    print("\n" + "="*70)
    print("HOW TO UPGRADE TO PAID TIER")
    print("="*70)
    print("\n📝 Step 1: Enable Billing")
    print("   → https://console.cloud.google.com/billing")
    print("\n📝 Step 2: Link Credit Card")
    print("   → No charges until you use it!")
    print("\n📝 Step 3: Enable Vertex AI API")
    print("   → https://console.cloud.google.com/apis/library/aiplatform.googleapis.com")
    print("\n📝 Step 4: Create New API Key")
    print("   → https://console.cloud.google.com/apis/credentials")
    print("\n📝 Step 5: Update .env file")
    print("   GEMINI_API_KEY=your-new-paid-api-key")
    print("\n💰 Pricing (Very Cheap!):")
    print("   • $0.075 per 1M input tokens")
    print("   • $0.30 per 1M output tokens")
    print("   • 25 records = ~$0.01")
    print("   • 1,000 records = ~$0.50")
    print("\n" + "="*70)

if __name__ == '__main__':
    if len(sys.argv) > 1:
        # Command-line mode
        cmd = sys.argv[1].lower()
        if cmd == 'check':
            check_quota()
        elif cmd == 'enable':
            enable_gemini()
        elif cmd == 'disable':
            disable_gemini()
        elif cmd == 'status':
            show_status()
        elif cmd == 'upgrade':
            show_upgrade_instructions()
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: python manage_gemini.py [check|enable|disable|status|upgrade]")
    else:
        # Interactive mode
        while True:
            show_menu()
            try:
                choice = input("\nEnter choice (1-6): ").strip()
                
                if choice == '1':
                    check_quota()
                elif choice == '2':
                    enable_gemini()
                elif choice == '3':
                    disable_gemini()
                elif choice == '4':
                    show_status()
                elif choice == '5':
                    show_upgrade_instructions()
                elif choice == '6':
                    print("\n👋 Goodbye!\n")
                    break
                else:
                    print("❌ Invalid choice. Please enter 1-6.")
                
                input("\nPress Enter to continue...")
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!\n")
                break

