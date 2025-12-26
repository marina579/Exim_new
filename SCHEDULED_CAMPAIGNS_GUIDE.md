# 📅 Scheduled Email Campaigns - Complete Guide

## 🎯 Overview

Your app now supports **automated scheduled email campaigns** that send emails daily, weekly, monthly, or once at a specific time!

---

## ✨ Features

### Schedule Types:
- ✅ **Daily** - Send every day at a specific time (e.g., 9:00 AM)
- ✅ **Weekly** - Send on a specific day of week (e.g., Monday 9:00 AM)
- ✅ **Monthly** - Send on a specific day of month (e.g., 1st at 9:00 AM)
- ✅ **Once** - Send one time at a specific date/time

### Auto-Features:
- ✅ **Auto-sync contacts** - Automatically syncs contacts from database to Zoho Campaigns before sending
- ✅ **Background scheduling** - Runs in background, no manual intervention needed
- ✅ **Status tracking** - Tracks sent, failed, pending campaigns
- ✅ **Error handling** - Logs errors and continues with other campaigns

---

## 🚀 How It Works

### 1. Create Scheduled Campaign

```python
campaign_config = {
    'name': 'Weekly Newsletter',
    'list_key': 'marketing_list',
    'template_key': 'newsletter_template',
    'subject': 'Weekly Update from Marineco',
    'from_email': 'marketing@marineco.com',
    'from_name': 'Marineco AI',
    'schedule_type': 'weekly',  # daily, weekly, monthly, once
    'schedule_time': '09:00',   # HH:MM format
    'schedule_day': 0,          # 0=Monday, 6=Sunday (for weekly)
    'enabled': True,
    'auto_sync_contacts': True  # Auto-sync before sending
}
```

### 2. Scheduler Runs Automatically

- Scheduler runs in background
- Checks for scheduled campaigns
- Sends emails at specified times
- Updates status in database

### 3. Auto-Sync Contacts

Before each campaign:
- Gets all contacts from database
- Syncs to Zoho Campaigns list
- Ensures latest contacts are included

---

## 📋 Schedule Type Examples

### Daily Campaign
```python
{
    'schedule_type': 'daily',
    'schedule_time': '09:00'  # Every day at 9 AM
}
```

### Weekly Campaign
```python
{
    'schedule_type': 'weekly',
    'schedule_time': '09:00',
    'schedule_day': 0  # Monday (0=Mon, 1=Tue, ..., 6=Sun)
}
```

### Monthly Campaign
```python
{
    'schedule_type': 'monthly',
    'schedule_time': '09:00',
    'schedule_day': 1  # 1st of every month
}
```

### One-Time Campaign
```python
{
    'schedule_type': 'once',
    'schedule_time': '09:00',
    'start_date': '2025-01-15'  # YYYY-MM-DD format
}
```

---

## 🔧 Implementation Details

### Database Table: `scheduled_campaigns`

Stores all scheduled campaigns with:
- Campaign configuration
- Schedule settings
- Status (pending, sent, failed)
- Last sent timestamp
- Error messages

### Scheduler Service: `campaign_scheduler.py`

- Uses APScheduler for background scheduling
- Automatically starts when app starts
- Handles all schedule types
- Manages job lifecycle

### Integration Points:

1. **After Contact Enrichment**
   - Optionally auto-create scheduled campaigns
   - Sync contacts to Campaigns list

2. **UI Dashboard**
   - View all scheduled campaigns
   - Create/edit/delete campaigns
   - Enable/disable campaigns
   - View campaign history

3. **Background Process**
   - Scheduler runs continuously
   - Sends campaigns at scheduled times
   - Updates status automatically

---

## 📊 UI Features (To Be Added)

### Campaign Management Page:
- ✅ List all scheduled campaigns
- ✅ Create new campaign
- ✅ Edit existing campaign
- ✅ Enable/disable campaign
- ✅ Delete campaign
- ✅ View campaign history
- ✅ Test send campaign

