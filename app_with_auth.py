"""
Marineco AI Chatbot
Advanced contact enrichment system with AI chatbot and duplicate detection.
"""

import os
import uuid
import threading
import time
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import pandas as pd
import requests
from dotenv import load_dotenv
from hybrid_enricher import HybridEnricher
from database import db
from zoho_crm_service import ZohoCRMService

# Auto-push to Zoho configuration
AUTO_PUSH_TO_ZOHO = os.getenv('AUTO_PUSH_TO_ZOHO', 'true').lower() == 'true'
from automated_processor import process_file_automated

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'marineco_exim_contact_finder_secure_2024_auth_key')  # Change in production!
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['OUTPUT_FOLDER'] = 'outputs'
app.config['CLEANED_FOLDER'] = 'cleaned'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Create folders
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
os.makedirs(app.config['CLEANED_FOLDER'], exist_ok=True)

# Progress tracking
progress_data = {}

# Allowed extensions
ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'xlsm', 'xlsb'}

# Configuration
MAX_RECORDS_TO_PROCESS = None  # Process ALL records

# ⚡ MODE SELECTION:
# FREE_MODE: All FREE methods (ChatGPT, WhatsApp Hunter, IndiaMART) - NO SerpAPI
# PAID_MODE: Includes SerpAPI + all other methods
USE_FREE_MODE = False  # Set to False to enable SerpAPI (NEW KEY PROVIDED!)

COLLECT_ALL_CONTACTS = True  # Collect ALL contacts from ALL methods (multiple contacts per company)
USE_GEMINI = bool(os.getenv('GEMINI_API_KEY') and os.getenv('GEMINI_API_KEY') != 'YOUR_GEMINI_API_KEY_HERE')  # Auto-enable if key is set

# ⚡ SPEED OPTIMIZATION (for FREE MODE)
# Reduces delays and timeouts for faster processing
SPEED_OPTIMIZED = True  # Set to True for 2x faster processing

# ==================== AUTHENTICATION ====================

# Authentication is now handled by database (see database.py)
# Default admin user is created automatically:
#   Username: admin
#   Password: admin123
# Change the password after first login!

def login_required(f):
    """Decorator to require login for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page with database authentication."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Verify credentials using database
        user = db.verify_user(username, password)
        
        if user:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['is_admin'] = user['is_admin']
            session['login_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            flash(f'Welcome back, {user["full_name"] or username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password, or account is inactive', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout user."""
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('login'))


# ==================== USER MANAGEMENT ====================

@app.route('/admin/users')
@login_required
def admin_users():
    """Admin panel for user management."""
    if not session.get('is_admin'):
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    users = db.get_all_users()
    return render_template('admin_users.html', users=users, username=session.get('username'))


@app.route('/admin/users/create', methods=['POST'])
@login_required
def admin_create_user():
    """Create a new user (admin only)."""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    is_admin = request.form.get('is_admin') == 'on'
    
    if not username or not password:
        flash('Username and password are required', 'error')
        return redirect(url_for('admin_users'))
    
    if len(password) < 6:
        flash('Password must be at least 6 characters', 'error')
        return redirect(url_for('admin_users'))
    
    result = db.create_user(
        username=username,
        password=password,
        full_name=full_name,
        email=email,
        is_admin=is_admin,
        created_by_id=session.get('user_id')
    )
    
    flash(result['message'], 'success' if result['success'] else 'error')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@login_required
def admin_toggle_user(user_id):
    """Toggle user active/inactive status (admin only)."""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    # Prevent admin from deactivating themselves
    if user_id == session.get('user_id'):
        return jsonify({'success': False, 'message': 'Cannot deactivate your own account'}), 400
    
    result = db.toggle_user_status(user_id)
    return jsonify(result)


@app.route('/admin/users/<int:user_id>/reset-password', methods=['POST'])
@login_required
def admin_reset_password(user_id):
    """Reset user password (admin only)."""
    if not session.get('is_admin'):
        return jsonify({'success': False, 'message': 'Access denied'}), 403
    
    new_password = request.form.get('new_password', '').strip()
    
    if not new_password or len(new_password) < 6:
        return jsonify({'success': False, 'message': 'Password must be at least 6 characters'}), 400
    
    result = db.admin_reset_password(user_id, new_password)
    return jsonify(result)


@app.route('/profile/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change own password - Admins use Admin Panel, regular users redirected."""
    if request.method == 'POST':
        old_password = request.form.get('old_password', '').strip()
        new_password = request.form.get('new_password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()
        
        if not old_password or not new_password or not confirm_password:
            flash('All fields are required', 'error')
            return redirect(url_for('admin_users') if session.get('is_admin') else url_for('index'))
        
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('admin_users') if session.get('is_admin') else url_for('index'))
        
        if len(new_password) < 6:
            flash('New password must be at least 6 characters', 'error')
            return redirect(url_for('admin_users') if session.get('is_admin') else url_for('index'))
        
        result = db.change_password(
            user_id=session.get('user_id'),
            old_password=old_password,
            new_password=new_password
        )
        
        flash(result['message'], 'success' if result['success'] else 'error')
        
        if result['success']:
            return redirect(url_for('admin_users') if session.get('is_admin') else url_for('index'))
        else:
            return redirect(url_for('admin_users') if session.get('is_admin') else url_for('index'))
    
    # GET request - redirect to appropriate page
    if session.get('is_admin'):
        flash('Use the Admin Panel to change your password', 'info')
        return redirect(url_for('admin_users'))
    else:
        flash('Password change feature is available in Admin Panel (admin only)', 'info')
        return redirect(url_for('index'))

# ==================== UTILITY FUNCTIONS ====================

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def clean_and_standardize_excel(file_path, file_id):
    """Step 1: Clean, deduplicate, and standardize company data."""
    progress_data[file_id]['status'] = 'processing'
    progress_data[file_id]['message'] = 'Reading Excel file...'
    
    try:
        df = None
        company_col = None
        address_col = None
        
        # Try different header rows
        for header_row in [0, 1, 2]:
            try:
                test_df = pd.read_excel(file_path, header=header_row, engine='openpyxl')
                
                # Look for company name column with priority
                priority_keywords = [
                    ['seller'],
                    ['seller name'],
                    ['company name'],
                    ['exporter name', 'business name', 'firm name'],
                ]
                
                for keyword_group in priority_keywords:
                    for col in test_df.columns:
                        col_lower = str(col).lower().strip()
                        if col_lower in ['id', 'shipment id', 'gstin', 'gst', 'pan', 'iec']:
                            continue
                        if any(keyword == col_lower for keyword in keyword_group):
                            sample = test_df[col].dropna().head(10).astype(str)
                            if any(len(str(val)) > 3 and not str(val).replace(' ', '').isdigit() for val in sample):
                                company_col = col
                                break
                    if company_col:
                        break
                
                # Look for address column
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
            progress_data[file_id]['message'] = 'Could not find Company Name column.'
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
            (cleaned_df['Company Name'].str.len() > 2)
        ]
        
        # Filter out numbers and GSTINs
        cleaned_df = cleaned_df[~cleaned_df['Company Name'].str.match(r'^\d+$', na=False)]
        cleaned_df = cleaned_df[~cleaned_df['Company Name'].str.match(r'^\d{15}$', na=False)]
        
        total_before = len(cleaned_df)
        progress_data[file_id]['total_original'] = total_before
        
        # Remove duplicates
        cleaned_df['_name_lower'] = cleaned_df['Company Name'].str.lower()
        cleaned_df = cleaned_df.drop_duplicates(subset=['_name_lower'], keep='first')
        cleaned_df = cleaned_df.drop(columns=['_name_lower'])
        
        total_after = len(cleaned_df)
        duplicates_removed = total_before - total_after
        progress_data[file_id]['duplicates_removed'] = duplicates_removed
        
        # Filter for Indian addresses
        if address_col and cleaned_df['Company Address'].notna().any():
            indian_keywords = ['india', 'mumbai', 'delhi', 'bangalore', 'kolkata', 'chennai',
                             'hyderabad', 'pune', 'ahmedabad', 'jaipur', 'lucknow', 'kanpur',
                             'west bengal', 'maharashtra', 'karnataka', 'tamil nadu', 'gujarat',
                             'rajasthan', 'uttar pradesh', 'telangana', 'kerala', 'punjab']
            
            cleaned_df = cleaned_df[
                cleaned_df['Company Address'].str.lower().str.contains('|'.join(indian_keywords), na=False)
            ]
        
        progress_data[file_id]['total_unique'] = len(cleaned_df)
        
        # Save cleaned file
        output_filename = f'{file_id}_cleaned.xlsx'
        output_path = os.path.join(app.config['CLEANED_FOLDER'], output_filename)
        cleaned_df.to_excel(output_path, index=False, engine='openpyxl')
        
        progress_data[file_id]['status'] = 'complete'
        progress_data[file_id]['percentage'] = 100
        progress_data[file_id]['output_file'] = output_filename
        progress_data[file_id]['message'] = f'✅ Cleaning complete! {len(cleaned_df)} companies ready.'
        
    except Exception as e:
        progress_data[file_id]['status'] = 'error'
        progress_data[file_id]['message'] = f'Error: {str(e)}'


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
        # Get contacts from database (they were just saved) with their IDs
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


