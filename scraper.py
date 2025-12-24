"""
Web scraping module for extracting contact information from Indian business websites.
Uses requests and BeautifulSoup to scrape publicly available contact data.
Focuses only on Indian businesses and Indian contact information.
Can use AI/LLM for intelligent extraction when standard methods fail.
"""

import requests
from bs4 import BeautifulSoup
import time
import re
import random
from typing import Dict, Optional, List
from urllib.parse import quote, urljoin, urlparse
import logging
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Request headers to mimic a real browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# Rate limiting: seconds to wait between requests
# OPTIMIZED: Reduced from 20-30s to 2-5s for 5-10x speedup
# If you encounter rate limiting (429 errors), increase these values
RATE_LIMIT_DELAY = 3  # Reduced from 20s - monitor for rate limit errors
MAX_RETRIES = 2  # Keep at 2 retries
RETRY_DELAY = 30  # Reduced from 60s - backoff delay after rate limit


def scrape_contact_info(seller_name: str, seller_address: str, use_hunter: bool = False, prefer_indiamart: bool = True) -> Dict[str, str]:
    """
    Scrape contact information for an Indian seller based on name and address.
    Only extracts Indian phone numbers and addresses.
    Tries IndiaMART first (better for Indian businesses), then falls back to Google search.
    Includes rate limiting and error handling for Google blocking.
    
    Args:
        seller_name: Name of the seller/company
        seller_address: Address of the seller
        prefer_indiamart: If True, try IndiaMART first (default: True)
        
    Returns:
        Dictionary containing contact information:
        - contact_name: Contact person name
        - contact_address: Company address (Indian only)
        - email: Email address(es)
        - phone: Phone number(s) (Indian only)
        - source_url: URL where information was found
    """
    result = {
        'contact_name': '',
        'contact_address': '',
        'email': '',
        'phone': '',
        'source_url': ''
    }
    
    try:
        from utils import build_search_query, is_indian_address
        
        # Try IndiaMART first (better for Indian businesses and phone numbers)
        if prefer_indiamart:
            logger.info(f"Trying IndiaMART for: {seller_name}")
            indiamart_data = find_indiamart_listing(seller_name, seller_address)
            
            if indiamart_data and (indiamart_data.get('phone') or indiamart_data.get('email')):
                logger.info(f"Found IndiaMART listing for: {seller_name}")
                result.update(indiamart_data)
                # If we got good data from IndiaMART, return early
                if result.get('phone') or result.get('email'):
                    # Small delay to be respectful
                    time.sleep(random.uniform(2, 4))
                    return result
        
        # Fallback to Google search if IndiaMART didn't work
        logger.info(f"Trying Google search for: {seller_name}")
        search_query = build_search_query(seller_name, seller_address)
        website_url = find_website_url(search_query)
        
        if website_url:
            result['source_url'] = website_url
            # Scrape the website
            contact_data = scrape_website(website_url)
            
            # Merge results (only Indian addresses and phones)
            if contact_data.get('contact_name') and not result.get('contact_name'):
                result['contact_name'] = contact_data['contact_name']
            
            # Only include Indian addresses
            if contact_data.get('contact_address'):
                if is_indian_address(contact_data['contact_address']):
                    if not result.get('contact_address'):
                        result['contact_address'] = contact_data['contact_address']
            
            if contact_data.get('email') and not result.get('email'):
                result['email'] = contact_data['email']
            
            # Only include Indian phone numbers
            if contact_data.get('phone'):
                indian_phones = filter_indian_phones(contact_data['phone'])
                if indian_phones:
                    if not result.get('phone'):
                        result['phone'] = indian_phones
        else:
            # If website not found (possibly due to rate limiting), log it
            logger.debug(f"Could not find website for {seller_name} (may be due to rate limiting)")
        
        # Rate limiting - OPTIMIZED: reduced from 20-30s to 2-5s for 5-10x speedup
        # If you hit rate limits (HTTP 429), increase these delays
        delay = 2 + random.uniform(0, 3)  # 2-5s instead of 20-30s
        time.sleep(delay)
        
    except Exception as e:
        logger.error(f"Error scraping contact info for {seller_name}: {str(e)}")
    
    return result


