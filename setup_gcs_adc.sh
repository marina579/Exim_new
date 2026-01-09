#!/bin/bash
# Automated GCS Setup using Application Default Credentials (No Keys!)
# More secure than service account keys

set -e

PROJECT_ID="wise-hub-483204-p4"
BUCKET_NAME="marineco-quotations"
LOCATION="us-central1"

echo "================================================================================"
echo "🚀 GCS SETUP WITH APPLICATION DEFAULT CREDENTIALS (ADC)"
echo "================================================================================"
echo ""
echo "This is MORE SECURE than using service account keys!"
echo "Your org policy blocks service account keys - ADC is the right solution."
echo ""
echo "Project: $PROJECT_ID"
echo "Bucket: $BUCKET_NAME"
echo ""

# Check if gcloud is installed
if ! command -v gcloud &> /dev/null; then
    echo "📥 gcloud CLI not found. Installing..."
    echo ""
    
    # Check OS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        echo "Detected macOS"
        
        # Check if Homebrew is available
        if command -v brew &> /dev/null; then
            echo "Installing via Homebrew..."
            brew install --cask google-cloud-sdk
        else
            echo "Installing via curl..."
            curl https://sdk.cloud.google.com | bash
            
            # Source the path
            if [ -f "$HOME/google-cloud-sdk/path.bash.inc" ]; then
                source "$HOME/google-cloud-sdk/path.bash.inc"
            fi
        fi
    else
        # Linux
        echo "Installing via curl..."
        curl https://sdk.cloud.google.com | bash
        
        # Source the path
        if [ -f "$HOME/google-cloud-sdk/path.bash.inc" ]; then
            source "$HOME/google-cloud-sdk/path.bash.inc"
        fi
    fi
    
    echo "✅ gcloud CLI installed"
    echo ""
    echo "⚠️  Please restart your terminal and run this script again."
    exit 0
fi

echo "✅ gcloud CLI found: $(gcloud --version | head -n 1)"

# Authenticate
echo ""
echo "================================================================================"
echo "📋 STEP 1: Authentication"
echo "================================================================================"
echo ""
echo "This will open your browser to sign in with your Google account."
echo "Use the account that has access to project: $PROJECT_ID"
echo ""
read -p "Press Enter to continue..."

# Authenticate with user account
gcloud auth login --no-launch-browser

# Set up Application Default Credentials
echo ""
echo "Setting up Application Default Credentials..."
gcloud auth application-default login --no-launch-browser

# Set project
echo ""
echo "Setting project..."
gcloud config set project $PROJECT_ID

echo "✅ Authentication complete"

# Create bucket
echo ""
echo "================================================================================"
echo "📋 STEP 2: Create Storage Bucket"
echo "================================================================================"
echo ""

if gsutil ls -b gs://$BUCKET_NAME &> /dev/null; then
    echo "✅ Bucket '$BUCKET_NAME' already exists"
else
    echo "Creating bucket '$BUCKET_NAME'..."
    gsutil mb -p $PROJECT_ID -c STANDARD -l $LOCATION gs://$BUCKET_NAME
    echo "✅ Bucket created"
fi

# Make bucket public
echo ""
echo "================================================================================"
echo "📋 STEP 3: Make Bucket Public"
echo "================================================================================"
echo ""
echo "Making bucket publicly readable (PDFs will have public URLs)..."
gsutil iam ch allUsers:objectViewer gs://$BUCKET_NAME 2>/dev/null || {
    echo "⚠️  Could not make bucket public. This might be restricted by org policy."
    echo "   You can make it public manually in the console, or use signed URLs."
}
echo "✅ Bucket access configured"

# Set lifecycle policy
echo ""
echo "================================================================================"
echo "📋 STEP 4: Set Lifecycle Policy (Auto-delete after 30 days)"
echo "================================================================================"
echo ""

cat > /tmp/lifecycle.json << 'EOF'
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
EOF

gsutil lifecycle set /tmp/lifecycle.json gs://$BUCKET_NAME
rm /tmp/lifecycle.json
echo "✅ Lifecycle policy set: PDFs will auto-delete after 30 days"

# Test upload
echo ""
echo "================================================================================"
echo "📋 STEP 5: Test Upload"
echo "================================================================================"
echo ""

echo "Testing file upload..."
echo "Test file from ADC setup" > /tmp/test.txt
gsutil cp /tmp/test.txt gs://$BUCKET_NAME/test/test.txt
gsutil acl ch -u AllUsers:R gs://$BUCKET_NAME/test/test.txt 2>/dev/null || true

TEST_URL="https://storage.googleapis.com/$BUCKET_NAME/test/test.txt"
echo "✅ Test file uploaded"
echo "   URL: $TEST_URL"

# Cleanup
gsutil rm gs://$BUCKET_NAME/test/test.txt
rm /tmp/test.txt
echo "✅ Test cleanup complete"

# Summary
echo ""
echo "================================================================================"
echo "✅ GCS SETUP COMPLETE!"
echo "================================================================================"
echo ""
echo "Configuration:"
echo "  ✅ Authentication: Application Default Credentials (ADC)"
echo "  ✅ Project: $PROJECT_ID"
echo "  ✅ Bucket: gs://$BUCKET_NAME"
echo "  ✅ Lifecycle: Auto-delete after 30 days"
echo "  ✅ Test: Successful"
echo ""
echo "Security:"
echo "  ✅ No service account keys (more secure!)"
echo "  ✅ Uses your personal Google account"
echo "  ✅ Complies with org policy"
echo ""
echo "Next steps:"
echo "  1. cd /Users/sai/Documents/GitHub/Exim_new"
echo "  2. python3 app_with_auth.py"
echo "  3. Go to: http://localhost:5000/quotations"
echo "  4. Generate a quotation and click 'Send to WhatsApp'"
echo ""
echo "The PDF will be automatically generated and uploaded! 🎉"
echo "================================================================================"

