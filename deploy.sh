#!/bin/bash
# WhatsApp Inbox Deployment Script

echo "🚀 Starting deployment to Railway via GitHub..."
echo ""

cd /Users/sai/Documents/GitHub/Exim_new

echo "📋 Files to be committed:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ls -lh app_with_auth.py 2>/dev/null | awk '{print "  ✓", $9, "(" $5 ")"}'
ls -lh whatsapp_db.py 2>/dev/null | awk '{print "  ✓", $9, "(" $5 ")"}'
ls -lh whatsapp_routes.py 2>/dev/null | awk '{print "  ✓", $9, "(" $5 ")"}'
ls -lh setup_whatsapp_db.py 2>/dev/null | awk '{print "  ✓", $9, "(" $5 ")"}'
ls -lh DEPLOY_TO_RAILWAY.sql 2>/dev/null | awk '{print "  ✓", $9, "(" $5 ")"}'
ls -lh SETUP_INSTRUCTIONS.md 2>/dev/null | awk '{print "  ✓", $9, "(" $5 ")"}'
ls -lh QUICK_START.txt 2>/dev/null | awk '{print "  ✓", $9, "(" $5 ")"}'
ls -lh templates/whatsapp_*.html 2>/dev/null | awk '{print "  ✓", $9, "(" $5 ")"}'
echo "  ✓ whatsapp_inbox/ (folder)"
echo ""

# Stage all changes
echo "📦 Staging files..."
/usr/bin/git add app_with_auth.py
/usr/bin/git add whatsapp_db.py
/usr/bin/git add whatsapp_routes.py
/usr/bin/git add setup_whatsapp_db.py
/usr/bin/git add DEPLOY_TO_RAILWAY.sql
/usr/bin/git add SETUP_INSTRUCTIONS.md
/usr/bin/git add QUICK_START.txt
/usr/bin/git add templates/whatsapp_inbox.html templates/whatsapp_chat.html 2>/dev/null
/usr/bin/git add whatsapp_inbox/
echo "✅ Files staged!"
echo ""

# Commit
echo "💾 Committing changes..."
/usr/bin/git commit -m "Add WhatsApp Inbox integration with RBAC

Features:
- WhatsApp conversation management UI
- Real-time message updates via SSE
- Funnel stage tracking (NEW -> ENGAGED -> QUALIFIED -> CONVERTED)
- Agent reply functionality
- Role-based access control (admin/whatsapp_agent/ui_viewer/full_access)
- Database schema with 7 new tables
- Integration with n8n workflows
- Permission management system

Tables: campaigns, conversations, messages, leads, agent_actions, email_notifications, permission_audit_log"

if [ $? -eq 0 ]; then
    echo "✅ Commit successful!"
    echo ""
else
    echo "⚠️  Nothing to commit or commit failed"
    echo ""
fi

# Push
echo "🚀 Pushing to GitHub (this will trigger Railway deployment)..."
/usr/bin/git push origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ DEPLOYMENT INITIATED!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📡 Railway is now building and deploying..."
    echo ""
    echo "⚠️  IMPORTANT: You still need to create database tables!"
    echo ""
    echo "   1. Go to Railway → PostgreSQL → Query tab"
    echo "   2. Copy contents of: DEPLOY_TO_RAILWAY.sql"
    echo "   3. Paste and click 'Run Query'"
    echo ""
    echo "📊 Monitor deployment:"
    echo "   • Railway Dashboard → Deployments"
    echo "   • Should complete in ~2-3 minutes"
    echo ""
    echo "🎉 After deployment completes:"
    echo "   Visit: https://your-app.railway.app/whatsapp/inbox"
    echo ""
else
    echo ""
    echo "❌ Push failed!"
    echo ""
    echo "Common fixes:"
    echo "  1. Check internet connection"
    echo "  2. Verify GitHub credentials"
    echo "  3. Try: git pull origin main (if behind)"
    echo ""
fi

