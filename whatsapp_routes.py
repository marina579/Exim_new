"""
WhatsApp Inbox - Flask Routes
Add these routes to app_with_auth.py
"""

import os
import logging
import requests
from datetime import datetime
from flask import render_template, request, jsonify, session, redirect, url_for
from functools import wraps

logger = logging.getLogger(__name__)

# Use adapter to work with N8N's chat_history and Lead tables
try:
    from whatsapp_db_adapter import whatsapp_db
    logger.info("✅ Using WhatsApp DB Adapter (chat_history + Lead tables)")
except ImportError:
    from whatsapp_db import whatsapp_db
    logger.info("⚠️  Using standard WhatsApp DB")

# N8N webhook URL for sending messages (set in Railway env vars)
N8N_SEND_WEBHOOK = os.getenv('N8N_WEBHOOK_URL', '')
logger.info(f"🔧 N8N Webhook configured: {N8N_SEND_WEBHOOK if N8N_SEND_WEBHOOK else '❌ NOT SET'}")

# Try to import GCS handler for file attachments
try:
    from gcs_pdf_handler import get_gcs_client, GCS_BUCKET_NAME
    GCS_AVAILABLE = True
    logger.info("✅ GCS file attachment support enabled")
except (ImportError, OSError, Exception) as e:
    GCS_AVAILABLE = False
    logger.warning(f"⚠️  GCS not available - file attachments disabled: {str(e)}")


def upload_file_to_gcs(file, conversation_id):
    """
    Upload file to Google Cloud Storage.
    
    Args:
        file: FileStorage object from Flask request.files
        conversation_id: ID of the conversation
        
    Returns:
        str: Public URL of uploaded file
    """
    if not GCS_AVAILABLE:
        raise Exception("GCS not configured - file uploads disabled")
    
    try:
        # Generate unique filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Sanitize original filename
        safe_filename = "".join(c for c in file.filename if c.isalnum() or c in ".-_ ")
        blob_name = f"whatsapp_attachments/{conversation_id}/{timestamp}_{safe_filename}"
        
        # Get GCS client and upload
        client = get_gcs_client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_name)
        
        # Set content type
        blob.content_type = file.content_type or 'application/octet-stream'
        
        # Upload file
        file.seek(0)  # Reset file pointer
        blob.upload_from_file(file, content_type=blob.content_type)
        
        # Make blob publicly accessible
        blob.make_public()
        
        # Get public URL
        public_url = blob.public_url
        
        logger.info(f"✅ Uploaded file to GCS: {blob_name}")
        return public_url
    
    except Exception as e:
        logger.error(f"GCS upload error: {str(e)}", exc_info=True)
        raise


