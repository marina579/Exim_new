# 🤖 n8n Developer Guide - WhatsApp Inbox Integration

## Complete Data Flow & PostgreSQL Integration Spec

This document defines **EXACTLY** how n8n workflows should interact with PostgreSQL.

---

## 🎯 Overview

```
Exotel WhatsApp → n8n → PostgreSQL → UI (real-time)
                    ↑
                    └─ UI sends message → n8n → Exotel
```

---

## 📊 Core Workflow: Inbound Message Handling

### Step 1: Receive Exotel Webhook

**Webhook URL:** `https://your-n8n.com/webhook/exotel-inbound`

**Exotel sends:**
```json
{
  "From": "whatsapp:+919876543210",
  "To": "whatsapp:+917001234567",
  "Body": "Hello! I need help with import.",
  "MessageSid": "WHXXXXXXXXXXXXXXXXXXXXXXXXX",
  "AccountSid": "EXXXXXXXXXXXXXXXXXXX",
  "SmsStatus": "received",
  "Direction": "inbound"
}
```

---

### Step 2: Extract & Normalize Phone

**n8n Code Node:**

```javascript
// Extract phone number (remove 'whatsapp:' prefix)
const rawPhone = $input.item.json.From; // "whatsapp:+919876543210"
const phone = rawPhone.replace('whatsapp:', '').replace(/\s/g, '');

// Normalize to +91-XXXXXXXXXX format
let normalizedPhone = phone;
if (!normalizedPhone.startsWith('+')) {
    normalizedPhone = '+' + normalizedPhone;
}
if (normalizedPhone.startsWith('+91') && !normalizedPhone.includes('-')) {
    normalizedPhone = normalizedPhone.replace('+91', '+91-');
}

return {
    json: {
        phone: normalizedPhone,
        message: $input.item.json.Body,
        provider_message_id: $input.item.json.MessageSid,
        raw_payload: $input.item.json
    }
};
```

**Output:**
```json
{
  "phone": "+91-9876543210",
  "message": "Hello! I need help with import.",
  "provider_message_id": "WHXXXXXXXXXXXXXXXXXXXXXXXXX",
  "raw_payload": {...}
}
```

---

### Step 3: Check if Conversation Exists

**PostgreSQL Node (SELECT):**

**SQL Query:**
```sql
SELECT id, language, intent, funnel_stage, has_user_replied
FROM conversations
WHERE phone = '{{ $json.phone }}';
```

**Output:**
- If exists: Returns conversation record
- If not exists: Returns empty array

---

### Step 4A: Create New Conversation (if not exists)

**PostgreSQL Node (INSERT):**

**Condition:** Previous query returned empty array

**SQL Query:**
```sql
INSERT INTO conversations (
    phone,
    language,
    funnel_stage,
    is_active
) VALUES (
    '{{ $json.phone }}',
    'en',  -- Default to English (chatbot will detect later)
    'NEW',
    false  -- Not active until user replies
)
RETURNING id;
```

**Output:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### Step 4B: Use Existing Conversation

**Set Node:** Store conversation ID from Step 3

---

### Step 5: Insert Message into Database

**PostgreSQL Node (INSERT):**

**SQL Query:**
```sql
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    provider_message_id,
    raw_payload,
    status,
    created_at
) VALUES (
    '{{ $json.conversation_id }}',
    'inbound',
    'user',
    '{{ $json.message }}',
    '{{ $json.provider_message_id }}',
    '{{ $json.raw_payload | jsonStringify }}',
    'delivered',
    CURRENT_TIMESTAMP
)
RETURNING id;
```

**IMPORTANT:** 
- `raw_payload` must be JSONB type
- Use `jsonStringify` or equivalent in n8n
- `direction` = 'inbound' (from user)
- `sender` = 'user'

**Output:**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001"
}
```

---

### Step 6: Trigger Auto-Update

**✅ DATABASE TRIGGER HANDLES THIS AUTOMATICALLY**

When message is inserted, PostgreSQL trigger `trg_update_conv_on_msg` will:

1. Update `last_message_at`
2. Update `last_user_message_at`
3. Set `has_user_replied` = true
4. Set `is_active` = true
5. Move from 'NEW' → 'ENGAGED'
6. Send real-time notification to UI via NOTIFY

**No n8n action required - PostgreSQL handles this!**

---

### Step 7: Chatbot Response (if enabled)

**If:** Chatbot should respond

**AI Node / Function Node:**

```javascript
// Process with chatbot logic
const userMessage = $json.message;
const language = $json.language || 'en';
const conversationId = $json.conversation_id;

