"""
WhatsApp Detective - Two-Pronged Approach for Finding WhatsApp Numbers

APPROACH 1: Google Maps API (via SerpApi) for local/boutique addresses
APPROACH 2: GST/B2B Enrichment API for industrial addresses

Architecture:
1. Parse address (extract landmark, pincode, city, state)
2. Determine if local/boutique or industrial
3. Try appropriate method first, then fallback to other
4. Validate mobile numbers (10 digits, starts with 6-9)
5. Return WhatsApp number with confidence score
"""

import os
import re
import logging
from typing import Dict, Optional, Tuple
import requests
from urllib.parse import quote

logger = logging.getLogger(__name__)


class AddressParser:
    """Parse Indian addresses to extract components."""
    
    @staticmethod
    def parse(address: str) -> Dict[str, str]:
        """
        Parse address into components.
        
        Returns:
            Dict with: landmark, city, state, pincode, is_industrial
        """
        address_upper = address.upper()
        
        # Extract pincode (6 digits)
        pincode_match = re.search(r'\b\d{6}\b', address)
        pincode = pincode_match.group(0) if pincode_match else ''
        
        # Extract state (common patterns)
        state_patterns = {
            'MAHARASHTRA|MUMBAI|PUNE|NAGPUR': 'Maharashtra',
            'WEST BENGAL|KOLKATA|BENGAL|WB': 'West Bengal',
            'DELHI|NEW DELHI': 'Delhi',
            'TAMIL NADU|CHENNAI|TN': 'Tamil Nadu',
            'KARNATAKA|BANGALORE|BENGALURU': 'Karnataka',
            'GUJARAT|AHMEDABAD|SURAT': 'Gujarat',
            'KERALA|KOCHI|THIRUVANANTHAPURAM': 'Kerala',
            'RAJASTHAN|JAIPUR': 'Rajasthan',
            'UTTAR PRADESH|UP|LUCKNOW|KANPUR': 'Uttar Pradesh',
            'HARYANA|GURGAON|GURUGRAM': 'Haryana',
        }
        
        state = ''
        for pattern, state_name in state_patterns.items():
            if re.search(pattern, address_upper):
                state = state_name
                break
        
        # Detect industrial address
        industrial_keywords = [
            'INDUSTRIAL', 'ESTATE', 'COMPLEX', 'SHED', 'PLOT',
            'FACTORY', 'UNIT', 'SECTOR', 'PHASE', 'ZONE', 'GIDC'
        ]
        is_industrial = any(keyword in address_upper for keyword in industrial_keywords)
        
        # Extract landmark (words before comma or industrial keywords)
        landmark = ''
        if ',' in address:
            first_part = address.split(',')[0].strip()
            if len(first_part) < 100:  # Reasonable length for landmark
                landmark = first_part
        
        return {
            'landmark': landmark,
            'pincode': pincode,
            'state': state,
            'is_industrial': is_industrial,
            'original': address
        }


