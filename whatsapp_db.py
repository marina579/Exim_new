"""
WhatsApp Inbox - Database Module
Handles all PostgreSQL queries for WhatsApp conversations and messages.
"""

import os
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
import sqlite3

logger = logging.getLogger(__name__)

# Auto-detect database type
DATABASE_URL = os.getenv('DATABASE_URL')

if DATABASE_URL:
    DB_TYPE = 'postgresql'
    logger.info("🐘 Using PostgreSQL for WhatsApp inbox")
else:
    DB_TYPE = 'sqlite'
    DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'whatsapp.db')
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    logger.info(f"📁 Using SQLite for WhatsApp inbox: {DB_PATH}")


class WhatsAppDatabase:
    """Manages WhatsApp conversation and message storage."""
    
    def __init__(self):
        """Initialize database connection."""
        self.db_type = DB_TYPE
    
    def _get_connection(self):
        """Get database connection."""
        if self.db_type == 'postgresql':
            return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn
    
    # ============================================
    # CONVERSATIONS
    # ============================================
    
    def get_active_conversations(self, filters: Dict = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        Get active conversations for inbox view.
        
        Args:
            filters: Optional filters (funnel_stage, has_replied, language, assigned_to)
            limit: Max results to return
            offset: Pagination offset
        
        Returns:
            List of conversation dictionaries with lead data and preview
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Build WHERE clause from filters
            where_clauses = ["c.is_active = true", "c.funnel_stage != 'DROPPED'"]
            params = []
            
            if filters:
                if filters.get('funnel_stage'):
                    where_clauses.append("c.funnel_stage = %s" if self.db_type == 'postgresql' else "c.funnel_stage = ?")
                    params.append(filters['funnel_stage'])
                
                if filters.get('has_replied') is not None:
                    where_clauses.append("c.has_user_replied = %s" if self.db_type == 'postgresql' else "c.has_user_replied = ?")
                    params.append(filters['has_replied'])
                
                if filters.get('language'):
                    where_clauses.append("c.language = %s" if self.db_type == 'postgresql' else "c.language = ?")
                    params.append(filters['language'])
                
                if filters.get('assigned_to'):
                    where_clauses.append("c.assigned_to = %s" if self.db_type == 'postgresql' else "c.assigned_to = ?")
                    params.append(filters['assigned_to'])
                
                if filters.get('search'):
                    search_clause = """(
                        c.phone LIKE %s OR 
                        l.name LIKE %s OR 
                        l.company LIKE %s OR
                        l.email LIKE %s
                    )""" if self.db_type == 'postgresql' else """(
                        c.phone LIKE ? OR 
                        l.name LIKE ? OR 
                        l.company LIKE ? OR
                        l.email LIKE ?
                    )"""
                    where_clauses.append(search_clause)
                    search_term = f"%{filters['search']}%"
                    params.extend([search_term, search_term, search_term, search_term])
            
            where_sql = " AND ".join(where_clauses)
            
            # Add pagination params
            params.extend([limit, offset])
            
            query = f"""
                SELECT 
                    c.id as conversation_id,
                    c.id,
                    c.phone,
                    c.name,
                    c.language,
                    c.intent,
                    c.funnel_stage,
                    c.lead_score,
                    c.has_user_replied,
                    c.last_message_at,
                    c.assigned_to,
                    c.created_at,
                    l.name as lead_name,
                    l.email,
                    l.company,
                    l.origin,
                    l.destination,
                    l.mode,
                    l.cargo_type,
                    (SELECT message 
                     FROM messages m 
                     WHERE m.conversation_id = c.id 
                     ORDER BY m.created_at DESC 
                     LIMIT 1) as last_message_preview,
                    (SELECT COUNT(*) 
                     FROM messages m 
                     WHERE m.conversation_id = c.id 
                     AND m.direction = 'inbound' 
                     AND m.status != 'read') as unread_count
                FROM conversations c
                LEFT JOIN leads l ON l.conversation_id = c.id
                WHERE {where_sql}
                ORDER BY c.last_message_at DESC NULLS LAST
                LIMIT {"%s" if self.db_type == "postgresql" else "?"} OFFSET {"%s" if self.db_type == "postgresql" else "?"}
            """
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Convert to dict
            conversations = []
            for row in rows:
                conv = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                conversations.append(conv)
            
            return conversations
            
        finally:
            conn.close()
    
    def get_conversation_by_id(self, conversation_id: str) -> Optional[Dict]:
        """Get single conversation with lead data."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT 
                    c.*,
                    l.name as lead_name,
                    l.email,
                    l.company,
                    l.origin,
                    l.destination,
                    l.mode,
                    l.cargo_type,
                    l.weight,
                    l.shipment_type,
                    l.notes
                FROM conversations c
                LEFT JOIN leads l ON l.conversation_id = c.id
                WHERE c.id = {param_placeholder}
            """
            
            cursor.execute(query, (conversation_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
            return None
            
        finally:
            conn.close()
    
    def get_conversation_by_phone(self, phone: str) -> Optional[Dict]:
        """Get conversation by phone number."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT * FROM conversations
                WHERE phone = {param_placeholder}
            """
            
            cursor.execute(query, (phone,))
            row = cursor.fetchone()
            
            if row:
                return dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
            return None
            
        finally:
            conn.close()
    
    def update_conversation_funnel(self, conversation_id: str, funnel_stage: str) -> bool:
        """Update conversation funnel stage."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                UPDATE conversations
                SET funnel_stage = {param_placeholder},
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {param_placeholder}
            """
            
            cursor.execute(query, (funnel_stage, conversation_id))
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating funnel: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def assign_conversation(self, conversation_id: str, agent_name: str) -> bool:
        """Assign conversation to an agent."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                UPDATE conversations
                SET assigned_to = {param_placeholder},
                    assigned_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = {param_placeholder}
            """
            
            cursor.execute(query, (agent_name, conversation_id))
            conn.commit()
            
            # Log action
            self.log_agent_action(conversation_id, agent_name, 'assign', {'assigned_to': agent_name})
            
            return True
            
        except Exception as e:
            logger.error(f"Error assigning conversation: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    # ============================================
    # MESSAGES
    # ============================================
    
    def get_conversation_messages(self, conversation_id: str, limit: int = 100) -> List[Dict]:
        """Get all messages for a conversation."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT 
                    id,
                    conversation_id,
                    direction,
                    sender,
                    message,
                    status,
                    media_url,
                    media_type,
                    created_at,
                    delivered_at,
                    read_at
                FROM messages
                WHERE conversation_id = {param_placeholder}
                ORDER BY created_at ASC
                LIMIT {param_placeholder}
            """
            
            cursor.execute(query, (conversation_id, limit))
            rows = cursor.fetchall()
            
            messages = []
            for row in rows:
                msg = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                messages.append(msg)
            
            return messages
            
        finally:
            conn.close()
    
    def mark_messages_as_read(self, conversation_id: str) -> bool:
        """Mark all inbound messages as read."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                UPDATE messages
                SET status = 'read',
                    read_at = CURRENT_TIMESTAMP
                WHERE conversation_id = {param_placeholder}
                  AND direction = 'inbound'
                  AND status != 'read'
            """
            
            cursor.execute(query, (conversation_id,))
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error marking messages as read: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    # ============================================
    # LEADS
    # ============================================
    
    def get_lead_by_conversation(self, conversation_id: str) -> Optional[Dict]:
        """Get lead data for a conversation."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT * FROM leads
                WHERE conversation_id = {param_placeholder}
            """
            
            cursor.execute(query, (conversation_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
            return None
            
        finally:
            conn.close()
    
    def update_lead_notes(self, conversation_id: str, notes: str) -> bool:
        """Update notes for a lead."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                UPDATE leads
                SET notes = {param_placeholder},
                    updated_at = CURRENT_TIMESTAMP
                WHERE conversation_id = {param_placeholder}
            """
            
            cursor.execute(query, (notes, conversation_id))
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating lead notes: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    # ============================================
    # AGENT ACTIONS
    # ============================================
    
    def insert_message(self, conversation_id: str, direction: str, sender: str, 
                      message: str, status: str = 'sent') -> bool:
        """
        Insert a new message into the messages table.
        
        Args:
            conversation_id: UUID of the conversation
            direction: 'inbound' or 'outbound'
            sender: 'user', 'bot', 'agent', or 'campaign'
            message: The message text
            status: Message status (default: 'sent')
        
        Returns:
            bool: True if successful
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                query = """
                    INSERT INTO messages (conversation_id, direction, sender, message, status)
                    VALUES (%s, %s, %s, %s, %s)
                """
                cursor.execute(query, (conversation_id, direction, sender, message, status))
            else:
                query = """
                    INSERT INTO messages (conversation_id, direction, sender, message, status)
                    VALUES (?, ?, ?, ?, ?)
                """
                cursor.execute(query, (conversation_id, direction, sender, message, status))
            
            conn.commit()
            logger.info(f"✅ Message inserted: {direction} from {sender}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting message: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def log_agent_action(self, conversation_id: str, agent_name: str, 
                        action_type: str, action_data: Dict = None) -> bool:
        """Log an agent action for audit trail."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                import json
                query = """
                    INSERT INTO agent_actions (conversation_id, agent_name, action_type, action_data)
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(query, (conversation_id, agent_name, action_type, json.dumps(action_data or {})))
            else:
                import json
                query = """
                    INSERT INTO agent_actions (conversation_id, agent_name, action_type, action_data)
                    VALUES (?, ?, ?, ?)
                """
                cursor.execute(query, (conversation_id, agent_name, action_type, json.dumps(action_data or {})))
            
            conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error logging agent action: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    # ============================================
    # STATISTICS
    # ============================================
    
    def get_inbox_stats(self) -> Dict:
        """Get overall inbox statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT 
                    COUNT(*) FILTER (WHERE is_active = true) as active_total,
                    COUNT(*) FILTER (WHERE funnel_stage = 'NEW') as new_count,
                    COUNT(*) FILTER (WHERE funnel_stage = 'ENGAGED') as engaged_count,
                    COUNT(*) FILTER (WHERE funnel_stage = 'QUALIFIED') as qualified_count,
                    COUNT(*) FILTER (WHERE funnel_stage = 'QUOTE_REQUESTED') as quote_requested_count,
                    COUNT(*) FILTER (WHERE funnel_stage = 'CONTACT_SHARED') as contact_shared_count,
                    COUNT(*) FILTER (WHERE funnel_stage = 'CONVERTED') as converted_count,
                    COUNT(*) FILTER (WHERE has_user_replied = true) as replied_count,
                    (SELECT COUNT(*) FROM messages WHERE direction = 'inbound' AND status != 'read') as unread_total
                FROM conversations
            """
            
            cursor.execute(query)
            row = cursor.fetchone()
            
            if row:
                return dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
            return {}
            
        finally:
            conn.close()
    
    def get_funnel_breakdown(self) -> List[Dict]:
        """Get funnel stage breakdown."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT * FROM v_funnel_breakdown
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            breakdown = []
            for row in rows:
                stage = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                breakdown.append(stage)
            
            return breakdown
            
        finally:
            conn.close()


# Global instance
whatsapp_db = WhatsAppDatabase()

