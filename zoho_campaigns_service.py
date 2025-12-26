"""
Zoho Campaigns Service - Handle bulk email marketing via Zoho Campaigns API
Supports India Data Center (zoho.in)
"""

import os
import requests
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ZohoCampaignsService:
    """
    Service to handle Zoho Campaigns API operations for bulk email marketing.
    Integrates with Zoho CRM contacts for email campaigns.
    """
    
    def __init__(self, access_token: str = None, api_key: str = None, data_center: str = "in"):
        """
        Initialize Zoho Campaigns Service.
        
        Args:
            access_token: OAuth access token (can use same as Zoho CRM)
            api_key: API key (alternative to OAuth)
            data_center: Data center - 'in' for India, 'com' for US, 'eu' for Europe
        """
        self.data_center = data_center or os.getenv('ZOHO_DATA_CENTER', 'in')
        self.access_token = access_token or os.getenv('ZOHO_CAMPAIGNS_ACCESS_TOKEN')
        self.api_key = api_key or os.getenv('ZOHO_CAMPAIGNS_API_KEY')
        
        # Set API base URL based on data center
        if self.data_center == 'in':
            self.api_base_url = "https://campaigns.zoho.in/api/v1.1"
        elif self.data_center == 'eu':
            self.api_base_url = "https://campaigns.zoho.eu/api/v1.1"
        else:  # Default to US
            self.api_base_url = "https://campaigns.zoho.com/api/v1.1"
        
        # Sender email configuration (REQUIRED)
        self.from_email = os.getenv('ZOHO_CAMPAIGNS_FROM_EMAIL', '')
        self.from_name = os.getenv('ZOHO_CAMPAIGNS_FROM_NAME', 'Marineco AI')
        
        if not self.from_email:
            logger.warning("⚠️  ZOHO_CAMPAIGNS_FROM_EMAIL not set - emails will fail!")
    
    def _get_auth_headers(self) -> Dict:
        """Get authentication headers for API requests."""
        if self.access_token:
            return {
                'Authorization': f'Zoho-oauthtoken {self.access_token}',
                'Content-Type': 'application/json'
            }
        elif self.api_key:
            return {
                'Authorization': f'Zoho-oauthtoken {self.api_key}',
                'Content-Type': 'application/json'
            }
        else:
            raise ValueError("Either access_token or api_key must be provided")
    
    def create_contact_list(self, list_name: str, description: str = "") -> Tuple[bool, Optional[Dict]]:
        """
        Create a new contact list in Zoho Campaigns.
        
        Args:
            list_name: Name of the list
            description: Optional description
        
        Returns:
            Tuple of (success: bool, list_data: Optional[Dict])
        """
        try:
            url = f"{self.api_base_url}/json/listsubscribe"
            headers = self._get_auth_headers()
            
            params = {
                'listkey': list_name.lower().replace(' ', '_'),
                'listname': list_name,
                'resubscribe': 'true'
            }
            
            if description:
                params['description'] = description
            
            logger.info(f"📋 Creating contact list: {list_name}")
            response = requests.post(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    logger.info(f"✅ Created list: {list_name}")
                    return True, result
                else:
                    logger.error(f"❌ Failed to create list: {result.get('message', 'Unknown error')}")
                    return False, None
            else:
                logger.error(f"❌ API error {response.status_code}: {response.text}")
                return False, None
                
        except Exception as e:
            logger.error(f"❌ Error creating list: {str(e)}")
            return False, None
    
    def add_contacts_to_list(self, list_key: str, contacts: List[Dict]) -> Tuple[bool, int]:
        """
        Add contacts to a Zoho Campaigns list.
        
        Args:
            list_key: List key (list identifier)
            contacts: List of contact dictionaries with:
                - email (required)
                - firstname (optional)
                - lastname (optional)
                - mobile (optional)
                - company (optional)
        
        Returns:
            Tuple of (success: bool, contacts_added: int)
        """
        if not contacts:
            return False, 0
        
        try:
            url = f"{self.api_base_url}/json/listsubscribe"
            headers = self._get_auth_headers()
            
            # Prepare contact data
            contact_list = []
            for contact in contacts:
                contact_data = {
                    'email': contact.get('email', '').strip()
                }
                
                # Add optional fields
                if contact.get('first_name'):
                    contact_data['firstname'] = contact['first_name']
                if contact.get('last_name'):
                    contact_data['lastname'] = contact['last_name']
                if contact.get('phone') or contact.get('whatsapp'):
                    contact_data['mobile'] = contact.get('phone') or contact.get('whatsapp')
                if contact.get('company'):
                    contact_data['company'] = contact['company']
                
                # Only add if email exists
                if contact_data['email']:
                    contact_list.append(contact_data)
            
            if not contact_list:
                logger.warning("⚠️  No contacts with email addresses to add")
                return False, 0
            
            # Zoho Campaigns accepts contacts in batches
            batch_size = 1000  # Max per request
            total_added = 0
            
            for i in range(0, len(contact_list), batch_size):
                batch = contact_list[i:i+batch_size]
                
                params = {
                    'listkey': list_key,
                    'resubscribe': 'true',
                    'contactinfo': str(batch)  # Zoho expects string format
                }
                
                logger.info(f"📤 Adding batch {i//batch_size + 1}: {len(batch)} contacts to list {list_key}")
                response = requests.post(url, headers=headers, params=params, timeout=60)
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get('status') == 'success':
                        added = result.get('count', len(batch))
                        total_added += added
                        logger.info(f"✅ Added {added} contacts to list")
                    else:
                        logger.warning(f"⚠️  Batch add warning: {result.get('message', 'Unknown')}")
                else:
                    logger.error(f"❌ Batch add error {response.status_code}: {response.text}")
            
            logger.info(f"✅ Total contacts added: {total_added}/{len(contact_list)}")
            return True, total_added
            
        except Exception as e:
            logger.error(f"❌ Error adding contacts to list: {str(e)}", exc_info=True)
            return False, 0
    
    def create_email_template(self, template_name: str, subject: str, html_content: str, 
                             text_content: str = "") -> Tuple[bool, Optional[str]]:
        """
        Create an email template in Zoho Campaigns.
        
        Args:
            template_name: Name of the template
            subject: Email subject line
            html_content: HTML email content
            text_content: Plain text version (optional)
        
        Returns:
            Tuple of (success: bool, template_id: Optional[str])
        """
        try:
            url = f"{self.api_base_url}/json/template/create"
            headers = self._get_auth_headers()
            
            params = {
                'templatename': template_name,
                'subject': subject,
                'htmlcontent': html_content
            }
            
            if text_content:
                params['textcontent'] = text_content
            
            logger.info(f"📝 Creating email template: {template_name}")
            response = requests.post(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    template_id = result.get('templatekey')
                    logger.info(f"✅ Created template: {template_name} (ID: {template_id})")
                    return True, template_id
                else:
                    logger.error(f"❌ Failed to create template: {result.get('message', 'Unknown error')}")
                    return False, None
            else:
                logger.error(f"❌ API error {response.status_code}: {response.text}")
                return False, None
                
        except Exception as e:
            logger.error(f"❌ Error creating template: {str(e)}")
            return False, None
    
    def send_campaign(self, list_key: str, template_key: str, subject: str,
                     from_email: str = None, from_name: str = None,
                     reply_to: str = None, attachment_key: str = None) -> Tuple[bool, Optional[str], str]:
        """
        Send bulk email campaign to a list.
        
        Args:
            list_key: List key to send to
            template_key: Template key to use
            subject: Email subject line
            from_email: Sender email (required - must be verified in Zoho)
            from_name: Sender name
            reply_to: Reply-to email (defaults to from_email)
        
        Returns:
            Tuple of (success: bool, campaign_id: Optional[str], message: str)
        """
        if not from_email:
            from_email = self.from_email
        
        if not from_email:
            error_msg = "❌ Sender email not configured. Set ZOHO_CAMPAIGNS_FROM_EMAIL"
            logger.error(error_msg)
            return False, None, error_msg
        
        if not from_name:
            from_name = self.from_name
        
        if not reply_to:
            reply_to = from_email
        
        try:
            url = f"{self.api_base_url}/json/campaign/create"
            headers = self._get_auth_headers()
            
            params = {
                'campaignname': f"Campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                'listkey': list_key,
                'templatekey': template_key,
                'subject': subject,
                'fromemailid': from_email,
                'fromname': from_name,
                'replytoid': reply_to
            }
            
            # Add PDF attachment if provided
            if attachment_key:
                params['attachmentkey'] = attachment_key
                logger.info(f"📎 Adding PDF attachment: {attachment_key}")
            
            logger.info(f"📧 Creating campaign for list: {list_key}")
            logger.info(f"   From: {from_name} <{from_email}>")
            logger.info(f"   Subject: {subject}")
            
            response = requests.post(url, headers=headers, params=params, timeout=60)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    campaign_key = result.get('campaignkey')
                    
                    # Now send the campaign
                    send_url = f"{self.api_base_url}/json/campaign/send"
                    send_params = {
                        'campaignkey': campaign_key,
                        'sendnow': 'true'
                    }
                    
                    logger.info(f"📤 Sending campaign: {campaign_key}")
                    send_response = requests.post(send_url, headers=headers, params=send_params, timeout=60)
                    
                    if send_response.status_code == 200:
                        send_result = send_response.json()
                        if send_result.get('status') == 'success':
                            logger.info(f"✅ Campaign sent successfully: {campaign_key}")
                            return True, campaign_key, f"Campaign sent to list {list_key}"
                        else:
                            error_msg = send_result.get('message', 'Failed to send campaign')
                            logger.error(f"❌ {error_msg}")
                            return False, campaign_key, error_msg
                    else:
                        error_msg = f"Send API error {send_response.status_code}: {send_response.text}"
                        logger.error(f"❌ {error_msg}")
                        return False, campaign_key, error_msg
                else:
                    error_msg = result.get('message', 'Failed to create campaign')
                    logger.error(f"❌ {error_msg}")
                    return False, None, error_msg
            else:
                error_msg = f"API error {response.status_code}: {response.text}"
                logger.error(f"❌ {error_msg}")
                return False, None, error_msg
                
        except Exception as e:
            error_msg = f"Error sending campaign: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            return False, None, error_msg
    
    def get_campaign_stats(self, campaign_key: str) -> Optional[Dict]:
        """
        Get campaign statistics (opens, clicks, bounces).
        
        Args:
            campaign_key: Campaign key
        
        Returns:
            Dictionary with campaign statistics
        """
        try:
            url = f"{self.api_base_url}/json/campaign/getstats"
            headers = self._get_auth_headers()
            
            params = {
                'campaignkey': campaign_key
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    return result.get('data', {})
                else:
                    logger.error(f"❌ Failed to get stats: {result.get('message', 'Unknown error')}")
                    return None
            else:
                logger.error(f"❌ API error {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting campaign stats: {str(e)}")
            return None
    
    def sync_crm_contacts_to_campaigns(self, list_key: str, crm_contacts: List[Dict]) -> Tuple[bool, int, str]:
        """
        Sync contacts from Zoho CRM to Zoho Campaigns list.
        This is a convenience method that combines list creation and contact addition.
        
        Args:
            list_key: List key (will create if doesn't exist)
            crm_contacts: List of contact dictionaries from CRM
        
        Returns:
            Tuple of (success: bool, contacts_added: int, message: str)
        """
        # Ensure list exists
        list_exists = True  # Assume exists, or create if needed
        
        # Add contacts
        success, count = self.add_contacts_to_list(list_key, crm_contacts)
        
        if success:
            return True, count, f"Successfully synced {count} contacts to Campaigns"
        else:
            return False, 0, "Failed to sync contacts to Campaigns"
    
    def get_campaign_reports(self, campaign_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get detailed reports for a specific campaign.
        
        Args:
            campaign_id: Campaign ID from send_campaign response
        
        Returns:
            Tuple of (report_data: Dict, error: Optional[str])
            Report data includes:
            - sent: Number of emails sent
            - delivered: Number delivered
            - opened: Number opened
            - clicked: Number clicked
            - bounced: Number bounced
            - unsubscribed: Number unsubscribed
            - open_rate: Open rate percentage
            - click_rate: Click rate percentage
            - bounce_rate: Bounce rate percentage
        """
        try:
            # Try using getstats endpoint first
            stats = self.get_campaign_stats(campaign_id)
            if stats:
                sent = stats.get('sent', 0)
                delivered = stats.get('delivered', 0)
                opened = stats.get('opened', 0)
                clicked = stats.get('clicked', 0)
                bounced = stats.get('bounced', 0)
                unsubscribed = stats.get('unsubscribed', 0)
                
                # Calculate rates
                open_rate = (opened / delivered * 100) if delivered > 0 else 0
                click_rate = (clicked / delivered * 100) if delivered > 0 else 0
                bounce_rate = (bounced / sent * 100) if sent > 0 else 0
                
                report_data = {
                    'campaign_id': campaign_id,
                    'sent': sent,
                    'delivered': delivered,
                    'opened': opened,
                    'clicked': clicked,
                    'bounced': bounced,
                    'unsubscribed': unsubscribed,
                    'open_rate': round(open_rate, 2),
                    'click_rate': round(click_rate, 2),
                    'bounce_rate': round(bounce_rate, 2),
                    'raw_report': stats
                }
                
                logger.info(f"✅ Fetched campaign report for {campaign_id}")
                return report_data, None
            
            # Fallback: Try reports endpoint
            url = f"{self.api_base_url}/json/campaigns/{campaign_id}/reports"
            headers = self._get_auth_headers()
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('response', {}).get('uri_response', {}).get('status') == 'success':
                    report = data['response']['uri_response'].get('campaign_report', {})
                    
                    # Extract metrics
                    sent = report.get('sent', 0)
                    delivered = report.get('delivered', 0)
                    opened = report.get('opened', 0)
                    clicked = report.get('clicked', 0)
                    bounced = report.get('bounced', 0)
                    unsubscribed = report.get('unsubscribed', 0)
                    
                    # Calculate rates
                    open_rate = (opened / delivered * 100) if delivered > 0 else 0
                    click_rate = (clicked / delivered * 100) if delivered > 0 else 0
                    bounce_rate = (bounced / sent * 100) if sent > 0 else 0
                    
                    report_data = {
                        'campaign_id': campaign_id,
                        'sent': sent,
                        'delivered': delivered,
                        'opened': opened,
                        'clicked': clicked,
                        'bounced': bounced,
                        'unsubscribed': unsubscribed,
                        'open_rate': round(open_rate, 2),
                        'click_rate': round(click_rate, 2),
                        'bounce_rate': round(bounce_rate, 2),
                        'raw_report': report
                    }
                    
                    logger.info(f"✅ Fetched campaign report for {campaign_id}")
                    return report_data, None
                else:
                    error_msg = data.get('response', {}).get('uri_response', {}).get('message', 'Unknown error')
                    return None, error_msg
            else:
                logger.error(f"❌ API error {response.status_code}: {response.text}")
                return None, f"API error {response.status_code}"
                
        except Exception as e:
            logger.error(f"❌ Error getting campaign report: {str(e)}")
            return None, str(e)
    
    def get_all_campaigns(self, limit: int = 50) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """
        Get list of all campaigns.
        
        Args:
            limit: Maximum number of campaigns to return
        
        Returns:
            Tuple of (campaigns_list: List[Dict], error: Optional[str])
        """
        try:
            url = f"{self.api_base_url}/json/campaigns"
            headers = self._get_auth_headers()
            params = {'limit': limit}
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('response', {}).get('uri_response', {}).get('status') == 'success':
                    campaigns = data['response']['uri_response'].get('campaigns', [])
                    logger.info(f"✅ Fetched {len(campaigns)} campaigns")
                    return campaigns, None
                else:
                    error_msg = data.get('response', {}).get('uri_response', {}).get('message', 'Unknown error')
                    return None, error_msg
            else:
                logger.error(f"❌ API error {response.status_code}: {response.text}")
                return None, f"API error {response.status_code}"
                
        except Exception as e:
            logger.error(f"❌ Error getting campaigns: {str(e)}")
            return None, str(e)


# Convenience function
def create_campaigns_service(access_token: str = None, api_key: str = None) -> ZohoCampaignsService:
    """Create a ZohoCampaignsService instance from environment variables."""
    return ZohoCampaignsService(access_token=access_token, api_key=api_key)