def filter_indian_phones(phones: List[str]) -> str:
    """
    Filter phone numbers to only include Indian numbers.
    
    Args:
        phones: List of phone numbers
        
    Returns:
        Comma-separated string of Indian phone numbers
    """
    from utils import extract_phone
    
    # Combine all phones and re-extract with Indian pattern
    all_text = ' '.join(phones)
    indian_phones = extract_phone(all_text)
    
    return ', '.join(indian_phones) if indian_phones else ''


def find_website_url(search_query: str, retry_count: int = 0) -> Optional[str]:
    """
    Find the official website URL using Google search (India-focused).
    Includes retry logic and rate limiting handling.
    
    Args:
        search_query: Search query string (should include "India")
        retry_count: Current retry attempt number
        
    Returns:
        Website URL if found, None otherwise
    """
    try:
        # Google search URL with India focus
        search_url = f"https://www.google.com/search?q={quote(search_query)}&gl=in&hl=en"
        
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        
        # Check for rate limiting
        if response.status_code == 429:
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * (retry_count + 1)  # Exponential backoff
                logger.warning(f"Google rate limiting (429). Waiting {wait_time}s before retry {retry_count + 1}/{MAX_RETRIES}")
                time.sleep(wait_time)
                return find_website_url(search_query, retry_count + 1)
            else:
                logger.warning(f"Google rate limiting (429). Max retries reached. Skipping: {search_query[:50]}")
                return None
        
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find first organic search result
        # Google search results are typically in <a> tags with href
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            if href and href.startswith('/url?q='):
                # Extract actual URL from Google's redirect
                actual_url = href.split('/url?q=')[1].split('&')[0]
                # Decode URL
                actual_url = requests.utils.unquote(actual_url)
                
                # Filter out Google's own pages
                if 'google.com' not in actual_url.lower():
                    return actual_url
        
        return None
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            if retry_count < MAX_RETRIES:
                wait_time = RETRY_DELAY * (retry_count + 1)
                logger.warning(f"HTTP 429 error. Waiting {wait_time}s before retry {retry_count + 1}/{MAX_RETRIES}")
                time.sleep(wait_time)
                return find_website_url(search_query, retry_count + 1)
            else:
                logger.warning(f"Google rate limiting (429). Max retries reached. Skipping: {search_query[:50]}")
        else:
            logger.error(f"HTTP error finding website URL: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error finding website URL: {str(e)}")
        return None


def scrape_website(url: str) -> Dict[str, str]:
    """
    Scrape contact information from a website.
    Prioritizes Contact and About pages.
    Only extracts Indian addresses and phone numbers.
    Includes better error handling for rate limiting.
    
    Args:
        url: Website URL to scrape
        
    Returns:
        Dictionary with contact information (Indian only)
    """
    result = {
        'contact_name': '',
        'contact_address': '',
        'email': '',
        'phone': ''
    }
    
    try:
        from utils import is_indian_address, extract_phone
        
        # First, try to find Contact or About page
        contact_pages = find_contact_pages(url)
        
        # Scrape main page and contact pages (limit to avoid too many requests)
        pages_to_scrape = [url] + contact_pages[:1]  # Limit to 1 contact page to reduce requests
        
        all_emails = []
        all_phones = []
        all_addresses = []
        all_names = []
        
        for page_url in pages_to_scrape:
            try:
                page_data = scrape_page(page_url)
                
                if page_data.get('email'):
                    all_emails.extend(page_data['email'])
                
                # Filter for Indian phones only
                if page_data.get('phone'):
                    indian_phones = extract_phone(' '.join(page_data['phone']))
                    if indian_phones:
                        all_phones.extend(indian_phones.split(', '))
                
                # Filter for Indian addresses only
                if page_data.get('address'):
                    if is_indian_address(page_data['address']):
                        all_addresses.append(page_data['address'])
                
                if page_data.get('contact_name'):
                    all_names.append(page_data['contact_name'])
                
                # Delay between page requests to avoid rate limiting
                time.sleep(2)
                
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    logger.warning(f"Rate limited when scraping {page_url}. Skipping remaining pages.")
                    break
                else:
                    logger.warning(f"Error scraping page {page_url}: {str(e)}")
            except Exception as e:
                logger.warning(f"Error scraping page {page_url}: {str(e)}")
                continue
        
        # Select most frequent or most complete values
        if all_emails:
            result['email'] = select_best_value(all_emails)
        if all_phones:
            result['phone'] = select_best_value(all_phones)
        if all_addresses:
            result['contact_address'] = select_best_value(all_addresses)
        if all_names:
            result['contact_name'] = select_best_value(all_names)
        
    except Exception as e:
        logger.error(f"Error scraping website {url}: {str(e)}")
    
    return result