def enrich_contacts(file_path, file_id):
    """Step 2: Enrich with contact information."""
    progress_data[file_id]['status'] = 'processing'
    progress_data[file_id]['message'] = 'Initializing enrichment...'
    
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
        
        if 'Company Name' not in df.columns:
            progress_data[file_id]['status'] = 'error'
            progress_data[file_id]['message'] = 'Invalid file format.'
            return
        
        total = len(df)
        if MAX_RECORDS_TO_PROCESS:
            total = min(total, MAX_RECORDS_TO_PROCESS)
            df = df.head(MAX_RECORDS_TO_PROCESS)
        
        progress_data[file_id]['total_unique'] = total
        
        # Initialize enricher
        serpapi_key = os.getenv('SERPAPI_API_KEY')
        openai_key = os.getenv('OPENAI_API_KEY')
        gemini_key = os.getenv('GEMINI_API_KEY') if USE_GEMINI else None
        
        if not serpapi_key:
            progress_data[file_id]['status'] = 'error'
            progress_data[file_id]['message'] = 'SerpApi API key not found.'
            return
        
        # Set speed optimization environment variable
        if SPEED_OPTIMIZED:
            os.environ['SPEED_OPTIMIZED'] = 'true'
        
        # Initialize enricher based on mode
        if USE_FREE_MODE:
            # 🆓 FREE MODE: All FREE methods (NO SerpAPI)
            # Uses: ChatGPT, WhatsApp Hunter, WhatsApp Detective, IndiaMART
            enricher = HybridEnricher(
                serpapi_key=None,  # ❌ Disable SerpAPI (trial over)
                openai_key=openai_key,
                gemini_key=gemini_key if USE_GEMINI else None,
                collect_all=COLLECT_ALL_CONTACTS  # Try all methods
            )
            # All free methods are enabled by default
            mode_desc = 'FREE (ChatGPT + WhatsApp Hunter + IndiaMART)'
            if SPEED_OPTIMIZED:
                mode_desc += ' - OPTIMIZED'
            progress_data[file_id]['mode'] = mode_desc
        else:
            # 💰 PAID MODE: All methods including SerpAPI
            enricher = HybridEnricher(
                serpapi_key=serpapi_key,
                openai_key=openai_key,
                gemini_key=gemini_key if USE_GEMINI else None,
                collect_all=COLLECT_ALL_CONTACTS
            )
            progress_data[file_id]['mode'] = 'PAID (All methods including SerpAPI)'
        
        # Enrich each company
        results = []
        stats = {'phone': 0, 'email': 0, 'whatsapp': 0, 'cached': 0, 'processed': 0}
        
        for idx, row in df.iterrows():
            if idx >= total:
                break
            
            company_name = str(row['Company Name']).strip()
            company_addr = str(row.get('Company Address', '')).strip()
            
            progress_data[file_id]['current'] = idx + 1
            progress_data[file_id]['percentage'] = int((idx + 1) / total * 100)
            progress_data[file_id]['current_seller'] = company_name
            
            # 🔍 CHECK CACHE FIRST (avoid re-processing)
            company_id = db.check_company_exists(company_name)
            
            if company_id:
                # ✅ Found in database - use cached contacts
                progress_data[file_id]['message'] = f'💾 Using cached data for: {company_name}'
                contacts = db.get_company_contacts(company_id)
                stats['cached'] += 1
            else:
                # ❌ Not in database - process now
                progress_data[file_id]['message'] = f'🔍 Processing: {company_name}'
                stats['processed'] += 1
                
                # Get contacts from all available methods
                if COLLECT_ALL_CONTACTS:
                    contacts = enricher.enrich_contact_all(company_name, company_addr)
                else:
                    contact_result = enricher.enrich_contact(company_name, company_addr)
                    contacts = [contact_result] if contact_result.get('phone') or contact_result.get('email') else []
                
                # 💾 Save to database for future use
                if contacts:
                    try:
                        company_id = db.save_company_and_contacts(company_name, company_addr, contacts)
                        # Auto-push to Zoho if enabled and configured
                        auto_push = os.getenv('AUTO_PUSH_TO_ZOHO', 'true').lower() == 'true'
                        if auto_push:
                            try:
                                _auto_push_contacts_to_zoho(company_id, company_name, contacts)
                            except Exception as e:
                                logger.warning(f"⚠️  Auto-push to Zoho failed for {company_name}: {str(e)}")
                    except Exception as e:
                        logger.error(f"Failed to save to database: {str(e)}")
            
            if contacts:
                for contact in contacts:
                    phone = contact.get('phone', '').strip()
                    email = contact.get('email', '').strip()
                    whatsapp = contact.get('whatsapp', '').strip()
                    contact_name = contact.get('contact_name', '').strip()
                    
                    # Split name
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
                    
                    results.append({
                        'Lead Name': contact_name,
                        'First Name': first_name,
                        'Last Name': last_name,
                        'Company': company_name,
                        'Email': email,
                        'Phone': phone,
                        'Mobile': phone,
                        'Lead Source': contact.get('method', '').replace('_', ' ').title(),
                        'Lead Owner': 'Auto Import',
                        'Description': f"Address: {company_addr}",
                        'Website': contact.get('source_url', ''),
                        'WhatsApp': whatsapp
                    })
            else:
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
        
        # Get database stats
        db_stats = db.get_stats()
        
        progress_data[file_id]['status'] = 'complete'
        progress_data[file_id]['percentage'] = 100
        progress_data[file_id]['output_file'] = output_filename
        progress_data[file_id]['stats'] = stats
        progress_data[file_id]['db_stats'] = db_stats
        progress_data[file_id]['message'] = f'✅ Complete! Found {stats["phone"]} phones, {stats["email"]} emails. (💾 Cached: {stats["cached"]}, 🔍 Processed: {stats["processed"]})'
        
    except Exception as e:
        progress_data[file_id]['status'] = 'error'
        progress_data[file_id]['message'] = f'Error: {str(e)}'


