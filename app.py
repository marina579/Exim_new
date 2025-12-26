"""
Flask app for EXIM Contact Enrichment using SerpApi.
Uploads Excel, removes duplicates, enriches with SerpApi, downloads results.
"""

import os
import uuid
import threading
import time
import logging
import requests
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session
from werkzeug.utils import secure_filename
import pandas as pd
from hybrid_enricher import HybridEnricher
from database import db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'exim_contact_enricher_secret_key_2024'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max file size

# Create folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# Progress tracking
progress_data = {}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'xlsm', 'xlsb'}

# TESTING MODE: Set to None to process all records, or a number to limit
# Example: MAX_RECORDS_TO_PROCESS = 25  (for testing)
#          MAX_RECORDS_TO_PROCESS = None (for production - process all)
MAX_RECORDS_TO_PROCESS = 25  # 🔥 TESTING MODE: Only process 25 records

# MULTI-ROW MODE: If True, creates multiple rows for each unique contact found
# Example: If Company A has 3 contacts, creates 3 rows
COLLECT_ALL_CONTACTS = True  # 🔥 NEW FEATURE: Multiple rows per company

# TEMPORARY FIX: Disable Gemini due to quota exhaustion (1,500 requests/day limit)
USE_GEMINI = False  # 🚫 Disabled temporarily - change to True when quota resets (midnight UTC)
# To check quota: python check_gemini_quota.py


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _split_name(full_name):
    """
    Split full name into first name and last name.
    Handles various Indian name formats.
    
    Examples:
    - "Rajesh Kumar" → ("Rajesh", "Kumar")
    - "Mr. Amit Sharma" → ("Amit", "Sharma")
    - "Dr. Priya Gupta" → ("Priya", "Gupta")
    - "Kumar" → ("Kumar", "")
    """
    if not full_name:
        return '', ''
    
    # Remove common titles
    titles = ['mr', 'mrs', 'ms', 'dr', 'prof', 'sir', 'shri', 'smt', 'kumar']
    name_parts = full_name.strip().split()
    
    # Filter out titles and dots
    filtered_parts = []
    for part in name_parts:
        clean_part = part.lower().replace('.', '').strip()
        if clean_part not in titles and len(clean_part) > 1:
            filtered_parts.append(part)
    
    if not filtered_parts:
        return full_name, ''
    elif len(filtered_parts) == 1:
        return filtered_parts[0], ''
    else:
        # First word is first name, rest is last name
        first_name = filtered_parts[0]
        last_name = ' '.join(filtered_parts[1:])
        return first_name, last_name


def _extract_enrichment_metadata(contact):
    """
    Extract enrichment metadata from contact for caching.
    Includes GST, PAN, website, etc. to avoid future API calls.
    """
    metadata = {}
    
    # Extract GST/GSTIN if present
    if contact.get('gstin'):
        metadata['gstin'] = contact['gstin']
    if contact.get('gst'):
        metadata['gstin'] = contact['gst']
    
    # Extract other identifiers
    if contact.get('pan'):
        metadata['pan'] = contact['pan']
    if contact.get('cin'):
        metadata['cin'] = contact['cin']
    
    # Extract website
    source_url = contact.get('source_url', '')
    if source_url and 'http' in source_url:
        # Clean up source URL to get domain
        if 'indiamart.com' not in source_url and 'google.com' not in source_url:
            metadata['website'] = source_url
    
    # Extract any additional enrichment data
    enrichment_data = {}
    if contact.get('director_name'):
        enrichment_data['director_name'] = contact['director_name']
    if contact.get('industry'):
        enrichment_data['industry'] = contact['industry']
        metadata['industry'] = contact['industry']
    if contact.get('business_type'):
        enrichment_data['business_type'] = contact['business_type']
    
    if enrichment_data:
        metadata['enrichment_data'] = enrichment_data
    
    return metadata


