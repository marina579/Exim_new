from zoho_crm_service import ZohoCRMService
import logging

logging.basicConfig(level=logging.INFO)

# Your credentials
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# SECURITY: Never hardcode credentials! Use environment variables.
client_id = os.getenv('ZOHO_CLIENT_ID', '')
client_secret = os.getenv('ZOHO_CLIENT_SECRET', '')
refresh_token = os.getenv('ZOHO_REFRESH_TOKEN', '')

if not client_id or not client_secret or not refresh_token:
    print("❌ ERROR: Zoho credentials must be set in environment variables!")
    print("   Set ZOHO_CLIENT_ID, ZOHO_CLIENT_SECRET, and ZOHO_REFRESH_TOKEN in your .env file")
    exit(1)

print("\n" + "="*70)
print("🧪 Testing Zoho CRM Connection")
print("="*70 + "\n")

# Create service
service = ZohoCRMService(
    client_id=client_id,
    client_secret=client_secret,
    refresh_token=refresh_token,
    data_center="in"  # India
)

# Test connection
print("Testing connection to Zoho India (zoho.in)...")
access_token, error = service.get_access_token()

if error:
    print(f"\n❌ Connection Failed!")
    print(f"Error: {error}")
    print("\n📝 Next Steps:")
    print("1. Generate a new refresh token")
    print("2. Visit: https://accounts.zoho.in/oauth/v2/auth?response_type=code&client_id=" + (client_id if client_id else "YOUR_CLIENT_ID") + "&scope=ZohoCRM.modules.ALL&redirect_uri=https://www.zoho.com/crm&access_type=offline&prompt=consent")
else:
    print(f"\n✅ Connection Successful!")
    print(f"Access Token: {access_token[:50]}...")
    
print("\n" + "="*70 + "\n")
