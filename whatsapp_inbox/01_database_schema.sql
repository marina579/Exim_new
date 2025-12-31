-- ============================================
-- WhatsApp Campaign Inbox - Database Schema
-- PostgreSQL (Railway)
-- Version: 1.0
-- ============================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================
-- 1. CAMPAIGNS TABLE
-- Stores outbound campaign metadata
-- ============================================
CREATE TABLE campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    template_name TEXT,
    total_sent INTEGER DEFAULT 0,
    total_replied INTEGER DEFAULT 0,
    total_converted INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed')),
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_campaigns_status ON campaigns(status);
CREATE INDEX idx_campaigns_created ON campaigns(created_at DESC);

-- ============================================
-- 2. CONVERSATIONS TABLE (CRITICAL)
-- One record per WhatsApp user
-- ============================================
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone VARCHAR(20) NOT NULL UNIQUE,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE SET NULL,
    
    -- Language & Intent
    language VARCHAR(5) DEFAULT 'en' CHECK (language IN ('en', 'hi', 'te')),
    intent VARCHAR(50),
    
    -- Funnel Management
    funnel_stage VARCHAR(30) DEFAULT 'NEW' CHECK (funnel_stage IN (
        'NEW', 'ENGAGED', 'QUALIFIED', 'QUOTE_REQUESTED', 
        'CONTACT_SHARED', 'CONVERTED', 'DROPPED'
    )),
    
    -- Lead Scoring
    lead_score INTEGER DEFAULT 0,
    
    -- Activity Flags
    has_user_replied BOOLEAN DEFAULT false,
    is_active BOOLEAN DEFAULT true,
    
    -- Timestamps
    last_message_at TIMESTAMP,
    last_user_message_at TIMESTAMP,
    last_bot_message_at TIMESTAMP,
    first_reply_at TIMESTAMP,
    converted_at TIMESTAMP,
    dropped_at TIMESTAMP,
    
    -- Follow-up Management
    followup_count INTEGER DEFAULT 0,
    next_followup_at TIMESTAMP,
    
    -- Agent Assignment
    assigned_to VARCHAR(100),
    assigned_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

-- Indexes for performance
CREATE INDEX idx_conv_phone ON conversations(phone);
CREATE INDEX idx_conv_campaign ON conversations(campaign_id);
CREATE INDEX idx_conv_funnel ON conversations(funnel_stage);
CREATE INDEX idx_conv_active ON conversations(is_active);
CREATE INDEX idx_conv_last_msg ON conversations(last_message_at DESC);
CREATE INDEX idx_conv_replied ON conversations(has_user_replied);
CREATE INDEX idx_conv_language ON conversations(language);

-- ============================================
-- 3. MESSAGES TABLE
-- ALL inbound & outbound WhatsApp messages
-- ============================================
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    
    -- Message Details
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    sender VARCHAR(20) NOT NULL CHECK (sender IN ('user', 'bot', 'agent', 'campaign')),
    message TEXT NOT NULL,
    
    -- Provider Info (Exotel)
    provider_message_id TEXT,
    exotel_sid TEXT,
    status VARCHAR(20) DEFAULT 'sent' CHECK (status IN ('sent', 'delivered', 'read', 'failed')),
    
    -- Metadata
    raw_payload JSONB,
    media_url TEXT,
    media_type VARCHAR(20),
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT now(),
    delivered_at TIMESTAMP,
    read_at TIMESTAMP
);

-- Indexes
CREATE INDEX idx_msg_conv ON messages(conversation_id);
CREATE INDEX idx_msg_conv_time ON messages(conversation_id, created_at DESC);
CREATE INDEX idx_msg_direction ON messages(direction);
CREATE INDEX idx_msg_created ON messages(created_at DESC);
CREATE INDEX idx_msg_provider ON messages(provider_message_id) WHERE provider_message_id IS NOT NULL;
CREATE INDEX idx_msg_status ON messages(status);

