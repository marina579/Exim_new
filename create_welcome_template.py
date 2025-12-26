#!/usr/bin/env python3
"""
Create Welcome Email Template in Zoho Campaigns
Uploads the HTML template and configures it for auto-welcome emails.
"""

import os
import sys
from dotenv import load_dotenv
from zoho_campaigns_service import ZohoCampaignsService
from zoho_crm_service import ZohoCRMService

load_dotenv()

def read_template_file():
    """Read the HTML template file."""
    template_path = os.path.join(os.path.dirname(__file__), 'templates', 'email', 'welcome_template.html')
    
    if not os.path.exists(template_path):
        print(f"❌ Template file not found: {template_path}")
        return None
    
    with open(template_path, 'r', encoding='utf-8') as f:
        return f.read()

def upload_brochures_to_zoho():
    """
    Upload brochure PDFs to Zoho Campaigns and get their URLs.
    Returns tuple of (brochure1_url, brochure2_url)
    """
    print("\n📎 Uploading brochures to Zoho Campaigns...")
    
    # Get access token
    crm_service = ZohoCRMService()
    access_token, error = crm_service.get_access_token()
    
    if error or not access_token:
        print(f"❌ Cannot get access token: {error}")
        return None, None
    
    campaigns_service = ZohoCampaignsService(access_token=access_token)
    
    # Look for brochures in downloads folder
    downloads_path = os.path.join(os.path.expanduser('~'), 'Downloads')
    brochure_files = []
    
    for filename in os.listdir(downloads_path):
        if filename.lower().endswith('.pdf') and 'brochure' in filename.lower():
            brochure_files.append(os.path.join(downloads_path, filename))
    
    if len(brochure_files) < 2:
        print(f"⚠️  Found {len(brochure_files)} brochure(s) in Downloads. Need 2 brochures.")
        print("   Please ensure you have 2 PDF brochures in your Downloads folder.")
        return None, None
    
    brochure1_path = brochure_files[0]
    brochure2_path = brochure_files[1]
    
    print(f"   Found: {os.path.basename(brochure1_path)}")
    print(f"   Found: {os.path.basename(brochure2_path)}")
    
    # Note: Zoho Campaigns file upload API may require different approach
    # For now, we'll use placeholder URLs that you'll need to update
    # after uploading manually to Zoho Campaigns
    
    print("\n⚠️  IMPORTANT: Upload brochures manually to Zoho Campaigns:")
    print("   1. Go to Zoho Campaigns → Files")
    print("   2. Upload both PDF brochures")
    print("   3. Get the public URLs for each brochure")
    print("   4. Update the template with these URLs")
    
    return "{{brochure1_url}}", "{{brochure2_url}}"

def create_template():
    """Create the welcome email template in Zoho Campaigns."""
    print("\n" + "="*70)
    print("📧 CREATING WELCOME EMAIL TEMPLATE IN ZOHO CAMPAIGNS")
    print("="*70 + "\n")
    
    # Get access token
    crm_service = ZohoCRMService()
    access_token, error = crm_service.get_access_token()
    
    if error or not access_token:
        print(f"❌ Cannot get access token: {error}")
        print("\nPlease check your Zoho credentials:")
        print("  - ZOHO_CLIENT_ID")
        print("  - ZOHO_CLIENT_SECRET")
        print("  - ZOHO_REFRESH_TOKEN")
        return False
    
    # Read template
    html_content = read_template_file()
    if not html_content:
        return False
    
    # Get brochure URLs (or placeholders)
    brochure1_url, brochure2_url = upload_brochures_to_zoho()
    
    # Replace brochure placeholders in template
    # Note: You'll need to replace these with actual Zoho Campaigns file URLs
    html_content = html_content.replace('{{brochure1_url}}', brochure1_url or 'https://your-brochure1-url.com')
    html_content = html_content.replace('{{brochure2_url}}', brochure2_url or 'https://your-brochure2-url.com')
    
    # Create campaigns service
    campaigns_service = ZohoCampaignsService(access_token=access_token)
    
    # Template details
    template_name = "Marineco Welcome Email"
    subject = "Welcome to Marineco - Your Trusted Logistics Partner"
    
    print(f"📝 Creating template: {template_name}")
    print(f"   Subject: {subject}")
    
    # Create template in Zoho Campaigns
    success, template_key = campaigns_service.create_email_template(
        template_name=template_name,
        subject=subject,
        html_content=html_content,
        text_content=""  # Plain text version (optional)
    )
    
    if success:
        print(f"\n✅ Template created successfully!")
        print(f"   Template Key: {template_key}")
        print(f"\n📋 Next Steps:")
        print(f"   1. Add to Railway/.env:")
        print(f"      ZOHO_CAMPAIGNS_WELCOME_TEMPLATE={template_key}")
        print(f"   2. Upload brochures to Zoho Campaigns Files")
        print(f"   3. Get brochure URLs and update template in Zoho")
        print(f"   4. Test the template with a sample email")
        print(f"   5. Enable auto-welcome emails:")
        print(f"      AUTO_WELCOME_EMAIL=true")
        return True
    else:
        print(f"\n❌ Failed to create template")
        return False

if __name__ == '__main__':
    try:
        success = create_template()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