def parse_and_clean_excel(file_path):
    """
    Parse Excel and return cleaned, deduplicated seller list.
    Returns: DataFrame with unique sellers
    """
    # Try different header rows
    for header_row in [2, 1, 0]:
        try:
            df = pd.read_excel(file_path, header=header_row, engine='openpyxl')
            
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
                # Clean data
                sellers_df = pd.DataFrame()
                sellers_df['Seller Name'] = df[seller_name_col].astype(str).str.strip()
                
                if seller_addr_col:
                    sellers_df['Seller Address'] = df[seller_addr_col].astype(str).str.strip()
                else:
                    sellers_df['Seller Address'] = ''
                
                # Remove NaN and empty
                sellers_df = sellers_df[
                    (sellers_df['Seller Name'] != 'nan') & 
                    (sellers_df['Seller Name'] != '') &
                    (sellers_df['Seller Name'].notna())
                ]
                
                # Filter Indian addresses only
                if seller_addr_col:
                    indian_keywords = ['india', 'mumbai', 'delhi', 'bangalore', 'kolkata', 'chennai', 
                                     'hyderabad', 'pune', 'ahmedabad', 'jaipur', 'lucknow', 'kanpur',
                                     'west bengal', 'maharashtra', 'karnataka', 'tamil nadu', 'gujarat',
                                     'rajasthan', 'uttar pradesh', 'telangana', 'kerala', 'punjab']
                    
                    sellers_df = sellers_df[
                        sellers_df['Seller Address'].str.lower().str.contains('|'.join(indian_keywords), na=False)
                    ]
                
                # Remove duplicates (case-insensitive on Seller Name)
                sellers_df['_name_lower'] = sellers_df['Seller Name'].str.lower()
                sellers_df = sellers_df.drop_duplicates(subset=['_name_lower'], keep='first')
                sellers_df = sellers_df.drop(columns=['_name_lower'])
                
                return sellers_df, None
            
        except Exception as e:
            continue
    
    return None, "Could not parse Excel file. Please ensure it has Seller Name in Column P."