def find_contact_pages(base_url: str) -> List[str]:
    """
    Find Contact or About page links from the main page.
    
    Args:
        base_url: Base website URL
        
    Returns:
        List of contact page URLs
    """
    contact_pages = []
    
    try:
        response = requests.get(base_url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find links that might lead to contact pages
        contact_keywords = ['contact', 'about', 'reach', 'connect', 'get-in-touch']
        
        for link in soup.find_all('a', href=True):
            href = link.get('href')
            link_text = link.get_text().lower()
            
            # Check if link text or href contains contact keywords
            if any(keyword in link_text or keyword in href.lower() for keyword in contact_keywords):
                # Convert relative URLs to absolute
                full_url = urljoin(base_url, href)
                if full_url not in contact_pages:
                    contact_pages.append(full_url)
        
    except Exception as e:
        logger.warning(f"Error finding contact pages: {str(e)}")
    
    return contact_pages


def scrape_page(url: str) -> Dict:
    """
    Scrape a single page for contact information.
    Only extracts Indian phone numbers and addresses.
    
    Args:
        url: URL of the page to scrape
        
    Returns:
        Dictionary with extracted information
    """
    result = {
        'email': [],
        'phone': [],
        'address': '',
        'contact_name': ''
    }
    
    try:
        from utils import extract_phone, is_indian_address
        
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get all text content
        text_content = soup.get_text()
        
        # Extract emails
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, text_content, re.IGNORECASE)
        result['email'] = list(set(emails))
        
        # Extract Indian phones only
        indian_phones = extract_phone(text_content)
        result['phone'] = indian_phones.split(', ') if indian_phones else []
        
        # Try to find address in structured elements
        # Look for address-like patterns or specific HTML elements
        address_elements = soup.find_all(['address', 'div', 'p'], class_=re.compile(r'address|location|office', re.I))
        
        for elem in address_elements:
            text = elem.get_text().strip()
            # Check if it looks like an address and is Indian
            if re.search(r'\d+.*(street|st|avenue|ave|road|rd|boulevard|blvd|city|state|zip|country)', text, re.I):
                if is_indian_address(text):
                    result['address'] = text
                    break
        
        # Extract contact name
        # Look for patterns like "Contact: John Doe" or "Name: Jane Smith"
        name_patterns = [
            r'(?:Contact|Name|Manager|Director)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
        ]
        
        for pattern in name_patterns:
            match = re.search(pattern, text_content)
            if match:
                result['contact_name'] = match.group(1).strip()
                break
        
    except Exception as e:
        logger.warning(f"Error scraping page {url}: {str(e)}")
    
    return result


def select_best_value(values: List[str]) -> str:
    """
    Select the best value from a list (most frequent or most complete).
    
    Args:
        values: List of values
        
    Returns:
        Best value (most frequent, or longest if tie)
    """
    if not values:
        return ''
    
    # Count frequencies
    from collections import Counter
    counter = Counter(values)
    
    # Get most common
    most_common = counter.most_common(1)[0]
    
    # If there's a tie, prefer longer (more complete) value
    max_freq = most_common[1]
    candidates = [val for val, freq in counter.items() if freq == max_freq]
    
    # Return longest candidate
    return max(candidates, key=len)


