"""
SerpApi-based contact enrichment.
Uses SerpApi to search Google and extract contact info from search results.
More reliable than direct web scraping, handles rate limiting automatically.
"""

import os
import re
import logging
from typing import Dict, Optional
import requests
from contact_validator import (
    validate_contact, 
    filter_contacts_by_company,
    extract_domain_from_url,
    is_blocked_email
)
from smart_optimizer import build_optimized_serpapi_query

logger = logging.getLogger(__name__)


class SerpApiEnricher:
    """Uses SerpApi to find contact information via Google search."""
    
    def __init__(self, api_key: str = None):
        """
        Initialize SerpApi enricher.
        
        Args:
            api_key: SerpApi API key. If not provided, reads from SERPAPI_API_KEY env variable.
        """
        self.api_key = api_key or os.getenv('SERPAPI_API_KEY')
        if not self.api_key:
            raise ValueError("SerpApi API key required. Get one from: https://serpapi.com/")
        
        self.base_url = "https://serpapi.com/search"
        logger.info("✅ SerpApi enricher initialized")
    
    def find_contact(self, company_name: str, address: str = "") -> Dict[str, str]:
        """
        Use SerpApi to find phone number and email for a company (single contact).
        
        Args:
            company_name: Name of the company
            address: Address of the company (helps narrow down results)
        
        Returns:
            Dictionary with 'phone', 'email', 'source_url' keys
        """
        # Get all contacts and return first one
        contacts = self.find_all_contacts(company_name, address)
        if contacts:
            return contacts[0]
        
        return {
            'phone': '',
            'email': '',
            'whatsapp': '',
            'source_url': ''
        }
    
    def find_all_contacts(self, company_name: str, address: str = "") -> list:
        """
        Use SerpApi to find ALL contacts for a company from a SINGLE API call.
        Extracts multiple phone numbers, emails, and names from search results.
        
        Args:
            company_name: Name of the company
            address: Address of the company (helps narrow down results)
        
        Returns:
            List of contact dictionaries, each with 'phone', 'email', 'whatsapp', 'contact_name', 'source_url'
        """
        all_contacts = []
        seen_phones = set()
        seen_emails = set()
        
        try:
            # Build OPTIMIZED search query (better results!)
            query = build_optimized_serpapi_query(company_name, address)
            
            # Call SerpApi ONCE
            params = {
                'q': query,
                'api_key': self.api_key,
                'engine': 'google',
                'gl': 'in',  # India
                'hl': 'en',
                'num': 10  # Get top 10 results
            }
            
            logger.info(f"🔍 Making 1 SerpApi call to extract ALL contacts for: {company_name}")
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            # Extract ALL contact info from search results (not just first!)
            
            # 1. Check knowledge graph first (most reliable - usually main contact)
            if 'knowledge_graph' in data:
                kg = data['knowledge_graph']
                phone = self._normalize_phone(kg.get('phone', ''))
                email = self._extract_email(kg.get('description', ''))
                source = kg.get('website', '')
                kg_title = kg.get('title', '')  # Company name from knowledge graph
                
                if phone and phone not in seen_phones:
                    all_contacts.append({
                        'phone': phone,
                        'email': email,
                        'whatsapp': phone,
                        'contact_name': '',
                        'company_name': kg_title,  # Store for validation
                        'source_url': source,
                        'method': 'serpapi_knowledge_graph'
                    })
                    seen_phones.add(phone)
                    if email:
                        seen_emails.add(email)
                    logger.info(f"✅ Found contact in knowledge graph: {phone} ({kg_title})")
            
            # 2. Check local results (Google Maps listings - ALL locations/contacts)
            if 'local_results' in data and isinstance(data.get('local_results'), list):
                for idx, local in enumerate(data['local_results']):  # Process ALL local results (no limit)
                    phone = self._normalize_phone(local.get('phone', ''))
                    title = local.get('title', '')  # This is the business name from Google
                    link = local.get('link', '')
                    
                    # Try to extract email from description
                    description = local.get('description', '') + ' ' + local.get('snippet', '')
                    email = self._extract_email(description)
                    
                    if phone and phone not in seen_phones:
                        all_contacts.append({
                            'phone': phone,
                            'email': email,
                            'whatsapp': phone,
                            'contact_name': '',
                            'company_name': title,  # Store company name for validation
                            'source_url': link or 'Google Maps',
                            'method': 'serpapi_local_results'
                        })
                        seen_phones.add(phone)
                        if email:
                            seen_emails.add(email)
                        logger.info(f"✅ Found contact #{len(all_contacts)} in local results: {phone} ({title})")
            
            # 3. Check organic results (extract ALL contacts, not just first!)
            if 'organic_results' in data:
                for idx, result_item in enumerate(data['organic_results']):  # Process ALL organic results (no limit)
                    snippet = result_item.get('snippet', '')
                    title = result_item.get('title', '')
                    link = result_item.get('link', '')
                    
                    combined_text = f"{title} {snippet}"
                    
                    # Extract ALL phone numbers from this result (not just first!)
                    phones = self._extract_all_indian_phones(combined_text)
                    for phone in phones:
                        if phone and phone not in seen_phones:
                            # Try to find email nearby this phone
                            email = self._extract_email(combined_text)
                            
                            # Try to extract contact name (look for name patterns)
                            contact_name = self._extract_contact_name(combined_text)
                            
                            all_contacts.append({
                                'phone': phone,
                                'email': email if email not in seen_emails else '',
                                'whatsapp': self._extract_whatsapp(combined_text) or phone,
                                'contact_name': contact_name,
                                'company_name': title,  # Store title for validation
                                'source_url': link,
                                'method': 'serpapi_organic_results'
                            })
                            seen_phones.add(phone)
                            if email:
                                seen_emails.add(email)
                            logger.info(f"✅ Found contact #{len(all_contacts)} in organic result #{idx+1}: {phone} ({title})")
                    
                    # Also extract standalone emails (without phone)
                    emails = self._extract_all_emails(combined_text)
                    for email in emails:
                        if email and email not in seen_emails:
                            # Create contact with email only
                            all_contacts.append({
                                'phone': '',
                                'email': email,
                                'whatsapp': '',
                                'contact_name': self._extract_contact_name(combined_text),
                                'company_name': title,  # Store title for validation
                                'source_url': link,
                                'method': 'serpapi_organic_results'
                            })
                            seen_emails.add(email)
                            logger.info(f"✅ Found email-only contact #{len(all_contacts)}: {email} ({title})")
            
            logger.info(f"📊 Extracted {len(all_contacts)} unique contacts from 1 API call for: {company_name}")
            
            # VALIDATE CONTACTS - Filter out wrong companies with similar names (STRICT)
            # Pass address to handle branches (same company, different locations)
            logger.info(f"🔍 Validating contacts for company: {company_name}")
            validated_contacts = filter_contacts_by_company(
                searched_company=company_name,
                contacts=all_contacts,
                searched_address=address,  # Pass address for branch handling
                min_similarity=0.80
            )
            
            if len(validated_contacts) < len(all_contacts):
                rejected = len(all_contacts) - len(validated_contacts)
                logger.warning(f"⚠️  Rejected {rejected} contacts (wrong company or low confidence)")
            
            logger.info(f"✅ {len(validated_contacts)} validated contacts returned")
            return validated_contacts
            
        except Exception as e:
            logger.error(f"Error using SerpApi for {company_name}: {str(e)}")
            return []
    
    def _extract_indian_phone(self, text: str) -> str:
        """Extract first Indian phone number from text."""
        phones = self._extract_all_indian_phones(text)
        return phones[0] if phones else ''
    
    def _extract_all_indian_phones(self, text: str) -> list:
        """Extract ALL Indian phone numbers from text."""
        # Enhanced patterns to catch more formats
        patterns = [
            r'\+91[-.\s]?[6-9]\d{9}',  # +91-9876543210
            r'91[-.\s]?[6-9]\d{9}',     # 91-9876543210
            r'\+91[-.\s]?\d{5}[-.\s]?\d{5}',  # +91-98765-43210
            r'\b[6-9]\d{9}\b',          # 9876543210 (standalone)
            r'\b[6-9]\d{4}\s?\d{5}\b',  # 98765 43210
        ]
        
        found_phones = []
        seen = set()
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                normalized = self._normalize_phone(match)
                if normalized and normalized not in seen:
                    found_phones.append(normalized)
                    seen.add(normalized)
        
        return found_phones
    
    def _extract_email(self, text: str) -> str:
        """Extract first email from text."""
        emails = self._extract_all_emails(text)
        return emails[0] if emails else ''
    
    def _extract_all_emails(self, text: str) -> list:
        """Extract ALL emails from text (includes gmail, yahoo, hotmail for small businesses)."""
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        matches = re.findall(email_pattern, text, re.IGNORECASE)
        
        found_emails = []
        seen = set()
        
        for email in matches:
            # Filter out ONLY blocked emails (spam, temp, test) using validator
            # Allow gmail, yahoo, hotmail since small businesses use them
            if not is_blocked_email(email):
                if email.lower() not in seen:
                    found_emails.append(email)
                    seen.add(email.lower())
        
        return found_emails
    
    def _extract_whatsapp(self, text: str) -> str:
        """Extract WhatsApp number from text."""
        whatsapp_pattern = r'[Ww]hats[Aa]pp[:\s]*(\+91[-.\s]?[6-9]\d{9})'
        match = re.search(whatsapp_pattern, text)
        if match:
            return self._normalize_phone(match.group(1))
        return ''
    
    def _extract_contact_name(self, text: str) -> str:
        """Extract contact person name from text."""
        # Look for common patterns like "Contact: Name", "Director: Name", etc.
        patterns = [
            r'(?:Contact|Director|Manager|Owner|CEO|Founder|Partner|Head)[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*\([^)]*(?:Director|Manager|Owner|CEO|Founder)\)',
            r'(?:Mr\.|Mrs\.|Ms\.|Dr\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                # Validate it's a reasonable name (2-4 words, not too long)
                words = name.split()
                if 1 <= len(words) <= 4 and len(name) < 50:
                    return name
        
        return ''
    
    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number to +91-XXXXXXXXXX format."""
        # Extract digits only
        digits = re.sub(r'[^\d]', '', phone)
        
        # Get last 10 digits (mobile number)
        if len(digits) >= 10:
            mobile = digits[-10:]
            # Validate it starts with 6-9
            if mobile[0] in '6789':
                return f'+91-{mobile}'
        
        return ''


# Standalone function for easy use
def enrich_with_serpapi(input_excel: str, output_excel: str, api_key: str = None, max_rows: int = None):
    """
    Enrich EXIM Excel with SerpApi.
    
    Args:
        input_excel: Input Excel path
        output_excel: Output Excel path
        api_key: SerpApi API key
        max_rows: Max rows to process (for testing)
    """
    import pandas as pd
    
    print(f"\n{'='*70}")
    print("SerpApi Contact Enrichment")
    print(f"{'='*70}\n")
    
    # Initialize
    try:
        enricher = SerpApiEnricher(api_key=api_key)
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("\nGet API key from: https://serpapi.com/")
        return
    
    # Read Excel
    print(f"📄 Reading: {input_excel}")
    try:
        df = pd.read_excel(input_excel, header=2, engine='openpyxl')
        print(f"✅ Loaded {len(df)} sellers\n")
    except Exception as e:
        print(f"❌ Error reading Excel: {str(e)}")
        return
    
    # Find columns
    seller_name_col = None
    seller_addr_col = None
    
    for col in df.columns:
        col_upper = str(col).upper()
        if 'SELLER' in col_upper and 'ADDRESS' not in col_upper:
            seller_name_col = col
        elif 'SELLER' in col_upper and 'ADDRESS' in col_upper:
            seller_addr_col = col
    
    if not seller_name_col:
        print("❌ Could not find 'SELLER' column")
        return
    
    # Process
    rows_to_process = df.head(max_rows) if max_rows else df
    enriched_data = []
    stats = {'total': 0, 'with_phone': 0, 'with_email': 0}
    
    print("Processing sellers...\n")
    
    for idx, row in rows_to_process.iterrows():
        seller_name = str(row.get(seller_name_col, '')).strip()
        seller_addr = str(row.get(seller_addr_col, '')).strip() if seller_addr_col else ''
        
        if not seller_name or seller_name == 'nan':
            continue
        
        stats['total'] += 1
        print(f"[{stats['total']}] {seller_name[:50]:<50}", end=" ... ", flush=True)
        
        # Get contact
        contact = enricher.find_contact(seller_name, seller_addr)
        
        phone = contact.get('phone', '').strip()
        email = contact.get('email', '').strip()
        
        if phone:
            stats['with_phone'] += 1
        if email:
            stats['with_email'] += 1
        
        if phone or email:
            parts = []
            if phone:
                parts.append(f"📞 {phone}")
            if email:
                parts.append(f"✉️  {email}")
            print(f"✅ {' | '.join(parts)}")
        else:
            print("❌ No contact")
        
        enriched_data.append({
            'Seller Name': seller_name,
            'Seller Address': seller_addr,
            'Phone': phone,
            'Email': email,
            'Source URL': contact.get('source_url', '')
        })
    
    # Save
    print(f"\n💾 Saving to: {output_excel}")
    output_df = pd.DataFrame(enriched_data)
    output_df.to_excel(output_excel, index=False, engine='openpyxl')
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"Total: {stats['total']}")
    if stats['total'] > 0:
        print(f"With phone: {stats['with_phone']} ({stats['with_phone']*100//stats['total']}%)")
        print(f"With email: {stats['with_email']} ({stats['with_email']*100//stats['total']}%)")
    print(f"\n✅ Done! Output: {output_excel}")
    print(f"{'='*70}\n")

