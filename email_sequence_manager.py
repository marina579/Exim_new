"""
Email Sequence Manager - Apollo.io-style follow-up system
Manages multi-email sequences with reply tracking
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from database import db
from zoho_campaigns_service import ZohoCampaignsService
from zoho_crm_service import ZohoCRMService

logger = logging.getLogger(__name__)

# Email sequence configuration
EMAIL_SEQUENCE_CONFIG = {
    'introduction': {
        'step': 1,
        'template_key': os.getenv('ZOHO_CAMPAIGNS_INTRO_TEMPLATE', ''),
        'subject': os.getenv('ZOHO_CAMPAIGNS_INTRO_SUBJECT', 'Welcome to Marineco - Your Trusted Logistics Partner'),
        'delay_days': 0  # Send immediately
    },
    'reminder': {
        'step': 2,
        'template_key': os.getenv('ZOHO_CAMPAIGNS_REMINDER_TEMPLATE', ''),
        'subject': os.getenv('ZOHO_CAMPAIGNS_REMINDER_SUBJECT', 'Quick Reminder: Marineco Logistics Solutions'),
        'delay_days': 3  # Send 3 days after introduction
    },
    'final_close': {
        'step': 3,
        'template_key': os.getenv('ZOHO_CAMPAIGNS_FINAL_TEMPLATE', ''),
        'subject': os.getenv('ZOHO_CAMPAIGNS_FINAL_SUBJECT', 'Final Follow-up: Marineco Logistics'),
        'delay_days': 7  # Send 7 days after reminder (10 days total)
    }
}


class EmailSequenceManager:
    """Manages Apollo.io-style email follow-up sequences."""
    
    def __init__(self):
        self.crm_service = None
        self.campaigns_service = None
        self._init_services()
    
    def _init_services(self):
        """Initialize Zoho services (lazy loading - no token fetch on startup)."""
        try:
            # Initialize service but don't fetch token yet (lazy loading)
            # Token will be fetched on first use to avoid rate limits
            self.crm_service = ZohoCRMService()
            # Don't fetch token here - will be fetched when actually needed
            logger.info("✅ Email sequence manager initialized (token will be fetched on first use)")
        except Exception as e:
            logger.error(f"❌ Error initializing email sequence services: {str(e)}")
    
    def _ensure_services_ready(self):
        """Ensure Zoho services are ready (lazy initialization)."""
        if not self.campaigns_service:
            try:
                access_token, error = self.crm_service.get_access_token()
                if access_token and not error:
                    self.campaigns_service = ZohoCampaignsService(access_token=access_token)
                else:
                    logger.warning(f"⚠️  Could not get access token: {error}")
            except Exception as e:
                logger.error(f"❌ Error getting access token: {str(e)}")
    
    def start_sequence_for_contact(self, contact_id: int, contact_email: str, 
                                   first_name: str, company_name: str) -> Tuple[bool, str]:
        """
        Start email sequence for a new contact.
        Sends introduction email immediately.
        """
        try:
            # Check if contact already has email
            if not contact_email:
                return False, "Contact has no email address"
            
            # Check if already replied (don't send if they replied)
            conn = db._get_connection()
            cursor = conn.cursor()
            
            try:
                if db.db_type == 'postgresql':
                    cursor.execute("""
                        SELECT email_replied, email_sequence_status 
                        FROM contacts 
                        WHERE id = %s
                    """, (contact_id,))
                else:
                    cursor.execute("""
                        SELECT email_replied, email_sequence_status 
                        FROM contacts 
                        WHERE id = ?
                    """, (contact_id,))
                
                row = cursor.fetchone()
                if row:
                    if db.db_type == 'postgresql':
                        replied = row['email_replied'] if row['email_replied'] else False
                        status = row['email_sequence_status'] or 'not_started'
                    else:
                        replied = bool(row[0]) if row[0] else False
                        status = row[1] or 'not_started'
                    
                    if replied:
                        return False, "Contact has already replied - sequence stopped"
                    
                    if status != 'not_started':
                        return False, f"Email sequence already {status}"
            finally:
                conn.close()
            
            # Ensure services are ready (lazy initialization)
            self._ensure_services_ready()
            if not self.campaigns_service:
                return False, "Could not initialize Zoho services"
            
            # Send introduction email
            success, message = self._send_sequence_email(
                contact_id=contact_id,
                contact_email=contact_email,
                first_name=first_name,
                company_name=company_name,
                sequence_type='introduction'
            )
            
            if success:
                # Update contact status
                self._update_contact_sequence_status(
                    contact_id=contact_id,
                    status='in_progress',
                    step=1,
                    last_sent_at=datetime.now()
                )
                logger.info(f"✅ Started email sequence for contact {contact_id}")
                return True, "Introduction email sent"
            else:
                return False, message
                
        except Exception as e:
            logger.error(f"❌ Error starting email sequence: {str(e)}", exc_info=True)
            return False, str(e)
    
    def process_follow_ups(self) -> Dict[str, int]:
        """
        Process pending follow-up emails.
        Checks all contacts in sequence and sends next email if due.
        Returns stats: {'sent': count, 'skipped': count, 'replied': count}
        """
        # Ensure services are ready (lazy initialization)
        self._ensure_services_ready()
        if not self.campaigns_service:
            logger.warning("⚠️  Zoho services not ready - skipping follow-up processing")
            return {'sent': 0, 'skipped': 0, 'replied': 0}
        
        stats = {'sent': 0, 'skipped': 0, 'replied': 0}
        
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            try:
                # Get contacts in sequence who need follow-ups
                if db.db_type == 'postgresql':
                    cursor.execute("""
                        SELECT id, email, contact_name, first_name, last_name, 
                               email_sequence_status, email_sequence_step, 
                               email_last_sent_at, email_replied
                        FROM contacts
                        WHERE email IS NOT NULL 
                          AND email != ''
                          AND email_sequence_status = 'in_progress'
                          AND email_replied = FALSE
                        ORDER BY email_last_sent_at ASC
                    """)
                else:
                    cursor.execute("""
                        SELECT id, email, contact_name, first_name, last_name, 
                               email_sequence_status, email_sequence_step, 
                               email_last_sent_at, email_replied
                        FROM contacts
                        WHERE email IS NOT NULL 
                          AND email != ''
                          AND email_sequence_status = 'in_progress'
                          AND email_replied = 0
                        ORDER BY email_last_sent_at ASC
                    """)
                
                contacts = cursor.fetchall()
                
                for row in contacts:
                    if db.db_type == 'postgresql':
                        contact_id = row['id']
                        email = row['email']
                        contact_name = row['contact_name'] or ''
                        first_name = row['first_name'] or ''
                        last_name = row['last_name'] or ''
                        current_step = row['email_sequence_step'] or 0
                        last_sent = row['email_last_sent_at']
                        replied = row['email_replied'] or False
                    else:
                        contact_id = row[0]
                        email = row[1]
                        contact_name = row[2] or ''
                        first_name = row[3] or ''
                        last_name = row[4] or ''
                        current_step = row[6] or 0
                        last_sent = row[7]
                        replied = bool(row[8]) if row[8] else False
                    
                    # Skip if replied
                    if replied:
                        stats['replied'] += 1
                        continue
                    
                    # Get company name
                    if db.db_type == 'postgresql':
                        cursor.execute("""
                            SELECT name FROM companies 
                            WHERE id = (SELECT company_id FROM contacts WHERE id = %s)
                        """, (contact_id,))
                    else:
                        cursor.execute("""
                            SELECT name FROM companies 
                            WHERE id = (SELECT company_id FROM contacts WHERE id = ?)
                        """, (contact_id,))
                    
                    company_row = cursor.fetchone()
                    company_name = company_row[0] if company_row else 'Your Company'
                    
                    # Determine next step
                    if current_step == 1:
                        next_type = 'reminder'
                        delay_days = EMAIL_SEQUENCE_CONFIG['reminder']['delay_days']
                    elif current_step == 2:
                        next_type = 'final_close'
                        delay_days = EMAIL_SEQUENCE_CONFIG['final_close']['delay_days']
                    else:
                        # Sequence complete
                        self._update_contact_sequence_status(contact_id, 'completed', current_step)
                        stats['skipped'] += 1
                        continue
                    
                    # Check if enough time has passed
                    if last_sent:
                        if isinstance(last_sent, str):
                            last_sent = datetime.fromisoformat(last_sent.replace('Z', '+00:00'))
                        days_since = (datetime.now() - last_sent.replace(tzinfo=None)).days
                        
                        if days_since < delay_days:
                            stats['skipped'] += 1
                            continue
                    
                    # Send next email
                    first_name_display = first_name or contact_name.split()[0] if contact_name else 'there'
                    success, message = self._send_sequence_email(
                        contact_id=contact_id,
                        contact_email=email,
                        first_name=first_name_display,
                        company_name=company_name,
                        sequence_type=next_type
                    )
                    
                    if success:
                        self._update_contact_sequence_status(
                            contact_id=contact_id,
                            status='in_progress',
                            step=EMAIL_SEQUENCE_CONFIG[next_type]['step'],
                            last_sent_at=datetime.now()
                        )
                        stats['sent'] += 1
                        logger.info(f"✅ Sent {next_type} email to {email}")
                    else:
                        stats['skipped'] += 1
                        logger.warning(f"⚠️  Failed to send {next_type} email: {message}")
                
            finally:
                conn.close()
            
            logger.info(f"📧 Email sequence processing: {stats['sent']} sent, {stats['skipped']} skipped, {stats['replied']} already replied")
            return stats
            
        except Exception as e:
            logger.error(f"❌ Error processing follow-ups: {str(e)}", exc_info=True)
            return stats
    
    def _send_sequence_email(self, contact_id: int, contact_email: str, 
                           first_name: str, company_name: str, 
                           sequence_type: str) -> Tuple[bool, str]:
        """Send a sequence email to a contact."""
        try:
            if not self.campaigns_service:
                self._init_services()
            
            if not self.campaigns_service:
                return False, "Campaigns service not available"
            
            config = EMAIL_SEQUENCE_CONFIG.get(sequence_type)
            if not config:
                return False, f"Unknown sequence type: {sequence_type}"
            
            template_key = config['template_key']
            if not template_key:
                return False, f"Template not configured for {sequence_type}"
            
            # Get list key
            list_key = os.getenv('ZOHO_CAMPAIGNS_WELCOME_LIST', 'marketing_list')
            
            # Add contact to list first
            contacts = [{
                'email': contact_email,
                'first_name': first_name,
                'company': company_name
            }]
            
            success, count = self.campaigns_service.add_contacts_to_list(list_key, contacts)
            if not success:
                return False, "Failed to add contact to list"
            
            # Send email
            from_email = os.getenv('ZOHO_CAMPAIGNS_FROM_EMAIL', '')
            from_name = os.getenv('ZOHO_CAMPAIGNS_FROM_NAME', 'Sarita Reddy D')
            
            send_success, campaign_id, message = self.campaigns_service.send_campaign(
                list_key=list_key,
                template_key=template_key,
                subject=config['subject'],
                from_email=from_email,
                from_name=from_name
            )
            
            if send_success:
                logger.info(f"✅ Sent {sequence_type} email to {contact_email} (campaign: {campaign_id})")
                return True, f"Email sent successfully"
            else:
                return False, message
                
        except Exception as e:
            logger.error(f"❌ Error sending sequence email: {str(e)}", exc_info=True)
            return False, str(e)
    
    def _update_contact_sequence_status(self, contact_id: int, status: str, 
                                        step: int, last_sent_at: datetime = None):
        """Update contact's email sequence status."""
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            updates = {
                'email_sequence_status': status,
                'email_sequence_step': step
            }
            
            if last_sent_at:
                updates['email_last_sent_at'] = last_sent_at.isoformat()
            
            if db.db_type == 'postgresql':
                update_fields = [f"{k} = %s" for k in updates.keys()]
                values = list(updates.values()) + [contact_id]
                cursor.execute(
                    f"UPDATE contacts SET {', '.join(update_fields)} WHERE id = %s",
                    values
                )
            else:
                update_fields = [f"{k} = ?" for k in updates.keys()]
                values = list(updates.values()) + [contact_id]
                cursor.execute(
                    f"UPDATE contacts SET {', '.join(update_fields)} WHERE id = ?",
                    values
                )
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"❌ Error updating contact sequence status: {str(e)}")
        finally:
            conn.close()
    
    def mark_contact_replied(self, contact_email: str) -> bool:
        """
        Mark a contact as replied (stops email sequence).
        Called when we detect a reply to any email.
        """
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            if db.db_type == 'postgresql':
                cursor.execute("""
                    UPDATE contacts 
                    SET email_replied = TRUE,
                        email_replied_at = CURRENT_TIMESTAMP,
                        email_sequence_status = 'stopped'
                    WHERE email = %s AND email_replied = FALSE
                """, (contact_email.lower(),))
            else:
                cursor.execute("""
                    UPDATE contacts 
                    SET email_replied = 1,
                        email_replied_at = CURRENT_TIMESTAMP,
                        email_sequence_status = 'stopped'
                    WHERE email = ? AND email_replied = 0
                """, (contact_email.lower(),))
            
            conn.commit()
            updated = cursor.rowcount > 0
            
            if updated:
                logger.info(f"✅ Marked contact {contact_email} as replied - sequence stopped")
            
            return updated
            
        except Exception as e:
            logger.error(f"❌ Error marking contact as replied: {str(e)}")
            return False
        finally:
            conn.close()
    
    def mark_contact_opened(self, contact_email: str) -> bool:
        """Mark email as opened for a contact."""
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            if db.db_type == 'postgresql':
                cursor.execute("""
                    UPDATE contacts 
                    SET email_opened = TRUE
                    WHERE email = %s
                """, (contact_email.lower(),))
            else:
                cursor.execute("""
                    UPDATE contacts 
                    SET email_opened = 1
                    WHERE email = ?
                """, (contact_email.lower(),))
            
            conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"❌ Error marking email as opened: {str(e)}")
            return False
        finally:
            conn.close()
    
    def mark_contact_clicked(self, contact_email: str) -> bool:
        """Mark email as clicked for a contact."""
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            if db.db_type == 'postgresql':
                cursor.execute("""
                    UPDATE contacts 
                    SET email_clicked = TRUE
                    WHERE email = %s
                """, (contact_email.lower(),))
            else:
                cursor.execute("""
                    UPDATE contacts 
                    SET email_clicked = 1
                    WHERE email = ?
                """, (contact_email.lower(),))
            
            conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            logger.error(f"❌ Error marking email as clicked: {str(e)}")
            return False
        finally:
            conn.close()


# Global instance
email_sequence_manager = EmailSequenceManager()

