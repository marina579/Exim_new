"""
Hybrid Contact Enricher - Multi-source waterfall approach.
NEW PRIORITY ORDER:
1. Gemini AI + ChatGPT AI (BOTH TRIED - Results merged for best coverage!)
   - Gemini: Built-in Google Search, no SerpAPI needed
   - ChatGPT: Uses SerpAPI or Gemini internally
   - Results are merged (Gemini preferred, ChatGPT fills gaps)
2. WhatsApp Detective → WhatsApp Hunter → Google Places → SerpAPI → IndiaMART
Target: 80-90% total success rate
"""

import os
import logging
from typing import Dict, Optional
from serpapi_enricher import SerpApiEnricher

# IndiaMART imports
try:
    from scraper import find_indiamart_listing, scrape_indiamart_listing
    HAS_INDIAMART = True
except ImportError:
    HAS_INDIAMART = False
    logging.warning("IndiaMART scraper not available")

# ChatGPT imports
try:
    from chatgpt_enricher import ChatGPTEnricher
    HAS_CHATGPT = True
except ImportError:
    HAS_CHATGPT = False
    logging.warning("ChatGPT enricher not available")

# Google Places imports
try:
    from google_places_enricher import GooglePlacesEnricher
    HAS_GOOGLE_PLACES = True
except ImportError:
    HAS_GOOGLE_PLACES = False
    logging.warning("Google Places enricher not available")

# Gemini imports
try:
    from gemini_enricher import GeminiEnricher
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False
    logging.warning("Gemini enricher not available")

# WhatsApp Hunter imports
try:
    from whatsapp_hunter import WhatsAppHunter
    HAS_WHATSAPP_HUNTER = True
except ImportError:
    HAS_WHATSAPP_HUNTER = False
    logging.warning("WhatsApp Hunter not available")

# WhatsApp Detective imports (NEW!)
try:
    from whatsapp_detective import WhatsAppDetective
    HAS_WHATSAPP_DETECTIVE = True
except ImportError:
    HAS_WHATSAPP_DETECTIVE = False
    logging.warning("WhatsApp Detective not available")

logger = logging.getLogger(__name__)

# Email Enhancer imports
try:
    from email_enhancer import EmailEnhancer
    HAS_EMAIL_ENHANCER = True
except ImportError:
    HAS_EMAIL_ENHANCER = False
    logging.warning("Email Enhancer not available")


