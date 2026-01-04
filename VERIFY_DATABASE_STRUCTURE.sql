-- ============================================
-- VERIFY YOUR ACTUAL DATABASE STRUCTURE
-- Run this in Railway PostgreSQL to see what you have
-- ============================================

-- 1. List ALL tables in your database
SELECT '=== ALL TABLES ===' as section;
SELECT 
    table_name,
    table_type
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;

-- 2. Check for chat_history table
SELECT '=== CHAT_HISTORY TABLE ===' as section;
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'chat_history'
) as chat_history_exists;

-- 3. Check Lead table columns
SELECT '=== LEAD TABLE COLUMNS ===' as section;
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'Lead'
  AND table_schema = 'public'
ORDER BY ordinal_position;

-- 4. Check conversations table columns
SELECT '=== CONVERSATIONS TABLE COLUMNS ===' as section;
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'conversations'
  AND table_schema = 'public'
ORDER BY ordinal_position;

-- 5. Check messages table columns
SELECT '=== MESSAGES TABLE COLUMNS ===' as section;
SELECT 
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'messages'
  AND table_schema = 'public'
ORDER BY ordinal_position;

-- 6. Check if Lead table has conversation_id or uses phone as key
SELECT '=== LEAD TABLE SAMPLE DATA ===' as section;
SELECT 
    phone,
    name,
    company,
    origin,
    destination,
    mode,
    cargo_type
FROM "Lead"
LIMIT 5;

-- 7. Check conversations table data
SELECT '=== CONVERSATIONS TABLE SAMPLE DATA ===' as section;
SELECT 
    id,
    phone,
    name,
    funnel_stage,
    is_active,
    last_message_at
FROM conversations
LIMIT 5;

-- 8. Check messages table data
SELECT '=== MESSAGES TABLE SAMPLE DATA ===' as section;
SELECT 
    id,
    conversation_id,
    direction,
    sender,
    LEFT(message, 50) as message_preview,
    created_at
FROM messages
ORDER BY created_at DESC
LIMIT 5;

-- 9. Test JOIN between conversations and Lead
SELECT '=== TEST JOIN: conversations + Lead ===' as section;
SELECT 
    c.phone,
    c.name as conversation_name,
    l.name as lead_name,
    l.company,
    l.origin,
    l.destination,
    c.funnel_stage
FROM conversations c
LEFT JOIN "Lead" l ON l.phone = c.phone
LIMIT 5;

-- 10. Count records in each table
SELECT '=== RECORD COUNTS ===' as section;
SELECT 
    'conversations' as table_name,
    COUNT(*) as record_count
FROM conversations
UNION ALL
SELECT 
    'messages' as table_name,
    COUNT(*) as record_count
FROM messages
UNION ALL
SELECT 
    'Lead' as table_name,
    COUNT(*) as record_count
FROM "Lead";

-- ============================================
-- INSTRUCTIONS:
-- Copy the entire output and paste it here or share with me
-- This will help me understand your exact database structure
-- ============================================

