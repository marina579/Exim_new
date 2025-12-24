#!/usr/bin/env python3
"""
Fix existing contacts in database by re-merging them with improved logic.
This will combine contacts that have complementary data (email + phone).
"""

import sys
from database import db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_contacts():
    """Re-merge contacts for each company with improved logic."""
    
    print("\n" + "="*70)
    print("🔧 FIX EXISTING CONTACTS - Improved Merging")
    print("="*70 + "\n")
    
    print("This will re-merge contacts using improved logic:")
    print("✅ Combine contacts with email + phone into single row")
    print("✅ Keep separate rows only for truly different contacts")
    print("✅ Fill in missing data from complementary contacts\n")
    
    response = input("Continue? (yes/no): ").strip().lower()
    if response != 'yes':
        print("❌ Fix cancelled.")
        return
    
    print("\n🔄 Processing...\n")
    
    conn = db._get_connection()
    cursor = conn.cursor()
    
    # Get all companies
    cursor.execute("SELECT id, name FROM companies")
    companies = cursor.fetchall()
    
    total_before = 0
    total_after = 0
    companies_processed = 0
    
    for company_row in companies:
        company_id = company_row['id'] if db.db_type == 'postgresql' else company_row[0]
        company_name = company_row['name'] if db.db_type == 'postgresql' else company_row[1]
        
        # Get contacts for this company
        cursor.execute(
            "SELECT * FROM contacts WHERE company_id = %s" if db.db_type == 'postgresql'
            else "SELECT * FROM contacts WHERE company_id = ?",
            (company_id,)
        )
        raw_contacts = cursor.fetchall()
        
        if not raw_contacts or len(raw_contacts) <= 1:
            continue
        
        # Convert to list of dicts
        contacts_list = []
        for row in raw_contacts:
            if db.db_type == 'postgresql':
                contact = dict(row)
            else:
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
                    'confidence': row[10] if len(row) > 10 else 100
                }
            contacts_list.append(contact)
        
        original_count = len(contacts_list)
        total_before += original_count
        
        # Apply new merge logic
        merged_contacts = db._merge_duplicate_contacts(contacts_list)
        merged_count = len(merged_contacts)
        total_after += merged_count
        
        if original_count > merged_count:
            print(f"📦 {company_name}:")
            print(f"   Before: {original_count} contacts")
            print(f"   After:  {merged_count} contacts")
            print(f"   Merged: {original_count - merged_count} duplicates\n")
            companies_processed += 1
            
            # Delete old contacts
            cursor.execute(
                "DELETE FROM contacts WHERE company_id = %s" if db.db_type == 'postgresql'
                else "DELETE FROM contacts WHERE company_id = ?",
                (company_id,)
            )
            
            # Insert merged contacts
            for contact in merged_contacts:
                # Extract name from email if empty
                contact_name = contact.get('contact_name', '').strip()
                email = contact.get('email', '').strip()
                
                if not contact_name and email and '@' in email:
                    username = email.split('@')[0]
                    name = username.replace('.', ' ').replace('_', ' ').replace('-', ' ')
                    name_parts = [part.capitalize() for part in name.split() if len(part) > 1 and not part.isdigit()]
                    if len(name_parts) > 3:
                        name_parts = name_parts[:2]
                    contact_name = ' '.join(name_parts)
                
                if db.db_type == 'postgresql':
                    cursor.execute("""
                        INSERT INTO contacts 
                        (company_id, contact_name, first_name, last_name, phone, email, whatsapp, source_url, method, confidence)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        company_id,
                        contact_name,
                        contact.get('first_name', ''),
                        contact.get('last_name', ''),
                        contact.get('phone', ''),
                        email,
                        contact.get('whatsapp', ''),
                        contact.get('source_url', ''),
                        contact.get('method', ''),
                        contact.get('confidence', 100)
                    ))
                else:
                    cursor.execute("""
                        INSERT INTO contacts 
                        (company_id, contact_name, first_name, last_name, phone, email, whatsapp, source_url, method, confidence)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        company_id,
                        contact_name,
                        contact.get('first_name', ''),
                        contact.get('last_name', ''),
                        contact.get('phone', ''),
                        email,
                        contact.get('whatsapp', ''),
                        contact.get('source_url', ''),
                        contact.get('method', ''),
                        contact.get('confidence', 100)
                    ))
            
            conn.commit()
    
    conn.close()
    
    print("\n" + "="*70)
    print("✅ FIX COMPLETE!")
    print("="*70)
    print(f"\n📊 Summary:")
    print(f"   Companies processed: {companies_processed}")
    print(f"   Total contacts before: {total_before}")
    print(f"   Total contacts after: {total_after}")
    print(f"   Contacts merged: {total_before - total_after}")
    print(f"   Space saved: {((total_before - total_after) / total_before * 100):.1f}%\n")
    
    print("✅ Refresh your browser to see the improved contacts!\n")

if __name__ == '__main__':
    try:
        fix_contacts()
    except KeyboardInterrupt:
        print("\n\n❌ Fix cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

