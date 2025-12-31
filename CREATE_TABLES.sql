-- Quick Setup: WhatsApp Inbox Tables
-- Copy ALL of this and paste into Railway Query tab

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- 1. CAMPAIGNS
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    status VARCHAR(20) DEFAULT 'active',
    start_date TIMESTAMP DEFAULT now(),
    created_at TIMESTAMP DEFAULT now()
);

-- 2. CONVERSATIONS  
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL UNIQUE,
    name TEXT,
    campaign_id UUID REFERENCES campaigns(id),
    language VARCHAR(5) DEFAULT 'en',
    funnel_stage VARCHAR(30) DEFAULT 'NEW',
    lead_score INTEGER DEFAULT 0,
    has_user_replied BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    last_message_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT now()
);

-- 3. MESSAGES
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    direction VARCHAR(10) NOT NULL,
    sender VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'sent',
    created_at TIMESTAMP DEFAULT now()
);

-- 4. LEADS
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE UNIQUE,
    name TEXT,
    email VARCHAR(255),
    phone VARCHAR(20) NOT NULL,
    company TEXT,
    origin TEXT,
    destination TEXT,
    notes TEXT,
    status VARCHAR(30) DEFAULT 'new',
    created_at TIMESTAMP DEFAULT now()
);

-- 5. AGENT ACTIONS
CREATE TABLE IF NOT EXISTS agent_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL,
    action_data JSONB,
    created_at TIMESTAMP DEFAULT now()
);

-- 6. EMAIL NOTIFICATIONS
CREATE TABLE IF NOT EXISTS email_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    to_email VARCHAR(255) NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT now()
);

-- 7. PERMISSION AUDIT
CREATE TABLE IF NOT EXISTS permission_audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    old_permissions JSONB,
    new_permissions JSONB,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add permissions to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions JSONB DEFAULT '{"whatsapp": false, "contacts": false}'::jsonb;

-- Update admin user
UPDATE users SET 
    role = 'admin',
    permissions = '{"whatsapp": true, "contacts": true, "campaigns": true, "admin": true}'::jsonb
WHERE is_admin = true;

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_conv_phone ON conversations(phone);
CREATE INDEX IF NOT EXISTS idx_conv_funnel ON conversations(funnel_stage);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_msg_created ON messages(created_at DESC);

-- Insert sample campaign
INSERT INTO campaigns (name, description, status)
VALUES ('Test Campaign', 'Initial test campaign', 'active')
ON CONFLICT DO NOTHING;

-- Verify
SELECT 'SUCCESS! Tables created:' as status;
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('campaigns', 'conversations', 'messages', 'leads', 'agent_actions', 'email_notifications')
ORDER BY table_name;

