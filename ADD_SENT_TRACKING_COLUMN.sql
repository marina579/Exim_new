-- ============================================
-- Add Tracking Columns to chat_history
-- This allows N8N to track which Agent messages have been sent
-- ============================================

-- Add columns to track message sending status
ALTER TABLE chat_history 
ADD COLUMN IF NOT EXISTS sent_via_whatsapp BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS sent_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS exotel_message_id TEXT;

-- Mark all existing messages as already sent (don't re-send old messages)
UPDATE chat_history 
SET sent_via_whatsapp = true 
WHERE role IN ('Customer', 'AI Agent', 'Bot');

-- Keep Agent messages as unsent if they're recent (last 5 minutes)
UPDATE chat_history 
SET sent_via_whatsapp = false 
WHERE role = 'Agent' 
AND created_at > NOW() - INTERVAL '5 minutes';

-- Create index for fast queries
CREATE INDEX IF NOT EXISTS idx_chat_history_unsent 
ON chat_history(role, sent_via_whatsapp, created_at) 
WHERE sent_via_whatsapp = false;

-- Verify the changes
SELECT 
    'chat_history table updated successfully!' as status,
    COUNT(*) FILTER (WHERE sent_via_whatsapp = false AND role = 'Agent') as unsent_agent_messages,
    COUNT(*) FILTER (WHERE sent_via_whatsapp = true) as sent_messages,
    COUNT(*) as total_messages
FROM chat_history;

-- Show unsent Agent messages (these will be picked up by N8N)
SELECT 
    '=== UNSENT AGENT MESSAGES ===' as section;

SELECT 
    id,
    phone,
    content as message,
    created_at,
    sent_via_whatsapp
FROM chat_history
WHERE role = 'Agent' 
AND sent_via_whatsapp = false
ORDER BY created_at DESC
LIMIT 10;

SELECT '
✅ MIGRATION COMPLETE!

Next steps for N8N developer:
1. Create N8N workflow with Schedule Trigger (every 30 seconds)
2. Query: SELECT * FROM chat_history WHERE role=''Agent'' AND sent_via_whatsapp=false
3. Send each message via Exotel WhatsApp API
4. Update: UPDATE chat_history SET sent_via_whatsapp=true WHERE id=?

See: N8N_AGENT_REPLY_WORKFLOW.md for complete guide
' as instructions;

