"""
Automated background processing with chunking and database caching.
Processes files in chunks of 50 companies for large files.
"""

import os
import time
import pandas as pd
import logging
from hybrid_enricher import HybridEnricher
from database import db

logger = logging.getLogger(__name__)

# Auto-push to Zoho configuration
AUTO_PUSH_TO_ZOHO = os.getenv('AUTO_PUSH_TO_ZOHO', 'true').lower() == 'true'


def _auto_push_contacts_to_zoho(company_id: int, company_name: str, contacts: list):
    """
    Automatically push newly saved contacts to Zoho CRM.
    
    Args:
        company_id: Company ID
        company_name: Company name
        contacts: List of contact dictionaries (original contact data)
    """
    # Check if Zoho is configured
    zoho_client_id = os.getenv('ZOHO_CLIENT_ID')
    zoho_client_secret = os.getenv('ZOHO_CLIENT_SECRET')
    zoho_refresh_token = os.getenv('ZOHO_REFRESH_TOKEN')
    
    if not all([zoho_client_id, zoho_client_secret, zoho_refresh_token]):
        logger.debug(f"⏭️  Zoho not configured, skipping auto-push for {company_name}")
        return
    
    try:
        from zoho_crm_service import ZohoCRMService
        
        # Get contacts from database (they were just saved) with their IDs
        # We need to get contact IDs, so we'll query the database directly
        conn = db._get_connection()
        cursor = conn.cursor()
        
        try:
            if db.db_type == 'postgresql':
                cursor.execute("""
                    SELECT id, contact_name, first_name, last_name, email, phone, whatsapp
                    FROM contacts
                    WHERE company_id = %s
                    ORDER BY id DESC
                    LIMIT %s
                """, (company_id, len(contacts)))
            else:
                cursor.execute("""
                    SELECT id, contact_name, first_name, last_name, email, phone, whatsapp
                    FROM contacts
                    WHERE company_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                """, (company_id, len(contacts)))
            
            rows = cursor.fetchall()
        finally:
            conn.close()
        
        if not rows:
            logger.warning(f"⚠️  No contacts found in database for {company_name} after save")
            return
        
        # Prepare contacts for Zoho push with contact IDs
        zoho_service = ZohoCRMService(
            client_id=zoho_client_id,
            client_secret=zoho_client_secret,
            refresh_token=zoho_refresh_token,
            data_center=os.getenv('ZOHO_DATA_CENTER', 'in')
        )
        
        zoho_contacts = []
        
        for row in rows:
            if db.db_type == 'postgresql':
                contact_id = row['id']
                contact_name = row['contact_name'] or ''
                first_name = row['first_name'] or ''
                last_name = row['last_name'] or ''
                email = row['email'] or ''
                phone = row['whatsapp'] or row['phone'] or ''
            else:
                contact_id = row[0]
                contact_name = row[1] or ''
                first_name = row[2] or ''
                last_name = row[3] or ''
                email = row[4] or ''
                phone = row[6] or row[5] or ''
            
            # Build lead name
            lead_name = contact_name or f"{first_name} {last_name}".strip()
            if not lead_name and email:
                # Extract from email
                username = email.split('@')[0]
                lead_name = username.replace('.', ' ').replace('_', ' ').title()
            
            name_parts = lead_name.split() if lead_name else []
            zoho_first_name = name_parts[0] if name_parts else 'Unknown'
            zoho_last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else '.'
            
            contact_data = {
                'first_name': zoho_first_name,
                'last_name': zoho_last_name,
                'company': company_name,
                'email': email,
                'phone': phone,
                '_contact_id': contact_id,  # Store contact ID for status updates
            }
            zoho_contacts.append(contact_data)
        
        if not zoho_contacts:
            return
        
        logger.info(f"📤 Auto-pushing {len(zoho_contacts)} contacts to Zoho for {company_name}...")
        
        # Mark as pushing
        for contact_data in zoho_contacts:
            contact_id = contact_data.get('_contact_id')
            if contact_id:
                db.update_zoho_status(contact_id, 'pushing')
        
        # Push to Zoho (check duplicates by default)
        result = zoho_service.push_bulk_to_zoho(zoho_contacts, batch_size=100, check_duplicates=True)
        
        # Update database status for pushed contacts
        # Handle skipped contacts
        for skipped_item in result.get('skipped_contacts', []):
            skipped_contact = skipped_item.get('contact', {})
            contact_id = skipped_contact.get('_contact_id')
            if contact_id:
                lead_id = skipped_item.get('lead_id')
                db.update_zoho_status(contact_id, 'skipped', lead_id=lead_id)
        
        # Handle failed contacts
        for failed_item in result.get('failed_contacts', []):
            failed_contact = failed_item.get('contact', {})
            contact_id = failed_contact.get('_contact_id')
            if contact_id:
                error_msg = failed_item.get('error', 'Unknown error')
                db.update_zoho_status(contact_id, 'failed', error=error_msg)
        
        # Handle successful contacts
        for success_item in result.get('successful_contacts', []):
            success_contact = success_item.get('contact', {})
            contact_id = success_contact.get('_contact_id')
            lead_id = success_item.get('lead_id')
            if contact_id:
                db.update_zoho_status(contact_id, 'pushed', lead_id=lead_id)
        
        total_pushed = result.get('total_pushed', 0)
        total_skipped = result.get('total_skipped', 0)
        total_failed = result.get('total_failed', 0)
        
        if total_pushed > 0 or total_skipped > 0:
            logger.info(f"✅ Auto-pushed to Zoho: {total_pushed} pushed, {total_skipped} skipped, {total_failed} failed for {company_name}")
        else:
            logger.warning(f"⚠️  Auto-push to Zoho: All {total_failed} contacts failed for {company_name}")
            
    except ImportError:
        logger.debug(f"⏭️  Zoho service not available, skipping auto-push")
    except Exception as e:
        logger.error(f"❌ Error in auto-push to Zoho for {company_name}: {str(e)}", exc_info=True)
        # Don't raise - auto-push failures shouldn't break the main process

