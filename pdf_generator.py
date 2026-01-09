"""
PDF Generator for Quotations
Converts HTML quotations to PDF format
"""

import os
import logging
from weasyprint import HTML, CSS
from datetime import datetime
import tempfile

logger = logging.getLogger(__name__)

# Create PDFs directory
PDF_STORAGE_DIR = os.path.join(os.path.dirname(__file__), 'data', 'pdfs')
os.makedirs(PDF_STORAGE_DIR, exist_ok=True)

def generate_pdf_from_html(html_content, quote_number, output_path=None):
    """
    Generate PDF from HTML content.
    
    Args:
        html_content: HTML string to convert
        quote_number: Quote number for filename
        output_path: Optional custom output path
    
    Returns:
        str: Path to generated PDF file
    """
    try:
        # Generate filename
        if not output_path:
            safe_quote_number = quote_number.replace('/', '-').replace('\\', '-')
            filename = f"quotation_{safe_quote_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            output_path = os.path.join(PDF_STORAGE_DIR, filename)
        
        # Convert HTML to PDF
        logger.info(f"Generating PDF: {output_path}")
        
        # Create PDF with WeasyPrint
        HTML(string=html_content).write_pdf(output_path)
        
        logger.info(f"✅ PDF generated successfully: {output_path}")
        return output_path
        
    except Exception as e:
        logger.error(f"❌ Error generating PDF: {e}")
        raise

def get_pdf_url(quote_number, request_base_url):
    """
    Get the URL to access a PDF.
    
    Args:
        quote_number: Quote number
        request_base_url: Base URL from request (e.g., http://localhost:5000)
    
    Returns:
        str: URL to download PDF
    """
    safe_quote_number = quote_number.replace('/', '-').replace('\\', '-')
    return f"{request_base_url}/quotations/pdf/{safe_quote_number}"

def cleanup_old_pdfs(days=7):
    """
    Clean up PDFs older than specified days.
    
    Args:
        days: Number of days to keep PDFs
    """
    try:
        import time
        now = time.time()
        cutoff = now - (days * 86400)  # days * seconds_per_day
        
        for filename in os.listdir(PDF_STORAGE_DIR):
            filepath = os.path.join(PDF_STORAGE_DIR, filename)
            if os.path.isfile(filepath):
                if os.path.getmtime(filepath) < cutoff:
                    os.remove(filepath)
                    logger.info(f"Cleaned up old PDF: {filename}")
        
    except Exception as e:
        logger.error(f"Error cleaning up PDFs: {e}")

def get_pdf_size(pdf_path):
    """
    Get size of PDF file in bytes.
    
    Args:
        pdf_path: Path to PDF file
    
    Returns:
        int: Size in bytes
    """
    try:
        return os.path.getsize(pdf_path)
    except:
        return 0

