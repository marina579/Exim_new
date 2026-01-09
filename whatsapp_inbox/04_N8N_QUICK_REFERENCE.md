# 🚀 n8n Quick Reference - Copy & Paste SQL Queries

## Essential PostgreSQL Queries for n8n

---

## 📥 INBOUND MESSAGE FLOW

### 1. Check if Conversation Exists

```sql
SELECT id, language, funnel_stage, has_user_replied
FROM conversations
WHERE phone = '{{ $json.phone }}';
```

**Returns:**
- Empty if new user
- Conversation record if exists

---

### 2. Create New Conversation

```sql
INSERT INTO conversations (
    phone,
    language,
    funnel_stage,
    is_active,
    campaign_id
) VALUES (
    '{{ $json.phone }}',
    'en',
    'NEW',
    false,
    '{{ $json.campaign_id }}'
)
RETURNING id, phone, language;
```

**Use when:** User doesn't exist yet

---

### 3. Insert Inbound Message

```sql
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    provider_message_id,
    raw_payload,
    status
) VALUES (
    '{{ $json.conversation_id }}',
    'inbound',
    'user',
    '{{ $json.message }}',
    '{{ $json.provider_message_id }}',
    '{{ $json.raw_payload | json }}',
    'delivered'
)
RETURNING id, created_at;
```

**Notes:**
- `raw_payload` must be JSONB (use `| json` filter in n8n)
- Database trigger auto-updates conversation!

---

## 📤 OUTBOUND MESSAGE FLOW

### 4. Insert Bot Response

```sql
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    provider_message_id,
    status
) VALUES (
    '{{ $json.conversation_id }}',
    'outbound',
    'bot',
    '{{ $json.bot_response }}',
    '{{ $json.exotel_message_id }}',
    'sent'
)
RETURNING id;
```

**Use after:** Sending message via Exotel

---

### 5. Insert Agent Message

```sql
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    provider_message_id,
    status
) VALUES (
    '{{ $json.conversation_id }}',
    'outbound',
    'agent',
    '{{ $json.message }}',
    '{{ $json.exotel_message_id }}',
    'sent'
)
RETURNING id;
```

**Sender:** `agent` (not `bot`)

---

## 👤 LEAD DATA MANAGEMENT

### 6. Create/Update Lead (UPSERT)

```sql
INSERT INTO leads (
    conversation_id,
    phone,
    name,
    email,
    company,
    origin,
    destination,
    mode,
    cargo_type,
    weight,
    shipment_type,
    raw_extracted_data,
    status
) VALUES (
    '{{ $json.conversation_id }}',
    '{{ $json.phone }}',
    '{{ $json.name }}',
    '{{ $json.email }}',
    '{{ $json.company }}',
    '{{ $json.origin }}',
    '{{ $json.destination }}',
    '{{ $json.mode }}',
    '{{ $json.cargo_type }}',
    '{{ $json.weight }}',
    '{{ $json.shipment_type }}',
    '{{ $json.raw_data | json }}',
    'engaged'
)
ON CONFLICT (conversation_id) 
DO UPDATE SET
    name = COALESCE(EXCLUDED.name, leads.name),
    email = COALESCE(EXCLUDED.email, leads.email),
    company = COALESCE(EXCLUDED.company, leads.company),
    origin = COALESCE(EXCLUDED.origin, leads.origin),
    destination = COALESCE(EXCLUDED.destination, leads.destination),
    mode = COALESCE(EXCLUDED.mode, leads.mode),
    cargo_type = COALESCE(EXCLUDED.cargo_type, leads.cargo_type),
    weight = COALESCE(EXCLUDED.weight, leads.weight),
    shipment_type = COALESCE(EXCLUDED.shipment_type, leads.shipment_type),
    raw_extracted_data = EXCLUDED.raw_extracted_data,
    updated_at = CURRENT_TIMESTAMP;
```

**Notes:**
- Uses COALESCE to preserve existing data
- Only updates non-null new values

---

## 🎯 FUNNEL STAGE UPDATES

### 7. Update to ENGAGED (First Reply)

```sql
UPDATE conversations
SET funnel_stage = 'ENGAGED',
    has_user_replied = true,
    first_reply_at = COALESCE(first_reply_at, CURRENT_TIMESTAMP),
    is_active = true,
    updated_at = CURRENT_TIMESTAMP
WHERE id = '{{ $json.conversation_id }}';
```

