"""
n8n Webhook Endpoints for Zoho Integration
Simple webhook endpoints that n8n can call for Zoho operations
"""

from flask import Blueprint, request, jsonify
import os
import logging
from zoho_crm_service import ZohoCRMService
from database import db

logger = logging.getLogger(__name__)

# Create Blueprint for n8n webhooks
n8n_webhooks = Blueprint('n8n_webhooks', __name__)

@n8n_webhooks.route('/webhook/zoho/push-contact', methods=['POST'])
def webhook_push_contact():
    """
    Webhook for n8n to push a single contact to Zoho CRM.
    
    Expected JSON:
    {
        "company": "Company Name",
        "contact_name": "John Doe",
        "email": "john@example.com",
        "phone": "+91-1234567890",
        "check_duplicates": true
    }
    
    Returns:
    {
        "success": true/false,
        "message": "...",
        "lead_id": "..." (if successful)
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No JSON data provided'
            }), 400
        
        # Extract contact data
        company = data.get('company', '').strip()
        contact_name = data.get('contact_name', '').strip()
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        check_duplicates = data.get('check_duplicates', True)
        
        if not company:
            return jsonify({
                'success': False,
                'message': 'Company name is required'
            }), 400
        
        # Initialize Zoho service
        zoho_service = ZohoCRMService()
        
        # Prepare contact data
        contact_data = {
            'Company': company,
            'Last_Name': contact_name.split()[-1] if contact_name else '',
            'First_Name': ' '.join(contact_name.split()[:-1]) if contact_name and len(contact_name.split()) > 1 else contact_name,
            'Email': email,
            'Phone': phone
        }
        
        # Check for duplicates if requested
        if check_duplicates:
            is_duplicate, existing_id = zoho_service.check_duplicate_in_zoho(email=email, phone=phone)
            if is_duplicate:
                return jsonify({
                    'success': False,
                    'message': f'Contact already exists in Zoho (Lead ID: {existing_id})',
                    'lead_id': existing_id,
                    'duplicate': True
                }), 200
        
        # Push to Zoho
        success, lead_id, error_msg = zoho_service.push_single_contact_to_zoho(contact_data)
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Contact pushed to Zoho successfully',
                'lead_id': lead_id
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': error_msg or 'Failed to push contact to Zoho'
            }), 500
            
    except Exception as e:
        logger.error(f"Error in webhook_push_contact: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@n8n_webhooks.route('/webhook/zoho/push-bulk', methods=['POST'])
def webhook_push_bulk():
    """
    Webhook for n8n to push multiple contacts to Zoho CRM.
    
    Expected JSON:
    {
        "contacts": [
            {
                "company": "Company 1",
                "contact_name": "John Doe",
                "email": "john@example.com",
                "phone": "+91-1234567890"
            },
            {
                "company": "Company 2",
                ...
            }
        ],
        "check_duplicates": true
    }
    
    Returns:
    {
        "success": true/false,
        "pushed": 10,
        "skipped": 2,
        "failed": 1,
        "results": [...]
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'message': 'No JSON data provided'
            }), 400
        
        contacts = data.get('contacts', [])
        check_duplicates = data.get('check_duplicates', True)
        
        if not contacts or not isinstance(contacts, list):
            return jsonify({
                'success': False,
                'message': 'contacts array is required'
            }), 400
        
        # Initialize Zoho service
        zoho_service = ZohoCRMService()
        
        # Prepare contacts for Zoho
        zoho_contacts = []
        for contact in contacts:
            company = contact.get('company', '').strip()
            contact_name = contact.get('contact_name', '').strip()
            email = contact.get('email', '').strip()
            phone = contact.get('phone', '').strip()
            
            if not company:
                continue
            
            zoho_contact = {
                'Company': company,
                'Last_Name': contact_name.split()[-1] if contact_name else '',
                'First_Name': ' '.join(contact_name.split()[:-1]) if contact_name and len(contact_name.split()) > 1 else contact_name,
                'Email': email,
                'Phone': phone
            }
            zoho_contacts.append(zoho_contact)
        
        if not zoho_contacts:
            return jsonify({
                'success': False,
                'message': 'No valid contacts to push'
            }), 400
        
        # Push to Zoho
        result = zoho_service.push_bulk_to_zoho(zoho_contacts, check_duplicates=check_duplicates)
        
        return jsonify({
            'success': result.get('success', False),
            'pushed': result.get('pushed', 0),
            'skipped': result.get('skipped', 0),
            'failed': result.get('failed', 0),
            'results': result.get('results', [])
        }), 200
            
    except Exception as e:
        logger.error(f"Error in webhook_push_bulk: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@n8n_webhooks.route('/webhook/zoho/check-duplicate', methods=['POST'])
def webhook_check_duplicate():
    """
    Webhook for n8n to check if a contact exists in Zoho CRM.
    
    Expected JSON:
    {
        "email": "john@example.com",
        "phone": "+91-1234567890"
    }
    
    Returns:
    {
        "exists": true/false,
        "lead_id": "..." (if exists)
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'exists': False,
                'message': 'No JSON data provided'
            }), 400
        
        email = data.get('email', '').strip()
        phone = data.get('phone', '').strip()
        
        if not email and not phone:
            return jsonify({
                'exists': False,
                'message': 'Email or phone is required'
            }), 400
        
        # Initialize Zoho service
        zoho_service = ZohoCRMService()
        
        # Check for duplicate
        is_duplicate, lead_id = zoho_service.check_duplicate_in_zoho(email=email, phone=phone)
        
        return jsonify({
            'exists': is_duplicate,
            'lead_id': lead_id if is_duplicate else None
        }), 200
            
    except Exception as e:
        logger.error(f"Error in webhook_check_duplicate: {str(e)}", exc_info=True)
        return jsonify({
            'exists': False,
            'message': f'Internal error: {str(e)}'
        }), 500


@n8n_webhooks.route('/webhook/zoho/token-status', methods=['GET'])
def webhook_token_status():
    """
    Webhook for n8n to check Zoho token status.
    
    Returns:
    {
        "token_valid": true/false,
        "data_center": "com",
        "expires_in_seconds": 3200
    }
    """
    try:
        import time
        zoho_service = ZohoCRMService()
        
        # Try to get access token
        access_token, error = zoho_service.get_access_token()
        
        token_valid = bool(access_token and not error)
        expires_in = 0
        if zoho_service.token_expiry:
            expires_in = int(zoho_service.token_expiry - time.time())
        
        return jsonify({
            'token_valid': token_valid,
            'data_center': zoho_service.data_center,
            'expires_in_seconds': expires_in,
            'error': error if error else None
        }), 200
            
    except Exception as e:
        logger.error(f"Error in webhook_token_status: {str(e)}", exc_info=True)
        return jsonify({
            'token_valid': False,
            'error': str(e)
        }), 500


@n8n_webhooks.route('/webhook/zoho/get-contacts', methods=['POST'])
def webhook_get_contacts():
    """
    Webhook for n8n to get contacts from database.
    
    Expected JSON (optional):
    {
        "company": "Company Name",
        "limit": 100
    }
    
    Returns:
    {
        "success": true,
        "contacts": [...],
        "count": 10
    }
    """
    try:
        data = request.get_json() or {}
        
        company = data.get('company', '').strip()
        limit = data.get('limit', 100)
        
        if company:
            # Get contacts for specific company
            company_id = db.check_company_exists(company)
            if company_id:
                contacts = db.get_company_contacts(company_id)
            else:
                contacts = []
        else:
            # Get all contacts (limited)
            contacts = db.get_all_contacts_for_campaign_sync()[:limit]
        
        # Format contacts for n8n
        formatted_contacts = []
        for contact in contacts:
            formatted_contacts.append({
                'id': contact.get('id'),
                'company': contact.get('company_name', ''),
                'contact_name': contact.get('contact_name', ''),
                'email': contact.get('email', ''),
                'phone': contact.get('phone', ''),
                'whatsapp': contact.get('whatsapp', ''),
                'source_url': contact.get('source_url', ''),
                'method': contact.get('method', '')
            })
        
        return jsonify({
            'success': True,
            'contacts': formatted_contacts,
            'count': len(formatted_contacts)
        }), 200
            
    except Exception as e:
        logger.error(f"Error in webhook_get_contacts: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'Internal error: {str(e)}'
        }), 500

