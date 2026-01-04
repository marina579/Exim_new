#!/usr/bin/env python3
"""
Verify WhatsApp Integration - Database Structure and Data Check
Run this script to verify your database setup for WhatsApp UI
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL not found in environment variables")
    print("Make sure you have .env file with DATABASE_URL set")
    sys.exit(1)

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    print("❌ ERROR: psycopg2 not installed")
    print("Run: pip install psycopg2-binary")
    sys.exit(1)

def print_section(title):
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80 + "\n")

def run_query(cursor, query, description):
    try:
        cursor.execute(query)
        results = cursor.fetchall()
        
        if not results:
            print(f"❌ No data found for: {description}")
            return None
        
        print(f"✅ {description}:")
        for row in results:
            print(f"   {dict(row)}")
        return results
    except Exception as e:
        print(f"❌ Error in {description}: {str(e)}")
        return None

def main():
    print("\n🔍 WHATSAPP INTEGRATION VERIFICATION TOOL")
    print("="*80)
    
    try:
        # Connect to database
        print("\n📡 Connecting to PostgreSQL database...")
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        print("✅ Connected successfully!")
        
        # 1. Check all tables
        print_section("1. ALL TABLES IN DATABASE")
        cursor.execute("""
            SELECT table_name, table_type
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        for table in tables:
            print(f"   📋 {table['table_name']} ({table['table_type']})")
        
        # 2. Check if chat_history exists
        print_section("2. CHECKING FOR 'chat_history' TABLE")
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'chat_history'
            ) as exists;
        """)
        result = cursor.fetchone()
        if result['exists']:
            print("   ✅ chat_history table EXISTS")
        else:
            print("   ❌ chat_history table DOES NOT EXIST")
            print("   ℹ️  Using 'messages' table for chat history instead")
        
        # 3. Check Lead table structure
        print_section("3. LEAD TABLE STRUCTURE")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'Lead'
            AND table_schema = 'public'
            ORDER BY ordinal_position;
        """)
        lead_columns = cursor.fetchall()
        if lead_columns:
            print("   Columns in 'Lead' table:")
            for col in lead_columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                print(f"      • {col['column_name']:<20} {col['data_type']:<15} {nullable}")
        else:
            print("   ❌ Lead table not found")
        
        # 4. Check conversations table structure
        print_section("4. CONVERSATIONS TABLE STRUCTURE")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'conversations'
            AND table_schema = 'public'
            ORDER BY ordinal_position;
        """)
        conv_columns = cursor.fetchall()
        if conv_columns:
            print("   Columns in 'conversations' table:")
            for col in conv_columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                print(f"      • {col['column_name']:<20} {col['data_type']:<15} {nullable}")
        else:
            print("   ❌ conversations table not found")
        
        # 5. Check messages table structure
        print_section("5. MESSAGES TABLE STRUCTURE")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'messages'
            AND table_schema = 'public'
            ORDER BY ordinal_position;
        """)
        msg_columns = cursor.fetchall()
        if msg_columns:
            print("   Columns in 'messages' table:")
            for col in msg_columns:
                nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
                print(f"      • {col['column_name']:<20} {col['data_type']:<15} {nullable}")
        else:
            print("   ❌ messages table not found")
        
        # 6. Count records
        print_section("6. RECORD COUNTS")
        
        try:
            cursor.execute('SELECT COUNT(*) as count FROM "Lead"')
            lead_count = cursor.fetchone()['count']
            print(f"   📊 Lead table: {lead_count} records")
        except:
            print("   ❌ Could not count Lead records")
        
        try:
            cursor.execute('SELECT COUNT(*) as count FROM conversations')
            conv_count = cursor.fetchone()['count']
            print(f"   📊 conversations table: {conv_count} records")
        except:
            print("   ❌ Could not count conversations records")
        
        try:
            cursor.execute('SELECT COUNT(*) as count FROM messages')
            msg_count = cursor.fetchone()['count']
            print(f"   📊 messages table: {msg_count} records")
        except:
            print("   ❌ Could not count messages records")
        
        # 7. Sample data from Lead
        print_section("7. SAMPLE DATA FROM LEAD TABLE")
        run_query(cursor, """
            SELECT phone, name, company, origin, destination, mode, cargo_type
            FROM "Lead"
            LIMIT 5;
        """, "First 5 leads")
        
        # 8. Sample data from conversations
        print_section("8. SAMPLE DATA FROM CONVERSATIONS TABLE")
        run_query(cursor, """
            SELECT id, phone, name, funnel_stage, is_active, 
                   last_message_at, created_at
            FROM conversations
            ORDER BY created_at DESC
            LIMIT 5;
        """, "Last 5 conversations")
        
        # 9. Sample data from messages
        print_section("9. SAMPLE DATA FROM MESSAGES TABLE")
        run_query(cursor, """
            SELECT id, conversation_id, direction, sender, 
                   LEFT(message, 50) as message_preview, created_at
            FROM messages
            ORDER BY created_at DESC
            LIMIT 5;
        """, "Last 5 messages")
        
        # 10. Test JOIN
        print_section("10. TEST JOIN: conversations + Lead")
        run_query(cursor, """
            SELECT 
                c.phone,
                c.name as conversation_name,
                c.funnel_stage,
                c.is_active,
                l.name as lead_name,
                l.company,
                l.origin,
                l.destination
            FROM conversations c
            LEFT JOIN "Lead" l ON l.phone = c.phone
            WHERE c.is_active = true
            LIMIT 5;
        """, "Active conversations with lead data")
        
        # 11. Check phone number formats
        print_section("11. PHONE NUMBER FORMAT CHECK")
        print("   Checking if phone formats match between tables...")
        
        try:
            cursor.execute('SELECT DISTINCT phone FROM conversations LIMIT 3')
            conv_phones = cursor.fetchall()
            print("\n   Sample phones from conversations:")
            for p in conv_phones:
                print(f"      {p['phone']}")
        except Exception as e:
            print(f"   ❌ Error getting conversation phones: {e}")
        
        try:
            cursor.execute('SELECT DISTINCT phone FROM "Lead" LIMIT 3')
            lead_phones = cursor.fetchall()
            print("\n   Sample phones from Lead:")
            for p in lead_phones:
                print(f"      {p['phone']}")
        except Exception as e:
            print(f"   ❌ Error getting Lead phones: {e}")
        
        # Final summary
        print_section("✅ VERIFICATION COMPLETE")
        
        print("\n📋 SUMMARY:")
        print("   ✅ Database connection: Working")
        print(f"   ✅ Lead table: {lead_count if 'lead_count' in locals() else '?'} records")
        print(f"   ✅ conversations table: {conv_count if 'conv_count' in locals() else '?'} records")
        print(f"   ✅ messages table: {msg_count if 'msg_count' in locals() else '?'} records")
        
        print("\n🎯 NEXT STEPS:")
        if 'conv_count' in locals() and conv_count > 0:
            print("   ✅ You have data! Your WhatsApp UI should show conversations")
            print("   🌐 Open: http://localhost:5000/whatsapp/inbox (or your Railway URL)")
        else:
            print("   ⚠️  No conversations found. Your N8N developer needs to:")
            print("      1. Create conversations when WhatsApp messages arrive")
            print("      2. Insert messages into the messages table")
            print("      3. Optionally update Lead table with extracted info")
        
        print("\n" + "="*80)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print("\nTroubleshooting:")
        print("  1. Check your DATABASE_URL in .env file")
        print("  2. Make sure PostgreSQL is accessible")
        print("  3. Verify your database credentials")
        sys.exit(1)

if __name__ == "__main__":
    main()

