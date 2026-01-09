# Railway Environment Variables Setup

## Required Environment Variables

Add these in your Railway project settings:

### 1. GCS Configuration (for PDF Storage)
```
GCS_BUCKET_NAME=marineco-quotations
GCS_PROJECT_ID=wise-hub-483204-p4
```

### 2. GCS Credentials (Service Account Key)

You need to add the service account key as a JSON string:

```
GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"wise-hub-483204-p4",...}
```

### 3. N8N Webhook (for WhatsApp Messaging)
```
N8N_WEBHOOK_URL=https://n8n.srv1243049.hstgr.cloud/webhook/0a82c35c-0bb2-4d12-934f-02411715e85a
```

This webhook is used to send WhatsApp messages from the Web UI.

## How to Get Service Account Key:

1. Go to: https://console.cloud.google.com/iam-admin/serviceaccounts?project=wise-hub-483204-p4
2. Create a new service account OR use existing one
3. Click on the service account
4. Go to "Keys" tab
5. Click "Add Key" → "Create new key" → JSON
6. Download the JSON file
7. Open it in a text editor
8. Copy the ENTIRE JSON content (single line)
9. Paste it as the value for `GCS_CREDENTIALS_JSON` in Railway

## How to Add in Railway:

1. Go to your Railway project
2. Click on your service
3. Go to "Variables" tab
4. Click "New Variable"
5. Add each variable name and value
6. Click "Deploy" or let it auto-deploy

## System Dependencies:

The `nixpacks.toml` file will automatically install:
- Pango (for PDF text rendering)
- Cairo (for PDF graphics)
- GObject (required libraries)

Railway will install these during deployment.

## About GCS Authentication:

**For Railway (external platform), we use Service Account Keys:**
- ✅ Simple and reliable for external platforms like Railway
- ✅ Works immediately without complex setup
- ⚠️  Google recommends Workload Identity Federation for better security
- ⚠️  But Workload Identity Federation requires complex OIDC setup

**Why not Workload Identity Federation?**
- Requires OIDC token exchange
- More complex configuration
- Railway doesn't natively support it (yet)
- Service account keys are the practical choice for external deployments

**Security Best Practices:**
- Store the key securely in Railway environment variables (not in code)
- Use least-privilege IAM roles (only Storage Object Creator permission)
- Rotate keys periodically
- Never commit keys to Git

## After Setup:

1. Add all environment variables in Railway
2. Push your code to GitHub
3. Railway will automatically rebuild
4. PDF generation will work!
5. WhatsApp messaging will work!

