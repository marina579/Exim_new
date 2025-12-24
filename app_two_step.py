"""
Two-Step EXIM Contact Enricher:
Step 1: Clean & Standardize (deduplicate, format company names/addresses)
Step 2: Enrich Contacts (find phone, email, WhatsApp)
"""

import os
import uuid
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from werkzeug.utils import secure_filename
import pandas as pd
from hybrid_enricher import HybridEnricher

app = Flask(__name__)
app.secret_key = 'exim_contact_enricher_two_step_2024'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['CLEANED_FOLDER'] = 'cleaned'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB

# Create folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(app.config['CLEANED_FOLDER'], exist_ok=True)

# Progress tracking
progress_data = {}

# Allowed extensions
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'xlsm', 'xlsb'}

# Configuration
MAX_RECORDS_TO_PROCESS = None  # Process ALL records (set to 25 for testing)
COLLECT_ALL_CONTACTS = True  # Multi-row output
USE_GEMINI = False  # Disabled due to quota


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_and_standardize_excel(file_path, file_id):
    """
    Step 1: Clean, deduplicate, and standardize company data.
    Works with ANY Excel format - auto-detects Company Name and Address columns.
    """
    progress_data[file_id]['status'] = 'processing'
    progress_data[file_id]['message'] = 'Reading Excel file...'
    
    try:
        # Try multiple strategies to read Excel
        df = None
        company_col = None
        address_col = None
        
        # Strategy 1: Try different header rows
        for header_row in [0, 1, 2]:
            try:
                test_df = pd.read_excel(file_path, header=header_row, engine='openpyxl')
                
                # Look for company name column (case-insensitive, more specific)
                # Priority order: SELLER > SELLER NAME > COMPANY NAME > etc.
                priority_keywords = [
                    ['seller'],  # Highest priority - exact match
                    ['seller name'],
                    ['company name'],
                    ['exporter name', 'business name', 'firm name'],
                ]
                
                for keyword_group in priority_keywords:
                    for col in test_df.columns:
                        col_lower = str(col).lower().strip()
                        # Skip numeric or ID columns
                        if col_lower in ['id', 'shipment id', 'gstin', 'gst', 'pan', 'iec']:
                            continue
                        # Check if column matches any keyword in this group
                        if any(keyword == col_lower for keyword in keyword_group):
                            # Verify it has text data (not just numbers)
                            sample = test_df[col].dropna().head(10).astype(str)
                            if any(len(str(val)) > 3 and not str(val).replace(' ', '').isdigit() for val in sample):
                                company_col = col
                                break
                    if company_col:
                        break
                
                # Look for address column (priority: SELLER ADDRESS > COMPANY ADDRESS > ADDRESS)
                address_priority = ['seller address', 'company address', 'business address', 'address']
                for addr_keyword in address_priority:
                    for col in test_df.columns:
                        col_lower = str(col).lower().strip()
                        if addr_keyword == col_lower or addr_keyword in col_lower:
                            address_col = col
                            break
                    if address_col:
                        break
                
                if company_col:
                    df = test_df
                    progress_data[file_id]['message'] = f'Found columns: {company_col}, {address_col or "N/A"}'
                    break
                    
            except Exception as e:
                continue
        
        if df is None or company_col is None:
            progress_data[file_id]['status'] = 'error'
            progress_data[file_id]['message'] = 'Could not find Company Name column. Please ensure your Excel has a column with company names.'
            return
        
        progress_data[file_id]['message'] = 'Cleaning and standardizing data...'
        
        # Create cleaned dataset
        cleaned_df = pd.DataFrame()
        cleaned_df['Company Name'] = df[company_col].astype(str).str.strip()
        
        if address_col:
            cleaned_df['Company Address'] = df[address_col].astype(str).str.strip()
        else:
            cleaned_df['Company Address'] = ''
        
        # Remove invalid rows
        cleaned_df = cleaned_df[
            (cleaned_df['Company Name'] != 'nan') & 
            (cleaned_df['Company Name'] != '') &
            (cleaned_df['Company Name'].notna()) &
            (cleaned_df['Company Name'].str.len() > 2)  # At least 3 characters
        ]
        
        # Filter out rows that are just numbers (likely IDs, not company names)
        cleaned_df = cleaned_df[~cleaned_df['Company Name'].str.match(r'^\d+$', na=False)]
        
        # Filter out rows that look like GSTINs (15 digits starting with 2 numbers)
        cleaned_df = cleaned_df[~cleaned_df['Company Name'].str.match(r'^\d{15}$', na=False)]
        
        total_before = len(cleaned_df)
        progress_data[file_id]['total_original'] = total_before
        progress_data[file_id]['message'] = f'Found {total_before} companies...'
        
        # Remove duplicates (case-insensitive)
        cleaned_df['_name_lower'] = cleaned_df['Company Name'].str.lower()
        cleaned_df = cleaned_df.drop_duplicates(subset=['_name_lower'], keep='first')
        cleaned_df = cleaned_df.drop(columns=['_name_lower'])
        
        total_after = len(cleaned_df)
        duplicates_removed = total_before - total_after
        
        progress_data[file_id]['total_unique'] = total_after
        progress_data[file_id]['duplicates_removed'] = duplicates_removed
        progress_data[file_id]['message'] = f'Removed {duplicates_removed} duplicates. {total_after} unique companies.'
        
        # Filter for Indian addresses (if address column exists)
        if address_col and cleaned_df['Company Address'].notna().any():
            indian_keywords = ['india', 'mumbai', 'delhi', 'bangalore', 'kolkata', 'chennai',
                             'hyderabad', 'pune', 'ahmedabad', 'jaipur', 'lucknow', 'kanpur',
                             'west bengal', 'maharashtra', 'karnataka', 'tamil nadu', 'gujarat',
                             'rajasthan', 'uttar pradesh', 'telangana', 'kerala', 'punjab']
            
            cleaned_df = cleaned_df[
                cleaned_df['Company Address'].str.lower().str.contains('|'.join(indian_keywords), na=False)
            ]
            
            total_indian = len(cleaned_df)
            progress_data[file_id]['total_indian'] = total_indian
            progress_data[file_id]['message'] = f'Filtered to {total_indian} Indian companies.'
        
        # Save cleaned file
        output_filename = f'{file_id}_cleaned.xlsx'
        output_path = os.path.join(app.config['CLEANED_FOLDER'], output_filename)
        
        cleaned_df.to_excel(output_path, index=False, engine='openpyxl')
        
        progress_data[file_id]['status'] = 'complete'
        progress_data[file_id]['percentage'] = 100
        progress_data[file_id]['output_file'] = output_filename
        progress_data[file_id]['message'] = f'✅ Cleaning complete! {len(cleaned_df)} companies ready for enrichment.'
        
    except Exception as e:
        progress_data[file_id]['status'] = 'error'
        progress_data[file_id]['message'] = f'Error cleaning file: {str(e)}'
        import traceback
        print(f"Error details: {traceback.format_exc()}")


