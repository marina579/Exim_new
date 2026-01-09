#!/bin/bash
# Automated GCS Setup Script for Marineco Quotations

set -e  # Exit on error

PROJECT_ID="wise-hub-483204-p4"
BUCKET_NAME="marineco-quotations"
SERVICE_ACCOUNT_NAME="quotation-uploader"
LOCATION="us-central1"

echo "================================================================================"
echo "🚀 AUTOMATED GCS SETUP FOR PDF QUOTATIONS"
echo "================================================================================"
echo ""
echo "Project: $PROJECT_ID"
echo "Bucket: $BUCKET_NAME"
echo "Location: $LOCATION"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "❌ gcloud CLI not found. Please install:"
    echo "   https://cloud.google.com/sdk/docs/install"
    exit 1
fi

echo "✅ gcloud CLI found"

# Set project
echo ""
echo "📋 Step 1: Setting project..."
gcloud config set project $PROJECT_ID

# Enable Cloud Storage API (if not already enabled)
echo ""
echo "📋 Step 2: Enabling Cloud Storage API..."
gcloud services enable storage.googleapis.com

# Check if bucket exists
echo ""
echo "📋 Step 3: Checking if bucket exists..."
if gsutil ls -b gs://$BUCKET_NAME &> /dev/null; then
    echo "✅ Bucket '$BUCKET_NAME' already exists"
else
    echo "Creating bucket '$BUCKET_NAME'..."
    gsutil mb -p $PROJECT_ID -c STANDARD -l $LOCATION gs://$BUCKET_NAME
    echo "✅ Bucket created"
fi

# Check if service account exists
echo ""
echo "📋 Step 4: Setting up service account..."
SERVICE_ACCOUNT_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if gcloud iam service-accounts describe $SERVICE_ACCOUNT_EMAIL &> /dev/null; then
    echo "✅ Service account already exists: $SERVICE_ACCOUNT_EMAIL"
else
    echo "Creating service account..."
    gcloud iam service-accounts create $SERVICE_ACCOUNT_NAME \
        --display-name="Quotation PDF Uploader" \
        --description="Service account for uploading quotation PDFs to GCS"
    echo "✅ Service account created"
fi

# Grant permissions to service account
echo ""
echo "📋 Step 5: Granting permissions..."
gsutil iam ch serviceAccount:${SERVICE_ACCOUNT_EMAIL}:objectCreator gs://$BUCKET_NAME
gsutil iam ch serviceAccount:${SERVICE_ACCOUNT_EMAIL}:objectViewer gs://$BUCKET_NAME
echo "✅ Permissions granted"

# Create and download service account key
echo ""
echo "📋 Step 6: Creating service account key..."
KEY_FILE="gcs-credentials.json"

if [ -f "$KEY_FILE" ]; then
    echo "⚠️  Key file already exists: $KEY_FILE"
    read -p "Overwrite? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm $KEY_FILE
        gcloud iam service-accounts keys create $KEY_FILE \
            --iam-account=$SERVICE_ACCOUNT_EMAIL
        echo "✅ New key created: $KEY_FILE"
    else
        echo "⏭️  Using existing key file"
    fi
else
    gcloud iam service-accounts keys create $KEY_FILE \
        --iam-account=$SERVICE_ACCOUNT_EMAIL
    echo "✅ Key created: $KEY_FILE"
fi

# Set file permissions
chmod 600 $KEY_FILE
echo "✅ Key file secured (chmod 600)"

# Set up lifecycle policy
echo ""
echo "📋 Step 7: Setting up lifecycle policy (auto-delete after 30 days)..."

cat > lifecycle.json << 'LIFECYCLE_EOF'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 30,
          "matchesPrefix": ["quotations/"]
        }
      }
    ]
  }
}
LIFECYCLE_EOF

gsutil lifecycle set lifecycle.json gs://$BUCKET_NAME
rm lifecycle.json
echo "✅ Lifecycle policy configured"

# Make bucket public (for public URLs)
echo ""
echo "📋 Step 8: Configuring bucket for public access..."
gsutil iam ch allUsers:objectViewer gs://$BUCKET_NAME 2>/dev/null || echo "⚠️  Public access already configured or restricted by org policy"

# Test upload
echo ""
echo "📋 Step 9: Testing upload..."

cat > test.txt << 'TEST_EOF'
This is a test file for GCS setup verification.
If you can see this, the setup is working correctly!
TEST_EOF

gsutil cp test.txt gs://$BUCKET_NAME/test/test.txt
TEST_URL="https://storage.googleapis.com/$BUCKET_NAME/test/test.txt"
echo "✅ Test file uploaded"
echo "   URL: $TEST_URL"

# Cleanup test file
gsutil rm gs://$BUCKET_NAME/test/test.txt
rm test.txt
echo "✅ Test file cleaned up"

# Summary
echo ""
echo "================================================================================"
echo "✅ GCS SETUP COMPLETE!"
echo "================================================================================"
echo ""
echo "Configuration:"
echo "  Project ID: $PROJECT_ID"
echo "  Bucket: gs://$BUCKET_NAME"
echo "  Service Account: $SERVICE_ACCOUNT_EMAIL"
echo "  Credentials: $KEY_FILE"
echo "  Lifecycle: Auto-delete after 30 days"
echo ""
echo "Environment variables set in .env:"
echo "  GCS_BUCKET_NAME=$BUCKET_NAME"
echo "  GCS_PROJECT_ID=$PROJECT_ID"
echo "  GCS_CREDENTIALS_PATH=./$KEY_FILE"
echo ""
echo "Next steps:"
echo "  1. Restart your Flask app: python3 app_with_auth.py"
echo "  2. Go to: http://localhost:5000/quotations"
echo "  3. Generate a quotation"
echo "  4. Click 'Send to WhatsApp'"
echo "  5. PDF will be automatically generated and uploaded!"
echo ""
echo "================================================================================"