**When:** User sends first message

---

### 8. Update to QUALIFIED

```sql
UPDATE conversations
SET funnel_stage = 'QUALIFIED',
    updated_at = CURRENT_TIMESTAMP
WHERE id = '{{ $json.conversation_id }}';
```

**When:** 3+ key fields captured (origin, destination, mode)

---

### 9. Update to QUOTE_REQUESTED

```sql
UPDATE conversations
SET funnel_stage = 'QUOTE_REQUESTED',
    updated_at = CURRENT_TIMESTAMP
WHERE id = '{{ $json.conversation_id }}';
```

**When:** User asks about price/cost/quote

---

### 10. Update to CONTACT_SHARED

```sql
UPDATE conversations
SET funnel_stage = 'CONTACT_SHARED',
    updated_at = CURRENT_TIMESTAMP
WHERE id = '{{ $json.conversation_id }}';
```

**When:** User shares email or phone

---

## 🌐 LANGUAGE MANAGEMENT

### 11. Update Language

```sql
UPDATE conversations
SET language = '{{ $json.detected_language }}',
    updated_at = CURRENT_TIMESTAMP
WHERE id = '{{ $json.conversation_id }}';
```

**Languages:** `en`, `hi`, `te`

---

## 📊 LEAD SCORING

### 12. Calculate Lead Score

```sql
SELECT calculate_lead_score('{{ $json.conversation_id }}');
```

**Returns:** Integer score (0-100)

---

## 📧 EMAIL NOTIFICATIONS

### 13. Queue Email Notification

```sql
INSERT INTO email_notifications (
    conversation_id,
    lead_id,
    to_email,
    subject,
    body,
    notification_type,
    status
) VALUES (
    '{{ $json.conversation_id }}',
    '{{ $json.lead_id }}',
    'sarita@marineco.co',
    'New Qualified Lead: {{ $json.lead_name }}',
    'Lead Details:\nOrigin: {{ $json.origin }}\nDestination: {{ $json.destination }}\nMode: {{ $json.mode }}\nPhone: {{ $json.phone }}',
    'qualified',
    'pending'
)
RETURNING id;
```

**When:** Lead score ≥ 40 OR funnel = QUOTE_REQUESTED

---

## 📋 CAMPAIGN MESSAGES

### 14. Create Conversation for Campaign

```sql
INSERT INTO conversations (
    phone,
    campaign_id,
    language,
    funnel_stage,
    is_active
) VALUES (
    '{{ $json.phone }}',
    '{{ $json.campaign_id }}',
    'en',
    'NEW',
    false
)
ON CONFLICT (phone) DO NOTHING
RETURNING id;
```

**Important:** `is_active = false` (until user replies)

---

### 15. Insert Campaign Message

```sql
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    provider_message_id,
    status
) VALUES (
    '{{ $json.conversation_id }}',
    'outbound',
    'campaign',
    '{{ $json.template_message }}',
    '{{ $json.exotel_message_id }}',
    'sent'
);
```

**Sender:** `campaign` (not `bot`)

---

## 🔍 LOOKUP QUERIES

### 16. Get Conversation by Phone

```sql
SELECT id, phone, language, funnel_stage, lead_score
FROM conversations
WHERE phone = '{{ $json.phone }}';
```

---

### 17. Get Lead by Conversation

```sql
SELECT *
FROM leads
WHERE conversation_id = '{{ $json.conversation_id }}';
```

---

### 18. Get Recent Messages

```sql
SELECT direction, sender, message, created_at
FROM messages
WHERE conversation_id = '{{ $json.conversation_id }}'
ORDER BY created_at DESC
LIMIT 10;
```

---

## 📈 ANALYTICS QUERIES

### 19. Campaign Performance

```sql
SELECT 
    COUNT(*) as total_sent,
    COUNT(*) FILTER (WHERE has_user_replied = true) as replied,
    COUNT(*) FILTER (WHERE funnel_stage = 'CONVERTED') as converted,
    ROUND(100.0 * COUNT(*) FILTER (WHERE has_user_replied = true) / COUNT(*), 2) as reply_rate
FROM conversations
WHERE campaign_id = '{{ $json.campaign_id }}';
```

