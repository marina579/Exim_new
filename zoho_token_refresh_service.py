#!/usr/bin/env python3
"""
Zoho Token Refresh Service
Proactive token management to prevent daily expiry issues
"""

import os
import time
import logging
import threading
from datetime import datetime, timedelta
from zoho_crm_service import ZohoCRMService

logger = logging.getLogger(__name__)

class ZohoTokenRefreshService:
    """Service to proactively refresh Zoho tokens before expiry."""
    
    _instance = None
    _refresh_thread = None
    _stop_refresh = False
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize token refresh service."""
        if hasattr(self, '_initialized'):
            return
        
        self.zoho_service = ZohoCRMService()
        self.refresh_interval = 3000  # Refresh every 50 minutes (tokens last 1 hour)
        self.last_refresh_time = None
        self.refresh_failures = 0
        self.max_failures = 3
        
        self._initialized = True
        logger.info("✅ Zoho Token Refresh Service initialized")
    
    def start_background_refresh(self):
        """Start background thread to refresh tokens proactively."""
        if self._refresh_thread and self._refresh_thread.is_alive():
            logger.info("ℹ️  Token refresh thread already running")
            return
        
        self._stop_refresh = False
        self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
        self._refresh_thread.start()
        logger.info("✅ Background token refresh started")
    
    def stop_background_refresh(self):
        """Stop background token refresh."""
        self._stop_refresh = True
        if self._refresh_thread:
            self._refresh_thread.join(timeout=5)
        logger.info("🛑 Background token refresh stopped")
    
    def _refresh_loop(self):
        """Background loop to refresh tokens (only runs if token was already fetched)."""
        logger.info("🔄 Token refresh loop started (will wait for first token use)")
        
        # Wait for token to be used at least once before starting refresh loop
        # This prevents rate limits on startup
        initial_wait = 300  # Wait 5 minutes before first check
        logger.info(f"⏳ Waiting {initial_wait}s before first token check (to avoid startup rate limits)...")
        time.sleep(initial_wait)
        
        while not self._stop_refresh:
            try:
                # Get Zoho service (lazy initialization)
                zoho_service = self._get_zoho_service()
                
                # Only check if token was already fetched (has expiry time)
                # Don't fetch token if it was never used
                if not zoho_service.token_expiry:
                    # Token was never fetched - wait longer
                    logger.debug("⏳ Token not yet used, waiting...")
                    time.sleep(300)  # Wait 5 minutes
                    continue
                
                # Check if token needs refresh
                if not zoho_service.is_token_valid():
                    logger.info("🔄 Token expired or invalid, refreshing...")
                    access_token, error = zoho_service.get_access_token(force_refresh=True)
                    
                    if error:
                        self.refresh_failures += 1
                        logger.error(f"❌ Token refresh failed ({self.refresh_failures}/{self.max_failures}): {error}")
                        
                        if self.refresh_failures >= self.max_failures:
                            logger.error("❌ Max token refresh failures reached. Stopping background refresh.")
                            break
                    else:
                        self.refresh_failures = 0
                        self.last_refresh_time = datetime.now()
                        logger.info(f"✅ Token refreshed successfully. Next refresh in {self.refresh_interval}s")
                else:
                    # Token is still valid, but refresh proactively if close to expiry
                    if zoho_service.token_expiry:
                        time_until_expiry = zoho_service.token_expiry - time.time()
                        if time_until_expiry < 600:  # Less than 10 minutes
                            logger.info("🔄 Token expires soon, refreshing proactively...")
                            access_token, error = zoho_service.get_access_token(force_refresh=True)
                            if not error:
                                self.last_refresh_time = datetime.now()
                                logger.info("✅ Proactive token refresh successful")
                
                # Sleep until next check
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"❌ Error in token refresh loop: {str(e)}")
                time.sleep(60)  # Wait before retrying
        
        logger.info("🛑 Token refresh loop stopped")
    
    def ensure_valid_token(self):
        """Ensure we have a valid token, refresh if needed."""
        if not self.zoho_service.is_token_valid():
            logger.info("🔄 Ensuring valid token...")
            access_token, error = self.zoho_service.get_access_token(force_refresh=True)
            if error:
                logger.error(f"❌ Failed to ensure valid token: {error}")
                return False
            return True
        return True
    
    def get_token_status(self):
        """Get current token status."""
        is_valid = self.zoho_service.is_token_valid()
        expires_in = 0
        if self.zoho_service.token_expiry:
            expires_in = int(self.zoho_service.token_expiry - time.time())
        
        return {
            'is_valid': is_valid,
            'expires_in_seconds': expires_in,
            'expires_in_minutes': expires_in // 60 if expires_in > 0 else 0,
            'last_refresh': self.last_refresh_time.isoformat() if self.last_refresh_time else None,
            'refresh_failures': self.refresh_failures,
            'data_center': self.zoho_service.data_center
        }

# Global instance
token_refresh_service = ZohoTokenRefreshService()