def enrich_contacts(file_path, file_id):
    """
    Step 2: Enrich with contact information (phone, email, WhatsApp).
    """
    progress_data[file_id]['status'] = 'processing'
    progress_data[file_id]['message'] = 'Initializing enrichment...'
    
    try:
        # Read cleaned file
        df = pd.read_excel(file_path, engine='openpyxl')
        
        if 'Company Name' not in df.columns:
            progress_data[file_id]['status'] = 'error'
            progress_data[file_id]['message'] = 'Invalid file format. Please upload the cleaned file from Step 1.'
            return
        
        total = len(df)
        if MAX_RECORDS_TO_PROCESS:
            total = min(total, MAX_RECORDS_TO_PROCESS)
            df = df.head(MAX_RECORDS_TO_PROCESS)
        
        progress_data[file_id]['total_unique'] = total
        progress_data[file_id]['message'] = f'Processing {total} companies...'
        
        # Initialize enricher
        serpapi_key = os.getenv('SERPAPI_API_KEY')
        openai_key = os.getenv('OPENAI_API_KEY')
        gemini_key = os.getenv('GEMINI_API_KEY') if USE_GEMINI else None
        
        if not serpapi_key:
            progress_data[file_id]['status'] = 'error'
            progress_data[file_id]['message'] = 'SerpApi API key not found.'
            return
        
        enricher = HybridEnricher(
            serpapi_key=serpapi_key,
            openai_key=openai_key,
            gemini_key=gemini_key,
            collect_all=COLLECT_ALL_CONTACTS
        )
        
        # Enrich each company
        results = []
        stats = {'phone': 0, 'email': 0, 'whatsapp': 0, 'total_contacts': 0}
        
        for idx, row in df.iterrows():
            if idx >= total:
                break
            
            company_name = str(row['Company Name']).strip()
            company_addr = str(row.get('Company Address', '')).strip()
            
            progress_data[file_id]['current'] = idx + 1
            progress_data[file_id]['percentage'] = int((idx + 1) / total * 100)
            progress_data[file_id]['current_seller'] = company_name
            progress_data[file_id]['message'] = f'Processing: {company_name}'
            
            # Enrich contacts
            if COLLECT_ALL_CONTACTS:
                contacts = enricher.enrich_contact_all(company_name, company_addr)
                
                if contacts:
                    for contact in contacts:
                        phone = contact.get('phone', '').strip()
                        email = contact.get('email', '').strip()
                        whatsapp = contact.get('whatsapp', '').strip()
                        contact_name = contact.get('contact_name', '').strip()
                        
                        # Split name into first and last
                        if contact_name:
                            name_parts = contact_name.split()
                            first_name = name_parts[0] if name_parts else ''
                            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
                        else:
                            first_name = ''
                            last_name = ''
                        
                        if phone:
                            stats['phone'] += 1
                        if email:
                            stats['email'] += 1
                        if whatsapp:
                            stats['whatsapp'] += 1
                        
                        # CRM-ready format
                        results.append({
                            'Lead Name': contact_name,
                            'First Name': first_name,
                            'Last Name': last_name,
                            'Company': company_name,
                            'Email': email,
                            'Phone': phone,
                            'Mobile': phone,  # Duplicate for CRM compatibility
                            'Lead Source': contact.get('method', '').replace('_', ' ').title(),
                            'Lead Owner': 'Auto Import',  # Can be customized
                            'Description': f"Address: {company_addr}",
                            'Website': contact.get('source_url', ''),
                            'WhatsApp': whatsapp
                        })
                    stats['total_contacts'] += len(contacts)
                else:
                    # No contacts found - create empty row
                    results.append({
                        'Lead Name': '',
                        'First Name': '',
                        'Last Name': '',
                        'Company': company_name,
                        'Email': '',
                        'Phone': '',
                        'Mobile': '',
                        'Lead Source': 'Not Found',
                        'Lead Owner': 'Auto Import',
                        'Description': f"Address: {company_addr}",
                        'Website': '',
                        'WhatsApp': ''
                    })
        
        # Save enriched file
        output_filename = f'{file_id}_enriched.xlsx'
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        results_df = pd.DataFrame(results)
        results_df.to_excel(output_path, index=False, engine='openpyxl')
        
        progress_data[file_id]['status'] = 'complete'
        progress_data[file_id]['percentage'] = 100
        progress_data[file_id]['output_file'] = output_filename
        progress_data[file_id]['stats'] = stats
        progress_data[file_id]['message'] = f'✅ Enrichment complete! Found {stats["phone"]} phones, {stats["email"]} emails.'
        
    except Exception as e:
        progress_data[file_id]['status'] = 'error'
        progress_data[file_id]['message'] = f'Error enriching file: {str(e)}'
        import traceback
        print(f"Error details: {traceback.format_exc()}")


