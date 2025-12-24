"""
Email Pattern Finder - Generate and verify email addresses using contact name + company domain.

Strategy:
1. Find company website
2. Extract domain
3. Generate common email patterns
4. Verify which emails are valid
"""

import re
import logging
import requests
from typing import List, Dict, Optional
from urllib.parse import urlparse
import time

logger = logging.getLogger(__name__)

# Try to import email validator
try:
    from email_validator import validate_email, EmailNotValidError
    HAS_EMAIL_VALIDATOR = True
except ImportError:
    HAS_EMAIL_VALIDATOR = False
    logger.warning("email-validator not available")


class EmailPatternFinder:
    """Find email addresses using name + domain pattern matching."""
    
    def __init__(self, serpapi_key: str = None, openai_key: str = None, use_ai_validation: bool = True):
        self.serpapi_key = serpapi_key
        self.openai_key = openai_key
        self.use_ai_validation = use_ai_validation
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # Initialize AI validator if available
        if use_ai_validation and openai_key:
            try:
                from ai_email_validator import AIEmailValidator
                self.ai_validator = AIEmailValidator(openai_api_key=openai_key, serpapi_key=serpapi_key)
                logger.info("✅ AI Email Validation enabled")
            except ImportError:
                self.ai_validator = None
                logger.warning("⚠️  AI Email Validator not available")
        else:
            self.ai_validator = None
    
    def find_email_from_name(self, contact_name: str, company_name: str, 
                            company_website: str = None, address: str = "") -> Dict[str, str]:
        """
        Find email using contact name and company info.
        
        Returns:
            Dict with 'email', 'confidence', 'source_url', 'pattern'
        """
        result = {
            'email': '',
            'confidence': 0,
            'source_url': '',
            'pattern': ''
        }
        
        if not contact_name or len(contact_name.strip()) < 2:
            logger.debug("No valid contact name provided")
            return result
        
        # Step 1: Get company website if not provided
        if not company_website:
            logger.info(f"   [Email Pattern] Finding website for {company_name}...")
            company_website = self._find_company_website(company_name, address)
        
        if not company_website:
            logger.debug(f"   No website found for {company_name}")
            return result
        
        # Step 2: Extract domain
        domain = self._extract_domain(company_website)
        if not domain:
            logger.debug(f"   Could not extract domain from {company_website}")
            return result
        
        logger.info(f"   [Email Pattern] Using domain: {domain}")
        
        # Step 3: Parse contact name
        first_name, last_name = self._parse_name(contact_name)
        if not first_name:
            logger.debug(f"   Could not parse name: {contact_name}")
            return result
        
        logger.info(f"   [Email Pattern] Name: {first_name} {last_name}")
        
        # Step 4: Generate email patterns
        patterns = self._generate_email_patterns(first_name, last_name, domain)
        logger.info(f"   [Email Pattern] Testing {len(patterns)} patterns...")
        
        # Step 5: Check which patterns exist on the website
        verified_email = self._verify_email_on_website(patterns, company_website)
        if verified_email:
            result['email'] = verified_email['email']
            result['confidence'] = 90
            result['source_url'] = company_website
            result['pattern'] = verified_email['pattern']
            logger.info(f"   ✅ Found email on website: {verified_email['email']}")
            return result
        
        # Step 5.5: Use AI to validate/choose best pattern (NEW!)
        if self.ai_validator:
            logger.info(f"   [AI Validation] Using ChatGPT to verify patterns...")
            ai_result = self.ai_validator.validate_multiple_patterns(
                email_patterns=patterns,
                contact_name=contact_name,
                company_name=company_name,
                company_website=company_website
            )
            
            if ai_result.get('best_email'):
                result['email'] = ai_result['best_email']
                result['confidence'] = ai_result.get('confidence', 70)
                result['source_url'] = 'AI Verified' if ai_result.get('found_online') else company_website
                result['pattern'] = 'ai_verified'
                status = "✅ AI Verified" if ai_result.get('found_online') else "⚠️  AI Suggested"
                logger.info(f"   {status}: {result['email']} (Confidence: {result['confidence']}%)")
                logger.debug(f"      Reasoning: {ai_result.get('reasoning', '')[:100]}")
                return result
        
        # Step 6: Fallback - Validate email syntax (basic check)
        for pattern_info in patterns:
            email = pattern_info['email']
            if self._validate_email_syntax(email):
                # Return most likely pattern (first one)
                result['email'] = email
                result['confidence'] = pattern_info['confidence'] - 10  # Lower confidence (no verification)
                result['source_url'] = company_website
                result['pattern'] = pattern_info['pattern']
                logger.info(f"   ⚠️  Probable email (not verified): {email}")
                return result
        
        return result
    
    def _find_company_website(self, company_name: str, address: str = "") -> str:
        """Find company website using Google search."""
        try:
            # Try SerpApi first
            if self.serpapi_key:
                query = f'"{company_name}" {address} official website'.strip()
                params = {
                    'q': query,
                    'api_key': self.serpapi_key,
                    'num': 5,
                    'gl': 'in'
                }
                
                response = requests.get('https://serpapi.com/search', params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Check knowledge graph first
                    if 'knowledge_graph' in data and 'website' in data['knowledge_graph']:
                        return data['knowledge_graph']['website']
                    
                    # Check organic results
                    for result in data.get('organic_results', [])[:5]:
                        link = result.get('link', '')
                        # Filter for likely company websites
                        if any(domain in link.lower() for domain in ['.com', '.in', '.co.in', '.org']):
                            # Skip social media, directories
                            if not any(skip in link.lower() for skip in 
                                     ['facebook', 'linkedin', 'twitter', 'instagram', 
                                      'indiamart', 'justdial', 'tradeindia', 'wikipedia']):
                                logger.debug(f"      Found website: {link}")
                                return link
            
            # Fallback: Try direct URL construction
            company_slug = company_name.lower().replace(' ', '').replace('&', '').replace('-', '')
            common_tlds = ['.com', '.in', '.co.in', '.net']
            
            for tld in common_tlds:
                test_url = f"https://www.{company_slug}{tld}"
                try:
                    test_response = self.session.head(test_url, timeout=5)
                    if test_response.status_code == 200:
                        logger.debug(f"      Found via direct URL: {test_url}")
                        return test_url
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"      Error finding website: {e}")
        
        return ''
    
    def _extract_domain(self, website: str) -> str:
        """Extract domain from website URL."""
        try:
            parsed = urlparse(website)
            domain = parsed.netloc or parsed.path
            # Remove www.
            domain = domain.replace('www.', '')
            # Remove any path
            domain = domain.split('/')[0]
            return domain
        except:
            return ''
    
    def _parse_name(self, full_name: str) -> tuple:
        """Parse full name into first and last name."""
        # Remove titles
        titles = ['mr', 'mrs', 'ms', 'dr', 'prof', 'sir', 'shri', 'smt']
        name_parts = full_name.strip().split()
        
        filtered_parts = []
        for part in name_parts:
            clean_part = part.lower().replace('.', '').strip()
            if clean_part not in titles and len(clean_part) > 1:
                filtered_parts.append(part)
        
        if not filtered_parts:
            return '', ''
        elif len(filtered_parts) == 1:
            return filtered_parts[0].lower(), ''
        else:
            return filtered_parts[0].lower(), filtered_parts[-1].lower()
    
    def _generate_email_patterns(self, first_name: str, last_name: str, domain: str) -> List[Dict]:
        """
        Generate common email patterns.
        
        Returns list of dicts with 'email', 'pattern', 'confidence'
        """
        patterns = []
        
        # Most common patterns (higher confidence)
        if last_name:
            patterns.extend([
                {'email': f"{first_name}.{last_name}@{domain}", 'pattern': 'firstname.lastname', 'confidence': 85},
                {'email': f"{first_name}{last_name}@{domain}", 'pattern': 'firstnamelastname', 'confidence': 80},
                {'email': f"{first_name[0]}{last_name}@{domain}", 'pattern': 'flastname', 'confidence': 75},
                {'email': f"{first_name}@{domain}", 'pattern': 'firstname', 'confidence': 70},
                {'email': f"{last_name}@{domain}", 'pattern': 'lastname', 'confidence': 65},
                {'email': f"{first_name}_{last_name}@{domain}", 'pattern': 'firstname_lastname', 'confidence': 60},
            ])
        else:
            patterns.extend([
                {'email': f"{first_name}@{domain}", 'pattern': 'firstname', 'confidence': 70},
            ])
        
        # Generic patterns (lower confidence)
        patterns.extend([
            {'email': f"info@{domain}", 'pattern': 'info', 'confidence': 50},
            {'email': f"contact@{domain}", 'pattern': 'contact', 'confidence': 50},
            {'email': f"sales@{domain}", 'pattern': 'sales', 'confidence': 45},
        ])
        
        return patterns
    
    def _verify_email_on_website(self, patterns: List[Dict], website: str) -> Optional[Dict]:
        """
        Check if any email pattern exists on the company website.
        """
        try:
            response = self.session.get(website, timeout=10)
            if response.status_code != 200:
                return None
            
            # Get page text
            page_text = response.text.lower()
            
            # Check each pattern
            for pattern_info in patterns:
                email = pattern_info['email']
                if email.lower() in page_text:
                    logger.debug(f"      ✅ Email found on website: {email}")
                    return pattern_info
            
            # Also check contact page
            try:
                contact_urls = [
                    f"{website.rstrip('/')}/contact",
                    f"{website.rstrip('/')}/contact-us",
                    f"{website.rstrip('/')}/about",
                ]
                
                for contact_url in contact_urls:
                    try:
                        contact_response = self.session.get(contact_url, timeout=5)
                        if contact_response.status_code == 200:
                            contact_text = contact_response.text.lower()
                            for pattern_info in patterns:
                                email = pattern_info['email']
                                if email.lower() in contact_text:
                                    logger.debug(f"      ✅ Email found on contact page: {email}")
                                    return pattern_info
                    except:
                        continue
            except:
                pass
                
        except Exception as e:
            logger.debug(f"      Error checking website: {e}")
        
        return None
    
    def _validate_email_syntax(self, email: str) -> bool:
        """Validate email syntax."""
        if not email:
            return False
        
        # Basic regex validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            return False
        
        # Use email-validator if available
        if HAS_EMAIL_VALIDATOR:
            try:
                validate_email(email, check_deliverability=False)  # Syntax only
                return True
            except EmailNotValidError:
                return False
        
        return True


