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
from whatsapp_db import whatsapp_db

logger = logging.getLogger(__name__)

# N8N webhook URL for sending messages (set in Railway env vars)
N8N_SEND_WEBHOOK = os.getenv('N8N_SEND_WEBHOOK_URL', 'https://your-n8n-instance.com/webhook/send-whatsapp')


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
        Main WhatsApp inbox view - shows conversation list.
        """
        # Get filter parameters
        filters = {}
        
        if request.args.get('funnel'):
            filters['funnel_stage'] = request.args.get('funnel')
        
        if request.args.get('replied'):
            filters['has_replied'] = request.args.get('replied') == 'true'
        
        if request.args.get('language'):
            filters['language'] = request.args.get('language')
        
        if request.args.get('search'):
            filters['search'] = request.args.get('search')
        
        # Get conversations
        conversations = whatsapp_db.get_active_conversations(filters=filters, limit=50)
        
        # Get inbox stats
        stats = whatsapp_db.get_inbox_stats()
        
        # Get funnel breakdown
        funnel_breakdown = whatsapp_db.get_funnel_breakdown()
        
        return render_template(
            'whatsapp_inbox.html',
            conversations=conversations,
            stats=stats,
            funnel_breakdown=funnel_breakdown,
            filters=filters,
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
            
            response = requests.post(
                N8N_SEND_WEBHOOK,
                json=webhook_payload,
                timeout=10
            )
            
            if response.status_code == 200:
                # Log agent action
                whatsapp_db.log_agent_action(
                    conversation_id,
                    agent_name,
                    'reply',
                    {'message': message[:100]}
                )
                
                return jsonify({
                    'success': True,
                    'message': 'Message sent successfully'
                })
            else:
                logger.error(f"n8n webhook error: {response.status_code} - {response.text}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to send message: {response.text}'
                }), 500
        
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {str(e)}", exc_info=True)
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
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
        
        if request.args.get('replied'):
            filters['has_replied'] = request.args.get('replied') == 'true'
        
        if request.args.get('language'):
            filters['language'] = request.args.get('language')
        
        conversations = whatsapp_db.get_active_conversations(filters=filters, limit=50)
        
        # Convert datetime objects to strings
        for conv in conversations:
            for key, value in conv.items():
                if isinstance(value, datetime):
                    conv[key] = value.isoformat()
        
        return jsonify({
            'success': True,
            'conversations': conversations
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
    
    logger.info("✅ WhatsApp inbox routes registered")

