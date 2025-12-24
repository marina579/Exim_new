"""
Google Places API enricher.
Most reliable method for finding phone numbers from addresses.
"""

import os
import logging
import requests
from typing import Dict
from urllib.parse import quote

logger = logging.getLogger(__name__)


class GooglePlacesEnricher:
    """Uses Google Places API to find phone numbers from addresses."""
    
    def __init__(self, api_key: str = None):
        """
        Initialize Google Places enricher.
        
        Args:
            api_key: Google Maps API key
        """
        self.api_key = api_key or os.getenv('GOOGLE_MAPS_API_KEY')
        if not self.api_key:
            raise ValueError("Google Maps API key required. Get one from: https://console.cloud.google.com/")
        
        logger.info("✅ Google Places enricher initialized")
    
    def find_contact(self, company_name: str, address: str = "") -> Dict[str, str]:
        """
        Use Google Places to find phone number for a business.
        
        Args:
            company_name: Name of the company
            address: Address of the company
        
        Returns:
            Dictionary with 'phone', 'email', 'website' keys
        """
        result = {
            'phone': '',
            'email': '',
            'website': ''
        }
        
        try:
            # Build search query
            if address:
                query = f"{company_name} {address}"
            else:
                query = company_name
            
            # Step 1: Find Place using Text Search
            place_id = self._find_place(query)
            
            if not place_id:
                logger.info(f"No place found for: {company_name}")
                return result
            
            logger.info(f"Found place_id: {place_id}")
            
            # Step 2: Get Place Details
            details = self._get_place_details(place_id)
            
            if details:
                result['phone'] = details.get('formatted_phone_number', '')
                result['website'] = details.get('website', '')
                
                # Try to extract email from website if available
                if result['website']:
                    # Note: Google Places doesn't provide email directly
                    # Would need to scrape the website for email
                    pass
                
                if result['phone']:
                    logger.info(f"✅ Found phone via Google Places: {result['phone']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error with Google Places for {company_name}: {str(e)}")
            return result
    
    def _find_place(self, query: str) -> str:
        """
        Find place_id using Text Search.
        
        Args:
            query: Search query (company + address)
        
        Returns:
            place_id or empty string
        """
        url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
        
        params = {
            'input': query,
            'inputtype': 'textquery',
            'fields': 'place_id',
            'key': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') == 'OK' and data.get('candidates'):
                return data['candidates'][0]['place_id']
            
            logger.warning(f"Place search status: {data.get('status')}")
            return ''
            
        except Exception as e:
            logger.error(f"Error finding place: {str(e)}")
            return ''
    
    def _get_place_details(self, place_id: str) -> Dict:
        """
        Get place details including phone number.
        
        Args:
            place_id: Google Place ID
        
        Returns:
            Dictionary with place details
        """
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        
        params = {
            'place_id': place_id,
            'fields': 'name,formatted_phone_number,international_phone_number,website,formatted_address',
            'key': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') == 'OK' and data.get('result'):
                return data['result']
            
            logger.warning(f"Place details status: {data.get('status')}")
            return {}
            
        except Exception as e:
            logger.error(f"Error getting place details: {str(e)}")
            return {}

