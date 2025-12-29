"""
Smart Optimization Engine
Additional optimizations for cost saving and better results
"""

import logging
import time
from typing import Dict, List, Optional, Tuple
from functools import lru_cache
import hashlib

logger = logging.getLogger(__name__)

# ===== OPTIMIZATION 1: Smart SerpAPI Query Builder =====
def build_optimized_serpapi_query(company_name: str, address: str = "") -> str:
    """
    Build optimized SerpAPI query for better first-time results.
    Better query = better results = fewer fallbacks = cost savings!
    
    Args:
        company_name: Company name
        address: Company address
    
    Returns:
        Optimized search query
    """
    # Clean company name (remove extra suffixes that confuse search)
    clean_name = company_name
    for suffix in [' pvt ltd', ' private limited', ' pvt. ltd.', ' ltd.', ' llc', ' inc.']:
        clean_name = clean_name.lower().replace(suffix, '')
    
    # Build query with high-value keywords
    if address:
        # Extract city/state from address
        address_lower = address.lower()
        cities = ['mumbai', 'delhi', 'bangalore', 'bengaluru', 'chennai', 'hyderabad', 
                 'pune', 'kolkata', 'ahmedabad', 'surat', 'jaipur']
        city = next((c for c in cities if c in address_lower), None)
        
        if city:
            # City-specific query (better accuracy)
            query = f'"{clean_name}" {city} india contact phone email'
        else:
            query = f'"{clean_name}" {address} india contact phone'
    else:
        # No address - broad search with contact keywords
        query = f'"{clean_name}" india contact phone email address'
    
    logger.debug(f"Optimized query: {query}")
    return query


# ===== OPTIMIZATION 2: Progressive Enrichment (Free → Paid) =====
class ProgressiveEnricher:
    """
    Try free methods first, only use paid APIs if needed.
    Cost savings: ~40-50% on API costs
    """
    
    def __init__(self):
        self.free_methods_tried = set()
        self.paid_methods_tried = set()
    
    def should_try_paid_methods(self, free_results: List[Dict]) -> bool:
        """
        Decide if we need paid APIs based on free results quality.
        
        Args:
            free_results: Results from free methods
        
        Returns:
            True if should try paid methods
        """
        if not free_results:
            return True  # No free results, need paid
        
        # Check quality of free results
        has_phone = any(r.get('phone') for r in free_results)
        has_email = any(r.get('email') for r in free_results)
        
        if has_phone and has_email:
            logger.info("✅ Free methods found both phone and email - skipping paid APIs")
            return False  # Good enough, skip paid
        
        logger.info("⚠️  Free methods incomplete - trying paid APIs")
        return True  # Need more data


# ===== OPTIMIZATION 3: Result Confidence Scoring =====
def calculate_result_confidence(contact: Dict, company_name: str, address: str = None) -> float:
    """
    Calculate confidence score for a contact (0.0 to 1.0).
    Higher score = better quality result.
    
    Args:
        contact: Contact dictionary
        company_name: Searched company name
        address: Searched address
    
    Returns:
        Confidence score (0.0 to 1.0)
    """
    score = 0.0
    
    # Has phone number? +0.3
    if contact.get('phone'):
        score += 0.3
    
    # Has email? +0.3
    if contact.get('email'):
        score += 0.3
    
    # Has contact name? +0.1
    if contact.get('contact_name'):
        score += 0.1
    
    # Has source URL? +0.1
    if contact.get('source_url') and contact['source_url'] not in ['', 'Google Maps', 'unknown']:
        score += 0.1
    
    # Company name in source? +0.1
    if contact.get('company_name'):
        company_lower = company_name.lower()
        found_lower = contact['company_name'].lower()
        if any(word in found_lower for word in company_lower.split() if len(word) >= 4):
            score += 0.1
    
    # Address match? +0.1
    if address and contact.get('source_url'):
        address_lower = address.lower()
        source_lower = contact['source_url'].lower()
        if any(word in source_lower for word in address_lower.split() if len(word) >= 4):
            score += 0.1
    
    return min(1.0, score)


def rank_contacts_by_confidence(contacts: List[Dict], company_name: str, address: str = None) -> List[Dict]:
    """
    Rank contacts by confidence score (best first).
    
    Returns:
        Sorted list of contacts with confidence scores
    """
    for contact in contacts:
        contact['confidence_score'] = calculate_result_confidence(contact, company_name, address)
    
    # Sort by confidence (highest first)
    sorted_contacts = sorted(contacts, key=lambda x: x.get('confidence_score', 0.0), reverse=True)
    
    logger.info(f"📊 Ranked {len(contacts)} contacts by confidence")
    return sorted_contacts


# ===== OPTIMIZATION 4: Session-level Deduplication =====
_session_cache = {}

