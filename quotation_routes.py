"""
Logistics Quotation Generator - Flask Routes
Professional document generation for freight quotations
"""

import os
import logging
from datetime import datetime, timedelta
from flask import render_template, request, jsonify, session, redirect, url_for, send_file
from functools import wraps
from io import BytesIO
from logo_data import LOGO_BASE64
from individual_quotation import generate_individual_quotation

logger = logging.getLogger(__name__)


def register_quotation_routes(app):
    """
    Register all quotation generator routes to Flask app.
    
    Usage in app_with_auth.py:
        from quotation_routes import register_quotation_routes
        register_quotation_routes(app)
    """
    
    # Define login_required decorator inside function to avoid conflicts
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'logged_in' not in session:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    
    @app.route('/quotations')
    @login_required
    def quotations_index():
        """
        Main quotation generator page with form.
        """
        # Generate next quote number
        quote_number = generate_quote_number()
        
        return render_template(
            'quotation_generator.html',
            quote_number=quote_number,
            quote_date=datetime.now().strftime('%Y-%m-%d'),
            username=session.get('username', 'Agent')
        )
    
    @app.route('/quotations/generate', methods=['POST'])
    @login_required
    def quotations_generate():
        """
        Generate quotation document from form data.
        Returns HTML preview or downloadable document.
        """
        data = request.json if request.is_json else request.form.to_dict()
        
        # Check quotation type
        quotation_type = data.get('quotation_type', 'company')
        
        # Validate required fields based on type
        if quotation_type == 'individual':
            required_fields = ['quote_number', 'ind_client_name', 'ind_pol', 'ind_pod', 'ind_commodity', 'ind_volume']
            missing_fields = [f for f in required_fields if not data.get(f)]
            
            # Check for at least one pricing item
            has_pricing = data.get('ind_rate_1') or data.get('ind_rate') 
            if not has_pricing:
                missing_fields.append('ind_rate (at least one pricing item required)')
        else:
            required_fields = ['quote_number', 'client_company', 'origin', 'destination', 'transport_mode']
            missing_fields = [f for f in required_fields if not data.get(f)]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        try:
            # Generate document based on type
            if quotation_type == 'individual':
                document_html = generate_individual_quotation(data)
            else:
                document_html = generate_quotation_document(data)
            
            return jsonify({
                'success': True,
                'document': document_html,
                'quote_number': data.get('quote_number')
            })
        
        except Exception as e:
            logger.error(f"Error generating quotation: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/quotations/export/<format>', methods=['POST'])
    @login_required
    def quotations_export(format):
        """
        Export quotation to PDF or DOCX format.
        """
        data = request.json
        document_html = data.get('document_html')
        quote_number = data.get('quote_number', 'QUOTE')
        
        if not document_html:
            return jsonify({'success': False, 'error': 'No document to export'}), 400
        
        try:
            if format == 'pdf':
                file_content, mimetype, filename = export_to_pdf(document_html, quote_number)
            elif format == 'docx':
                file_content, mimetype, filename = export_to_docx(document_html, quote_number)
            else:
                return jsonify({'success': False, 'error': 'Invalid format'}), 400
            
            return send_file(
                BytesIO(file_content),
                mimetype=mimetype,
                as_attachment=True,
                download_name=filename
            )
        
        except Exception as e:
            logger.error(f"Error exporting quotation: {str(e)}", exc_info=True)
            return jsonify({'success': False, 'error': str(e)}), 500
    
    logger.info("✅ Quotation generator routes registered")


# ============================================
# HELPER FUNCTIONS
# ============================================

def generate_quote_number():
    """Generate unique quote number: MAR-YYYY-MMDD-XXXX"""
    now = datetime.now()
    date_part = now.strftime('%Y-%m%d')
    # In production, increment from database
    sequence = str(now.hour * 100 + now.minute).zfill(4)
    return f"MAR-{date_part}-{sequence}"


def generate_quotation_document(data):
    """
    Generate complete professional quotation document.
    
    Args:
        data: Dictionary with form fields
    
    Returns:
        HTML string ready for display or export
    """
    
    # Extract data with defaults
    quote_number = data.get('quote_number', 'N/A')
    quote_date = data.get('quote_date', datetime.now().strftime('%Y-%m-%d'))
    client_company = data.get('client_company', 'N/A')
    client_contact = data.get('client_contact', '')
    origin = data.get('origin', 'N/A')
    destination = data.get('destination', 'N/A')
    transport_mode = data.get('transport_mode', 'N/A')
    shipment_type = data.get('shipment_type', 'N/A')
    cargo_description = data.get('cargo_description', 'General Cargo')
    gross_weight = data.get('gross_weight', 'N/A')
    volume = data.get('volume', 'N/A')
    service_level = data.get('service_level', 'Port-to-Port')
    validity_days = data.get('validity_days', '15')
    
    # Pricing fields (optional)
    freight_charges = data.get('freight_charges', 'As per applicable carrier rates')
    customs_charges = data.get('customs_charges', 'As per regulatory requirements')
    local_transport_charges = data.get('local_transport_charges', 'As per distance and service level')
    total_amount = data.get('total_amount', '')
    
    # Additional custom pricing items (JSON format)
    import json
    additional_items = []
    try:
        additional_items_json = data.get('additional_pricing_items', '[]')
        if additional_items_json:
            additional_items = json.loads(additional_items_json) if isinstance(additional_items_json, str) else additional_items_json
    except:
        additional_items = []
    
    # Signatory name
    signatory_name = data.get('signatory_name', '')
    
    # Calculate validity date
    try:
        validity_date = (datetime.strptime(quote_date, '%Y-%m-%d') + 
                        timedelta(days=int(validity_days))).strftime('%Y-%m-%d')
    except:
        validity_date = 'As specified'
    
    # Generate scope of services based on transport mode
    scope_services = generate_scope_of_services(transport_mode, service_level)
    
    # Generate shipment overview paragraph
    overview = generate_shipment_overview(origin, destination, transport_mode, 
                                          cargo_description, shipment_type)
    
    # Marineco logo (base64 encoded for embedding)
    logo_base64 = LOGO_BASE64
    
    # Build document HTML
    document = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Quotation - {quote_number}</title>
    <style>
        @page {{
            size: A4;
            margin: 15mm;
        }}
        
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            width: 210mm;
            max-width: 210mm;
            margin: 0 auto;
            padding: 15mm;
            background: white;
            color: #333;
            line-height: 1.5;
            font-size: 11pt;
        }}
        
        .header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 3px solid #2c3e50;
            padding-bottom: 15px;
            margin-bottom: 20px;
        }}
        
        .header-left {{
            flex: 0 0 auto;
        }}
        
        .header-right {{
            flex: 1;
            text-align: right;
        }}
        
        .logo-svg {{
            width: 140px;
            height: auto;
        }}
        
        .company-name {{
            font-size: 20pt;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 3px;
            line-height: 1.2;
        }}
        
        .tagline {{
            font-size: 10pt;
            color: #666;
            margin-bottom: 3px;
        }}
        
        .website {{
            font-size: 9pt;
            color: #0066cc;
        }}
        
        .metadata {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin-bottom: 18px;
            padding: 12px;
            background: #f8f9fa;
            border-left: 3px solid #2c3e50;
        }}
        
        .metadata-item {{
            margin-bottom: 8px;
        }}
        
        .metadata-label {{
            font-weight: bold;
            color: #555;
            font-size: 9pt;
            text-transform: uppercase;
        }}
        
        .metadata-value {{
            color: #333;
            font-size: 10pt;
            margin-top: 2px;
        }}
        
        h2 {{
            color: #2c3e50;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 6px;
            margin-top: 18px;
            margin-bottom: 10px;
            font-size: 13pt;
        }}
        
        .overview {{
            background: #f8f9fa;
            padding: 10px 12px;
            border-left: 3px solid #0066cc;
            margin-bottom: 15px;
            font-size: 10pt;
            line-height: 1.5;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0 15px 0;
            font-size: 10pt;
        }}
        
        th {{
            background: #2c3e50;
            color: white;
            padding: 8px 10px;
            text-align: left;
            font-weight: 600;
        }}
        
        td {{
            padding: 7px 10px;
            border: 1px solid #ddd;
        }}
        
        tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        
        ul {{
            margin: 8px 0;
            padding-left: 20px;
        }}
        
        li {{
            margin-bottom: 5px;
            line-height: 1.4;
            font-size: 10pt;
        }}
        
        .terms {{
            background: #fff9e6;
            padding: 10px 12px;
            border-left: 3px solid #ffc107;
            margin: 15px 0;
            font-size: 9pt;
        }}
        
        .terms ul {{
            margin: 5px 0;
        }}
        
        .closing {{
            margin-top: 18px;
            padding: 12px;
            background: #f8f9fa;
            border-left: 3px solid #28a745;
            font-size: 10pt;
        }}
        
        .signature {{
            margin-top: 25px;
            padding-top: 15px;
            border-top: 2px solid #e0e0e0;
        }}
        
        .signature-line {{
            margin-bottom: 3px;
            font-size: 10pt;
        }}
        
        .signature-title {{
            font-weight: 600;
            color: #2c3e50;
            font-size: 11pt;
        }}
        
        .signature-text {{
            font-family: 'Brush Script MT', 'Lucida Handwriting', cursive;
            font-size: 24pt;
            color: #4a5568;
            margin: 15px 0;
            font-weight: 300;
            opacity: 0.85;
            font-style: italic;
        }}
        
        .footer {{
            margin-top: 25px;
            padding: 12px;
            background: #f8f9fa;
            border-top: 2px solid #2c3e50;
            font-size: 9pt;
        }}
        
        .contact-info {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin: 10px 0;
            text-align: left;
        }}
        
        .contact-item {{
            margin-bottom: 8px;
        }}
        
        .contact-label {{
            font-weight: 600;
            color: #2c3e50;
            font-size: 9pt;
        }}
        
        .contact-value {{
            color: #555;
            font-size: 9pt;
        }}
        
        @media print {{
            body {{
                margin: 0;
                padding: 20px;
            }}
            
            .logo {{
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}
            
            .header {{
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                display: flex !important;
                align-items: center !important;
                justify-content: space-between !important;
            }}
            
            .header-left {{
                display: block !important;
            }}
            
            .header-right {{
                display: block !important;
            }}
            
            .logo-svg, .header-left svg {{
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                display: block !important;
                width: 140px !important;
                height: auto !important;
            }}
            
            .footer {{
                page-break-inside: avoid;
            }}
            
            .signature {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div style="text-align: center; margin-bottom: 10px;">
            <img src="data:image/png;base64,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" 
                 alt="Marineco Logo" 
                 style="width: 90px; height: auto; display: block; margin: 0 auto;">
        </div>
        <div class="company-name">Marineco Private Limited</div>
        <div class="tagline">Global Logistics & Freight Forwarding</div>
        <div class="website">www.marineco.co</div>
    </div>
    
    <div style="text-align: center; margin-bottom: 30px;">
        <h1 style="color: #2c3e50; margin: 0; font-size: 24px;">FREIGHT QUOTATION</h1>
    </div>
    
    <div class="metadata">
        <div>
            <div class="metadata-item">
                <div class="metadata-label">Quotation Number</div>
                <div class="metadata-value">{quote_number}</div>
            </div>
            <div class="metadata-item">
                <div class="metadata-label">Date of Issue</div>
                <div class="metadata-value">{quote_date}</div>
            </div>
        </div>
        <div>
            <div class="metadata-item">
                <div class="metadata-label">Client Company</div>
                <div class="metadata-value">{client_company}</div>
            </div>
            {f'<div class="metadata-item"><div class="metadata-label">Contact Person</div><div class="metadata-value">{client_contact}</div></div>' if client_contact else ''}
        </div>
    </div>
    
    <h2>Shipment Overview</h2>
    <div class="overview">
        {overview}
    </div>
    
    <h2>Shipment Details</h2>
    <table>
        <tr>
            <th>Parameter</th>
            <th>Details</th>
        </tr>
        <tr>
            <td><strong>Origin</strong></td>
            <td>{origin}</td>
        </tr>
        <tr>
            <td><strong>Destination</strong></td>
            <td>{destination}</td>
        </tr>
        <tr>
            <td><strong>Mode of Transport</strong></td>
            <td>{transport_mode}</td>
        </tr>
        <tr>
            <td><strong>Shipment Type</strong></td>
            <td>{shipment_type}</td>
        </tr>
        <tr>
            <td><strong>Cargo Description</strong></td>
            <td>{cargo_description}</td>
        </tr>
        <tr>
            <td><strong>Gross Weight</strong></td>
            <td>{gross_weight}</td>
        </tr>
        <tr>
            <td><strong>Volume/CBM</strong></td>
            <td>{volume}</td>
        </tr>
        <tr>
            <td><strong>Service Level</strong></td>
            <td>{service_level}</td>
        </tr>
    </table>
    
    <h2>Scope of Services</h2>
    <ul>
        {scope_services}
    </ul>
    
    <h2>Commercial Summary</h2>
    <table>
        <tr>
            <th>Service</th>
            <th>Amount</th>
        </tr>
        <tr>
            <td><strong>Freight Charges</strong></td>
            <td>{freight_charges}</td>
        </tr>
        <tr>
            <td><strong>Customs Clearance</strong></td>
            <td>{customs_charges}</td>
        </tr>
        <tr>
            <td><strong>Local Transportation</strong></td>
            <td>{local_transport_charges}</td>
        </tr>
        {''.join([f'<tr><td><strong>{item.get("name", "Additional Service")}</strong></td><td>{item.get("price", "On request")}</td></tr>' for item in additional_items])}
        <tr>
            <td><strong>Documentation Charges</strong></td>
            <td>Standard documentation fees applicable</td>
        </tr>
        {f'<tr style="background: #f0f8ff; font-weight: bold;"><td><strong>TOTAL</strong></td><td>{total_amount}</td></tr>' if total_amount else ''}
    </table>
    
    <h2>Validity & Transit Information</h2>
    <div style="margin: 15px 0; font-size: 14px;">
        <p><strong>Quotation Validity:</strong> This quotation is valid until {validity_date}.</p>
        <p><strong>Transit Time:</strong> Transit time is subject to carrier schedules, routing, and operational conditions. Estimated transit time will be provided upon booking confirmation.</p>
        <p><strong>Rate Disclaimer:</strong> Rates are subject to change based on fuel surcharges, carrier tariff revisions, currency fluctuations, and regulatory changes. Final rates will be confirmed at the time of booking.</p>
    </div>
    
    <h2>Terms & Conditions</h2>
    <div class="terms">
        <ul>
            <li>This quotation is subject to space and carrier availability at the time of booking.</li>
            <li>All shipments are subject to applicable customs regulations and import/export compliance requirements.</li>
            <li>Rates exclude insurance unless explicitly mentioned. Cargo insurance can be arranged on request.</li>
            <li>Additional charges including but not limited to demurrage, detention, storage, and special handling will be charged as applicable.</li>
            <li>Payment terms are as per company policy and must be agreed upon prior to shipment execution.</li>
            <li>This quotation does not constitute a binding contract until a formal booking confirmation is issued.</li>
            <li>Marineco Pvt Ltd reserves the right to modify or withdraw this quotation without prior notice.</li>
        </ul>
    </div>
    
    <div class="closing">
        We thank you for the opportunity to quote on your logistics requirements. Our team is committed to providing reliable, efficient, and professional freight forwarding services. Should you require any clarifications, modifications, or wish to proceed with this quotation, please do not hesitate to contact us.
    </div>
    
    <div class="signature">
        <div class="signature-line"><span class="signature-title">For Marineco Private Limited</span></div>
        {f'<div class="signature-text">{signatory_name}</div>' if signatory_name else '<div style="margin-top: 40px; margin-bottom: 5px;">_______________________</div>'}
        <div class="signature-line">Authorized Signatory</div>
        <div class="signature-line" style="color: #666;">Logistics Operations</div>
    </div>
    
    <div class="footer">
        <div style="font-weight: 600; font-size: 14px; color: #2c3e50; margin-bottom: 15px;">
            CONTACT INFORMATION
        </div>
        
        <div class="contact-info">
            <div>
                <div class="contact-item">
                    <div class="contact-label">📞 PHONE</div>
                    <div class="contact-value">+91 8977647790</div>
                    <div class="contact-value">+91 99489 89777</div>
                </div>
                
                <div class="contact-item">
                    <div class="contact-label">✉️ EMAIL</div>
                    <div class="contact-value">sarita@marineco.co</div>
                    <div class="contact-value">sales01@marineco.co</div>
                </div>
            </div>
            
            <div>
                <div class="contact-item">
                    <div class="contact-label">📍 OFFICE ADDRESS</div>
                    <div class="contact-value">
                        Flat 301, 3rd Floor, Street No 5<br>
                        Prakash Nagar, Begumpet<br>
                        Hyderabad, INDIA
                    </div>
                </div>
            </div>
        </div>
        
        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #ddd; font-size: 11px; color: #999;">
            This is a system-generated quotation document from Marineco Private Limited.
        </div>
    </div>
</body>
</html>
"""
    
    return document


def generate_scope_of_services(transport_mode, service_level):
    """Generate scope of services based on transport mode and service level."""
    
    services = []
    
    # Core freight service
    if transport_mode.lower() == 'air':
        services.append('<li>Air freight transportation from origin airport to destination airport</li>')
    elif transport_mode.lower() == 'sea':
        services.append('<li>Ocean freight transportation via containerized shipping</li>')
    elif transport_mode.lower() == 'road':
        services.append('<li>Road freight transportation via dedicated trucks</li>')
    else:
        services.append('<li>Freight transportation as per selected mode</li>')
    
    # Service level specific
    if 'door' in service_level.lower():
        services.append('<li>Door-to-door cargo pickup and delivery coordination</li>')
        services.append('<li>Local transportation at origin and destination</li>')
    else:
        services.append('<li>Port-to-port or terminal-to-terminal freight movement</li>')
    
    # Standard services
    services.extend([
        '<li>Cargo handling and warehousing coordination</li>',
        '<li>Freight documentation preparation and processing</li>',
        '<li>Shipment tracking and status updates</li>',
        '<li>Customs clearance and regulatory compliance support</li>',
        '<li>Coordination with carriers, agents, and authorities</li>',
        '<li>Proof of delivery and final documentation</li>'
    ])
    
    return '\n        '.join(services)


def generate_shipment_overview(origin, destination, transport_mode, cargo_description, shipment_type):
    """Generate professional shipment overview paragraph."""
    
    mode_text = {
        'Air': 'via air freight',
        'Sea': 'via ocean freight',
        'Road': 'via road transportation'
    }.get(transport_mode, 'using the specified transport mode')
    
    overview = f"""
    This quotation is prepared for the movement of {cargo_description} from {origin} to {destination} 
    {mode_text}. The shipment is classified as {shipment_type} service and will be handled in accordance 
    with industry best practices and regulatory requirements. Our comprehensive logistics solution includes 
    freight coordination, documentation, customs facilitation, and end-to-end shipment visibility. 
    All services are executed through our network of verified carriers and agents to ensure timely, 
    secure, and cost-effective delivery.
    """
    
    return overview.strip()


def export_to_pdf(html_content, quote_number):
    """
    Export HTML document to PDF format.
    Fallback: Returns HTML for browser printing
    """
    try:
        from weasyprint import HTML
        
        pdf_bytes = HTML(string=html_content).write_pdf()
        filename = f"Quotation_{quote_number}.pdf"
        mimetype = 'application/pdf'
        
        return pdf_bytes, mimetype, filename
    
    except ImportError:
        # Fallback: Return HTML that can be printed as PDF from browser
        logger.warning("WeasyPrint not installed - using browser print fallback")
        html_bytes = html_content.encode('utf-8')
        filename = f"Quotation_{quote_number}.html"
        mimetype = 'text/html'
        
        return html_bytes, mimetype, filename


def export_to_docx(html_content, quote_number):
    """
    Export HTML document to DOCX format.
    Requires: pip install python-docx htmldocx
    """
    try:
        from docx import Document
        from htmldocx import HtmlToDocx
        
        document = Document()
        new_parser = HtmlToDocx()
        new_parser.add_html_to_document(html_content, document)
        
        # Save to BytesIO
        docx_bytes = BytesIO()
        document.save(docx_bytes)
        docx_bytes.seek(0)
        
        filename = f"Quotation_{quote_number}.docx"
        mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        
        return docx_bytes.read(), mimetype, filename
    
    except ImportError:
        logger.warning("python-docx or htmldocx not installed - DOCX export unavailable")
        raise Exception("DOCX export requires: pip install python-docx htmldocx")

