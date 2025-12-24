"""
Gemini AI-powered contact enrichment.
Uses Google's Gemini API to search and extract phone + email for companies.
Updated to use the new google-genai package.
"""

import os
import json
import logging
import re
import requests
from typing import Dict

try:
    from google import genai
    from google.genai import types
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    logging.warning("google-genai not installed")

logger = logging.getLogger(__name__)


class GeminiEnricher:
    """Uses Gemini AI to find contact information."""
    
    def __init__(self, api_key: str = None):
        """
        Initialize Gemini enricher.
        
        Args:
            api_key: Google AI Studio API key
        """
        if not HAS_GEMINI:
            raise ImportError("google-genai package not installed. Run: pip install google-genai")
        
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Gemini API key required. Get one from: https://aistudio.google.com/apikey")
        
        # Initialize client (only pass api_key to avoid proxies error)
        try:
            self.client = genai.Client(api_key=self.api_key)
        except TypeError as e:
            if 'proxies' in str(e):
                # Retry without any extra parameters
                self.client = genai.Client(api_key=self.api_key)
            else:
                raise
        
        logger.info("✅ Gemini enricher initialized")
    
    def find_contact(self, company_name: str, address: str = "") -> Dict[str, str]:
        """
        Use Gemini with Google Search to find phone number and email for a company.
        This uses Google Search Grounding - Gemini searches the web itself!
        
        Args:
            company_name: Name of the company
            address: Address of the company (helps accuracy)
        
        Returns:
            Dictionary with 'phone', 'email', 'whatsapp' keys
        """
        result = {
            'phone': '',
            'email': '',
            'whatsapp': '',
            'contact_name': ''
        }
        
        try:
            # Build prompt - let Gemini search the web itself!
            if address:
                prompt = f"""Search the web and find the contact information for "{company_name}" located at "{address}" in India.

Find their:
- Contact person name (Proprietor, Director, or Owner name)
- Phone number (Indian mobile: +91-XXXXXXXXXX)
- Email address
- WhatsApp number if mentioned

Return ONLY this JSON format:
{{"contact_name": "Full Name", "phone": "+91-XXXXXXXXXX", "email": "xxx@xxx.com", "whatsapp": "+91-XXXXXXXXXX"}}

If not found, use empty string "".
"""
            else:
                prompt = f"""Search the web and find the contact information for "{company_name}" in India.

Find their:
- Contact person name (Proprietor, Director, or Owner name)
- Phone number (Indian mobile: +91-XXXXXXXXXX)  
- Email address
- WhatsApp number if mentioned

Return ONLY this JSON format:
{{"contact_name": "Full Name", "phone": "+91-XXXXXXXXXX", "email": "xxx@xxx.com", "whatsapp": "+91-XXXXXXXXXX"}}

If not found, use empty string "".
"""
            
            # Call Gemini API with Google Search Grounding enabled
            # Using gemini-2.5-flash (latest stable model with Google Search)
            response = self.client.models.generate_content(
                model='models/gemini-2.5-flash',  # Latest stable model!
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    tools=[types.Tool(google_search=types.GoogleSearch())]  # Enable web search!
                )
            )
            
            result_text = response.text.strip()
            
            logger.info(f"Gemini response for {company_name}: {result_text[:300]}")
            
            # Try JSON parsing first
            try:
                # Clean markdown code blocks if present
                clean_text = result_text
                if '```' in clean_text:
                    clean_text = clean_text.split('```')[1]
                    if clean_text.startswith('json'):
                        clean_text = clean_text[4:]
                
                result_json = json.loads(clean_text.strip())
                
                return {
                    'phone': result_json.get('phone', ''),
                    'email': result_json.get('email', ''),
                    'whatsapp': result_json.get('whatsapp', '')
                }
            except (json.JSONDecodeError, Exception):
                # JSON parsing failed - extract from text (Gemini often returns prose)
                logger.info("Extracting from text response...")
                phone = self._extract_phone_from_text(result_text)
                email = self._extract_email_from_text(result_text)
                whatsapp = self._extract_whatsapp_from_text(result_text)
                
                if phone or email:
                    logger.info(f"✅ Extracted: phone={phone}, email={email}")
                
                return {
                    'phone': phone,
                    'email': email,
                    'whatsapp': whatsapp
                }
            
        except Exception as e:
            logger.error(f"Error finding contact for {company_name}: {str(e)}")
            return result
    
    def _search_with_serpapi(self, company_name: str, address: str = "") -> str:
        """
        Use SerpApi to get search results.
        Returns formatted search results text for Gemini to parse.
        """
        try:
            serpapi_key = os.getenv('SERPAPI_API_KEY')
            if not serpapi_key:
                logger.warning("SerpApi key not available for Gemini fallback")
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
                kg_text = f"Business: {kg.get('title', '')} - {kg.get('type', '')}\n"
                if 'address' in kg:
                    kg_text += f"Address: {kg['address']}\n"
                if 'phone' in kg:
                    kg_text += f"Phone: {kg['phone']}\n"
                results_text.insert(0, kg_text)
            
            # Extract from local results
            if 'local_results' in data and isinstance(data.get('local_results'), list):
                for local in data.get('local_results', [])[:3]:
                    local_text = f"Business: {local.get('title', '')}\n"
                    if 'phone' in local:
                        local_text += f"Phone: {local['phone']}\n"
                    if 'address' in local:
                        local_text += f"Address: {local['address']}\n"
                    results_text.insert(0, local_text)
            
            combined = '\n---\n'.join(results_text[:15])
            
            return combined if combined else "No search results found"
            
        except Exception as e:
            logger.error(f"Error searching with SerpApi: {str(e)}")
            return ""
    
    def _extract_phone_from_text(self, text: str) -> str:
        """Extract Indian phone number from text."""
        patterns = [
            r'\+91[-.\s]?[6-9]\d{9}',
            r'91[-.\s]?[6-9]\d{9}',
            r'\b[6-9]\d{9}\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                phone = match.group()
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
        whatsapp_pattern = r'[Ww]hats[Aa]pp[:\s]+(\+91[-.\s]?[6-9]\d{9})'
        match = re.search(whatsapp_pattern, text)
        if match:
            digits = re.sub(r'[^\d]', '', match.group(1))
            if len(digits) >= 10:
                return '+91-' + digits[-10:]
        return ''