-- ============================================
-- 4. LEADS TABLE
-- Enriched lead data extracted from conversations
-- ============================================
CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE UNIQUE,
    
    -- Contact Info
    name TEXT,
    email VARCHAR(255),
    phone VARCHAR(20) NOT NULL,
    company TEXT,
    
    -- Shipment Details
    origin TEXT,
    destination TEXT,
    mode VARCHAR(20) CHECK (mode IN ('air', 'sea', 'lcl', 'fcl', 'door_to_door')),
    cargo_type TEXT,
    weight TEXT,
    volume TEXT,
    shipment_type VARCHAR(20) CHECK (shipment_type IN ('import', 'export', 'domestic')),
    is_commercial BOOLEAN,
    
    -- Additional Context
    notes TEXT,
    raw_extracted_data JSONB,
    
    -- Lead Status
    status VARCHAR(30) DEFAULT 'new' CHECK (status IN (
        'new', 'engaged', 'qualified', 'quote_requested', 
        'contact_shared', 'converted', 'dropped'
    )),
    
    -- Timestamps
    qualified_at TIMESTAMP,
    contacted_at TIMESTAMP,
    converted_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_leads_conv ON leads(conversation_id);
CREATE INDEX idx_leads_phone ON leads(phone);
CREATE INDEX idx_leads_status ON leads(status);
CREATE INDEX idx_leads_email ON leads(email) WHERE email IS NOT NULL;

-- ============================================
-- 5. AGENT_ACTIONS TABLE
-- Audit trail of agent actions
-- ============================================
CREATE TABLE agent_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    agent_name VARCHAR(100) NOT NULL,
    action_type VARCHAR(50) NOT NULL CHECK (action_type IN (
        'reply', 'funnel_change', 'assign', 'note_added', 'contact_shared', 'read'
    )),
    action_data JSONB,
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_agent_conv ON agent_actions(conversation_id);
CREATE INDEX idx_agent_name ON agent_actions(agent_name);
CREATE INDEX idx_agent_created ON agent_actions(created_at DESC);

-- ============================================
-- 6. EMAIL_NOTIFICATIONS TABLE
-- Internal notifications to sales team
-- ============================================
CREATE TABLE email_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    lead_id UUID REFERENCES leads(id) ON DELETE CASCADE,
    
    -- Email Details
    to_email VARCHAR(255) NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    notification_type VARCHAR(30) CHECK (notification_type IN (
        'new_lead', 'qualified', 'quote_requested', 'contact_shared', 'converted'
    )),
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    
    -- Metadata
    error_message TEXT,
    sent_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX idx_email_status ON email_notifications(status);
CREATE INDEX idx_email_conv ON email_notifications(conversation_id);

-- ============================================
-- 7. REAL-TIME NOTIFICATION TRIGGER
-- Postgres NOTIFY for instant UI updates
-- ============================================

