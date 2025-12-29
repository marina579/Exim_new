"""
Google Geocoding API Integration for Address Validation
Uses Google Geo API to verify and normalize addresses for better matching
"""

import os
import logging
import requests
from typing import Dict, Tuple, Optional
import time

logger = logging.getLogger(__name__)

# Cache to avoid duplicate geocoding calls
_geocoding_cache = {}


class GeoValidator:
    """Uses Google Geocoding API to validate and normalize addresses."""
    
    def __init__(self, api_key: str = None):
        """
        Initialize Geo Validator.
        
        Args:
            api_key: Google Maps API key (with Geocoding API enabled)
        """
        self.api_key = api_key or os.getenv('GOOGLE_MAPS_API_KEY') or os.getenv('GOOGLE_GEO_API_KEY')
        self.base_url = "https://maps.googleapis.com/maps/api/geocode/json"
        
        if self.api_key:
            logger.info("✅ Google Geo API initialized")
        else:
            logger.warning("⚠️  Google Geo API key not found (GOOGLE_MAPS_API_KEY or GOOGLE_GEO_API_KEY)")
    
    def geocode_address(self, address: str, use_cache: bool = True) -> Optional[Dict]:
        """
        Geocode an address using Google Geocoding API.
        
        Args:
            address: Address string to geocode
            use_cache: Use cached results if available
        
        Returns:
            Dictionary with normalized address components or None
        """
        if not self.api_key or not address:
            return None
        
        # Check cache first
        if use_cache and address in _geocoding_cache:
            logger.debug(f"♻️  Using cached geocoding for: {address}")
            return _geocoding_cache[address]
        
        try:
            params = {
                'address': address,
                'key': self.api_key,
                'region': 'in'  # Bias results to India
            }
            
            response = requests.get(self.base_url, params=params, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') == 'OK' and data.get('results'):
                result = data['results'][0]
                
                # Extract components
                components = {}
                for comp in result.get('address_components', []):
                    types = comp.get('types', [])
                    long_name = comp.get('long_name', '')
                    
                    if 'locality' in types or 'administrative_area_level_2' in types:
                        components['city'] = long_name.lower()
                    elif 'administrative_area_level_1' in types:
                        components['state'] = long_name.lower()
                    elif 'country' in types:
                        components['country'] = long_name.lower()
                        components['country_code'] = comp.get('short_name', '').lower()
                
                # Extract formatted address
                components['formatted_address'] = result.get('formatted_address', '').lower()
                
                # Cache the result
                _geocoding_cache[address] = components
                
                logger.debug(f"✅ Geocoded: {address} → {components.get('city', 'unknown')}, {components.get('state', 'unknown')}")
                return components
            else:
                logger.warning(f"⚠️  Geocoding failed for: {address} (status: {data.get('status')})")
                return None
                
        except Exception as e:
            logger.error(f"❌ Geocoding error for '{address}': {str(e)}")
            return None
    
    def validate_address_match(self, searched_address: str, found_address: str) -> Tuple[bool, float]:
        """
        Validate if two addresses match using geocoding.
        
        Args:
            searched_address: Address from Excel
            found_address: Address from search results
        
        Returns:
            Tuple of (is_match: bool, confidence: float)
        """
        if not self.api_key:
            return False, 0.0
        
        # Geocode both addresses
        searched_geo = self.geocode_address(searched_address)
        found_geo = self.geocode_address(found_address)
        
        if not searched_geo or not found_geo:
            return False, 0.0
        
        # Check country match (must be India)
        searched_country = searched_geo.get('country_code', '')
        found_country = found_geo.get('country_code', '')
        
        if searched_country != 'in' or found_country != 'in':
            logger.warning(f"⚠️  Non-Indian address detected: {searched_country} vs {found_country}")
            return False, 0.1
        
        # Check city match
        searched_city = searched_geo.get('city', '')
        found_city = found_geo.get('city', '')
        
        if searched_city and found_city:
            if searched_city == found_city:
                return True, 0.95  # High confidence - same city
            else:
                # Check if one is contained in the other (e.g., "Bangalore" vs "Bengaluru")
                if searched_city in found_city or found_city in searched_city:
                    return True, 0.85  # Good confidence - similar city names
        
        # Check state match as fallback
        searched_state = searched_geo.get('state', '')
        found_state = found_geo.get('state', '')
        
        if searched_state and found_state:
            if searched_state == found_state:
                return True, 0.70  # Moderate confidence - same state
        
        return False, 0.3
    
    def is_indian_address(self, address: str) -> bool:
        """
        Check if address is in India using geocoding.
        
        Args:
            address: Address string
        
        Returns:
            True if address is in India
        """
        if not self.api_key:
            return True  # Assume Indian if can't verify
        
        geo_data = self.geocode_address(address)
        
        if geo_data:
            country_code = geo_data.get('country_code', '')
            return country_code == 'in'
        
        return True  # Assume Indian if geocoding fails


# Singleton instance
_geo_validator = None


def get_geo_validator() -> Optional[GeoValidator]:
    """Get singleton GeoValidator instance."""
    global _geo_validator
    
    if _geo_validator is None:
        api_key = os.getenv('GOOGLE_MAPS_API_KEY') or os.getenv('GOOGLE_GEO_API_KEY')
        if api_key:
            _geo_validator = GeoValidator(api_key=api_key)
        else:
            logger.debug("Google Geo API not available (no API key)")
            return None
    
    return _geo_validator