### Campaign Form:
- Campaign name
- Email list selector
- Template selector
- Subject line
- Schedule type (daily/weekly/monthly/once)
- Schedule time
- Schedule day (for weekly/monthly)
- Start/end dates
- Enable/disable toggle

---

## 🎯 Use Cases

### 1. Daily Newsletter
```
Schedule: Daily at 8:00 AM
Purpose: Send daily updates to all contacts
```

### 2. Weekly Summary
```
Schedule: Weekly on Monday at 9:00 AM
Purpose: Weekly business summary
```

### 3. Monthly Report
```
Schedule: Monthly on 1st at 10:00 AM
Purpose: Monthly performance report
```

### 4. Product Launch
```
Schedule: Once on 2025-02-01 at 12:00 PM
Purpose: One-time product announcement
```

---

## ⚙️ Configuration

### Environment Variables:
```bash
# Sender email (required)
ZOHO_CAMPAIGNS_FROM_EMAIL=marketing@marineco.com
ZOHO_CAMPAIGNS_FROM_NAME=Marineco AI

# Zoho access (can use same as CRM)
ZOHO_CAMPAIGNS_ACCESS_TOKEN=<token>
# OR
ZOHO_CAMPAIGNS_API_KEY=<api_key>
```

### Scheduler Settings:
- Runs in background automatically
- No additional configuration needed
- Persists across app restarts (via database)

---

## 📝 API Endpoints (To Be Added)

### Create Campaign:
```
POST /api/campaigns/schedule
Body: { campaign_config }
```

### List Campaigns:
```
GET /api/campaigns/scheduled
```

### Update Campaign:
```
PUT /api/campaigns/scheduled/<id>
Body: { updates }
```

### Delete Campaign:
```
DELETE /api/campaigns/scheduled/<id>
```

### Test Send:
```
POST /api/campaigns/scheduled/<id>/test
```

---

## 🔍 Monitoring

### Check Campaign Status:
- View in database: `scheduled_campaigns` table
- Check logs for execution details
- View last sent timestamp
- Check error messages if failed

### Logs to Watch:
```
✅ Scheduled campaign 'Weekly Newsletter' (ID: 1)
📧 Executing scheduled campaign: 1
🔄 Auto-syncing contacts from CRM to list: marketing_list
✅ Synced 150 contacts to Campaigns list
📤 Sending campaign: campaign_abc123
✅ Scheduled campaign sent successfully: campaign_abc123
```

---

## ⚠️ Important Notes

### Sender Email:
- Must be verified in Zoho Campaigns
- Must have DNS TXT record
- Cannot use Gmail/Yahoo

### Contact Sync:
- Auto-syncs before each campaign
- Only syncs contacts with email addresses
- Syncs from database to Zoho Campaigns list

### Schedule Accuracy:
- Scheduler runs in background
- Times are in server timezone
- Adjust for your timezone if needed

### Error Handling:
- Failed campaigns are logged
- Status updated in database
- Scheduler continues with other campaigns
- Check error_message field for details

---

## 🚀 Next Steps

1. ✅ **Service Created** - `campaign_scheduler.py`
2. ✅ **Database Table** - `scheduled_campaigns`
3. ⏳ **UI Integration** - Add campaign management page
4. ⏳ **API Routes** - Add REST endpoints
5. ⏳ **Testing** - Test with small batches first

---

## 📋 Example: Create Daily Campaign

```python
from campaign_scheduler import campaign_scheduler

config = {
    'name': 'Daily Newsletter',
    'list_key': 'marketing_list',
    'template_key': 'daily_template',
    'subject': 'Your Daily Update',
    'from_email': 'marketing@marineco.com',
    'from_name': 'Marineco AI',
    'schedule_type': 'daily',
    'schedule_time': '09:00',
    'enabled': True,
    'auto_sync_contacts': True
}

success, schedule_id, message = campaign_scheduler.create_scheduled_campaign(config)
```

---

**Ready to add UI?** Let me know and I'll create the campaign management interface! 🚀