class HybridEnricher:
    """
    Multi-source contact enricher with waterfall approach.
    
    NEW: Supports collecting ALL contacts from ALL methods (multi-row output).
    """
    
    def __init__(self, serpapi_key: str = None, openai_key: str = None, gemini_key: str = None, google_maps_key: str = None, leadzen_key: str = None, collect_all: bool = False):
        """
        Initialize hybrid enricher.
        
        Args:
            serpapi_key: SerpApi API key
            openai_key: OpenAI API key (for ChatGPT fallback)
            gemini_key: Google Gemini API key (for Gemini fallback)
            google_maps_key: Google Maps API key (for Places API)
            leadzen_key: Leadzen.ai API key (for GST enrichment)
        """
        self.serpapi_key = serpapi_key or os.getenv('SERPAPI_API_KEY')
        self.openai_key = openai_key or os.getenv('OPENAI_API_KEY')
        self.gemini_key = gemini_key or os.getenv('GEMINI_API_KEY')
        self.google_maps_key = google_maps_key or os.getenv('GOOGLE_MAPS_API_KEY')
        self.leadzen_key = leadzen_key or os.getenv('LEADZEN_API_KEY')
        self.collect_all = collect_all  # If True, collect ALL contacts from ALL methods
        self.enable_indiamart = True  # Can be set to False to disable IndiaMART scraping
        
        # Initialize Email Enhancer (NEW - Advanced email extraction with Gemini + Pattern Matching + AI Validation!)
        if HAS_EMAIL_ENHANCER:
            try:
                self.email_enhancer = EmailEnhancer(
                    gemini_api_key=self.gemini_key,
                    serpapi_key=self.serpapi_key,  # For email pattern finder
                    openai_key=self.openai_key  # For AI validation
                )
                logger.info("✅ Email Enhancer initialized (Tiered extraction + Gemini AI + Pattern Matching + AI Validation)")
            except Exception as e:
                self.email_enhancer = None
                logger.warning(f"⚠️  Email Enhancer initialization failed: {str(e)}")
        else:
            self.email_enhancer = None
        
        # Initialize WhatsApp Detective (BEST - Two-pronged approach!)
        if HAS_WHATSAPP_DETECTIVE:
            try:
                self.whatsapp_detective = WhatsAppDetective(
                    serpapi_key=self.serpapi_key,
                    leadzen_key=self.leadzen_key
                )
                logger.info("✅ WhatsApp Detective initialized (Google Maps + GSTIN Enrichment)")
            except Exception as e:
                self.whatsapp_detective = None
                logger.warning(f"⚠️  WhatsApp Detective initialization failed: {str(e)}")
        else:
            self.whatsapp_detective = None
            logger.warning("⚠️  WhatsApp Detective not available")
        
        # Initialize WhatsApp Hunter (Backup method)
        if HAS_WHATSAPP_HUNTER:
            try:
                self.whatsapp_hunter = WhatsAppHunter(serpapi_key=self.serpapi_key)
                logger.info("✅ WhatsApp Hunter initialized (Google Dorking + Indian Directories)")
            except Exception as e:
                self.whatsapp_hunter = None
                logger.warning(f"⚠️  WhatsApp Hunter initialization failed: {str(e)}")
        else:
            self.whatsapp_hunter = None
            logger.warning("⚠️  WhatsApp Hunter not available")
        
        # Initialize Google Places enricher (BEST for addresses!)
        if self.google_maps_key and HAS_GOOGLE_PLACES:
            try:
                self.google_places = GooglePlacesEnricher(api_key=self.google_maps_key)
                logger.info("✅ Google Places enricher initialized")
            except Exception as e:
                self.google_places = None
                logger.warning(f"⚠️  Google Places initialization failed: {str(e)}")
        else:
            self.google_places = None
            if not self.google_maps_key:
                logger.warning("⚠️  Google Maps API key not found - Google Places disabled")
        
        # Initialize SerpApi enricher
        if self.serpapi_key:
            self.serpapi = SerpApiEnricher(api_key=self.serpapi_key)
            logger.info("✅ SerpApi enricher initialized")
        else:
            self.serpapi = None
            logger.warning("⚠️  SerpApi key not found")
        
        # Initialize ChatGPT enricher
        if self.openai_key and HAS_CHATGPT:
            self.chatgpt = ChatGPTEnricher(api_key=self.openai_key)
            logger.info("✅ ChatGPT enricher initialized")
        else:
            self.chatgpt = None
            if not self.openai_key:
                logger.warning("⚠️  OpenAI key not found - ChatGPT fallback disabled")
        
        # Initialize Gemini enricher
        if self.gemini_key and HAS_GEMINI:
            try:
                self.gemini = GeminiEnricher(api_key=self.gemini_key)
                logger.info("✅ Gemini enricher initialized")
            except Exception as e:
                self.gemini = None
                logger.warning(f"⚠️  Gemini initialization failed: {str(e)}")
        else:
            self.gemini = None
            if not self.gemini_key:
                logger.warning("⚠️  Gemini key not found - Gemini fallback disabled")
    
    def enrich_contact(self, company_name: str, address: str = "") -> Dict[str, str]:
        """
        Enrich contact using waterfall approach.
        Order: WhatsApp Detective → WhatsApp Hunter → Google Places → Gemini → ChatGPT → SerpApi → IndiaMART
        
        NOTE: This uses waterfall approach - stops after first successful method.
        Methods like WhatsApp Detective/Hunter may use SerpAPI internally, but since we stop
        after first success, there's no duplication of SerpAPI calls across methods.
        
        Args:
            company_name: Company name
            address: Company address
        
        Returns:
            Dictionary with phone, email, whatsapp, source, method
        """
        result = {
            'phone': '',
            'email': '',
            'whatsapp': '',
            'source_url': '',
            'method': 'none'
        }
        
        # Step 1: Try WhatsApp Detective (BEST - Two-pronged approach!)
        if self.whatsapp_detective:
            logger.info(f"[1/7] Trying WhatsApp Detective for: {company_name}")
            try:
                detective_result = self.whatsapp_detective.find_whatsapp(company_name, address)
                
                if detective_result.get('phone') or detective_result.get('whatsapp'):
                    result.update(detective_result)
                    logger.info(f"✅ WhatsApp Detective found contact for: {company_name}")
                    return result
                else:
                    logger.info(f"❌ WhatsApp Detective: No contact found")
            except Exception as e:
                logger.error(f"Error with WhatsApp Detective: {str(e)}")
        
        # Step 2: Try WhatsApp Hunter (Backup method)
        if self.whatsapp_hunter:
            logger.info(f"[2/7] Trying WhatsApp Hunter for: {company_name}")
            try:
                hunter_result = self.whatsapp_hunter.find_contacts(company_name, address)
                
                if hunter_result.get('phone') or hunter_result.get('whatsapp'):
                    result.update(hunter_result)
                    result['method'] = 'whatsapp_hunter'
                    logger.info(f"✅ WhatsApp Hunter found contact for: {company_name}")
                    return result
                else:
                    logger.info(f"❌ WhatsApp Hunter: No contact found")
            except Exception as e:
                logger.error(f"Error with WhatsApp Hunter: {str(e)}")
        
        # Step 3: Try Google Places (BEST for addresses!)
        if self.google_places and address:
            logger.info(f"[3/7] Trying Google Places for: {company_name}")
            try:
                places_result = self.google_places.find_contact(company_name, address)
                
                if places_result.get('phone'):
                    result['phone'] = places_result.get('phone', '')
                    result['email'] = places_result.get('email', '')
                    result['source_url'] = places_result.get('website', 'Google Maps')
                    result['method'] = 'google_places'
                    logger.info(f"✅ Google Places found contact for: {company_name}")
                    return result
                else:
                    logger.info(f"❌ Google Places: No phone found")
            except Exception as e:
                logger.error(f"Error with Google Places: {str(e)}")
        
        # STEP 4: Call SerpAPI ONCE, then use results for BOTH Gemini and ChatGPT
        gemini_result = {}
        chatgpt_result = {}
        serpapi_search_results = ""
        serpapi_used = False  # Track if SerpAPI was actually used
        
        # Step 4a: Get search results from SerpAPI ONCE (if available)
        if self.serpapi:
            logger.info(f"[4/7] 🔍 Calling SerpAPI ONCE for: {company_name} (will share results with Gemini & ChatGPT)")
            # Log SerpAPI key prefix to verify new key is being used
            serpapi_key = os.getenv('SERPAPI_API_KEY')
            if serpapi_key:
                logger.info(f"   🔑 Using SerpAPI key: {serpapi_key[:10]}... (first 10 chars)")
            try:
                # Use ChatGPT's internal method to get search results text (same format)
                from chatgpt_enricher import ChatGPTEnricher
                temp_chatgpt = ChatGPTEnricher()
                serpapi_search_results = temp_chatgpt._search_with_serpapi(company_name, address)
                if serpapi_search_results and serpapi_search_results != "No search results found":
                    serpapi_used = True  # Mark that SerpAPI was successfully used
                    logger.info(f"✅ Got {len(serpapi_search_results)} chars from SerpAPI (1 call - will be shared)")
                    logger.info(f"   📊 SerpAPI search results preview: {serpapi_search_results[:200]}...")
                else:
                    logger.warning(f"⚠️  SerpAPI returned no results")
                    serpapi_search_results = ""
            except Exception as e:
                logger.error(f"❌ SerpAPI error: {str(e)}")
                serpapi_search_results = ""
        else:
            logger.warning(f"⚠️  SerpAPI not available (key missing or not initialized)")
        
        # Step 4b: Try Gemini AI (with SerpAPI results as context if available)
        if self.gemini:
            logger.info(f"[4b/7] 🥇 Trying Gemini AI for: {company_name}")
            try:
                # Pass SerpAPI results to Gemini as additional context (Gemini will also do its own search)
                gemini_result = self.gemini.find_contact(company_name, address, search_results=serpapi_search_results if serpapi_search_results else None)
                
                if gemini_result.get('phone') or gemini_result.get('email'):
                    logger.info(f"✅ Gemini found: phone={gemini_result.get('phone', 'N/A')}, email={gemini_result.get('email', 'N/A')}")
                else:
                    logger.info(f"❌ Gemini: No contact found")
            except Exception as e:
                logger.error(f"❌ Gemini error: {str(e)}")
        
        # Step 4c: Try ChatGPT AI (with SerpAPI results - skip SerpAPI call in ChatGPT)
        if self.chatgpt:
            logger.info(f"[4c/7] 🥈 Trying ChatGPT AI for: {company_name}")
            try:
                # Pass SerpAPI results directly to ChatGPT (skips SerpAPI call inside ChatGPT)
                chatgpt_result = self.chatgpt.find_contact(company_name, address, search_results=serpapi_search_results if serpapi_search_results else None)
                
                if chatgpt_result.get('phone') or chatgpt_result.get('email'):
                    logger.info(f"✅ ChatGPT found: phone={chatgpt_result.get('phone', 'N/A')}, email={chatgpt_result.get('email', 'N/A')}")
                else:
                    logger.info(f"❌ ChatGPT: No contact found")
            except Exception as e:
                logger.error(f"❌ ChatGPT error: {str(e)}")
        
        # MERGE results from both Gemini and ChatGPT (prefer Gemini for conflicts)
        has_any_result = False
        methods_used = []  # Track which methods were used
        
        if gemini_result.get('phone') or gemini_result.get('email'):
            result.update(gemini_result)
            methods_used.append('gemini')
            has_any_result = True
            logger.info(f"📊 Merged Gemini results into final result")
        
        if chatgpt_result.get('phone') or chatgpt_result.get('email'):
            # Merge ChatGPT results, but don't overwrite Gemini data
            if not result.get('phone') and chatgpt_result.get('phone'):
                result['phone'] = chatgpt_result.get('phone')
                logger.info(f"📊 Added ChatGPT phone: {chatgpt_result.get('phone')}")
            if not result.get('email') and chatgpt_result.get('email'):
                result['email'] = chatgpt_result.get('email')
                logger.info(f"📊 Added ChatGPT email: {chatgpt_result.get('email')}")
            if not result.get('contact_name') and chatgpt_result.get('contact_name'):
                result['contact_name'] = chatgpt_result.get('contact_name')
            if not result.get('whatsapp') and chatgpt_result.get('whatsapp'):
                result['whatsapp'] = chatgpt_result.get('whatsapp')
            
            methods_used.append('chatgpt')
            has_any_result = True
        
        # Build method name to show all sources used (including SerpAPI if it was used)
        if methods_used:
            method_name = '+'.join(methods_used)
            if serpapi_used:
                method_name = f"{method_name}+serpapi"
            result['method'] = method_name
            logger.info(f"📊 Final method: {method_name} (SerpAPI used: {serpapi_used})")
        
        # If we got results from either Gemini or ChatGPT, return merged result
        if has_any_result:
            logger.info(f"✅ Combined AI results for: {company_name}")
            logger.info(f"   → Phone: {result.get('phone', 'N/A')}")
            logger.info(f"   → Email: {result.get('email', 'N/A')}")
            logger.info(f"   → Method: {result.get('method', 'N/A')}")
            return result
        else:
            logger.info(f"❌ Both Gemini and ChatGPT returned empty, trying other methods...")
        
        # STEP 6: Try SerpApi (Google search API)
        if self.serpapi:
            logger.info(f"[6/7] Trying SerpApi for: {company_name}")
            serpapi_result = self.serpapi.find_contact(company_name, address)
            
            if serpapi_result.get('phone') or serpapi_result.get('email'):
                result.update(serpapi_result)
                result['method'] = 'serpapi'
                logger.info(f"✅ SerpApi found contact for: {company_name}")
                return result
            else:
                logger.info(f"❌ SerpApi: No contact found")
        
        # STEP 7: Try IndiaMART direct scraping (last resort)
        if HAS_INDIAMART and self.enable_indiamart:
            logger.info(f"[7/7] Trying IndiaMART for: {company_name}")
            try:
                # Find IndiaMART listing
                indiamart_url = find_indiamart_listing(company_name, address)
                
                if indiamart_url:
                    logger.info(f"Found IndiaMART listing: {indiamart_url}")
                    
                    # Scrape the listing
                    indiamart_data = scrape_indiamart_listing(indiamart_url)
                    
                    if indiamart_data.get('phone') or indiamart_data.get('email'):
                        result['phone'] = indiamart_data.get('phone', '')
                        result['email'] = indiamart_data.get('email', '')
                        result['whatsapp'] = indiamart_data.get('whatsapp', '')
                        result['source_url'] = indiamart_url
                        result['method'] = 'indiamart'
                        logger.info(f"✅ IndiaMART found contact for: {company_name}")
                        return result
                else:
                    logger.info(f"❌ IndiaMART: No listing found")
            except Exception as e:
                logger.error(f"Error with IndiaMART: {str(e)}")
        
        # No contact found
        logger.warning(f"❌ All methods failed for: {company_name}")
        return result
    
    def enrich_contact_all(self, company_name: str, address: str = "") -> list:
        """
        Collect ALL contacts from ALL methods (multi-row output).
        
        Returns a list of contact dictionaries, one for each unique contact found.
        Each contact includes: phone, email, whatsapp, source_url, method
        
        Args:
            company_name: Name of the company
            address: Address of the company (optional but helps)
        
        Returns:
            List of contact dictionaries
        """
        all_contacts = []
        seen_phones = set()
        seen_emails = set()
        
        logger.info(f"🔍 Collecting ALL contacts for: {company_name}")
        
        # Try ALL methods and collect results
        # NEW ORDER: Gemini + ChatGPT (BOTH TRIED) → Other methods
        methods = []
        
        # Method 1: Gemini (Always try)
        if self.gemini:
            methods.append(('Gemini AI', lambda: self.gemini.find_contact(company_name, address)))
        
        # Method 2: ChatGPT (Always try - not fallback, both are tried!)
        if self.chatgpt:
            methods.append(('ChatGPT', lambda: self.chatgpt.find_contact(company_name, address)))
        
        # Method 3: WhatsApp Detective
        if self.whatsapp_detective:
            methods.append(('WhatsApp Detective', lambda: self.whatsapp_detective.find_whatsapp(company_name, address)))
        
        # Method 4: WhatsApp Hunter
        if self.whatsapp_hunter:
            methods.append(('WhatsApp Hunter', lambda: self.whatsapp_hunter.find_contacts(company_name, address)))
        
        # Method 5: Google Places
        if self.google_places and address:
            methods.append(('Google Places', lambda: self.google_places.find_contact(company_name, address)))
        
        # Method 6: SerpApi
        if self.serpapi:
            methods.append(('SerpApi', lambda: self.serpapi.find_contact(company_name, address)))
        
        # Method 7: IndiaMART
        if HAS_INDIAMART and self.enable_indiamart:
            def indiamart_search():
                try:
                    url = find_indiamart_listing(company_name)
                    if url:
                        return scrape_indiamart_listing(url)
                except:
                    pass
                return {}
            methods.append(('IndiaMART', indiamart_search))
        
        # Execute all methods
        for method_name, method_func in methods:
            try:
                logger.info(f"   [{len(all_contacts)+1}/{len(methods)}] Trying {method_name}...")
                result = method_func()
                
                if result and isinstance(result, dict):
                    phone = result.get('phone', '').strip()
                    email = result.get('email', '').strip()
                    whatsapp = result.get('whatsapp', '').strip() or phone
                    
                    # Only add if we found NEW contact info
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
                            'whatsapp': whatsapp,
                            'contact_name': result.get('contact_name', ''),
                            'source_url': result.get('source_url', result.get('website', '')),
                            'method': method_name.lower().replace(' ', '_')
                        }
                        all_contacts.append(contact)
                        logger.info(f"      ✅ {method_name}: Found contact (phone={phone[:15] if phone else 'N/A'}, email={email[:25] if email else 'N/A'})")
                    else:
                        logger.info(f"      ℹ️  {method_name}: Duplicate contact (skipped)")
                else:
                    logger.info(f"      ❌ {method_name}: No contact found")
                    
            except Exception as e:
                logger.error(f"      ❌ {method_name} error: {str(e)[:50]}")
        
        logger.info(f"   📊 Total unique contacts found: {len(all_contacts)}")
        
        # BONUS: Enhanced email extraction if email enhancer is available
        if self.email_enhancer and all_contacts:
            logger.info(f"   [BONUS] Running advanced email extraction...")
            
            # Collect metadata from contacts
            gstin = None
            director_name = None
            website = None
            
            for contact in all_contacts:
                if contact.get('gstin'):
                    gstin = contact['gstin']
                if contact.get('contact_name'):
                    director_name = contact['contact_name']
                if contact.get('source_url') and 'http' in contact['source_url']:
                    website = contact['source_url']
            
            # Run enhanced email search
            try:
                email_result = self.email_enhancer.find_emails(
                    company_name, 
                    address,
                    gstin=gstin,
                    director_name=director_name,
                    website=website
                )
                
                # Add enhanced emails to existing contacts or create new ones
                if email_result.get('primary'):
                    # Check if any contact already has this email
                    has_email = any(c.get('email') == email_result['primary'] for c in all_contacts)
                    
                    if not has_email:
                        # Add as new contact
                        all_contacts.append({
                            'phone': '',
                            'email': email_result['primary'],
                            'whatsapp': '',
                            'contact_name': director_name or '',
                            'source_url': email_result.get('sources', {}).get(email_result['primary'], 'Email Enhancer'),
                            'method': 'email_enhancer'
                        })
                        logger.info(f"      ✅ Enhanced email added: {email_result['primary']}")
                    else:
                        logger.info(f"      ℹ️  Email already in contacts: {email_result['primary']}")
                
                # Add secondary email if different
                if email_result.get('secondary') and email_result['secondary'] != email_result.get('primary'):
                    has_email = any(c.get('email') == email_result['secondary'] for c in all_contacts)
                    if not has_email:
                        all_contacts.append({
                            'phone': '',
                            'email': email_result['secondary'],
                            'whatsapp': '',
                            'contact_name': director_name or '',
                            'source_url': email_result.get('sources', {}).get(email_result['secondary'], 'Email Enhancer'),
                            'method': 'email_enhancer'
                        })
                        logger.info(f"      ✅ Secondary email added: {email_result['secondary']}")
            
            except Exception as e:
                logger.error(f"      ❌ Email enhancement error: {str(e)[:100]}")
        
        return all_contacts


