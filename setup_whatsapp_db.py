#!/usr/bin/env python3
"""
Script to setup WhatsApp Inbox database tables on Railway PostgreSQL
Run this once to create all required tables.

Usage:
    python setup_whatsapp_db.py
"""

import os
import psycopg2
from psycopg2 import sql

def read_sql_file(filename):
    """Read SQL file contents"""
    with open(filename, 'r') as f:
        return f.read()

def execute_sql(cursor, sql_content, description):
    """Execute SQL and handle errors"""
    try:
        cursor.execute(sql_content)
        print(f"✅ {description} - SUCCESS")
        return True
    except Exception as e:
        print(f"❌ {description} - FAILED: {str(e)}")
        return False

def main():
    # Get DATABASE_URL from environment
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("❌ ERROR: DATABASE_URL environment variable not set!")
        print("\nFor Railway, get it from:")
        print("  Railway Dashboard → PostgreSQL → Variables → DATABASE_URL")
        print("\nThen run:")
        print("  export DATABASE_URL='your_database_url_here'")
        print("  python setup_whatsapp_db.py")
        return
    
    print("🚀 Starting WhatsApp Inbox Database Setup...\n")
    
    try:
        # Connect to database
        print("📡 Connecting to PostgreSQL...")
        conn = psycopg2.connect(database_url)
        conn.autocommit = True
        cursor = conn.cursor()
        print("✅ Connected successfully!\n")
        
        # Read SQL files
        print("📄 Reading SQL schema files...\n")
        
        sql_files = [
            ('whatsapp_inbox/01_database_schema.sql', 'WhatsApp Inbox Tables'),
            ('whatsapp_inbox/06_RBAC_SCHEMA.sql', 'RBAC Tables (Role-Based Access Control)')
        ]
        
        success_count = 0
        
        for sql_file, description in sql_files:
            if os.path.exists(sql_file):
                print(f"📝 Creating {description}...")
                sql_content = read_sql_file(sql_file)
                if execute_sql(cursor, sql_content, description):
                    success_count += 1
                print()
            else:
                print(f"⚠️  File not found: {sql_file}")
                print()
        
        # Verify tables were created
        print("🔍 Verifying tables created...\n")
        
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN (
                'campaigns', 'conversations', 'messages', 'leads', 
                'agent_actions', 'email_notifications',
                'roles', 'permissions', 'role_permissions', 'user_roles'
            )
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        
        if tables:
            print("✅ Successfully created tables:")
            for table in tables:
                print(f"   • {table[0]}")
            print()
        else:
            print("❌ No tables found!")
            print()
        
        # Insert default roles
        print("👥 Creating default roles...")
        
        default_roles_sql = """
        -- Insert default roles (if not exist)
        INSERT INTO roles (name, description) 
        VALUES 
            ('admin', 'Full system access'),
            ('whatsapp_agent', 'WhatsApp inbox access only'),
            ('ui_viewer', 'UI access without WhatsApp'),
            ('full_access', 'Both WhatsApp and full UI access')
        ON CONFLICT (name) DO NOTHING;
        
        -- Insert default permissions
        INSERT INTO permissions (code, name, description)
        VALUES
            ('whatsapp.view', 'View WhatsApp Inbox', 'Can view WhatsApp conversations'),
            ('whatsapp.reply', 'Reply to WhatsApp', 'Can send replies in WhatsApp'),
            ('whatsapp.manage', 'Manage WhatsApp', 'Can update funnel stages and lead info'),
            ('ui.dashboard', 'Access Dashboard', 'Can access main dashboard'),
            ('ui.contacts', 'Access Contacts', 'Can view and manage contacts'),
            ('ui.campaigns', 'Access Campaigns', 'Can view and manage campaigns'),
            ('admin.users', 'Manage Users', 'Can create and manage users'),
            ('admin.settings', 'Manage Settings', 'Can modify system settings')
        ON CONFLICT (code) DO NOTHING;
        
        -- Assign permissions to roles
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.name = 'admin'  -- Admin gets all permissions
        ON CONFLICT DO NOTHING;
        
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        JOIN permissions p ON p.code IN ('whatsapp.view', 'whatsapp.reply', 'whatsapp.manage')
        WHERE r.name = 'whatsapp_agent'
        ON CONFLICT DO NOTHING;
        
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        JOIN permissions p ON p.code IN ('ui.dashboard', 'ui.contacts', 'ui.campaigns')
        WHERE r.name = 'ui_viewer'
        ON CONFLICT DO NOTHING;
        
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id
        FROM roles r
        JOIN permissions p ON p.code NOT IN ('admin.users', 'admin.settings')
        WHERE r.name = 'full_access'
        ON CONFLICT DO NOTHING;
        """
        
        if execute_sql(cursor, default_roles_sql, "Default Roles and Permissions"):
            print()
        
        # Show role summary
        cursor.execute("""
            SELECT r.name, COUNT(rp.permission_id) as permission_count
            FROM roles r
            LEFT JOIN role_permissions rp ON r.id = rp.id
            GROUP BY r.name
            ORDER BY r.name;
        """)
        
        roles = cursor.fetchall()
        if roles:
            print("📋 Roles created:")
            for role, perm_count in roles:
                print(f"   • {role}: {perm_count} permissions")
            print()
        
        # Summary
        print("=" * 50)
        print(f"✅ Setup complete! ({success_count}/2 schema files)")
        print("=" * 50)
        print("\n📌 Next Steps:")
        print("1. Push code to GitHub: git add . && git commit -m 'Add WhatsApp inbox' && git push")
        print("2. Railway will auto-deploy")
        print("3. Visit: https://your-app.railway.app/whatsapp/inbox")
        print("4. Configure n8n webhooks (see 03_N8N_DEVELOPER_GUIDE.md)")
        print("\n✨ Done!")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        print("\nMake sure:")
        print("  1. DATABASE_URL is correct")
        print("  2. PostgreSQL is running")
        print("  3. You have network access to Railway")

if __name__ == '__main__':
    main()

