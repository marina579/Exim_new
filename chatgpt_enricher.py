"""
ChatGPT-powered contact enrichment for EXIM sellers.
Uses OpenAI API to search and extract phone + email for each company.
"""

import os
import pandas as pd
import logging
from typing import Dict, Optional
import json
import re
import requests

# Note: You need to install openai package (Enhanced with error logging)
# pip install openai

try:
    from openai import OpenAI
except ImportError:
    print("⚠️  OpenAI package not installed. Run: pip install openai")
    OpenAI = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatGPTEnricher:
    """Uses ChatGPT to find contact information for companies."""
    
    def __init__(self, api_key: str = None):
        """
        Initialize ChatGPT enricher.
        
        Args:
            api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env variable.
        """
        if OpenAI is None:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
        
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY env variable or pass api_key parameter.")
        
        self.client = OpenAI(api_key=self.api_key)
        logger.info("✅ ChatGPT enricher initialized")
    
    def find_contact(self, company_name: str, address: str = "") -> Dict[str, str]:
        """
        Use ChatGPT to find phone number and email for a company.
        
        Args:
            company_name: Name of the company
            address: Address of the company (optional but helps accuracy)
        
        Returns:
            Dictionary with 'phone', 'email', 'whatsapp' keys
        """
        # Since ChatGPT API doesn't have web search, we use SerpApi to get search data
        # then use ChatGPT to extract contacts from the structured results
        
        # Step 1: Get search results from SerpApi
        search_results = self._search_with_serpapi(company_name, address)
        
        # Step 2: Use ChatGPT to extract contact info from search results
        if address:
            prompt = f"""I searched Google for "{company_name} {address} India contact" and got these results:

{search_results}

Extract the contact person name, phone number, WhatsApp number, and email address for this Indian business from the search results above.
Look for: Proprietor name, Director name, Owner name, or main contact person.
Return ONLY valid Indian phone numbers (starting with +91 and digits 6-9) and business emails.
Return in this exact JSON format: {{"contact_name": "Full Name", "phone": "+91-XXXXXXXXXX", "email": "xxx@xxx.com", "whatsapp": "+91-XXXXXXXXXX"}}
If not found, use empty string "".
"""
        else:
            prompt = f"""I searched Google for "{company_name} India contact" and got these results:

{search_results}

Extract the contact person name, phone number, WhatsApp number, and email address for this Indian business from the search results above.
Look for: Proprietor name, Director name, Owner name, or main contact person.
Return ONLY valid Indian phone numbers (starting with +91 and digits 6-9) and business emails.
Return in this exact JSON format: {{"contact_name": "Full Name", "phone": "+91-XXXXXXXXXX", "email": "xxx@xxx.com", "whatsapp": "+91-XXXXXXXXXX"}}
If not found, use empty string "".
"""
        
        try:
            # Call ChatGPT API to parse search results
            logger.info(f"🤖 Calling OpenAI API for {company_name}...")
            logger.debug(f"API Key present: {bool(self.api_key)}")
            logger.debug(f"API Key prefix: {self.api_key[:10] if self.api_key else 'N/A'}...")
            
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Faster and cheaper model
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data extraction expert. Extract contact information from search results and return it in JSON format. Only return verified, valid Indian phone numbers and business emails."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Very low temperature for factual extraction
                max_tokens=200
            )
            
            # Extract response
            result_text = response.choices[0].message.content.strip()
            logger.info(f"✅ ChatGPT response for {company_name}: {result_text[:100]}")
            
            # Try to parse JSON response
            try:
                # Extract JSON from response (might have markdown code blocks)
                json_match = re.search(r'\{[^}]+\}', result_text)
                if json_match:
                    result_json = json.loads(json_match.group())
                    return {
                        'contact_name': result_json.get('contact_name', ''),
                        'phone': result_json.get('phone', ''),
                        'email': result_json.get('email', ''),
                        'whatsapp': result_json.get('whatsapp', '')
                    }
            except json.JSONDecodeError:
                # If JSON parsing fails, try to extract from text
                phone = self._extract_phone_from_text(result_text)
                email = self._extract_email_from_text(result_text)
                whatsapp = self._extract_whatsapp_from_text(result_text)
                contact_name = self._extract_name_from_text(result_text)
                
                return {
                    'contact_name': contact_name,
                    'phone': phone,
                    'email': email,
                    'whatsapp': whatsapp
                }
            
            return {'contact_name': '', 'phone': '', 'email': '', 'whatsapp': ''}
            
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(f"❌ ChatGPT error for {company_name}: {error_type}: {error_msg}")
            
            # Log specific error types for debugging
            if "401" in error_msg or "Unauthorized" in error_msg:
                logger.error("🔑 API Key issue: Invalid or expired OpenAI API key")
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                logger.error("⏱️  Rate limit exceeded: Too many requests to OpenAI")
            elif "timeout" in error_msg.lower():
                logger.error("⏰ Timeout: OpenAI API request timed out")
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                logger.error("🌐 Network issue: Cannot connect to OpenAI API")
            else:
                logger.error(f"❓ Unknown error: {error_type}")
            
            return {'contact_name': '', 'phone': '', 'email': '', 'whatsapp': ''}
    
    def _extract_phone_from_text(self, text: str) -> str:
        """Extract Indian phone number from text."""
        # Look for +91-XXXXXXXXXX or similar patterns
        patterns = [
            r'\+91[-.\s]?[6-9]\d{9}',
            r'91[-.\s]?[6-9]\d{9}',
            r'\+91[-.\s]?\d{5}[-.\s]?\d{5}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group()
                # Normalize format
                digits = re.sub(r'[^\d]', '', phone)
                if len(digits) >= 10:
                    return '+91-' + digits[-10:]
        
        return ''
    
    def _extract_email_from_text(self, text: str) -> str:
        """Extract email from text."""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, text, re.IGNORECASE)
        return match.group() if match else ''
    
    def _extract_whatsapp_from_text(self, text: str) -> str:
        """Extract WhatsApp number from text."""
        # Look for WhatsApp mentions with phone numbers
        whatsapp_pattern = r'[Ww]hats[Aa]pp[:\s]+(\+91[-.\s]?[6-9]\d{9})'
        match = re.search(whatsapp_pattern, text)
        if match:
            digits = re.sub(r'[^\d]', '', match.group(1))
            if len(digits) >= 10:
                return '+91-' + digits[-10:]
        return ''
    
    def _extract_name_from_text(self, text: str) -> str:
        """Extract contact person name from text."""
        # Look for common patterns like "Proprietor: Name", "Director: Name", "Owner: Name"
        patterns = [
            r'[Pp]roprietor[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'[Dd]irector[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'[Oo]wner[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'[Cc]ontact[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'[Mm]r\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'[Mm]rs\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        
        return ''
    
    def _search_with_serpapi(self, company_name: str, address: str = "") -> str:
        """
        Use SerpApi to get search results (more reliable than direct Google scraping).
        Returns formatted search results text for ChatGPT to parse.
        """
        try:
            # Check if SerpApi key is available
            serpapi_key = os.getenv('SERPAPI_API_KEY')
            if not serpapi_key:
                logger.warning("SerpApi key not available for ChatGPT fallback")
                return ""
            
            # Build search query
            if address:
                query = f"{company_name} {address} India phone contact email"
            else:
                query = f"{company_name} India contact phone email IndiaMART Justdial"
            
            # Call SerpApi
            params = {
                'q': query,
                'api_key': serpapi_key,
                'engine': 'google',
                'gl': 'in',
                'hl': 'en',
                'num': 10
            }
            
            response = requests.get('https://serpapi.com/search', params=params, timeout=30)
            
            if response.status_code != 200:
                logger.warning(f"SerpApi returned {response.status_code}")
                return ""
            
            data = response.json()
            results_text = []
            
            # Extract from organic results
            if 'organic_results' in data:
                for result in data['organic_results'][:10]:
                    title = result.get('title', '')
                    snippet = result.get('snippet', '')
                    link = result.get('link', '')
                    
                    if title or snippet:
                        results_text.append(f"Title: {title}\nURL: {link}\n{snippet}\n")
            
            # Extract from knowledge graph
            if 'knowledge_graph' in data:
                kg = data['knowledge_graph']
                kg_text = f"Business Info: {kg.get('title', '')} - {kg.get('type', '')}\n"
                if 'address' in kg:
                    kg_text += f"Address: {kg['address']}\n"
                if 'phone' in kg:
                    kg_text += f"Phone: {kg['phone']}\n"
                results_text.insert(0, kg_text)
            
            # Extract from local results
            if 'local_results' in data and isinstance(data['local_results'], list):
                for local in data['local_results'][:3]:
                    local_text = f"Business: {local.get('title', '')}\n"
                    if 'phone' in local:
                        local_text += f"Phone: {local['phone']}\n"
                    if 'address' in local:
                        local_text += f"Address: {local['address']}\n"
                    results_text.insert(0, local_text)
            
            combined = '\n---\n'.join(results_text[:15])
            logger.debug(f"SerpApi search results length: {len(combined)} chars")
            
            return combined if combined else "No search results found"
            
        except Exception as e:
            logger.error(f"Error searching with SerpApi: {str(e)}")
            return ""
    
    def _search_google(self, company_name: str, address: str = "") -> str:
        """
        Search Google for company contact information.
        Returns formatted search results text for ChatGPT to parse.
        """
        from bs4 import BeautifulSoup
        from urllib.parse import quote
        
        try:
            # Build search query
            if address:
                query = f"{company_name} {address} India contact phone email"
            else:
                query = f"{company_name} India contact phone email IndiaMART"
            
            # Search URL
            search_url = f"https://www.google.com/search?q={quote(query)}&gl=in&hl=en"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(search_url, headers=headers, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Google search returned {response.status_code}")
                return ""
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract search result snippets
            results_text = []
            
            # Get text from search results
            page_text = soup.get_text()
            
            # Extract snippets with phone numbers
            phone_snippets = re.findall(r'.{0,100}\+?91[-.\s]?[6-9]\d{9}.{0,100}', page_text)
            results_text.extend(phone_snippets[:5])
            
            # Extract snippets with email addresses
            email_snippets = re.findall(r'.{0,100}[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}.{0,100}', page_text, re.I)
            results_text.extend(email_snippets[:5])
            
            # Get some general result snippets
            for div in soup.find_all(['div', 'span'], limit=20):
                text = div.get_text().strip()
                if 20 < len(text) < 300 and (
                    'phone' in text.lower() or 
                    'contact' in text.lower() or 
                    'email' in text.lower() or
                    '@' in text or
                    '+91' in text
                ):
                    results_text.append(text)
            
            # Limit to avoid token overflow
            combined = '\n---\n'.join(results_text[:15])
            
            logger.debug(f"Search results length: {len(combined)} chars")
            
            return combined if combined else "No search results found"
            
        except Exception as e:
            logger.error(f"Error searching Google: {str(e)}")
            return ""


def enrich_excel_with_chatgpt(input_excel: str, output_excel: str, api_key: str = None, max_rows: int = None):
    """
    Enrich EXIM Excel file with contact information using ChatGPT.
    
    Args:
        input_excel: Path to input Excel file
        output_excel: Path to output Excel file
        api_key: OpenAI API key (optional if OPENAI_API_KEY env var is set)
        max_rows: Maximum rows to process (for testing)
    """
    print(f"\n{'='*70}")
    print("ChatGPT Contact Enrichment")
    print(f"{'='*70}\n")
    
    # Initialize enricher
    try:
        enricher = ChatGPTEnricher(api_key=api_key)
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return
    
    # Read Excel
    print(f"📄 Reading: {input_excel}")
    try:
        df = pd.read_excel(input_excel, header=2, engine='openpyxl')
        print(f"✅ Loaded {len(df)} sellers\n")
    except Exception as e:
        print(f"❌ Error reading Excel: {str(e)}")
        return
    
    # Find seller name and address columns
    seller_name_col = None
    seller_addr_col = None
    
    for col in df.columns:
        col_upper = str(col).upper()
        if 'SELLER' in col_upper and 'ADDRESS' not in col_upper:
            seller_name_col = col
        elif 'SELLER' in col_upper and 'ADDRESS' in col_upper:
            seller_addr_col = col
    
    if not seller_name_col:
        print("❌ Could not find 'SELLER' column in Excel")
        return
    
    # Process rows
    rows_to_process = df.head(max_rows) if max_rows else df
    
    enriched_data = []
    stats = {'total': 0, 'with_phone': 0, 'with_email': 0, 'with_whatsapp': 0}
    
    print("Processing sellers...\n")
    
    for idx, row in rows_to_process.iterrows():
        seller_name = str(row.get(seller_name_col, '')).strip()
        seller_addr = str(row.get(seller_addr_col, '')).strip() if seller_addr_col else ''
        
        if not seller_name or seller_name == 'nan':
            continue
        
        stats['total'] += 1
        print(f"[{stats['total']}] {seller_name[:50]:<50}", end=" ... ", flush=True)
        
        # Get contact info from ChatGPT
        contact = enricher.find_contact(seller_name, seller_addr)
        
        phone = contact.get('phone', '').strip()
        email = contact.get('email', '').strip()
        whatsapp = contact.get('whatsapp', '').strip()
        
        if phone:
            stats['with_phone'] += 1
        if email:
            stats['with_email'] += 1
        if whatsapp:
            stats['with_whatsapp'] += 1
        
        # Display result
        if phone or email or whatsapp:
            parts = []
            if phone:
                parts.append(f"📞 {phone}")
            if email:
                parts.append(f"✉️  {email}")
            if whatsapp:
                parts.append(f"💬 {whatsapp}")
            print(f"✅ {' | '.join(parts)}")
        else:
            print("❌ No contact found")
        
        # Add to output
        enriched_data.append({
            'Seller Name': seller_name,
            'Seller Address': seller_addr,
            'Phone': phone,
            'WhatsApp': whatsapp,
            'Email': email
        })
    
    # Save to Excel
    print(f"\n💾 Saving to: {output_excel}")
    output_df = pd.DataFrame(enriched_data)
    output_df.to_excel(output_excel, index=False, engine='openpyxl')
    
    # Print summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Total processed: {stats['total']}")
    if stats['total'] > 0:
        print(f"With phone: {stats['with_phone']} ({stats['with_phone']*100//stats['total']}%)")
        print(f"With email: {stats['with_email']} ({stats['with_email']*100//stats['total']}%)")
        print(f"With WhatsApp: {stats['with_whatsapp']} ({stats['with_whatsapp']*100//stats['total']}%)")
    print(f"\n✅ Done! Output saved to: {output_excel}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    import sys
    
    # Example usage
    print("\n" + "="*70)
    print("ChatGPT Contact Enrichment - Setup")
    print("="*70 + "\n")
    
    # Check for API key
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OpenAI API key not found!")
        print("\nTo use this tool:")
        print("1. Get your API key from: https://platform.openai.com/api-keys")
        print("2. Set it as environment variable:")
        print("   export OPENAI_API_KEY='your-api-key-here'")
        print("\nOr pass it directly when calling enrich_excel_with_chatgpt()")
        sys.exit(1)
    
    print("✅ API key found")
    print("\nUsage:")
    print("  python chatgpt_enricher.py")
    print("\nOr in your code:")
    print("  from chatgpt_enricher import enrich_excel_with_chatgpt")
    print("  enrich_excel_with_chatgpt('input.xlsx', 'output.xlsx', max_rows=10)")
    print("\n" + "="*70 + "\n")

