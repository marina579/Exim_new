"""
Contact Validator - Smart validation for enriched contacts
Prevents matching wrong companies and validates contact accuracy
"""

import re
import logging
from typing import Dict, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Generic email providers that are acceptable for small businesses
ALLOWED_GENERIC_PROVIDERS = [
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 
    'rediffmail.com', 'yahoo.co.in', 'live.com', 'msn.com'
]

# Email providers to always reject (spam, temp, test)
BLOCKED_PROVIDERS = [
    'noreply', 'no-reply', 'example.com', 'test.com', 'sample.com', 
    'domain.com', 'tempmail', 'mailinator', 'guerrillamail'
]


def normalize_company_name(name: str) -> str:
    """
    Normalize company name for comparison.
    Removes common suffixes and standardizes format.
    """
    if not name:
        return ''
    
    # Convert to lowercase
    normalized = name.lower().strip()
    
    # Remove common company suffixes
    suffixes = [
        r'\s+pvt\.?\s*ltd\.?$',
        r'\s+private\s+limited$',
        r'\s+ltd\.?$',
        r'\s+limited$',
        r'\s+llc\.?$',
        r'\s+inc\.?$',
        r'\s+corp\.?$',
        r'\s+corporation$',
        r'\s+company$',
        r'\s+co\.?$',
        r'\s+\(india\)$',
        r'\s+india$',
    ]
    
    for suffix in suffixes:
        normalized = re.sub(suffix, '', normalized, flags=re.IGNORECASE)
    
    # Remove special characters except spaces
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    
    # Remove extra whitespace
    normalized = ' '.join(normalized.split())
    
    return normalized