def process_file_background(file_id, file_path, output_path):
    """Background processing with SerpApi."""
    try:
        # Update progress
        progress_data[file_id]['status'] = 'parsing'
        progress_data[file_id]['message'] = 'Parsing Excel file...'
        
        # Parse and clean
        sellers_df, error = parse_and_clean_excel(file_path)
        
        if error:
            progress_data[file_id]['status'] = 'error'
            progress_data[file_id]['message'] = error
            return
        
        total_original = len(sellers_df)
        
        # Apply testing limit if set
        if MAX_RECORDS_TO_PROCESS:
            sellers_df = sellers_df.head(MAX_RECORDS_TO_PROCESS)
            progress_data[file_id]['testing_mode'] = True
            progress_data[file_id]['message'] = f'🧪 TESTING MODE: Processing first {MAX_RECORDS_TO_PROCESS} of {total_original} unique sellers'
        else:
            progress_data[file_id]['testing_mode'] = False
            progress_data[file_id]['message'] = f'Found {total_original} unique Indian sellers. Enriching contacts...'
        
        total_to_process = len(sellers_df)
        progress_data[file_id]['total_original'] = total_original
        progress_data[file_id]['total_unique'] = total_to_process
        progress_data[file_id]['status'] = 'enriching'
        
        # Initialize Hybrid Enricher (SerpApi + IndiaMART + ChatGPT + Gemini)
        serpapi_key = os.getenv('SERPAPI_API_KEY')
        openai_key = os.getenv('OPENAI_API_KEY')
        gemini_key = os.getenv('GEMINI_API_KEY') if USE_GEMINI else None  # Disable if quota hit
        
        if not serpapi_key:
            progress_data[file_id]['status'] = 'error'
            progress_data[file_id]['message'] = 'SerpApi API key not found. Please set SERPAPI_API_KEY environment variable.'
            return
        
        enricher = HybridEnricher(
            serpapi_key=serpapi_key, 
            openai_key=openai_key, 
            gemini_key=gemini_key,  # Will be None if USE_GEMINI=False
            collect_all=COLLECT_ALL_CONTACTS
        )
        
        # Enrich each seller with DATABASE CACHING
        results = []
        stats = {'phone': 0, 'email': 0, 'whatsapp': 0, 'total_contacts': 0, 
                 'cached': 0, 'processed': 0, 'multi_contact_companies': 0}
        
        for idx, row in sellers_df.iterrows():
            seller_name = row['Seller Name']
            seller_addr = row.get('Seller Address', '')
            
            # Update progress
            current = idx + 1
            progress_data[file_id]['current'] = current
            progress_data[file_id]['percentage'] = int((current / total_to_process) * 100)
            progress_data[file_id]['current_seller'] = seller_name
            
            # 🔍 CHECK DATABASE CACHE FIRST (Avoids duplicate API calls!)
            company_id = db.check_company_exists(seller_name)
            
            contacts_list = []
            
            if company_id:
                # ✅ Found in database - use cached contacts (0 API calls!)
                progress_data[file_id]['message'] = f'💾 Using cached data for: {seller_name}'
                logger.info(f"💾 Cache hit for: {seller_name}")
                contacts_list = db.get_company_contacts(company_id)
                stats['cached'] += 1
            else:
                # ❌ Not in database - process now
                # 🚀 NEW: Extract ALL contacts from 1 API call (not multiple calls!)
                progress_data[file_id]['message'] = f'🔍 Processing: {seller_name}'
                logger.info(f"🔍 Processing new contact: {seller_name} (multi-contact extraction)")
                stats['processed'] += 1
                
                # Use SerpApi's find_all_contacts() to extract MULTIPLE contacts from 1 API call
                # This is MORE EFFICIENT than trying multiple methods!
                if COLLECT_ALL_CONTACTS:
                    # Extract ALL contacts from single API call
                    contacts_list = enricher.serpapi.find_all_contacts(seller_name, seller_addr) if enricher.serpapi else []
                    logger.info(f"🎯 Extracted {len(contacts_list)} contacts from 1 API call")
                else:
                    # Extract single best contact
                    contact = enricher.enrich_contact(seller_name, seller_addr)
                    if contact and (contact.get('phone') or contact.get('email')):
                        contacts_list = [contact]
                    else:
                        contacts_list = []
                
                # Extract enrichment metadata from first contact (GST, PAN, website, etc.)
                metadata = {}
                if contacts_list:
                    metadata = _extract_enrichment_metadata(contacts_list[0])
                
                # 💾 Save ALL contacts to database with enrichment metadata
                if contacts_list:
                    try:
                        db.save_company_and_contacts(
                            company_name=seller_name,
                            address=seller_addr,
                            contacts=contacts_list,
                            gstin=metadata.get('gstin'),
                            pan=metadata.get('pan'),
                            cin=metadata.get('cin'),
                            website=metadata.get('website'),
                            industry=metadata.get('industry'),
                            enrichment_data=metadata.get('enrichment_data')
                        )
                        logger.info(f"💾 Saved {len(contacts_list)} contacts to database: {seller_name} (GST: {metadata.get('gstin', 'N/A')})")
                    except Exception as e:
                        logger.error(f"Failed to save to database: {str(e)}")
                else:
                    contacts_list = []
            
            # Process contacts and create result rows
            if contacts_list:
                # Track multi-contact companies
                if len(contacts_list) > 1:
                    stats['multi_contact_companies'] += 1
                
                # Create a row for EACH contact
                for contact in contacts_list:
                    phone = contact.get('phone', '').strip()
                    email = contact.get('email', '').strip()
                    whatsapp = contact.get('whatsapp', '').strip()
                    source = contact.get('source_url', '').strip()
                    method = contact.get('method', 'cached' if company_id else 'unknown')
                    contact_name = contact.get('contact_name', '').strip()
                    
                    # Split contact name into first and last names
                    first_name, last_name = _split_name(contact_name)
                    
                    if phone:
                        stats['phone'] += 1
                    if email:
                        stats['email'] += 1
                    if whatsapp:
                        stats['whatsapp'] += 1
                    stats['total_contacts'] += 1
                    
                    results.append({
                        'Seller Name': seller_name,
                        'Seller Address': seller_addr,
                        'Contact Name': contact_name,
                        'First Name': first_name,
                        'Last Name': last_name,
                        'Phone': phone,
                        'Email': email,
                        'WhatsApp': whatsapp,
                        'Source URL': source,
                        'Method': method
                    })
            else:
                # No contacts found - create empty row
                results.append({
                    'Seller Name': seller_name,
                    'Seller Address': seller_addr,
                    'Contact Name': '',
                    'First Name': '',
                    'Last Name': '',
                    'Phone': '',
                    'Email': '',
                    'WhatsApp': '',
                    'Source URL': '',
                    'Method': 'none'
                })
            
            # Update stats
            progress_data[file_id]['stats'] = stats.copy()
            
            # NO MORE SLEEP - Rate limiting handled by individual enrichers
            # Removed: time.sleep(0.5)
        
        # Save output
        output_df = pd.DataFrame(results)
        output_df.to_excel(output_path, index=False, engine='openpyxl')
        
        # Auto-generate Zoho CRM format exports
        logger.info("📊 Generating Zoho CRM format exports...")
        try:
            zoho_excel, zoho_csv = _create_zoho_export(output_path)
            if zoho_excel and zoho_csv:
                logger.info(f"✅ Zoho exports created: {os.path.basename(zoho_excel)} and {os.path.basename(zoho_csv)}")
        except Exception as e:
            logger.warning(f"Could not create Zoho exports: {str(e)}")
        
        # Complete
        progress_data[file_id]['status'] = 'complete'
        msg = f'Complete! {stats["total_contacts"]} contacts ({stats["phone"]} phones, {stats["email"]} emails)'
        if stats.get('cached', 0) > 0:
            msg += f' | 💾 {stats["cached"]} cached (0 API calls!)'
        if stats.get('processed', 0) > 0:
            msg += f' | 🔍 {stats["processed"]} new'
        if stats.get('multi_contact_companies', 0) > 0:
            msg += f' | {stats["multi_contact_companies"]} multi-contact companies'
        progress_data[file_id]['message'] = msg
        progress_data[file_id]['output_file'] = os.path.basename(output_path)
        progress_data[file_id]['percentage'] = 100
        
    except Exception as e:
        progress_data[file_id]['status'] = 'error'
        progress_data[file_id]['message'] = f'Error: {str(e)}'


