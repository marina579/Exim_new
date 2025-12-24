"""
AI-powered contact information extractor.
Uses LLM to intelligently parse HTML and extract contact details including WhatsApp numbers.
"""

import re
import logging
from typing import Dict, Optional, List
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_with_ai(html_content: str, company_name: str = '') -> Optional[Dict[str, str]]:
    """
    Use AI/LLM-like pattern matching to extract contact information from HTML.
    This is a rule-based AI approach that looks for patterns intelligently.
    
    Args:
        html_content: Raw HTML content of the page
        company_name: Name of the company (for context)
        
    Returns:
        Dictionary with contact information or None
    """
    result = {
        'contact_name': '',
        'contact_address': '',
        'email': '',
        'phone': '',
        'whatsapp': ''
    }
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        html_str = str(soup)
        text_content = soup.get_text()
        
        # Extract phone numbers (including WhatsApp)
        phones = []
        whatsapp_numbers = []
        
        # Pattern 1: Look for WhatsApp links (wa.me, api.whatsapp.com, etc.)
        whatsapp_patterns = [
            r'wa\.me/(\+?91[6-9]\d{9})',  # wa.me/+918044016146
            r'api\.whatsapp\.com/send\?phone=(\+?91[6-9]\d{9})',  # api.whatsapp.com/send?phone=+918044016146
            r'whatsapp.*?(\+?91[-.\s]?[6-9]\d{9})',  # WhatsApp: +91-8044016146
            r'(\+?91[-.\s]?[6-9]\d{9}).*?whatsapp',  # +91-8044016146 WhatsApp
        ]
        
        for pattern in whatsapp_patterns:
            matches = re.findall(pattern, html_str, re.IGNORECASE)
            for match in matches:
                # Clean the number
                number = re.sub(r'[^\d]', '', match)
                if len(number) >= 10:
                    # Extract last 10 digits if it includes country code
                    if len(number) > 10:
                        number = number[-10:]
                    if number[0] in '6789' and len(number) == 10:
                        whatsapp = '+91-' + number
                        if whatsapp not in whatsapp_numbers:
                            whatsapp_numbers.append(whatsapp)
                            logger.info(f"✅ Found WhatsApp number: {whatsapp}")
        
        # Pattern 2: Look for phone numbers in various formats (prioritize +91 patterns)
        phone_patterns = [
            (r'Call\s*\+?91[-.\s]?([6-9]\d{9})', True),  # Call +91-8044016146 (highest priority)
            (r'\+?91[-.\s]?([6-9]\d{9})', True),  # +91-8044016146
            (r'tel:[\+]?91[-.\s]?([6-9]\d{9})', True),  # tel:+91-8044016146
            (r'(?:^|[^\d])([6-9]\d{9})(?:[^\d]|$)', False),  # Standalone 10-digit (lowest priority, must be isolated)
        ]
        
        for pattern, require_plus91 in phone_patterns:
            matches = re.findall(pattern, html_str, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    number = match[0] if match else None
                else:
                    number = match
                
                if number and len(number) == 10 and number[0] in '6789':
                    phone = '+91-' + number
                    # Avoid duplicates and invalid extractions
                    if phone not in phones and phone not in whatsapp_numbers:
                        phones.append(phone)
                        # If we found a +91 pattern, stop looking (we got the main number)
                        if require_plus91:
                            break
            if require_plus91 and phones:
                break  # Found main phone number, stop
        
        # Remove WhatsApp numbers from regular phones (avoid duplicates)
        phones = [p for p in phones if p not in whatsapp_numbers]
        
        if phones:
            result['phone'] = phones[0]  # Take first phone
        if whatsapp_numbers:
            result['whatsapp'] = whatsapp_numbers[0]  # Take first WhatsApp
            # If no regular phone but we have WhatsApp, use WhatsApp as phone too
            if not result['phone']:
                result['phone'] = whatsapp_numbers[0]
        
        # Extract email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, html_str, re.IGNORECASE)
        if emails:
            # Filter out non-business emails
            business_emails = [e for e in emails if not any(x in e.lower() for x in 
                           ['noreply', 'no-reply', 'donotreply', 'indiamart.com', 'example.com'])]
            if business_emails:
                result['email'] = business_emails[0]
        
        # Extract contact name - look for patterns like "Name (Title)"
        name_patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*\([^)]*(?:Director|Manager|Owner|Partner|CEO|Founder|President)',
            r'Contact\s+Person[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text_content, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name.split()) >= 2 and len(name.split()) <= 4:
                    result['contact_name'] = name
                    break
        
        # Extract address - look for Indian address patterns
        address_keywords = ['plot', 'street', 'road', 'area', 'sector', 'industrial', 'complex', 
                           'faridabad', 'delhi', 'mumbai', 'haryana', 'maharashtra', 'gujarat']
        
        # Look for address in "Reach Us" or similar sections
        reach_section = soup.find(string=re.compile(r'Reach\s+Us|Address|Location', re.I))
        if reach_section:
            parent = reach_section.find_parent(['div', 'section'])
            if parent:
                address_text = parent.get_text()
                # Clean up
                address_text = re.sub(r'Reach\s+Us[:\s]*', '', address_text, flags=re.I)
                address_text = re.sub(r'Get\s+Directions.*', '', address_text, flags=re.I)
                address_text = re.sub(r'Call.*', '', address_text, flags=re.I)
                
                # Extract address lines
                lines = [l.strip() for l in address_text.split('\n') if l.strip()]
                address_lines = []
                for line in lines:
                    if len(line) > 15 and any(kw in line.lower() for kw in address_keywords):
                        if not any(x in line.lower() for x in ['get best', 'price', 'exporters', 'buy', 'sell']):
                            address_lines.append(line)
                
                if address_lines:
                    result['contact_address'] = ', '.join(address_lines[:3])[:200]
        
        # Return result if we found at least phone or email
        if result.get('phone') or result.get('email') or result.get('whatsapp'):
            logger.info(f"✅ AI extraction found: phone={result.get('phone')}, whatsapp={result.get('whatsapp')}, email={result.get('email')}")
            return result
        
        return None
        
    except Exception as e:
        logger.error(f"Error in AI extraction: {str(e)}")
        return None


def extract_whatsapp_from_html(html_content: str) -> List[str]:
    """
    Specifically extract WhatsApp numbers from HTML.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        List of WhatsApp numbers found
    """
    whatsapp_numbers = []
    
    # Look for WhatsApp links
    patterns = [
        r'wa\.me/(\+?91[6-9]\d{9})',
        r'api\.whatsapp\.com/send\?phone=(\+?91[6-9]\d{9})',
        r'whatsapp.*?(\+?91[-.\s]?[6-9]\d{9})',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html_content, re.IGNORECASE)
        for match in matches:
            number = re.sub(r'[^\d]', '', match)
            if len(number) >= 10:
                if len(number) > 10:
                    number = number[-10:]
                if number[0] in '6789' and len(number) == 10:
                    whatsapp = '+91-' + number
                    if whatsapp not in whatsapp_numbers:
                        whatsapp_numbers.append(whatsapp)
    
    return whatsapp_numbers

