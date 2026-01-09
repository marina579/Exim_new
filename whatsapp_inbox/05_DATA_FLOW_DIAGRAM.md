# 📊 WhatsApp Inbox - Complete Data Flow Diagram

## Visual Guide for Understanding the System

---

## 🔄 INBOUND MESSAGE FLOW (User → Agent)

```
┌─────────────────┐
│  WhatsApp User  │
│  +91-987654321  │
│                 │
│  "I need air    │
│   freight"      │
└────────┬────────┘
         │ Send Message
         ↓
┌─────────────────┐
│     Exotel      │  ← WhatsApp Business API Provider
│   (India API)   │
│                 │
│  Receives &     │
│  Forwards       │
└────────┬────────┘
         │ Webhook POST
         │ {
         │   "From": "whatsapp:+919876543210",
         │   "Body": "I need air freight",
         │   "MessageSid": "WHXXXXX"
         │ }
         ↓
┌─────────────────┐
│      n8n        │  ← Workflow Automation
│   Workflow 1    │
│  (Inbound)      │
└────────┬────────┘
         │
         ├─ STEP 1: Normalize Phone
         │  Output: "+91-9876543210"
         │
         ├─ STEP 2: Check Conversation Exists
         │  SQL: SELECT * FROM conversations WHERE phone = ?
         │
         ├─ STEP 3a: Create Conversation (if new)
         │  SQL: INSERT INTO conversations (phone, language, funnel_stage)
         │        VALUES ('+91-9876543210', 'en', 'NEW')
         │
         ├─ STEP 4: Insert Message to Database
         │  SQL: INSERT INTO messages 
         │        (conversation_id, direction, sender, message)
         │        VALUES (uuid, 'inbound', 'user', 'I need air freight')
         │
         ↓
┌─────────────────┐
│   PostgreSQL    │  ← Railway Database
│    Database     │
│                 │
│  TRIGGER FIRES: │
│  - Update last_message_at
│  - Set has_user_replied = true
│  - Set is_active = true
│  - Move NEW → ENGAGED
│  - pg_notify('new_message', {...})
└────────┬────────┘
         │ NOTIFY event
         ↓
┌─────────────────┐
│   Flask UI      │  ← Your App (SSE Listener)
│  (app_with_     │
│   auth.py)      │
│                 │
│  EventSource    │
│  /whatsapp/     │
│   stream        │
└────────┬────────┘
         │ Real-time update
         ↓
┌─────────────────┐
│  Agent Browser  │
│                 │
│  Message appears│
│  instantly!     │
│  (No refresh)   │
└─────────────────┘
```

---

## 📤 OUTBOUND MESSAGE FLOW (Agent → User)

```
┌─────────────────┐
│  Agent Browser  │
│                 │
│  Types: "We can │
│   help with     │
│   your shipment"│
│                 │
│  Clicks [Send]  │
└────────┬────────┘
         │ AJAX POST
         │ /whatsapp/api/send
         ↓
┌─────────────────┐
│   Flask UI      │
│  whatsapp_      │
│  routes.py      │
└────────┬────────┘
         │ Webhook POST
         │ N8N_SEND_WEBHOOK_URL
         │ {
         │   "phone": "+91-9876543210",
         │   "message": "We can help...",
         │   "sender": "agent",
         │   "conversation_id": "uuid"
         │ }
         ↓
┌─────────────────┐
│      n8n        │
│   Workflow 2    │
│  (Outbound)     │
└────────┬────────┘
         │
         ├─ STEP 1: Call Exotel API
         │  POST https://api.exotel.com/v2/accounts/{sid}/messages
         │  Body: {
         │    "from": "whatsapp:+917001234567",
         │    "to": "whatsapp:+919876543210",
         │    "body": "We can help..."
         │  }
         │
         ├─ STEP 2: Insert to Database
         │  SQL: INSERT INTO messages
         │        (conversation_id, direction, sender, message)
         │        VALUES (uuid, 'outbound', 'agent', 'We can help...')
         │
         ↓
┌─────────────────┐
│     Exotel      │
└────────┬────────┘
         │ Sends WhatsApp
         ↓
┌─────────────────┐
│  WhatsApp User  │
│                 │
│  Receives:      │
│  "We can help   │
│   with your     │
│   shipment"     │
└─────────────────┘
```

---

## 🤖 CHATBOT AUTO-RESPONSE FLOW

