"""
Advanced Email Extraction and Verification Module.

Features:
1. Tiered email extraction (official > corporate > generic)
2. Email validation and verification
3. Director name-based email discovery
4. Trade directory scraping
5. Website email extraction
"""

import re
import logging
import requests
import os
from typing import List, Dict, Optional, Set
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import time

logger = logging.getLogger(__name__)

# Gemini imports
try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    logging.warning("Gemini not available for email extraction")

# Email Validator library for deliverability checking
try:
    from email_validator import validate_email, EmailNotValidError
    HAS_EMAIL_VALIDATOR = True
except ImportError:
    HAS_EMAIL_VALIDATOR = False
    logging.warning("email-validator library not available - install with: pip install email-validator")

# Email Pattern Finder
try:
    from email_pattern_finder import EmailPatternFinder
    HAS_PATTERN_FINDER = True
except ImportError:
    HAS_PATTERN_FINDER = False
    logging.warning("EmailPatternFinder not available")

# Advanced email regex (captures complex corporate formats)
EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

# Generic email prefixes to deprioritize
GENERIC_PREFIXES = [
    'info', 'contact', 'sales', 'support', 'admin', 'inquiry',
    'hello', 'mail', 'office', 'enquiry', 'help', 'service'
]


class EmailEnhancer:
    """Advanced email extraction with verification and prioritization."""
    
    def __init__(self, gemini_api_key: str = None, serpapi_key: str = None, openai_key: str = None):
        """Initialize email enhancer."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        
        self.serpapi_key = serpapi_key
        self.openai_key = openai_key or os.getenv('OPENAI_API_KEY')
        
        # Initialize Email Pattern Finder with AI Validation
        if HAS_PATTERN_FINDER and serpapi_key:
            self.pattern_finder = EmailPatternFinder(
                serpapi_key=serpapi_key,
                openai_key=self.openai_key,  # Enable AI validation
                use_ai_validation=True
            )
            logger.info("✅ Email Pattern Finder initialized (with AI validation)")
        else:
            self.pattern_finder = None
            logger.warning("⚠️  Email Pattern Finder not available")
        
        # Initialize Gemini for AI-powered email extraction
        self.gemini_client = None
        if HAS_GEMINI:
            api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
            if api_key:
                try:
                    # Initialize with only api_key parameter (no proxies)
                    self.gemini_client = genai.Client(api_key=api_key)
                    logger.info("✅ Gemini AI initialized for email extraction")
                except TypeError as e:
                    if 'proxies' in str(e):
                        logger.warning(f"⚠️  Gemini Client proxies error (version issue): {str(e)}")
                        # Try alternative initialization if proxies error
                        try:
                            self.gemini_client = genai.Client(api_key=api_key)
                        except Exception as e2:
                            logger.warning(f"⚠️  Gemini initialization failed: {str(e2)}")
                    else:
                        logger.warning(f"⚠️  Gemini initialization failed: {str(e)}")
                except Exception as e:
                    logger.warning(f"⚠️  Gemini initialization failed: {str(e)}")
        else:
            logger.warning("⚠️  Gemini not available")
    
    def find_emails(self, company_name: str, address: str = "", 
                   gstin: str = None, director_name: str = None,
                   website: str = None) -> Dict[str, str]:
        """
        Tiered email extraction strategy.
        
        Priority:
        1. Official (GSTIN-based government email)
        2. Corporate (director name-based)
        3. Website emails
        4. Trade directory emails
        5. Generic fallback
        
        Args:
            company_name: Company name
            address: Company address
            gstin: GST identification number (if available)
            director_name: Director/owner name (if available)
            website: Company website URL (if available)
        
        Returns:
            Dict with 'primary', 'secondary', 'all' emails
        """
        all_emails = []
        
        logger.info(f"🔍 Enhanced email search for: {company_name}")
        
        # TIER 1: Official registry emails (GSTIN-based)
        if gstin:
            logger.info("   [Tier 1] Searching official registry emails...")
            official_email = self._find_official_email(gstin, company_name)
            if official_email:
                all_emails.append({
                    'email': official_email,
                    'type': 'official',
                    'priority': 1,
                    'source': 'GST Registry'
                })
        
        # TIER 1.5: Gemini AI email search (NEW - AI-powered!)
        if self.gemini_client:
            logger.info("   [Tier 1.5] Using Gemini AI for email search...")
            gemini_emails = self._find_emails_with_gemini(company_name, address, director_name)
            for email in gemini_emails:
                if not self._is_email_in_list(email, all_emails):
                    email_type = 'corporate' if not self._is_generic(email) else 'generic'
                    all_emails.append({
                        'email': email,
                        'type': email_type,
                        'priority': 2 if email_type == 'corporate' else 3,
                        'source': 'Gemini AI'
                    })
        
        # TIER 2: Corporate emails (director name-based)
        if director_name and website:
            logger.info("   [Tier 2] Searching director-based emails...")
            corporate_emails = self._find_corporate_emails(website, director_name)
            for email in corporate_emails:
                all_emails.append({
                    'email': email,
                    'type': 'corporate',
                    'priority': 2,
                    'source': 'Corporate Website'
                })
        
        # TIER 2.5: Email Pattern Matching (NEW! - Name + Domain)
        if self.pattern_finder and director_name:
            logger.info("   [Tier 2.5] Using Email Pattern Matching...")
            pattern_result = self.pattern_finder.find_email_from_name(
                contact_name=director_name,
                company_name=company_name,
                company_website=website,
                address=address
            )
            if pattern_result['email']:
                email_type = 'corporate' if pattern_result['confidence'] >= 70 else 'probable'
                all_emails.append({
                    'email': pattern_result['email'],
                    'type': email_type,
                    'priority': 2 if pattern_result['confidence'] >= 85 else 3,
                    'source': f"Pattern: {pattern_result['pattern']} ({pattern_result['confidence']}%)"
                })
        
        # TIER 3: Website emails (general scraping)
        if website:
            logger.info("   [Tier 3] Scraping website emails...")
            website_emails = self._scrape_website_emails(website)
            for email in website_emails:
                if not self._is_email_in_list(email, all_emails):
                    email_type = 'corporate' if not self._is_generic(email) else 'generic'
                    all_emails.append({
                        'email': email,
                        'type': email_type,
                        'priority': 3 if email_type == 'corporate' else 4,
                        'source': 'Website'
                    })
        
        # TIER 4: Trade directory emails
        logger.info("   [Tier 4] Searching trade directories...")
        trade_emails = self._find_trade_directory_emails(company_name, address)
        for email in trade_emails:
            if not self._is_email_in_list(email, all_emails):
                all_emails.append({
                    'email': email,
                    'type': 'trade',
                    'priority': 3,
                    'source': 'Trade Directory'
                })
        
        # Validate all emails
        validated_emails = []
        for email_obj in all_emails:
            if self._validate_email_syntax(email_obj['email']):
                validated_emails.append(email_obj)
            else:
                logger.warning(f"   ⚠️  Invalid email syntax: {email_obj['email']}")
        
        # Sort by priority (lower = better)
        validated_emails.sort(key=lambda x: x['priority'])
        
        # Prepare result
        result = {
            'primary': validated_emails[0]['email'] if validated_emails else '',
            'secondary': validated_emails[1]['email'] if len(validated_emails) > 1 else '',
            'all': [e['email'] for e in validated_emails],
            'sources': {e['email']: e['source'] for e in validated_emails}
        }
        
        if result['primary']:
            logger.info(f"   ✅ Primary email: {result['primary']} (Source: {validated_emails[0]['source']})")
        
        return result
    
    def _find_emails_with_gemini(self, company_name: str, address: str = "", 
                                  director_name: str = None) -> List[str]:
        """
        Use Gemini AI with Google Search to find emails.
        Gemini can intelligently search and extract email addresses.
        """
        emails = []
        
        if not self.gemini_client:
            return emails
        
        try:
            # Build targeted prompt for email search
            if director_name:
                prompt = f"""Search the web and find the EMAIL ADDRESSES for "{company_name}" located at "{address}".

