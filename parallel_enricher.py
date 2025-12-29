"""
Parallel Enrichment Engine
Runs multiple enrichers in parallel for faster processing
"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Callable, Tuple
import time

logger = logging.getLogger(__name__)


class ParallelEnricher:
    """Runs enrichment methods in parallel for faster processing."""
    
    def __init__(self, max_workers: int = 4):
        """
        Initialize parallel enricher.
        
        Args:
            max_workers: Maximum number of parallel threads (default: 4)
        """
        self.max_workers = max_workers
        logger.info(f"✅ Parallel enricher initialized (max workers: {max_workers})")
    
    def run_enrichers_parallel(self, enricher_functions: List[Tuple[str, Callable]]) -> List[Dict]:
        """
        Run multiple enricher functions in parallel.
        
        Args:
            enricher_functions: List of (name, function) tuples
        
        Returns:
            List of results from all enrichers
        """
        if not enricher_functions:
            return []
        
        results = []
        start_time = time.time()
        
        logger.info(f"🚀 Starting {len(enricher_functions)} enrichers in parallel...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_name = {
                executor.submit(func): name 
                for name, func in enricher_functions
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    result = future.result(timeout=30)  # 30 second timeout per enricher
                    if result:
                        results.append({'name': name, 'data': result})
                        logger.info(f"✅ {name} completed ({len(results)}/{len(enricher_functions)})")
                    else:
                        logger.info(f"⚠️  {name} returned no results")
                except Exception as e:
                    logger.error(f"❌ {name} failed: {str(e)[:50]}")
        
        elapsed = time.time() - start_time
        logger.info(f"⚡ Parallel enrichment completed in {elapsed:.2f}s (would take ~{len(enricher_functions) * 5:.1f}s sequential)")
        
        return results
    
    def merge_enricher_results(self, results: List[Dict], seen_phones: set, seen_emails: set) -> List[Dict]:
        """
        Merge results from parallel enrichers, removing duplicates.
        
        Args:
            results: List of enricher results
            seen_phones: Set of already seen phone numbers
            seen_emails: Set of already seen emails
        
        Returns:
            List of unique contacts
        """
        unique_contacts = []
        
        for result_obj in results:
            enricher_name = result_obj.get('name', 'unknown')
            data = result_obj.get('data', {})
            
            if not data or not isinstance(data, dict):
                continue
            
            phone = data.get('phone', '').strip()
            email = data.get('email', '').strip()
            
            # Skip if no contact info
            if not phone and not email:
                continue
            
            # Check if new
            is_new = False
            if phone and phone not in seen_phones:
                seen_phones.add(phone)
                is_new = True
            if email and email not in seen_emails:
                seen_emails.add(email)
                is_new = True
            
            if is_new:
                contact = {
                    'phone': phone,
                    'email': email,
                    'whatsapp': data.get('whatsapp', phone),
                    'contact_name': data.get('contact_name', ''),
                    'source_url': data.get('source_url', ''),
                    'method': enricher_name.lower().replace(' ', '_')
                }
                unique_contacts.append(contact)
                logger.debug(f"Added contact from {enricher_name}")
        
        return unique_contacts


# Singleton instance
_parallel_enricher = None


def get_parallel_enricher(max_workers: int = 4) -> ParallelEnricher:
    """Get singleton parallel enricher instance."""
    global _parallel_enricher
    
    if _parallel_enricher is None:
        _parallel_enricher = ParallelEnricher(max_workers=max_workers)
    
    return _parallel_enricher