@app.route('/test-chatgpt')
def test_chatgpt():
    """Test endpoint to verify ChatGPT/OpenAI API is working."""
    try:
        from chatgpt_enricher import ChatGPTEnricher
        
        # Check if API key is set
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            return jsonify({
                'status': 'error',
                'message': 'OPENAI_API_KEY not found in environment variables',
                'key_present': False
            }), 500
        
        # Initialize enricher
        try:
            enricher = ChatGPTEnricher(api_key=api_key)
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Failed to initialize ChatGPTEnricher: {str(e)}',
                'error_type': type(e).__name__
            }), 500
        
        # Test with a simple company
        test_company = "Tata Consultancy Services"
        test_address = "Mumbai, India"
        
        logger.info(f"🧪 Testing ChatGPT with: {test_company}")
        
        try:
            result = enricher.find_contact(test_company, test_address)
            
            return jsonify({
                'status': 'success',
                'message': 'ChatGPT API is working!',
                'test_company': test_company,
                'result': result,
                'api_key_prefix': api_key[:15] + '...' if api_key else 'N/A',
                'has_phone': bool(result.get('phone')),
                'has_email': bool(result.get('email')),
                'has_whatsapp': bool(result.get('whatsapp')),
                'has_contact_name': bool(result.get('contact_name'))
            })
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            
            # Check for specific error types
            error_details = {
                'error_type': error_type,
                'error_message': error_msg,
                'api_key_prefix': api_key[:15] + '...' if api_key else 'N/A'
            }
            
            if "401" in error_msg or "Unauthorized" in error_msg:
                error_details['diagnosis'] = 'Invalid or expired API key'
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                error_details['diagnosis'] = 'Rate limit exceeded'
            elif "timeout" in error_msg.lower():
                error_details['diagnosis'] = 'Request timeout'
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                error_details['diagnosis'] = 'Network connectivity issue'
            else:
                error_details['diagnosis'] = 'Unknown error - check logs'
            
            return jsonify({
                'status': 'error',
                'message': 'ChatGPT API call failed',
                **error_details
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Test endpoint error: {str(e)}',
            'error_type': type(e).__name__
        }), 500


@app.route('/')
def index():
    """Home page with upload form."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and start processing."""
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    if not allowed_file(file.filename):
        flash('Invalid file type. Please upload .xlsx or .xls file', 'error')
        return redirect(url_for('index'))
    
    try:
        # Save uploaded file
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_{filename}')
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], f'{file_id}_enriched.xlsx')
        
        file.save(upload_path)
        
        # Initialize progress tracking
        progress_data[file_id] = {
            'status': 'uploaded',
            'message': 'File uploaded successfully',
            'filename': filename,
            'upload_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'file_size': os.path.getsize(upload_path),
            'total_original': 0,
            'total_unique': 0,
            'current': 0,
            'percentage': 0,
            'current_seller': '',
            'stats': {'phone': 0, 'email': 0, 'whatsapp': 0},
            'output_file': None
        }
        
        # Start background processing
        thread = threading.Thread(
            target=process_file_background,
            args=(file_id, upload_path, output_path)
        )
        thread.daemon = True
        thread.start()
        
        # Redirect to progress page
        return redirect(url_for('progress', file_id=file_id))
        
    except Exception as e:
        flash(f'Error uploading file: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/progress/<file_id>')