# ==================== ROUTES ====================

@app.route('/')
@login_required
def index():
    """Home page with tabs - Auto Upload and Manual Process."""
    tab = request.args.get('tab', 'auto')  # Default to auto upload
    step = request.args.get('step', 1, type=int)  # Manual step (1 or 2)
    
    return render_template('index_two_step.html', tab=tab, step=step, username=session.get('username'))


@app.route('/step2')
@login_required
def step2():
    """Step 2 page - redirect to manual tab step 2."""
    return redirect(url_for('index', tab='manual', step=2))


@app.route('/test-gemini')
def test_gemini():
    """Test endpoint to verify Gemini API is working."""
    try:
        from gemini_enricher import GeminiEnricher
        
        # Check if API key is set
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            return jsonify({
                'status': 'error',
                'message': 'GEMINI_API_KEY not found in environment variables',
                'key_present': False
            }), 500
        
        # Initialize enricher
        try:
            enricher = GeminiEnricher(api_key=api_key)
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Failed to initialize GeminiEnricher: {str(e)}',
                'error_type': type(e).__name__
            }), 500
        
        # Test with a simple company
        test_company = "Tata Consultancy Services"
        test_address = "Mumbai, India"
        
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"🧪 Testing Gemini with: {test_company}")
        
        try:
            result = enricher.find_contact(test_company, test_address)
            
            return jsonify({
                'status': 'success',
                'message': 'Gemini API is working!',
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
            
            if "401" in error_msg or "Unauthorized" in error_msg or "API key" in error_msg.lower():
                error_details['diagnosis'] = 'Invalid or expired API key'
            elif "429" in error_msg or "rate limit" in error_msg.lower() or "quota" in error_msg.lower():
                error_details['diagnosis'] = 'Rate limit exceeded or quota exhausted'
            elif "timeout" in error_msg.lower():
                error_details['diagnosis'] = 'Request timeout'
            elif "network" in error_msg.lower() or "connection" in error_msg.lower():
                error_details['diagnosis'] = 'Network connectivity issue'
            else:
                error_details['diagnosis'] = 'Unknown error - check logs'
            
            return jsonify({
                'status': 'error',
                'message': 'Gemini API call failed',
                **error_details
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Test endpoint error: {str(e)}',
            'error_type': type(e).__name__
        }), 500


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
        
        import logging
        logger = logging.getLogger(__name__)
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


@app.route('/chatbot')
@login_required
def chatbot():
    """Chatbot page for instant contact lookup."""
    return render_template('chatbot.html', username=session.get('username'))


@app.route('/contacts')
@app.route('/view_contacts')
@login_required
def view_contacts():
    """View all contacts from database with pagination, search, date filtering, and Zoho export."""
    import logging
    from datetime import datetime, timedelta
    logger = logging.getLogger(__name__)
    
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search_query = request.args.get('search', '', type=str).strip()
        date_filter = request.args.get('date_filter', 'all', type=str)
        
        # Calculate date range based on filter
        start_date = None
        end_date = None
        
        if date_filter == 'today':
            start_date = datetime.now().strftime('%Y-%m-%d 00:00:00')
            end_date = datetime.now().strftime('%Y-%m-%d 23:59:59')
        elif date_filter == 'yesterday':
            yesterday = datetime.now() - timedelta(days=1)
            start_date = yesterday.strftime('%Y-%m-%d 00:00:00')
            end_date = yesterday.strftime('%Y-%m-%d 23:59:59')
        elif date_filter == 'week':
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
            end_date = datetime.now().strftime('%Y-%m-%d 23:59:59')
        elif date_filter == 'month':
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d 00:00:00')
            end_date = datetime.now().strftime('%Y-%m-%d 23:59:59')
        elif date_filter == 'custom':
            start_date = request.args.get('start_date')
            end_date = request.args.get('end_date')
            if start_date:
                start_date = start_date + ' 00:00:00'
            if end_date:
                end_date = end_date + ' 23:59:59'
        
        data = db.get_all_contacts_paginated(
            page, per_page, 
            search_query if search_query else None,
            start_date=start_date,
            end_date=end_date
        )
        stats = db.get_stats()
        
        # Check if Zoho is configured
        zoho_configured = all([
            os.getenv('ZOHO_CLIENT_ID'),
            os.getenv('ZOHO_CLIENT_SECRET'),
            os.getenv('ZOHO_REFRESH_TOKEN')
        ])
        
        # Use the simpler template with Zoho support
        return render_template('view_contacts_simple.html', 
                             contacts=data['contacts'],
                             page=data['page'],
                             per_page=data['per_page'],
                             total=data['total'],
                             total_pages=data['total_pages'],
                             has_prev=data['has_prev'],
                             has_next=data['has_next'],
                             stats=stats,
                             search_query=search_query,
                             zoho_configured=zoho_configured,
                             username=session.get('username'))
    except Exception as e:
        logger.error(f"Error viewing contacts: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/api/search_company', methods=['POST'])
@login_required
def search_company():
    """API endpoint to search for company in database or trigger AI analysis."""
    data = request.get_json()
    company_name = data.get('company_name', '').strip()
    
    if not company_name:
        return jsonify({'error': 'Company name is required'}), 400
    
    # Check if company exists in database
    company_id = db.check_company_exists(company_name)
    
    if company_id:
        # Found in database
        contacts = db.get_company_contacts(company_id)
        return jsonify({
            'status': 'found',
            'company_name': company_name,
            'contacts': contacts,
            'source': 'database'
        })
    else:
        # Not found - return option to process
        return jsonify({
            'status': 'not_found',
            'company_name': company_name,
            'message': 'Company not found in database. Would you like to run AI analysis?'
        })


@app.route('/api/process_company', methods=['POST'])
@login_required
def process_company():
    """Process a single company with AI enrichment."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'error', 'message': 'Invalid JSON data'}), 400
            
        company_name = data.get('company_name', '').strip()
        company_address = data.get('company_address', '').strip()
        
        if not company_name:
            return jsonify({'status': 'error', 'message': 'Company name is required'}), 400
        
        # Initialize enricher
        serpapi_key = os.getenv('SERPAPI_API_KEY')
        openai_key = os.getenv('OPENAI_API_KEY')
        gemini_key = os.getenv('GEMINI_API_KEY') if USE_GEMINI else None
        
        # Log API key status for debugging
        logger.info(f"🔑 API Keys Status:")
        logger.info(f"   SerpAPI: {'✅ Set' if serpapi_key else '❌ Missing'} ({serpapi_key[:10] + '...' if serpapi_key else 'N/A'})")
        logger.info(f"   OpenAI: {'✅ Set' if openai_key else '❌ Missing'}")
        logger.info(f"   Gemini: {'✅ Set' if gemini_key else '❌ Missing'}")
        logger.info(f"   USE_FREE_MODE: {USE_FREE_MODE}")
        
        if USE_FREE_MODE:
            logger.warning("⚠️  FREE MODE: SerpAPI disabled")
            enricher = HybridEnricher(
                serpapi_key=None,
                openai_key=openai_key,
                gemini_key=gemini_key,
                collect_all=COLLECT_ALL_CONTACTS
            )
        else:
            logger.info("✅ PAID MODE: SerpAPI enabled")
            enricher = HybridEnricher(
                serpapi_key=serpapi_key,
                openai_key=openai_key,
                gemini_key=gemini_key,
                collect_all=COLLECT_ALL_CONTACTS
            )
        
        # Verify SerpAPI is initialized
        if enricher.serpapi:
            logger.info("✅ SerpAPI enricher initialized successfully")
        else:
            logger.warning("⚠️  SerpAPI enricher NOT initialized - check SERPAPI_API_KEY")
        
        # Process company
        if COLLECT_ALL_CONTACTS:
            contacts = enricher.enrich_contact_all(company_name, company_address)
        else:
            contact_result = enricher.enrich_contact(company_name, company_address)
            contacts = [contact_result] if contact_result.get('phone') or contact_result.get('email') else []
        
        # Save to database
        if contacts:
            company_id = db.save_company_and_contacts(company_name, company_address, contacts)
            
            # Auto-push to Zoho if enabled and configured
            auto_push = os.getenv('AUTO_PUSH_TO_ZOHO', 'true').lower() == 'true'
            if auto_push:
                try:
                    _auto_push_contacts_to_zoho(company_id, company_name, contacts)
                except Exception as e:
                    logger.warning(f"⚠️  Auto-push to Zoho failed for {company_name}: {str(e)}")
            
            return jsonify({
                'status': 'success',
                'company_name': company_name,
                'contacts': contacts,
                'source': 'ai_analysis'
            })
        else:
            return jsonify({
                'status': 'no_results',
                'company_name': company_name,
                'message': 'No contacts found for this company.'
            })
    
    except Exception as e:
        logger.error(f"Error processing company: {str(e)}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/upload_step1', methods=['POST'])
@login_required
def upload_step1():
    """Handle Step 1 file upload."""
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('index'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('index'))
    
    if not allowed_file(file.filename):
        flash('Invalid file type', 'error')
        return redirect(url_for('index'))
    
    try:
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_{filename}')
        
        file.save(upload_path)
        
        progress_data[file_id] = {
            'status': 'uploaded',
            'message': 'File uploaded. Starting cleaning...',
            'step': 1,
            'filename': filename,
            'percentage': 0,
            'user': session.get('username')
        }
        
        thread = threading.Thread(target=clean_and_standardize_excel, args=(upload_path, file_id))
        thread.daemon = True
        thread.start()
        
        return redirect(url_for('progress', file_id=file_id, step=1))
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/upload_step2', methods=['POST'])
@login_required
def upload_step2():
    """Handle Step 2 file upload."""
    if 'file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('step2'))
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('step2'))
    
    if not allowed_file(file.filename):
        flash('Invalid file type', 'error')
        return redirect(url_for('step2'))
    
    try:
        filename = secure_filename(file.filename)
        file_id = str(uuid.uuid4())
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{file_id}_{filename}')
        
        file.save(upload_path)
        
        progress_data[file_id] = {
            'status': 'uploaded',
            'message': 'File uploaded. Starting enrichment...',
            'step': 2,
            'filename': filename,
            'percentage': 0,
            'user': session.get('username')
        }
        
        thread = threading.Thread(target=enrich_contacts, args=(upload_path, file_id))
        thread.daemon = True
        thread.start()
        
        return redirect(url_for('progress', file_id=file_id, step=2))
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('step2'))


@app.route('/progress/<file_id>/<int:step>')
@login_required
def progress(file_id, step):
    """Show progress page."""
    return render_template('progress_two_step.html', file_id=file_id, step=step)


@app.route('/api/progress/<file_id>')
@login_required
def api_progress(file_id):
    """API endpoint for progress updates."""
    if file_id not in progress_data:
        return jsonify({'error': 'File ID not found'}), 404
    
    return jsonify(progress_data[file_id])


@app.route('/download/<file_id>/<int:step>')
@login_required
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


# ==================== ZOHO CRM INTEGRATION ====================

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
    import logging
    logger = logging.getLogger(__name__)
    
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


@app.route('/download_zoho/<file_id>/<format>')
@login_required
def download_zoho(file_id, format):
    """
    Download Zoho CRM formatted export.
    
    Args:
        file_id: Processing file ID
        format: 'excel' or 'csv'
    """
    import logging
    logger = logging.getLogger(__name__)
    
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


@app.route('/export_database_zoho')
@login_required
def export_database_zoho():
    """
    Export all database contacts in Zoho CRM format.
    Creates Excel and CSV files from database.
    """
    import logging
    logger = logging.getLogger(__name__)
    
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
@login_required
def download_database_export(format):
    """Download database Zoho export (Excel or CSV)."""
    import logging
    logger = logging.getLogger(__name__)
    
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
@login_required
def zoho_config():
    """Configure Zoho CRM integration."""
    import logging
    logger = logging.getLogger(__name__)
    
    if request.method == 'POST':
        # Save Zoho credentials
        zoho_client_id = request.form.get('zoho_client_id', '').strip()
        zoho_client_secret = request.form.get('zoho_client_secret', '').strip()
        zoho_refresh_token = request.form.get('zoho_refresh_token', '').strip()
        zoho_api_domain = request.form.get('zoho_api_domain', 'https://www.zohoapis.com').strip()
        
        logger.info(f"📝 Received Zoho config form:")
        logger.info(f"   Client ID: {zoho_client_id[:20]}..." if zoho_client_id else "   Client ID: EMPTY")
        logger.info(f"   Client Secret: {'*' * 10}" if zoho_client_secret else "   Client Secret: EMPTY")
        logger.info(f"   Refresh Token: {zoho_refresh_token[:20]}..." if zoho_refresh_token else "   Refresh Token: EMPTY")
        logger.info(f"   API Domain: {zoho_api_domain}")
        
        if not all([zoho_client_id, zoho_client_secret, zoho_refresh_token]):
            logger.error("❌ Missing required fields!")
            flash('All fields are required!', 'error')
            return redirect(url_for('zoho_config'))
        
        # Store in environment (current session)
        os.environ['ZOHO_CLIENT_ID'] = zoho_client_id
        os.environ['ZOHO_CLIENT_SECRET'] = zoho_client_secret
        os.environ['ZOHO_REFRESH_TOKEN'] = zoho_refresh_token
        os.environ['ZOHO_API_DOMAIN'] = zoho_api_domain
        
        logger.info("✅ Stored in os.environ")
        
        # Also save to .env file for persistence
        env_file_path = os.path.join(os.path.dirname(__file__), '.env')
        try:
            # Read existing .env content
            env_lines = []
            if os.path.exists(env_file_path):
                with open(env_file_path, 'r') as f:
                    env_lines = f.readlines()
            
            # Update or add Zoho variables
            zoho_vars = {
                'ZOHO_CLIENT_ID': zoho_client_id,
                'ZOHO_CLIENT_SECRET': zoho_client_secret,
                'ZOHO_REFRESH_TOKEN': zoho_refresh_token,
                'ZOHO_API_DOMAIN': zoho_api_domain
            }
            
            # Remove existing Zoho variables
            env_lines = [line for line in env_lines if not line.startswith(('ZOHO_CLIENT_ID=', 'ZOHO_CLIENT_SECRET=', 'ZOHO_REFRESH_TOKEN=', 'ZOHO_API_DOMAIN='))]
            
            # Add new Zoho variables
            for key, value in zoho_vars.items():
                env_lines.append(f"{key}={value}\n")
            
            # Write back to .env
            with open(env_file_path, 'w') as f:
                f.writelines(env_lines)
            
            logger.info("✅ Zoho credentials saved to .env file")
            flash('Zoho CRM credentials saved successfully! They will persist across restarts.', 'success')
        except Exception as e:
            logger.error(f"Error saving to .env file: {str(e)}")
            flash(f'Credentials saved for this session, but could not persist to .env file: {str(e)}', 'warning')
        
        return redirect(url_for('view_contacts'))
    
    # GET - show configuration form
    return render_template('zoho_config.html',
                         zoho_client_id=os.getenv('ZOHO_CLIENT_ID', ''),
                         zoho_api_domain=os.getenv('ZOHO_API_DOMAIN', 'https://www.zohoapis.com'))


def _get_zoho_access_token():
    """Get Zoho CRM access token using refresh token."""
    import logging
    logger = logging.getLogger(__name__)
    
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
        
        logger.info(f"🔄 Requesting access token from Zoho...")
        response = requests.post(token_url, params=params, timeout=10)
        
        logger.info(f"📡 Zoho API Response Status: {response.status_code}")
        logger.info(f"📡 Zoho API Response: {response.text}")
        
        if response.status_code != 200:
            error_msg = f"Zoho API returned {response.status_code}: {response.text}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
        
        data = response.json()
        access_token = data.get('access_token')
        
        if not access_token:
            error_msg = f"No access_token in response: {data}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
        
        logger.info(f"✅ Successfully obtained Zoho access token")
        return access_token, None
        
    except requests.exceptions.RequestException as e:
        error_msg = f"Network error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return None, error_msg


@app.route('/zoho_status')
@login_required
def zoho_status():
    """Debug route to check Zoho configuration status."""
    import logging
    logger = logging.getLogger(__name__)
    
    status = {
        'ZOHO_CLIENT_ID': os.getenv('ZOHO_CLIENT_ID', 'NOT SET'),
        'ZOHO_CLIENT_SECRET': '***' if os.getenv('ZOHO_CLIENT_SECRET') else 'NOT SET',
        'ZOHO_REFRESH_TOKEN': '***' if os.getenv('ZOHO_REFRESH_TOKEN') else 'NOT SET',
        'ZOHO_API_DOMAIN': os.getenv('ZOHO_API_DOMAIN', 'NOT SET')
    }
    
    # Check .env file
    env_file_path = os.path.join(os.path.dirname(__file__), '.env')
    env_file_exists = os.path.exists(env_file_path)
    
    # Try to get access token
    access_token, error = _get_zoho_access_token()
    
    return jsonify({
        'status': status,
        'env_file_exists': env_file_exists,
        'env_file_path': env_file_path,
        'can_get_access_token': access_token is not None,
        'access_token_error': error
    })


@app.route('/upload_automated', methods=['GET'])
@login_required
def upload_automated_page():
    """Automated upload page - single upload, automatic processing."""
    return render_template('upload_automated.html', username=session.get('username'))


@app.route('/upload_automated', methods=['POST'])
@login_required
def upload_automated():
    """Handle automated file upload and start background processing."""
    import logging
    from datetime import datetime
    import threading
    logger = logging.getLogger(__name__)
    
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not file.filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'Please upload an Excel file (.xlsx or .xls)'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        file.save(file_path)
        
        file_size = os.path.getsize(file_path)
        user_id = session.get('user_id')
        
        # Create processing job in database
        job_id = db.create_processing_job(filename, file_size, user_id)
        
        logger.info(f"📝 Created job {job_id} for file: {filename}")
        
        # Start background processing
        thread = threading.Thread(
            target=process_file_automated,
            args=(job_id, file_path, unique_filename, app.config['OUTPUT_FOLDER'])
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'message': 'File uploaded successfully. Processing in background...'
        })
        
    except Exception as e:
        logger.error(f"Error in automated upload: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/job_progress/<int:job_id>')
@login_required
def get_job_progress(job_id):
    """Get processing job status and progress."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        job = db.get_job_by_id(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        return jsonify(job)
    except Exception as e:
        logger.error(f"Error getting job progress: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/kill_job/<int:job_id>', methods=['POST'])
@login_required
def kill_job(job_id):
    """Kill/cancel a running processing job."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        job = db.get_job_by_id(job_id)
        if not job:
            return jsonify({'success': False, 'error': 'Job not found'}), 404
        
        if job['status'] not in ['pending', 'processing']:
            return jsonify({'success': False, 'error': 'Job is not running'}), 400
        
        # Mark job as cancelled
        db.update_job_status(job_id, 'cancelled', 
                           error_message='Job cancelled by user')
        
        logger.info(f"🛑 Job {job_id} cancelled by user")
        
        return jsonify({
            'success': True,
            'message': 'Job cancelled successfully'
        })
        
    except Exception as e:
        logger.error(f"Error killing job: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/download_job/<int:job_id>')
@login_required
def download_job(job_id):
    """Download completed job output file."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        job = db.get_job_by_id(job_id)
        if not job:
            flash('Job not found', 'error')
            return redirect(url_for('processing_history'))
        
        if job['status'] != 'completed':
            flash('Job is not completed yet', 'warning')
            return redirect(url_for('processing_history'))
        
        if not job['output_file']:
            flash('Output file not found', 'error')
            return redirect(url_for('processing_history'))
        
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], job['output_file'])
        if not os.path.exists(file_path):
            flash('Output file does not exist', 'error')
            return redirect(url_for('processing_history'))
        
        return send_file(file_path, as_attachment=True, download_name=job['output_file'])
        
    except Exception as e:
        logger.error(f"Error downloading job file: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('processing_history'))


@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page with statistics and charts."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        days = request.args.get('days', 90, type=int)
        stats = db.get_statistics(days=days)
        recent_jobs = db.get_processing_history(limit=10)
        
        return render_template('dashboard.html',
                             stats=stats,
                             recent_jobs=recent_jobs,
                             days=days,
                             username=session.get('username'))
    except Exception as e:
        logger.error(f"Error loading dashboard: {str(e)}")
        flash(f'Error loading dashboard: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/processing_history')
@login_required
def processing_history():
    """View processing job history with filters."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        status = request.args.get('status', None)
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)
        
        if start_date:
            start_date = start_date + ' 00:00:00'
        if end_date:
            end_date = end_date + ' 23:59:59'
        
        jobs = db.get_processing_history(
            limit=100,
            status=status,
            start_date=start_date,
            end_date=end_date
        )
        
        return render_template('processing_history.html',
                             jobs=jobs,
                             username=session.get('username'))
    except Exception as e:
        logger.error(f"Error loading processing history: {str(e)}")
        flash(f'Error loading history: {str(e)}', 'error')
        return redirect(url_for('index'))


@app.route('/push_to_zoho/<int:contact_id>', methods=['POST'])
@login_required
def push_single_contact_to_zoho(contact_id):
    """
    Push a single contact to Zoho CRM (AJAX endpoint) with duplicate checking.
    
    Returns JSON response for AJAX requests.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Get check_duplicates option from request (default: True)
        check_duplicates = request.json.get('check_duplicates', True) if request.is_json else True
        
        # Get the contact from database
        contact = db.get_contact_by_id(contact_id)
        
        if not contact:
            return jsonify({
                'success': False,
                'message': 'Contact not found'
            }), 404
        
        # Create Zoho service
        zoho_service = ZohoCRMService(
            client_id=os.getenv('ZOHO_CLIENT_ID'),
            client_secret=os.getenv('ZOHO_CLIENT_SECRET'),
            refresh_token=os.getenv('ZOHO_REFRESH_TOKEN'),
            data_center=os.getenv('ZOHO_DATA_CENTER', 'in')
        )
        
        # Prepare contact data
        lead_name = ''
        if contact.get('contact_name'):
            lead_name = contact['contact_name']
        elif contact.get('first_name'):
            first = contact.get('first_name', '').strip()
            last = contact.get('last_name', '').strip()
            lead_name = f"{first} {last}".strip()
        elif contact.get('email'):
            lead_name = _extract_name_from_email(contact['email'])
        
        # Split name for Zoho
        name_parts = lead_name.split() if lead_name else []
        first_name = name_parts[0] if name_parts else 'Unknown'
        last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else '.'
        
        contact_data = {
            'first_name': first_name,
            'last_name': last_name,
            'company': contact.get('company_name') or 'N/A',
            'email': contact.get('email', ''),
            'phone': contact.get('whatsapp', '') or contact.get('phone', ''),
        }
        
        logger.info(f"📤 Pushing contact {contact_id} to Zoho CRM (check_duplicates={check_duplicates})...")
        
        # Update status to 'pushing'
        db.update_zoho_status(contact_id, 'pushing')
        
        # Push to Zoho (with automatic 401 retry and duplicate checking)
        success, message, lead_id = zoho_service.push_to_zoho(contact_data, retry_on_401=True, check_duplicates=check_duplicates)
        
        if success:
            # Update status to 'pushed' with lead_id
            db.update_zoho_status(contact_id, 'pushed', lead_id=lead_id)
            return jsonify({
                'success': True,
                'message': message,
                'status': 'pushed',
                'lead_id': lead_id
            }), 200
        else:
            # Check if it's a duplicate (already exists)
            if 'already exists' in message.lower() or 'skipped' in message.lower():
                # Update status to 'skipped' and extract lead_id if available
                import re
                lead_id_match = re.search(r'ID:\s*([^,\)]+)', message)
                existing_lead_id = lead_id_match.group(1).strip() if lead_id_match else lead_id
                db.update_zoho_status(contact_id, 'skipped', lead_id=existing_lead_id)
                return jsonify({
                    'success': False,
                    'message': message,
                    'status': 'skipped',
                    'lead_id': existing_lead_id
                }), 200  # Return 200 since it's not really an error
            else:
                # Update status to 'failed' with error message
                db.update_zoho_status(contact_id, 'failed', error=message)
                return jsonify({
                    'success': False,
                    'message': message,
                    'status': 'failed'
                }), 400
            
    except Exception as e:
        logger.error(f"Error pushing contact {contact_id} to Zoho: {str(e)}")
        # Update status to 'failed' on exception
        try:
            db.update_zoho_status(contact_id, 'failed', error=str(e))
        except:
            pass  # Don't fail if status update fails
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}',
            'status': 'failed'
        }), 500


