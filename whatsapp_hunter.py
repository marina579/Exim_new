"""
WhatsApp Hunter - Advanced Indian Business Contact Finder

Implements the proven manual techniques for finding WhatsApp numbers:

TECHNIQUE 1: Google Dorking (Search Operator Hack)
  - site:facebook.com "Company Name" "WhatsApp"
  - site:instagram.com "Company Name" "+91"
  - site:linkedin.com "Company Name" "contact"

TECHNIQUE 2: wa.me Link Extraction
  - https://wa.me/91XXXXXXXXXX
  - https://api.whatsapp.com/send?phone=91XXXXXXXXXX

TECHNIQUE 3: Verified Indian Directories
  - Justdial (with "JD Trust" badge)
  - Sulekha
  - TradeIndia
  - IndiaMART

TECHNIQUE 4: GST & MCA Records (Most Reliable - requires paid API)
  - GST-based mobile lookup (LeadCloud, Surereach)
  - Director mobile from MCA filings (Zauba Corp, Tofler)
"""

import os
import re
import time
import random
import logging
from typing import Dict, Optional
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

logger = logging.getLogger(__name__)

# Speed optimization check
SPEED_OPTIMIZED = os.getenv('SPEED_OPTIMIZED', 'false').lower() == 'true'
DELAY_MIN = 0.5 if SPEED_OPTIMIZED else 2
DELAY_MAX = 1 if SPEED_OPTIMIZED else 4
REQUEST_TIMEOUT = 8 if SPEED_OPTIMIZED else 15

# Request headers to mimic browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}


