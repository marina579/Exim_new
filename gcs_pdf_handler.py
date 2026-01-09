"""
Google Cloud Storage and PDF Generation Handler
Manages PDF generation and upload to GCS with auto-deletion
"""

import io
import os
import json
import tempfile
from datetime import datetime, timedelta
from weasyprint import HTML
from google.cloud import storage

# GCS Configuration
GCS_BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'marineco-quotations')
GCS_PROJECT_ID = os.environ.get('GCS_PROJECT_ID', '')
GCS_CREDENTIALS_PATH = os.environ.get('GCS_CREDENTIALS_PATH', './gcs-credentials.json')
GCS_CREDENTIALS_JSON = os.environ.get('GCS_CREDENTIALS_JSON', '')  # For Railway deployment

# Quotation expiry (days)
QUOTATION_EXPIRY_DAYS = int(os.environ.get('QUOTATION_EXPIRY_DAYS', '30'))


def generate_pdf_from_html(html_content):
    """
    Generate PDF from HTML content in memory
    
    Args:
        html_content (str): HTML string to convert to PDF
        
    Returns:
        bytes: PDF file as bytes
    """
    try:
        # Convert HTML to PDF in memory
        pdf_bytes = HTML(string=html_content).write_pdf()
        return pdf_bytes
    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        raise


def get_gcs_client():
    """
    Get Google Cloud Storage client
    
    Priority order (tries in sequence):
    1. Application Default Credentials (ADC) - for local development with gcloud
    2. Environment variable JSON (GCS_CREDENTIALS_JSON) - for Railway/Heroku deployment  
    3. Service account key file - fallback
    
    Returns:
        storage.Client: GCS client instance
    """
    try:
        # Option 1: Try Application Default Credentials (local development)
        # Works when user has run: gcloud auth application-default login
        try:
            client = storage.Client(project=GCS_PROJECT_ID)
            # Test if we can access the client
            _ = client.project
            print(f"✅ Using Application Default Credentials (ADC)")
            return client
        except Exception as adc_error:
            pass  # Try next option
            
        # Option 2: Try environment variable JSON (Railway/Heroku deployment)
        # Set GCS_CREDENTIALS_JSON as environment variable with full JSON string
        if GCS_CREDENTIALS_JSON:
            try:
                # Parse JSON from environment variable
                credentials_dict = json.loads(GCS_CREDENTIALS_JSON)
                
                # Create temporary file for credentials
                # (Google Cloud library expects a file path)
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
                    json.dump(credentials_dict, temp_file)
                    temp_credentials_path = temp_file.name
                
                client = storage.Client.from_service_account_json(
                    temp_credentials_path,
                    project=GCS_PROJECT_ID
                )
                
                # Clean up temp file
                try:
                    os.unlink(temp_credentials_path)
                except:
                    pass
                
                print(f"✅ Using credentials from environment variable (Railway/Heroku)")
                return client
                
            except json.JSONDecodeError as e:
                print(f"⚠️  Invalid JSON in GCS_CREDENTIALS_JSON: {str(e)}")
            except Exception as e:
                print(f"⚠️  Could not use GCS_CREDENTIALS_JSON: {str(e)}")
            
        # Option 3: Try service account key file (traditional approach)
        if os.path.exists(GCS_CREDENTIALS_PATH):
            print(f"✅ Using service account key file: {GCS_CREDENTIALS_PATH}")
            client = storage.Client.from_service_account_json(
                GCS_CREDENTIALS_PATH,
                project=GCS_PROJECT_ID
            )
            return client
            
        # No authentication method available
        raise Exception(
            "❌ No GCS authentication available. Choose one:\n\n"
            "For local development:\n"
            "  → Run: gcloud auth application-default login\n\n"
            "For Railway/Heroku deployment:\n"
            "  → Set environment variable: GCS_CREDENTIALS_JSON='{...json...}'\n\n"
            "For traditional setup:\n"
            "  → Provide service account key at: " + GCS_CREDENTIALS_PATH
        )
        
    except Exception as e:
        print(f"❌ Error creating GCS client: {str(e)}")
        raise


def upload_pdf_to_gcs(pdf_bytes, quote_number, expiry_days=QUOTATION_EXPIRY_DAYS):
    """
    Upload PDF to Google Cloud Storage with public URL
    
    Args:
        pdf_bytes (bytes): PDF file as bytes
        quote_number (str): Quotation number for filename
        expiry_days (int): Days until file expires (default 30)
        
    Returns:
        dict: {
            'url': Public URL to download PDF,
            'blob_name': GCS blob name,
            'size': File size in bytes,
            'expires_at': Expiry timestamp
        }
    """
    try:
        # Get GCS client
        client = get_gcs_client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        blob_name = f"quotations/{quote_number}_{timestamp}.pdf"
        
        # Create blob
        blob = bucket.blob(blob_name)
        
        # Set metadata
        blob.metadata = {
            'quote_number': quote_number,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(days=expiry_days)).isoformat()
        }
        
        # Set content type
        blob.content_type = 'application/pdf'
        
        # Upload PDF
        blob.upload_from_string(pdf_bytes, content_type='application/pdf')
        
        # Make blob publicly accessible (temporary)
        blob.make_public()
        
        # Get public URL
        public_url = blob.public_url
        
        return {
            'url': public_url,
            'blob_name': blob_name,
            'size': len(pdf_bytes),
            'expires_at': (datetime.now() + timedelta(days=expiry_days)).isoformat(),
            'quote_number': quote_number
        }
        
    except Exception as e:
        print(f"Error uploading PDF to GCS: {str(e)}")
        raise