@app.route('/push_to_zoho', methods=['POST'])
@login_required
def push_to_zoho():
    """
    Push selected contacts from database to Zoho CRM using ZohoCRMService with duplicate checking.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Get check_duplicates option from form (default: True)
        check_duplicates = request.form.get('check_duplicates', 'true').lower() == 'true'
        
        logger.info(f"🚀 Starting Zoho bulk push (check_duplicates={check_duplicates})...")
        
        # Check if credentials exist
        client_id = os.getenv('ZOHO_CLIENT_ID')
        client_secret = os.getenv('ZOHO_CLIENT_SECRET')
        refresh_token = os.getenv('ZOHO_REFRESH_TOKEN')
        
        logger.info(f"🔑 Credentials check:")
        logger.info(f"   Client ID: {client_id[:20] if client_id else 'MISSING'}...")
        logger.info(f"   Client Secret: {client_secret[:10] if client_secret else 'MISSING'}...")
        logger.info(f"   Refresh Token: {refresh_token[:20] if refresh_token else 'MISSING'}...")
        
        if not all([client_id, client_secret, refresh_token]):
            logger.error("❌ Missing Zoho credentials!")
            flash('Zoho CRM not configured. Please configure your credentials.', 'error')
            return redirect(url_for('zoho_config'))
        
        # Create Zoho service
        zoho_service = ZohoCRMService(
            client_id=os.getenv('ZOHO_CLIENT_ID'),
            client_secret=os.getenv('ZOHO_CLIENT_SECRET'),
            refresh_token=os.getenv('ZOHO_REFRESH_TOKEN'),
            data_center=os.getenv('ZOHO_DATA_CENTER', 'in')
        )
        
        # Test connection first
        logger.info(f"🔍 Testing Zoho CRM connection...")
        access_token, error = zoho_service.get_access_token()
        if error:
            logger.error(f"❌ Zoho connection failed: {error}")
            
            # Provide helpful error message
            if "invalid_code" in error.lower() or "invalid refresh token" in error.lower():
                flash('Your Zoho refresh token is invalid or expired. Please generate a new one.', 'error')
                flash('Run: ./venv/bin/python generate_zoho_token.py', 'info')
            else:
                flash(f'Zoho CRM connection failed: {error}', 'error')
            
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
        
        # Prepare contacts for Zoho service (include contact_id for tracking)
        logger.info(f"📦 Preparing {len(contacts)} contacts for Zoho...")
        
        zoho_contacts = []
        
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
            
            # Split name for Zoho
            name_parts = lead_name.split() if lead_name else []
            first_name = name_parts[0] if name_parts else 'Unknown'
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else '.'
            
            # Prepare contact data for service
            email = contact.get('email', '')
            phone = contact.get('whatsapp', '') or contact.get('phone', '')
            company = contact.get('company_name', 'Unknown')
            
            contact_data = {
                'first_name': first_name,
                'last_name': last_name,
                'company': company,
                'email': email,
                'phone': phone,
                '_contact_id': contact.get('id'),  # Store contact_id for tracking
            }
            
            # Only add if we have minimum data
            if first_name and contact_data['company']:
                zoho_contacts.append(contact_data)
                logger.debug(f"  Added contact {contact.get('id')} to push list")
        
        if not zoho_contacts:
            flash('No valid contacts to push to Zoho', 'warning')
            return redirect(url_for('view_contacts'))
        
        logger.info(f"🚀 Pushing {len(zoho_contacts)} contacts to Zoho CRM...")
        
        # Mark all contacts as 'pushing' before starting
        pushing_count = 0
        for contact_data in zoho_contacts:
            contact_id = contact_data.get('_contact_id')
            if contact_id:
                db.update_zoho_status(contact_id, 'pushing')
                pushing_count += 1
            else:
                logger.warning(f"⚠️  Contact data missing _contact_id: {contact_data.get('first_name', 'Unknown')}")
        logger.info(f"✅ Marked {pushing_count} contacts as 'pushing'")
        
        # Use the Zoho service to push in bulk
        logger.info(f"🚀 Calling push_bulk_to_zoho with {len(zoho_contacts)} contacts...")
        try:
            result = zoho_service.push_bulk_to_zoho(zoho_contacts, batch_size=100, check_duplicates=check_duplicates)
        except Exception as e:
            logger.error(f"❌ Exception during push_bulk_to_zoho: {str(e)}", exc_info=True)
            # Reset all contacts that were marked as 'pushing'
            logger.warning("⚠️  Resetting all contacts from 'pushing' to 'not_pushed' due to exception")
            for contact_data in zoho_contacts:
                contact_id = contact_data.get('_contact_id')
                if contact_id:
                    try:
                        db.update_zoho_status(contact_id, 'not_pushed')
                    except:
                        pass
            flash(f'❌ Error during bulk push: {str(e)}', 'error')
            return redirect(url_for('view_contacts'))
        
        # Ensure result has expected keys
        if not isinstance(result, dict):
            logger.error(f"❌ push_bulk_to_zoho returned unexpected type: {type(result)}")
            # Reset all contacts that were marked as 'pushing'
            logger.warning("⚠️  Resetting all contacts from 'pushing' to 'not_pushed' due to unexpected result type")
            for contact_data in zoho_contacts:
                contact_id = contact_data.get('_contact_id')
                if contact_id:
                    try:
                        db.update_zoho_status(contact_id, 'not_pushed')
                    except:
                        pass
            flash(f'❌ Unexpected response from Zoho service', 'error')
            return redirect(url_for('view_contacts'))
        
        # Log the result structure for debugging
        logger.info(f"📊 Bulk push result: success={result.get('success')}, pushed={result.get('total_pushed', 0)}, skipped={result.get('total_skipped', 0)}, failed={result.get('total_failed', 0)}, error={result.get('error', 'None')}")
        logger.info(f"📊 Result keys: {list(result.keys())}")
        logger.info(f"📊 Successful contacts count: {len(result.get('successful_contacts', []))}")
        logger.info(f"📊 Skipped contacts count: {len(result.get('skipped_contacts', []))}")
        logger.info(f"📊 Failed contacts count: {len(result.get('failed_contacts', []))}")
        
        # Log sample of successful contacts to verify _contact_id is preserved
        successful_sample = result.get('successful_contacts', [])[:3]
        if successful_sample:
            logger.info(f"📊 Sample successful contacts (first 3):")
            for item in successful_sample:
                contact = item.get('contact', {})
                logger.info(f"  - Contact ID: {contact.get('_contact_id')}, Name: {contact.get('first_name')}, Lead ID: {item.get('lead_id')}")
        
        # Update database status for all contacts based on results
        logger.info(f"📊 Updating database status: {result.get('total_pushed', 0)} pushed, {result.get('total_skipped', 0)} skipped, {result.get('total_failed', 0)} failed")
        
        # Track all contact IDs that were processed
        processed_contact_ids = set()
        
        try:
            # Handle skipped contacts (duplicates)
            skipped_count = 0
            for skipped_item in result.get('skipped_contacts', []):
                skipped_contact = skipped_item.get('contact', {})
                contact_id = skipped_contact.get('_contact_id')
                if contact_id:
                    try:
                        lead_id = skipped_item.get('lead_id')
                        db.update_zoho_status(contact_id, 'skipped', lead_id=lead_id)
                        processed_contact_ids.add(contact_id)
                        skipped_count += 1
                    except Exception as e:
                        logger.error(f"❌ Error updating skipped contact {contact_id}: {str(e)}")
                else:
                    logger.warning(f"⚠️  Skipped contact missing _contact_id: {skipped_contact.get('first_name', 'Unknown')}")
            logger.info(f"✅ Updated {skipped_count} skipped contacts")
            
            # Handle failed contacts
            failed_count = 0
            for failed_item in result.get('failed_contacts', []):
                failed_contact = failed_item.get('contact', {})
                contact_id = failed_contact.get('_contact_id')
                if contact_id:
                    try:
                        error_msg = failed_item.get('error', 'Unknown error')
                        db.update_zoho_status(contact_id, 'failed', error=error_msg)
                        processed_contact_ids.add(contact_id)
                        failed_count += 1
                    except Exception as e:
                        logger.error(f"❌ Error updating failed contact {contact_id}: {str(e)}")
                else:
                    logger.warning(f"⚠️  Failed contact missing _contact_id: {failed_contact.get('first_name', 'Unknown')}")
            logger.info(f"✅ Updated {failed_count} failed contacts")
            
            # Handle successfully pushed contacts (with lead_ids)
            success_count = 0
            successful_contacts_list = result.get('successful_contacts', [])
            logger.info(f"📋 Processing {len(successful_contacts_list)} successful contacts")
            for idx, success_item in enumerate(successful_contacts_list):
                success_contact = success_item.get('contact', {})
                contact_id = success_contact.get('_contact_id')
                lead_id = success_item.get('lead_id')
                logger.info(f"  [{idx+1}/{len(successful_contacts_list)}] Contact ID: {contact_id}, Lead ID: {lead_id}, Contact data keys: {list(success_contact.keys())}")
                if contact_id:
                    try:
                        success = db.update_zoho_status(contact_id, 'pushed', lead_id=lead_id)
                        if success:
                            success_count += 1
                            processed_contact_ids.add(contact_id)
                            logger.info(f"  ✅ Updated contact {contact_id} to 'pushed' status")
                        else:
                            logger.error(f"  ❌ Failed to update status for contact {contact_id}")
                    except Exception as e:
                        logger.error(f"  ❌ Error updating pushed contact {contact_id}: {str(e)}", exc_info=True)
                else:
                    logger.warning(f"  ⚠️  Successful contact missing _contact_id. Full item: {success_item}")
            logger.info(f"✅ Updated {success_count} successfully pushed contacts out of {len(successful_contacts_list)}")
            
            # Cleanup: Reset any contacts still in 'pushing' status that weren't processed
            # This handles edge cases where updates might have failed
            all_contact_ids = {contact_data.get('_contact_id') for contact_data in zoho_contacts if contact_data.get('_contact_id')}
            stuck_contact_ids = all_contact_ids - processed_contact_ids
            if stuck_contact_ids:
                logger.warning(f"⚠️  Found {len(stuck_contact_ids)} contacts still in 'pushing' status, resetting to 'not_pushed'")
                for stuck_id in stuck_contact_ids:
                    try:
                        db.update_zoho_status(stuck_id, 'not_pushed')
                        logger.info(f"  ✅ Reset contact {stuck_id} from 'pushing' to 'not_pushed'")
                    except Exception as e:
                        logger.error(f"  ❌ Error resetting contact {stuck_id}: {str(e)}")
            
            # Final safety check: Ensure no contacts are still in 'pushing' status after processing
            logger.info("🔍 Final safety check: Verifying no contacts are stuck in 'pushing' status...")
            remaining_stuck = [c.get('_contact_id') for c in zoho_contacts if c.get('_contact_id') and c.get('_contact_id') not in processed_contact_ids]
            if remaining_stuck:
                logger.warning(f"⚠️  Final check found {len(remaining_stuck)} contacts that may still be stuck, resetting...")
                for contact_id in remaining_stuck:
                    try:
                        db.update_zoho_status(contact_id, 'not_pushed')
                    except:
                        pass
        except Exception as e:
            logger.error(f"❌ Error during status updates: {str(e)}", exc_info=True)
            # Emergency cleanup: Reset all contacts that were marked as 'pushing' to 'not_pushed'
            logger.warning("⚠️  Resetting all contacts that were marked as 'pushing' due to error")
            for contact_data in zoho_contacts:
                contact_id = contact_data.get('_contact_id')
                if contact_id:
                    try:
                        db.update_zoho_status(contact_id, 'not_pushed')
                    except:
                        pass
        
        # Show appropriate message based on results
        total_pushed = result.get('total_pushed', 0)
        total_skipped = result.get('total_skipped', 0)
        total_failed = result.get('total_failed', 0)
        error_msg = result.get('error')
        
        # Check if any failed contacts have rate limit errors
        failed_list = result.get('failed_contacts', [])
        rate_limit_errors = [f.get('error', '') for f in failed_list if 'rate limit' in f.get('error', '').lower() or '429' in f.get('error', '')]
        
        if rate_limit_errors:
            flash(f'⏸️  Zoho API Rate Limit Exceeded: Too many requests in the past 24 hours. Please try again tomorrow or contact Zoho support. ({total_failed} contacts failed due to rate limit)', 'warning')
            logger.warning(f"⚠️  Rate limit hit: {len(rate_limit_errors)} contacts failed due to rate limiting")
        elif error_msg:
            # There was an actual error
            flash(f'❌ Failed to push contacts to Zoho CRM: {error_msg}', 'error')
            logger.error(f"❌ Bulk push error: {error_msg}")
        elif total_pushed > 0:
            # Some contacts were successfully pushed
            flash(f'✅ Successfully pushed {total_pushed} contacts to Zoho CRM! (Skipped: {total_skipped}, Failed: {total_failed})', 'success')
            if total_skipped > 0:
                logger.info(f"⏭️  {total_skipped} contacts skipped (duplicates)")
            if total_failed > 0:
                logger.warning(f"⚠️  {total_failed} contacts failed to push")
        elif total_skipped > 0 and total_failed == 0:
            # All contacts were skipped (duplicates)
            flash(f'⏭️  All {total_skipped} contacts were already in Zoho CRM (skipped duplicates)', 'info')
            logger.info(f"⏭️  All contacts were skipped as duplicates")
        elif total_failed > 0:
            # All contacts failed
            flash(f'❌ Failed to push {total_failed} contacts to Zoho CRM. Check logs for details.', 'error')
            logger.error(f"❌ All contacts failed to push")
        else:
            # No contacts to process or unknown state
            flash(f'⚠️  No contacts were processed. Check logs for details.', 'warning')
            logger.warning(f"⚠️  Bulk push completed but no contacts were processed")
        
        return redirect(url_for('view_contacts'))
        
    except Exception as e:
        logger.error(f"Error pushing to Zoho CRM: {str(e)}", exc_info=True)
        flash(f'❌ Error pushing to Zoho CRM: {str(e)}', 'error')
        return redirect(url_for('view_contacts'))


@app.route('/reset_stuck_zoho_contacts', methods=['POST'])
@login_required
def reset_stuck_zoho_contacts():
    """Reset all contacts stuck in 'pushing' status to 'not_pushed'."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        count = db.reset_stuck_pushing_contacts()
        if count > 0:
            flash(f'✅ Reset {count} contacts that were stuck in "pushing" status', 'success')
            logger.info(f"✅ Reset {count} stuck contacts")
        else:
            flash('ℹ️  No contacts were stuck in "pushing" status', 'info')
        return redirect(url_for('view_contacts'))
    except Exception as e:
        logger.error(f"Error resetting stuck contacts: {str(e)}")
        flash(f'Error resetting stuck contacts: {str(e)}', 'error')
        return redirect(url_for('view_contacts'))