```
┌─────────────────┐
│  User Message   │
│  "I need air    │
│   freight"      │
└────────┬────────┘
         │ (After inserting to DB)
         ↓
┌─────────────────┐
│      n8n        │
│   AI Node       │
└────────┬────────┘
         │
         ├─ STEP 1: Detect Intent
         │  AI analyzes: "air freight inquiry"
         │  Language: English
         │
         ├─ STEP 2: Extract Lead Data
         │  {
         │    "mode": "air",
         │    "origin": null,
         │    "destination": null
         │  }
         │
         ├─ STEP 3: Generate Response
         │  "Thanks! Which route? Please share
         │   origin and destination."
         │
         ├─ STEP 4: Update Lead Table
         │  SQL: INSERT INTO leads
         │        (conversation_id, mode, status)
         │        VALUES (uuid, 'air', 'engaged')
         │        ON CONFLICT DO UPDATE...
         │
         ├─ STEP 5: Send Bot Response (via Exotel)
         │
         ├─ STEP 6: Insert Bot Message
         │  SQL: INSERT INTO messages
         │        (conversation_id, direction, sender, message)
         │        VALUES (uuid, 'outbound', 'bot', response)
         │
         └─ STEP 7: Calculate Lead Score
            SQL: SELECT calculate_lead_score(uuid);
            Returns: 25 (mode filled = +15, replied = +10)
```

---

## 📊 FUNNEL PROGRESSION FLOW

```
Campaign Message Sent
         ↓
┌─────────────────┐
│   NEW STAGE     │  ← is_active = false
│                 │    (Hidden from UI inbox)
└────────┬────────┘
         │ User replies
         ↓
┌─────────────────┐
│ ENGAGED STAGE   │  ← is_active = true
│                 │    (Now visible in UI)
│  - User replied │
│  - Bot responds │
└────────┬────────┘
         │ 3+ fields captured
         │ (origin, dest, mode)
         ↓
┌─────────────────┐
│ QUALIFIED STAGE │  ← Lead score ≥ 40
│                 │    Email sent to sales
│  - Route known  │
│  - Mode known   │
│  - Cargo type   │
└────────┬────────┘
         │ User asks about price
         ↓
┌─────────────────┐
│ QUOTE_REQUESTED │  ← High priority
│                 │    Alert sales team
│  - Pricing req  │
└────────┬────────┘
         │ Email/phone shared
         ↓
┌─────────────────┐
│ CONTACT_SHARED  │  ← Ready for handoff
│                 │
│  - Email ✓      │
│  - Phone ✓      │
└────────┬────────┘
         │ Sales calls/emails
         ↓
┌─────────────────┐
│  CONVERTED      │  ← Deal in progress
│                 │
│  - Quote sent   │
│  - Customer OK  │
└─────────────────┘
```

---

## 🌐 LANGUAGE DETECTION FLOW

```
First Message from User
         ↓
┌─────────────────┐
│  Language Menu  │
│  Sent by Bot:   │
│                 │
│  "Please choose:│
│   1. English    │
│   2. हिंदी      │
│   3. తెలుగు     │
└────────┬────────┘
         │ User replies "2"
         ↓
┌─────────────────┐
│  n8n Detects    │
│  Language       │
└────────┬────────┘
         │
         ├─ Code Node:
         │  if (reply === "2") {
         │    language = "hi"
         │  }
         │
         ├─ Update DB:
         │  SQL: UPDATE conversations
         │       SET language = 'hi'
         │
         └─ Route to Hindi Chatbot
            ↓
         ┌─────────────────┐
         │ Hindi Chatbot   │
         │ Responds:       │
         │ "धन्यवाद! आप   │
         │  कहाँ से कहाँ   │
         │  भेजना चाहते हैं│
         └─────────────────┘
```

---

## 📧 EMAIL NOTIFICATION FLOW

```
Lead Data Updated
         ↓
         Check Conditions:
         - Lead score ≥ 40?
         - OR funnel = QUOTE_REQUESTED?
         - OR funnel = CONTACT_SHARED?
         ↓
         YES
         ↓
┌─────────────────┐
│  n8n Insert     │
│  Notification   │
│                 │
│  SQL: INSERT    │
│  INTO email_    │
│  notifications  │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Separate n8n   │
│  Workflow       │
│  (Email Send)   │
└────────┬────────┘
         │
         ├─ Fetch pending notifications
         │  SQL: SELECT * FROM email_notifications
         │       WHERE status = 'pending'
         │
         ├─ Send Email (SMTP/SendGrid)
         │  To: sarita@marineco.co
         │  Subject: "New Qualified Lead"
         │  Body: Lead details...
         │
         └─ Mark as sent
            SQL: UPDATE email_notifications
                 SET status = 'sent'
```

---

## 🎯 CAMPAIGN MESSAGE FLOW

```
Campaign Created
         ↓
┌─────────────────┐
│  Campaign List  │
│  (1000 phones)  │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  n8n Loop       │
│  Over List      │
└────────┬────────┘
         │
         ├─ For Each Phone:
         │
         ├─ STEP 1: Create/Get Conversation
         │  SQL: INSERT INTO conversations
         │       (phone, campaign_id, is_active)
         │       VALUES (phone, campaign_id, false)
         │       ON CONFLICT DO NOTHING
         │
         ├─ STEP 2: Send Message via Exotel
         │  POST to Exotel API
         │
         ├─ STEP 3: Insert to Database
         │  SQL: INSERT INTO messages
         │       (conversation_id, direction, sender)
         │       VALUES (uuid, 'outbound', 'campaign')
         │
         └─ IMPORTANT: is_active = false
            └─ NOT shown in UI until user replies!
```