// Call your chatbot service (Claude, GPT, Gemini)
// Extract intent and lead data
// Generate response

return {
    json: {
        conversation_id: conversationId,
        response_message: "Thanks! Which service? Air or Sea freight?",
        detected_language: 'en',
        detected_intent: 'general_inquiry',
        lead_data: {
            origin: null,
            destination: null,
            mode: null
        }
    }
};
```

---

### Step 8: Update Lead Data (if extracted)

**PostgreSQL Node (UPSERT):**

**SQL Query:**
```sql
INSERT INTO leads (
    conversation_id,
    phone,
    origin,
    destination,
    mode,
    raw_extracted_data,
    status
) VALUES (
    '{{ $json.conversation_id }}',
    '{{ $json.phone }}',
    '{{ $json.lead_data.origin }}',
    '{{ $json.lead_data.destination }}',
    '{{ $json.lead_data.mode }}',
    '{{ $json.lead_data | jsonStringify }}',
    'engaged'
)
ON CONFLICT (conversation_id) 
DO UPDATE SET
    origin = COALESCE(EXCLUDED.origin, leads.origin),
    destination = COALESCE(EXCLUDED.destination, leads.destination),
    mode = COALESCE(EXCLUDED.mode, leads.mode),
    raw_extracted_data = EXCLUDED.raw_extracted_data,
    updated_at = CURRENT_TIMESTAMP;
```

**Note:** Only updates non-null values (preserves existing data)

---

### Step 9: Send Bot Response to User

**HTTP Request Node:** Call Exotel API

**URL:** `https://api.exotel.com/v2/accounts/{sid}/messages`

**Headers:**
```json
{
  "Authorization": "Basic <base64_encoded_api_key>",
  "Content-Type": "application/json"
}
```

**Body:**
```json
{
  "from": "whatsapp:+917001234567",
  "to": "whatsapp:{{ $json.phone }}",
  "body": "{{ $json.response_message }}"
}
```

---

### Step 10: Insert Bot Response into Database

**PostgreSQL Node (INSERT):**

**SQL Query:**
```sql
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    provider_message_id,
    status,
    created_at
) VALUES (
    '{{ $json.conversation_id }}',
    'outbound',
    'bot',
    '{{ $json.response_message }}',
    '{{ $json.exotel_message_id }}',
    'sent',
    CURRENT_TIMESTAMP
)
RETURNING id;
```

**IMPORTANT:**
- `direction` = 'outbound' (from bot to user)
- `sender` = 'bot'
- `status` = 'sent' initially (update to 'delivered'/'read' via Exotel webhooks)

---

## 📤 Outbound Workflow: Agent Sends Message

### Trigger: Webhook from UI

**Webhook URL:** `https://your-n8n.com/webhook/send-whatsapp`

**UI sends:**
```json
{
  "phone": "+91-9876543210",
  "message": "Hi! We can help with your shipment. When do you need it?",
  "sender": "agent",
  "agent_name": "Sarita",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

### Step 1: Send to Exotel

**HTTP Request Node:**

Same as Step 9 above, but use agent message.

---

### Step 2: Insert Agent Message into Database

**PostgreSQL Node (INSERT):**

```sql
INSERT INTO messages (
    conversation_id,
    direction,
    sender,
    message,
    provider_message_id,
    status,
    created_at
) VALUES (
    '{{ $json.conversation_id }}',
    'outbound',
    'agent',
    '{{ $json.message }}',
    '{{ $json.exotel_message_id }}',
    'sent',
    CURRENT_TIMESTAMP
)
RETURNING id;
```

**IMPORTANT:**
- `sender` = 'agent' (not 'bot')
- `direction` = 'outbound'

---

## 📋 Campaign Message Workflow

### Step 1: Send Bulk Campaign Messages

**Loop through campaign list:**

```javascript
// For each recipient
const recipients = $input.item.json.recipients; // Array of phone numbers

