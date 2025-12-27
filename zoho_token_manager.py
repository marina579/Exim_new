"""
Zoho Token Manager - Persistent token storage with locking and exponential backoff
Prevents rate limits by ensuring only one refresh happens at a time
"""

import os
import time
import threading
import requests
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple
from database import db

logger = logging.getLogger(__name__)

# Global refresh lock to prevent parallel refreshes
_refresh_lock = threading.Lock()
_last_refresh_attempt = {}  # Track last refresh attempt time per data center


class ZohoTokenManager:
    """Manages Zoho OAuth tokens with persistent storage and locking."""
    
    def __init__(self, data_center: str = "in"):
        self.data_center = data_center or os.getenv('ZOHO_DATA_CENTER', 'in')
        self.client_id = os.getenv('ZOHO_CLIENT_ID')
        self.client_secret = os.getenv('ZOHO_CLIENT_SECRET')
        self.refresh_token = os.getenv('ZOHO_REFRESH_TOKEN')
        
        # Clean refresh token
        if self.refresh_token:
            self.refresh_token = self.refresh_token.strip().replace('\n', '').replace('\r', '')
        
        # Set auth URL based on data center
        if self.data_center == 'in':
            self.auth_url = "https://accounts.zoho.in/oauth/v2/token"
        elif self.data_center == 'eu':
            self.auth_url = "https://accounts.zoho.eu/oauth/v2/token"
        elif self.data_center == 'au':
            self.auth_url = "https://accounts.zoho.com.au/oauth/v2/token"
        else:
            self.auth_url = "https://accounts.zoho.com/oauth/v2/token"
        
        # Initialize token table
        self._init_token_table()
    
    def _init_token_table(self):
        """Create token storage table if it doesn't exist."""
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            if db.db_type == 'postgresql':
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS zoho_tokens (
                        id SERIAL PRIMARY KEY,
                        data_center VARCHAR(10) UNIQUE NOT NULL,
                        access_token TEXT,
                        refresh_token TEXT,
                        expires_at TIMESTAMP,
                        last_refresh_at TIMESTAMP,
                        refresh_attempts INTEGER DEFAULT 0,
                        last_error TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            else:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS zoho_tokens (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data_center VARCHAR(10) UNIQUE NOT NULL,
                        access_token TEXT,
                        refresh_token TEXT,
                        expires_at TIMESTAMP,
                        last_refresh_at TIMESTAMP,
                        refresh_attempts INTEGER DEFAULT 0,
                        last_error TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            
            conn.commit()
            conn.close()
            logger.info("✅ Zoho token table initialized")
        except Exception as e:
            logger.error(f"❌ Error initializing token table: {str(e)}")
    
    def getValidAccessToken(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get a valid access token, refreshing if needed.
        Returns: (access_token, error_message)
        """
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            return None, "Missing Zoho credentials"
        
        # Check if we have a valid cached token
        token_data = self._get_stored_token()
        
        if token_data:
            access_token = token_data.get('access_token')
            expires_at = token_data.get('expires_at')
            
            # Check if token is still valid (with 5 minute buffer)
            if access_token and expires_at:
                try:
                    expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if expires_dt.tzinfo is None:
                        expires_dt = expires_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                    
                    # Check if token expires in more than 5 minutes
                    buffer_time = timedelta(minutes=5)
                    if datetime.now(expires_dt.tzinfo) < (expires_dt - buffer_time):
                        logger.debug("✅ Using cached access token")
                        return access_token, None
                except Exception as e:
                    logger.warning(f"⚠️  Error parsing expiry date: {str(e)}")
        
        # Token expired or missing - refresh it
        return self.refreshZohoAccessToken()
    
    def refreshZohoAccessToken(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Refresh Zoho access token with locking and exponential backoff.
        Returns: (access_token, error_message)
        """
        # Check if we should retry (exponential backoff)
        if not self._should_attempt_refresh():
            last_error = self._get_last_error()
            return None, f"Rate limited - {last_error}. Will retry later."
        
        # Acquire lock to prevent parallel refreshes
        if not _refresh_lock.acquire(blocking=False):
            logger.warning("⚠️  Another refresh in progress, waiting...")
            # Wait for lock (max 30 seconds)
            if _refresh_lock.acquire(timeout=30):
                try:
                    # Check if token was refreshed while waiting
                    token_data = self._get_stored_token()
                    if token_data and token_data.get('access_token'):
                        expires_at = token_data.get('expires_at')
                        if expires_at:
                            try:
                                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                                if expires_dt.tzinfo is None:
                                    expires_dt = expires_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
                                buffer_time = timedelta(minutes=5)
                                if datetime.now(expires_dt.tzinfo) < (expires_dt - buffer_time):
                                    logger.info("✅ Token refreshed by another thread")
                                    return token_data.get('access_token'), None
                            except:
                                pass
                finally:
                    _refresh_lock.release()
            else:
                return None, "Timeout waiting for token refresh lock"
        
        try:
            # Perform refresh
            logger.info(f"🔄 Refreshing Zoho access token ({self.data_center})...")
            
            params = {
                'refresh_token': self.refresh_token,
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'refresh_token'
            }
            
            response = requests.post(self.auth_url, params=params, timeout=15)
            
            if response.status_code != 200:
                error_msg = f"Zoho API returned {response.status_code}: {response.text}"
                logger.error(f"❌ {error_msg}")
                self._record_refresh_failure(error_msg)
                return None, error_msg
            
            data = response.json()
            
            if 'error' in data:
                error_code = data.get('error', 'unknown_error')
                error_description = data.get('error_description', '')
                error_msg = f"Zoho error: {error_code} - {error_description}"
                logger.error(f"❌ {error_msg}")
                self._record_refresh_failure(error_msg)
                return None, error_msg
            
            access_token = data.get('access_token')
            expires_in = data.get('expires_in', 3600)  # Default 1 hour
            
            if not access_token:
                error_msg = f"No access token in response: {data}"
                logger.error(f"❌ {error_msg}")
                self._record_refresh_failure(error_msg)
                return None, error_msg
            
            # Calculate expiry time
            expires_at = datetime.now() + timedelta(seconds=expires_in)
            
            # Store token in database
            self._store_token(access_token, expires_at)
            
            logger.info(f"✅ Successfully refreshed Zoho access token (expires in {expires_in}s)")
            return access_token, None
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            logger.error(f"❌ {error_msg}")
            self._record_refresh_failure(error_msg)
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(f"❌ {error_msg}", exc_info=True)
            self._record_refresh_failure(error_msg)
            return None, error_msg
        finally:
            _refresh_lock.release()
    
    def _get_stored_token(self) -> Optional[dict]:
        """Get stored token from database."""
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            if db.db_type == 'postgresql':
                cursor.execute("""
                    SELECT access_token, refresh_token, expires_at, last_refresh_at, 
                           refresh_attempts, last_error
                    FROM zoho_tokens
                    WHERE data_center = %s
                """, (self.data_center,))
            else:
                cursor.execute("""
                    SELECT access_token, refresh_token, expires_at, last_refresh_at, 
                           refresh_attempts, last_error
                    FROM zoho_tokens
                    WHERE data_center = ?
                """, (self.data_center,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                if db.db_type == 'postgresql':
                    return {
                        'access_token': row['access_token'],
                        'refresh_token': row['refresh_token'],
                        'expires_at': row['expires_at'].isoformat() if row['expires_at'] else None,
                        'last_refresh_at': row['last_refresh_at'].isoformat() if row['last_refresh_at'] else None,
                        'refresh_attempts': row['refresh_attempts'],
                        'last_error': row['last_error']
                    }
                else:
                    return {
                        'access_token': row[0],
                        'refresh_token': row[1],
                        'expires_at': row[2].isoformat() if row[2] else None,
                        'last_refresh_at': row[3].isoformat() if row[3] else None,
                        'refresh_attempts': row[4],
                        'last_error': row[5]
                    }
            return None
        except Exception as e:
            logger.error(f"❌ Error getting stored token: {str(e)}")
            return None
    
    def _store_token(self, access_token: str, expires_at: datetime):
        """Store token in database."""
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            if db.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO zoho_tokens 
                    (data_center, access_token, refresh_token, expires_at, last_refresh_at, refresh_attempts, updated_at)
                    VALUES (%s, %s, %s, %s, %s, 0, CURRENT_TIMESTAMP)
                    ON CONFLICT (data_center) 
                    DO UPDATE SET 
                        access_token = EXCLUDED.access_token,
                        refresh_token = EXCLUDED.refresh_token,
                        expires_at = EXCLUDED.expires_at,
                        last_refresh_at = EXCLUDED.last_refresh_at,
                        refresh_attempts = 0,
                        last_error = NULL,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    self.data_center,
                    access_token,
                    self.refresh_token,
                    expires_at,
                    datetime.now()
                ))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO zoho_tokens 
                    (data_center, access_token, refresh_token, expires_at, last_refresh_at, refresh_attempts, updated_at)
                    VALUES (?, ?, ?, ?, ?, 0, CURRENT_TIMESTAMP)
                """, (
                    self.data_center,
                    access_token,
                    self.refresh_token,
                    expires_at,
                    datetime.now()
                ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"❌ Error storing token: {str(e)}")
    
    def _record_refresh_failure(self, error: str):
        """Record refresh failure with attempt count."""
        try:
            conn = db._get_connection()
            cursor = conn.cursor()
            
            if db.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO zoho_tokens 
                    (data_center, refresh_token, refresh_attempts, last_error, last_refresh_at, updated_at)
                    VALUES (%s, %s, 1, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (data_center) 
                    DO UPDATE SET 
                        refresh_attempts = zoho_tokens.refresh_attempts + 1,
                        last_error = EXCLUDED.last_error,
                        last_refresh_at = EXCLUDED.last_refresh_at,
                        updated_at = CURRENT_TIMESTAMP
                """, (self.data_center, self.refresh_token, error))
            else:
                cursor.execute("""
                    INSERT OR REPLACE INTO zoho_tokens 
                    (data_center, refresh_token, refresh_attempts, last_error, last_refresh_at, updated_at)
                    VALUES (?, ?, 
                        COALESCE((SELECT refresh_attempts FROM zoho_tokens WHERE data_center = ?), 0) + 1,
                        ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (self.data_center, self.refresh_token, self.data_center, error))
            
            conn.commit()
            conn.close()
            
            # Track last refresh attempt time
            _last_refresh_attempt[self.data_center] = time.time()
        except Exception as e:
            logger.error(f"❌ Error recording refresh failure: {str(e)}")
    
    def _should_attempt_refresh(self) -> bool:
        """Check if we should attempt refresh (exponential backoff)."""
        token_data = self._get_stored_token()
        
        if not token_data:
            return True  # No previous attempts
        
        attempts = token_data.get('refresh_attempts', 0)
        last_refresh = token_data.get('last_refresh_at')
        
        if attempts == 0:
            return True
        
        if not last_refresh:
            return True
        
        try:
            last_refresh_dt = datetime.fromisoformat(last_refresh.replace('Z', '+00:00'))
            if last_refresh_dt.tzinfo is None:
                last_refresh_dt = last_refresh_dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
            
            elapsed = (datetime.now(last_refresh_dt.tzinfo) - last_refresh_dt).total_seconds()
            
            # Exponential backoff: 60s, 5min, 30min
            if attempts == 1:
                return elapsed >= 60
            elif attempts == 2:
                return elapsed >= 300  # 5 minutes
            elif attempts >= 3:
                return elapsed >= 1800  # 30 minutes
            
            return True
        except:
            return True
    
    def _get_last_error(self) -> str:
        """Get last error message."""
        token_data = self._get_stored_token()
        if token_data:
            return token_data.get('last_error', 'Unknown error')
        return 'Unknown error'


# Global token manager instance (singleton per data center)
_token_managers = {}
_manager_lock = threading.Lock()


def get_token_manager(data_center: str = "in") -> ZohoTokenManager:
    """Get or create token manager for data center."""
    with _manager_lock:
        if data_center not in _token_managers:
            _token_managers[data_center] = ZohoTokenManager(data_center=data_center)
        return _token_managers[data_center]


def getValidZohoAccessToken(data_center: str = "in") -> Tuple[Optional[str], Optional[str]]:
    """
    Get valid Zoho access token (public API).
    Returns: (access_token, error_message)
    """
    manager = get_token_manager(data_center)
    return manager.getValidAccessToken()


def refreshZohoAccessToken(data_center: str = "in") -> Tuple[Optional[str], Optional[str]]:
    """
    Force refresh Zoho access token (public API).
    Returns: (access_token, error_message)
    """
    manager = get_token_manager(data_center)
    return manager.refreshZohoAccessToken()