---

### 20. Active Conversations Count

```sql
SELECT COUNT(*) as active_count
FROM conversations
WHERE is_active = true 
AND funnel_stage != 'DROPPED';
```

---

## ⚠️ ERROR HANDLING

### 21. Mark Message as Failed

```sql
UPDATE messages
SET status = 'failed'
WHERE provider_message_id = '{{ $json.exotel_message_id }}';
```

---

### 22. Mark Message as Delivered

```sql
UPDATE messages
SET status = 'delivered',
    delivered_at = CURRENT_TIMESTAMP
WHERE provider_message_id = '{{ $json.exotel_message_id }}';
```

---

## 🧪 TEST DATA

### Insert Test Conversation

```sql
INSERT INTO conversations (phone, language, funnel_stage, is_active)
VALUES ('+91-9999999999', 'en', 'ENGAGED', true)
RETURNING id;
```

### Insert Test Message

```sql
INSERT INTO messages (conversation_id, direction, sender, message)
VALUES ('YOUR_CONV_ID', 'inbound', 'user', 'I need air freight quote from Mumbai to Dubai');
```

---

## 📋 COMMON PATTERNS

### Pattern: Receive Webhook → Process → Store

```javascript
// 1. Normalize phone
const phone = $input.item.json.From.replace('whatsapp:', '');

// 2. Check conversation exists
// Use Query #1

// 3. Create if needed
// Use Query #2

// 4. Insert message
// Use Query #3

// 5. Process with chatbot
// Your AI logic here

// 6. Update lead data
// Use Query #6

// 7. Send bot response
// Call Exotel API

// 8. Insert bot message
// Use Query #4
```

---

## 🎯 VALIDATION RULES

### Phone Format

```javascript
// Normalize to +91-XXXXXXXXXX
function normalizePhone(phone) {
    let clean = phone.replace(/[^\d+]/g, '');
    if (!clean.startsWith('+')) clean = '+' + clean;
    if (clean.startsWith('+91') && !clean.includes('-')) {
        clean = clean.replace('+91', '+91-');
    }
    return clean;
}
```

### Language Detection

```javascript
function detectLanguage(message) {
    const text = message.toLowerCase();
    if (text.includes('नमस्ते') || text.includes('hindi')) return 'hi';
    if (text.includes('నమస్కారం') || text.includes('telugu')) return 'te';
    return 'en';
}
```

---

## 🔐 Environment Variables

```
EXOTEL_API_KEY=your_key_here
EXOTEL_SID=your_sid_here
POSTGRES_HOST=railway_host
POSTGRES_PORT=5432
POSTGRES_DB=railway
POSTGRES_USER=postgres
POSTGRES_PASSWORD=railway_password
```

---

## ✅ Testing Checklist

- [ ] Inbound webhook receives message
- [ ] Conversation created (if new)
- [ ] Message inserted to database
- [ ] Chatbot generates response
- [ ] Response sent via Exotel
- [ ] Bot message inserted to database
- [ ] Lead data extracted and saved
- [ ] Funnel stage updated correctly
- [ ] UI shows message in real-time
- [ ] Agent can reply from UI

---

## 🆘 Quick Troubleshoot

### Message not appearing in UI?

```sql
-- Check if message was inserted
SELECT * FROM messages 
WHERE conversation_id = 'YOUR_ID'
ORDER BY created_at DESC LIMIT 5;
```

### Conversation not active?

```sql
-- Check conversation status
SELECT is_active, has_user_replied, funnel_stage 
FROM conversations 
WHERE phone = '+91-XXXXXXXXXX';

-- Manually activate if needed
UPDATE conversations 
SET is_active = true 
WHERE phone = '+91-XXXXXXXXXX';
```

### Lead data not saving?

```sql
-- Check if lead exists
SELECT * FROM leads WHERE conversation_id = 'YOUR_ID';

-- Check for conflicts
SELECT conversation_id, COUNT(*) 
FROM leads 
GROUP BY conversation_id 
HAVING COUNT(*) > 1;
```

---

**Copy these queries directly into your n8n PostgreSQL nodes!**

**Need full context?** See `03_N8N_DEVELOPER_GUIDE.md`