return recipients.map(phone => ({
    json: {
        phone: phone,
        message: $input.item.json.template_message,
        campaign_id: $input.item.json.campaign_id
    }
}));
```

---

### Step 2: Create Conversation (if new)

**Same as Inbound Step 4A:**

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
    false  -- NOT active until user replies
)
ON CONFLICT (phone) DO NOTHING
RETURNING id;
```

---

### Step 3: Send Campaign Message

**HTTP Request to Exotel** (same as outbound)

---

### Step 4: Insert Campaign Message

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
    '{{ $json.message }}',
    '{{ $json.exotel_message_id }}',
    'sent'
);
```

**IMPORTANT:**
- `sender` = 'campaign' (not 'bot' or 'agent')
- `is_active` stays false until user replies

**UI WILL NOT SHOW THESE** until user responds!

---

## 🎯 Lead Scoring Logic (Optional but Recommended)

### When to Update Lead Score

After inserting/updating lead data:

**PostgreSQL Function Call:**

```sql
SELECT calculate_lead_score('{{ $json.conversation_id }}');
```

**Function already exists in database schema!**

Scoring rules:
- User replied: +10
- Origin provided: +10
- Destination provided: +10
- Mode selected: +15
- Cargo type: +10
- Quote requested: +20
- Email shared: +15
- Phone verified: +15

---

## 📧 Email Notification Logic

### When to Send Email to Sales Team

**Conditions:**
- Lead score ≥ 40
- OR funnel stage = 'QUOTE_REQUESTED'
- OR funnel stage = 'CONTACT_SHARED'

**PostgreSQL Insert:**

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
    'Lead details: Origin: {{ $json.origin }}, Destination: {{ $json.destination }}',
    'qualified',
    'pending'
)
RETURNING id;
```

---

## 🔄 Funnel Stage Auto-Updates

### When User Asks for Price

**Detect keywords:** "price", "cost", "quote", "rate", "how much"

**Update:**
```sql
UPDATE conversations
SET funnel_stage = 'QUOTE_REQUESTED',
    updated_at = CURRENT_TIMESTAMP
WHERE id = '{{ $json.conversation_id }}';
```

---

### When User Shares Contact Info

**Detect:** Email pattern or phone pattern in message

**Update:**
```sql
UPDATE conversations
SET funnel_stage = 'CONTACT_SHARED',
    updated_at = CURRENT_TIMESTAMP
WHERE id = '{{ $json.conversation_id }}';

-- Also update leads table
UPDATE leads
SET email = '{{ $json.extracted_email }}',
    updated_at = CURRENT_TIMESTAMP
WHERE conversation_id = '{{ $json.conversation_id }}';
```

---

## 🌐 Multi-Language Chatbot Flow

### Step 1: Language Detection (First Message)

**AI Node:** Detect language from user message

```javascript
const message = $json.message.toLowerCase();

let detected_language = 'en';

if (message.includes('नमस्ते') || message.includes('हिंदी') || message.includes('hindi')) {
    detected_language = 'hi';
} else if (message.includes('నమస్కారం') || message.includes('తెలుగు') || message.includes('telugu')) {
    detected_language = 'te';
}

return {
    json: {
        conversation_id: $json.conversation_id,
        language: detected_language
    }
};
```

---

### Step 2: Update Conversation Language

```sql
UPDATE conversations
SET language = '{{ $json.language }}',
    updated_at = CURRENT_TIMESTAMP
WHERE id = '{{ $json.conversation_id }}';
```

---

### Step 3: Route to Language-Specific Chatbot

**Switch Node:**

- If language = 'en' → English chatbot flow
- If language = 'hi' → Hindi chatbot flow
- If language = 'te' → Telugu chatbot flow

---

## 📊 Required PostgreSQL Connections in n8n

### Connection 1: Railway PostgreSQL

**Host:** Provided by Railway  
**Port:** 5432  
**Database:** railway  
**Username:** postgres  
**Password:** Provided by Railway  
**SSL:** Required (set to `true`)

### Test Connection

```sql
SELECT 1;
```

Should return `1`.

---

## ✅ Data Validation Checklist

### Before Inserting Message:

- [ ] `conversation_id` is valid UUID
- [ ] `direction` is 'inbound' or 'outbound'
- [ ] `sender` is 'user', 'bot', 'agent', or 'campaign'
- [ ] `message` is not empty
- [ ] `raw_payload` is valid JSON (for JSONB column)

