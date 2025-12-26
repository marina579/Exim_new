#!/usr/bin/env python3
"""
Zoho Token Diagnostic Tool
Helps diagnose why refresh tokens keep expiring
"""

import os
import sys
import requests
import logging
from datetime import datetime
from zoho_crm_service import ZohoCRMService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_token_health():
    """Check Zoho token health and diagnose issues."""
    
    print("\n" + "="*80)
    print("🔍 ZOHO TOKEN DIAGNOSTIC TOOL")
    print("="*80 + "\n")
    
    # Check environment variables
    print("📋 Step 1: Checking Environment Variables")
    print("-" * 80)
    
    client_id = os.getenv('ZOHO_CLIENT_ID')
    client_secret = os.getenv('ZOHO_CLIENT_SECRET')
    refresh_token = os.getenv('ZOHO_REFRESH_TOKEN')
    data_center = os.getenv('ZOHO_DATA_CENTER', 'in')
    
    checks = {
        'ZOHO_CLIENT_ID': (client_id, len(client_id) if client_id else 0),
        'ZOHO_CLIENT_SECRET': (client_secret, len(client_secret) if client_secret else 0),
        'ZOHO_REFRESH_TOKEN': (refresh_token, len(refresh_token) if refresh_token else 0),
        'ZOHO_DATA_CENTER': (data_center, len(data_center) if data_center else 0)
    }
    
    all_present = True
    for key, (value, length) in checks.items():
        if value:
            print(f"  ✅ {key}: Present ({length} chars)")
            if key == 'ZOHO_REFRESH_TOKEN':
                print(f"     Preview: {value[:20]}...{value[-10:]}")
        else:
            print(f"  ❌ {key}: MISSING")
            all_present = False
    
    if not all_present:
        print("\n❌ ERROR: Missing required environment variables!")
        print("   Please set all Zoho credentials in Railway variables.")
        return False
    
    print("\n✅ All environment variables present")
    
    # Test token validity
    print("\n📋 Step 2: Testing Refresh Token")
    print("-" * 80)
    
    try:
        service = ZohoCRMService()
        
        # Try to get access token
        print("  🔄 Attempting to get access token using refresh token...")
        access_token, error = service.get_access_token()
        
        if error:
            print(f"  ❌ FAILED: {error}")
            
            # Analyze error
            if 'invalid_grant' in error.lower() or 'invalid refresh token' in error.lower():
                print("\n  🔍 DIAGNOSIS: Refresh token is invalid")
                print("     Possible causes:")
                print("     1. Token was revoked in Zoho API Console")
                print("     2. Token was regenerated (old one becomes invalid)")
                print("     3. Security settings changed in Zoho account")
                print("     4. Token has spaces or formatting issues")
                
                # Check for spaces
                if ' ' in refresh_token:
                    print("\n  ⚠️  WARNING: Refresh token contains spaces!")
                    print("     This can cause 'invalid_grant' errors.")
                    print("     Remove all spaces from the token in Railway variables.")
                
            elif 'invalid_client' in error.lower():
                print("\n  🔍 DIAGNOSIS: Client ID or Secret is wrong")
                print("     Check ZOHO_CLIENT_ID and ZOHO_CLIENT_SECRET in Railway")
                
            return False
        else:
            print(f"  ✅ SUCCESS: Access token obtained")
            print(f"     Token expires in: {int(service.token_expiry - service.token_expiry) if service.token_expiry else 'N/A'} seconds")
            
            # Test if we can make an API call
            print("\n📋 Step 3: Testing API Call")
            print("-" * 80)
            
            try:
                # Try a simple API call
                api_url = f"{service.api_base_url}/crm/v3/org"
                headers = {
                    'Authorization': f'Zoho-oauthtoken {access_token}',
                    'Content-Type': 'application/json'
                }
                
                response = requests.get(api_url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    print("  ✅ API call successful - Token is working!")
                    org_data = response.json()
                    if 'org' in org_data:
                        print(f"     Organization: {org_data['org'][0].get('company_name', 'N/A')}")
                    return True
                else:
                    print(f"  ⚠️  API call returned status {response.status_code}")
                    print(f"     Response: {response.text[:200]}")
                    return False
                    
            except Exception as e:
                print(f"  ⚠️  API call failed: {str(e)}")
                print("     But token refresh worked, so token is valid")
                return True
                
    except Exception as e:
        print(f"  ❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def check_token_storage():
    """Check if token storage might be causing issues."""
    print("\n📋 Step 4: Checking Token Storage")
    print("-" * 80)
    
    refresh_token = os.getenv('ZOHO_REFRESH_TOKEN', '')
    
    issues = []
    
    # Check for common issues
    if refresh_token.startswith(' ') or refresh_token.endswith(' '):
        issues.append("Token has leading/trailing spaces")
    
    if '\n' in refresh_token or '\r' in refresh_token:
        issues.append("Token contains line breaks")
    
    if len(refresh_token) < 50:
        issues.append("Token seems too short (might be truncated)")
    
    if len(refresh_token) > 500:
        issues.append("Token seems too long (might have extra content)")
    
    if issues:
        print("  ⚠️  Potential issues found:")
        for issue in issues:
            print(f"     • {issue}")
        print("\n  💡 Fix: Update token in Railway, ensure no spaces/line breaks")
    else:
        print("  ✅ Token format looks good")

def check_zoho_security_settings():
    """Provide guidance on Zoho security settings."""
    print("\n📋 Step 5: Zoho Security Settings Check")
    print("-" * 80)
    print("  📝 Manual checks to perform in Zoho:")
    print("     1. Go to: https://api-console.zoho.in/")
    print("     2. Check your app's status")
    print("     3. Look for 'Token Expiry' or 'Token Lifetime' settings")
    print("     4. Check if 'Auto-refresh' is enabled")
    print("     5. Verify no security policies are revoking tokens")
    print("     6. Check if IP restrictions are blocking requests")

def main():
    """Main diagnostic function."""
    success = check_token_health()
    check_token_storage()
    check_zoho_security_settings()
    
    print("\n" + "="*80)
    if success:
        print("✅ DIAGNOSIS COMPLETE: Token is working")
        print("\n💡 If token keeps expiring daily:")
        print("   • Check Zoho API Console for token expiry settings")
        print("   • Verify no security policies are revoking tokens")
        print("   • Check Railway logs for patterns")
        print("   • Ensure token has no spaces/formatting issues")
    else:
        print("❌ DIAGNOSIS COMPLETE: Issues found")
        print("\n💡 Next steps:")
        print("   • Generate new refresh token: python3 generate_zoho_token.py")
        print("   • Update in Railway variables (no spaces!)")
        print("   • Check Zoho API Console for revoked tokens")
    print("="*80 + "\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Diagnostic cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

