-- ============================================
-- TEST WHATSAPP INTEGRATION
-- Run this in Railway PostgreSQL to test the integration
-- ============================================

-- STEP 1: Check if tables exist
SELECT 'Checking tables...' as status;

SELECT 
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
FROM information_schema.tables t
WHERE table_schema = 'public' 
AND table_name IN ('conversations', 'messages', 'leads', 'campaigns')
ORDER BY table_name;

-- ============================================
-- STEP 2: Insert Test Campaign
-- ============================================
SELECT 'Creating test campaign...' as status;

INSERT INTO campaigns (id, name, description, status)
VALUES (
    '11111111-1111-1111-1111-111111111111',
    'Test Campaign - WhatsApp Integration',
    'Testing data flow from N8N to UI',
    'active'
)
ON CONFLICT (id) DO NOTHING;

-- ============================================
-- STEP 3: Insert Test Conversation
-- ============================================
SELECT 'Creating test conversation...' as status;

INSERT INTO conversations (
    id,
    phone,
    name,
    campaign_id,
    language,
    funnel_stage,
    lead_score,
    has_user_replied,
    is_active,
    last_message_at
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    '+91-9876543210',
    'Rajesh Kumar',
    '11111111-1111-1111-1111-111111111111',
    'en',
    'ENGAGED',
    45,
    true,
    true,
    CURRENT_TIMESTAMP
)
ON CONFLICT (phone) DO UPDATE SET
    name = EXCLUDED.name,
    funnel_stage = EXCLUDED.funnel_stage,
    lead_score = EXCLUDED.lead_score,
    is_active = EXCLUDED.is_active,
    last_message_at = EXCLUDED.last_message_at;

-- ============================================
-- STEP 4: Insert Test Lead
-- ============================================
SELECT 'Creating test lead...' as status;

INSERT INTO "Lead" (
    id,
    conversation_id,
    name,
    email,
    phone,
    company,
    origin,
    destination,
    mode,
    cargo_type,
    notes,
    status
) VALUES (
    '33333333-3333-3333-3333-333333333333',
    '22222222-2222-2222-2222-222222222222',
    'Rajesh Kumar',
    'rajesh@kumarelectronics.com',
    '+91-9876543210',
    'Kumar Electronics',
    'China',
    'India',
    'sea',
    'Electronics',
    'Interested in importing mobile phones and accessories. Around 500 units per month.',
    'engaged'
)
ON CONFLICT (conversation_id) DO UPDATE SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    company = EXCLUDED.company,
    origin = EXCLUDED.origin,
    destination = EXCLUDED.destination,
    mode = EXCLUDED.mode,
    cargo_type = EXCLUDED.cargo_type,
    notes = EXCLUDED.notes,
    status = EXCLUDED.status;

-- ============================================
-- STEP 5: Insert Test Messages (Chat History)
-- ============================================
SELECT 'Creating test messages...' as status;

-- Message 1: User sends first message (INBOUND)
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    status,
    created_at
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    'inbound',
    'user',
    'Hi! I need help with importing electronics from China.',
    'delivered',
    CURRENT_TIMESTAMP - INTERVAL '10 minutes'
);

-- Message 2: Bot responds (OUTBOUND)
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    status,
    created_at
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    'outbound',
    'bot',
    'Hello! We are Marineco, your trusted partner for import/export services. How can we help you today?',
    'read',
    CURRENT_TIMESTAMP - INTERVAL '9 minutes'
);

-- Message 3: User provides details (INBOUND)
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    status,
    created_at
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    'inbound',
    'user',
    'Mobile phones and accessories. Around 500 units per month.',
    'delivered',
    CURRENT_TIMESTAMP - INTERVAL '8 minutes'
);

-- Message 4: Bot asks for more info (OUTBOUND)
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    status,
    created_at
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    'outbound',
    'bot',
    'Great! I can help with that. What type of electronics are you looking to import?',
    'read',
    CURRENT_TIMESTAMP - INTERVAL '7 minutes'
);

-- Message 5: Agent takes over (OUTBOUND)
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    status,
    created_at
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    'outbound',
    'agent',
    'Hi Rajesh! This is Sarita from Marineco. I can help you with sea freight from China to India. Would you like a quote?',
    'delivered',
    CURRENT_TIMESTAMP - INTERVAL '5 minutes'
);

-- Message 6: User responds positively (INBOUND)
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    status,
    created_at
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    'inbound',
    'user',
    'Yes please! What information do you need?',
    'delivered',
    CURRENT_TIMESTAMP - INTERVAL '3 minutes'
);

