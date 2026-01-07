"""
Individual Quotation Generator - Simplified format matching company style
"""

def format_indian_date(date_str):
    """Convert date to Indian format: DD-MON-YYYY (e.g., 06-JAN-2026)"""
    from datetime import datetime
    try:
        # Parse the date string (assumes YYYY-MM-DD format from form)
        if date_str and date_str.strip():
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            return date_obj.strftime('%d-%b-%Y').upper()
    except:
        pass
    return date_str

def generate_individual_quotation(data):
    """
    Generate simplified individual quotation document.
    Format matches company quotation style but with simpler field layout.
    Payment terms: 50% + 50%
    """
    from logo_data import LOGO_BASE64
    from datetime import datetime
    
    # Extract data
    quote_number = data.get('quote_number', 'IND-' + datetime.now().strftime('%Y%m%d-%H%M'))
    quote_date = data.get('quote_date', datetime.now().strftime('%Y-%m-%d'))
    client_name = data.get('ind_client_name', '')
    pol = data.get('ind_pol', '')
    pod = data.get('ind_pod', '')
    commodity = data.get('ind_commodity', '')
    volume = data.get('ind_volume', '')
    transit_time = data.get('ind_transit_time', '')
    notes = data.get('ind_notes', '')
    remarks = data.get('ind_remarks', '')
    validity = data.get('ind_validity', '')
    gst_type = data.get('ind_gst_type', 'inclusive')
    gst_value = data.get('ind_gst_value', '')
    
    # Format validity to Indian date format if it looks like a date
    if validity and '-' in validity and len(validity) == 10:
        validity_formatted = format_indian_date(validity)
    else:
        validity_formatted = validity
    
    # Extract pricing items (support multiple)
    pricing_items = []
    item_counter = 1
    while True:
        charge_desc = data.get(f'ind_charge_desc_{item_counter}')
        rate = data.get(f'ind_rate_{item_counter}')
        hide_item = data.get(f'ind_hide_item_{item_counter}')
        
        if not charge_desc and not rate:
            break
            
        if charge_desc and rate and not hide_item:  # Only include if not hidden
            pricing_items.append({
                'description': charge_desc,
                'rate': rate
            })
        
        item_counter += 1
    
    # If no items found, try single item format (backward compatibility)
    if not pricing_items:
        single_desc = data.get('ind_charge_desc')
        single_rate = data.get('ind_rate')
        if single_desc and single_rate:
            pricing_items.append({
                'description': single_desc,
                'rate': single_rate
            })
    
    logo_base64 = LOGO_BASE64
    
    document = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Freight Quotation - {client_name}</title>
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
        
        /* Header matching company format */
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
            display: block;
        }}
        
        .company-name {{
            font-size: 16pt;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 2pt;
        }}
        
        .tagline {{
            font-size: 9pt;
            color: #666;
            margin-bottom: 1pt;
        }}
        
        .website {{
            font-size: 8pt;
            color: #0066cc;
        }}
        
        /* Title */
        h1 {{
            text-align: center;
            color: #2c3e50;
            font-size: 20pt;
            margin: 20px 0 30px 0;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        /* Shipment info grid */
        .shipment-info {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px 30px;
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border-left: 4px solid #3498db;
        }}
        
        .info-row {{
            display: flex;
            margin-bottom: 10px;
        }}
        
        .info-label {{
            font-weight: 600;
            min-width: 130px;
            color: #2c3e50;
        }}
        
        .info-value {{
            color: #555;
        }}
        
        /* Pricing table matching company style */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        
        th {{
            background: #E3F2FD;
            color: #1565C0;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 10pt;
            letter-spacing: 0.5px;
            border: 1px solid #90CAF9;
        }}
        
        th:last-child {{
            text-align: center;
        }}
        
        td {{
            padding: 12px;
            border: 1px solid #BBDEFB;
            background: #FAFAFA;
        }}
        
        tr:hover {{
            background: #F5F5F5;
        }}
        
        .grand-total {{
            background: #FFF9C4;
            color: #F57F17;
            font-weight: bold;
            font-size: 14pt;
            text-align: center;
            padding: 15px;
            border: 2px solid #FBC02D;
        }}
        
        /* Notes section */
        .notes-section {{
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            font-size: 10pt;
        }}
        
        .notes-section strong {{
            color: #856404;
        }}
        
        /* GST badge */
        .gst-badge {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
            color: white;
            text-align: center;
            padding: 12px;
            font-weight: bold;
            margin: 20px 0;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        /* Terms section */
        .terms-section {{
            margin: 20px 0;
            padding: 15px;
            background: #f8f9fa;
            border: 1px solid #dee2e6;
        }}
        
        .terms-section h2 {{
            color: #2c3e50;
            font-size: 14pt;
            margin-top: 0;
            margin-bottom: 15px;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
        }}
        
        .terms-section ul {{
            margin: 10px 0;
            padding-left: 25px;
        }}
        
        .terms-section li {{
            margin-bottom: 8px;
            line-height: 1.6;
        }}
        
        /* Signature */
        .signature {{
            margin-top: 50px;
            text-align: right;
        }}
        
        .signature-line {{
            margin: 10px 0;
        }}
        
        .signature-title {{
            font-weight: 600;
            color: #2c3e50;
        }}
        
        /* Footer */
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 2px solid #dee2e6;
            font-size: 9pt;
        }}
        
        .contact-info {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
        }}
        
        .contact-item {{
            margin-bottom: 15px;
        }}
        
        .contact-label {{
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 5px;
        }}
        
        .contact-value {{
            color: #555;
        }}
        
        @media print {{
            body {{
                print-color-adjust: exact;
                -webkit-print-color-adjust: exact;
            }}
            
            .header-left {{
                display: block !important;
            }}
            
            .header-right {{
                display: block !important;
            }}
            
            .logo-svg {{
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                display: block !important;
                width: 140px !important;
                height: auto !important;
            }}
        }}
    </style>