class WhatsAppHunter:
    """
    Finds WhatsApp/mobile numbers using multi-source approach optimized for Indian businesses.
    """
    
    def __init__(self, serpapi_key: str = None):
        """Initialize WhatsApp Hunter."""
        self.serpapi_key = serpapi_key or os.getenv('SERPAPI_API_KEY')
        logger.info("✅ WhatsApp Hunter initialized")
    
    def find_contacts(self, company_name: str, address: str = "") -> Dict[str, str]:
        """
        Find WhatsApp/mobile using all techniques.
        
        Priority order:
        1. Google Dorking (Facebook, Instagram)
        2. wa.me link extraction
        3. Verified directories (Justdial, Sulekha, TradeIndia, IndiaMART)
        4. GST/MCA records (if API available)
        
        Args:
            company_name: Company name
            address: Company address
        
        Returns:
            Dictionary with phone, whatsapp, email, source_url
        """
        logger.info(f"🔍 WhatsApp Hunter searching: {company_name}")
        
        result = {
            'phone': '',
            'whatsapp': '',
            'email': '',
            'contact_name': '',
            'address': '',
            'source_url': '',
            'method': ''
        }
        
        # TECHNIQUE 1: Google Dorking (Most Effective)
        logger.info("  📱 Trying Google Dorking (Facebook/Instagram)...")
        dorking_result = self._google_dorking(company_name, address)
        if dorking_result.get('phone') or dorking_result.get('whatsapp'):
            result.update(dorking_result)
            result['method'] = 'Google Dorking'
            logger.info(f"  ✅ Found via Dorking: {result.get('phone') or result.get('whatsapp')}")
            return result
        
        # TECHNIQUE 2: wa.me Link Extraction
        logger.info("  🔗 Searching for wa.me links...")
        wame_result = self._search_wame_links(company_name, address)
        if wame_result.get('whatsapp'):
            result.update(wame_result)
            result['method'] = 'wa.me Links'
            logger.info(f"  ✅ Found wa.me link: {result['whatsapp']}")
            return result
        
        # TECHNIQUE 3: Verified Indian Directories
        logger.info("  📖 Checking verified directories...")
        directory_result = self._check_directories(company_name, address)
        if directory_result.get('phone'):
            result.update(directory_result)
            result['method'] = 'Verified Directory'
            logger.info(f"  ✅ Found in directory: {result['phone']}")
            return result
        
        # TECHNIQUE 4: Aggressive Email Search (NEW!)
        logger.info("  📧 Searching for email addresses...")
        email_result = self._search_emails_aggressive(company_name, address)
        if email_result.get('email'):
            result.update(email_result)
            result['method'] = result.get('method', 'Email Search')
            logger.info(f"  ✅ Found email: {result['email']}")
            # Continue to try finding phone if missing
        
        # TECHNIQUE 5: GST/MCA Records (if available)
        # This requires paid API access, so we'll skip for now
        # but provide the hook for future integration
        
        logger.info(f"  ❌ No contacts found for: {company_name}")
        return result
    
    def _google_dorking(self, company: str, address: str) -> Dict:
        """
        TECHNIQUE 1: Google Dorking
        Search social media and PDFs for WhatsApp numbers.
        """
        searches = [
            f'site:facebook.com "{company}" WhatsApp',
            f'site:facebook.com "{company}" "+91"',
            f'site:instagram.com "{company}" WhatsApp',
            f'site:instagram.com "{company}" contact',
            f'site:linkedin.com "{company}" phone India',
            f'"{company}" WhatsApp India contact',
            f'"{company}" "+91" mobile',
        ]
        
        for query in searches:
            if self.serpapi_key:
                result = self._serpapi_search(query)
            else:
                result = self._google_search(query)
            
            if result.get('phone') or result.get('whatsapp'):
                return result
            
            # Rate limit
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        
        return {}
    
    def _search_wame_links(self, company: str, address: str) -> Dict:
        """
        TECHNIQUE 2: wa.me Link Extraction
        Search for direct WhatsApp links.
        """
        query = f'"{company}" wa.me OR api.whatsapp.com India'
        
        if self.serpapi_key:
            return self._serpapi_search(query)
        else:
            return self._google_search(query)
    
    def _check_directories(self, company: str, address: str) -> Dict:
        """
        TECHNIQUE 3: Verified Indian Directories
        Check Justdial, Sulekha, TradeIndia, IndiaMART.
        """
        directories = [
            ('justdial.com', self._scrape_justdial),
            ('sulekha.com', self._scrape_sulekha),
            ('tradeindia.com', self._scrape_tradeindia),
            ('indiamart.com', self._scrape_indiamart),
        ]
        
        for site, scraper_func in directories:
            logger.info(f"    Checking {site}...")
            
            # First, search Google to find the listing
            query = f'site:{site} "{company}"'
            
            if self.serpapi_key:
                search_result = self._serpapi_search(query)
            else:
                search_result = self._google_search(query)
            
            # If we found a URL, try to scrape it
            if search_result.get('source_url'):
                scrape_result = scraper_func(search_result['source_url'])
                if scrape_result.get('phone'):
                    return scrape_result
            
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        
        return {}
    
    def _serpapi_search(self, query: str) -> Dict:
        """Execute search via SerpApi."""
        result = {'phone': '', 'whatsapp': '', 'email': '', 'source_url': ''}
        
        try:
            params = {
                'q': query,
                'api_key': self.serpapi_key,
                'engine': 'google',
                'gl': 'in',
                'hl': 'en',
                'num': 10
            }
            
            response = requests.get('https://serpapi.com/search', params=params, timeout=20)
            if response.status_code != 200:
                return result
            
            data = response.json()
            
            # Extract from entire response
            all_text = str(data)
            
            # Look for wa.me links (highest priority)
            whatsapp_links = re.findall(r'wa\.me/(\d+)', all_text)
            if whatsapp_links:
                phone = whatsapp_links[0]
                if len(phone) >= 10:
                    mobile = phone[-10:]
                    if mobile[0] in '6789':
                        result['whatsapp'] = f"+91-{mobile}"
                        result['phone'] = result['whatsapp']
                        logger.debug(f"      Found wa.me: {result['whatsapp']}")
            
            # Look for api.whatsapp.com links
            if not result['whatsapp']:
                api_whatsapp = re.findall(r'api\.whatsapp\.com/send\?phone=(\d+)', all_text)
                if api_whatsapp:
                    phone = api_whatsapp[0]
                    if len(phone) >= 10:
                        mobile = phone[-10:]
                        if mobile[0] in '6789':
                            result['whatsapp'] = f"+91-{mobile}"
                            result['phone'] = result['whatsapp']
                            logger.debug(f"      Found api.whatsapp: {result['whatsapp']}")
            
            # Extract from organic results
            if 'organic_results' in data:
                for item in data['organic_results'][:10]:
                    snippet = item.get('snippet', '')
                    title = item.get('title', '')
                    link = item.get('link', '')
                    
                    combined = f"{title} {snippet}"
                    
                    # Find Indian mobile numbers (10 digits, starts with 6-9)
                    if not result['phone']:
                        phones = re.findall(r'\+91[-\s]?[6-9]\d{9}|\b[6-9]\d{9}\b', combined)
                        if phones:
                            phone = re.sub(r'[^\d]', '', phones[0])
                            if len(phone) == 10:
                                result['phone'] = f"+91-{phone}"
                                result['source_url'] = link
                                logger.debug(f"      Found mobile: {result['phone']}")
                    
                    # Find email - COLLECT ALL, don't stop at first
                    if not result['email']:
                        emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', combined)
                        # Filter out common generic emails
                        generic_emails = ['example@', 'test@', 'noreply@', 'no-reply@']
                        for email in emails:
                            if not any(gen in email.lower() for gen in generic_emails):
                                result['email'] = email.lower()
                                logger.debug(f"      Found email: {result['email']}")
                                break
                    
                    # Continue searching even if we have partial results
                    if result['phone'] and result['email']:
                        break
            
            # Check knowledge graph
            if 'knowledge_graph' in data and not result['phone']:
                kg = data['knowledge_graph']
                if 'phone' in kg:
                    normalized = self._normalize_phone(kg['phone'])
                    if normalized:
                        result['phone'] = normalized
                        logger.debug(f"      Found in knowledge graph: {result['phone']}")
            
            # Check local results
            if 'local_results' in data and not result['phone']:
                for local in data.get('local_results', {}).get('places', [])[:3]:
                    if 'phone' in local:
                        normalized = self._normalize_phone(local['phone'])
                        if normalized:
                            result['phone'] = normalized
                            result['source_url'] = local.get('link', '')
                            logger.debug(f"      Found in local results: {result['phone']}")
                            break
            
            return result
            
        except Exception as e:
            logger.error(f"      SerpApi error: {str(e)}")
            return result
    
    def _google_search(self, query: str) -> Dict:
        """Fallback: Direct Google search (if no SerpApi)."""
        result = {'phone': '', 'whatsapp': '', 'email': '', 'source_url': ''}
        
        try:
            url = f"https://www.google.com/search?q={quote(query)}&gl=in&hl=en"
            
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                logger.warning(f"      Google returned {response.status_code}")
                return result
            
            soup = BeautifulSoup(response.content, 'html.parser')
            html = str(soup)
            
            # Extract wa.me links
            whatsapp_links = re.findall(r'wa\.me/(\d+)', html)
            for phone in whatsapp_links:
                if len(phone) >= 10:
                    mobile = phone[-10:]
                    if mobile[0] in '6789':
                        result['whatsapp'] = f"+91-{mobile}"
                        result['phone'] = result['whatsapp']
                        break
            
            # Extract mobile numbers
            if not result['phone']:
                phones = re.findall(r'\+91[-\s]?[6-9]\d{9}|\b[6-9]\d{9}\b', html)
                for phone in phones:
                    clean = re.sub(r'[^\d]', '', phone)
                    if len(clean) == 10 and clean[0] in '6789':
                        result['phone'] = f"+91-{clean}"
                        break
            
            # Extract emails
            emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', html)
            if emails:
                result['email'] = emails[0].lower()
            
            return result
            
        except Exception as e:
            logger.error(f"      Google search error: {str(e)}")
            return result
    
    def _scrape_justdial(self, url: str) -> Dict:
        """Scrape Justdial listing (verified numbers)."""
        result = {'phone': '', 'email': '', 'source_url': url}
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                return result
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for phone numbers
            phone_elements = soup.find_all(['span', 'a', 'div'], class_=re.compile(r'phone|mobile|contact', re.I))
            for elem in phone_elements:
                text = elem.get_text()
                phones = re.findall(r'[6-9]\d{9}', text)
                if phones:
                    result['phone'] = f"+91-{phones[0]}"
                    break
            
            # Look for emails
            emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', str(soup))
            if emails:
                result['email'] = emails[0].lower()
            
            return result
            
        except Exception as e:
            logger.error(f"      Justdial scrape error: {str(e)}")
            return result
    
    def _scrape_sulekha(self, url: str) -> Dict:
        """Scrape Sulekha listing."""
        result = {'phone': '', 'email': '', 'source_url': url}
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                return result
            
            soup = BeautifulSoup(response.content, 'html.parser')
            html = str(soup)
            
            # Extract phone numbers
            phones = re.findall(r'[6-9]\d{9}', html)
            if phones:
                result['phone'] = f"+91-{phones[0]}"
            
            # Extract emails
            emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', html)
            if emails:
                result['email'] = emails[0].lower()
            
            return result
            
        except Exception as e:
            logger.error(f"      Sulekha scrape error: {str(e)}")
            return result
    
    def _scrape_tradeindia(self, url: str) -> Dict:
        """Scrape TradeIndia listing."""
        result = {'phone': '', 'whatsapp': '', 'email': '', 'source_url': url}
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                return result
            
            soup = BeautifulSoup(response.content, 'html.parser')
            html = str(soup)
            
            # Look for wa.me links
            whatsapp_links = re.findall(r'wa\.me/(\d+)', html)
            if whatsapp_links:
                phone = whatsapp_links[0]
                if len(phone) >= 10:
                    mobile = phone[-10:]
                    if mobile[0] in '6789':
                        result['whatsapp'] = f"+91-{mobile}"
                        result['phone'] = result['whatsapp']
            
            # Look for phone numbers
            if not result['phone']:
                phones = re.findall(r'[6-9]\d{9}', html)
                if phones:
                    result['phone'] = f"+91-{phones[0]}"
            
            # Extract emails
            emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', html)
            if emails:
                result['email'] = emails[0].lower()
            
            return result
            
        except Exception as e:
            logger.error(f"      TradeIndia scrape error: {str(e)}")
            return result
    
    def _scrape_indiamart(self, url: str) -> Dict:
        """Scrape IndiaMART listing (enhanced for wa.me links)."""
        result = {'phone': '', 'whatsapp': '', 'email': '', 'source_url': url}
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                return result
            
            soup = BeautifulSoup(response.content, 'html.parser')
            html = str(soup)
            
            # Priority 1: wa.me links (highest confidence)
            whatsapp_links = re.findall(r'wa\.me/(\d+)', html)
            if whatsapp_links:
                phone = whatsapp_links[0]
                if len(phone) >= 10:
                    mobile = phone[-10:]
                    if mobile[0] in '6789':
                        result['whatsapp'] = f"+91-{mobile}"
                        result['phone'] = result['whatsapp']
                        return result
            
            # Priority 2: Call +91-XXXXXXXXXX patterns
            call_patterns = re.findall(r'Call\s+\+91[- ]?([6-9]\d{9})', html, re.I)
            if call_patterns:
                result['phone'] = f"+91-{call_patterns[0]}"
                return result
            
            # Priority 3: Any Indian mobile number
            phones = re.findall(r'[6-9]\d{9}', html)
            if phones:
                result['phone'] = f"+91-{phones[0]}"
            
            # Extract emails
            emails = re.findall(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', html)
            if emails:
                result['email'] = emails[0].lower()
            
            return result
            
        except Exception as e:
            logger.error(f"      IndiaMART scrape error: {str(e)}")
            return result
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone to +91-XXXXXXXXXX format."""
        digits = re.sub(r'[^\d]', '', phone)
        if len(digits) >= 10:
            mobile = digits[-10:]
            if mobile[0] in '6789':
                return f'+91-{mobile}'
        return ''
    
    # TECHNIQUE 4: GST/MCA Records (Future Integration)
    # These require paid API access:
    # - LeadCloud.io (GST-based mobile lookup)
    # - Surereach.io (Director mobile from MCA)
    # - Kredily (GSTIN search)
    # - Razorpay GST Search (free tier available)
    
    def find_via_gst(self, company_name: str, gstin: str = None) -> Dict:
        """
        TECHNIQUE 4: Find mobile via GST records (requires paid API).
        
        This is the MOST RELIABLE method for Indian businesses because:
        - GST-linked mobile is the owner's primary number
        - Used for tax OTPs, so always active
        - 95% of Indian business owners use it for WhatsApp
        
        To implement:
        1. Sign up for LeadCloud.io or Surereach.io
        2. Get API key
        3. Search by GSTIN or company name
        4. Returns: mobile, email, owner name
        
        Args:
            company_name: Company name
            gstin: GST Identification Number (if known)
        
        Returns:
            Dictionary with phone, email, contact_name
        """
        # Placeholder for future paid API integration
        logger.info("  💼 GST/MCA search requires paid API (LeadCloud, Surereach)")
        return {}


    def _search_emails_aggressive(self, company: str, address: str) -> Dict:
        """
        NEW TECHNIQUE 4: Aggressive Email Search
        Specifically searches for email addresses using multiple strategies.
        """
        result = {'phone': '', 'whatsapp': '', 'email': '', 'source_url': ''}
        
        # Strategy 1: Direct email search with company name
        email_queries = [
            f'"{company}" email contact India',
            f'"{company}" @gmail.com OR @yahoo.com',
            f'"{company}" proprietor email OR director email',
            f'site:indiamart.com "{company}" email',
            f'site:tradeindia.com "{company}" email',
            f'site:exportersindia.com "{company}" email',
        ]
        
        for query in email_queries:
            try:
                if self.serpapi_key:
                    search_result = self._serpapi_search(query)
                else:
                    search_result = self._google_search(query)
                
                if search_result.get('email'):
                    result['email'] = search_result['email']
                    result['source_url'] = search_result.get('source_url', '')
                    logger.info(f"      ✅ Email found via query: {query[:50]}...")
                    return result
                
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
            except Exception as e:
                logger.debug(f"      Error in email search: {e}")
                continue
        
        return result


if __name__ == '__main__':
    # Test the WhatsApp Hunter
    logging.basicConfig(level=logging.INFO)
    
    hunter = WhatsAppHunter()
    
    test_companies = [
        ("Star Exports", "50 KAZI SAYED STREET, MUMBAI"),
        ("Hitaashi Solutions", "BELGHARIA, KOLKATA"),
        ("Four He Art Creations", "THRISSUR, KERALA"),
    ]
    
    print("\n" + "="*70)
    print("Testing WhatsApp Hunter")
    print("="*70 + "\n")
    
    for company, address in test_companies:
        print(f"\n🔍 Searching: {company}")
        print(f"   Address: {address}")
        
        result = hunter.find_contacts(company, address)
        
        if result.get('phone') or result.get('whatsapp'):
            print(f"   ✅ Phone: {result.get('phone', 'N/A')}")
            print(f"   ✅ WhatsApp: {result.get('whatsapp', 'N/A')}")
            print(f"   📧 Email: {result.get('email', 'N/A')}")
            print(f"   🔗 Source: {result.get('source_url', 'N/A')}")
            print(f"   📍 Method: {result.get('method', 'N/A')}")
        else:
            print(f"   ❌ No contacts found")
        
        time.sleep(DELAY_MAX)  # Rate limit between searches