@app.route('/')
def index():
    """Home page - Step 1: Clean & Deduplicate."""
    return render_template('index_two_step.html', step=1)


@app.route('/step2')
def step2():
    """Step 2 page - Enrich Contacts."""
    return render_template('index_two_step.html', step=2)


@app.route('/upload_step1', methods=['POST'])
def upload_step1():
    """Handle Step 1 file upload (Clean & Deduplicate)."""
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
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_{filename}')
        
        file.save(upload_path)
        
        # Initialize progress
        progress_data[file_id] = {
            'status': 'uploaded',
            'message': 'File uploaded. Starting cleaning...',
            'step': 1,
            'filename': filename,
            'percentage': 0
        }
        
        # Start background processing
        thread = threading.Thread(target=clean_and_standardize_excel, args=(upload_path, file_id))
        thread.daemon = True
        thread.start()
        
        return redirect(url_for('progress', file_id=file_id, step=1))
        
    except Exception as e:
        flash(f'Error uploading file: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/upload_step2', methods=['POST'])
def upload_step2():
    """Handle Step 2 file upload (Enrich Contacts)."""
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('step2'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('step2'))
    
    if not allowed_file(file.filename):
        flash('Invalid file type. Please upload .xlsx or .xls file', 'error')
        return redirect(url_for('step2'))
    
    try:
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_{filename}')
        
        file.save(upload_path)
        
        # Initialize progress
        progress_data[file_id] = {
            'status': 'uploaded',
            'message': 'File uploaded. Starting enrichment...',
            'step': 2,
            'filename': filename,
            'percentage': 0
        }
        
        # Start background processing
        thread = threading.Thread(target=enrich_contacts, args=(upload_path, file_id))
        thread.daemon = True
        thread.start()
        
        return redirect(url_for('progress', file_id=file_id, step=2))
        
    except Exception as e:
        flash(f'Error uploading file: {str(e)}', 'error')
        return redirect(url_for('step2'))


@app.route('/progress/<file_id>/<int:step>')
def progress(file_id, step):
    """Show progress page."""
    return render_template('progress_two_step.html', file_id=file_id, step=step)


@app.route('/api/progress/<file_id>')
def api_progress(file_id):
    """API endpoint for progress updates."""
    if file_id not in progress_data:
        return jsonify({'error': 'File ID not found'}), 404
    
    return jsonify(progress_data[file_id])


@app.route('/download/<file_id>/<int:step>')
def download(file_id, step):
    """Download processed file."""
    if file_id not in progress_data:
        flash('File not found', 'error')
        return redirect(url_for('index'))
    
    output_filename = progress_data[file_id].get('output_file')
    if not output_filename:
        flash('Output file not ready', 'error')
        return redirect(url_for('index'))
    
    if step == 1:
        output_path = os.path.join(app.config['CLEANED_FOLDER'], output_filename)
    else:
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
    
    return send_file(output_path, as_attachment=True, download_name=output_filename)


if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚀 EXIM CONTACT ENRICHER - TWO-STEP PROCESS")
    print("="*70)
    print("\nStep 1: Clean & Deduplicate → http://127.0.0.1:5000")
    print("Step 2: Enrich Contacts → http://127.0.0.1:5000/step2")
    print("\n" + "="*70 + "\n")
    
    app.run(debug=True, host='127.0.0.1', port=5000)