-- ============================================
-- STEP 6: Insert Agent Action Log
-- ============================================
SELECT 'Logging agent action...' as status;

INSERT INTO agent_actions (
    conversation_id,
    agent_name,
    action_type,
    action_data
) VALUES (
    '22222222-2222-2222-2222-222222222222',
    'Sarita',
    'reply',
    '{"message": "Agent took over conversation"}'::jsonb
);

-- ============================================
-- STEP 7: Verify Data
-- ============================================
SELECT 'Verification Results:' as status;

-- Check conversation
SELECT 
    'Conversation Created' as test,
    phone,
    name,
    funnel_stage,
    lead_score,
    has_user_replied,
    is_active
FROM conversations
WHERE phone = '+91-9876543210';

-- Check messages count
SELECT 
    'Messages Created' as test,
    COUNT(*) as message_count,
    COUNT(*) FILTER (WHERE direction = 'inbound') as inbound_count,
    COUNT(*) FILTER (WHERE direction = 'outbound') as outbound_count,
    COUNT(*) FILTER (WHERE sender = 'user') as user_messages,
    COUNT(*) FILTER (WHERE sender = 'bot') as bot_messages,
    COUNT(*) FILTER (WHERE sender = 'agent') as agent_messages
FROM messages
WHERE conversation_id = '22222222-2222-2222-2222-222222222222';

-- Check lead
SELECT 
    'Lead Created' as test,
    name,
    email,
    company,
    origin,
    destination,
    mode,
    status
FROM leads
WHERE conversation_id = '22222222-2222-2222-2222-222222222222';

-- ============================================
-- STEP 8: Test UI Query (Same as whatsapp_db.py)
-- ============================================
SELECT 'Testing UI Query:' as status;

SELECT 
    c.id as conversation_id,
    c.phone,
    c.name,
    c.language,
    c.funnel_stage,
    c.lead_score,
    c.has_user_replied,
    c.last_message_at,
    l.name as lead_name,
    l.email,
    l.company,
    l.origin,
    l.destination,
    (SELECT message 
     FROM messages m 
     WHERE m.conversation_id = c.id 
     ORDER BY m.created_at DESC 
     LIMIT 1) as last_message_preview,
    (SELECT COUNT(*) 
     FROM messages m 
     WHERE m.conversation_id = c.id 
     AND m.direction = 'inbound' 
     AND m.status != 'read') as unread_count
FROM conversations c
LEFT JOIN leads l ON l.conversation_id = c.id
WHERE c.phone = '+91-9876543210'
  AND c.is_active = true;

-- ============================================
-- STEP 9: Test Message History Query
-- ============================================
SELECT 'Testing Message History Query:' as status;

SELECT 
    id,
    direction,
    sender,
    message,
    status,
    created_at,
    CASE 
        WHEN direction = 'inbound' THEN 'User'
        WHEN sender = 'bot' THEN 'Bot'
        WHEN sender = 'agent' THEN 'Agent'
        ELSE sender
    END as display_sender
FROM messages
WHERE conversation_id = '22222222-2222-2222-2222-222222222222'
ORDER BY created_at ASC;

-- ============================================
-- ✅ SUCCESS!
-- ============================================
SELECT '
╔══════════════════════════════════════════════════════════════╗
║                    ✅ TEST COMPLETE!                         ║
╚══════════════════════════════════════════════════════════════╝

Next Steps:
1. Open your Flask app: https://your-app.railway.app/whatsapp/inbox
2. You should see "Rajesh Kumar" in the conversation list
3. Click on it to see the full chat history
4. Try sending a message from the UI

If you see the conversation and messages, your integration is working! 🎉

Your N8N developer just needs to:
- Insert data into these same tables
- Use the same structure (conversation_id, direction, sender, message)
- The UI will automatically display everything!

' as instructions;

-- ============================================
-- CLEANUP (Optional - run this to remove test data)
-- ============================================
-- Uncomment the lines below to delete test data:

-- DELETE FROM messages WHERE conversation_id = '22222222-2222-2222-2222-222222222222';
-- DELETE FROM leads WHERE conversation_id = '22222222-2222-2222-2222-222222222222';
-- DELETE FROM agent_actions WHERE conversation_id = '22222222-2222-2222-2222-222222222222';
-- DELETE FROM conversations WHERE id = '22222222-2222-2222-2222-222222222222';
-- DELETE FROM campaigns WHERE id = '11111111-1111-1111-1111-111111111111';