CREATE OR REPLACE FUNCTION notify_new_message()
RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify(
        'new_message',
        json_build_object(
            'message_id', NEW.id,
            'conversation_id', NEW.conversation_id,
            'direction', NEW.direction,
            'sender', NEW.sender,
            'message', NEW.message,
            'created_at', NEW.created_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_notify_new_message
AFTER INSERT ON messages
FOR EACH ROW
EXECUTE FUNCTION notify_new_message();

-- ============================================
-- 8. AUTO-UPDATE CONVERSATION ON MESSAGE
-- Keeps conversation state in sync
-- ============================================

CREATE OR REPLACE FUNCTION update_conversation_on_message()
RETURNS trigger AS $$
BEGIN
    UPDATE conversations
    SET 
        last_message_at = NEW.created_at,
        last_user_message_at = CASE 
            WHEN NEW.direction = 'inbound' THEN NEW.created_at 
            ELSE last_user_message_at 
        END,
        last_bot_message_at = CASE 
            WHEN NEW.direction = 'outbound' AND NEW.sender IN ('bot', 'campaign') THEN NEW.created_at 
            ELSE last_bot_message_at 
        END,
        has_user_replied = CASE 
            WHEN NEW.direction = 'inbound' THEN true 
            ELSE has_user_replied 
        END,
        first_reply_at = CASE 
            WHEN NEW.direction = 'inbound' AND first_reply_at IS NULL THEN NEW.created_at 
            ELSE first_reply_at 
        END,
        is_active = CASE 
            WHEN NEW.direction = 'inbound' THEN true 
            ELSE is_active 
        END,
        funnel_stage = CASE 
            WHEN NEW.direction = 'inbound' AND funnel_stage = 'NEW' THEN 'ENGAGED'
            ELSE funnel_stage 
        END,
        updated_at = NEW.created_at
    WHERE id = NEW.conversation_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_update_conv_on_msg
AFTER INSERT ON messages
FOR EACH ROW
EXECUTE FUNCTION update_conversation_on_message();

-- ============================================
-- 9. FUNNEL STAGE CHANGE NOTIFICATION
-- Notifies when lead moves through funnel
-- ============================================

CREATE OR REPLACE FUNCTION notify_funnel_change()
RETURNS trigger AS $$
BEGIN
    IF OLD.funnel_stage IS DISTINCT FROM NEW.funnel_stage THEN
        PERFORM pg_notify(
            'funnel_change',
            json_build_object(
                'conversation_id', NEW.id,
                'phone', NEW.phone,
                'old_stage', OLD.funnel_stage,
                'new_stage', NEW.funnel_stage,
                'lead_score', NEW.lead_score,
                'changed_at', now()
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_notify_funnel_change
AFTER UPDATE ON conversations
FOR EACH ROW
EXECUTE FUNCTION notify_funnel_change();

-- ============================================
-- 10. HELPER VIEWS
-- Pre-computed views for UI
-- ============================================

-- Active inbox view (what agents see)
CREATE VIEW v_active_inbox AS
SELECT 
    c.id as conversation_id,
    c.phone,
    c.language,
    c.intent,
    c.funnel_stage,
    c.lead_score,
    c.has_user_replied,
    c.last_message_at,
    c.assigned_to,
    l.name as lead_name,
    l.email,
    l.company,
    l.origin,
    l.destination,
    l.mode,
    l.cargo_type,
    (SELECT message 
     FROM messages m 
     WHERE m.conversation_id = c.id 
     ORDER BY m.created_at DESC 
     LIMIT 1) as last_message_preview,
    COALESCE(
        (SELECT COUNT(*) 
         FROM messages m 
         WHERE m.conversation_id = c.id 
         AND m.direction = 'inbound' 
         AND m.status != 'read'), 0
    ) as unread_count
FROM conversations c
LEFT JOIN leads l ON l.conversation_id = c.id
WHERE c.is_active = true
  AND c.funnel_stage != 'DROPPED'
ORDER BY c.last_message_at DESC NULLS LAST;

-- Campaign performance view
CREATE VIEW v_campaign_stats AS
SELECT 
    camp.id,
    camp.name,
    camp.status,
    COUNT(DISTINCT c.id) as total_sent,
    COUNT(DISTINCT c.id) FILTER (WHERE c.has_user_replied = true) as total_replied,
    COUNT(DISTINCT c.id) FILTER (WHERE c.funnel_stage = 'QUALIFIED') as total_qualified,
    COUNT(DISTINCT c.id) FILTER (WHERE c.funnel_stage = 'CONVERTED') as total_converted,
    ROUND(100.0 * COUNT(DISTINCT c.id) FILTER (WHERE c.has_user_replied = true) / 
          NULLIF(COUNT(DISTINCT c.id), 0), 2) as reply_rate,
    ROUND(100.0 * COUNT(DISTINCT c.id) FILTER (WHERE c.funnel_stage = 'CONVERTED') / 
          NULLIF(COUNT(DISTINCT c.id), 0), 2) as conversion_rate
FROM campaigns camp
LEFT JOIN conversations c ON c.campaign_id = camp.id
GROUP BY camp.id, camp.name, camp.status;

-- Funnel breakdown view
CREATE VIEW v_funnel_breakdown AS
SELECT 
    funnel_stage,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage,
    AVG(lead_score)::INTEGER as avg_score
FROM conversations
WHERE is_active = true
GROUP BY funnel_stage
ORDER BY 
    CASE funnel_stage
        WHEN 'NEW' THEN 1
        WHEN 'ENGAGED' THEN 2
        WHEN 'QUALIFIED' THEN 3
        WHEN 'QUOTE_REQUESTED' THEN 4
        WHEN 'CONTACT_SHARED' THEN 5
        WHEN 'CONVERTED' THEN 6
        WHEN 'DROPPED' THEN 7
    END;

-- ============================================
-- SETUP COMPLETE! ✅
-- ============================================

-- Insert sample data (optional - for testing)
INSERT INTO campaigns (name, description, status)
VALUES 
    ('Q1 2025 Export Campaign', 'Target exporters in South India', 'active'),
    ('Import Services Promotion', 'Import customs clearance focus', 'active');

COMMENT ON TABLE campaigns IS 'WhatsApp campaign metadata';
COMMENT ON TABLE conversations IS 'One conversation per WhatsApp user';
COMMENT ON TABLE messages IS 'All inbound/outbound WhatsApp messages';
COMMENT ON TABLE leads IS 'Extracted lead information from conversations';
COMMENT ON TABLE agent_actions IS 'Audit trail of agent interactions';
COMMENT ON TABLE email_notifications IS 'Internal email notifications to sales team';

