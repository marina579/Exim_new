"""
Campaign Scheduler - Handles scheduled email campaigns
Uses APScheduler for background task scheduling
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from database import db
from zoho_campaigns_service import ZohoCampaignsService
from zoho_crm_service import ZohoCRMService

logger = logging.getLogger(__name__)

# Import email sequence manager for follow-up processing
try:
    from email_sequence_manager import email_sequence_manager
except ImportError:
    email_sequence_manager = None
    logger.warning("⚠️  Email sequence manager not available")

# Global scheduler instance
scheduler = None


def get_scheduler() -> BackgroundScheduler:
    """Get or create the global scheduler instance."""
    global scheduler
    if scheduler is None:
        scheduler = BackgroundScheduler()
        scheduler.start()
        logger.info("✅ Campaign scheduler started")
    return scheduler


class CampaignScheduler:
    """Manages scheduled email campaigns."""
    
    def __init__(self):
        self.scheduler = get_scheduler()
        self.campaigns_service = None
        self.crm_service = None
        self._init_services()
    
    def _init_services(self):
        """Initialize Zoho services."""
        try:
            # Get access token from CRM service (can be reused)
            crm_service = ZohoCRMService()
            access_token, error = crm_service.get_access_token()
            
            if access_token and not error:
                self.campaigns_service = ZohoCampaignsService(access_token=access_token)
                self.crm_service = crm_service
                logger.info("✅ Campaign scheduler services initialized")
            else:
                logger.warning("⚠️  Could not initialize Zoho services for scheduler")
        except Exception as e:
            logger.error(f"❌ Error initializing scheduler services: {str(e)}")
    
    def create_scheduled_campaign(self, campaign_config: Dict) -> Tuple[bool, Optional[str], str]:
        """
        Create a scheduled email campaign.
        
        Args:
            campaign_config: Dictionary with:
                - name: Campaign name
                - list_key: Zoho Campaigns list key
                - template_key: Email template key
                - subject: Email subject
                - from_email: Sender email
                - from_name: Sender name
                - schedule_type: 'daily', 'weekly', 'monthly', 'once'
                - schedule_time: Time in HH:MM format (e.g., '09:00')
                - schedule_day: Day of week (0-6, Monday=0) for weekly, or day of month (1-31) for monthly
                - start_date: Start date (YYYY-MM-DD) - optional
                - end_date: End date (YYYY-MM-DD) - optional
                - enabled: True/False
        
        Returns:
            Tuple of (success: bool, schedule_id: Optional[str], message: str)
        """
        try:
            # Validate config
            required_fields = ['name', 'list_key', 'template_key', 'subject', 
                             'schedule_type', 'schedule_time']
            for field in required_fields:
                if field not in campaign_config:
                    return False, None, f"Missing required field: {field}"
            
            schedule_type = campaign_config['schedule_type']
            schedule_time = campaign_config['schedule_time']
            
            # Parse time
            try:
                hour, minute = map(int, schedule_time.split(':'))
            except:
                return False, None, "Invalid time format. Use HH:MM (e.g., 09:00)"
            
            # Create trigger based on schedule type
            trigger = None
            
            if schedule_type == 'daily':
                trigger = CronTrigger(hour=hour, minute=minute)
            elif schedule_type == 'weekly':
                day_of_week = campaign_config.get('schedule_day', 0)  # Default Monday
                trigger = CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)
            elif schedule_type == 'monthly':
                day_of_month = campaign_config.get('schedule_day', 1)  # Default 1st
                trigger = CronTrigger(day=day_of_month, hour=hour, minute=minute)
            elif schedule_type == 'once':
                start_date = campaign_config.get('start_date')
                if start_date:
                    try:
                        start_datetime = datetime.strptime(f"{start_date} {schedule_time}", "%Y-%m-%d %H:%M")
                        trigger = DateTrigger(run_date=start_datetime)
                    except:
                        return False, None, "Invalid date format. Use YYYY-MM-DD"
                else:
                    return False, None, "start_date required for 'once' schedule"
            else:
                return False, None, f"Invalid schedule_type: {schedule_type}. Use: daily, weekly, monthly, once"
            
            # Save to database
            schedule_id = db.save_scheduled_campaign(campaign_config)
            
            if not schedule_id:
                return False, None, "Failed to save campaign to database"
            
            # Schedule the job
            if campaign_config.get('enabled', True):
                job_id = f"campaign_{schedule_id}"
                
                self.scheduler.add_job(
                    func=self._send_scheduled_campaign,
                    trigger=trigger,
                    id=job_id,
                    args=[schedule_id],
                    replace_existing=True,
                    max_instances=1
                )
                
                logger.info(f"✅ Scheduled campaign '{campaign_config['name']}' (ID: {schedule_id})")
                return True, schedule_id, f"Campaign scheduled successfully"
            else:
                logger.info(f"ℹ️  Campaign '{campaign_config['name']}' saved but disabled")
                return True, schedule_id, "Campaign saved but not scheduled (disabled)"
                
        except Exception as e:
            logger.error(f"❌ Error creating scheduled campaign: {str(e)}", exc_info=True)
            return False, None, f"Error: {str(e)}"
    
    def _send_scheduled_campaign(self, schedule_id: int):
        """
        Internal method to send a scheduled campaign.
        Called by the scheduler.
        """
        try:
            logger.info(f"📧 Executing scheduled campaign: {schedule_id}")
            
            # Get campaign config from database
            campaign = db.get_scheduled_campaign(schedule_id)
            if not campaign:
                logger.error(f"❌ Campaign {schedule_id} not found in database")
                return
            
            if not campaign.get('enabled', True):
                logger.info(f"ℹ️  Campaign {schedule_id} is disabled, skipping")
                return
            
            # Check if we need to sync contacts first
            list_key = campaign.get('list_key')
            template_key = campaign.get('template_key')
            subject = campaign.get('subject')
            from_email = campaign.get('from_email')
            from_name = campaign.get('from_name')
            
            # Sync contacts from CRM if needed
            auto_sync = campaign.get('auto_sync_contacts', True)
            if auto_sync and self.crm_service:
                logger.info(f"🔄 Auto-syncing contacts from CRM to list: {list_key}")
                # Get contacts from database
                contacts = db.get_all_contacts_for_campaign()
                if contacts:
                    success, count = self.campaigns_service.add_contacts_to_list(list_key, contacts)
                    if success:
                        logger.info(f"✅ Synced {count} contacts to Campaigns list")
            
            # Send campaign
            if not self.campaigns_service:
                self._init_services()
            
            if self.campaigns_service:
                success, campaign_id, message = self.campaigns_service.send_campaign(
                    list_key=list_key,
                    template_key=template_key,
                    subject=subject,
                    from_email=from_email,
                    from_name=from_name
                )
                
                if success:
                    # Update database
                    db.update_scheduled_campaign_status(schedule_id, 'sent', campaign_id)
                    logger.info(f"✅ Scheduled campaign sent successfully: {campaign_id}")
                else:
                    db.update_scheduled_campaign_status(schedule_id, 'failed', None, message)
                    logger.error(f"❌ Failed to send scheduled campaign: {message}")
            else:
                logger.error("❌ Campaigns service not available")
                db.update_scheduled_campaign_status(schedule_id, 'failed', None, "Service not available")
                
        except Exception as e:
            logger.error(f"❌ Error executing scheduled campaign {schedule_id}: {str(e)}", exc_info=True)
            db.update_scheduled_campaign_status(schedule_id, 'failed', None, str(e))
    
    def update_scheduled_campaign(self, schedule_id: int, updates: Dict) -> Tuple[bool, str]:
        """Update a scheduled campaign."""
        try:
            # Update in database
            success = db.update_scheduled_campaign(schedule_id, updates)
            if not success:
                return False, "Failed to update campaign in database"
            
            # Reschedule if enabled status changed
            if 'enabled' in updates:
                job_id = f"campaign_{schedule_id}"
                if updates['enabled']:
                    # Re-enable: get campaign and reschedule
                    campaign = db.get_scheduled_campaign(schedule_id)
                    if campaign:
                        # Remove old job
                        try:
                            self.scheduler.remove_job(job_id)
                        except:
                            pass
                        
                        # Recreate with same config
                        self.create_scheduled_campaign(campaign)
                else:
                    # Disable: remove job
                    try:
                        self.scheduler.remove_job(job_id)
                        logger.info(f"⏸️  Disabled scheduled campaign: {schedule_id}")
                    except:
                        pass
            
            return True, "Campaign updated successfully"
            
        except Exception as e:
            logger.error(f"❌ Error updating scheduled campaign: {str(e)}")
            return False, str(e)
    
    def delete_scheduled_campaign(self, schedule_id: int) -> Tuple[bool, str]:
        """Delete a scheduled campaign."""
        try:
            # Remove from scheduler
            job_id = f"campaign_{schedule_id}"
            try:
                self.scheduler.remove_job(job_id)
            except:
                pass  # Job might not exist
            
            # Delete from database
            success = db.delete_scheduled_campaign(schedule_id)
            if success:
                logger.info(f"✅ Deleted scheduled campaign: {schedule_id}")
                return True, "Campaign deleted successfully"
            else:
                return False, "Failed to delete campaign from database"
                
        except Exception as e:
            logger.error(f"❌ Error deleting scheduled campaign: {str(e)}")
            return False, str(e)
    
    def get_all_scheduled_campaigns(self) -> List[Dict]:
        """Get all scheduled campaigns."""
        return db.get_all_scheduled_campaigns()
    
    def get_scheduled_campaign(self, schedule_id: int) -> Optional[Dict]:
        """Get a specific scheduled campaign."""
        return db.get_scheduled_campaign(schedule_id)


# Global instance
campaign_scheduler = CampaignScheduler()