Focus on finding:
1. Official company email addresses
2. Email of {director_name} (Director/Owner)
3. Corporate emails (not generic info@, contact@)

Return ONLY the email addresses, one per line. If you find multiple emails, list all of them.

Email addresses:"""
            else:
                prompt = f"""Search the web and find the EMAIL ADDRESSES for "{company_name}" located at "{address}".

Find:
1. Official company email addresses
2. Director/Owner email addresses
3. Corporate contact emails (not generic info@, contact@)

Return ONLY the email addresses, one per line.

Email addresses:"""
            
            # Call Gemini with Google Search enabled
            response = self.gemini_client.models.generate_content(
                model='models/gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            
            result_text = response.text.strip()
            logger.info(f"      Gemini response: {result_text[:150]}...")
            
            # Extract emails from response
            found_emails = re.findall(EMAIL_REGEX, result_text)
            for email in found_emails:
                email = email.lower().strip()
                if self._validate_email_syntax(email):
                    emails.append(email)
                    logger.info(f"      ✅ Gemini found email: {email}")
            
        except Exception as e:
            logger.error(f"      ❌ Gemini email search error: {str(e)[:100]}")
        
        return list(set(emails))  # Remove duplicates
    
    def _find_official_email(self, gstin: str, company_name: str) -> Optional[str]:
        """
        Find official email from GST registry.
        Uses Google Dorking to find GSTIN-associated email.
        """
        try:
            query = f'"{gstin}" "{company_name}" "authorized signatory" email'
            search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}&gl=in"
            
            response = self.session.get(search_url, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                text = soup.get_text()
                
                emails = re.findall(EMAIL_REGEX, text)
                # Filter for company domain or professional emails
                for email in emails:
                    if company_name.lower().replace(' ', '') in email.lower():
                        logger.info(f"      ✅ Official email found: {email}")
                        return email.lower()
            
            time.sleep(2)  # Rate limiting
        except Exception as e:
            logger.error(f"      Error finding official email: {str(e)[:50]}")
        
        return None
    
    def _find_corporate_emails(self, website: str, director_name: str) -> List[str]:
        """
        Find corporate emails matching director's name on website.
        Patterns: firstname.lastname@domain.com, flastname@domain.com, etc.
        """
        emails = []
        
        try:
            # Parse director name
            name_parts = director_name.lower().split()
            if len(name_parts) < 2:
                return emails
            
            first_name = name_parts[0]
            last_name = name_parts[-1]
            
            # Get domain from website
            domain = urlparse(website).netloc.replace('www.', '')
            
            # Generate potential email patterns
            patterns = [
                f"{first_name}.{last_name}@{domain}",
                f"{first_name}@{domain}",
                f"{first_name[0]}{last_name}@{domain}",
                f"{last_name}@{domain}",
            ]
            
            # Scrape website to find matching emails
            response = self.session.get(website, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for mailto links
                mailto_links = soup.find_all('a', href=re.compile(r'^mailto:'))
                for link in mailto_links:
                    email = link.get('href').replace('mailto:', '').strip()
                    # Check if matches director name patterns
                    if any(part in email.lower() for part in [first_name, last_name]):
                        emails.append(email.lower())
                        logger.info(f"      ✅ Director email found: {email}")
                
                # Check if any generated patterns exist in page text
                page_text = soup.get_text().lower()
                for pattern in patterns:
                    if pattern in page_text:
                        emails.append(pattern)
                        logger.info(f"      ✅ Pattern match: {pattern}")
            
            time.sleep(2)  # Rate limiting
        except Exception as e:
            logger.error(f"      Error finding corporate emails: {str(e)[:50]}")
        
        return list(set(emails))  # Remove duplicates
    
    def _scrape_website_emails(self, website: str) -> List[str]:
        """
        Scrape all emails from website.
        Handles mailto links and text extraction.
        """
        emails = []
        
        try:
            response = self.session.get(website, timeout=10)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Method 1: mailto links
                mailto_links = soup.find_all('a', href=re.compile(r'^mailto:'))
                for link in mailto_links:
                    email = link.get('href').replace('mailto:', '').strip().split('?')[0]
                    if email:
                        emails.append(email.lower())
                
                # Method 2: Text extraction
                page_text = soup.get_text()
                found_emails = re.findall(EMAIL_REGEX, page_text)
                emails.extend([e.lower() for e in found_emails])
                
                # Method 3: Check "Contact Us" page
                contact_links = soup.find_all('a', href=re.compile(r'contact', re.I))
                if contact_links:
                    contact_url = urljoin(website, contact_links[0].get('href'))
                    try:
                        contact_response = self.session.get(contact_url, timeout=10)
                        if contact_response.status_code == 200:
                            contact_soup = BeautifulSoup(contact_response.content, 'html.parser')
                            contact_text = contact_soup.get_text()
                            contact_emails = re.findall(EMAIL_REGEX, contact_text)
                            emails.extend([e.lower() for e in contact_emails])
                    except:
                        pass
            
            time.sleep(2)  # Rate limiting
        except Exception as e:
            logger.error(f"      Error scraping website: {str(e)[:50]}")
        
        return list(set(emails))  # Remove duplicates
    
    def _find_trade_directory_emails(self, company_name: str, address: str) -> List[str]:
        """
        Find emails from trade directories (SGEPC, IndiaMART, ExportersIndia).
        """
        emails = []
        
        try:
            # Try Export Council directories
            councils = [
                ('sgepc.in', 'SGEPC'),
                ('eepcindia.org', 'EEPC'),
                ('aepcindia.com', 'AEPC'),
            ]
            
            for domain, name in councils:
                query = f'site:{domain} "{company_name}" email'
                search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}&gl=in"
                
                response = self.session.get(search_url, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    # Extract from snippets
                    snippets = soup.find_all(['span', 'div'], class_=re.compile('snippet|description|VwiC3b'))
                    for snippet in snippets:
                        text = snippet.get_text()
                        found_emails = re.findall(EMAIL_REGEX, text)
                        for email in found_emails:
                            if not self._is_generic(email):
                                emails.append(email.lower())
                                logger.info(f"      ✅ Trade directory email: {email} ({name})")
                
                time.sleep(2)  # Rate limiting
        except Exception as e:
            logger.error(f"      Error searching trade directories: {str(e)[:50]}")
        
        return list(set(emails))
    
    def _validate_email_syntax(self, email: str) -> bool:
        """
        Validate email syntax and deliverability.
        Uses email-validator library for professional validation.
        """
        if not email:
            return False
        
        # Use professional email-validator library if available
        if HAS_EMAIL_VALIDATOR:
            try:
                # Validate email with DNS checking
                validated = validate_email(email, check_deliverability=True)
                logger.info(f"      ✅ Email validated: {validated.normalized}")
                return True
            except EmailNotValidError as e:
                logger.warning(f"      ⚠️  Email validation failed: {email} - {str(e)[:50]}")
                return False
        
        # Fallback to basic validation if library not available
        # Basic checks
        if '@' not in email or '.' not in email.split('@')[1]:
            return False
        
        # Check format
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return False
        
        # Check for common typos
        if '..' in email or email.startswith('.') or email.endswith('.'):
            return False
        
        return True
    
    def _is_generic(self, email: str) -> bool:
        """Check if email has generic prefix."""
        prefix = email.split('@')[0].lower()
        return any(generic in prefix for generic in GENERIC_PREFIXES)
    
    def _is_email_in_list(self, email: str, email_list: List[Dict]) -> bool:
        """Check if email already in list."""
        return any(e['email'].lower() == email.lower() for e in email_list)


# Standalone function for easy integration
def enhance_email_extraction(company_name: str, address: str = "",
                            gstin: str = None, director_name: str = None,
                            website: str = None) -> str:
    """
    Quick function to get best email for a company.
    
    Returns primary email or empty string.
    """
    enhancer = EmailEnhancer()
    result = enhancer.find_emails(company_name, address, gstin, director_name, website)
    return result['primary']

