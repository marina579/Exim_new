# 💬 WhatsApp Campaign Inbox - Complete System

## 🎯 What This Is

A production-ready **WhatsApp inbox system** integrated with:
- ✅ **Exotel WhatsApp API** (India)
- ✅ **n8n workflow automation** (chatbot logic)
- ✅ **PostgreSQL** (Railway) for data storage
- ✅ **Flask web UI** (integrated with Exim app)
- ✅ **Real-time updates** via Server-Sent Events

---

## 📦 What's Included

```
whatsapp_inbox/
├── 01_database_schema.sql         # PostgreSQL schema (run this first!)
├── 02_INTEGRATION_GUIDE.md        # For YOU - how to integrate into app
├── 03_N8N_DEVELOPER_GUIDE.md      # For n8n developer - data format specs
├── whatsapp_db.py                 # Database queries module
├── whatsapp_routes.py             # Flask routes module
├── templates/
│   ├── whatsapp_inbox.html        # Inbox list view
│   └── whatsapp_chat.html         # Chat interface
└── README.md                      # This file
```

---

## 🚀 Quick Start

### For You (UI Developer):

1. **Setup Database**
   ```bash
   psql $DATABASE_URL < 01_database_schema.sql
   ```

2. **Copy Files**
   ```bash
   cp whatsapp_db.py ../
   cp whatsapp_routes.py ../
   cp templates/* ../templates/
   ```

3. **Integrate into app_with_auth.py**
   ```python
   from whatsapp_routes import register_whatsapp_routes
   register_whatsapp_routes(app)
   ```

4. **Deploy**
   ```bash
   git add . && git commit -m "Add WhatsApp inbox" && git push
   ```

5. **Access**
   ```
   https://your-app.railway.app/whatsapp/inbox
   ```

**Full instructions:** See `02_INTEGRATION_GUIDE.md`

---

### For n8n Developer:

1. **Read the spec:** `03_N8N_DEVELOPER_GUIDE.md`

2. **Key Requirements:**
   - Handle Exotel inbound webhooks
   - Insert messages to PostgreSQL (exact format specified)
   - Send outbound messages via Exotel
   - Update lead data based on conversation
   - Support multi-language chatbot (EN/HI/TE)

3. **Database format examples:**
   ```sql
   -- Inbound message
   INSERT INTO messages (conversation_id, direction, sender, message)
   VALUES ('uuid', 'inbound', 'user', 'Hello!');
   
   -- Outbound message
   INSERT INTO messages (conversation_id, direction, sender, message)
   VALUES ('uuid', 'outbound', 'bot', 'How can I help?');
   ```

**Full specs:** See `03_N8N_DEVELOPER_GUIDE.md`

---

## 🏗️ System Architecture

```
┌─────────────┐
│ WhatsApp    │
│ User        │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Exotel    │ ← WhatsApp API Provider
│   API       │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│    n8n      │ ← Workflow Automation
│  Workflows  │   - Receive webhooks
│             │   - Chatbot logic
│             │   - Lead extraction
└──────┬──────┘
       │
       ↓
┌─────────────┐
│ PostgreSQL  │ ← Data Storage (Railway)
│  Database   │   - conversations
│             │   - messages
│             │   - leads
└──────┬──────┘
       │
       ↓ (LISTEN/NOTIFY)
┌─────────────┐
│   Flask     │ ← Web UI
│   Web UI    │   - Inbox view
│             │   - Chat interface
│             │   - Real-time updates
└─────────────┘
       ↑
       │
┌─────────────┐
│   Agent     │
│  Browser    │
└─────────────┘
```

---

## ✨ Features

### For Agents (UI):
- ✅ View all active WhatsApp conversations
- ✅ Filter by funnel stage (New, Qualified, Converted, etc.)
- ✅ Search by phone/name/company
- ✅ Read message history in WhatsApp-like interface
- ✅ Reply to messages (sent via n8n → Exotel)
- ✅ Update funnel stage manually
- ✅ Add notes to leads
- ✅ See real-time message updates
- ✅ View lead details (shipment info, scores)
- ✅ Inbox statistics dashboard

### For n8n (Automation):
- ✅ Receive Exotel webhooks
- ✅ Multi-language chatbot (English, Hindi, Telugu)
- ✅ Automatic lead qualification
- ✅ Lead scoring system
- ✅ Email notifications to sales team
- ✅ Campaign message tracking
- ✅ Conversation state management

---

## 📊 Database Tables

### Core Tables:

1. **`campaigns`** - Campaign metadata
2. **`conversations`** - One per WhatsApp user
3. **`messages`** - ALL messages (in/out)
4. **`leads`** - Enriched lead data
5. **`agent_actions`** - Audit trail
6. **`email_notifications`** - Internal notifications

### Key Indexes:
- Phone number (fast lookup)
- Conversation timestamps (sorting)
- Funnel stages (filtering)
- Unread messages (performance)

---

## 🎯 Funnel Stages

```
NEW
  ↓ (user replies)
ENGAGED
  ↓ (3+ key fields captured)
QUALIFIED
  ↓ (user asks for price)
QUOTE_REQUESTED
  ↓ (email/phone shared)
CONTACT_SHARED
  ↓ (sales team contacted)
CONVERTED
```

**DROPPED** - No reply after 3 follow-ups

---

## 🌐 Multi-Language Support

### Language Codes:
- `en` - English
- `hi` - Hindi (हिंदी)
- `te` - Telugu (తెలుగు)

