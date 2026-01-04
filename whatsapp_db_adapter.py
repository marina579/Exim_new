"""
WhatsApp Database Adapter
Adapts chat_history and Lead tables (used by N8N) to work with WhatsApp UI
"""

import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
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


class WhatsAppDatabaseAdapter:
    """
    Adapts N8N's chat_history and Lead tables to WhatsApp UI format.
    
    Mappings:
    - chat_history -> messages (role: "Customer" = inbound, "AI Agent" = outbound)
    - Lead -> lead info
    - Generates virtual conversations from chat_history
    """
    
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
    # CONVERSATIONS (Generated from chat_history)
    # ============================================
    
    def get_active_conversations(self, filters: Dict = None, limit: int = 50, offset: int = 0) -> List[Dict]:
        """
        Get active conversations by aggregating chat_history.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Build WHERE clause from filters
            where_clauses = []
            params = []
            
            if filters:
                if filters.get('search'):
                    search_clause = """(
                        ch.phone LIKE %s OR 
                        l.name LIKE %s OR 
                        l.company LIKE %s
                    )""" if self.db_type == 'postgresql' else """(
                        ch.phone LIKE ? OR 
                        l.name LIKE ? OR 
                        l.company LIKE ?
                    )"""
                    where_clauses.append(search_clause)
                    search_term = f"%{filters['search']}%"
                    params.extend([search_term, search_term, search_term])
            
            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            
            # Add pagination params
            params.extend([limit, offset])
            
            # Aggregate conversations from chat_history
            query = f"""
                WITH conversation_summary AS (
                    SELECT 
                        ch.phone,
                        MAX(ch.created_at) as last_message_at,
                        COUNT(*) as message_count,
                        COUNT(*) FILTER (WHERE ch.role = 'Customer') as user_message_count,
                        (SELECT content 
                         FROM chat_history 
                         WHERE phone = ch.phone 
                         ORDER BY created_at DESC 
                         LIMIT 1) as last_message_preview
                    FROM chat_history ch
                    GROUP BY ch.phone
                )
                SELECT 
                    cs.phone as conversation_id,
                    cs.phone,
                    cs.last_message_at,
                    cs.last_message_preview,
                    cs.message_count,
                    l.name as lead_name,
                    l.name,
                    l.company,
                    l.origin,
                    l.destination,
                    l.mode,
                    l.cargo_type,
                    l.language,
                    l.status as funnel_stage,
                    CASE 
                        WHEN cs.user_message_count > 0 THEN true 
                        ELSE false 
                    END as has_user_replied,
                    COALESCE(
                        CASE 
                            WHEN l.origin IS NOT NULL AND l.destination IS NOT NULL THEN 60
                            WHEN l.company IS NOT NULL THEN 40
                            WHEN cs.user_message_count > 2 THEN 30
                            ELSE 10
                        END, 10
                    ) as lead_score,
                    0 as unread_count
                FROM conversation_summary cs
                LEFT JOIN "Lead" l ON l.phone = cs.phone
                WHERE {where_sql}
                ORDER BY cs.last_message_at DESC
                LIMIT {"%s" if self.db_type == "postgresql" else "?"} OFFSET {"%s" if self.db_type == "postgresql" else "?"}
            """
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Convert to dict
            conversations = []
            for row in rows:
                conv = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                # Parse timestamp if string
                if isinstance(conv.get('last_message_at'), str):
                    try:
                        conv['last_message_at'] = datetime.fromisoformat(conv['last_message_at'].replace('+00', ''))
                    except:
                        pass
                conversations.append(conv)
            
            return conversations
            
        finally:
            conn.close()
    
    def get_conversation_by_id(self, conversation_id: str) -> Optional[Dict]:
        """
        Get single conversation (conversation_id is actually phone number).
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT 
                    l.phone as id,
                    l.phone,
                    l.name,
                    l.language,
                    l.status as funnel_stage,
                    l.company,
                    l.origin,
                    l.destination,
                    l.mode,
                    l.cargo_type,
                    l.weight,
                    l.shipment_type,
                    l.notes,
                    50 as lead_score,
                    true as has_user_replied,
                    true as is_active,
                    (SELECT MAX(created_at) FROM chat_history WHERE phone = l.phone) as last_message_at
                FROM "Lead" l
                WHERE l.phone = {param_placeholder}
            """
            
            cursor.execute(query, (conversation_id,))
            row = cursor.fetchone()
            
            if row:
                conv = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                # Parse timestamp if string
                if isinstance(conv.get('last_message_at'), str):
                    try:
                        conv['last_message_at'] = datetime.fromisoformat(conv['last_message_at'].replace('+00', ''))
                    except:
                        pass
                return conv
            return None
            
        finally:
            conn.close()
    
    def get_conversation_by_phone(self, phone: str) -> Optional[Dict]:
        """Get conversation by phone number (same as by ID)."""
        return self.get_conversation_by_id(phone)
    
    def update_conversation_funnel(self, conversation_id: str, funnel_stage: str) -> bool:
        """Update Lead status (maps to funnel_stage)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                UPDATE "Lead"
                SET status = {param_placeholder},
                    updated_at = CURRENT_TIMESTAMP
                WHERE phone = {param_placeholder}
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
        """Assign conversation (placeholder - not in Lead table)."""
        logger.info(f"Assignment requested for {conversation_id} to {agent_name} (not stored in Lead table)")
        return True
    
    # ============================================
    # MESSAGES (Adapted from chat_history)
    # ============================================
    
    def get_conversation_messages(self, conversation_id: str, limit: int = 100) -> List[Dict]:
        """
        Get all messages for a conversation from chat_history.
        Maps role to direction/sender.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT 
                    id,
                    phone as conversation_id,
                    CASE 
                        WHEN role = 'Customer' THEN 'inbound'
                        ELSE 'outbound'
                    END as direction,
                    CASE 
                        WHEN role = 'Customer' THEN 'user'
                        WHEN role = 'AI Agent' THEN 'bot'
                        ELSE 'bot'
                    END as sender,
                    content as message,
                    'delivered' as status,
                    NULL as media_url,
                    NULL as media_type,
                    created_at,
                    NULL as delivered_at,
                    NULL as read_at
                FROM chat_history
                WHERE phone = {param_placeholder}
                ORDER BY created_at ASC
                LIMIT {param_placeholder}
            """
            
            cursor.execute(query, (conversation_id, limit))
            rows = cursor.fetchall()
            
            messages = []
            for row in rows:
                msg = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                # Parse timestamp if string
                if isinstance(msg.get('created_at'), str):
                    try:
                        msg['created_at'] = datetime.fromisoformat(msg['created_at'].replace('+00', ''))
                    except:
                        pass
                messages.append(msg)
            
            return messages
            
        finally:
            conn.close()
    
    def mark_messages_as_read(self, conversation_id: str) -> bool:
        """Mark messages as read (placeholder)."""
        logger.info(f"Mark as read: {conversation_id} (not implemented in chat_history)")
        return True
    
    # ============================================
    # LEADS (From Lead table)
    # ============================================
    
    def get_lead_by_conversation(self, conversation_id: str) -> Optional[Dict]:
        """Get lead data (conversation_id is phone number)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT * FROM "Lead"
                WHERE phone = {param_placeholder}
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
                UPDATE "Lead"
                SET notes = {param_placeholder},
                    updated_at = CURRENT_TIMESTAMP
                WHERE phone = {param_placeholder}
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
        Insert a new message into chat_history table.
        Maps direction/sender back to role.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Map direction/sender to role
            if direction == 'inbound' or sender == 'user':
                role = 'Customer'
            elif sender == 'agent':
                role = 'Agent'
            else:
                role = 'AI Agent'
            
            if self.db_type == 'postgresql':
                query = """
                    INSERT INTO chat_history (phone, role, content, created_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """
                cursor.execute(query, (conversation_id, role, message))
            else:
                query = """
                    INSERT INTO chat_history (phone, role, content, created_at)
                    VALUES (?, ?, ?, datetime('now'))
                """
                cursor.execute(query, (conversation_id, role, message))
            
            conn.commit()
            logger.info(f"✅ Message inserted into chat_history: {direction} from {sender}")
            return True
            
        except Exception as e:
            logger.error(f"Error inserting message: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def log_agent_action(self, conversation_id: str, agent_name: str, 
                        action_type: str, action_data: Dict = None) -> bool:
        """Log an agent action (placeholder)."""
        logger.info(f"Agent action: {agent_name} - {action_type} on {conversation_id}")
        return True
    
    # ============================================
    # STATISTICS
    # ============================================
    
    def get_inbox_stats(self) -> Dict:
        """Get overall inbox statistics from chat_history and Lead."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # Count unique conversations
            cursor.execute("""
                SELECT COUNT(DISTINCT phone) as total_conversations
                FROM chat_history
            """)
            total = cursor.fetchone()
            total_count = total['total_conversations'] if self.db_type == 'postgresql' else total[0]
            
            # Count by status in Lead table
            cursor.execute("""
                SELECT 
                    status,
                    COUNT(*) as count
                FROM "Lead"
                GROUP BY status
            """)
            status_counts = {}
            for row in cursor.fetchall():
                status_dict = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                status_counts[status_dict['status'] or 'unknown'] = status_dict['count']
            
            return {
                'active_total': total_count,
                'new_count': status_counts.get('NEW', 0),
                'engaged_count': status_counts.get('ENGAGED', 0),
                'qualified_count': status_counts.get('QUALIFIED', 0),
                'quote_requested_count': status_counts.get('QUOTE_REQUESTED', 0),
                'contact_shared_count': status_counts.get('CONTACT_SHARED', 0),
                'converted_count': status_counts.get('CONVERTED', 0),
                'replied_count': total_count,  # All in chat_history have replied
                'unread_total': 0  # Not tracked in chat_history
            }
            
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {}
        finally:
            conn.close()
    
    def get_funnel_breakdown(self) -> List[Dict]:
        """Get funnel stage breakdown from Lead table."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            query = """
                SELECT 
                    status as funnel_stage,
                    COUNT(*) as count,
                    ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 2) as percentage,
                    50 as avg_score
                FROM "Lead"
                GROUP BY status
            """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            breakdown = []
            for row in rows:
                stage = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                breakdown.append(stage)
            
            return breakdown
            
        except Exception as e:
            logger.error(f"Error getting funnel breakdown: {e}")
            return []
        finally:
            conn.close()


# Global instance
whatsapp_db = WhatsAppDatabaseAdapter()