# Configuration
CHUNK_SIZE = 50  # Process 50 companies at a time
COLLECT_ALL_CONTACTS = True
USE_GEMINI = bool(os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_API_KEY') != 'YOUR_GEMINI_API_KEY_HERE')


def process_file_automated(job_id, file_path, filename, output_folder, test_mode=False, test_limit=25):
    """
    Automated background processing with chunking and database caching.
    
    Steps:
    1. Parse Excel file
    2. Clean and deduplicate
    3. Check database for existing companies (skip them!)
    4. Process new companies in chunks of 50
    5. Generate output file with all contacts
    """
    start_time = time.time()
    
    try:
        # Update job status to processing
        db.update_job_status(job_id, 'processing')
        
        logger.info(f"🚀 Starting automated processing for job {job_id}: {filename}")
        
        # Step 1: Parse Excel file
        logger.info(f"📖 Step 1: Parsing Excel file...")
        try:
            df = pd.read_excel(file_path, engine='openpyxl')
        except Exception as e:
            error_msg = f"Failed to parse Excel file: {str(e)}"
            logger.error(error_msg)
            db.update_job_status(job_id, 'failed', error_message=error_msg)
            return
        
        # Step 2: Clean and deduplicate
        logger.info(f"🧹 Step 2: Cleaning and deduplicating...")
        
        # Find Seller Name column (column P or similar)
        seller_col = None
        for col in df.columns:
            if 'seller' in str(col).lower() and 'name' in str(col).lower():
                seller_col = col
                break
        
        if seller_col is None:
            # Try column index P (16th column, index 15)
            if len(df.columns) >= 16:
                seller_col = df.columns[15]
            else:
                error_msg = "Could not find Seller Name column. Please ensure your Excel has 'Seller Name' column."
                logger.error(error_msg)
                db.update_job_status(job_id, 'failed', error_message=error_msg)
                return
        
        # Find address column
        addr_col = None
        for col in df.columns:
            if 'seller' in str(col).lower() and 'address' in str(col).lower():
                addr_col = col
                break
        
        # Extract sellers
        sellers_df = df[[seller_col]].copy()
        sellers_df.columns = ['Seller Name']
        
        if addr_col:
            sellers_df['Seller Address'] = df[addr_col]
        else:
            sellers_df['Seller Address'] = ''
        
        # Remove nulls and duplicates
        sellers_df = sellers_df.dropna(subset=['Seller Name'])
        sellers_df = sellers_df[sellers_df['Seller Name'].str.strip() != '']
        original_count = len(sellers_df)
        sellers_df = sellers_df.drop_duplicates(subset=['Seller Name'], keep='first')
        unique_count = len(sellers_df)
        duplicates_removed = original_count - unique_count
        
        logger.info(f"📊 Found {unique_count} unique companies ({duplicates_removed} duplicates removed)")
        
        # Update job with initial stats
        db.update_job_status(job_id, 'processing', 
                           total_rows=unique_count,
                           duplicates_removed=duplicates_removed)
        
        # Step 3: Check database for existing companies
        logger.info(f"💾 Step 3: Checking database for existing companies...")
        new_companies = []
        cached_companies = []
        
        for idx, row in sellers_df.iterrows():
            company_name = row['Seller Name']
            company_id = db.check_company_exists(company_name)
            
            if company_id:
                cached_companies.append({'name': company_name, 'id': company_id})
            else:
                new_companies.append(row)
        
        logger.info(f"💾 Found {len(cached_companies)} companies in database (will skip)")
        logger.info(f"🆕 Found {len(new_companies)} new companies (will process)")
        
        # Step 4: Process new companies in chunks of 50
        total_chunks = (len(new_companies) + CHUNK_SIZE - 1) // CHUNK_SIZE if new_companies else 0
        
        logger.info(f"📦 Step 4: Processing {len(new_companies)} companies in {total_chunks} chunks of {CHUNK_SIZE}...")
        
        # Initialize enricher
        serpapi_key = os.getenv('SERPAPI_API_KEY')
        openai_key = os.getenv('OPENAI_API_KEY')
        gemini_key = os.getenv('GEMINI_API_KEY') if USE_GEMINI else None
        
        if not serpapi_key:
            error_msg = "SerpAPI key not found. Please set SERPAPI_API_KEY in environment variables."
            logger.error(error_msg)
            db.update_job_status(job_id, 'failed', error_message=error_msg)
            return
        
        enricher = HybridEnricher(
            serpapi_key=serpapi_key,
            openai_key=openai_key,
            gemini_key=gemini_key,
            collect_all=COLLECT_ALL_CONTACTS
        )
        
        contacts_found = 0
        companies_found = 0
        api_calls_used = 0
        
        # Process in chunks
        for chunk_idx in range(total_chunks):
            chunk_start = chunk_idx * CHUNK_SIZE
            chunk_end = min(chunk_start + CHUNK_SIZE, len(new_companies))
            chunk = new_companies[chunk_start:chunk_end]
            
            logger.info(f"📦 Processing chunk {chunk_idx + 1}/{total_chunks} ({len(chunk)} companies)...")
            
            for company_data in chunk:
                # Check if job was cancelled by user
                current_job = db.get_job_by_id(job_id)
                if current_job and current_job.get('status') == 'cancelled':
                    logger.info(f"🛑 Job {job_id} cancelled by user - stopping processing")
                    return
                
                company_name = company_data['Seller Name']
                company_address = company_data.get('Seller Address', '')
                
                logger.info(f"🔍 Processing: {company_name}")
                
                try:
                    # Extract all contacts from single API call
                    # NOTE: Only using SerpAPI directly, not HybridEnricher full waterfall
                    # to avoid multiple API calls per company
                    contacts_list = enricher.serpapi.find_all_contacts(company_name, company_address) if enricher.serpapi else []
                    api_calls_used += 1
                    logger.info(f"📊 API call #{api_calls_used} for {company_name}")
                    
                    if contacts_list:
                        # Extract enrichment metadata
                        metadata = {}
                        if contacts_list:
                            first_contact = contacts_list[0]
                            metadata = {
                                'gstin': first_contact.get('gstin', ''),
                                'pan': first_contact.get('pan', ''),
                                'cin': first_contact.get('cin', ''),
                                'website': first_contact.get('website', ''),
                                'industry': first_contact.get('industry', '')
                            }
                        
                        # Save to database
                        company_id = db.save_company_and_contacts(
                            company_name=company_name,
                            address=company_address,
                            contacts=contacts_list,
                            **metadata
                        )
                        
                        contacts_found += len(contacts_list)
                        companies_found += 1
                        logger.info(f"✅ Saved {len(contacts_list)} contacts for {company_name}")
                        
                        # Auto-push to Zoho if enabled and configured
                        if AUTO_PUSH_TO_ZOHO:
                            try:
                                _auto_push_contacts_to_zoho(company_id, company_name, contacts_list)
                            except Exception as e:
                                logger.warning(f"⚠️  Auto-push to Zoho failed for {company_name}: {str(e)}")
                                # Don't fail the entire process if auto-push fails
                    else:
                        logger.info(f"⚠️ No contacts found for {company_name}")
                    
                    # Update job progress
                    db.update_job_status(job_id, 'processing',
                                       contacts_found=contacts_found,
                                       companies_found=companies_found + len(cached_companies),
                                       new_companies=companies_found,
                                       api_calls_used=api_calls_used)
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {company_name}: {str(e)}")
                    continue
            
            logger.info(f"✅ Chunk {chunk_idx + 1}/{total_chunks} complete")
        
        # Step 5: Generate output file with all contacts (cached + new)
        logger.info(f"📄 Step 5: Generating output file...")
        
        # Get all contacts for this job
        output_data = []
        for idx, row in sellers_df.iterrows():
            company_name = row['Seller Name']
            company_id = db.check_company_exists(company_name)
            
            if company_id:
                contacts = db.get_company_contacts(company_id)
                for contact in contacts:
                    output_data.append({
                        'Company': company_name,
                        'Contact Name': contact.get('contact_name', ''),
                        'First Name': contact.get('first_name', ''),
                        'Last Name': contact.get('last_name', ''),
                        'Phone': contact.get('phone', ''),
                        'Email': contact.get('email', ''),
                        'WhatsApp': contact.get('whatsapp', ''),
                        'Source': contact.get('source_url', ''),
                        'Method': contact.get('method', '')
                    })
        
        # Save output file
        output_filename = f"enriched_{filename}"
        output_path = os.path.join(output_folder, output_filename)
        
        if output_data:
            output_df = pd.DataFrame(output_data)
            output_df.to_excel(output_path, index=False, engine='openpyxl')
            logger.info(f"💾 Output file saved: {output_filename}")
        else:
            # Create empty file
            pd.DataFrame().to_excel(output_path, index=False, engine='openpyxl')
        
        # Calculate processing time
        processing_time = int(time.time() - start_time)
        
        # Mark job as completed
        db.update_job_status(job_id, 'completed',
                           contacts_found=contacts_found,
                           companies_found=companies_found + len(cached_companies),
                           new_companies=companies_found,
                           api_calls_used=api_calls_used,
                           processing_time=processing_time,
                           output_file=output_filename)
        
        logger.info(f"✅ Job {job_id} completed successfully!")
        logger.info(f"📊 Stats: {contacts_found} contacts, {companies_found} new companies, {api_calls_used} API calls, {processing_time}s")
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"❌ Job {job_id} failed: {error_msg}")
        import traceback
        traceback.print_exc()
        db.update_job_status(job_id, 'failed', error_message=error_msg)

