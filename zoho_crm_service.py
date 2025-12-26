"""
Zoho CRM Service - Handle all Zoho CRM operations
Supports India Data Center (zoho.in)
"""

import os
import time
import requests
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ZohoCRMService:
    """Service to handle Zoho CRM API operations with automatic token management."""
    
    # Singleton instance for token reuse
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Implement singleton pattern for token reuse."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, client_id: str = None, client_secret: str = None, 
                 refresh_token: str = None, data_center: str = "in"):
        """
        Initialize Zoho CRM Service.
        
        Args:
            client_id: Zoho Client ID
            client_secret: Zoho Client Secret
            refresh_token: Zoho Refresh Token
            data_center: Data center - 'in' for India, 'com' for US, 'eu' for Europe
        """
        # Only initialize once (singleton)
        if hasattr(self, '_initialized'):
            return
        
        self.client_id = client_id or os.getenv('ZOHO_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('ZOHO_CLIENT_SECRET')
        self.refresh_token = refresh_token or os.getenv('ZOHO_REFRESH_TOKEN')
        self.data_center = data_center or os.getenv('ZOHO_DATA_CENTER', 'in')
        
        # Set endpoints based on data center - ALWAYS use India for this app
        if self.data_center == 'in':
            self.auth_url = "https://accounts.zoho.in/oauth/v2/token"
            self.api_base_url = "https://www.zohoapis.in"
        elif self.data_center == 'eu':
            self.auth_url = "https://accounts.zoho.eu/oauth/v2/token"
            self.api_base_url = "https://www.zohoapis.eu"
        elif self.data_center == 'au':
            self.auth_url = "https://accounts.zoho.com.au/oauth/v2/token"
            self.api_base_url = "https://www.zohoapis.com.au"
        else:  # Default to US
            self.auth_url = "https://accounts.zoho.com/oauth/v2/token"
            self.api_base_url = "https://www.zohoapis.com"
        
        # Token cache
        self.access_token = None
        self.token_expiry = None  # Timestamp when token expires
        self.token_lifetime = 3300  # 55 minutes (tokens last 1 hour, refresh before expiry)
        
        self._initialized = True
    
    def is_token_valid(self) -> bool:
        """
        Check if the current access token is still valid.
        
        Returns:
            True if token exists and hasn't expired
        """
        if not self.access_token or not self.token_expiry:
            return False
        
        # Check if token is still valid (with 5 minute buffer)
        return time.time() < (self.token_expiry - 300)
    
    def get_access_token(self, force_refresh: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Get a valid access token. Uses cached token if still valid, otherwise refreshes.
        
        Args:
            force_refresh: Force refresh even if cached token is valid
        
        Returns:
            Tuple of (access_token, error_message)
        """
        # Check if we have a valid cached token
        if not force_refresh and self.is_token_valid():
            logger.info(f"✅ Using cached access token (expires in {int(self.token_expiry - time.time())}s)")
            return self.access_token, None
        
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            error = "Missing credentials. Please configure Client ID, Client Secret, and Refresh Token."
            logger.error(f"❌ {error}")
            return None, error
        
        try:
            logger.info(f"🔄 Requesting new access token from Zoho ({self.data_center})...")
            
            params = {
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'refresh_token'
            }
            
            response = requests.post(self.auth_url, params=params, timeout=15)
            
            logger.info(f"📡 Zoho Auth Response Status: {response.status_code}")
            
            if response.status_code != 200:
                error_msg = f"Zoho API returned {response.status_code}: {response.text}"
                logger.error(f"❌ {error_msg}")
                return None, error_msg
            
            data = response.json()
            
            # Log full response for debugging
            logger.debug(f"📋 Full Zoho auth response: {data}")
            
            # Check for errors in response
            if 'error' in data:
                error_code = data.get('error', 'unknown_error')
                error_description = data.get('error_description', '')
                
                # Log all available error fields
                logger.error(f"❌ Zoho error detected:")
                logger.error(f"   Error code: {error_code}")
                logger.error(f"   Error description: {error_description}")
                logger.error(f"   Full response: {data}")
                
                # Build detailed error message
                if error_description:
                    error_msg = f"Zoho error: {error_code} - {error_description}"
                else:
                    # Try to get more details from response
                    error_details = (data.get('error_description') or 
                                   data.get('message') or 
                                   data.get('details') or 
                                   data.get('error_uri') or
                                   response.text)
                    if error_details and error_details != response.text:
                        error_msg = f"Zoho error: {error_code} - {error_details}"
                    else:
                        error_msg = f"Zoho error: {error_code}"
                
                # Provide helpful error messages based on error code
                if error_code == 'invalid_code' or 'invalid_code' in str(error_code).lower():
                    error_msg = "Invalid refresh token. Please generate a new one from Zoho API Console."
                elif error_code == 'invalid_client' or 'invalid_client' in str(error_code).lower():
                    error_msg = "Invalid Client ID or Client Secret. Please check your credentials."
                elif error_code == 'invalid_grant':
                    error_msg = "Invalid refresh token or token expired. Please generate a new refresh token."
                elif error_code == 'general_error' or error_code == 'access_denied':
                    # Try to extract more details from description or other fields
                    if error_description:
                        error_msg = f"Zoho API error: {error_description}"
                    elif data.get('message'):
                        error_msg = f"Zoho API error: {data.get('message')}"
                    else:
                        error_msg = f"Zoho API error: {error_code}. Check Railway logs for full details. Common causes: invalid credentials, expired token, or insufficient API permissions."
                
                return None, error_msg
            
            access_token = data.get('access_token')
            
            if not access_token:
                error_msg = f"No access token in response: {data}"
                logger.error(f"❌ {error_msg}")
                return None, error_msg
            
            # Cache the token with expiry time
            self.access_token = access_token
            self.token_expiry = time.time() + self.token_lifetime
            
            logger.info(f"✅ Successfully obtained Zoho access token (valid for {self.token_lifetime}s)")
            
            return access_token, None
            
        except requests.exceptions.Timeout:
            error_msg = "Request timed out. Please check your internet connection."
            logger.error(f"❌ {error_msg}")
            return None, error_msg
        except requests.exceptions.ConnectionError:
            error_msg = "Connection error. Please check your internet connection."
            logger.error(f"❌ {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
    
    def check_duplicate_in_zoho(self, email: str = None, phone: str = None) -> Tuple[bool, Optional[Dict]]:
        """
        Check if a contact already exists in Zoho CRM by email or phone.
        
        Args:
            email: Email address to search
            phone: Phone number to search
        
        Returns:
            Tuple of (exists: bool, existing_lead: Optional[Dict])
        """
        if not email and not phone:
            return False, None
        
        # Get valid access token
        access_token, error = self.get_access_token()
        if error:
            logger.error(f"❌ Cannot check duplicates: {error}")
            return False, None
        
        try:
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Search by email first (more reliable)
            if email:
                search_url = f"{self.api_base_url}/crm/v3/Leads/search"
                params = {
                    'criteria': f'(Email:equals:{email})'
                }
                
                logger.info(f"🔍 Checking Zoho for duplicate: {email}")
                response = requests.get(search_url, headers=headers, params=params, timeout=15)
                
                if response.status_code == 200:
                    result = response.json()
                    data = result.get('data', [])
                    
                    if data:
                        existing_lead = data[0]  # Get first match
                        logger.info(f"✅ Found existing lead in Zoho: {existing_lead.get('id')} - {existing_lead.get('Full_Name')}")
                        return True, existing_lead
            
            # Search by phone if email search didn't find anything
            if phone:
                search_url = f"{self.api_base_url}/crm/v3/Leads/search"
                # Clean phone number (remove spaces, dashes, etc.)
                clean_phone = ''.join(filter(str.isdigit, phone))[-10:]  # Last 10 digits
                params = {
                    'criteria': f'(Phone:equals:{phone})'
                }
                
                logger.info(f"🔍 Checking Zoho for duplicate: {phone}")
                response = requests.get(search_url, headers=headers, params=params, timeout=15)
                
                if response.status_code == 200:
                    result = response.json()
                    data = result.get('data', [])
                    
                    if data:
                        existing_lead = data[0]
                        logger.info(f"✅ Found existing lead in Zoho: {existing_lead.get('id')} - {existing_lead.get('Full_Name')}")
                        return True, existing_lead
            
            logger.info(f"✅ No duplicate found in Zoho")
            return False, None
            
        except Exception as e:
            logger.error(f"❌ Error checking duplicates in Zoho: {str(e)}")
            return False, None
    
    def push_to_zoho(self, contact_data: Dict, retry_on_401: bool = True, check_duplicates: bool = True) -> Tuple[bool, str, Optional[str]]:
        """
        Push a single contact to Zoho CRM as a Lead with automatic 401 retry and duplicate checking.
        
        Args:
            contact_data: Dictionary with keys:
                - first_name (required)
                - last_name (optional, defaults to '.')
                - company (optional, defaults to 'N/A')
                - email (optional)
                - phone (optional)
                - description (optional)
            retry_on_401: Automatically retry once on 401 Unauthorized
            check_duplicates: Check if contact already exists in Zoho before pushing
        
        Returns:
            Tuple of (success: bool, message: str, lead_id: Optional[str])
        """
        # Check for duplicates first if enabled
        if check_duplicates:
            email = contact_data.get('email')
            phone = contact_data.get('phone')
            
            exists, existing_lead = self.check_duplicate_in_zoho(email=email, phone=phone)
            
            if exists:
                lead_id = existing_lead.get('id')
                lead_name = existing_lead.get('Full_Name', 'Unknown')
                skip_msg = f"⏭️  Skipped: Contact already exists in Zoho (ID: {lead_id}, Name: {lead_name})"
                logger.info(skip_msg)
                return False, skip_msg, lead_id
        
        # Get valid access token (uses cache if available)
        access_token, error = self.get_access_token()
        if error:
            return False, error, None
        
        try:
            # Prepare lead data with fallbacks
            lead = {
                'First_Name': contact_data.get('first_name', 'Unknown'),
                'Last_Name': contact_data.get('last_name') or '.',  # Zoho requires Last_Name
                'Company': contact_data.get('company') or 'N/A',  # Fallback to N/A if no company
            }
            
            # Add optional fields
            if contact_data.get('email'):
                lead['Email'] = contact_data['email']
            
            if contact_data.get('phone'):
                lead['Phone'] = contact_data['phone']
            
            if contact_data.get('description'):
                lead['Description'] = contact_data['description']
            else:
                lead['Description'] = f"Imported from Contact Enricher on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            lead['Lead_Source'] = 'Contact Enrichment System'
            
            # Prepare API request
            url = f"{self.api_base_url}/crm/v3/Leads"
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'data': [lead],
                'trigger': ['approval', 'workflow', 'blueprint']
            }
            
            logger.info(f"📤 Pushing lead to Zoho: {lead.get('First_Name')} {lead.get('Last_Name')} - {lead.get('Company')}")
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            logger.info(f"📡 Zoho CRM Response Status: {response.status_code}")
            
            # Handle 429 Rate Limit - return clear error message
            if response.status_code == 429:
                error_data = response.json() if response.text else {}
                rate_limit_msg = error_data.get('message', 'Rate limit exceeded (429 Too Many Requests)')
                logger.error(f"❌ Rate limit exceeded: {rate_limit_msg}")
                return False, f"Zoho API error 429: {rate_limit_msg}", None
            
            # Handle 401 Unauthorized - token expired, retry once with fresh token
            if response.status_code == 401 and retry_on_401:
                logger.warning(f"⚠️  Got 401 Unauthorized, refreshing token and retrying...")
                
                # Force refresh the token
                access_token, error = self.get_access_token(force_refresh=True)
                if error:
                    return False, f"Token refresh failed: {error}", None
                
                # Retry with new token
                headers['Authorization'] = f'Zoho-oauthtoken {access_token}'
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                logger.info(f"📡 Retry Response Status: {response.status_code}")
            
            if response.status_code == 201:
                result = response.json()
                data = result.get('data', [])
                
                if data and data[0].get('code') == 'SUCCESS':
                    lead_id = data[0].get('details', {}).get('id')
                    success_msg = f"✅ Successfully created lead in Zoho CRM (ID: {lead_id})"
                    logger.info(success_msg)
                    return True, success_msg, lead_id
                else:
                    error_msg = f"Failed to create lead: {data[0].get('message', 'Unknown error')}"
                    logger.error(f"❌ {error_msg}")
                    return False, error_msg, None
            elif response.status_code == 429:
                # Rate limit exceeded
                error_data = response.json() if response.text else {}
                rate_limit_msg = error_data.get('message', 'Rate limit exceeded (429 Too Many Requests)')
                logger.error(f"❌ Rate limit exceeded: {rate_limit_msg}")
                return False, f"Zoho API error 429: {rate_limit_msg}", None
            else:
                # Extract error message from response if available
                error_msg = f"Zoho API error {response.status_code}"
                try:
                    error_data = response.json()
                    logger.error(f"❌ Zoho API error response: {error_data}")
                    
                    if isinstance(error_data, dict):
                        # Try multiple fields for error message
                        msg = (error_data.get('message') or 
                               error_data.get('error_description') or 
                               error_data.get('error') or 
                               error_data.get('details', {}).get('message') if isinstance(error_data.get('details'), dict) else None or
                               response.text)
                        
                        code = error_data.get('code') or error_data.get('error', '')
                        
                        # Check for nested error structure
                        if 'data' in error_data and isinstance(error_data['data'], list) and len(error_data['data']) > 0:
                            first_item = error_data['data'][0]
                            if isinstance(first_item, dict):
                                msg = first_item.get('message', msg)
                                code = first_item.get('code', code)
                        
                        if code:
                            error_msg = f"Zoho API error {response.status_code}: {code}: {msg}"
                        else:
                            error_msg = f"Zoho API error {response.status_code}: {msg}"
                except Exception as parse_error:
                    logger.error(f"❌ Failed to parse Zoho error response: {parse_error}")
                    error_msg = f"Zoho API error {response.status_code}: {response.text[:200]}"
                
                logger.error(f"❌ {error_msg}")
                return False, error_msg, None
                
        except Exception as e:
            error_msg = f"Error pushing to Zoho: {str(e)}"
            logger.error(f"❌ {error_msg}")
            return False, error_msg, None
    
    def push_bulk_to_zoho(self, contacts: List[Dict], batch_size: int = 100, check_duplicates: bool = True) -> Dict:
        """
        Push multiple contacts to Zoho CRM in batches with duplicate checking.
        
        Args:
            contacts: List of contact dictionaries
            batch_size: Number of contacts per batch (max 100)
            check_duplicates: Check each contact for duplicates before pushing
        
        Returns:
            Dictionary with success count, failure count, skipped count, and details
        """
        # Get fresh access token
        access_token, error = self.get_access_token()
        if error:
            logger.error(f"❌ Cannot get access token for bulk push: {error}")
            return {
                'success': False,
                'total_pushed': 0,
                'total_failed': len(contacts),
                'total_skipped': 0,
                'successful_contacts': [],
                'failed_contacts': [],
                'skipped_contacts': [],
                'error': error
            }
        
        total_pushed = 0
        total_failed = 0
        total_skipped = 0
        failed_contacts = []
        skipped_contacts = []
        successful_contacts = []  # Track successful contacts with lead_ids
        
        try:
            url = f"{self.api_base_url}/crm/v3/Leads"
            
            headers = {
                'Authorization': f'Zoho-oauthtoken {access_token}',
                'Content-Type': 'application/json'
            }
            
            # Filter out duplicates if check_duplicates is enabled
            contacts_to_push = []
            
            if check_duplicates:
                logger.info(f"🔍 Checking {len(contacts)} contacts for duplicates in Zoho...")
                for contact in contacts:
                    email = contact.get('email')
                    phone = contact.get('phone')
                    
                    exists, existing_lead = self.check_duplicate_in_zoho(email=email, phone=phone)
                    
                    if exists:
                        total_skipped += 1
                        lead_id = existing_lead.get('id')
                        skipped_contacts.append({
                            'contact': contact,
                            'reason': f"Already exists (ID: {lead_id})",
                            'lead_id': lead_id
                        })
                        logger.info(f"⏭️  Skipping duplicate: {contact.get('first_name')} {contact.get('last_name')} (ID: {lead_id})")
                    else:
                        contacts_to_push.append(contact)
                
                logger.info(f"📊 {len(contacts_to_push)} new contacts to push, {total_skipped} duplicates skipped")
            else:
                contacts_to_push = contacts
            
            # Process in batches
            for i in range(0, len(contacts_to_push), batch_size):
                batch = contacts_to_push[i:i+batch_size]
                
                # Prepare leads data
                leads = []
                for contact in batch:
                    lead = {
                        'First_Name': contact.get('first_name', 'Unknown'),
                        'Last_Name': contact.get('last_name', '.'),
                        'Company': contact.get('company', 'Unknown'),
                        'Lead_Source': 'Contact Enrichment System',
                        'Description': f"Imported from Contact Enricher on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    }
                    
                    if contact.get('email'):
                        lead['Email'] = contact['email']
                    if contact.get('phone'):
                        lead['Phone'] = contact['phone']
                    
                    leads.append(lead)
                
                payload = {
                    'data': leads,
                    'trigger': ['approval', 'workflow', 'blueprint']
                }
                
                logger.info(f"📤 Pushing batch {i//batch_size + 1}: {len(leads)} leads")
                
                response = requests.post(url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 201:
                    result = response.json()
                    result_data = result.get('data', [])
                    success_count = len([d for d in result_data if d.get('code') == 'SUCCESS'])
                    total_pushed += success_count
                    total_failed += len(batch) - success_count
                    
                    logger.info(f"✅ Batch {i//batch_size + 1}: {success_count}/{len(batch)} successful")
                    
                    # Track successful and failed contacts
                    for idx, item in enumerate(result_data):
                        if item.get('code') == 'SUCCESS':
                            # Successfully pushed - extract lead_id
                            lead_id = item.get('details', {}).get('id')
                            successful_contacts.append({
                                'contact': batch[idx],
                                'lead_id': lead_id
                            })
                        else:
                            failed_contacts.append({
                                'contact': batch[idx],
                                'error': item.get('message', 'Unknown error')
                            })
                elif response.status_code == 429:
                    # Rate limit exceeded - mark all remaining contacts as failed and stop processing
                    error_data = response.json() if response.text else {}
                    rate_limit_msg = error_data.get('message', 'Rate limit exceeded (429 Too Many Requests)')
                    logger.error(f"❌ Rate limit exceeded (429): {rate_limit_msg}")
                    logger.warning(f"⚠️  Stopping bulk push due to rate limit. Remaining contacts will be marked as failed.")
                    
                    # Mark current batch as failed
                    for contact in batch:
                        failed_contacts.append({
                            'contact': contact,
                            'error': f"Rate limit exceeded: {rate_limit_msg}"
                        })
                    total_failed += len(batch)
                    
                    # Mark all remaining contacts as failed
                    remaining_contacts = contacts_to_push[i + batch_size:]
                    for contact in remaining_contacts:
                        failed_contacts.append({
                            'contact': contact,
                            'error': f"Rate limit exceeded: {rate_limit_msg}"
                        })
                    total_failed += len(remaining_contacts)
                    
                    # Break out of the loop - no point in continuing
                    break
                else:
                    total_failed += len(batch)
                    error_text = response.text
                    logger.error(f"❌ Batch {i//batch_size + 1} failed: {response.status_code} - {error_text}")
                    
                    # Try to extract error message from response
                    error_msg = f"API error {response.status_code}"
                    try:
                        error_data = response.json()
                        if isinstance(error_data, dict):
                            error_msg = error_data.get('message', error_msg)
                            # Include code if available
                            if 'code' in error_data:
                                error_msg = f"{error_data.get('code')}: {error_msg}"
                    except:
                        pass
                    
                    for contact in batch:
                        failed_contacts.append({
                            'contact': contact,
                            'error': error_msg
                        })
            
            return {
                'success': total_pushed > 0,
                'total_pushed': total_pushed,
                'total_failed': total_failed,
                'total_skipped': total_skipped,
                'successful_contacts': successful_contacts,
                'failed_contacts': failed_contacts,
                'skipped_contacts': skipped_contacts
            }
            
        except Exception as e:
            error_msg = f"Error in bulk push: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return {
                'success': False,
                'total_pushed': total_pushed,
                'total_failed': total_failed + (len(contacts_to_push) - total_pushed - total_failed),
                'total_skipped': total_skipped,
                'successful_contacts': successful_contacts,
                'failed_contacts': failed_contacts,
                'skipped_contacts': skipped_contacts,
                'error': error_msg
            }


# Convenience functions
def create_zoho_service() -> ZohoCRMService:
    """Create a ZohoCRMService instance from environment variables."""
    return ZohoCRMService()


def test_connection() -> Tuple[bool, str]:
    """Test the Zoho CRM connection."""
    service = create_zoho_service()
    access_token, error = service.get_access_token()
    
    if error:
        return False, f"Connection failed: {error}"
    
    return True, "✅ Successfully connected to Zoho CRM!"


# Test script
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "="*70)
    print("🧪 ZOHO CRM SERVICE TEST")
    print("="*70 + "\n")
    
    # Test 1: Connection
    print("Test 1: Testing connection...")
    success, message = test_connection()
    print(message)
    
    if success:
        print("\n✅ All tests passed!")
        print("\nYou can now use this service to push contacts to Zoho CRM.")
    else:
        print("\n❌ Connection failed. Please check your credentials.")
        print("\nTo fix:")
        print("1. Generate a new refresh token from Zoho API Console")
        print("2. Update your .env file with the new token")
    
    print("\n" + "="*70 + "\n")