def enrich_excel_hybrid(input_excel: str, output_excel: str, 
                        serpapi_key: str = None, openai_key: str = None,
                        max_rows: int = None):
    """
    Enrich Excel file using hybrid approach.
    
    Args:
        input_excel: Input Excel path
        output_excel: Output Excel path
        serpapi_key: SerpApi API key
        openai_key: OpenAI API key
        max_rows: Max rows to process (for testing)
    """
    import pandas as pd
    from datetime import datetime
    
    print(f"\n{'='*70}")
    print("🔥 HYBRID CONTACT ENRICHMENT")
    print("SerpApi → IndiaMART → ChatGPT AI Fallback")
    print(f"{'='*70}\n")
    
    # Initialize enricher
    enricher = HybridEnricher(serpapi_key=serpapi_key, openai_key=openai_key)
    
    # Read Excel
    print(f"📄 Reading: {input_excel}")
    try:
        # Try different header rows
        for header_row in [2, 1, 0]:
            try:
                df = pd.read_excel(input_excel, header=header_row, engine='openpyxl')
                
                # Find seller columns
                seller_name_col = None
                seller_addr_col = None
                
                for col in df.columns:
                    col_upper = str(col).upper()
                    if 'SELLER' in col_upper and 'ADDRESS' not in col_upper:
                        seller_name_col = col
                    elif 'SELLER' in col_upper and 'ADDRESS' in col_upper:
                        seller_addr_col = col
                
                if seller_name_col:
                    break
            except:
                continue
        
        if not seller_name_col:
            print("❌ Could not find seller columns")
            return
        
        print(f"✅ Loaded {len(df)} sellers\n")
        
    except Exception as e:
        print(f"❌ Error reading Excel: {str(e)}")
        return
    
    # Prepare data
    sellers_df = pd.DataFrame()
    sellers_df['Seller Name'] = df[seller_name_col].astype(str).str.strip()
    
    if seller_addr_col:
        sellers_df['Seller Address'] = df[seller_addr_col].astype(str).str.strip()
    else:
        sellers_df['Seller Address'] = ''
    
    # Filter and deduplicate
    sellers_df = sellers_df[
        (sellers_df['Seller Name'] != 'nan') & 
        (sellers_df['Seller Name'] != '') &
        (sellers_df['Seller Name'].notna())
    ]
    
    # Filter Indian addresses
    if seller_addr_col:
        indian_keywords = ['india', 'mumbai', 'delhi', 'bangalore', 'kolkata', 'chennai']
        sellers_df = sellers_df[
            sellers_df['Seller Address'].str.lower().str.contains('|'.join(indian_keywords), na=False)
        ]
    
    # Remove duplicates
    sellers_df['_name_lower'] = sellers_df['Seller Name'].str.lower()
    sellers_df = sellers_df.drop_duplicates(subset=['_name_lower'], keep='first')
    sellers_df = sellers_df.drop(columns=['_name_lower'])
    
    # Limit for testing
    if max_rows:
        sellers_df = sellers_df.head(max_rows)
    
    print(f"Processing {len(sellers_df)} unique sellers...\n")
    
    # Process each seller
    results = []
    stats = {
        'whatsapp_detective': 0,
        'google_maps': 0,
        'gst_enrichment': 0,
        'whatsapp_link': 0,
        'whatsapp_hunter': 0,
        'google_places': 0,
        'gemini': 0,
        'chatgpt': 0,
        'serpapi': 0,
        'indiamart': 0,
        'failed': 0,
        'total_phone': 0,
        'total_email': 0
    }
    
    start_time = datetime.now()
    
    for idx, row in sellers_df.iterrows():
        seller_name = row['Seller Name']
        seller_addr = row.get('Seller Address', '')
        
        current = idx + 1
        print(f"[{current}/{len(sellers_df)}] {seller_name[:50]:<50}", end=" ... ", flush=True)
        
        # Enrich
        contact = enricher.enrich_contact(seller_name, seller_addr)
        
        # Update stats
        method = contact.get('method', 'none')
        if method != 'none':
            stats[method] += 1
        else:
            stats['failed'] += 1
        
        if contact.get('phone'):
            stats['total_phone'] += 1
        if contact.get('email'):
            stats['total_email'] += 1
        
        # Display result
        if contact.get('phone') or contact.get('email'):
            parts = []
            if contact.get('phone'):
                parts.append(f"📞 {contact['phone']}")
            if contact.get('email'):
                parts.append(f"✉️  {contact['email']}")
            print(f"✅ {' | '.join(parts)} ({method})")
        else:
            print(f"❌ No contact")
        
        # Store result
        results.append({
            'Seller Name': seller_name,
            'Seller Address': seller_addr,
            'Phone': contact.get('phone', ''),
            'Email': contact.get('email', ''),
            'WhatsApp': contact.get('whatsapp', ''),
            'Source URL': contact.get('source_url', ''),
            'Method': method
        })
    
    # Save output
    print(f"\n💾 Saving to: {output_excel}")
    output_df = pd.DataFrame(results)
    output_df.to_excel(output_excel, index=False, engine='openpyxl')
    
    # Summary
    elapsed = (datetime.now() - start_time).total_seconds()
    total = len(results)
    found = total - stats['failed']
    
    print(f"\n{'='*70}")
    print("📊 SUMMARY")
    print(f"{'='*70}")
    print(f"Total processed: {total}")
    print(f"Success rate: {found}/{total} ({found*100//total if total > 0 else 0}%)")
    print(f"\n🎯 By Method:")
    print(f"  🔍 WhatsApp Detective:")
    print(f"     - Google Maps: {stats.get('google_maps', 0)} ({stats.get('google_maps', 0)*100//total if total > 0 else 0}%)")
    print(f"     - GST Enrichment: {stats.get('gst_enrichment', 0)} ({stats.get('gst_enrichment', 0)*100//total if total > 0 else 0}%)")
    print(f"     - WhatsApp Link: {stats.get('whatsapp_link', 0)} ({stats.get('whatsapp_link', 0)*100//total if total > 0 else 0}%)")
    print(f"  📱 WhatsApp Hunter: {stats['whatsapp_hunter']} ({stats['whatsapp_hunter']*100//total if total > 0 else 0}%)")
    print(f"  🗺️  Google Places: {stats['google_places']} ({stats['google_places']*100//total if total > 0 else 0}%)")
    print(f"  🤖 Gemini AI: {stats['gemini']} ({stats['gemini']*100//total if total > 0 else 0}%)")
    print(f"  🤖 ChatGPT AI: {stats['chatgpt']} ({stats['chatgpt']*100//total if total > 0 else 0}%)")
    print(f"  🔍 SerpApi: {stats['serpapi']} ({stats['serpapi']*100//total if total > 0 else 0}%)")
    print(f"  🏭 IndiaMART: {stats['indiamart']} ({stats['indiamart']*100//total if total > 0 else 0}%)")
    print(f"  ❌ Failed: {stats['failed']} ({stats['failed']*100//total if total > 0 else 0}%)")
    print(f"\n📞 Contacts Found:")
    print(f"  With phone: {stats['total_phone']} ({stats['total_phone']*100//total if total > 0 else 0}%)")
    print(f"  With email: {stats['total_email']} ({stats['total_email']*100//total if total > 0 else 0}%)")
    print(f"\n⏱️  Time: {elapsed:.1f}s ({elapsed/total:.1f}s per seller)")
    print(f"\n✅ Done! Output: {output_excel}")
    print(f"{'='*70}\n")

