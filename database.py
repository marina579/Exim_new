"""
Database Manager - Handles contact caching and duplicate detection.
Supports both SQLite (local) and PostgreSQL (Railway deployment).
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
import json
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

# Auto-detect database type
DATABASE_URL = os.getenv('DATABASE_URL')  # Railway provides this for PostgreSQL

if DATABASE_URL:
    # PostgreSQL (Railway)
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_TYPE = 'postgresql'
    logger.info("🐘 Using PostgreSQL database (Railway)")
else:
    # SQLite (Local)
    import sqlite3
    DB_TYPE = 'sqlite'
    DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'contacts.db')
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    logger.info(f"📁 Using SQLite database: {DB_PATH}")


class ContactDatabase:
    """Manages contact storage and duplicate detection."""
    
    def __init__(self):
        """Initialize database connection and create tables."""
        self.db_type = DB_TYPE
        self._init_database()
    
    def _get_connection(self):
        """Get database connection."""
        if self.db_type == 'postgresql':
            return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn
    
    def _init_database(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Log database connection info (without sensitive data)
        if self.db_type == 'postgresql':
            db_info = DATABASE_URL.split('@')[-1] if DATABASE_URL else 'Unknown'
            logger.info(f"🔗 Connected to PostgreSQL: {db_info}")
        else:
            logger.info(f"🔗 Using SQLite database: {DB_PATH}")
        
        if self.db_type == 'postgresql':
            # PostgreSQL syntax
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(500) NOT NULL,
                    name_normalized VARCHAR(500) NOT NULL,
                    address TEXT,
                    gstin VARCHAR(50),
                    pan VARCHAR(20),
                    cin VARCHAR(50),
                    website TEXT,
                    industry VARCHAR(200),
                    enrichment_data TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(name_normalized)
                )
            """)
            
            # Add columns if they don't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS gstin VARCHAR(50)")
                cursor.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS pan VARCHAR(20)")
                cursor.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS cin VARCHAR(50)")
                cursor.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS website TEXT")
                cursor.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS industry VARCHAR(200)")
                cursor.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS enrichment_data TEXT")
            except Exception as e:
                logger.debug(f"Columns may already exist: {str(e)}")
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id SERIAL PRIMARY KEY,
                    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                    contact_name VARCHAR(255),
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    phone VARCHAR(50),
                    email VARCHAR(255),
                    whatsapp VARCHAR(50),
                    source_url TEXT,
                    method VARCHAR(50),
                    confidence INTEGER DEFAULT 100,
                    zoho_status VARCHAR(20) DEFAULT 'not_pushed',
                    zoho_lead_id VARCHAR(100),
                    zoho_pushed_at TIMESTAMP,
                    zoho_error TEXT,
                    email_sequence_status VARCHAR(50) DEFAULT 'not_started',
                    email_sequence_step INTEGER DEFAULT 0,
                    email_last_sent_at TIMESTAMP,
                    email_replied BOOLEAN DEFAULT FALSE,
                    email_replied_at TIMESTAMP,
                    email_opened BOOLEAN DEFAULT FALSE,
                    email_clicked BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add Zoho tracking columns if they don't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS zoho_status VARCHAR(20) DEFAULT 'not_pushed'")
                cursor.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS zoho_lead_id VARCHAR(100)")
                cursor.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS zoho_pushed_at TIMESTAMP")
                cursor.execute("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS zoho_error TEXT")
            except Exception as e:
                logger.debug(f"Zoho columns may already exist: {str(e)}")
            
            # Users table for authentication
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    email VARCHAR(255),
                    is_admin BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    created_by INTEGER REFERENCES users(id)
                )
            """)
            
            # Processing jobs table for tracking file uploads and processing
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_jobs (
                    id SERIAL PRIMARY KEY,
                    file_name VARCHAR(255),
                    file_size INTEGER,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'pending',
                    total_rows INTEGER,
                    contacts_found INTEGER,
                    duplicates_removed INTEGER,
                    companies_found INTEGER,
                    new_companies INTEGER,
                    api_calls_used INTEGER,
                    processing_time INTEGER,
                    error_message TEXT,
                    output_file VARCHAR(255),
                    user_id INTEGER REFERENCES users(id)
                )
            """)
            
            # Scheduled campaigns table for email marketing
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_campaigns (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    list_key VARCHAR(255) NOT NULL,
                    template_key VARCHAR(255) NOT NULL,
                    subject VARCHAR(500) NOT NULL,
                    from_email VARCHAR(255) NOT NULL,
                    from_name VARCHAR(255),
                    schedule_type VARCHAR(50) NOT NULL,
                    schedule_time VARCHAR(10) NOT NULL,
                    schedule_day INTEGER,
                    start_date DATE,
                    end_date DATE,
                    enabled BOOLEAN DEFAULT TRUE,
                    auto_sync_contacts BOOLEAN DEFAULT TRUE,
                    last_sent_at TIMESTAMP,
                    last_campaign_id VARCHAR(255),
                    status VARCHAR(50) DEFAULT 'pending',
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    user_id INTEGER REFERENCES users(id)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_company_name ON companies(name_normalized)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_company ON contacts(company_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_created ON contacts(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_status ON processing_jobs(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_uploaded ON processing_jobs(uploaded_at)")
        else:
            # SQLite syntax
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    name_normalized TEXT NOT NULL UNIQUE,
                    address TEXT,
                    gstin TEXT,
                    pan TEXT,
                    cin TEXT,
                    website TEXT,
                    industry TEXT,
                    enrichment_data TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add columns if they don't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN gstin TEXT")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN pan TEXT")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN cin TEXT")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN website TEXT")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN industry TEXT")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE companies ADD COLUMN enrichment_data TEXT")
            except:
                pass
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    contact_name TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    phone TEXT,
                    email TEXT,
                    whatsapp TEXT,
                    source_url TEXT,
                    method TEXT,
                    confidence INTEGER DEFAULT 100,
                    zoho_status TEXT DEFAULT 'not_pushed',
                    zoho_lead_id TEXT,
                    zoho_pushed_at TIMESTAMP,
                    zoho_error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
                )
            """)
            
            # Add Zoho tracking columns if they don't exist (for existing databases)
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN zoho_status TEXT DEFAULT 'not_pushed'")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN zoho_lead_id TEXT")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN zoho_pushed_at TIMESTAMP")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN zoho_error TEXT")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN email_sequence_status TEXT DEFAULT 'not_started'")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN email_sequence_step INTEGER DEFAULT 0")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN email_last_sent_at TIMESTAMP")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN email_replied INTEGER DEFAULT 0")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN email_replied_at TIMESTAMP")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN email_opened INTEGER DEFAULT 0")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE contacts ADD COLUMN email_clicked INTEGER DEFAULT 0")
            except:
                pass
            
            # Users table for authentication
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    email TEXT,
                    is_admin INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    created_by INTEGER,
                    FOREIGN KEY (created_by) REFERENCES users(id)
                )
            """)
            
            # Processing jobs table for tracking file uploads and processing
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT,
                    file_size INTEGER,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT DEFAULT 'pending',
                    total_rows INTEGER,
                    contacts_found INTEGER,
                    duplicates_removed INTEGER,
                    companies_found INTEGER,
                    new_companies INTEGER,
                    api_calls_used INTEGER,
                    processing_time INTEGER,
                    error_message TEXT,
                    output_file TEXT,
                    user_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_company_name ON companies(name_normalized)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_company ON contacts(company_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_created ON contacts(created_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_status ON processing_jobs(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_job_uploaded ON processing_jobs(uploaded_at)")
        
        conn.commit()
        
        # Check existing data count AFTER creating tables (for safety verification)
        try:
            if self.db_type == 'postgresql':
                cursor.execute("SELECT COUNT(*) as count FROM companies")
                companies_count = cursor.fetchone()['count']
                cursor.execute("SELECT COUNT(*) as count FROM contacts")
                contacts_count = cursor.fetchone()['count']
            else:
                cursor.execute("SELECT COUNT(*) as count FROM companies")
                companies_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) as count FROM contacts")
                contacts_count = cursor.fetchone()[0]
            
            logger.info(f"📊 Database status: {companies_count} companies, {contacts_count} contacts")
            
            if companies_count > 0 or contacts_count > 0:
                logger.info(f"✅ Database has existing data - data preserved!")
            else:
                logger.info(f"📊 Database is empty (new database or no data yet)")
        except Exception as e:
            logger.warning(f"⚠️  Could not verify data count: {str(e)}")
        
        conn.close()
        logger.info("✅ Database tables initialized")
        
        # Create default admin user if no users exist
        self._create_default_admin()
    
    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for duplicate detection."""
        if not name:
            return ""
        
        # Convert to lowercase, remove extra spaces, remove common suffixes
        normalized = name.lower().strip()
        
        # Remove common company suffixes
        suffixes = [
            'private limited', 'pvt ltd', 'pvt. ltd.', 'pvt ltd.', 'pvt. ltd',
            'limited', 'ltd', 'ltd.', 'llp', 'llc', 'inc', 'inc.',
            'corporation', 'corp', 'corp.', 'company', 'co', 'co.',
        ]
        
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
        
        # Remove special characters except spaces
        normalized = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in normalized)
        
        # Remove extra spaces
        normalized = ' '.join(normalized.split())
        
        return normalized
    
    def _merge_duplicate_contacts(self, contacts: List[Dict]) -> List[Dict]:
        """
        Merge contacts with same name, email, or phone into single records.
        Combines multiple phone numbers/emails for same person.
        Also merges contacts with complementary data (phone + email) from same source.
        
        Args:
            contacts: List of contact dictionaries
        
        Returns:
            List of merged contact dictionaries
        """
        if not contacts:
            return []
        
        # Group contacts by name, email, or phone
        contact_groups = {}
        
        for contact in contacts:
            # Create a unique key based on name, email, or phone
            name = contact.get('contact_name', '').strip().lower()
            email = contact.get('email', '').strip().lower()
            phone = contact.get('phone', '').strip()
            whatsapp = contact.get('whatsapp', '').strip()
            first_name = contact.get('first_name', '').strip().lower()
            last_name = contact.get('last_name', '').strip().lower()
            
            # Normalize phone numbers (remove spaces, dashes, country codes for comparison)
            def normalize_phone(p):
                if not p:
                    return ''
                # Remove common prefixes and non-digits
                p = p.replace('+91', '').replace('+1', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
                # Keep only last 10 digits (Indian mobile numbers)
                if len(p) >= 10:
                    return p[-10:]
                return p
            
            phone_normalized = normalize_phone(phone) or normalize_phone(whatsapp)
            
            # Store normalize_phone function for later use
            if 'normalize_phone' not in globals():
                globals()['normalize_phone'] = normalize_phone
            
            # Try to find a matching key
            key = None
            
            # Priority 1: If we have an email, use that as primary key
            if email and '@' in email:
                key = f"email:{email}"
            # Priority 2: If we have a phone number, use that as key
            elif phone_normalized:
                key = f"phone:{phone_normalized}"
            # Priority 3: If we have a full name, use that
            elif name:
                key = f"name:{name}"
            elif first_name or last_name:
                key = f"name:{first_name} {last_name}".strip()
            else:
                # No identifying info, create unique key (don't merge)
                import time
                key = f"unique:{time.time()}:{id(contact)}"
            
            # Check if we should merge with an existing group
            merged = False
            for existing_key, existing_contacts in list(contact_groups.items()):
                # Check if email matches
                if email and email in existing_key:
                    contact_groups[existing_key].append(contact)
                    merged = True
                    break
                # Check if phone matches
                elif phone_normalized and phone_normalized in existing_key:
                    contact_groups[existing_key].append(contact)
                    merged = True
                    break
                # Check if name matches
                elif name and name in existing_key:
                    contact_groups[existing_key].append(contact)
                    merged = True
                    break
            
            if not merged:
                contact_groups[key] = [contact]
        
        # Merge contacts in each group
        merged_contacts = []
        
        for key, group in contact_groups.items():
            if len(group) == 1:
                # No duplicates, keep as is
                merged_contacts.append(group[0])
            else:
                # Merge multiple contacts into one
                merged = {
                    'contact_name': '',
                    'first_name': '',
                    'last_name': '',
                    'title': '',
                    'department': '',
                    'phone': '',
                    'email': '',
                    'whatsapp': '',
                    'linkedin_url': '',
                    'twitter_url': '',
                    'source_url': '',
                    'method': '',
                    'confidence': 100
                }
                
                # Collect all values
                all_phones = []
                all_emails = []
                all_whatsapps = []
                all_sources = []
                all_methods = []
                
                for contact in group:
                    # Take first non-empty name
                    if not merged['contact_name'] and contact.get('contact_name'):
                        merged['contact_name'] = contact['contact_name']
                    if not merged['first_name'] and contact.get('first_name'):
                        merged['first_name'] = contact['first_name']
                    if not merged['last_name'] and contact.get('last_name'):
                        merged['last_name'] = contact['last_name']
                    if not merged['title'] and contact.get('title'):
                        merged['title'] = contact['title']
                    if not merged['department'] and contact.get('department'):
                        merged['department'] = contact['department']
                    if not merged['linkedin_url'] and contact.get('linkedin_url'):
                        merged['linkedin_url'] = contact['linkedin_url']
                    if not merged['twitter_url'] and contact.get('twitter_url'):
                        merged['twitter_url'] = contact['twitter_url']
                    
                    # Collect all phones, emails, etc.
                    if contact.get('phone'):
                        all_phones.append(contact['phone'])
                    if contact.get('email'):
                        all_emails.append(contact['email'])
                    if contact.get('whatsapp'):
                        all_whatsapps.append(contact['whatsapp'])
                    if contact.get('source_url'):
                        all_sources.append(contact['source_url'])
                    if contact.get('method'):
                        all_methods.append(contact['method'])
                
                # Deduplicate and combine
                all_phones = list(set([p for p in all_phones if p]))
                all_emails = list(set([e for e in all_emails if e]))
                all_whatsapps = list(set([w for w in all_whatsapps if w]))
                all_sources = list(set([s for s in all_sources if s]))
                all_methods = list(set([m for m in all_methods if m]))
                
                # Take the first/best value for single fields
                # Prefer phone over whatsapp if both exist
                if all_phones:
                    merged['phone'] = all_phones[0]
                    # If whatsapp is same as phone, don't duplicate
                    if all_whatsapps and all_whatsapps[0] == all_phones[0]:
                        merged['whatsapp'] = all_phones[0]
                    elif all_whatsapps:
                        merged['whatsapp'] = all_whatsapps[0]
                    else:
                        merged['whatsapp'] = all_phones[0]  # Use phone as WhatsApp if no separate WhatsApp
                elif all_whatsapps:
                    merged['phone'] = all_whatsapps[0]
                    merged['whatsapp'] = all_whatsapps[0]
                else:
                    merged['phone'] = ''
                    merged['whatsapp'] = ''
                
                merged['email'] = all_emails[0] if all_emails else ''
                merged['source_url'] = all_sources[0] if all_sources else ''
                merged['method'] = ', '.join(all_methods[:3]) if all_methods else ''
                
                merged_contacts.append(merged)
                
                logger.info(f"🔗 Merged {len(group)} contacts into 1: {merged.get('contact_name') or merged.get('email')}")
        
        # STEP 2: Merge contacts with complementary data (phone-only + email-only)
        # Identify contacts that need complementary data
        complementary_phone_only = []  # Contacts with phone but no email
        complementary_email_only = []  # Contacts with email but no phone
        final_merged = []  # Contacts that already have both or were merged
        
        for contact in merged_contacts:
            phone = contact.get('phone', '').strip()
            email = contact.get('email', '').strip()
            
            if phone and not email:
                complementary_phone_only.append(contact)
            elif email and not phone:
                complementary_email_only.append(contact)
            else:
                # Has both or neither - keep as is
                final_merged.append(contact)
        
        # Merge complementary contacts (phone-only + email-only from same method/source)
        used_phone_indices = set()
        used_email_indices = set()
        
        for i, phone_contact in enumerate(complementary_phone_only):
            if i in used_phone_indices:
                continue
                
            phone_method = phone_contact.get('method', '').lower()
            phone_source = phone_contact.get('source_url', '')
            
            # Try to find matching email contact (same method or source)
            best_match_idx = None
            for j, email_contact in enumerate(complementary_email_only):
                if j in used_email_indices:
                    continue
                    
                email_method = email_contact.get('method', '').lower()
                email_source = email_contact.get('source_url', '')
                
                # Match if same method (e.g., both from 'serpapi') or same source URL
                if phone_method and email_method and phone_method == email_method:
                    best_match_idx = j
                    break
                elif phone_source and email_source and phone_source == email_source:
                    best_match_idx = j
                    break
            
            # If no exact match, use first available email contact
            if best_match_idx is None and complementary_email_only:
                for j, email_contact in enumerate(complementary_email_only):
                    if j not in used_email_indices:
                        best_match_idx = j
                        break
            
            if best_match_idx is not None:
                email_contact = complementary_email_only[best_match_idx]
                
                # Merge them into one contact
                merged_comp = {
                    'contact_name': phone_contact.get('contact_name') or email_contact.get('contact_name', ''),
                    'first_name': phone_contact.get('first_name') or email_contact.get('first_name', ''),
                    'last_name': phone_contact.get('last_name') or email_contact.get('last_name', ''),
                    'phone': phone_contact.get('phone', ''),
                    'email': email_contact.get('email', ''),
                    'whatsapp': phone_contact.get('whatsapp') or phone_contact.get('phone', ''),
                    'source_url': phone_contact.get('source_url') or email_contact.get('source_url', ''),
                    'method': f"{phone_contact.get('method', '')}+{email_contact.get('method', '')}".strip('+'),
                    'confidence': min(phone_contact.get('confidence', 100), email_contact.get('confidence', 100))
                }
                
                final_merged.append(merged_comp)
                used_phone_indices.add(i)
                used_email_indices.add(best_match_idx)
                logger.info(f"🔗 Merged complementary: phone={merged_comp.get('phone', 'N/A')[:15]}, email={merged_comp.get('email', 'N/A')[:25]}")
        
        # Add remaining unused complementary contacts
        for i, phone_contact in enumerate(complementary_phone_only):
            if i not in used_phone_indices:
                final_merged.append(phone_contact)
        for i, email_contact in enumerate(complementary_email_only):
            if i not in used_email_indices:
                final_merged.append(email_contact)
        
        logger.info(f"📊 Contact deduplication: {len(contacts)} → {len(final_merged)} contacts")
        return final_merged
    
    def check_company_exists(self, company_name: str) -> Optional[int]:
        """
        Check if company already exists in database.
        Returns company_id if exists, None otherwise.
        """
        normalized = self._normalize_company_name(company_name)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id FROM companies WHERE name_normalized = %s" if self.db_type == 'postgresql' 
            else "SELECT id FROM companies WHERE name_normalized = ?",
            (normalized,)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            company_id = result['id'] if self.db_type == 'postgresql' else result[0]
            logger.info(f"💾 Found cached company: {company_name} (ID: {company_id})")
            return company_id
        
        return None
    
    def get_company_contacts(self, company_id: int) -> List[Dict]:
        """Get all contacts for a company from database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM contacts WHERE company_id = %s ORDER BY created_at DESC" if self.db_type == 'postgresql'
            else "SELECT * FROM contacts WHERE company_id = ? ORDER BY created_at DESC",
            (company_id,)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        contacts = []
        for row in rows:
            contacts.append({
                'contact_name': row['contact_name'] if self.db_type == 'postgresql' else row[2],
                'first_name': row['first_name'] if self.db_type == 'postgresql' else row[3],
                'last_name': row['last_name'] if self.db_type == 'postgresql' else row[4],
                'phone': row['phone'] if self.db_type == 'postgresql' else row[5],
                'email': row['email'] if self.db_type == 'postgresql' else row[6],
                'whatsapp': row['whatsapp'] if self.db_type == 'postgresql' else row[7],
                'source_url': row['source_url'] if self.db_type == 'postgresql' else row[8],
                'method': row['method'] if self.db_type == 'postgresql' else row[9],
            })
        
        logger.info(f"💾 Retrieved {len(contacts)} cached contacts for company ID {company_id}")
        return contacts
    
    def get_contact_by_id(self, contact_id: int) -> Optional[Dict]:
        """
        Get a single contact by ID with company information.
        
        Args:
            contact_id: Contact ID
        
        Returns:
            Dictionary with contact and company data, or None if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get contact with company info (JOIN)
            cursor.execute(
                """
                SELECT c.*, comp.name as company_name
                FROM contacts c
                LEFT JOIN companies comp ON c.company_id = comp.id
                WHERE c.id = %s
                """ if self.db_type == 'postgresql'
                else """
                SELECT c.*, comp.name as company_name
                FROM contacts c
                LEFT JOIN companies comp ON c.company_id = comp.id
                WHERE c.id = ?
                """,
                (contact_id,)
            )
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            if self.db_type == 'postgresql':
                contact = {
                    'id': row['id'],
                    'company_id': row['company_id'],
                    'contact_name': row['contact_name'],
                    'first_name': row['first_name'],
                    'last_name': row['last_name'],
                    'title': row.get('title'),
                    'department': row.get('department'),
                    'phone': row['phone'],
                    'email': row['email'],
                    'whatsapp': row['whatsapp'],
                    'linkedin_url': row.get('linkedin_url'),
                    'twitter_url': row.get('twitter_url'),
                    'source_url': row['source_url'],
                    'method': row['method'],
                    'confidence': row['confidence'],
                    'zoho_status': row.get('zoho_status', 'not_pushed'),
                    'zoho_lead_id': row.get('zoho_lead_id'),
                    'zoho_pushed_at': str(row['zoho_pushed_at']) if row.get('zoho_pushed_at') else None,
                    'zoho_error': row.get('zoho_error'),
                    'company_name': row['company_name'],
                }
            else:  # SQLite - columns: id, company_id, contact_name, first_name, last_name, phone, email, whatsapp, source_url, method, confidence, zoho_status, zoho_lead_id, zoho_pushed_at, zoho_error, created_at, company_name
                contact = {
                    'id': row[0],
                    'company_id': row[1],
                    'contact_name': row[2],
                    'first_name': row[3],
                    'last_name': row[4],
                    'phone': row[5],
                    'email': row[6],
                    'whatsapp': row[7],
                    'source_url': row[8],
                    'method': row[9],
                    'confidence': row[10],
                    'zoho_status': row[11] if len(row) > 11 else 'not_pushed',
                    'zoho_lead_id': row[12] if len(row) > 12 else None,
                    'zoho_pushed_at': str(row[13]) if len(row) > 13 and row[13] else None,
                    'zoho_error': row[14] if len(row) > 14 else None,
                    'company_name': row[-1],  # Last column from JOIN
                }
            
            return contact
            
        except Exception as e:
            logger.error(f"Error getting contact {contact_id}: {str(e)}")
            return None
        finally:
            conn.close()
    
    def update_zoho_status(self, contact_id: int, status: str, lead_id: str = None, error: str = None) -> bool:
        """
        Update Zoho push status for a contact.
        
        Args:
            contact_id: Contact ID
            status: Status ('not_pushed', 'pushing', 'pushed', 'skipped', 'failed')
            lead_id: Zoho Lead ID (optional, only for 'pushed' status)
            error: Error message (optional, only for 'failed' status)
        
        Returns:
            True if updated successfully, False otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Build update query
            if self.db_type == 'postgresql':
                if status == 'pushed':
                    cursor.execute("""
                        UPDATE contacts 
                        SET zoho_status = %s, 
                            zoho_lead_id = %s, 
                            zoho_pushed_at = CURRENT_TIMESTAMP,
                            zoho_error = NULL
                        WHERE id = %s
                    """, (status, lead_id, contact_id))
                elif status == 'failed':
                    cursor.execute("""
                        UPDATE contacts 
                        SET zoho_status = %s, 
                            zoho_error = %s,
                            zoho_pushed_at = NULL
                        WHERE id = %s
                    """, (status, error, contact_id))
                else:
                    cursor.execute("""
                        UPDATE contacts 
                        SET zoho_status = %s,
                            zoho_error = NULL
                        WHERE id = %s
                    """, (status, contact_id))
            else:  # SQLite
                if status == 'pushed':
                    cursor.execute("""
                        UPDATE contacts 
                        SET zoho_status = ?, 
                            zoho_lead_id = ?, 
                            zoho_pushed_at = CURRENT_TIMESTAMP,
                            zoho_error = NULL
                        WHERE id = ?
                    """, (status, lead_id, contact_id))
                elif status == 'failed':
                    cursor.execute("""
                        UPDATE contacts 
                        SET zoho_status = ?, 
                            zoho_error = ?,
                            zoho_pushed_at = NULL
                        WHERE id = ?
                    """, (status, error, contact_id))
                else:
                    cursor.execute("""
                        UPDATE contacts 
                        SET zoho_status = ?,
                            zoho_error = NULL
                        WHERE id = ?
                    """, (status, contact_id))
            
            conn.commit()
            logger.info(f"✅ Updated Zoho status for contact {contact_id}: {status}")
            return True
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error updating Zoho status for contact {contact_id}: {str(e)}")
            return False
        finally:
            conn.close()
    
    def reset_stuck_pushing_contacts(self) -> int:
        """
        Reset all contacts stuck in 'pushing' status to 'not_pushed'.
        Useful for cleaning up contacts that got stuck during bulk push operations.
        
        Returns:
            Number of contacts reset
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute("""
                    UPDATE contacts 
                    SET zoho_status = 'not_pushed'
                    WHERE zoho_status = 'pushing'
                """)
                count = cursor.rowcount
            else:
                cursor.execute("""
                    UPDATE contacts 
                    SET zoho_status = 'not_pushed'
                    WHERE zoho_status = 'pushing'
                """)
                count = cursor.rowcount
            
            conn.commit()
            logger.info(f"✅ Reset {count} contacts from 'pushing' to 'not_pushed'")
            return count
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error resetting stuck contacts: {str(e)}")
            return 0
        finally:
            conn.close()
    
    def get_company_enrichment_data(self, company_id: int) -> Dict:
        """
        Get enrichment metadata for a company (GST, PAN, website, etc).
        Returns empty dict if not found.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT gstin, pan, cin, website, industry, enrichment_data FROM companies WHERE id = %s" if self.db_type == 'postgresql'
            else "SELECT gstin, pan, cin, website, industry, enrichment_data FROM companies WHERE id = ?",
            (company_id,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {}
        
        result = {
            'gstin': row['gstin'] if self.db_type == 'postgresql' else row[0],
            'pan': row['pan'] if self.db_type == 'postgresql' else row[1],
            'cin': row['cin'] if self.db_type == 'postgresql' else row[2],
            'website': row['website'] if self.db_type == 'postgresql' else row[3],
            'industry': row['industry'] if self.db_type == 'postgresql' else row[4],
        }
        
        # Parse enrichment_data JSON if present
        enrichment_json = row['enrichment_data'] if self.db_type == 'postgresql' else row[5]
        if enrichment_json:
            try:
                result['enrichment_data'] = json.loads(enrichment_json)
            except:
                pass
        
        logger.info(f"💾 Retrieved enrichment data for company ID {company_id}")
        return result
    
    def save_company_and_contacts(self, company_name: str, address: str, contacts: List[Dict], 
                                   gstin: str = None, pan: str = None, cin: str = None,
                                   website: str = None, industry: str = None, 
                                   enrichment_data: Dict = None) -> int:
        """
        Save company and its contacts to database with enrichment metadata.
        
        Args:
            company_name: Company name
            address: Company address
            contacts: List of contact dictionaries
            gstin: GST Identification Number (cached for future use)
            pan: PAN number
            cin: Corporate Identity Number
            website: Company website URL
            industry: Industry/business type
            enrichment_data: Additional enrichment metadata as JSON
        
        Returns:
            company_id
        """
        normalized = self._normalize_company_name(company_name)
        
        # Convert enrichment_data dict to JSON string
        enrichment_json = json.dumps(enrichment_data) if enrichment_data else None
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Insert or update company with enrichment metadata
            if self.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO companies (name, name_normalized, address, gstin, pan, cin, 
                                         website, industry, enrichment_data, processed_at, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (name_normalized) 
                    DO UPDATE SET 
                        last_updated = CURRENT_TIMESTAMP, 
                        address = EXCLUDED.address,
                        gstin = COALESCE(EXCLUDED.gstin, companies.gstin),
                        pan = COALESCE(EXCLUDED.pan, companies.pan),
                        cin = COALESCE(EXCLUDED.cin, companies.cin),
                        website = COALESCE(EXCLUDED.website, companies.website),
                        industry = COALESCE(EXCLUDED.industry, companies.industry),
                        enrichment_data = COALESCE(EXCLUDED.enrichment_data, companies.enrichment_data)
                    RETURNING id
                """, (company_name, normalized, address, gstin, pan, cin, website, industry, enrichment_json))
                company_id = cursor.fetchone()['id']
            else:
                # For SQLite, check if record exists first
                cursor.execute("SELECT id, gstin, pan, cin, website, industry, enrichment_data FROM companies WHERE name_normalized = ?", (normalized,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing, keeping non-null values
                    company_id = existing[0]
                    cursor.execute("""
                        UPDATE companies 
                        SET address = ?, 
                            gstin = COALESCE(?, gstin),
                            pan = COALESCE(?, pan),
                            cin = COALESCE(?, cin),
                            website = COALESCE(?, website),
                            industry = COALESCE(?, industry),
                            enrichment_data = COALESCE(?, enrichment_data),
                            last_updated = CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (address, gstin, pan, cin, website, industry, enrichment_json, company_id))
                else:
                    # Insert new
                    cursor.execute("""
                        INSERT INTO companies (name, name_normalized, address, gstin, pan, cin, 
                                             website, industry, enrichment_data, processed_at, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """, (company_name, normalized, address, gstin, pan, cin, website, industry, enrichment_json))
                    company_id = cursor.lastrowid
            
            # Delete old contacts for this company (to avoid duplicates)
            cursor.execute(
                "DELETE FROM contacts WHERE company_id = %s" if self.db_type == 'postgresql'
                else "DELETE FROM contacts WHERE company_id = ?",
                (company_id,)
            )
            
            # Merge duplicate contacts (same name/email should be in one record)
            merged_contacts = self._merge_duplicate_contacts(contacts)
            
            # Insert merged contacts
            for contact in merged_contacts:
                # Extract name from email if contact_name is empty
                contact_name = contact.get('contact_name', '').strip()
                email = contact.get('email', '').strip()
                
                if not contact_name and email and '@' in email:
                    # Extract name from email (e.g., john.doe@example.com → John Doe)
                    username = email.split('@')[0]
                    name = username.replace('.', ' ').replace('_', ' ').replace('-', ' ')
                    name_parts = [part.capitalize() for part in name.split() if len(part) > 1 and not part.isdigit()]
                    if len(name_parts) > 3:
                        name_parts = name_parts[:2]
                    contact_name = ' '.join(name_parts)
                    logger.info(f"📧 Extracted name from email: {email} → {contact_name}")
                
                if self.db_type == 'postgresql':
                    cursor.execute("""
                        INSERT INTO contacts 
                        (company_id, contact_name, first_name, last_name, phone, email, whatsapp, source_url, method)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        company_id,
                        contact_name,
                        contact.get('first_name', ''),
                        contact.get('last_name', ''),
                        contact.get('phone', ''),
                        email,
                        contact.get('whatsapp', ''),
                        contact.get('source_url', ''),
                        contact.get('method', '')
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO contacts 
                        (company_id, contact_name, first_name, last_name, phone, email, whatsapp, source_url, method)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        company_id,
                        contact_name,
                        contact.get('first_name', ''),
                        contact.get('last_name', ''),
                        contact.get('phone', ''),
                        email,
                        contact.get('whatsapp', ''),
                        contact.get('source_url', ''),
                        contact.get('method', '')
                    ))
            
            conn.commit()
            logger.info(f"💾 Saved {len(contacts)} contacts for: {company_name} (ID: {company_id})")
            return company_id
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error saving to database: {str(e)}")
            raise
        finally:
            conn.close()
    
    def get_stats(self) -> Dict:
        """Get database statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Total companies
        cursor.execute("SELECT COUNT(*) as count FROM companies")
        total_companies = cursor.fetchone()['count'] if self.db_type == 'postgresql' else cursor.fetchone()[0]
        
        # Total contacts
        cursor.execute("SELECT COUNT(*) as count FROM contacts")
        total_contacts = cursor.fetchone()['count'] if self.db_type == 'postgresql' else cursor.fetchone()[0]
        
        # Companies with contacts
        cursor.execute("SELECT COUNT(DISTINCT company_id) as count FROM contacts")
        companies_with_contacts = cursor.fetchone()['count'] if self.db_type == 'postgresql' else cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_companies': total_companies,
            'total_contacts': total_contacts,
            'companies_with_contacts': companies_with_contacts,
            'db_type': self.db_type
        }
    
    def get_all_contacts_paginated(self, page: int = 1, per_page: int = 50, search_query: str = None, 
                                   start_date: str = None, end_date: str = None) -> Dict:
        """
        Get all contacts with company info, paginated, searchable, and date-filterable.
        
        Args:
            page: Page number (starting from 1)
            per_page: Number of contacts per page
            search_query: Optional search term for company name or contact name
            start_date: Optional start date filter (YYYY-MM-DD HH:MM:SS)
            end_date: Optional end date filter (YYYY-MM-DD HH:MM:SS)
        
        Returns:
            Dict with contacts, total, pages, current_page
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        offset = (page - 1) * per_page
        
        # Build WHERE clause for search and date filter
        where_clauses = []
        search_params = []
        
        if search_query:
            search_term = f"%{search_query}%"
            if self.db_type == 'postgresql':
                search_clause = """
                    (companies.name ILIKE %s 
                    OR contacts.contact_name ILIKE %s
                    OR contacts.first_name ILIKE %s
                    OR contacts.last_name ILIKE %s
                    OR contacts.phone LIKE %s
                    OR contacts.email LIKE %s)
                """
            else:
                search_clause = """
                    (companies.name LIKE ? 
                    OR contacts.contact_name LIKE ?
                    OR contacts.first_name LIKE ?
                    OR contacts.last_name LIKE ?
                    OR contacts.phone LIKE ?
                    OR contacts.email LIKE ?)
                """
            where_clauses.append(search_clause)
            search_params.extend([search_term] * 6)
        
        # Add date filtering
        if start_date:
            date_param = '%s' if self.db_type == 'postgresql' else '?'
            where_clauses.append(f"contacts.created_at >= {date_param}")
            search_params.append(start_date)
        
        if end_date:
            date_param = '%s' if self.db_type == 'postgresql' else '?'
            where_clauses.append(f"contacts.created_at <= {date_param}")
            search_params.append(end_date)
        
        where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # Get total count with search filter
        count_query = f"""
            SELECT COUNT(*) as count 
            FROM contacts 
            JOIN companies ON contacts.company_id = companies.id
            {where_clause}
        """
        if search_params:
            cursor.execute(count_query, search_params)
        else:
            cursor.execute(count_query)
        total = cursor.fetchone()['count'] if self.db_type == 'postgresql' else cursor.fetchone()[0]
        
        # Get paginated contacts with company info
        if self.db_type == 'postgresql':
            query = f"""
                SELECT 
                    contacts.id,
                    companies.name as company_name,
                    companies.address as company_address,
                    contacts.contact_name,
                    contacts.first_name,
                    contacts.last_name,
                    contacts.phone,
                    contacts.email,
                    contacts.whatsapp,
                    contacts.source_url,
                    contacts.method,
                    contacts.zoho_status,
                    contacts.zoho_lead_id,
                    contacts.zoho_pushed_at,
                    contacts.zoho_error,
                    contacts.created_at
                FROM contacts
                JOIN companies ON contacts.company_id = companies.id
                {where_clause}
                ORDER BY contacts.created_at DESC
                LIMIT %s OFFSET %s
            """
            params = search_params + [per_page, offset] if search_params else [per_page, offset]
            cursor.execute(query, params)
        else:
            query = f"""
                SELECT 
                    contacts.id,
                    companies.name as company_name,
                    companies.address as company_address,
                    contacts.contact_name,
                    contacts.first_name,
                    contacts.last_name,
                    contacts.phone,
                    contacts.email,
                    contacts.whatsapp,
                    contacts.source_url,
                    contacts.method,
                    contacts.zoho_status,
                    contacts.zoho_lead_id,
                    contacts.zoho_pushed_at,
                    contacts.zoho_error,
                    contacts.created_at
                FROM contacts
                JOIN companies ON contacts.company_id = companies.id
                {where_clause}
                ORDER BY contacts.created_at DESC
                LIMIT ? OFFSET ?
            """
            params = search_params + [per_page, offset] if search_params else [per_page, offset]
            cursor.execute(query, params)
        
        rows = cursor.fetchall()
        conn.close()
        
        contacts = []
        for row in rows:
            if self.db_type == 'postgresql':
                contacts.append({
                    'id': row['id'],
                    'company_name': row['company_name'],
                    'company_address': row['company_address'],
                    'contact_name': row['contact_name'],
                    'first_name': row['first_name'],
                    'last_name': row['last_name'],
                    'phone': row['phone'],
                    'email': row['email'],
                    'whatsapp': row['whatsapp'],
                    'source_url': row['source_url'],
                    'method': row['method'],
                    'zoho_status': row.get('zoho_status', 'not_pushed'),
                    'zoho_lead_id': row.get('zoho_lead_id'),
                    'zoho_pushed_at': str(row['zoho_pushed_at']) if row.get('zoho_pushed_at') else None,
                    'zoho_error': row.get('zoho_error'),
                    'created_at': str(row['created_at'])
                })
            else:
                contacts.append({
                    'id': row[0],
                    'company_name': row[1],
                    'company_address': row[2],
                    'contact_name': row[3],
                    'first_name': row[4],
                    'last_name': row[5],
                    'phone': row[6],
                    'email': row[7],
                    'whatsapp': row[8],
                    'source_url': row[9],
                    'method': row[10],
                    'zoho_status': row[11] if len(row) > 11 else 'not_pushed',
                    'zoho_lead_id': row[12] if len(row) > 12 else None,
                    'zoho_pushed_at': str(row[13]) if len(row) > 13 and row[13] else None,
                    'zoho_error': row[14] if len(row) > 14 else None,
                    'created_at': str(row[15]) if len(row) > 15 else (str(row[11]) if len(row) > 11 else '')  # Fallback for old structure
                })
        
        total_pages = (total + per_page - 1) // per_page
        
        return {
            'contacts': contacts,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages
        }
    
    # ===================================================================
    # USER MANAGEMENT METHODS
    # ===================================================================
    
    def _create_default_admin(self):
        """Create default admin user if no users exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check if any users exist
        cursor.execute("SELECT COUNT(*) as count FROM users")
        count = cursor.fetchone()['count'] if self.db_type == 'postgresql' else cursor.fetchone()[0]
        
        if count == 0:
            # Create default admin
            password_hash = generate_password_hash('admin123')
            
            if self.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, is_admin, is_active)
                    VALUES (%s, %s, %s, %s, %s)
                """, ('admin', password_hash, 'System Administrator', True, True))
            else:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, is_admin, is_active)
                    VALUES (?, ?, ?, ?, ?)
                """, ('admin', password_hash, 'System Administrator', 1, 1))
            
            conn.commit()
            logger.info("✅ Created default admin user (username: admin, password: admin123)")
        
        conn.close()
    
    def verify_user(self, username: str, password: str) -> Optional[Dict]:
        """
        Verify user credentials and return user info if valid.
        
        Args:
            username: Username
            password: Plain text password
        
        Returns:
            User dict if valid, None otherwise
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if self.db_type == 'postgresql':
            cursor.execute("""
                SELECT id, username, password_hash, full_name, email, is_admin, is_active
                FROM users
                WHERE username = %s
            """, (username,))
        else:
            cursor.execute("""
                SELECT id, username, password_hash, full_name, email, is_admin, is_active
                FROM users
                WHERE username = ?
            """, (username,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        # Extract data based on DB type
        if self.db_type == 'postgresql':
            user_data = {
                'id': row['id'],
                'username': row['username'],
                'password_hash': row['password_hash'],
                'full_name': row['full_name'],
                'email': row['email'],
                'is_admin': row['is_admin'],
                'is_active': row['is_active']
            }
        else:
            user_data = {
                'id': row[0],
                'username': row[1],
                'password_hash': row[2],
                'full_name': row[3],
                'email': row[4],
                'is_admin': bool(row[5]),
                'is_active': bool(row[6])
            }
        
        # Check if account is active
        if not user_data['is_active']:
            return None
        
        # Verify password
        if not check_password_hash(user_data['password_hash'], password):
            return None
        
        # Update last login
        self._update_last_login(user_data['id'])
        
        # Remove password hash from returned data
        del user_data['password_hash']
        
        return user_data
    
    def _update_last_login(self, user_id: int):
        """Update last login timestamp for user."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if self.db_type == 'postgresql':
            cursor.execute("""
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (user_id,))
        else:
            cursor.execute("""
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (user_id,))
        
        conn.commit()
        conn.close()
    
    def create_user(self, username: str, password: str, full_name: str, email: str, 
                    is_admin: bool, created_by_id: int) -> Dict:
        """
        Create a new user.
        
        Args:
            username: Unique username
            password: Plain text password (will be hashed)
            full_name: User's full name
            email: User's email
            is_admin: Whether user is admin
            created_by_id: ID of admin creating this user
        
        Returns:
            Dict with success status and message
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if username already exists
            if self.db_type == 'postgresql':
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            else:
                cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            
            if cursor.fetchone():
                conn.close()
                return {'success': False, 'message': 'Username already exists'}
            
            # Hash password
            password_hash = generate_password_hash(password)
            
            # Insert new user
            if self.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, email, is_admin, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (username, password_hash, full_name, email, is_admin, created_by_id))
            else:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, email, is_admin, created_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (username, password_hash, full_name, email, 1 if is_admin else 0, created_by_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Created new user: {username}")
            return {'success': True, 'message': 'User created successfully'}
        
        except Exception as e:
            conn.close()
            logger.error(f"Error creating user: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def change_password(self, user_id: int, old_password: str, new_password: str) -> Dict:
        """
        Change user password.
        
        Args:
            user_id: User ID
            old_password: Current password (for verification)
            new_password: New password
        
        Returns:
            Dict with success status and message
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get current password hash
            if self.db_type == 'postgresql':
                cursor.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
            else:
                cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            
            row = cursor.fetchone()
            if not row:
                conn.close()
                return {'success': False, 'message': 'User not found'}
            
            current_hash = row['password_hash'] if self.db_type == 'postgresql' else row[0]
            
            # Verify old password
            if not check_password_hash(current_hash, old_password):
                conn.close()
                return {'success': False, 'message': 'Current password is incorrect'}
            
            # Update with new password
            new_hash = generate_password_hash(new_password)
            
            if self.db_type == 'postgresql':
                cursor.execute("""
                    UPDATE users
                    SET password_hash = %s
                    WHERE id = %s
                """, (new_hash, user_id))
            else:
                cursor.execute("""
                    UPDATE users
                    SET password_hash = ?
                    WHERE id = ?
                """, (new_hash, user_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Password changed for user ID: {user_id}")
            return {'success': True, 'message': 'Password changed successfully'}
        
        except Exception as e:
            conn.close()
            logger.error(f"Error changing password: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def admin_reset_password(self, user_id: int, new_password: str) -> Dict:
        """
        Admin function to reset user password without requiring old password.
        
        Args:
            user_id: User ID
            new_password: New password
        
        Returns:
            Dict with success status and message
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            new_hash = generate_password_hash(new_password)
            
            if self.db_type == 'postgresql':
                cursor.execute("""
                    UPDATE users
                    SET password_hash = %s
                    WHERE id = %s
                """, (new_hash, user_id))
            else:
                cursor.execute("""
                    UPDATE users
                    SET password_hash = ?
                    WHERE id = ?
                """, (new_hash, user_id))
            
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Admin reset password for user ID: {user_id}")
            return {'success': True, 'message': 'Password reset successfully'}
        
        except Exception as e:
            conn.close()
            logger.error(f"Error resetting password: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def get_all_users(self) -> List[Dict]:
        """Get all users (excluding password hashes)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if self.db_type == 'postgresql':
            cursor.execute("""
                SELECT id, username, full_name, email, is_admin, is_active, created_at, last_login
                FROM users
                ORDER BY created_at DESC
            """)
        else:
            cursor.execute("""
                SELECT id, username, full_name, email, is_admin, is_active, created_at, last_login
                FROM users
                ORDER BY created_at DESC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            if self.db_type == 'postgresql':
                users.append({
                    'id': row['id'],
                    'username': row['username'],
                    'full_name': row['full_name'],
                    'email': row['email'],
                    'is_admin': row['is_admin'],
                    'is_active': row['is_active'],
                    'created_at': str(row['created_at']) if row['created_at'] else None,
                    'last_login': str(row['last_login']) if row['last_login'] else None
                })
            else:
                users.append({
                    'id': row[0],
                    'username': row[1],
                    'full_name': row[2],
                    'email': row[3],
                    'is_admin': bool(row[4]),
                    'is_active': bool(row[5]),
                    'created_at': str(row[6]) if row[6] else None,
                    'last_login': str(row[7]) if row[7] else None
                })
        
        return users
    
    def toggle_user_status(self, user_id: int) -> Dict:
        """Toggle user active/inactive status."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute("""
                    UPDATE users
                    SET is_active = NOT is_active
                    WHERE id = %s
                    RETURNING is_active
                """, (user_id,))
                new_status = cursor.fetchone()['is_active']
            else:
                # SQLite doesn't support RETURNING, so we need two queries
                cursor.execute("SELECT is_active FROM users WHERE id = ?", (user_id,))
                current_status = cursor.fetchone()[0]
                new_status = 0 if current_status else 1
                cursor.execute("""
                    UPDATE users
                    SET is_active = ?
                    WHERE id = ?
                """, (new_status, user_id))
            
            conn.commit()
            conn.close()
            
            status_text = 'active' if new_status else 'inactive'
            logger.info(f"✅ User ID {user_id} status changed to: {status_text}")
            return {'success': True, 'message': f'User is now {status_text}'}
        
        except Exception as e:
            conn.close()
            logger.error(f"Error toggling user status: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if self.db_type == 'postgresql':
            cursor.execute("""
                SELECT id, username, full_name, email, is_admin, is_active
                FROM users
                WHERE id = %s
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT id, username, full_name, email, is_admin, is_active
                FROM users
                WHERE id = ?
            """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        if self.db_type == 'postgresql':
            return {
                'id': row['id'],
                'username': row['username'],
                'full_name': row['full_name'],
                'email': row['email'],
                'is_admin': row['is_admin'],
                'is_active': row['is_active']
            }
        else:
            return {
                'id': row[0],
                'username': row[1],
                'full_name': row[2],
                'email': row[3],
                'is_admin': bool(row[4]),
                'is_active': bool(row[5])
            }
    
    # ==================== Processing Jobs Methods ====================
    
    def create_processing_job(self, file_name: str, file_size: int, user_id: int = None) -> int:
        """Create a new processing job record."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if self.db_type == 'postgresql':
            cursor.execute("""
                INSERT INTO processing_jobs (file_name, file_size, user_id, status)
                VALUES (%s, %s, %s, 'pending')
                RETURNING id
            """, (file_name, file_size, user_id))
            job_id = cursor.fetchone()['id']
        else:
            cursor.execute("""
                INSERT INTO processing_jobs (file_name, file_size, user_id, status)
                VALUES (?, ?, ?, 'pending')
            """, (file_name, file_size, user_id))
            job_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        logger.info(f"📝 Created processing job ID: {job_id} for file: {file_name}")
        return job_id
    
    def update_job_status(self, job_id: int, status: str, **kwargs):
        """Update processing job status and optional fields."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Build dynamic update query
        update_fields = ['status = ?'] if self.db_type == 'sqlite' else ['status = %s']
        values = [status]
        
        if status == 'processing' and 'started_at' not in kwargs:
            update_fields.append('started_at = CURRENT_TIMESTAMP')
        elif status in ['completed', 'failed'] and 'completed_at' not in kwargs:
            update_fields.append('completed_at = CURRENT_TIMESTAMP')
        
        for key, value in kwargs.items():
            if self.db_type == 'sqlite':
                update_fields.append(f"{key} = ?")
            else:
                update_fields.append(f"{key} = %s")
            values.append(value)
        
        values.append(job_id)
        query = f"""
            UPDATE processing_jobs 
            SET {', '.join(update_fields)}
            WHERE id = {'?' if self.db_type == 'sqlite' else '%s'}
        """
        
        cursor.execute(query, values)
        conn.commit()
        conn.close()
        logger.info(f"📊 Updated job {job_id} status to: {status}")
    
    def get_job_by_id(self, job_id: int) -> Optional[Dict]:
        """Get processing job by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if self.db_type == 'postgresql':
            cursor.execute("SELECT * FROM processing_jobs WHERE id = %s", (job_id,))
        else:
            cursor.execute("SELECT * FROM processing_jobs WHERE id = ?", (job_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return dict(row) if self.db_type == 'postgresql' else {
            'id': row[0], 'file_name': row[1], 'file_size': row[2],
            'uploaded_at': row[3], 'started_at': row[4], 'completed_at': row[5],
            'status': row[6], 'total_rows': row[7], 'contacts_found': row[8],
            'duplicates_removed': row[9], 'companies_found': row[10],
            'new_companies': row[11], 'api_calls_used': row[12],
            'processing_time': row[13], 'error_message': row[14],
            'output_file': row[15], 'user_id': row[16]
        }
    
    def get_processing_history(self, limit: int = 50, status: str = None, 
                              start_date: str = None, end_date: str = None) -> List[Dict]:
        """Get processing job history with optional filters, including username."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        where_clauses = []
        params = []
        
        if status:
            where_clauses.append(f"pj.status = {'?' if self.db_type == 'sqlite' else '%s'}")
            params.append(status)
        
        if start_date:
            where_clauses.append(f"pj.uploaded_at >= {'?' if self.db_type == 'sqlite' else '%s'}")
            params.append(start_date)
        
        if end_date:
            where_clauses.append(f"pj.uploaded_at <= {'?' if self.db_type == 'sqlite' else '%s'}")
            params.append(end_date)
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        query = f"""
            SELECT pj.*, u.username
            FROM processing_jobs pj
            LEFT JOIN users u ON pj.user_id = u.id
            {where_sql}
            ORDER BY pj.uploaded_at DESC
            LIMIT {limit}
        """
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        if self.db_type == 'postgresql':
            return [dict(row) for row in rows]
        else:
            return [{
                'id': row[0], 'file_name': row[1], 'file_size': row[2],
                'uploaded_at': row[3], 'started_at': row[4], 'completed_at': row[5],
                'status': row[6], 'total_rows': row[7], 'contacts_found': row[8],
                'duplicates_removed': row[9], 'companies_found': row[10],
                'new_companies': row[11], 'api_calls_used': row[12],
                'processing_time': row[13], 'error_message': row[14],
                'output_file': row[15], 'user_id': row[16],
                'username': row[17]
            } for row in rows]
    
    def get_statistics(self, days: int = 90) -> Dict:
        """Get statistics for the last N days."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Check if processing_jobs table exists
            if self.db_type == 'postgresql':
                cursor.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'processing_jobs'
                    )
                """)
                table_exists = cursor.fetchone()[0]
            else:
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='processing_jobs'
                """)
                table_exists = cursor.fetchone() is not None
            
            # Initialize job_stats to zeros (will be updated if table exists)
            job_stats = (0, 0, 0, 0, 0, 0, 0, 0, 0)
            
            # Only query processing_jobs if table exists
            if table_exists:
                try:
                    if self.db_type == 'postgresql':
                        date_filter = f"uploaded_at >= NOW() - INTERVAL '{days} days'"
                    else:
                        date_filter = f"uploaded_at >= datetime('now', '-{days} days')"
                    
                    # Get job statistics
                    cursor.execute(f"""
                        SELECT 
                            COUNT(*) as total_jobs,
                            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_jobs,
                            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed_jobs,
                            SUM(CASE WHEN status = 'processing' THEN 1 ELSE 0 END) as processing_jobs,
                            COALESCE(SUM(contacts_found), 0) as total_contacts,
                            COALESCE(SUM(duplicates_removed), 0) as total_duplicates,
                            COALESCE(SUM(new_companies), 0) as total_new_companies,
                            COALESCE(SUM(api_calls_used), 0) as total_api_calls,
                            COALESCE(AVG(processing_time), 0) as avg_processing_time
                        FROM processing_jobs
                        WHERE {date_filter}
                    """)
                    
                    job_stats = cursor.fetchone()
                    
                    # Handle case where job_stats is None or empty
                    if not job_stats:
                        job_stats = (0, 0, 0, 0, 0, 0, 0, 0, 0)
                    
                    # Convert PostgreSQL dict result to tuple if needed
                    if self.db_type == 'postgresql' and isinstance(job_stats, dict):
                        job_stats = (
                            job_stats.get('total_jobs', 0) or 0,
                            job_stats.get('completed_jobs', 0) or 0,
                            job_stats.get('failed_jobs', 0) or 0,
                            job_stats.get('processing_jobs', 0) or 0,
                            job_stats.get('total_contacts', 0) or 0,
                            job_stats.get('total_duplicates', 0) or 0,
                            job_stats.get('total_new_companies', 0) or 0,
                            job_stats.get('total_api_calls', 0) or 0,
                            job_stats.get('avg_processing_time', 0) or 0
                        )
                    elif not job_stats:
                        job_stats = (0, 0, 0, 0, 0, 0, 0, 0, 0)
                except Exception as e:
                    logger.warning(f"Error fetching job stats from processing_jobs: {str(e)}")
                    job_stats = (0, 0, 0, 0, 0, 0, 0, 0, 0)
            else:
                logger.info("ℹ️  processing_jobs table does not exist, using default zeros for job stats")
            
            # Get total companies and contacts in database - USING SAME PATTERN AS get_stats()
            total_companies = 0
            total_contacts_db = 0
            
            # Get total companies - CALL get_stats() which we know works!
            try:
                stats = self.get_stats()
                total_companies = stats.get('total_companies', 0) or 0
                total_contacts_db = stats.get('total_contacts', 0) or 0
                logger.info(f"📊 Using get_stats() - companies: {total_companies}, contacts: {total_contacts_db}")
            except Exception as e:
                logger.error(f"❌ Error getting stats: {str(e)}", exc_info=True)
                # Fallback to direct query
                try:
                    if self.db_type == 'postgresql':
                        cursor.execute("SELECT COUNT(*) as count FROM companies")
                        result = cursor.fetchone()
                        total_companies = int(result['count'] or 0) if result else 0
                        cursor.execute("SELECT COUNT(*) as count FROM contacts")
                        result = cursor.fetchone()
                        total_contacts_db = int(result['count'] or 0) if result else 0
                    else:
                        cursor.execute("SELECT COUNT(*) FROM companies")
                        result = cursor.fetchone()
                        total_companies = int(result[0] or 0) if result else 0
                        cursor.execute("SELECT COUNT(*) FROM contacts")
                        result = cursor.fetchone()
                        total_contacts_db = int(result[0] or 0) if result else 0
                    logger.info(f"📊 Fallback query - companies: {total_companies}, contacts: {total_contacts_db}")
                except Exception as e2:
                    logger.error(f"❌ Fallback query also failed: {str(e2)}", exc_info=True)
                    total_companies = 0
                    total_contacts_db = 0
            
            # Get contacts by date
            contacts_by_date = []
            try:
                if self.db_type == 'postgresql':
                    cursor.execute(f"""
                        SELECT DATE(created_at) as date, COUNT(*) as count
                        FROM contacts
                        WHERE created_at >= NOW() - INTERVAL '{days} days'
                        GROUP BY DATE(created_at)
                        ORDER BY date DESC
                        LIMIT 30
                    """)
                else:
                    cursor.execute(f"""
                        SELECT DATE(created_at) as date, COUNT(*) as count
                        FROM contacts
                        WHERE created_at >= datetime('now', '-{days} days')
                        GROUP BY DATE(created_at)
                        ORDER BY date DESC
                        LIMIT 30
                    """)
                
                contacts_by_date = cursor.fetchall()
            except Exception as e:
                logger.warning(f"Error fetching contacts by date: {str(e)}")
                contacts_by_date = []
            
            # Handle PostgreSQL vs SQLite result format
            # Extract values safely
            if self.db_type == 'postgresql':
                total_jobs = job_stats[0] if job_stats and len(job_stats) > 0 else 0
                completed_jobs = job_stats[1] if job_stats and len(job_stats) > 1 else 0
                failed_jobs = job_stats[2] if job_stats and len(job_stats) > 2 else 0
                processing_jobs = job_stats[3] if job_stats and len(job_stats) > 3 else 0
                total_contacts = job_stats[4] if job_stats and len(job_stats) > 4 else 0
                total_duplicates = job_stats[5] if job_stats and len(job_stats) > 5 else 0
                total_new_companies = job_stats[6] if job_stats and len(job_stats) > 6 else 0
                total_api_calls = job_stats[7] if job_stats and len(job_stats) > 7 else 0
                avg_processing_time = round(float(job_stats[8] or 0), 2) if job_stats and len(job_stats) > 8 else 0
            else:
                total_jobs = job_stats[0] if job_stats and len(job_stats) > 0 else 0
                completed_jobs = job_stats[1] if job_stats and len(job_stats) > 1 else 0
                failed_jobs = job_stats[2] if job_stats and len(job_stats) > 2 else 0
                processing_jobs = job_stats[3] if job_stats and len(job_stats) > 3 else 0
                total_contacts = job_stats[4] if job_stats and len(job_stats) > 4 else 0
                total_duplicates = job_stats[5] if job_stats and len(job_stats) > 5 else 0
                total_new_companies = job_stats[6] if job_stats and len(job_stats) > 6 else 0
                total_api_calls = job_stats[7] if job_stats and len(job_stats) > 7 else 0
                avg_processing_time = round(float(job_stats[8] or 0), 2) if job_stats and len(job_stats) > 8 else 0
            
            # Ensure database counts are always returned (even if 0)
            # Force convert to int to ensure no None values
            database_companies_val = int(total_companies) if total_companies else 0
            database_contacts_val = int(total_contacts_db) if total_contacts_db else 0
            
            final_stats = {
                'total_jobs': int(total_jobs or 0),
                'completed_jobs': int(completed_jobs or 0),
                'failed_jobs': int(failed_jobs or 0),
                'processing_jobs': int(processing_jobs or 0),
                'total_contacts': int(total_contacts or 0),
                'total_duplicates': int(total_duplicates or 0),
                'total_new_companies': int(total_new_companies or 0),
                'total_api_calls': int(total_api_calls or 0),
                'avg_processing_time': float(avg_processing_time or 0),
                'database_companies': database_companies_val,
                'database_contacts': database_contacts_val,
                'contacts_by_date': [
                    {'date': str(row[0]), 'count': row[1]} 
                    for row in contacts_by_date
                ]
            }
            
            logger.info(f"📊 Final stats being returned: companies={final_stats['database_companies']}, contacts={final_stats['database_contacts']}")
            logger.info(f"📊 Raw values: total_companies={total_companies}, total_contacts_db={total_contacts_db}")
            logger.info(f"📊 Full stats dict: {final_stats}")
            return final_stats
        except Exception as e:
            logger.error(f"Error in get_statistics: {str(e)}", exc_info=True)
            # Return safe defaults
            return {
                'total_jobs': 0,
                'completed_jobs': 0,
                'failed_jobs': 0,
                'processing_jobs': 0,
                'total_contacts': 0,
                'total_duplicates': 0,
                'total_new_companies': 0,
                'total_api_calls': 0,
                'avg_processing_time': 0,
                'database_companies': 0,
                'database_contacts': 0,
                'contacts_by_date': []
            }
        finally:
            conn.close()


    def save_scheduled_campaign(self, campaign_config: Dict) -> Optional[int]:
        """Save a scheduled campaign to database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO scheduled_campaigns 
                    (name, list_key, template_key, subject, from_email, from_name,
                     schedule_type, schedule_time, schedule_day, start_date, end_date,
                     enabled, auto_sync_contacts, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (
                    campaign_config.get('name'),
                    campaign_config.get('list_key'),
                    campaign_config.get('template_key'),
                    campaign_config.get('subject'),
                    campaign_config.get('from_email'),
                    campaign_config.get('from_name'),
                    campaign_config.get('schedule_type'),
                    campaign_config.get('schedule_time'),
                    campaign_config.get('schedule_day'),
                    campaign_config.get('start_date'),
                    campaign_config.get('end_date'),
                    campaign_config.get('enabled', True),
                    campaign_config.get('auto_sync_contacts', True),
                    campaign_config.get('user_id')
                ))
                result = cursor.fetchone()
                campaign_id = result['id'] if result else None
            else:
                cursor.execute("""
                    INSERT INTO scheduled_campaigns 
                    (name, list_key, template_key, subject, from_email, from_name,
                     schedule_type, schedule_time, schedule_day, start_date, end_date,
                     enabled, auto_sync_contacts, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    campaign_config.get('name'),
                    campaign_config.get('list_key'),
                    campaign_config.get('template_key'),
                    campaign_config.get('subject'),
                    campaign_config.get('from_email'),
                    campaign_config.get('from_name'),
                    campaign_config.get('schedule_type'),
                    campaign_config.get('schedule_time'),
                    campaign_config.get('schedule_day'),
                    campaign_config.get('start_date'),
                    campaign_config.get('end_date'),
                    1 if campaign_config.get('enabled', True) else 0,
                    1 if campaign_config.get('auto_sync_contacts', True) else 0,
                    campaign_config.get('user_id')
                ))
                campaign_id = cursor.lastrowid
            
            conn.commit()
            logger.info(f"✅ Saved scheduled campaign: {campaign_id}")
            return campaign_id
            
        except Exception as e:
            logger.error(f"❌ Error saving scheduled campaign: {str(e)}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def get_scheduled_campaign(self, schedule_id: int) -> Optional[Dict]:
        """Get a scheduled campaign by ID."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute("SELECT * FROM scheduled_campaigns WHERE id = %s", (schedule_id,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
            else:
                cursor.execute("SELECT * FROM scheduled_campaigns WHERE id = ?", (schedule_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'id': row[0], 'name': row[1], 'list_key': row[2], 'template_key': row[3],
                        'subject': row[4], 'from_email': row[5], 'from_name': row[6],
                        'schedule_type': row[7], 'schedule_time': row[8], 'schedule_day': row[9],
                        'start_date': row[10], 'end_date': row[11], 'enabled': bool(row[12]),
                        'auto_sync_contacts': bool(row[13]), 'last_sent_at': row[14],
                        'last_campaign_id': row[15], 'status': row[16], 'error_message': row[17],
                        'created_at': row[18], 'updated_at': row[19], 'user_id': row[20]
                    }
            return None
        except Exception as e:
            logger.error(f"❌ Error getting scheduled campaign: {str(e)}")
            return None
        finally:
            conn.close()
    
    def get_all_scheduled_campaigns(self) -> List[Dict]:
        """Get all scheduled campaigns."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT * FROM scheduled_campaigns ORDER BY created_at DESC")
            rows = cursor.fetchall()
            
            if self.db_type == 'postgresql':
                return [dict(row) for row in rows]
            else:
                return [{
                    'id': row[0], 'name': row[1], 'list_key': row[2], 'template_key': row[3],
                    'subject': row[4], 'from_email': row[5], 'from_name': row[6],
                    'schedule_type': row[7], 'schedule_time': row[8], 'schedule_day': row[9],
                    'start_date': row[10], 'end_date': row[11], 'enabled': bool(row[12]),
                    'auto_sync_contacts': bool(row[13]), 'last_sent_at': row[14],
                    'last_campaign_id': row[15], 'status': row[16], 'error_message': row[17],
                    'created_at': row[18], 'updated_at': row[19], 'user_id': row[20]
                } for row in rows]
        except Exception as e:
            logger.error(f"❌ Error getting scheduled campaigns: {str(e)}")
            return []
        finally:
            conn.close()
    
    def update_scheduled_campaign(self, schedule_id: int, updates: Dict) -> bool:
        """Update a scheduled campaign."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            update_fields = []
            values = []
            
            for key, value in updates.items():
                if key in ['enabled', 'auto_sync_contacts']:
                    value = 1 if value else 0 if self.db_type == 'sqlite' else value
                update_fields.append(f"{key} = {'?' if self.db_type == 'sqlite' else '%s'}")
                values.append(value)
            
            update_fields.append(f"updated_at = CURRENT_TIMESTAMP")
            
            if self.db_type == 'postgresql':
                query = f"UPDATE scheduled_campaigns SET {', '.join(update_fields)} WHERE id = %s"
            else:
                query = f"UPDATE scheduled_campaigns SET {', '.join(update_fields)} WHERE id = ?"
            
            values.append(schedule_id)
            cursor.execute(query, values)
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ Error updating scheduled campaign: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def update_scheduled_campaign_status(self, schedule_id: int, status: str, 
                                        campaign_id: str = None, error_message: str = None):
        """Update campaign status after sending."""
        updates = {
            'status': status,
            'last_sent_at': datetime.now().isoformat() if status == 'sent' else None
        }
        if campaign_id:
            updates['last_campaign_id'] = campaign_id
        if error_message:
            updates['error_message'] = error_message
        self.update_scheduled_campaign(schedule_id, updates)
    
    def delete_scheduled_campaign(self, schedule_id: int) -> bool:
        """Delete a scheduled campaign."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute("DELETE FROM scheduled_campaigns WHERE id = %s", (schedule_id,))
            else:
                cursor.execute("DELETE FROM scheduled_campaigns WHERE id = ?", (schedule_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Error deleting scheduled campaign: {str(e)}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def get_all_contacts_for_campaign(self) -> List[Dict]:
        """Get all contacts from database for campaign syncing."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                cursor.execute("""
                    SELECT c.contact_name, c.first_name, c.last_name, c.email, c.phone, c.whatsapp, co.name as company
                    FROM contacts c
                    JOIN companies co ON c.company_id = co.id
                    WHERE c.email IS NOT NULL AND c.email != ''
                    ORDER BY c.created_at DESC
                """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            else:
                cursor.execute("""
                    SELECT c.contact_name, c.first_name, c.last_name, c.email, c.phone, c.whatsapp, co.name as company
                    FROM contacts c
                    JOIN companies co ON c.company_id = co.id
                    WHERE c.email IS NOT NULL AND c.email != ''
                    ORDER BY c.created_at DESC
                """)
                rows = cursor.fetchall()
                return [{
                    'contact_name': row[0], 'first_name': row[1], 'last_name': row[2],
                    'email': row[3], 'phone': row[4], 'whatsapp': row[5], 'company': row[6]
                } for row in rows]
        except Exception as e:
            logger.error(f"❌ Error getting contacts for campaign: {str(e)}")
            return []
        finally:
            conn.close()


# Global database instance
db = ContactDatabase()

