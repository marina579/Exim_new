# Railway Environment Variables Setup

## Required Environment Variables

Add these in your Railway project settings:

### 1. GCS Configuration
```
GCS_BUCKET_NAME=marineco-quotations
GCS_PROJECT_ID=wise-hub-483204-p4
```

### 2. GCS Credentials (Service Account Key)

You need to add the service account key as a JSON string:

```
GCS_CREDENTIALS_JSON={"type":"service_account","project_id":"wise-hub-483204-p4",...}
```

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

## After Setup:

Railway will automatically rebuild and the PDF generation should work!

