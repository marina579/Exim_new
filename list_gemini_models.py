"""
List available Gemini models.
"""

import os
from google import genai

os.environ['GEMINI_API_KEY'] = 'AIzaSyDMMMWhWAi1jPYqcOFPo0lIYlTPHwNjQ0o'

client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

print("Available Gemini Models:")
print("=" * 70)

for model in client.models.list():
    print(f"✅ {model.name}")
    print()