### How It Works:
1. First message → Detect language
2. Store in `conversations.language`
3. Route to appropriate chatbot
4. All responses in user's language

---

## 🔒 Security

- ✅ All routes require authentication (`@login_required`)
- ✅ Uses existing user management system
- ✅ Agent actions logged for audit
- ✅ No hardcoded credentials (Railway env vars)
- ✅ SQL injection protection (parameterized queries)

---

## 📈 Scalability

### Designed for 1000s of conversations:

- ✅ PostgreSQL indexes for fast queries
- ✅ Pagination support (50 per page)
- ✅ Real-time via NOTIFY (not polling)
- ✅ Campaign messages hidden until reply
- ✅ Efficient filtering by funnel stage

---

## 🧪 Testing

### Test Inbound Message:

```bash
curl -X POST https://your-n8n.com/webhook/exotel-inbound \
  -H "Content-Type: application/json" \
  -d '{
    "From": "whatsapp:+919876543210",
    "Body": "I need air freight quote",
    "MessageSid": "WHTEST123"
  }'
```

### Test Outbound (from UI):

1. Go to `/whatsapp/conversation/{id}`
2. Type message
3. Click send
4. Should trigger n8n webhook → Exotel

---

## 🐛 Troubleshooting

### "No conversations showing"
- Check PostgreSQL connection
- Verify tables created (`01_database_schema.sql`)
- Check n8n is inserting data

### "Real-time not working"
- PostgreSQL NOTIFY requires PostgreSQL (not SQLite)
- Check browser console for SSE errors
- Verify DATABASE_URL is set

### "Can't send messages"
- Check N8N_SEND_WEBHOOK_URL env var
- Verify n8n webhook is running
- Check Railway logs for errors

---

## 📞 Environment Variables Required

```bash
# Railway PostgreSQL (auto-provided)
DATABASE_URL=postgresql://...

# n8n webhook for sending messages
N8N_SEND_WEBHOOK_URL=https://your-n8n.com/webhook/send-whatsapp
```

---

## 📚 Documentation Links

- **Integration Guide:** `02_INTEGRATION_GUIDE.md` (for UI integration)
- **n8n Guide:** `03_N8N_DEVELOPER_GUIDE.md` (for n8n developer)
- **Database Schema:** `01_database_schema.sql` (SQL to run)

---

## 🎨 Customization

### Change Colors:

Edit CSS in templates:
```css
/* WhatsApp green */
background: #008069;  

/* Message bubbles */
.message.outbound .message-bubble {
    background: #d9fdd3;
}
```

### Add Custom Filters:

In `whatsapp_routes.py`:
```python
if request.args.get('high_priority'):
    filters['lead_score'] = '>= 80'
```

---

## 📊 Metrics & KPIs

### Track via SQL:

```sql
-- Conversion rate
SELECT 
    COUNT(*) FILTER (WHERE funnel_stage = 'CONVERTED') * 100.0 / COUNT(*) as conversion_rate
FROM conversations
WHERE has_user_replied = true;

-- Average response time
SELECT AVG(
    EXTRACT(EPOCH FROM (first_reply_at - created_at))
) as avg_response_seconds
FROM conversations
WHERE first_reply_at IS NOT NULL;
```

---

## 🚀 Deployment Checklist

### Before Going Live:

- [ ] PostgreSQL schema executed
- [ ] All environment variables set
- [ ] n8n workflows tested
- [ ] Exotel webhooks configured
- [ ] UI accessible at `/whatsapp/inbox`
- [ ] Test conversation works end-to-end
- [ ] Real-time updates working
- [ ] Agent can send messages
- [ ] Funnel updates work
- [ ] Lead data populates correctly
- [ ] Email notifications working (optional)

---

## 📞 Support

**For UI Issues:**
- Check Railway logs: `railway logs`
- Check browser console (F12)
- Verify PostgreSQL connection

**For n8n Issues:**
- Check n8n execution logs
- Verify webhook URLs are correct
- Test PostgreSQL connection from n8n

**For Exotel Issues:**
- Check Exotel dashboard for webhook logs
- Verify API credentials
- Check message delivery status

---

## 🎯 Success Metrics

After deployment, track:

✅ **Response rate:** % of campaign sends that get replies  
✅ **Conversion rate:** % that reach CONVERTED stage  
✅ **Average lead score:** Quality of incoming leads  
✅ **Time to first response:** Bot + agent speed  
✅ **Qualified lead rate:** % reaching QUALIFIED or higher  

---

## 📝 Notes

### Campaign Messages:
- Sent via n8n → stored with `sender='campaign'`
- NOT shown in UI until user replies
- Keeps inbox clean and focused

### Real-Time Updates:
- Uses PostgreSQL LISTEN/NOTIFY
- More efficient than polling
- Instant UI updates on new messages

### Lead Scoring:
- Automatic based on conversation data
- Updates on every lead data change
- Used for prioritization and notifications

---

## ✅ Ready to Deploy!

1. **You (UI):** Follow `02_INTEGRATION_GUIDE.md`
2. **n8n Developer:** Follow `03_N8N_DEVELOPER_GUIDE.md`
3. **Test Together:** Ensure end-to-end flow works

**Questions?** Check the guides or Railway logs!

---

**Built with ❤️ for Marineco Private Limited**

🚢 Making logistics simple, one WhatsApp at a time.