---

## 🔍 UI FILTERING LOGIC

```
Agent Opens Inbox
         ↓
┌─────────────────┐
│  whatsapp_      │
│  routes.py      │
│                 │
│  /whatsapp/     │
│  inbox          │
└────────┬────────┘
         │
         ├─ Query Database:
         │  SQL: SELECT * FROM v_active_inbox
         │       WHERE is_active = true
         │       AND funnel_stage != 'DROPPED'
         │       ORDER BY last_message_at DESC
         │       LIMIT 50
         │
         ↓
┌─────────────────┐
│  Conversations  │
│  Returned:      │
│                 │
│  ✓ User replied │
│  ✓ Active chats │
│  ✗ Campaign     │
│    no-replies   │
│  ✗ Dropped      │
└─────────────────┘
```

---

## 📊 LEAD SCORING CALCULATION

```
Message Received / Lead Updated
         ↓
┌─────────────────┐
│  n8n Calls      │
│  Function       │
│                 │
│  SQL: SELECT    │
│  calculate_lead_│
│  score(conv_id) │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Scoring Logic  │
│  (in PostgreSQL)│
└────────┬────────┘
         │
         ├─ User replied? +10
         ├─ Origin filled? +10
         ├─ Destination filled? +10
         ├─ Mode selected? +15
         ├─ Cargo type? +10
         ├─ Quote requested? +20
         ├─ Email shared? +15
         └─ Phone verified? +15
         │
         ↓ Sum = Lead Score
┌─────────────────┐
│  Update Conv    │
│                 │
│  SQL: UPDATE    │
│  conversations  │
│  SET lead_score │
│  = calculated   │
└─────────────────┘
```

---

## 🔄 REAL-TIME UPDATE MECHANISM

```
┌─────────────────┐
│  PostgreSQL     │
│  Trigger        │
│  (on INSERT)    │
└────────┬────────┘
         │
         ├─ Message inserted
         │  ↓
         ├─ Trigger executes:
         │  PERFORM pg_notify(
         │    'new_message',
         │    json_data
         │  )
         │
         ↓
┌─────────────────┐
│  Flask App      │
│  SSE Endpoint   │
│  /whatsapp/     │
│  stream         │
└────────┬────────┘
         │
         ├─ LISTEN to channel
         │  conn.execute("LISTEN new_message")
         │
         ├─ Receives notification
         │  ↓
         └─ Sends to browser
            event: new_message
            data: {"conversation_id": "...", ...}
            ↓
┌─────────────────┐
│  Browser JS     │
│  EventSource    │
└────────┬────────┘
         │
         ├─ Receives event
         ├─ Updates DOM
         └─ Shows new message instantly!
```

---

## 📋 DATA STRUCTURE REFERENCE

### Message Object (PostgreSQL):
```json
{
  "id": "uuid",
  "conversation_id": "uuid",
  "direction": "inbound|outbound",
  "sender": "user|bot|agent|campaign",
  "message": "Text content",
  "provider_message_id": "Exotel SID",
  "status": "sent|delivered|read|failed",
  "created_at": "2025-01-15 10:30:00"
}
```

### Conversation Object:
```json
{
  "id": "uuid",
  "phone": "+91-9876543210",
  "language": "en|hi|te",
  "funnel_stage": "ENGAGED",
  "lead_score": 45,
  "has_user_replied": true,
  "is_active": true,
  "last_message_at": "2025-01-15 10:30:00"
}
```

### Lead Object:
```json
{
  "id": "uuid",
  "conversation_id": "uuid",
  "name": "Rajesh Kumar",
  "email": "rajesh@company.com",
  "phone": "+91-9876543210",
  "origin": "Mumbai",
  "destination": "Dubai",
  "mode": "air",
  "cargo_type": "Electronics",
  "weight": "50 kg",
  "status": "qualified"
}
```

---

## 🎯 KEY TAKEAWAYS

### For UI Developer:
- ✅ Real-time via PostgreSQL NOTIFY
- ✅ No polling needed
- ✅ Filter by `is_active = true`
- ✅ Campaign messages hidden until reply

### For n8n Developer:
- ✅ Insert messages with exact format
- ✅ Triggers handle conversation updates
- ✅ Use UPSERT for lead data
- ✅ Calculate lead score after updates
- ✅ Set `is_active = false` for campaigns

---

**This diagram shows the complete data flow!**

**Questions?** See detailed docs:
- `03_N8N_DEVELOPER_GUIDE.md` (full specs)
- `04_N8N_QUICK_REFERENCE.md` (SQL queries)