</head>
<body>
    <!-- Header matching company format -->
    <div class="header">
        <div class="header-left">
            <img src="{logo_base64}" alt="Marineco Logo" class="logo-svg">
        </div>
        <div class="header-right">
            <div class="company-name">Marineco Private Limited</div>
            <div class="tagline">Global Logistics & Freight Forwarding</div>
            <div class="website">www.marineco.co</div>
        </div>
    </div>
    
    <h1>FREIGHT QUOTATION</h1>
    
    <!-- Shipment Information Grid -->
    <div class="shipment-info">
        <div>
            <div class="info-row">
                <span class="info-label">POL :</span>
                <span class="info-value">{pol}</span>
            </div>
            <div class="info-row">
                <span class="info-label">Commodity :</span>
                <span class="info-value">{commodity}</span>
            </div>
            <div class="info-row">
                <span class="info-label">VOLUME :</span>
                <span class="info-value">{volume}</span>
            </div>
        </div>
        <div>
            <div class="info-row">
                <span class="info-label">Transit Time :</span>
                <span class="info-value">{transit_time}</span>
            </div>
            <div class="info-row">
                <span class="info-label">POD :</span>
                <span class="info-value">{pod}</span>
            </div>
        </div>
    </div>
    
    <!-- Pricing Table -->
    <table>
        <tr>
            <th>CHARGES</th>
            <th>Per {volume}</th>
        </tr>
        {''.join([f'<tr><td>{item["description"]}</td><td style="text-align: center; font-weight: 600; font-size: 12pt;">{item["rate"]}</td></tr>' for item in pricing_items])}
        <tr>
            <td colspan="2" class="grand-total">Grand Total<br><span style="font-size: 18pt; letter-spacing: 2px;">{pricing_items[0]['rate'] if pricing_items else 'N/A'}</span></td>
        </tr>
    </table>
    
    <!-- Notes -->
    {f'<div class="notes-section"><strong>Note : </strong>{notes}</div>' if notes else ''}
    
    <!-- Remarks -->
    {f'<div class="notes-section" style="border-left-color: #3498db; background: #e3f2fd;"><strong>Remarks : </strong>{remarks}</div>' if remarks else ''}
    
    <!-- GST Badge -->
    <div class="gst-badge">
        {f'✓ GST {gst_value}%' if gst_type == 'custom' and gst_value else '✓ Inclusive GST'}
    </div>
    
    <!-- Terms & Conditions -->
    <div class="terms-section">
        <h2>Terms & Conditions</h2>
        <ul>
            <li><strong>NOTE:</strong></li>
            <li>ABOVE RATES ARE VALID till {f"'{validity_formatted}'" if validity_formatted else 'AS PER AGREEMENT'}</li>
            <li>ABOVE RATES ARE NON RECEIPTED CHARGES</li>
        </ul>
        
        <h2 style="margin-top: 20px;">Payment Terms</h2>
        <ul>
            <li><strong>Payment Terms : 50% After sailing 50% before a week of vessel reaching to Port</strong></li>
            <li>Bill of Lading will be released once full payment is received</li>
        </ul>
    </div>
    
    <!-- Signature -->
    <div class="signature">
        <div style="margin-bottom: 50px;">
            <strong>For Marineco Private Limited</strong>
        </div>
        <div style="border-top: 1px solid #000; width: 200px; display: inline-block; padding-top: 5px;">
            Authorized Signatory
        </div>
        <div style="font-size: 9pt; color: #666; margin-top: 5px;">
            Logistics Operations
        </div>
    </div>
    
    <!-- Footer -->
    <div class="footer">
        <div style="font-weight: 600; font-size: 12px; color: #2c3e50; margin-bottom: 15px;">
            CONTACT INFORMATION
        </div>
        
        <div class="contact-info">
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
            
            <div class="contact-item">
                <div class="contact-label">📍 OFFICE ADDRESS</div>
                <div class="contact-value">
                    Flat 301, 3rd Floor, Street No 5<br>
                    Prakash Nagar, Begumpet<br>
                    Hyderabad, INDIA
                </div>
            </div>
        </div>
        
        <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #ddd; text-align: center; color: #999;">
            This is a system-generated quotation document from Marineco Private Limited.
        </div>
    </div>
</body>
</html>
"""
    
    return document

