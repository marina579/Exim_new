# 🔗 WhatsApp Inbox Integration Guide

## Integration with `app_with_auth.py`

Follow these steps to integrate the WhatsApp inbox into your existing Exim application.

---

## 📋 Step 1: Copy Files

Copy these files to your project root:

```bash
cp whatsapp_inbox/whatsapp_db.py /path/to/Exim_new/
cp whatsapp_inbox/whatsapp_routes.py /path/to/Exim_new/
cp whatsapp_inbox/templates/whatsapp_inbox.html /path/to/Exim_new/templates/
cp whatsapp_inbox/templates/whatsapp_chat.html /path/to/Exim_new/templates/
```

---

## 📝 Step 2: Update `app_with_auth.py`

### 2.1 Add Import at Top

```python
# Add these imports after existing imports
from whatsapp_routes import register_whatsapp_routes
```

### 2.2 Register Routes (After app creation)

Find where your Flask app is created:

```python
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', '...')
# ... other config ...

# ADD THIS LINE:
register_whatsapp_routes(app)
```

### 2.3 Update Navbar (Optional but Recommended)

Find your navbar template and add WhatsApp link:

```html
<nav class="navbar navbar-expand-lg navbar-dark bg-dark">
    <div class="container-fluid">
        <a class="navbar-brand" href="/">Marineco AI Labs</a>
        <div class="navbar-nav">
            <a class="nav-link" href="/">Dashboard</a>
            <a class="nav-link" href="/contacts">Contacts</a>
            <a class="nav-link" href="/campaigns">Campaigns</a>
            <!-- ADD THIS: -->
            <a class="nav-link" href="/whatsapp/inbox">
                <i class="fab fa-whatsapp"></i> WhatsApp
            </a>
            <a class="nav-link" href="/admin/users">Users</a>
        </div>
        <!-- ... rest of navbar ... -->
    </div>
</nav>
```

---

## 🗄️ Step 3: Setup Database

### 3.1 Run SQL Schema

Connect to your Railway PostgreSQL and run:

```bash
psql $DATABASE_URL < whatsapp_inbox/01_database_schema.sql
```

Or manually via Railway dashboard → PostgreSQL → Query tab → paste contents of `01_database_schema.sql`

### 3.2 Verify Tables Created

```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name IN ('conversations', 'messages', 'leads', 'campaigns');
```

Should return 4 tables.

---

## 🔧 Step 4: Environment Variables

Add these to your Railway environment variables:

```bash
# n8n webhook URL for sending messages
N8N_SEND_WEBHOOK_URL=https://your-n8n.com/webhook/send-whatsapp

# (DATABASE_URL already exists from Railway PostgreSQL)
```

---

## 📦 Step 5: Update requirements.txt

If not already present, add:

```txt
psycopg2-binary==2.9.9  # Already in your requirements.txt
```

---

## 🚀 Step 6: Deploy to Railway

```bash
git add .
git commit -m "Add WhatsApp inbox integration"
git push origin main
```

Railway will auto-deploy.

---

## ✅ Step 7: Test Integration

### 7.1 Login to App

```
https://your-railway-app.com/login
```

### 7.2 Navigate to WhatsApp Inbox

```
https://your-railway-app.com/whatsapp/inbox
```

You should see:
- Empty inbox (no conversations yet)
- Stats panel showing 0s
- Filter tabs

### 7.3 Test with Sample Data (Optional)

Insert a test conversation via PostgreSQL:

```sql
-- Insert test campaign
INSERT INTO campaigns (name) VALUES ('Test Campaign');

-- Insert test conversation
INSERT INTO conversations (phone, language, funnel_stage)
VALUES ('+91-9876543210', 'en', 'ENGAGED')
RETURNING id;

-- Insert test message (use conversation id from above)
INSERT INTO messages (conversation_id, direction, sender, message)
VALUES ('YOUR_CONVERSATION_ID_HERE', 'inbound', 'user', 'Hello! I need help with import.');
```

Refresh inbox - you should see the test conversation.

---

## 🔍 Troubleshooting

### Issue: "No module named 'whatsapp_db'"

**Solution:** Make sure files are in project root, not in subdirectory.

### Issue: "Table 'conversations' doesn't exist"

**Solution:** Run the SQL schema file again.

### Issue: "SSE not working (no real-time updates)"

**Solution:** 
- Check DATABASE_URL is set
- PostgreSQL NOTIFY requires PostgreSQL (not SQLite)
- Check browser console for errors

### Issue: "Can't send messages"

**Solution:**
- Verify N8N_SEND_WEBHOOK_URL is set
- Check n8n webhook is running
- Check Railway logs for errors

---

## 📊 Architecture Diagram

```
User Browser
    ↓
Flask App (app_with_auth.py)
    ├─ whatsapp_routes.py (UI routes)
    ├─ whatsapp_db.py (Database queries)
    └─ PostgreSQL (Railway)
        ├─ conversations
        ├─ messages
        ├─ leads
        └─ campaigns

External:
    ├─ n8n (message orchestration)
    └─ Exotel (WhatsApp API)
```

---

## 🎯 Features Enabled

After integration, users can:

✅ **View all WhatsApp conversations** in unified inbox  
✅ **Filter by funnel stage** (New, Qualified, Converted, etc.)  
✅ **Search conversations** by phone/name/company  
✅ **Read messages** in WhatsApp-like interface  
✅ **Reply to messages** (sent via n8n → Exotel)  
✅ **Update funnel stage** manually  
✅ **Add notes** to leads  
✅ **Real-time updates** via Server-Sent Events  
✅ **View lead details** (shipment info, contact data)  
✅ **See inbox statistics** (unread, qualified, converted)  

---

## 🔐 Security Notes

- ✅ All routes protected with `@login_required`
- ✅ Uses existing user authentication
- ✅ Session-based access control
- ✅ Agent actions logged in `agent_actions` table

---

## 📈 Scaling Considerations

### For 1000+ conversations:

1. **Add pagination** to inbox view (already supported via `limit/offset`)
2. **Add indexes** (already included in schema)
3. **Use connection pooling** for PostgreSQL
4. **Consider read replicas** for heavy read loads

---

## 🎨 Customization

### Change Colors

Edit CSS variables in templates:

```css
/* Primary WhatsApp green */
background: #008069;  /* Change to your brand color */

/* Message bubble colors */
.message.outbound .message-bubble {
    background: #d9fdd3;  /* Your outbound color */
}
```

### Add Custom Filters

In `whatsapp_routes.py`:

```python
if request.args.get('priority'):
    filters['lead_score'] = '>= 80'  # High priority leads
```

---

## 📞 Support

If you encounter issues:

1. Check Railway logs: `railway logs`
2. Check browser console for JavaScript errors
3. Verify all environment variables are set
4. Ensure n8n webhooks are working

---

## ✅ Integration Checklist

- [ ] Files copied to project root
- [ ] `register_whatsapp_routes(app)` added to app_with_auth.py
- [ ] Database schema executed on Railway PostgreSQL
- [ ] N8N_SEND_WEBHOOK_URL environment variable set
- [ ] Navbar updated with WhatsApp link
- [ ] Code pushed to GitHub
- [ ] Railway deployed successfully
- [ ] Can access /whatsapp/inbox route
- [ ] Can see test conversation
- [ ] Can send test message
- [ ] Real-time updates working

---

**Ready to go! 🚀**

Next: Configure n8n workflows (see `03_N8N_DEVELOPER_GUIDE.md`)