### Before Updating Lead:

- [ ] `phone` is normalized format (+91-XXXXXXXXXX)
- [ ] UPSERT logic used (handles duplicates)
- [ ] Only update non-null values

### Before Sending WhatsApp:

- [ ] Exotel credentials are valid
- [ ] Phone format matches Exotel requirements
- [ ] Message length < 1024 characters

---

## 🐛 Error Handling

### If Exotel API Fails:

**Update message status:**
```sql
UPDATE messages
SET status = 'failed'
WHERE id = '{{ $json.message_id }}';
```

### If PostgreSQL Insert Fails:

**Log to n8n error workflow:**
- Capture error message
- Store in separate error table (optional)
- Send alert to admin

---

## 📈 Performance Tips

### 1. Use Prepared Statements

In n8n PostgreSQL node, enable "Prepared Statement" for repeated queries.

### 2. Batch Inserts for Campaigns

```sql
INSERT INTO messages (conversation_id, direction, sender, message)
VALUES 
    ('id1', 'outbound', 'campaign', 'msg1'),
    ('id2', 'outbound', 'campaign', 'msg2'),
    ('id3', 'outbound', 'campaign', 'msg3');
```

### 3. Index Usage

Schema already includes indexes! No action needed.

---

## 🎯 Sample Data for Testing

### Insert Test Campaign:

```sql
INSERT INTO campaigns (id, name, status)
VALUES ('123e4567-e89b-12d3-a456-426614174000', 'Test Campaign', 'active');
```

### Insert Test Conversation:

```sql
INSERT INTO conversations (phone, language, funnel_stage)
VALUES ('+91-9876543210', 'en', 'ENGAGED')
RETURNING id;
```

### Insert Test Message:

```sql
INSERT INTO messages (conversation_id, direction, sender, message)
VALUES ('YOUR_CONVERSATION_ID', 'inbound', 'user', 'I need air freight quote');
```

---

## 🔐 Security Notes

### Environment Variables in n8n:

- `EXOTEL_API_KEY`
- `EXOTEL_SID`
- `POSTGRES_CONNECTION_STRING` (Railway provides)

**Never hardcode credentials!**

---

## 📞 API Endpoints Summary

### n8n Must Expose:

1. **Inbound Webhook**
   - URL: `/webhook/exotel-inbound`
   - Method: POST
   - Purpose: Receive messages from Exotel

2. **Outbound Webhook**
   - URL: `/webhook/send-whatsapp`
   - Method: POST
   - Purpose: Receive send requests from UI

---

## ✅ Implementation Checklist for n8n Developer

- [ ] Create inbound webhook workflow
- [ ] Add PostgreSQL connection to Railway
- [ ] Implement conversation creation logic
- [ ] Implement message insert logic
- [ ] Add chatbot AI integration
- [ ] Implement lead data extraction
- [ ] Create outbound sending workflow
- [ ] Add campaign message workflow
- [ ] Implement language detection
- [ ] Add lead scoring updates
- [ ] Setup email notifications
- [ ] Test all workflows end-to-end
- [ ] Setup error handling
- [ ] Add logging for debugging

---

## 📚 Reference: Column Mappings

### `conversations` Table:
- `phone` → "+91-XXXXXXXXXX" format (PRIMARY KEY equivalent)
- `language` → 'en' | 'hi' | 'te'
- `funnel_stage` → 'NEW' | 'ENGAGED' | 'QUALIFIED' | 'QUOTE_REQUESTED' | 'CONTACT_SHARED' | 'CONVERTED' | 'DROPPED'
- `is_active` → false initially, true after first user reply

### `messages` Table:
- `direction` → 'inbound' | 'outbound'
- `sender` → 'user' | 'bot' | 'agent' | 'campaign'
- `status` → 'sent' | 'delivered' | 'read' | 'failed'

### `leads` Table:
- `mode` → 'air' | 'sea' | 'lcl' | 'fcl' | 'door_to_door'
- `shipment_type` → 'import' | 'export' | 'domestic'

---

**Questions? Check PostgreSQL logs in Railway for detailed error messages.**

**Ready to build! 🚀**