def progress(file_id):
    """Show progress page."""
    if file_id not in progress_data:
        flash('Invalid file ID or session expired', 'error')
        return redirect(url_for('index'))
    
    return render_template('progress.html', file_id=file_id)


@app.route('/api/progress/<file_id>')
def api_progress(file_id):
    """API endpoint for progress updates."""
    if file_id not in progress_data:
        return jsonify({'error': 'File ID not found'}), 404
    
    return jsonify(progress_data[file_id])


def _extract_name_from_email(email: str) -> str:
    """
    Extract name from email address.
    Example: rajesh.kumar@company.com → Rajesh Kumar
    """
    if not email or '@' not in email:
        return ''
    
    # Get part before @
    username = email.split('@')[0]
    
    # Replace common separators with spaces
    name = username.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    
    # Capitalize each word
    name_parts = [part.capitalize() for part in name.split() if len(part) > 1]
    
    # Limit to first 2-3 words (avoid long usernames)
    if len(name_parts) > 3:
        name_parts = name_parts[:2]
    
    return ' '.join(name_parts)


def _create_zoho_export(output_path: str) -> str:
    """
    Create Zoho CRM formatted export from regular output file.
    
    Zoho Format:
    - Lead Name: Contact name or name extracted from email
    - Company: Seller/Company name
    - Email: Email address
    - Phone: Phone/WhatsApp (prefer mobile)
    
    Returns:
        Path to Zoho-formatted file
    """
    try:
        # Read the regular output file
        df = pd.read_excel(output_path, engine='openpyxl')
        
        # Create Zoho-formatted data
        zoho_data = []
        
        for _, row in df.iterrows():
            # Get lead name: prefer contact name, fallback to email extraction
            lead_name = ''
            if row.get('Contact Name') and str(row['Contact Name']).strip() and str(row['Contact Name']) != 'nan':
                lead_name = str(row['Contact Name']).strip()
            elif row.get('First Name') and str(row['First Name']).strip() and str(row['First Name']) != 'nan':
                # Combine first and last name
                first = str(row.get('First Name', '')).strip()
                last = str(row.get('Last Name', '')).strip()
                lead_name = f"{first} {last}".strip()
            elif row.get('Email') and str(row['Email']).strip() and str(row['Email']) != 'nan':
                # Extract name from email
                lead_name = _extract_name_from_email(str(row['Email']))
            
            # Get company name
            company = str(row.get('Seller Name', '')).strip() if row.get('Seller Name') else ''
            
            # Get email
            email = str(row.get('Email', '')).strip() if row.get('Email') and str(row['Email']) != 'nan' else ''
            
            # Get phone: prefer WhatsApp, then Phone
            phone = ''
            if row.get('WhatsApp') and str(row['WhatsApp']).strip() and str(row['WhatsApp']) != 'nan':
                phone = str(row['WhatsApp']).strip()
            elif row.get('Phone') and str(row['Phone']).strip() and str(row['Phone']) != 'nan':
                phone = str(row['Phone']).strip()
            
            # Only add if we have at least name or company
            if lead_name or company:
                zoho_data.append({
                    'Lead Name': lead_name or 'Unknown',
                    'Company': company,
                    'Email': email,
                    'Phone': phone
                })
        
        # Create Zoho DataFrame
        zoho_df = pd.DataFrame(zoho_data)
        
        # Generate Zoho filename
        base_name = os.path.splitext(output_path)[0]
        zoho_excel_path = f"{base_name}_zoho.xlsx"
        zoho_csv_path = f"{base_name}_zoho.csv"
        
        # Save as both Excel and CSV
        zoho_df.to_excel(zoho_excel_path, index=False, engine='openpyxl')
        zoho_df.to_csv(zoho_csv_path, index=False, encoding='utf-8')
        
        logger.info(f"✅ Created Zoho exports: {len(zoho_data)} leads")
        
        return zoho_excel_path, zoho_csv_path
        
    except Exception as e:
        logger.error(f"Error creating Zoho export: {str(e)}")
        return None, None


