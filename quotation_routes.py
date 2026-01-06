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
        
        # Validate required fields
        required_fields = ['quote_number', 'client_company', 'origin', 'destination', 'transport_mode']
        missing_fields = [f for f in required_fields if not data.get(f)]
        
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f'Missing required fields: {", ".join(missing_fields)}'
            }), 400
        
        try:
            # Generate document
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
    logo_base64 = """data:image/png;base64,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"""
    
    # Build document HTML
    document = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Quotation - {quote_number}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            max-width: 800px;
            margin: 40px auto;
            padding: 40px;
            background: white;
            color: #333;
            line-height: 1.6;
        }}
        
        .header {{
            text-align: center;
            border-bottom: 3px solid #2c3e50;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        
        .logo {{
            width: 100px;
            height: auto;
            margin-bottom: 10px;
            display: block;
            margin-left: auto;
            margin-right: auto;
        }}
        
        .company-name {{
            font-size: 28px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 5px;
        }}
        
        .tagline {{
            font-size: 14px;
            color: #666;
            margin-bottom: 5px;
        }}
        
        .website {{
            font-size: 12px;
            color: #0066cc;
        }}
        
        .metadata {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-left: 4px solid #2c3e50;
        }}
        
        .metadata-item {{
            margin-bottom: 10px;
        }}
        
        .metadata-label {{
            font-weight: bold;
            color: #555;
            font-size: 12px;
            text-transform: uppercase;
        }}
        
        .metadata-value {{
            color: #333;
            font-size: 14px;
            margin-top: 2px;
        }}
        
        h2 {{
            color: #2c3e50;
            border-bottom: 2px solid #e0e0e0;
            padding-bottom: 8px;
            margin-top: 30px;
            margin-bottom: 15px;
            font-size: 18px;
        }}
        
        .overview {{
            background: #f8f9fa;
            padding: 15px 20px;
            border-left: 4px solid #0066cc;
            margin-bottom: 25px;
            font-size: 14px;
            line-height: 1.7;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0 25px 0;
            font-size: 14px;
        }}
        
        th {{
            background: #2c3e50;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        
        td {{
            padding: 10px 12px;
            border: 1px solid #ddd;
        }}
        
        tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        
        ul {{
            margin: 10px 0;
            padding-left: 25px;
        }}
        
        li {{
            margin-bottom: 8px;
            line-height: 1.5;
        }}
        
        .terms {{
            background: #fff9e6;
            padding: 15px 20px;
            border-left: 4px solid #ffc107;
            margin: 20px 0;
            font-size: 13px;
        }}
        
        .terms ul {{
            margin: 10px 0;
        }}
        
        .closing {{
            margin-top: 30px;
            padding: 20px;
            background: #f8f9fa;
            border-left: 4px solid #28a745;
            font-size: 14px;
        }}
        
        .signature {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 2px solid #e0e0e0;
        }}
        
        .signature-line {{
            margin-bottom: 8px;
            font-size: 14px;
        }}
        
        .signature-title {{
            font-weight: bold;
            color: #2c3e50;
        }}
        
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #2c3e50;
            text-align: center;
            font-size: 12px;
            color: #555;
        }}
        
        .contact-info {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
            margin: 20px 0;
            text-align: left;
        }}
        
        .contact-item {{
            margin-bottom: 8px;
        }}
        
        .contact-label {{
            font-weight: 600;
            color: #2c3e50;
            font-size: 11px;
        }}
        
        .contact-value {{
            color: #555;
            font-size: 12px;
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
            <img src="data:image/png;base64,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" alt="Marineco Logo" style="height: 90px; width: auto; display: block; margin: 0 auto;">
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
        <p><strong>Quotation Validity:</strong> This quotation is valid until {validity_date} ({validity_days} days from date of issue).</p>
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
        <div style="margin-top: 40px; margin-bottom: 5px;">_______________________</div>
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

