"""
Check Gemini API quota and available models.
"""
import os
from google import genai
from google.genai import types

# Set API key
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', 'AIzaSyDMMMWhWAi1jPYqcOFPo0lIYlTPHwNjQ0o')

client = genai.Client(api_key=GEMINI_API_KEY)

print("="*70)
print("GEMINI API STATUS CHECK")
print("="*70)

# Test API connection
try:
    print("\n✅ Testing API connection...")
    response = client.models.generate_content(
        model='models/gemini-2.0-flash-exp',
        contents='Say "API Working" if you can read this'
    )
    print(f"✅ API Status: WORKING")
    print(f"   Response: {response.text[:100]}")
except Exception as e:
    print(f"❌ API Status: ERROR")
    print(f"   Error: {str(e)[:200]}")
    
    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
        print("\n⚠️  QUOTA EXHAUSTED - See options below")

# List available models
print("\n" + "="*70)
print("AVAILABLE GEMINI MODELS")
print("="*70)

try:
    models = client.models.list()
    
    print("\n🔹 FREE Tier Models:")
    free_models = []
    for model in models:
        if 'flash' in model.name.lower() or 'pro' in model.name.lower():
            free_models.append(model.name)
            print(f"   • {model.name}")
    
    if not free_models:
        print("   (No models found - may need to check API key)")
        
except Exception as e:
    print(f"❌ Error listing models: {str(e)[:200]}")

# Show quota info
print("\n" + "="*70)
print("QUOTA INFORMATION")
print("="*70)
print("\n🆓 FREE TIER (Current):")
print("   • 15 requests per minute")
print("   • 1,500 requests per day")
print("   • 1 million tokens per day")

print("\n💰 PAID TIER (Pay-as-you-go):")
print("   • No daily limits")
print("   • 1,000 requests per minute")
print("   • $0.075 per 1M input tokens")
print("   • $0.30 per 1M output tokens")

print("\n🔗 Useful Links:")
print("   • Check usage: https://aistudio.google.com/app/apikey")
print("   • Upgrade: https://console.cloud.google.com/billing")
print("   • Pricing: https://ai.google.dev/pricing")
print("\n" + "="*70)