if __name__ == '__main__':
    # Test the Email Pattern Finder
    logging.basicConfig(level=logging.INFO)
    
    import os
    serpapi_key = os.getenv('SERPAPI_API_KEY')
    
    finder = EmailPatternFinder(serpapi_key=serpapi_key)
    
    test_cases = [
        {
            'name': 'Manish Khimasia',
            'company': 'Star Exports',
            'website': 'https://www.starexports.com',
            'address': 'Mumbai'
        },
        {
            'name': 'Neha Kedia',
            'company': 'Hitaashi Solutions',
            'website': None,
            'address': 'Kolkata'
        },
        {
            'name': 'Robin Mepully',
            'company': 'Four He Art Creations',
            'website': None,
            'address': 'Kerala'
        }
    ]
    
    print("\n" + "="*70)
    print("EMAIL PATTERN FINDER - TEST")
    print("="*70)
    
    for test in test_cases:
        print(f"\n🔍 Testing: {test['name']} @ {test['company']}")
        
        result = finder.find_email_from_name(
            contact_name=test['name'],
            company_name=test['company'],
            company_website=test['website'],
            address=test['address']
        )
        
        if result['email']:
            print(f"   ✅ Email: {result['email']}")
            print(f"   📊 Confidence: {result['confidence']}%")
            print(f"   📋 Pattern: {result['pattern']}")
            print(f"   🔗 Source: {result['source_url']}")
        else:
            print(f"   ❌ No email found")
    
    print("\n" + "="*70)