def find_indiamart_listing(company_name: str, company_address: str = '') -> Optional[Dict[str, str]]:
    """
    Search IndiaMART for a company listing and extract contact information.
    IndiaMART is a popular B2B marketplace in India with good phone number coverage.
    
    Args:
        company_name: Name of the company
        company_address: Address of the company (optional, used for better matching)
        
    Returns:
        Dictionary with contact information if found, None otherwise
    """
    result = {
        'contact_name': '',
        'contact_address': '',
        'email': '',
        'phone': '',
        'source_url': ''
    }
    
    try:
        from utils import extract_phone, is_indian_address, normalize_text
        
        listing_url = None
        
        # Strategy 1: Try constructing URL directly from company name FIRST (no Google needed!)
        # IndiaMART URLs are often: indiamart.com/companyname/ or indiamart.com/companyname/enquiry.html
        company_slug = re.sub(r'[^a-z0-9]+', '', company_name.lower())
        potential_urls = [
            f"https://www.indiamart.com/{company_slug}/",
            f"https://www.indiamart.com/{company_slug}/enquiry.html",
            f"https://www.indiamart.com/{company_slug}/contact-us.html"
        ]
        
        # Try each URL to see if it exists (without Google)
        for url in potential_urls:
            try:
                test_response = requests.head(url, headers=HEADERS, timeout=10, allow_redirects=True)
                if test_response.status_code == 200:
                    listing_url = url
                    logger.info(f"Found IndiaMART listing via direct URL: {listing_url}")
                    break
            except:
                continue
        
        # Strategy 2: Only use Google if direct URL construction failed
        if not listing_url:
            # Use Google to search for IndiaMART listings (only if needed)
            search_query = f"{normalize_text(company_name)} site:indiamart.com"
            google_search_url = f"https://www.google.com/search?q={quote(search_query)}&gl=in&hl=en"
            
            logger.info(f"Searching Google for IndiaMART listing: {company_name}")
            
            # OPTIMIZED: Reduced delay from 15-20s to 2-3s for 7x speedup
            time.sleep(random.uniform(2, 3))
            
            # Search Google for IndiaMART listings
            response = requests.get(google_search_url, headers=HEADERS, timeout=15)
            
            if response.status_code == 429:
                logger.warning("Google rate limiting when searching IndiaMART. Skipping Google search.")
                # Don't return None - try direct URL construction as fallback
                listing_url = potential_urls[0]  # Use first constructed URL as last resort
                logger.info(f"Using constructed IndiaMART URL as fallback: {listing_url}")
            else:
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find IndiaMART listing URLs from Google search results
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    
                    # Extract URL from Google's redirect format
                    if href.startswith('/url?q='):
                        actual_url = href.split('/url?q=')[1].split('&')[0]
                        actual_url = requests.utils.unquote(actual_url)
                        
                        # Check if it's an IndiaMART URL - accept ANY indiamart.com URL
                        if 'indiamart.com' in actual_url.lower():
                            listing_url = actual_url
                            logger.info(f"Found IndiaMART listing via Google: {listing_url}")
                            break
                
                # Alternative: Look for direct indiamart.com links in page text
                if not listing_url:
                    page_text = soup.get_text()
                    url_pattern = r'https?://[^\s]*indiamart\.com[^\s]*'
                    matches = re.findall(url_pattern, page_text)
                    if matches:
                        listing_url = matches[0]
                        logger.info(f"Found IndiaMART URL in page text: {listing_url}")
        
        # Final fallback: Use constructed URL even if we couldn't verify it
        if not listing_url:
            listing_url = potential_urls[0]
            logger.info(f"Using constructed IndiaMART URL as final fallback: {listing_url}")
        
        if not listing_url:
            logger.debug(f"No IndiaMART listing found for: {company_name}")
            return None
        
        result['source_url'] = listing_url
        logger.info(f"Found IndiaMART listing: {listing_url}")
        
        # Scrape the company listing page
        time.sleep(random.uniform(2, 4))  # Be respectful with delays
        listing_data = scrape_indiamart_listing(listing_url)
        
        if listing_data:
            result.update(listing_data)
            logger.info(f"IndiaMART data: phone={result.get('phone', 'N/A')}, email={result.get('email', 'N/A')}, name={result.get('contact_name', 'N/A')}")
        
        # If no phone found, try AI-powered extraction as fallback
        if not result.get('phone') and not result.get('email'):
            logger.info("Trying AI-powered extraction as fallback...")
            try:
                from ai_extractor import extract_with_ai
                # Get the HTML again for AI extraction
                response = requests.get(listing_url, headers=HEADERS, timeout=30)
                if response.status_code == 200:
                    ai_result = extract_with_ai(response.text, company_name)
                    if ai_result:
                        # Merge AI results (prioritize AI findings)
                        if ai_result.get('phone') and not result.get('phone'):
                            result['phone'] = ai_result['phone']
                        if ai_result.get('whatsapp'):
                            result['whatsapp'] = ai_result['whatsapp']
                            # If no phone but we have WhatsApp, use WhatsApp as phone
                            if not result.get('phone'):
                                result['phone'] = ai_result['whatsapp']
                        if ai_result.get('email') and not result.get('email'):
                            result['email'] = ai_result['email']
                        if ai_result.get('contact_name') and not result.get('contact_name'):
                            result['contact_name'] = ai_result['contact_name']
                        if ai_result.get('contact_address') and not result.get('contact_address'):
                            result['contact_address'] = ai_result['contact_address']
                        logger.info(f"✅ AI extraction found additional data")
            except Exception as e:
                logger.debug(f"AI extraction failed: {str(e)}")
        
        # Return result if we found phone OR email (don't require both)
        has_data = result.get('phone') or result.get('email') or result.get('whatsapp') or result.get('contact_name') or result.get('contact_address')
        if has_data:
            logger.info(f"✅ Returning IndiaMART result with data")
        else:
            logger.debug(f"❌ No useful data found from IndiaMART")
        
        return result if has_data else None
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.warning("IndiaMART rate limiting. Skipping.")
        else:
            logger.error(f"HTTP error searching IndiaMART: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error searching IndiaMART: {str(e)}")
        return None