def calculate_name_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity between two company names (0.0 to 1.0).
    
    Args:
        name1: First company name
        name2: Second company name
    
    Returns:
        Similarity score (0.0 = completely different, 1.0 = identical)
    """
    if not name1 or not name2:
        return 0.0
    
    # Normalize both names
    norm1 = normalize_company_name(name1)
    norm2 = normalize_company_name(name2)
    
    if not norm1 or not norm2:
        return 0.0
    
    # Calculate similarity
    similarity = SequenceMatcher(None, norm1, norm2).ratio()
    
    return similarity


def is_company_name_match(searched_name: str, found_name: str, min_similarity: float = 0.80) -> Tuple[bool, float]:
    """
    Check if found company name matches the searched company name.
    STRICT matching to avoid similar but different companies (e.g., Cronisys vs Kronisys).
    
    Args:
        searched_name: Name we're searching for (e.g., "Cronisys IT LLC")
        found_name: Name found in search results (e.g., "Kronisys Technologies")
        min_similarity: Minimum similarity threshold (default: 0.80 - strict!)
    
    Returns:
        Tuple of (is_match: bool, similarity_score: float)
    """
    if not searched_name or not found_name:
        return False, 0.0
    
    similarity = calculate_name_similarity(searched_name, found_name)
    is_match = similarity >= min_similarity
    
    # Additional check: Core words must match (not just be similar)
    # Extract main words (ignore common suffixes)
    searched_normalized = normalize_company_name(searched_name)
    found_normalized = normalize_company_name(found_name)
    
    searched_words = set(searched_normalized.split())
    found_words = set(found_normalized.split())
    
    # Check if at least one significant word matches exactly
    significant_words = {w for w in searched_words if len(w) >= 4}
    has_exact_word_match = len(significant_words & found_words) > 0
    
    # If no exact word match, reduce confidence significantly
    if not has_exact_word_match and similarity < 0.95:
        logger.warning(f"No exact word match: '{searched_name}' vs '{found_name}' (similarity: {similarity:.2f})")
        is_match = False
        similarity = similarity * 0.5  # Penalize heavily
    
    logger.debug(f"Company name match: '{searched_name}' vs '{found_name}' = {similarity:.2f} (match: {is_match}, exact_word_match: {has_exact_word_match})")
    
    return is_match, similarity


def extract_domain_from_url(url: str) -> str:
    """Extract domain from URL (e.g., 'https://cronisys.com/contact' -> 'cronisys.com')"""
    if not url:
        return ''
    
    # Extract domain using regex
    match = re.search(r'(?:https?://)?(?:www\.)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', url)
    if match:
        domain = match.group(1).lower()
        # Remove www.
        domain = domain.replace('www.', '')
        return domain
    
    return ''


def extract_domain_from_email(email: str) -> str:
    """Extract domain from email (e.g., 'info@cronisys.com' -> 'cronisys.com')"""
    if not email or '@' not in email:
        return ''
    
    domain = email.split('@')[1].lower()
    return domain


def is_generic_email_provider(email: str) -> bool:
    """Check if email uses a generic provider (gmail, yahoo, etc.)"""
    if not email:
        return False
    
    domain = extract_domain_from_email(email)
    return domain in ALLOWED_GENERIC_PROVIDERS


def is_blocked_email(email: str) -> bool:
    """Check if email should be blocked (spam, temp, test emails)"""
    if not email:
        return True
    
    email_lower = email.lower()
    return any(blocked in email_lower for blocked in BLOCKED_PROVIDERS)


def validate_email_domain(email: str, company_website: str = None, company_name: str = None) -> Tuple[bool, str]:
    """
    Validate email - Accept ANY email domain except blocked ones.
    
    Args:
        email: Email to validate
        company_website: Company website URL (optional, not used but kept for compatibility)
        company_name: Company name (optional, not used but kept for compatibility)
    
    Returns:
        Tuple of (is_valid: bool, reason: str)
    """
    if not email:
        return False, "No email provided"
    
    # Check if blocked (spam, temp, test emails only)
    if is_blocked_email(email):
        return False, "Blocked email provider (spam/temp/test)"
    
    # Accept ALL other emails - business, gmail, yahoo, any domain
    return True, "Valid email (all domains accepted)"


def normalize_address_for_matching(address: str) -> str:
    """Normalize address for comparison."""
    if not address:
        return ''
    normalized = address.lower().strip()
    # Remove common words
    common_words = ['road', 'rd', 'street', 'st', 'avenue', 'ave', 'plot', 'no', 'number', 'building', 'floor']
    for word in common_words:
        normalized = re.sub(r'\b' + word + r'\b', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
    normalized = ' '.join(normalized.split())
    return normalized


def extract_location_keywords(address: str) -> list:
    """Extract city/location keywords from address."""
    if not address:
        return []
    address_lower = address.lower()
    words = re.findall(r'\b[a-z]{3,}\b', address_lower)
    # Filter out common non-location words
    common_words = {'road', 'street', 'avenue', 'plot', 'building', 'floor', 'near', 'pvt', 'ltd', 'limited', 
                    'private', 'company', 'india', 'indian', 'industries', 'industrial', 'estate', 'area',
                    'corporation', 'enterprise', 'enterprises', 'group'}
    locations = [w for w in words if w not in common_words and len(w) >= 4]
    return locations


def validate_contact(
    searched_company: str,
    found_company: str = None,
    email: str = None,
    phone: str = None,
    source_url: str = None,
    searched_address: str = None,
    found_address: str = None,
    min_name_similarity: float = 0.80
) -> Tuple[bool, str, float]:
    """
    Validate that found contact belongs to the searched company.
    
    VALIDATION PRIORITY:
    - P1 (Seller + Seller Address): BOTH must match (not address alone!)
    - P2 (Seller only): Company name must match (strict)
    
    P1: If Excel has BOTH Seller AND Seller Address:
        → Check address keywords match
        → Check company name match (STRICT 0.80 threshold)
        → BOTH must pass to accept
    
    P2: If Excel has ONLY Seller (no address):
        → Check company name match (STRICT 0.80 threshold)
    
    Args:
        searched_company: Company name from Excel (Seller column)
        found_company: Company name found in search results
        email: Email found
        phone: Phone found
        source_url: Source URL/website
        searched_address: Company address from Excel (Seller Address column)
        found_address: Address found in search results (optional)
        min_name_similarity: Minimum company name similarity (default: 0.80)
    
    Returns:
        Tuple of (is_valid: bool, reason: str, confidence: float)
    """
    reasons = []
    confidence = 0.0
    
    # Must have at least email or phone
    if not email and not phone:
        return False, "No contact information found", 0.0
    
    # PRIORITY 1: ADDRESS VALIDATION (if provided in Excel)
    address_matched = False
    if searched_address and searched_address.strip():
        # Extract location keywords from searched address
        searched_locations = extract_location_keywords(searched_address)
        
        if searched_locations:
            logger.debug(f"Searching for locations: {searched_locations} from address: {searched_address}")
            
            # Build search text from all available fields
            search_text_parts = []
            if found_address:
                search_text_parts.append(found_address.lower())
            if source_url:
                search_text_parts.append(source_url.lower())
            if found_company:
                search_text_parts.append(found_company.lower())
            
            search_text = ' '.join(search_text_parts)
            
            # Check for location matches
            matching_locations = [loc for loc in searched_locations if loc in search_text]
            
            if matching_locations:
                address_matched = True
                reasons.append(f"✓ Address matched ({', '.join(matching_locations)})")
                logger.info(f"✅ Address matched: {matching_locations}")
                
                # P1: BOTH address AND company name must match (not address alone!)
                # Now check company name with STRICT threshold (same as P2)
                if found_company:
                    is_match, similarity = is_company_name_match(searched_company, found_company, min_similarity)
                    if is_match:
                        # BOTH address AND company name matched → HIGH confidence
                        reasons.append(f"✓ Company name match ({similarity:.2f})")
                        confidence = 0.90  # Both matched = high confidence
                        logger.info(f"✅ P1: Both address AND company name matched")
                    else:
                        # Address matches but company name doesn't → REJECT
                        # This is a different company at the same location
                        return False, f"❌ P1 failed: Address matched but company different: '{searched_company}' ≠ '{found_company}' (similarity: {similarity:.2f})", similarity
                else:
                    # Address matched but no company name to verify → Lower confidence
                    confidence = 0.50
                    reasons.append("⚠ Address matched but no company name verification")
            else:
                # Address provided in Excel but doesn't match results - WRONG LOCATION!
                logger.warning(f"❌ Address mismatch: Excel has '{searched_address}' but not found in results")
                return False, f"❌ Address mismatch: searched '{searched_address}' but not found in results", 0.15
    
    # PRIORITY 2: COMPANY NAME VALIDATION (when address not available or already matched)
    if not address_matched:
        # No address match - rely on company name (STRICT)
        if found_company:
            is_match, similarity = is_company_name_match(searched_company, found_company, min_name_similarity)
            
            if not is_match:
                return False, f"❌ Company mismatch: '{searched_company}' ≠ '{found_company}' (similarity: {similarity:.2f})", similarity
            
            reasons.append(f"✓ Company match ({similarity:.2f})")
            confidence = similarity
        else:
            # No company name AND no address verification - VERY RISKY
            confidence = 0.35
            reasons.append("⚠ No company/address verification")
    
    # Validate email if provided (now accepts all emails except spam/temp)
    if email:
        email_valid, email_reason = validate_email_domain(email, source_url, searched_company)
        
        if email_valid:
            reasons.append(f"✓ {email_reason}")
            confidence = min(1.0, confidence + 0.15)
        else:
            # Blocked email (spam/temp)
            return False, f"❌ {email_reason}", confidence * 0.3
    
    # Validate phone format (Indian only)
    if phone:
        # Check if it's Indian format
        if phone.startswith('+91-') or phone.startswith('91-'):
            reasons.append("✓ Indian phone number")
            confidence = min(1.0, confidence + 0.15)
        else:
            # Non-Indian phone - REJECT (user wants Indian companies only)
            return False, f"❌ Not Indian company: {phone}", confidence * 0.2
    
    # Check source URL if provided
    if source_url:
        website_domain = extract_domain_from_url(source_url)
        if website_domain:
            # Check if company name appears in domain
            company_normalized = normalize_company_name(searched_company)
            company_words = [w for w in company_normalized.split() if len(w) >= 4]
            
            domain_matches = any(word in website_domain for word in company_words)
            if domain_matches:
                reasons.append("✓ Company name in domain")
                confidence = min(1.0, confidence + 0.1)
    
    # Final validation - STRICTER threshold
    if confidence >= 0.65:
        return True, " | ".join(reasons), confidence
    else:
        return False, f"❌ Low confidence ({confidence:.2f}): " + " | ".join(reasons), confidence


def filter_contacts_by_address_only(contacts: list, searched_address: str) -> list:
    """
    P3 Fallback: Filter contacts by address only (ignore company name).
    Used as last resort when both P1 and P2 fail.
    
    Args:
        contacts: List of contact dictionaries
        searched_address: Company address from Excel (Seller Address column)
    
    Returns:
        Filtered list of contacts from the same location
    """
    if not searched_address or not searched_address.strip():
        return []
    
    valid_contacts = []
    
    # Extract location keywords from searched address
    searched_locations = extract_location_keywords(searched_address)
    
    if not searched_locations:
        logger.warning(f"⚠️  P3: Could not extract location keywords from '{searched_address}'")
        return []
    
    logger.info(f"📋 P3: Filtering contacts by address only: {searched_locations}")
    
    for idx, contact in enumerate(contacts):
        # Extract contact info
        email = contact.get('email', '')
        phone = contact.get('phone', '')
        source_url = contact.get('source_url', '')
        found_company = contact.get('company_name', '') or contact.get('title', '')
        found_address = contact.get('address', '') or contact.get('location', '')
        
        # Must have at least email or phone
        if not email and not phone:
            continue
        
        # Build search text from all available fields
        search_text_parts = []
        if found_address:
            search_text_parts.append(found_address.lower())
        if source_url:
            search_text_parts.append(source_url.lower())
        if found_company:
            search_text_parts.append(found_company.lower())
        
        search_text = ' '.join(search_text_parts)
        
        # Check for location matches
        matching_locations = [loc for loc in searched_locations if loc in search_text]
        
        if matching_locations:
            # Validate phone format (Indian only)
            if phone:
                if not (phone.startswith('+91-') or phone.startswith('91-')):
                    logger.debug(f"P3: Skipping non-Indian phone: {phone}")
                    continue
            
            # Validate email (reject spam/temp only)
            if email:
                if is_blocked_email(email):
                    logger.debug(f"P3: Skipping blocked email: {email}")
                    continue
            
            # Accept contact based on address match
            contact['validation_status'] = 'address_only'
            contact['validation_reason'] = f"P3: Address matched ({', '.join(matching_locations)})"
            contact['confidence_score'] = 0.60  # Lower confidence (no company verification)
            valid_contacts.append(contact)
            logger.info(f"✅ P3 Contact #{idx+1}: Address matched ({', '.join(matching_locations)}), company: {found_company or 'unknown'}")
        else:
            logger.debug(f"P3: Address mismatch for contact #{idx+1}")
    
    return valid_contacts


def filter_contacts_by_company(searched_company: str, contacts: list, searched_address: str = None, min_similarity: float = 0.80) -> list:
    """
    Filter list of contacts to only include those matching the searched company.
    
    P1 (Seller + Seller Address): BOTH must match
    P2 (Seller only): Company name must match
    
    Args:
        searched_company: Company name from Excel (Seller column)
        contacts: List of contact dictionaries
        searched_address: Company address from Excel (Seller Address column) - If provided, P1 applies
        min_similarity: Minimum name similarity threshold (default: 0.80)
    
    Returns:
        Filtered list of valid contacts
    """
    valid_contacts = []
    
    logger.info(f"📋 Validating contacts for: {searched_company}")
    if searched_address:
        logger.info(f"   Address: {searched_address}")
    
    for idx, contact in enumerate(contacts):
        # Extract contact info
        email = contact.get('email', '')
        phone = contact.get('phone', '')
        source_url = contact.get('source_url', '')
        method = contact.get('method', 'unknown')
        
        # Try to extract company name from source title if available
        found_company = contact.get('company_name', '') or contact.get('title', '')
        
        # Extract found address if available
        found_address = contact.get('address', '') or contact.get('location', '')
        
        # Validate contact (with address as Priority 1, company name as Priority 2)
        is_valid, reason, confidence = validate_contact(
            searched_company=searched_company,
            found_company=found_company,
            email=email,
            phone=phone,
            source_url=source_url,
            searched_address=searched_address,
            found_address=found_address,
            min_name_similarity=min_similarity
        )
        
        if is_valid:
            # Add validation metadata
            contact['validation_status'] = 'valid'
            contact['validation_reason'] = reason
            contact['confidence_score'] = confidence
            valid_contacts.append(contact)
            logger.info(f"✅ Contact #{idx+1} validated: {reason} (confidence: {confidence:.2f})")
        else:
            logger.warning(f"❌ Contact #{idx+1} rejected: {reason}")
    
    logger.info(f"✅ Validation complete: {len(valid_contacts)}/{len(contacts)} contacts accepted")
    return valid_contacts


# Test function
if __name__ == '__main__':
    # Test cases
    print("Testing Contact Validator\n")
    
    # Test 1: Company name matching
    print("Test 1: Company Name Matching")
    print("-" * 50)
    
    test_cases = [
        ("Cronisys IT LLC", "Cronisys IT LLC", True),  # Exact match
        ("Cronisys IT LLC", "Cronisys IT", True),  # Same name, different suffix
        ("Cronisys IT LLC", "Kronisys Technologies", False),  # CRITICAL: Different company!
        ("ABC Industries Pvt Ltd", "ABC Industries", True),  # Same company
        ("XYZ Corp", "ABC Corp", False),  # Different companies
        ("Tech Solutions India", "Tech Solutions Pvt Ltd", True),  # Same company
        ("Tech Solutions India", "Tech Services India", False),  # Different companies
    ]
    
    for search, found, expected in test_cases:
        is_match, similarity = is_company_name_match(search, found)
        status = "✅" if is_match == expected else "❌"
        print(f"{status} '{search}' vs '{found}': {similarity:.2f} (match: {is_match})")
    
    # Test 2: Email validation
    print("\nTest 2: Email Domain Validation")
    print("-" * 50)
    
    email_tests = [
        ("info@cronisys.com", "https://cronisys.com", "Cronisys IT LLC", True),  # Business email
        ("info@kronisystechnologies.com", "https://cronisys.com", "Cronisys IT LLC", True),  # Accept all business emails
        ("contact@gmail.com", "", "ABC Corp", True),  # Gmail allowed
        ("sales@yahoo.com", "", "XYZ Ltd", True),  # Yahoo allowed
        ("info@anydomain.com", "", "Test Co", True),  # ANY domain allowed
        ("noreply@test.com", "", "Test Co", False),  # Only blocked emails rejected
    ]
    
    for email, website, company, expected in email_tests:
        is_valid, reason = validate_email_domain(email, website, company)
        status = "✅" if is_valid == expected else "❌"
        print(f"{status} {email}: {reason}")
    
    print("\n✅ Validator tests complete!")

