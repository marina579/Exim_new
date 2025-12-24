#!/usr/bin/env python3
"""
Zoho Refresh Token Generator
Easy-to-use script to generate a Zoho CRM refresh token
"""

import requests
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse

print("\n" + "="*80)
print("🔑 ZOHO CRM REFRESH TOKEN GENERATOR")
print("="*80 + "\n")

# Your credentials
CLIENT_ID = "1000.6CD571WYE0T62GTP6TAS2L4KZDHGOG"
CLIENT_SECRET = "1291d50e4263d9dd59f84b5dc9563b77a35304555e"
DATA_CENTER = "in"  # India

# Set URLs based on data center
if DATA_CENTER == "in":
    AUTH_URL = "https://accounts.zoho.in/oauth/v2/auth"
    TOKEN_URL = "https://accounts.zoho.in/oauth/v2/token"
else:
    AUTH_URL = "https://accounts.zoho.com/oauth/v2/auth"
    TOKEN_URL = "https://accounts.zoho.com/oauth/v2/token"

REDIRECT_URI = "https://www.zoho.com/crm"
SCOPES = "ZohoCRM.modules.ALL,ZohoCRM.settings.ALL"

print("📋 Your Zoho Configuration:")
print(f"   Client ID: {CLIENT_ID}")
print(f"   Data Center: {DATA_CENTER.upper()} (.{DATA_CENTER})")
print(f"   Scopes: {SCOPES}")
print("\n" + "-"*80 + "\n")

# Step 1: Generate authorization URL
auth_params = {
    'response_type': 'code',
    'client_id': CLIENT_ID,
    'scope': SCOPES,
    'redirect_uri': REDIRECT_URI,
    'access_type': 'offline',
    'prompt': 'consent'
}

authorization_url = f"{AUTH_URL}?{urlencode(auth_params)}"

print("📌 STEP 1: Get Authorization Code")
print("-" * 80)
print("\n1. Copy this URL and open it in your browser:\n")
print(f"   {authorization_url}\n")
print("2. Log in to your Zoho account and authorize the app")
print("3. You'll be redirected to a URL that looks like:")
print(f"   {REDIRECT_URI}?code=XXXXX&location=...\n")
print("4. Copy the ENTIRE redirect URL and paste it below\n")

# Try to open browser automatically
try:
    print("🌐 Opening browser automatically...")
    webbrowser.open(authorization_url)
    print("✅ Browser opened!")
except:
    print("⚠️  Could not open browser automatically. Please open the URL manually.")

print("\n" + "-"*80)

# Get the redirect URL from user
redirect_url = input("\n📝 Paste the full redirect URL here: ").strip()

# Extract the code
try:
    parsed_url = urlparse(redirect_url)
    query_params = parse_qs(parsed_url.query)
    code = query_params.get('code', [None])[0]
    
    if not code:
        print("\n❌ Error: Could not find 'code' in the URL")
        print("Please make sure you copied the complete redirect URL")
        exit(1)
    
    print(f"\n✅ Authorization code extracted: {code[:20]}...")
    
except Exception as e:
    print(f"\n❌ Error parsing URL: {str(e)}")
    exit(1)

print("\n" + "-"*80)
print("\n📌 STEP 2: Exchange Code for Refresh Token")
print("-" * 80 + "\n")

# Step 2: Exchange code for refresh token
token_params = {
    'code': code,
    'client_id': CLIENT_ID,
    'client_secret': CLIENT_SECRET,
    'redirect_uri': REDIRECT_URI,
    'grant_type': 'authorization_code'
}

print("🔄 Requesting refresh token from Zoho...")

try:
    response = requests.post(TOKEN_URL, data=token_params, timeout=15)
    
    if response.status_code == 200:
        data = response.json()
        
        if 'error' in data:
            print(f"\n❌ Error: {data.get('error')}")
            print(f"   Description: {data.get('error_description', 'No description')}")
            exit(1)
        
        refresh_token = data.get('refresh_token')
        access_token = data.get('access_token')
        
        if not refresh_token:
            print(f"\n❌ Error: No refresh token in response")
            print(f"Response: {data}")
            exit(1)
        
        print("\n" + "="*80)
        print("✅ SUCCESS! Here are your tokens:")
        print("="*80 + "\n")
        
        print(f"🔑 Refresh Token (SAVE THIS!):")
        print(f"   {refresh_token}\n")
        
        print(f"🎫 Access Token (temporary, expires in 1 hour):")
        print(f"   {access_token[:50]}...\n")
        
        print("="*80)
        print("\n📝 Next Steps:")
        print("="*80 + "\n")
        
        print("1. Save your Refresh Token in the .env file:")
        print(f"   ZOHO_REFRESH_TOKEN={refresh_token}\n")
        
        print("2. Or configure it in the web UI:")
        print("   Go to: http://127.0.0.1:5000/zoho_config")
        print(f"   Paste this refresh token: {refresh_token}\n")
        
        print("3. Test the connection:")
        print("   ./venv/bin/python test_zoho.py\n")
        
        print("="*80 + "\n")
        
        # Offer to update .env automatically
        update = input("Would you like to update the .env file automatically? (y/n): ").strip().lower()
        
        if update == 'y':
            try:
                with open('.env', 'r') as f:
                    env_content = f.read()
                
                # Update or add refresh token
                if 'ZOHO_REFRESH_TOKEN=' in env_content:
                    # Replace existing
                    lines = env_content.split('\n')
                    new_lines = []
                    for line in lines:
                        if line.startswith('ZOHO_REFRESH_TOKEN='):
                            new_lines.append(f'ZOHO_REFRESH_TOKEN={refresh_token}')
                        else:
                            new_lines.append(line)
                    env_content = '\n'.join(new_lines)
                else:
                    # Add new
                    env_content += f'\nZOHO_REFRESH_TOKEN={refresh_token}\n'
                
                with open('.env', 'w') as f:
                    f.write(env_content)
                
                print("\n✅ .env file updated successfully!")
                print("Restart your app to use the new token.\n")
                
            except Exception as e:
                print(f"\n❌ Error updating .env: {str(e)}")
                print("Please update it manually.\n")
        
    else:
        print(f"\n❌ Error: Zoho API returned status {response.status_code}")
        print(f"Response: {response.text}")
        exit(1)
        
except requests.exceptions.RequestException as e:
    print(f"\n❌ Network error: {str(e)}")
    exit(1)
except Exception as e:
    print(f"\n❌ Unexpected error: {str(e)}")
    exit(1)