def scrape_indiamart_listing(listing_url: str) -> Optional[Dict[str, str]]:
    """
    Scrape contact information from an IndiaMART company listing page.
    
    Args:
        listing_url: URL of the IndiaMART company listing
        
    Returns:
        Dictionary with contact information
    """
    result = {
        'contact_name': '',
        'contact_address': '',
        'email': '',
        'phone': ''
    }
    
    try:
        from utils import extract_phone, is_indian_address
        
        # Try to get the page with retries for timeout
        response = None
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(listing_url, headers=HEADERS, timeout=30)  # Increased timeout
                break
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 5
                    logger.warning(f"IndiaMART timeout (attempt {attempt + 1}/{max_retries}). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"IndiaMART timeout after {max_retries} attempts: {listing_url}")
                    return None
            except Exception as e:
                logger.error(f"Error fetching IndiaMART page: {str(e)}")
                return None
        
        if not response:
            return None
        
        if response.status_code == 404:
            logger.debug(f"IndiaMART listing not found (404): {listing_url}")
            return None
        
        if response.status_code == 429:
            logger.warning("IndiaMART rate limiting on listing page.")
            return None
        
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Get all text content
        text_content = soup.get_text()
        
        # Debug: Log a sample of the page text to see what we're working with
        logger.info(f"Page text length: {len(text_content)} chars")
        logger.info(f"Page text sample (first 500 chars): {text_content[:500]}")
        
        # Also check for phone numbers in HTML attributes (sometimes phone is in data attributes)
        html_str = str(soup)
        has_call = 'Call' in html_str or 'call' in html_str
        has_plus91 = '+91' in html_str
        logger.info(f"HTML contains 'Call': {has_call}, contains '+91': {has_plus91}")
        
        # Try to find phone in href attributes (sometimes phone is in tel: links)
        tel_links = soup.find_all('a', href=re.compile(r'tel:', re.I))
        for link in tel_links:
            tel_href = link.get('href', '')
            logger.info(f"Found tel: link: {tel_href}")
        
        # Extract phone numbers - ONLY look for "Call +91-XXXXXXXXXX" pattern (most reliable)
        # This is the ONLY pattern we trust from IndiaMART pages
        found_phone = None
        
        # Strategy 1: Look for phone in HTML attributes (href, data-*, etc.)
        # Sometimes phone is in tel: links or data attributes
        for element in soup.find_all(['a', 'button', 'div', 'span']):
            # Check href for tel: links
            href = element.get('href', '')
            if 'tel:' in href.lower():
                tel_match = re.search(r'tel:[\+]?91[-.\s]?([6-9]\d{9})', href, re.I)
                if tel_match:
                    number = tel_match.group(1)
                    if len(number) == 10 and number[0] in '6789':
                        found_phone = '+91-' + number
                        logger.info(f"✅ Found phone in tel: link: {found_phone}")
                        break
            
            # Check data attributes
            for attr_name, attr_value in element.attrs.items():
                if isinstance(attr_value, str) and ('phone' in attr_name.lower() or 'mobile' in attr_name.lower() or 'tel' in attr_name.lower()):
                    phone_match = re.search(r'\+?91[-.\s]?([6-9]\d{9})', attr_value)
                    if phone_match:
                        number = phone_match.group(1)
                        if len(number) == 10 and number[0] in '6789':
                            found_phone = '+91-' + number
                            logger.info(f"✅ Found phone in data attribute: {found_phone}")
                            break
            if found_phone:
                break
        
        # Strategy 2: Look for "Call +91-XXXXXXXXXX" in ALL elements (most reliable)
        if not found_phone:
            for element in soup.find_all(['button', 'a', 'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                element_text = element.get_text()
                # Look for "Call +91-XXXXXXXXXX" pattern - MUST start with 6-9
                call_match = re.search(r'Call\s*\+?91[-.\s]?([6-9]\d{9})', element_text, re.I)
                if call_match:
                    number = call_match.group(1)
                    # Double validation: must be 10 digits starting with 6-9
                    if len(number) == 10 and number[0] in '6789':
                        found_phone = '+91-' + number
                        logger.info(f"✅ Found phone in element text: {found_phone}")
                        break  # Found it, stop looking
        
        # Strategy 3: Search HTML string directly (sometimes text extraction misses it)
        if not found_phone:
            html_str = str(soup)
            # Look for "Call +91-XXXXXXXXXX" in raw HTML
            call_match = re.search(r'Call\s*\+?91[-.\s]?([6-9]\d{9})', html_str, re.I)
            if call_match:
                number = call_match.group(1)
                if len(number) == 10 and number[0] in '6789':
                    found_phone = '+91-' + number
                    logger.info(f"✅ Found phone in HTML string: {found_phone}")
        
        # Strategy 2: If not found, search full page text for "Call +91-XXXXXXXXXX"
        if not found_phone:
            call_match = re.search(r'Call\s*\+?91[-.\s]?([6-9]\d{9})', text_content, re.I)
            if call_match:
                number = call_match.group(1)
                if len(number) == 10 and number[0] in '6789':
                    found_phone = '+91-' + number
                    logger.info(f"✅ Found phone in page text: {found_phone}")
        
        # Strategy 4: Last resort - look for +91-XXXXXXXXXX in HTML (but ONLY if starts with 6-9)
        if not found_phone:
            plus91_match = re.search(r'\+?91[-.\s]?([6-9]\d{9})', html_str)
            if plus91_match:
                number = plus91_match.group(1)
                if len(number) == 10 and number[0] in '6789':
                    found_phone = '+91-' + number
                    logger.info(f"✅ Found phone via +91 pattern in HTML: {found_phone}")
        
        # Strategy 5: Look for standalone 10-digit numbers starting with 6-9 in HTML
        # Sometimes phone is shown without +91 prefix
        if not found_phone:
            # Look for patterns like "8044016146" or "91-8044016146" in HTML
            standalone_match = re.search(r'(?:^|[^\d])([6-9]\d{9})(?:[^\d]|$)', html_str)
            if standalone_match:
                number = standalone_match.group(1)
                if len(number) == 10 and number[0] in '6789':
                    found_phone = '+91-' + number
                    logger.info(f"✅ Found phone as standalone number in HTML: {found_phone}")
        
        # Set result - ONLY if we found a valid phone
        if found_phone:
            result['phone'] = found_phone
            logger.info(f"✅ Final phone number: {result['phone']}")
        else:
            logger.debug(f"❌ No valid phone number found (must match 'Call +91-XXXXXXXXXX' and start with 6-9)")
            # Debug: Show a snippet of page text to help diagnose
            if len(text_content) > 0:
                # Look for any phone-like patterns in the text for debugging
                debug_phones = re.findall(r'\+?91[-.\s]?\d{10}', text_content)
                if debug_phones:
                    logger.debug(f"Found phone-like patterns in page (may be invalid): {debug_phones[:3]}")
        
        # Extract emails - look in HTML string too (sometimes not in text content)
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        
        # Try text content first
        emails = re.findall(email_pattern, text_content, re.IGNORECASE)
        
        # If not found, try HTML string
        if not emails:
            emails = re.findall(email_pattern, html_str, re.IGNORECASE)
        
        if emails:
            # Filter out common non-business emails
            business_emails = [e for e in emails if not any(x in e.lower() for x in 
                           ['noreply', 'no-reply', 'donotreply', 'indiamart.com', 'example.com', 
                            'test.com', 'sample.com', 'gmail.com', 'yahoo.com', 'hotmail.com'])]
            if business_emails:
                result['email'] = business_emails[0]  # Take first valid email
                logger.info(f"✅ Found email: {result['email']}")
            else:
                # If only generic emails found, check if any look business-like
                # Look for emails with company domain or business patterns
                for email in emails:
                    domain = email.split('@')[1] if '@' in email else ''
                    # Accept if domain doesn't look like personal email
                    if domain and not any(x in domain for x in ['gmail', 'yahoo', 'hotmail', 'outlook', 'rediffmail']):
                        result['email'] = email
                        logger.info(f"✅ Found email (business domain): {result['email']}")
                        break
        
        # Try to find contact name - IndiaMART shows "Name (Title)" format
        # Look for patterns like "Abhishek Sharma (Project Director)"
        contact_name = None
        
        # Strategy 1: Look for name with title in parentheses (most common format)
        name_with_title = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*\([^)]*(?:Director|Manager|Owner|Partner|CEO|Founder|President|Head)', text_content)
        if name_with_title:
            contact_name = name_with_title.group(1).strip()
            logger.debug(f"Found contact name with title: {contact_name}")
        
        # Strategy 2: Look in "Reach Us" or contact sections
        if not contact_name:
            reach_section = soup.find(string=re.compile(r'Reach\s+Us', re.I))
            if reach_section:
                parent = reach_section.find_parent(['div', 'section'])
                if parent:
                    section_text = parent.get_text()
                    # Look for name pattern in this section
                    name_match = re.search(r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s*\([^)]*\)', section_text)
                    if name_match:
                        contact_name = name_match.group(1).strip()
        
        # Strategy 3: Look for "Contact Person:" pattern
        if not contact_name:
            contact_person_match = re.search(r'(?:Contact\s+Person|Contact\s+Name)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text_content, re.I)
            if contact_person_match:
                contact_name = contact_person_match.group(1).strip()
        
        # Filter out false positives
        if contact_name:
            # Remove common false positives
            if len(contact_name.split()) <= 4 and contact_name.lower() not in ['india', 'company', 'business', 'indiamart']:
                result['contact_name'] = contact_name
        
        # Try to find address - IndiaMART has "Reach Us" section
        # Look for "Reach Us" section specifically
        reach_us_section = soup.find(string=re.compile(r'Reach\s+Us', re.I))
        if reach_us_section:
            parent = reach_us_section.find_parent(['div', 'section'])
            if parent:
                # Get all text from this section
                address_text = parent.get_text()
                
                # Clean up: Remove "Reach Us" header, navigation items, buttons, etc.
                # Remove common IndiaMART UI elements
                address_text = re.sub(r'Reach\s+Us[:\s]*', '', address_text, flags=re.I)
                address_text = re.sub(r'Get\s+Directions.*', '', address_text, flags=re.I)
                address_text = re.sub(r'Call\s*\+?91[^\s]*.*', '', address_text, flags=re.I)  # Remove phone numbers
                address_text = re.sub(r'Contact\s+Supplier.*', '', address_text, flags=re.I)
                address_text = re.sub(r'Submit\s+Requirement.*', '', address_text, flags=re.I)
                address_text = re.sub(r'BuyLeads|Products|SellHelp|Messages|Home|About\s+Us|Photos|Contact\s+Us', '', address_text, flags=re.I)
                address_text = re.sub(r'IndiaMART.*', '', address_text, flags=re.I)
                
                # Remove extra whitespace
                address_text = ' '.join(address_text.split())
                
                # Extract just the address part (should contain location info)
                # Split by newlines and filter
                lines = [line.strip() for line in address_text.split('\n') if line.strip()]
                address_lines = []
                
                for line in lines:
                    # Skip very short lines
                    if len(line) < 15:
                        continue
                    
                    # Skip navigation and UI elements
                    skip_keywords = ['get best', 'price', 'exporters', 'lead manager', 'buy', 'sell', 
                                   'home', 'products', 'about us', 'photos', 'contact us', 'messages',
                                   'indiamart', 'call', 'contact supplier', 'submit requirement']
                    if any(x in line.lower() for x in skip_keywords):
                        continue
                    
                    # Skip if it's a phone number
                    if re.search(r'\+?91[-.\s]?\d{10}', line):
                        continue
                    
                    # Skip if it's a contact name (has title in parentheses)
                    if re.search(r'\([^)]*(?:Director|Manager|Owner|Partner|CEO)', line, re.I):
                        continue
                    
                    # Keep if it looks like an address
                    if is_indian_address(line) or any(x in line.lower() for x in ['plot', 'street', 'road', 'area', 'sector', 'industrial', 'complex', 'faridabad', 'delhi', 'mumbai', 'haryana', 'maharashtra']):
                        address_lines.append(line)
                
                if address_lines:
                    # Join address lines and clean up
                    clean_address = ', '.join(address_lines[:3])
                    # Remove extra commas and spaces
                    clean_address = re.sub(r',+', ',', clean_address)
                    clean_address = re.sub(r'\s+', ' ', clean_address).strip()
                    result['contact_address'] = clean_address[:200]
                    logger.info(f"Extracted address from Reach Us section: {result['contact_address']}")
        
        # Alternative: Look for address in specific divs/classes (but filter out navigation)
        if not result.get('contact_address'):
            address_divs = soup.find_all(['div', 'p'], class_=re.compile(r'address|location|office|reach', re.I))
            for div in address_divs:
                text = div.get_text().strip()
                # Filter out navigation and UI elements
                if any(x in text.lower() for x in ['get best', 'price', 'exporters', 'lead manager', 'buy', 'sell', 'home', 'products']):
                    continue
                
                # Clean up
                text = re.sub(r'^(Address|Location|Office|Reach\s+Us)[:\s]*', '', text, flags=re.I)
                text = ' '.join(text.split())  # Normalize whitespace
                
                if len(text) > 20 and is_indian_address(text):
                    result['contact_address'] = text[:200]
                    break
        
        return result
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.warning("IndiaMART rate limiting on listing page.")
        else:
            logger.error(f"HTTP error scraping IndiaMART listing: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error scraping IndiaMART listing: {str(e)}")
        return None

