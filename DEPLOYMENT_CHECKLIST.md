# 🚀 Deployment Checklist

## Pre-Deployment

- [x] Clean deployment folder created
- [x] All source files included
- [x] Configuration files ready (requirements.txt, Procfile, railway.json)
- [x] Database copied (optional - for testing)
- [x] UI updated (Database → Contacts)

## Environment Variables to Set

Make sure these are set in your deployment platform:

### Required
- `OPENAI_API_KEY` - Your OpenAI API key
- `SERPAPI_API_KEY` - Your SerpAPI key
- `SECRET_KEY` - Generate a random key: `python3 -c "import secrets; print(secrets.token_hex(32))"`

### Optional but Recommended
- `GEMINI_API_KEY` - For Gemini AI enrichment
- `ZOHO_CLIENT_ID` - Zoho CRM integration
- `ZOHO_CLIENT_SECRET` - Zoho CRM integration
- `ZOHO_REFRESH_TOKEN` - Zoho CRM integration
- `ZOHO_DATA_CENTER` - Usually 'com' or 'in'

### Optional Configuration
- `AUTO_PUSH_TO_ZOHO` - Set to 'true' (default) or 'false'
- `DATABASE_URL` - Auto-provided by Railway if using PostgreSQL

## Deployment Steps (Railway)

1. **Push to Git** (if using GitHub integration)
   ```bash
   git init
   git add .
   git commit -m "Ready for deployment"
   git remote add origin <your-repo-url>
   git push -u origin main
   ```

2. **Create Railway Project**
   - Go to https://railway.app
   - New Project → Deploy from GitHub repo
   - Select your repository

3. **Set Environment Variables**
   - Go to your project → Variables tab
   - Add all required variables from the list above

4. **Deploy**
   - Railway will auto-deploy on git push
   - Or click "Deploy" button

5. **Get Your URL**
   - Railway provides a public URL
   - Update it in your project settings if needed

## After Deployment

- [ ] App starts successfully (check logs)
- [ ] Can access login page
- [ ] Login works (admin/admin123 - **CHANGE PASSWORD!**)
- [ ] Test file upload
- [ ] Test contact enrichment
- [ ] Test Zoho integration (if configured)

## Security Reminders

⚠️ **IMPORTANT:**
1. **Change default password** immediately after first login
2. **Use strong SECRET_KEY** in production
3. **Don't commit .env file** (already in .gitignore)
4. **Set SESSION_COOKIE_SECURE=True** if using HTTPS

## Troubleshooting

- Check Railway logs for errors
- Verify all environment variables are set
- Ensure database folder exists (auto-created)
- Check API keys are valid

Good luck with your deployment! 🚀