def get_session_cache_key(company_name: str, address: str = "") -> str:
    """Generate unique cache key for company."""
    key_string = f"{company_name.lower().strip()}|{address.lower().strip()}"
    return hashlib.md5(key_string.encode()).hexdigest()


def check_session_cache(company_name: str, address: str = "") -> Optional[List[Dict]]:
    """
    Check if we already processed this company in current session.
    Avoids duplicate processing in same batch.
    
    Returns:
        Cached contacts or None
    """
    cache_key = get_session_cache_key(company_name, address)
    
    if cache_key in _session_cache:
        cached_data = _session_cache[cache_key]
        age = time.time() - cached_data['timestamp']
        
        # Cache valid for 1 hour
        if age < 3600:
            logger.info(f"♻️  Session cache hit for: {company_name} (age: {int(age)}s)")
            return cached_data['contacts']
    
    return None


def save_to_session_cache(company_name: str, address: str, contacts: List[Dict]):
    """Save enrichment result to session cache."""
    cache_key = get_session_cache_key(company_name, address)
    _session_cache[cache_key] = {
        'contacts': contacts,
        'timestamp': time.time()
    }
    logger.debug(f"💾 Saved to session cache: {company_name}")


def clear_session_cache():
    """Clear session cache (call periodically to free memory)."""
    _session_cache.clear()
    logger.info("🗑️  Session cache cleared")


# ===== OPTIMIZATION 5: API Cost Tracking =====
class CostTracker:
    """Track actual API costs per company."""
    
    def __init__(self):
        self.costs = {
            'serpapi': 0,
            'openai': 0,
            'gemini': 0,
            'google_geo': 0,
            'total_companies': 0
        }
        self.api_costs = {
            'serpapi': 0.002,  # $0.002 per search
            'openai': 0.0015,  # ~$0.0015 per call (GPT-4o-mini)
            'gemini': 0.0,  # Free tier
            'google_geo': 0.005,  # $0.005 per geocode
        }
    
    def log_api_call(self, api_name: str):
        """Log an API call."""
        if api_name in self.costs:
            self.costs[api_name] += 1
    
    def get_cost_for_company(self) -> float:
        """Get estimated cost for current company."""
        cost = 0.0
        for api, count in self.costs.items():
            if api in self.api_costs:
                cost += count * self.api_costs[api]
        return cost
    
    def get_total_cost(self) -> Dict:
        """Get total cost breakdown."""
        breakdown = {}
        total = 0.0
        
        for api, count in self.costs.items():
            if api == 'total_companies':
                continue
            if api in self.api_costs:
                api_cost = count * self.api_costs[api]
                breakdown[api] = {'calls': count, 'cost': api_cost}
                total += api_cost
        
        breakdown['total'] = total
        breakdown['companies'] = self.costs['total_companies']
        breakdown['cost_per_company'] = total / max(1, self.costs['total_companies'])
        
        return breakdown
    
    def log_summary(self):
        """Log cost summary."""
        summary = self.get_total_cost()
        logger.info(f"💰 Cost Summary:")
        logger.info(f"   Companies processed: {summary['companies']}")
        logger.info(f"   Total cost: ${summary['total']:.4f}")
        logger.info(f"   Cost per company: ${summary['cost_per_company']:.4f}")
        
        for api, data in summary.items():
            if api not in ['total', 'companies', 'cost_per_company']:
                logger.info(f"   {api}: {data['calls']} calls = ${data['cost']:.4f}")


# ===== OPTIMIZATION 6: Smart API Failover =====
def handle_api_error(api_name: str, error: Exception, retry_count: int = 0) -> Tuple[bool, int]:
    """
    Handle API errors with smart retry logic.
    
    Returns:
        (should_retry, wait_seconds)
    """
    error_str = str(error).lower()
    
    # Rate limit errors - exponential backoff
    if 'rate limit' in error_str or '429' in error_str:
        wait_time = min(300, (2 ** retry_count) * 5)  # Max 5 minutes
        logger.warning(f"⏰ {api_name} rate limited - waiting {wait_time}s (retry {retry_count + 1})")
        return True, wait_time
    
    # Quota exceeded - don't retry
    if 'quota' in error_str or 'exceeded' in error_str:
        logger.error(f"❌ {api_name} quota exceeded - skipping")
        return False, 0
    
    # Network errors - retry up to 3 times
    if 'timeout' in error_str or 'connection' in error_str:
        if retry_count < 3:
            wait_time = 5
            logger.warning(f"🔄 {api_name} network error - retrying in {wait_time}s")
            return True, wait_time
    
    # Unknown error - don't retry
    logger.error(f"❌ {api_name} error: {error}")
    return False, 0


# Global cost tracker
_cost_tracker = CostTracker()

def get_cost_tracker() -> CostTracker:
    """Get global cost tracker instance."""
    return _cost_tracker