@app.route('/migrate_database', methods=['GET'])
@login_required
def migrate_database_route():
    """
    Web route to run database migration.
    This imports and runs migrate_contacts() from migrate_database.py
    """
    # Check if user is admin
    if not session.get('is_admin'):
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('index'))
    
    try:
        import migrate_database
        result = migrate_database.migrate_contacts()
        
        flash('✅ Database migration completed successfully! Check the contacts page.', 'success')
        logger.info("✅ Database migration completed via web route")
        return redirect(url_for('view_contacts'))
    except ImportError:
        flash('❌ Migration script (migrate_database.py) not found. Please upload it to Railway first.', 'error')
        logger.error("Migration script not found")
        return redirect(url_for('view_contacts'))
    except Exception as e:
        flash(f'❌ Migration error: {str(e)}', 'error')
        logger.error(f"Migration error: {str(e)}", exc_info=True)
        return redirect(url_for('view_contacts'))


if __name__ == '__main__':
    print("\n" + "="*70)
    print("🚢 MARINECO AI EXIM CONTACT FINDER - SECURE VERSION")
    print("="*70)
    print("\n📍 Login: http://127.0.0.1:5000/login")
    print("   Username: admin")
    print("   Password: admin123")
    print("\n💬 Chatbot: http://127.0.0.1:5000/chatbot")
    print("   Quick contact lookup with AI analysis")
    
    # Show API status
    print("\n🔑 API Status:")
    print(f"   ✅ OpenAI API: {'Enabled' if os.getenv('OPENAI_API_KEY') else 'Not configured'}")
    print(f"   ✅ SerpAPI: {'Enabled' if os.getenv('SERPAPI_API_KEY') else 'Not configured'}")
    print(f"   {'✅' if USE_GEMINI else '❌'} Gemini API: {'Enabled (paid)' if USE_GEMINI else 'Not configured'}")
    
    print("\n⚠️  Change the default password in production!")
    print("="*70 + "\n")
    
    # Support Railway/Heroku deployment (uses PORT env var)
    port = int(os.getenv('PORT', 5000))
    # Bind to 0.0.0.0 in production (Railway, Heroku, etc.), 127.0.0.1 for local dev
    host = '0.0.0.0' if os.getenv('PORT') or os.getenv('RAILWAY_ENVIRONMENT') else '127.0.0.1'
    
    # Disable debug mode in production
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_mode, host=host, port=port, use_reloader=False)