@app.route('/download/<filename>')
def download_file(filename):
    """Download enriched file."""
    file_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
    
    if not os.path.exists(file_path):
        flash('File not found', 'error')
        return redirect(url_for('index'))
    
    return send_file(file_path, as_attachment=True)


@app.route('/download_zoho/<file_id>/<format>')
def download_zoho(file_id, format):
    """
    Download Zoho CRM formatted export.
    
    Args:
        file_id: Processing file ID
        format: 'excel' or 'csv'
    """
    try:
        # Get the original output filename
        if file_id not in progress_data or not progress_data[file_id].get('output_file'):
            flash('File not found or processing not complete', 'error')
            return redirect(url_for('index'))
        
        original_file = progress_data[file_id]['output_file']
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], original_file)
        
        # Create Zoho export if not already exists
        base_name = os.path.splitext(output_path)[0]
        zoho_excel_path = f"{base_name}_zoho.xlsx"
        zoho_csv_path = f"{base_name}_zoho.csv"
        
        # Check if Zoho files exist, if not create them
        if not os.path.exists(zoho_excel_path) or not os.path.exists(zoho_csv_path):
            zoho_excel_path, zoho_csv_path = _create_zoho_export(output_path)
            
            if not zoho_excel_path or not zoho_csv_path:
                flash('Error creating Zoho export', 'error')
                return redirect(url_for('progress', file_id=file_id))
        
        # Download requested format
        if format == 'csv':
            return send_file(zoho_csv_path, as_attachment=True, download_name=os.path.basename(zoho_csv_path))
        else:  # excel
            return send_file(zoho_excel_path, as_attachment=True, download_name=os.path.basename(zoho_excel_path))
            
    except Exception as e:
        logger.error(f"Error downloading Zoho export: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/view_contacts')
def view_contacts():
    """View all contacts in database with Zoho export options."""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 50
        search_query = request.args.get('search', '')
        
        # Get contacts from database
        result = db.get_all_contacts_paginated(page=page, per_page=per_page, search_query=search_query)
        
        # Get database stats
        stats = db.get_stats()
        
        # Check if Zoho is configured
        zoho_configured = all([
            os.getenv('ZOHO_CLIENT_ID'),
            os.getenv('ZOHO_CLIENT_SECRET'),
            os.getenv('ZOHO_REFRESH_TOKEN')
        ])
        
        return render_template('view_contacts_simple.html',
                             contacts=result['contacts'],
                             total=result['total'],
                             page=result['page'],
                             per_page=result['per_page'],
                             total_pages=result['total_pages'],
                             has_prev=result['has_prev'],
                             has_next=result['has_next'],
                             search_query=search_query,
                             stats=stats,
                             zoho_configured=zoho_configured)
    except Exception as e:
        logger.error(f"Error viewing contacts: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/export_database_zoho')
def export_database_zoho():
    """
    Export all database contacts in Zoho CRM format.
    Creates Excel and CSV files from database.
    """
    try:
        # Get all contacts from database
        result = db.get_all_contacts_paginated(page=1, per_page=100000)  # Get all
        contacts = result['contacts']
        
        if not contacts:
            flash('No contacts in database to export', 'info')
            return redirect(url_for('view_contacts'))
        
        # Create Zoho-formatted data
        zoho_data = []
        
        for contact in contacts:
            # Get lead name: prefer contact name, fallback to email extraction
            lead_name = ''
            if contact.get('contact_name'):
                lead_name = contact['contact_name']
            elif contact.get('first_name'):
                first = contact.get('first_name', '').strip()
                last = contact.get('last_name', '').strip()
                lead_name = f"{first} {last}".strip()
            elif contact.get('email'):
                lead_name = _extract_name_from_email(contact['email'])
            
            # Get company name
            company = contact.get('company_name', '').strip()
            
            # Get email
            email = contact.get('email', '').strip()
            
            # Get phone: prefer WhatsApp, then Phone
            phone = contact.get('whatsapp', '').strip() or contact.get('phone', '').strip()
            
            # Only add if we have at least name or company
            if lead_name or company:
                zoho_data.append({
                    'Lead Name': lead_name or 'Unknown',
                    'Company': company,
                    'Email': email,
                    'Phone': phone
                })
        
        # Create DataFrame
        zoho_df = pd.DataFrame(zoho_data)
        
        # Generate filenames
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zoho_excel_path = os.path.join(app.config['OUTPUT_FOLDER'], f'database_export_zoho_{timestamp}.xlsx')
        zoho_csv_path = os.path.join(app.config['OUTPUT_FOLDER'], f'database_export_zoho_{timestamp}.csv')
        
        # Save both formats
        zoho_df.to_excel(zoho_excel_path, index=False, engine='openpyxl')
        zoho_df.to_csv(zoho_csv_path, index=False, encoding='utf-8')
        
        logger.info(f"✅ Exported {len(zoho_data)} contacts from database in Zoho format")
        
        # Store in session for download
        session['zoho_excel_file'] = os.path.basename(zoho_excel_path)
        session['zoho_csv_file'] = os.path.basename(zoho_csv_path)
        
        flash(f'Successfully exported {len(zoho_data)} contacts in Zoho format!', 'success')
        return redirect(url_for('view_contacts'))
        
    except Exception as e:
        logger.error(f"Error exporting database to Zoho format: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('view_contacts'))


@app.route('/download_database_export/<format>')
def download_database_export(format):
    """Download database Zoho export (Excel or CSV)."""
    try:
        if format == 'excel':
            filename = session.get('zoho_excel_file')
        else:  # csv
            filename = session.get('zoho_csv_file')
        
        if not filename:
            flash('No export file available. Please export first.', 'error')
            return redirect(url_for('view_contacts'))
        
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], filename)
        
        if not os.path.exists(file_path):
            flash('Export file not found', 'error')
            return redirect(url_for('view_contacts'))
        
        return send_file(file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        logger.error(f"Error downloading database export: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('view_contacts'))


@app.route('/zoho_config', methods=['GET', 'POST'])
def zoho_config():
    """Configure Zoho CRM integration."""
    if request.method == 'POST':
        # Save Zoho credentials
        zoho_client_id = request.form.get('zoho_client_id')
        zoho_client_secret = request.form.get('zoho_client_secret')
        zoho_refresh_token = request.form.get('zoho_refresh_token')
        zoho_api_domain = request.form.get('zoho_api_domain', 'https://www.zohoapis.com')
        
        # Store in environment or session (in production, use secure storage)
        os.environ['ZOHO_CLIENT_ID'] = zoho_client_id
        os.environ['ZOHO_CLIENT_SECRET'] = zoho_client_secret
        os.environ['ZOHO_REFRESH_TOKEN'] = zoho_refresh_token
        os.environ['ZOHO_API_DOMAIN'] = zoho_api_domain
        
        flash('Zoho CRM credentials saved successfully!', 'success')
        return redirect(url_for('view_contacts'))
    
    # GET - show configuration form
    return render_template('zoho_config.html',
                         zoho_client_id=os.getenv('ZOHO_CLIENT_ID', ''),
                         zoho_api_domain=os.getenv('ZOHO_API_DOMAIN', 'https://www.zohoapis.com'))


def _get_zoho_access_token():
    """Get Zoho CRM access token using refresh token."""
    try:
        client_id = os.getenv('ZOHO_CLIENT_ID')
        client_secret = os.getenv('ZOHO_CLIENT_SECRET')
        refresh_token = os.getenv('ZOHO_REFRESH_TOKEN')
        
        if not all([client_id, client_secret, refresh_token]):
            return None, "Zoho credentials not configured"
        
        # Get access token
        token_url = "https://accounts.zoho.com/oauth/v2/token"
        params = {
            'refresh_token': refresh_token,
            'client_id': client_id,
            'client_secret': client_secret,
            'grant_type': 'refresh_token'
        }
        
        response = requests.post(token_url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        access_token = data.get('access_token')
        
        if not access_token:
            return None, "Failed to get access token"
        
        return access_token, None
        
    except Exception as e:
        logger.error(f"Error getting Zoho access token: {str(e)}")
        return None, str(e)


@app.route('/push_to_zoho', methods=['POST'])
def push_to_zoho():
    """
    Push selected contacts from database to Zoho CRM.
    Can push all contacts or specific ones.
    """
    try:
        # Get access token
        access_token, error = _get_zoho_access_token()
        if error:
            flash(f'Zoho CRM not configured: {error}. Please configure Zoho integration first.', 'error')
            return redirect(url_for('zoho_config'))
        
        # Get contacts to push (all or selected)
        push_all = request.form.get('push_all') == 'true'
        
        if push_all:
            # Get all contacts from database
            result = db.get_all_contacts_paginated(page=1, per_page=100000)
            contacts = result['contacts']
        else:
            # Get selected contact IDs (if implementing selection)
            # For now, push all
            result = db.get_all_contacts_paginated(page=1, per_page=100000)
            contacts = result['contacts']
        
        if not contacts:
            flash('No contacts to push', 'info')
            return redirect(url_for('view_contacts'))
        
        # Prepare Zoho leads data
        zoho_leads = []
        
        for contact in contacts:
            # Get lead name
            lead_name = ''
            if contact.get('contact_name'):
                lead_name = contact['contact_name']
            elif contact.get('first_name'):
                first = contact.get('first_name', '').strip()
                last = contact.get('last_name', '').strip()
                lead_name = f"{first} {last}".strip()
            elif contact.get('email'):
                lead_name = _extract_name_from_email(contact['email'])
            
            # Split name for Zoho (requires First_Name and Last_Name)
            name_parts = lead_name.split() if lead_name else []
            first_name = name_parts[0] if name_parts else 'Unknown'
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
            
            # Prepare lead data
            lead_data = {
                'First_Name': first_name,
                'Last_Name': last_name or '.',  # Zoho requires Last_Name
                'Company': contact.get('company_name', 'Unknown'),
                'Email': contact.get('email', ''),
                'Phone': contact.get('whatsapp', '') or contact.get('phone', ''),
                'Lead_Source': 'Contact Enrichment System',
                'Description': f"Imported from database on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
            
            # Only add if we have minimum required data
            if lead_data['First_Name'] and lead_data['Company']:
                zoho_leads.append(lead_data)
        
        if not zoho_leads:
            flash('No valid contacts to push to Zoho', 'warning')
            return redirect(url_for('view_contacts'))
        
        # Push to Zoho CRM in batches (max 100 per request)
        api_domain = os.getenv('ZOHO_API_DOMAIN', 'https://www.zohoapis.com')
        zoho_api_url = f"{api_domain}/crm/v2/Leads"
        
        headers = {
            'Authorization': f'Zoho-oauthtoken {access_token}',
            'Content-Type': 'application/json'
        }
        
        total_pushed = 0
        total_failed = 0
        batch_size = 100
        
        for i in range(0, len(zoho_leads), batch_size):
            batch = zoho_leads[i:i+batch_size]
            
            payload = {
                'data': batch,
                'trigger': ['approval', 'workflow', 'blueprint']
            }
            
            response = requests.post(zoho_api_url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 201:
                result = response.json()
                success_count = len([d for d in result.get('data', []) if d.get('code') == 'SUCCESS'])
                total_pushed += success_count
                total_failed += len(batch) - success_count
                logger.info(f"✅ Pushed batch {i//batch_size + 1}: {success_count}/{len(batch)} successful")
            else:
                total_failed += len(batch)
                logger.error(f"❌ Failed to push batch {i//batch_size + 1}: {response.status_code} - {response.text}")
        
        if total_pushed > 0:
            flash(f'Successfully pushed {total_pushed} contacts to Zoho CRM! (Failed: {total_failed})', 'success')
        else:
            flash(f'Failed to push contacts to Zoho CRM. Check logs for details.', 'error')
        
        return redirect(url_for('view_contacts'))
        
    except Exception as e:
        logger.error(f"Error pushing to Zoho CRM: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('view_contacts'))


if __name__ == '__main__':
    # Check for SerpApi key
    if not os.getenv('SERPAPI_API_KEY'):
        print("\n" + "="*70)
        print("⚠️  WARNING: SERPAPI_API_KEY environment variable not set!")
        print("="*70)
        print("\nThe app will not work without a SerpApi API key.")
        print("Get one from: https://serpapi.com/users/sign_up")
        print("\nThen run:")
        print("  export SERPAPI_API_KEY='your-key-here'")
        print("  python app.py")
        print("\n" + "="*70 + "\n")
    else:
        print("\n" + "="*70)
        print("✅ SerpApi API key found")
        print("="*70)
        print("\n🚀 Starting Flask app...")
        print("📱 Open: http://127.0.0.1:5000")
        print("\n" + "="*70 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