def login_required(f):
    """
    Decorator to require login for routes.
    NOTE: If app_with_auth.py already has this, use that one instead.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# ============================================
# WHATSAPP INBOX ROUTES
# ============================================

def register_whatsapp_routes(app):
    """
    Register all WhatsApp inbox routes to Flask app.
    
    Usage in app_with_auth.py:
        from whatsapp_routes import register_whatsapp_routes
        register_whatsapp_routes(app)
    """
    
    @app.route('/whatsapp/inbox')
    @login_required
    def whatsapp_inbox():
        """
        Main WhatsApp inbox view - unified layout (like real WhatsApp).
        """
        return render_template(
            'whatsapp_unified.html',
            username=session.get('username', 'Agent')
        )
    
    @app.route('/whatsapp/conversation/<conversation_id>')
    @login_required
    def whatsapp_conversation(conversation_id):
        """
        Individual chat view - WhatsApp-like interface.
        """
        # Get conversation details
        conversation = whatsapp_db.get_conversation_by_id(conversation_id)
        
        if not conversation:
            return "Conversation not found", 404
        
        # Get messages
        messages = whatsapp_db.get_conversation_messages(conversation_id)
        
        # Get lead data
        lead = whatsapp_db.get_lead_by_conversation(conversation_id)
        
        # Mark messages as read
        whatsapp_db.mark_messages_as_read(conversation_id)
        
        # Log agent action
        whatsapp_db.log_agent_action(
            conversation_id, 
            session.get('username', 'Unknown'), 
            'read'
        )
        
        return render_template(
            'whatsapp_chat.html',
            conversation=conversation,
            messages=messages,
            lead=lead or {},
            username=session.get('username', 'Agent')
        )
    
    # ============================================
    # API ENDPOINTS
    # ============================================
    
    @app.route('/whatsapp/api/send', methods=['POST'])
    @login_required
    def whatsapp_send_message():
        """
        Agent sends a WhatsApp message.
        Calls n8n webhook → Exotel → WhatsApp user.
        """
        data = request.json
        conversation_id = data.get('conversation_id')
        message = data.get('message', '').strip()
        
        if not conversation_id or not message:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        try:
            # Get conversation
            conversation = whatsapp_db.get_conversation_by_id(conversation_id)
            if not conversation:
                return jsonify({'success': False, 'error': 'Conversation not found'}), 404
            
            phone = conversation['phone']
            agent_name = session.get('username', 'Agent')
            
            # Send to n8n webhook
            webhook_payload = {
                'phone': phone,
                'message': message,
                'sender': 'agent',
                'agent_name': agent_name,
                'conversation_id': conversation_id
            }
            
            logger.info(f"Sending WhatsApp message via n8n: {phone}")
            
            # Check if n8n webhook is configured
            if N8N_SEND_WEBHOOK:
                try:
                    response = requests.post(
                        N8N_SEND_WEBHOOK,
                        json=webhook_payload,
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        logger.info(f"✅ Message sent via n8n webhook to {phone}")
                    else:
                        logger.error(f"n8n webhook error: {response.status_code} - {response.text}")
                        # Fall through to demo mode
                except Exception as e:
                    logger.error(f"n8n webhook request failed: {str(e)}")
                    # Fall through to demo mode
            else:
                logger.info(f"Demo mode: n8n webhook not configured")
            
            # Always save message to database
            logger.info(f"Saving agent message to database")
            
            # Insert message into database as outbound from agent
            whatsapp_db.insert_message(
                conversation_id=conversation_id,
                direction='outbound',
                sender='agent',
                message=message
            )
            
            # Log agent action
            whatsapp_db.log_agent_action(
                conversation_id,
                agent_name,
                'reply',
                {'message': message[:100]}
            )
            
            # Determine success message based on whether webhook was called
            if N8N_SEND_WEBHOOK:
                success_msg = 'Message sent successfully via WhatsApp'
            else:
                success_msg = 'Message saved (Demo mode - n8n webhook not configured)'
            
            return jsonify({
                'success': True,
                'message': success_msg
            })
        
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/whatsapp/api/conversation/<conversation_id>/update_stage', methods=['POST'])
    @login_required
    def whatsapp_update_stage(conversation_id):
        """
        API endpoint to update funnel stage.
        """
        data = request.json
        new_stage = data.get('stage')
        
        if not new_stage:
            return jsonify({'success': False, 'message': 'Stage is required'}), 400
        
        try:
            whatsapp_db.update_conversation_funnel(conversation_id, new_stage)
            whatsapp_db.log_agent_action(
                conversation_id,
                session.get('username', 'Agent'),
                'funnel_change',
                {'new_stage': new_stage}
            )
            return jsonify({'success': True, 'message': 'Stage updated successfully'})
        except Exception as e:
            logger.error(f"Error updating funnel stage: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/whatsapp/api/conversation/<conversation_id>/save_notes', methods=['POST'])
    @login_required
    def whatsapp_save_notes(conversation_id):
        """
        API endpoint to save notes for a lead.
        """
        data = request.json
        notes = data.get('notes', '')
        
        try:
            whatsapp_db.update_lead_notes(conversation_id, notes)
            whatsapp_db.log_agent_action(
                conversation_id,
                session.get('username', 'Agent'),
                'note_added',
                {'notes_length': len(notes)}
            )
            return jsonify({'success': True, 'message': 'Notes saved successfully'})
        except Exception as e:
            logger.error(f"Error saving notes: {str(e)}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/whatsapp/api/conversations')
    @login_required
    def whatsapp_api_conversations():
        """
        API endpoint to get conversations (for AJAX/polling).
        """
        # Get filter parameters
        filters = {}
        
        if request.args.get('funnel'):
            filters['funnel_stage'] = request.args.get('funnel')
        
        if request.args.get('stage'):  # Added for unified UI
            filters['funnel_stage'] = request.args.get('stage')
        
        if request.args.get('replied'):
            filters['has_replied'] = request.args.get('replied') == 'true'
        
        if request.args.get('language'):
            filters['language'] = request.args.get('language')
        
        if request.args.get('search'):  # Added for unified UI
            filters['search'] = request.args.get('search')
        
        conversations = whatsapp_db.get_active_conversations(filters=filters, limit=50)
        stats = whatsapp_db.get_inbox_stats()
        
        # Convert datetime objects to strings
        for conv in conversations:
            for key, value in conv.items():
                if isinstance(value, datetime):
                    conv[key] = value.isoformat()
        
        return jsonify({
            'success': True,
            'conversations': conversations,
            'stats': stats
        })
    
    @app.route('/whatsapp/api/messages/<conversation_id>')
    @login_required
    def whatsapp_api_messages(conversation_id):
        """
        API endpoint to get messages for a conversation (for polling).
        """
        messages = whatsapp_db.get_conversation_messages(conversation_id)
        
        # Convert datetime objects to strings
        for msg in messages:
            for key, value in msg.items():
                if isinstance(value, datetime):
                    msg[key] = value.isoformat()
        
        return jsonify({
            'success': True,
            'messages': messages
        })
    
    @app.route('/whatsapp/api/conversation/<conversation_id>')
    @login_required
    def whatsapp_api_conversation(conversation_id):
        """
        API endpoint to get full conversation details (conversation + messages + lead).
        Used by the unified inbox UI.
        """
        # Get conversation details
        conversation = whatsapp_db.get_conversation_by_id(conversation_id)
        
        if not conversation:
            return jsonify({'success': False, 'message': 'Conversation not found'}), 404
        
        # Get messages
        messages = whatsapp_db.get_conversation_messages(conversation_id)
        
        # Get lead data
        lead = whatsapp_db.get_lead_by_conversation(conversation_id)
        
        # Convert datetime objects to strings
        for key, value in conversation.items():
            if isinstance(value, datetime):
                conversation[key] = value.isoformat()
        
        for msg in messages:
            for key, value in msg.items():
                if isinstance(value, datetime):
                    msg[key] = value.isoformat()
        
        if lead:
            for key, value in lead.items():
                if isinstance(value, datetime):
                    lead[key] = value.isoformat()
        
        return jsonify({
            'success': True,
            'conversation': conversation,
            'messages': messages,
            'lead': lead or {}
        })
    
    @app.route('/whatsapp/api/funnel/update', methods=['POST'])
    @login_required
    def whatsapp_update_funnel():
        """
        Update conversation funnel stage.
        """
        data = request.json
        conversation_id = data.get('conversation_id')
        funnel_stage = data.get('funnel_stage')
        
        if not conversation_id or not funnel_stage:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Validate funnel stage
        valid_stages = ['NEW', 'ENGAGED', 'QUALIFIED', 'QUOTE_REQUESTED', 
                       'CONTACT_SHARED', 'CONVERTED', 'DROPPED']
        
        if funnel_stage not in valid_stages:
            return jsonify({'success': False, 'error': 'Invalid funnel stage'}), 400
        
        success = whatsapp_db.update_conversation_funnel(conversation_id, funnel_stage)
        
        if success:
            # Log agent action
            whatsapp_db.log_agent_action(
                conversation_id,
                session.get('username', 'Unknown'),
                'funnel_change',
                {'funnel_stage': funnel_stage}
            )
            
            return jsonify({'success': True, 'message': 'Funnel stage updated'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update funnel'}), 500
    
    @app.route('/whatsapp/api/assign', methods=['POST'])
    @login_required
    def whatsapp_assign_conversation():
        """
        Assign conversation to an agent.
        """
        data = request.json
        conversation_id = data.get('conversation_id')
        agent_name = data.get('agent_name') or session.get('username')
        
        if not conversation_id:
            return jsonify({'success': False, 'error': 'Missing conversation_id'}), 400
        
        success = whatsapp_db.assign_conversation(conversation_id, agent_name)
        
        if success:
            return jsonify({'success': True, 'message': 'Conversation assigned'})
        else:
            return jsonify({'success': False, 'error': 'Failed to assign'}), 500
    
    @app.route('/whatsapp/api/notes/update', methods=['POST'])
    @login_required
    def whatsapp_update_notes():
        """
        Update lead notes.
        """
        data = request.json
        conversation_id = data.get('conversation_id')
        notes = data.get('notes', '')
        
        if not conversation_id:
            return jsonify({'success': False, 'error': 'Missing conversation_id'}), 400
        
        success = whatsapp_db.update_lead_notes(conversation_id, notes)
        
        if success:
            # Log agent action
            whatsapp_db.log_agent_action(
                conversation_id,
                session.get('username', 'Unknown'),
                'note_added',
                {'notes_length': len(notes)}
            )
            
            return jsonify({'success': True, 'message': 'Notes updated'})
        else:
            return jsonify({'success': False, 'error': 'Failed to update notes'}), 500
    
    @app.route('/whatsapp/api/stats')
    @login_required
    def whatsapp_api_stats():
        """
        Get inbox statistics.
        """
        stats = whatsapp_db.get_inbox_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    
    # ============================================
    # REAL-TIME STREAM (SSE)
    # ============================================
    
    @app.route('/whatsapp/stream')
    @login_required
    def whatsapp_realtime_stream():
        """
        Server-Sent Events endpoint for real-time message updates.
        Uses PostgreSQL LISTEN/NOTIFY.
        """
        from flask import Response, stream_with_context
        import psycopg2
        import time
        import json
        
        def event_stream():
            """Generator function for SSE."""
            # Only works with PostgreSQL
            DATABASE_URL = os.getenv('DATABASE_URL')
            
            if not DATABASE_URL:
                logger.warning("SSE requires PostgreSQL - DATABASE_URL not set")
                yield f"data: {json.dumps({'error': 'PostgreSQL required'})}\n\n"
                return
            
            try:
                # Create dedicated connection for LISTEN
                conn = psycopg2.connect(DATABASE_URL)
                conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
                cursor = conn.cursor()
                
                # Listen to both channels
                cursor.execute("LISTEN new_message;")
                cursor.execute("LISTEN funnel_change;")
                
                logger.info(f"SSE stream opened for user: {session.get('username')}")
                
                # Send keepalive every 30 seconds
                last_keepalive = time.time()
                
                while True:
                    # Check for notifications
                    conn.poll()
                    
                    while conn.notifies:
                        notify = conn.notifies.pop(0)
                        
                        # Send notification to client
                        yield f"event: {notify.channel}\n"
                        yield f"data: {notify.payload}\n\n"
                    
                    # Send keepalive
                    if time.time() - last_keepalive > 30:
                        yield f"event: keepalive\n"
                        yield f"data: {json.dumps({'timestamp': time.time()})}\n\n"
                        last_keepalive = time.time()
                    
                    # Sleep briefly to avoid busy loop
                    time.sleep(0.1)
            
            except GeneratorExit:
                logger.info(f"SSE stream closed for user: {session.get('username')}")
                conn.close()
            except Exception as e:
                logger.error(f"SSE stream error: {str(e)}", exc_info=True)
                yield f"event: error\n"
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                conn.close()
        
        return Response(
            stream_with_context(event_stream()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
    
    # ============================================
    # FILE ATTACHMENT ROUTES
    # ============================================
    
    @app.route('/whatsapp/api/send_with_attachment', methods=['POST'])
    @login_required
    def send_with_attachment():
        """
        Handle file uploads and send message with attachment.
        Files are stored in GCS (NOT PostgreSQL) to avoid storage costs.
        """
        try:
            # Get uploaded file
            if 'file' not in request.files:
                return jsonify({'success': False, 'message': 'No file provided'}), 400
            
            file = request.files['file']
            
            if file.filename == '':
                return jsonify({'success': False, 'message': 'No file selected'}), 400
            
            # Get other form data
            conversation_id = request.form.get('conversation_id')
            message_text = request.form.get('message', '')
            
            if not conversation_id:
                return jsonify({'success': False, 'message': 'Conversation ID required'}), 400
            
            # Upload file to GCS
            try:
                file_url = upload_file_to_gcs(file, conversation_id)
            except Exception as e:
                logger.error(f"GCS upload error: {str(e)}")
                return jsonify({
                    'success': False,
                    'message': f'File upload failed: {str(e)}'
                }), 500
            
            # Prepare message with file link
            full_message = message_text
            if message_text:
                full_message += f"\n\n📎 Attachment: {file_url}"
            else:
                full_message = f"📎 Attachment: {file_url}"
            
            # Save message to database
            conversation = whatsapp_db.get_conversation_by_id(conversation_id)
            if not conversation:
                return jsonify({'success': False, 'message': 'Conversation not found'}), 404
            
            # Insert message
            whatsapp_db.insert_message(
                conversation_id=conversation_id,
                sender='agent',
                message=full_message
            )
            
            # Send via N8N webhook (if configured)
            if N8N_SEND_WEBHOOK:
                try:
                    webhook_payload = {
                        'to': conversation['phone'],
                        'message': full_message,
                        'conversation_id': conversation_id,
                        'agent': session.get('username', 'System')
                    }
                    
                    response = requests.post(
                        N8N_SEND_WEBHOOK,
                        json=webhook_payload,
                        timeout=5
                    )
                    
                    if response.status_code != 200:
                        logger.warning(f"N8N webhook returned status {response.status_code}")
                
                except Exception as e:
                    logger.error(f"N8N webhook error: {str(e)}")
            
            return jsonify({
                'success': True,
                'message': 'File sent successfully',
                'file_url': file_url
            })
        
        except Exception as e:
            logger.error(f"Error sending attachment: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'message': f'Error: {str(e)}'
            }), 500
    
    logger.info("✅ WhatsApp inbox routes registered")

