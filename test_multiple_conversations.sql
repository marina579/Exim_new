-- ============================================
-- TEST: Multiple Conversations in WhatsApp UI
-- Run this to add 3 more test conversations
-- ============================================

-- CONVERSATION 2: Priya Sharma (Mumbai → Singapore)
-- ============================================

INSERT INTO "Lead" (phone, name, language, company, origin, destination, mode, cargo_type, status)
VALUES ('+919988776655', 'Priya Sharma', 'en', 'Sharma Exports', 'Mumbai', 'Singapore', 'sea', 'textiles', 'QUALIFIED')
ON CONFLICT (phone) DO UPDATE SET
    name = EXCLUDED.name,
    company = EXCLUDED.company,
    origin = EXCLUDED.origin,
    destination = EXCLUDED.destination;

INSERT INTO chat_history (phone, role, content, created_at)
VALUES 
    ('+919988776655', 'Customer', 'Hi, I need a freight quote', CURRENT_TIMESTAMP - INTERVAL '30 minutes'),
    ('+919988776655', 'AI Agent', 'Hello! I can help you with that. What are you looking to ship?', CURRENT_TIMESTAMP - INTERVAL '29 minutes'),
    ('+919988776655', 'Customer', 'I need to export textiles from Mumbai to Singapore', CURRENT_TIMESTAMP - INTERVAL '28 minutes'),
    ('+919988776655', 'AI Agent', 'Great! Textiles from Mumbai to Singapore. What is the approximate weight or volume?', CURRENT_TIMESTAMP - INTERVAL '27 minutes'),
    ('+919988776655', 'Customer', 'Around 5000 kgs', CURRENT_TIMESTAMP - INTERVAL '26 minutes');

-- CONVERSATION 3: Ramesh Kumar (Delhi → New York)
-- ============================================

INSERT INTO "Lead" (phone, name, language, company, origin, destination, mode, cargo_type, status, is_commercial)
VALUES ('+918877665544', 'Ramesh Kumar', 'hi', 'Kumar Electronics', 'Delhi', 'New York', 'air', 'electronics', 'QUOTE_REQUESTED', true)
ON CONFLICT (phone) DO UPDATE SET
    name = EXCLUDED.name,
    company = EXCLUDED.company,
    origin = EXCLUDED.origin,
    destination = EXCLUDED.destination;

INSERT INTO chat_history (phone, role, content, created_at)
VALUES 
    ('+918877665544', 'Customer', 'नमस्ते! मुझे इलेक्ट्रॉनिक्स भेजने में मदद चाहिए', CURRENT_TIMESTAMP - INTERVAL '2 hours'),
    ('+918877665544', 'AI Agent', 'नमस्ते! मैं आपकी मदद कर सकता हूं। आप कहां से कहां भेजना चाहते हैं?', CURRENT_TIMESTAMP - INTERVAL '1 hour 59 minutes'),
    ('+918877665544', 'Customer', 'दिल्ली से न्यूयॉर्क', CURRENT_TIMESTAMP - INTERVAL '1 hour 58 minutes'),
    ('+918877665544', 'AI Agent', 'बहुत अच्छा! क्या आप एयर फ्रेट चाहते हैं?', CURRENT_TIMESTAMP - INTERVAL '1 hour 57 minutes'),
    ('+918877665544', 'Customer', 'हां, एयर फ्रेट चाहिए। कीमत क्या होगी?', CURRENT_TIMESTAMP - INTERVAL '1 hour 56 minutes'),
    ('+918877665544', 'Agent', 'Hi Ramesh! Let me prepare a quote for you. Air freight from Delhi to New York for electronics.', CURRENT_TIMESTAMP - INTERVAL '1 hour 50 minutes');

-- CONVERSATION 4: Sarah Johnson (London → Mumbai)
-- ============================================

INSERT INTO "Lead" (phone, name, language, company, origin, destination, mode, cargo_type, status, weight)
VALUES ('+447700900123', 'Sarah Johnson', 'en', 'UK Imports Ltd', 'London', 'Mumbai', 'sea', 'machinery', 'CONTACT_SHARED', '12000 kgs')
ON CONFLICT (phone) DO UPDATE SET
    name = EXCLUDED.name,
    company = EXCLUDED.company,
    origin = EXCLUDED.origin,
    destination = EXCLUDED.destination;

INSERT INTO chat_history (phone, role, content, created_at)
VALUES 
    ('+447700900123', 'Customer', 'Hello, I need to ship industrial machinery to India', CURRENT_TIMESTAMP - INTERVAL '5 hours'),
    ('+447700900123', 'AI Agent', 'Hello! I can help you with that. Where in India are you shipping to?', CURRENT_TIMESTAMP - INTERVAL '4 hours 59 minutes'),
    ('+447700900123', 'Customer', 'Mumbai. The machinery weighs about 12 tons', CURRENT_TIMESTAMP - INTERVAL '4 hours 58 minutes'),
    ('+447700900123', 'AI Agent', 'Thank you! For 12 tons of machinery from London to Mumbai, sea freight would be most economical. Would you like a detailed quote?', CURRENT_TIMESTAMP - INTERVAL '4 hours 57 minutes'),
    ('+447700900123', 'Customer', 'Yes please! Also need customs clearance help', CURRENT_TIMESTAMP - INTERVAL '4 hours 56 minutes'),
    ('+447700900123', 'Agent', 'Perfect! I will prepare a comprehensive quote including customs clearance. Can you share your email?', CURRENT_TIMESTAMP - INTERVAL '4 hours 50 minutes'),
    ('+447700900123', 'Customer', 'sarah.johnson@ukimports.co.uk', CURRENT_TIMESTAMP - INTERVAL '4 hours 45 minutes'),
    ('+447700900123', 'Agent', 'Thank you Sarah! Quote sent to your email. I will call you tomorrow to discuss details.', CURRENT_TIMESTAMP - INTERVAL '4 hours 40 minutes');

-- ============================================
-- VERIFY: Show all conversations
-- ============================================

SELECT '=== ALL CONVERSATIONS ===' as section;

SELECT 
    l.phone,
    l.name,
    l.company,
    l.origin || ' → ' || l.destination as route,
    l.cargo_type,
    l.status,
    COUNT(ch.id) as message_count,
    MAX(ch.created_at) as last_message_at
FROM "Lead" l
LEFT JOIN chat_history ch ON ch.phone = l.phone
GROUP BY l.phone, l.name, l.company, l.origin, l.destination, l.cargo_type, l.status
ORDER BY MAX(ch.created_at) DESC;

-- ============================================
-- SUCCESS MESSAGE
-- ============================================

SELECT '
✅ TEST DATA ADDED!

Now refresh your WhatsApp UI and you should see:

📱 4 CONVERSATIONS:
1. Abhijeet Singh  - Dubai → India (cars) - 16 messages
2. Priya Sharma    - Mumbai → Singapore (textiles) - 5 messages  
3. Ramesh Kumar    - Delhi → New York (electronics) - 6 messages (Hindi)
4. Sarah Johnson   - London → Mumbai (machinery) - 8 messages

Total: 4 contacts, 35 messages

🌐 Open: http://your-railway-app/whatsapp/inbox

' as result;