class WhatsAppDetective:
    """
    Find WhatsApp numbers using two-pronged approach:
    1. Google Maps API for local/boutique
    2. GSTIN + GST Enrichment API for industrial
    """
    
    def __init__(self, serpapi_key: str = None, leadzen_key: str = None):
        """
        Initialize WhatsApp Detective.
        
        Args:
            serpapi_key: SerpApi API key (for Google Maps & Search)
            leadzen_key: Leadzen.ai API key (for GST enrichment)
        """
        self.serpapi_key = serpapi_key or os.getenv('SERPAPI_API_KEY')
        self.leadzen_key = leadzen_key or os.getenv('LEADZEN_API_KEY')
        self.parser = AddressParser()
        
        logger.info("🔍 WhatsApp Detective initialized")
        if not self.serpapi_key:
            logger.warning("⚠️  SerpApi key missing - some features disabled")
        if not self.leadzen_key:
            logger.warning("⚠️  Leadzen API key missing - GST enrichment disabled")
    
    def find_whatsapp(self, company_name: str, address: str) -> Dict[str, str]:
        """
        Find WhatsApp number using two-pronged approach.
        
        Args:
            company_name: Company name
            address: Full address
        
        Returns:
            Dict with: phone, whatsapp, email, source_url, method, confidence
        """
        logger.info(f"🔍 WhatsApp Detective investigating: {company_name}")
        
        result = {
            'phone': '',
            'whatsapp': '',
            'email': '',
            'source_url': '',
            'method': '',
            'confidence': 0
        }
        
        # Parse address
        parsed = self.parser.parse(address)
        logger.info(f"   📍 Address type: {'Industrial' if parsed['is_industrial'] else 'Local/Boutique'}")
        if parsed['pincode']:
            logger.info(f"   📮 Pincode: {parsed['pincode']}")
        
        # Choose strategy based on address type
        if parsed['is_industrial']:
            # APPROACH 2: Industrial → Try GSTIN first
            logger.info("   🏭 Trying GSTIN approach...")
            
            # Step 1: Find GSTIN
            gstin = self._find_gstin(company_name, address, parsed)
            if gstin:
                logger.info(f"   ✅ Found GSTIN: {gstin}")
                
                # Step 2: Enrich via GST API
                gst_result = self._enrich_via_gst(gstin)
                if gst_result.get('phone'):
                    result.update(gst_result)
                    result['method'] = 'gst_enrichment'
                    result['confidence'] = 95  # GST data is highly reliable
                    logger.info(f"   ✅ GST Enrichment found: {result['phone']}")
                    return result
            
            # Fallback to Google Maps
            logger.info("   🗺️  Fallback to Google Maps...")
            maps_result = self._search_google_maps(company_name, address, parsed)
            if maps_result.get('phone'):
                result.update(maps_result)
                return result
        else:
            # APPROACH 1: Local/Boutique → Try Google Maps first
            logger.info("   🗺️  Trying Google Maps approach...")
            maps_result = self._search_google_maps(company_name, address, parsed)
            if maps_result.get('phone'):
                result.update(maps_result)
                return result
            
            # Fallback to GSTIN
            logger.info("   🏭 Fallback to GSTIN...")
            gstin = self._find_gstin(company_name, address, parsed)
            if gstin:
                gst_result = self._enrich_via_gst(gstin)
                if gst_result.get('phone'):
                    result.update(gst_result)
                    result['method'] = 'gst_enrichment'
                    result['confidence'] = 95
                    return result
        
        # Last resort: WhatsApp link finder
        logger.info("   🔗 Trying WhatsApp link finder...")
        link_result = self._find_whatsapp_links(company_name, address, parsed)
        if link_result.get('whatsapp'):
            result.update(link_result)
            return result
        
        logger.info(f"   ❌ No WhatsApp found for: {company_name}")
        return result
    
    def _search_google_maps(self, company: str, address: str, parsed: Dict) -> Dict:
        """
        APPROACH 1: Search Google Maps API for local businesses.
        """
        if not self.serpapi_key:
            return {}
        
        try:
            # Build search query with landmark and pincode for accuracy
            query_parts = [company]
            if parsed['landmark']:
                query_parts.append(parsed['landmark'])
            if parsed['pincode']:
                query_parts.append(parsed['pincode'])
            
            query = ' '.join(query_parts)
            
            params = {
                'engine': 'google_maps',
                'q': query,
                'api_key': self.serpapi_key,
                'type': 'search'
            }
            
            response = requests.get('https://serpapi.com/search', params=params, timeout=20)
            if response.status_code != 200:
                return {}
            
            data = response.json()
            
            # Extract from local results
            if 'local_results' in data and data['local_results']:
                place = data['local_results'][0]
                
                phone = place.get('phone', '')
                if phone:
                    normalized = self._normalize_phone(phone)
                    if normalized:
                        return {
                            'phone': normalized,
                            'whatsapp': normalized,  # Assume mobile = WhatsApp
                            'source_url': place.get('link', 'Google Maps'),
                            'method': 'google_maps',
                            'confidence': 85
                        }
            
            return {}
            
        except Exception as e:
            logger.error(f"   Error in Google Maps search: {str(e)}")
            return {}
    
    def _find_gstin(self, company: str, address: str, parsed: Dict) -> str:
        """
        APPROACH 2, Step 1: Find GSTIN (15-digit GST number).
        """
        if not self.serpapi_key:
            return ''
        
        try:
            # Search for company + GSTIN
            query = f'{company} GSTIN India'
            
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
                return ''
            
            data = response.json()
            
            # Look for 15-digit GSTIN in all results
            all_text = str(data)
            gstin_pattern = r'\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b'
            
            matches = re.findall(gstin_pattern, all_text)
            if matches:
                return matches[0]
            
            return ''
            
        except Exception as e:
            logger.error(f"   Error finding GSTIN: {str(e)}")
            return ''
    
    def _enrich_via_gst(self, gstin: str) -> Dict:
        """
        APPROACH 2, Step 2: Convert GSTIN to mobile number via GST Enrichment API.
        
        This uses Leadzen.ai or similar GST enrichment API.
        """
        if not self.leadzen_key:
            logger.info("   ⚠️  Leadzen API not configured - skipping GST enrichment")
            return {}
        
        try:
            # Leadzen.ai API endpoint (example)
            # NOTE: Replace with actual Leadzen API endpoint and format
            url = 'https://api.leadzen.ai/v1/enrich/gstin'
            headers = {
                'Authorization': f'Bearer {self.leadzen_key}',
                'Content-Type': 'application/json'
            }
            payload = {
                'gstin': gstin
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=20)
            if response.status_code != 200:
                return {}
            
            data = response.json()
            
            # Extract mobile number from response
            phone = data.get('registered_mobile_number', '') or data.get('mobile', '')
            email = data.get('email', '')
            
            if phone:
                normalized = self._normalize_phone(phone)
                if normalized:
                    return {
                        'phone': normalized,
                        'whatsapp': normalized,
                        'email': email,
                        'source_url': f'GST Record: {gstin}',
                        'method': 'gst_enrichment',
                        'confidence': 95
                    }
            
            return {}
            
        except Exception as e:
            logger.error(f"   Error in GST enrichment: {str(e)}")
            return {}
    
    def _find_whatsapp_links(self, company: str, address: str, parsed: Dict) -> Dict:
        """
        APPROACH 3: WhatsApp Link Finder (fallback).
        
        Searches for wa.me or api.whatsapp.com links.
        """
        if not self.serpapi_key:
            return {}
        
        try:
            # Search for company + WhatsApp
            query = f'{company} WhatsApp'
            if parsed['pincode']:
                query += f' {parsed["pincode"]}'
            
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
                return {}
            
            data = response.json()
            all_text = str(data)
            
            # Look for wa.me links
            whatsapp_links = re.findall(r'wa\.me/(\d+)', all_text)
            if whatsapp_links:
                phone = whatsapp_links[0]
                if len(phone) >= 10:
                    mobile = phone[-10:]
                    if mobile[0] in '6789':
                        return {
                            'phone': f'+91-{mobile}',
                            'whatsapp': f'+91-{mobile}',
                            'source_url': f'wa.me/{phone}',
                            'method': 'whatsapp_link',
                            'confidence': 80
                        }
            
            # Look for api.whatsapp.com links
            api_links = re.findall(r'api\.whatsapp\.com/send\?phone=(\d+)', all_text)
            if api_links:
                phone = api_links[0]
                if len(phone) >= 10:
                    mobile = phone[-10:]
                    if mobile[0] in '6789':
                        return {
                            'phone': f'+91-{mobile}',
                            'whatsapp': f'+91-{mobile}',
                            'source_url': f'api.whatsapp.com',
                            'method': 'whatsapp_link',
                            'confidence': 80
                        }
            
            # Look for phone numbers in snippets
            if 'organic_results' in data:
                for result in data['organic_results'][:5]:
                    snippet = result.get('snippet', '')
                    title = result.get('title', '')
                    combined = f"{title} {snippet}"
                    
                    # Find 10-digit mobile numbers
                    phones = re.findall(r'\b[6-9]\d{9}\b', combined)
                    if phones:
                        return {
                            'phone': f'+91-{phones[0]}',
                            'whatsapp': f'+91-{phones[0]}',
                            'source_url': result.get('link', ''),
                            'method': 'whatsapp_search',
                            'confidence': 70
                        }
            
            return {}
            
        except Exception as e:
            logger.error(f"   Error in WhatsApp link finder: {str(e)}")
            return {}
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone to +91-XXXXXXXXXX format."""
        digits = re.sub(r'[^\d]', '', phone)
        if len(digits) >= 10:
            mobile = digits[-10:]
            # Prioritize mobile numbers (starts with 6-9)
            if mobile[0] in '6789':
                return f'+91-{mobile}'
        return ''


if __name__ == '__main__':
    # Test WhatsApp Detective
    logging.basicConfig(level=logging.INFO)
    
    detective = WhatsAppDetective()
    
    test_cases = [
        {
            'name': 'Star Exports',
            'address': '50 KAZI SAYED STREET, ABOVE DELHI RAJASTHAN TRANSPORT COMPANY, MUMBAI, 400003',
            'type': 'Local/Boutique'
        },
        {
            'name': 'Hiemens Bottling Machines',
            'address': 'PLOT NO E-14, INDUSTRIAL ESTATE, FARIDABAD, HARYANA, 121003',
            'type': 'Industrial'
        },
    ]
    
    print("\n" + "="*80)
    print("🔍 WHATSAPP DETECTIVE TEST")
    print("="*80 + "\n")
    
    for case in test_cases:
        print(f"\n{'─'*80}")
        print(f"Company: {case['name']}")
        print(f"Address: {case['address']}")
        print(f"Type: {case['type']}")
        print(f"{'─'*80}")
        
        result = detective.find_whatsapp(case['name'], case['address'])
        
        if result.get('phone'):
            print(f"✅ Phone: {result['phone']}")
            print(f"📱 WhatsApp: {result.get('whatsapp', 'N/A')}")
            print(f"📧 Email: {result.get('email', 'N/A')}")
            print(f"🔗 Source: {result.get('source_url', 'N/A')}")
            print(f"🎯 Method: {result.get('method', 'N/A')}")
            print(f"💯 Confidence: {result.get('confidence', 0)}%")
        else:
            print("❌ No contact found")
    
    print("\n" + "="*80 + "\n")

