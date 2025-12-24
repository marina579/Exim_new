# Test Locally Before Deployment

## Quick Start

1. **Create virtual environment:**
   ```bash
   cd /Users/sai/exim_contact_enricher_deploy
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set environment variables:**
   
   Option A: Create `.env` file (recommended)
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

   Option B: Export variables
   ```bash
   export OPENAI_API_KEY='your-key'
   export SERPAPI_API_KEY='your-key'
   export GEMINI_API_KEY='your-key'
   export ZOHO_CLIENT_ID='your-id'
   export ZOHO_CLIENT_SECRET='your-secret'
   export ZOHO_REFRESH_TOKEN='your-token'
   export ZOHO_DATA_CENTER='com'
   export SECRET_KEY='your-secret-key'
   ```

4. **Run the application:**
   ```bash
   python app_with_auth.py
   ```

5. **Access the app:**
   - Open: http://127.0.0.1:5000/login
   - Username: `admin`
   - Password: `admin123`
   - ⚠️ Change password after first login!

## Testing Checklist

- [ ] App starts without errors
- [ ] Login page loads
- [ ] Can log in with admin/admin123
- [ ] Dashboard loads
- [ ] Can upload a test Excel file
- [ ] Contact enrichment works
- [ ] Zoho integration configured and tested
- [ ] Contact push to Zoho works

## Troubleshooting

### Import errors
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt` again

### Missing environment variables
- Check `.env` file exists and has correct values
- Or ensure all env vars are exported

### Database errors
- The app will create SQLite database automatically in `data/` folder
- For PostgreSQL, set `DATABASE_URL` environment variable

## Ready to Deploy?

Once local testing passes, you can deploy to Railway or Heroku using the files in this folder.