def delete_pdf_from_gcs(blob_name):
    """
    Delete PDF from Google Cloud Storage
    
    Args:
        blob_name (str): GCS blob name to delete
        
    Returns:
        bool: True if deleted successfully
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        
        if blob.exists():
            blob.delete()
            return True
        return False
        
    except Exception as e:
        print(f"Error deleting PDF from GCS: {str(e)}")
        return False


def generate_and_upload_quotation_pdf(html_content, quote_number):
    """
    Complete flow: Generate PDF from HTML and upload to GCS
    
    Args:
        html_content (str): HTML string
        quote_number (str): Quotation number
        
    Returns:
        dict: {
            'success': bool,
            'url': str (public URL),
            'blob_name': str,
            'size': int,
            'expires_at': str,
            'error': str (if failed)
        }
    """
    try:
        # Step 1: Generate PDF
        print(f"Generating PDF for quotation {quote_number}...")
        pdf_bytes = generate_pdf_from_html(html_content)
        print(f"PDF generated: {len(pdf_bytes):,} bytes")
        
        # Step 2: Upload to GCS
        print(f"Uploading PDF to Google Cloud Storage...")
        result = upload_pdf_to_gcs(pdf_bytes, quote_number)
        print(f"PDF uploaded successfully: {result['url']}")
        
        return {
            'success': True,
            **result
        }
        
    except Exception as e:
        error_msg = f"Error in generate_and_upload_quotation_pdf: {str(e)}"
        print(error_msg)
        return {
            'success': False,
            'error': error_msg
        }


def setup_gcs_lifecycle_policy():
    """
    Set up GCS bucket lifecycle policy to auto-delete old PDFs
    This should be run once during setup
    """
    try:
        client = get_gcs_client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        
        # Create lifecycle rule
        rule = {
            'action': {'type': 'Delete'},
            'condition': {
                'age': QUOTATION_EXPIRY_DAYS,  # Delete after N days
                'matchesPrefix': ['quotations/']  # Only quotation PDFs
            }
        }
        
        bucket.lifecycle_rules = [rule]
        bucket.patch()
        
        print(f"Lifecycle policy set: Delete quotations after {QUOTATION_EXPIRY_DAYS} days")
        return True
        
    except Exception as e:
        print(f"Error setting up lifecycle policy: {str(e)}")
        return False


# Cost calculator
def calculate_gcs_cost(num_quotations, avg_pdf_size_kb=140, storage_days=30):
    """
    Calculate estimated GCS cost
    
    Args:
        num_quotations (int): Number of quotations per month
        avg_pdf_size_kb (int): Average PDF size in KB
        storage_days (int): How long PDFs are kept
        
    Returns:
        dict: Cost breakdown
    """
    # GCS pricing (approximate)
    storage_cost_per_gb = 0.02  # Standard storage: $0.02 per GB/month
    network_cost_per_gb = 0.12  # Egress to internet: $0.12 per GB
    
    # Calculate storage
    total_size_gb = (num_quotations * avg_pdf_size_kb) / (1024 * 1024)
    prorated_storage_gb = total_size_gb * (storage_days / 30)
    storage_cost = prorated_storage_gb * storage_cost_per_gb
    
    # Calculate network (assume each PDF downloaded once)
    network_cost = total_size_gb * network_cost_per_gb
    
    # Total cost
    total_cost = storage_cost + network_cost
    
    return {
        'num_quotations': num_quotations,
        'total_size_gb': round(total_size_gb, 4),
        'storage_cost': round(storage_cost, 4),
        'network_cost': round(network_cost, 4),
        'total_cost': round(total_cost, 4),
        'cost_per_quotation': round(total_cost / num_quotations, 6) if num_quotations > 0 else 0
    }


if __name__ == '__main__':
    """
    Test and setup script
    """
    print("="*80)
    print("GCS PDF Handler - Setup & Cost Estimation")
    print("="*80)
    
    # Cost estimation
    print("\n📊 COST ESTIMATION:")
    print("-" * 80)
    
    for num in [1000, 10000, 100000]:
        cost = calculate_gcs_cost(num)
        print(f"\n{num:,} quotations/month:")
        print(f"  Storage: ${cost['storage_cost']:.4f}")
        print(f"  Network: ${cost['network_cost']:.4f}")
        print(f"  Total: ${cost['total_cost']:.4f}")
        print(f"  Per quote: ${cost['cost_per_quotation']:.6f}")
    
    print("\n" + "="*80)
    print("Comparison with Database Storage:")
    print("="*80)
    
    db_cost = calculate_gcs_cost(10000, storage_days=365*10)  # Assume DB keeps forever
    gcs_cost = calculate_gcs_cost(10000, storage_days=30)  # GCS keeps 30 days
    
    print(f"\nDatabase (10,000 quotes, stored forever):")
    print(f"  Cost: ${db_cost['total_cost']:.2f}")
    
    print(f"\nGCS (10,000 quotes, 30-day lifecycle):")
    print(f"  Cost: ${gcs_cost['total_cost']:.2f}")
    
    print(f"\nSavings: ${(db_cost['total_cost'] - gcs_cost['total_cost']):.2f}")
    print("="*80)

