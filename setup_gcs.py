#!/usr/bin/env python3
"""
Google Cloud Storage Setup Script for PDF Quotations
Run this script to configure GCS for quotation PDFs
"""

import os
import sys

print("="*80)
print("GOOGLE CLOUD STORAGE SETUP FOR PDF QUOTATIONS")
print("="*80)

# Step 1: Check environment variables
print("\n📋 STEP 1: Check Configuration")
print("-" * 80)

gcs_bucket = os.environ.get('GCS_BUCKET_NAME', '')
gcs_project = os.environ.get('GCS_PROJECT_ID', '')
gcs_creds = os.environ.get('GCS_CREDENTIALS_PATH', './gcs-credentials.json')

if not gcs_bucket:
    print("⚠️  GCS_BUCKET_NAME not set")
    print("   Please set: export GCS_BUCKET_NAME='your-bucket-name'")
else:
    print(f"✅ GCS_BUCKET_NAME: {gcs_bucket}")

if not gcs_project:
    print("⚠️  GCS_PROJECT_ID not set")
    print("   Please set: export GCS_PROJECT_ID='your-project-id'")
else:
    print(f"✅ GCS_PROJECT_ID: {gcs_project}")

if not os.path.exists(gcs_creds):
    print(f"⚠️  GCS credentials not found at: {gcs_creds}")
    print("   Please download your service account JSON and save it as gcs-credentials.json")
else:
    print(f"✅ GCS credentials found: {gcs_creds}")

# Step 2: Test GCS connection
print("\n🔌 STEP 2: Test GCS Connection")
print("-" * 80)

if gcs_bucket and (os.path.exists(gcs_creds) or gcs_project):
    try:
        from google.cloud import storage
        
        if os.path.exists(gcs_creds):
            client = storage.Client.from_service_account_json(gcs_creds, project=gcs_project)
        else:
            client = storage.Client(project=gcs_project)
        
        # Try to access bucket
        bucket = client.bucket(gcs_bucket)
        
        if bucket.exists():
            print(f"✅ Successfully connected to bucket: {gcs_bucket}")
            
            # Get bucket info
            print(f"\n📊 Bucket Information:")
            print(f"   - Location: {bucket.location}")
            print(f"   - Storage Class: {bucket.storage_class}")
            print(f"   - Created: {bucket.time_created}")
            
        else:
            print(f"⚠️  Bucket '{gcs_bucket}' does not exist")
            print("\nTo create the bucket, run:")
            print(f"   gsutil mb -p {gcs_project} -c STANDARD -l us-central1 gs://{gcs_bucket}")
            
    except ImportError:
        print("❌ google-cloud-storage not installed")
        print("   Run: pip3 install google-cloud-storage")
        sys.exit(1)
    
    except Exception as e:
        print(f"❌ Error connecting to GCS: {str(e)}")
        sys.exit(1)
else:
    print("⚠️  GCS not configured. Please set environment variables and credentials.")

# Step 3: Set up lifecycle policy
print("\n♻️  STEP 3: Set Up Lifecycle Policy (Auto-delete after 30 days)")
print("-" * 80)

if gcs_bucket and bucket.exists():
    try:
        from gcs_pdf_handler import setup_gcs_lifecycle_policy
        
        response = input("Do you want to set up auto-deletion of quotations after 30 days? (y/n): ")
        
        if response.lower() == 'y':
            success = setup_gcs_lifecycle_policy()
            if success:
                print("✅ Lifecycle policy configured successfully!")
                print("   - Quotations will be automatically deleted after 30 days")
                print("   - This saves storage costs")
            else:
                print("❌ Failed to set up lifecycle policy")
        else:
            print("⏭️  Skipped lifecycle policy setup")
    
    except Exception as e:
        print(f"❌ Error setting up lifecycle policy: {str(e)}")

# Step 4: Test PDF generation and upload
print("\n🧪 STEP 4: Test PDF Generation and Upload")
print("-" * 80)

if gcs_bucket and bucket.exists():
    response = input("Do you want to test PDF generation and upload? (y/n): ")
    
    if response.lower() == 'y':
        try:
            from gcs_pdf_handler import generate_and_upload_quotation_pdf
            
            # Create test HTML
            test_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Quotation</title>
                <style>
                    body { font-family: Arial, sans-serif; padding: 20px; }
                    h1 { color: #2c3e50; }
                </style>
            </head>
            <body>
                <h1>MARINECO PRIVATE LIMITED</h1>
                <h2>Test Quotation</h2>
                <p><strong>Quotation Number:</strong> TEST-001</p>
                <p><strong>Date:</strong> 08-JAN-2026</p>
                <p><strong>Client:</strong> Test Client</p>
                <p>This is a test quotation for GCS setup verification.</p>
            </body>
            </html>
            """
            
            print("\nGenerating test PDF...")
            result = generate_and_upload_quotation_pdf(test_html, 'TEST-001')
            
            if result['success']:
                print(f"\n✅ Test successful!")
                print(f"   - PDF URL: {result['url']}")
                print(f"   - Size: {result['size']:,} bytes ({result['size']/1024:.1f} KB)")
                print(f"   - Expires: {result['expires_at']}")
                print(f"\n   Open this URL in your browser to verify the PDF:")
                print(f"   {result['url']}")
                
                # Ask if user wants to delete test file
                delete = input("\nDelete test file? (y/n): ")
                if delete.lower() == 'y':
                    from gcs_pdf_handler import delete_pdf_from_gcs
                    if delete_pdf_from_gcs(result['blob_name']):
                        print("✅ Test file deleted")
            else:
                print(f"\n❌ Test failed: {result.get('error')}")
        
        except Exception as e:
            print(f"❌ Error during test: {str(e)}")
            import traceback
            traceback.print_exc()

# Step 5: Cost estimation
print("\n💰 STEP 5: Cost Estimation")
print("-" * 80)

try:
    from gcs_pdf_handler import calculate_gcs_cost
    
    print("\nEstimated monthly costs:")
    print("-" * 40)
    
    for num in [1000, 10000, 50000]:
        cost = calculate_gcs_cost(num, storage_days=30)
        print(f"\n{num:,} quotations/month:")
        print(f"  Storage: ${cost['storage_cost']:.4f}")
        print(f"  Network: ${cost['network_cost']:.4f}")
        print(f"  Total: ${cost['total_cost']:.2f}")
        print(f"  Per quotation: ${cost['cost_per_quotation']:.6f}")

except Exception as e:
    print(f"⚠️  Could not calculate costs: {str(e)}")

# Summary
print("\n" + "="*80)
print("SETUP SUMMARY")
print("="*80)

checks = {
    "GCS Bucket Configured": bool(gcs_bucket and gcs_project),
    "Credentials Available": os.path.exists(gcs_creds) or bool(gcs_project),
    "Connection Successful": 'bucket' in locals() and bucket.exists() if 'bucket' in locals() else False,
}

for check, status in checks.items():
    icon = "✅" if status else "❌"
    print(f"{icon} {check}")

if all(checks.values()):
    print("\n🎉 GCS is fully configured and ready to use!")
    print("\nNext steps:")
    print("  1. Restart your Flask app: python3 app_with_auth.py")
    print("  2. Go to http://localhost:5000/quotations")
    print("  3. Generate a quotation")
    print("  4. Click 'Send to WhatsApp'")
    print("  5. PDF will be automatically generated and uploaded to GCS!")
else:
    print("\n⚠️  GCS is not fully configured. Please complete the setup steps above.")

print("="*80)

