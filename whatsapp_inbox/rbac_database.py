"""
RBAC Database Functions
Add these methods to your existing database.py or use as separate module
"""

import json
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class RBACDatabase:
    """
    Role-Based Access Control database methods.
    Extend your existing ContactDatabase class with these methods.
    """
    
    def get_user_permissions(self, user_id: int) -> Dict:
        """
        Get user permissions.
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary of permissions
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT permissions, is_admin, role
                FROM users
                WHERE id = {param_placeholder}
                AND is_active = true
            """
            
            cursor.execute(query, (user_id,))
            row = cursor.fetchone()
            
            if row:
                if self.db_type == 'postgresql':
                    permissions = row['permissions'] or {}
                    is_admin = row['is_admin']
                else:
                    permissions = json.loads(row[0]) if row[0] else {}
                    is_admin = row[1]
                
                # Admins get all permissions
                if is_admin:
                    return {
                        'whatsapp': True,
                        'contacts': True,
                        'campaigns': True,
                        'admin': True
                    }
                
                return permissions
            
            return {}
            
        finally:
            conn.close()
    
    def update_user_permissions(self, user_id: int, permissions: Dict, changed_by: int = None) -> bool:
        """
        Update user permissions.
        
        Args:
            user_id: User ID to update
            permissions: New permissions dictionary
            changed_by: User ID making the change (for audit)
        
        Returns:
            True if successful
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                # Set audit user for trigger
                if changed_by:
                    cursor.execute(f"SET LOCAL app.current_user_id = {changed_by}")
                
                query = """
                    UPDATE users
                    SET permissions = %s::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """
                cursor.execute(query, (json.dumps(permissions), user_id))
            else:
                query = """
                    UPDATE users
                    SET permissions = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """
                cursor.execute(query, (json.dumps(permissions), user_id))
            
            conn.commit()
            logger.info(f"Updated permissions for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating permissions: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def create_user_with_permissions(self, username: str, password: str, full_name: str,
                                     email: str, role: str, permissions: Dict,
                                     created_by: int = None) -> Optional[int]:
        """
        Create new user with permissions.
        
        Args:
            username: Username
            password: Password (will be hashed)
            full_name: Full name
            email: Email address
            role: 'admin' or 'user'
            permissions: Permission dictionary
            created_by: User ID creating this user
        
        Returns:
            New user ID or None if failed
        """
        from werkzeug.security import generate_password_hash
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            password_hash = generate_password_hash(password)
            is_admin = (role == 'admin')
            
            if self.db_type == 'postgresql':
                query = """
                    INSERT INTO users (
                        username, password_hash, full_name, email,
                        role, is_admin, permissions, created_by, is_active
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s::jsonb, %s, true
                    )
                    RETURNING id
                """
                cursor.execute(query, (
                    username, password_hash, full_name, email,
                    role, is_admin, json.dumps(permissions), created_by
                ))
                result = cursor.fetchone()
                user_id = result['id'] if result else None
            else:
                query = """
                    INSERT INTO users (
                        username, password_hash, full_name, email,
                        role, is_admin, permissions, created_by, is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                """
                cursor.execute(query, (
                    username, password_hash, full_name, email,
                    role, is_admin, json.dumps(permissions), created_by
                ))
                user_id = cursor.lastrowid
            
            conn.commit()
            logger.info(f"Created user {username} with role {role}")
            return user_id
            
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            conn.rollback()
            return None
        finally:
            conn.close()
    
    def get_all_users_with_permissions(self) -> List[Dict]:
        """
        Get all users with their permissions decoded.
        
        Returns:
            List of user dictionaries with permissions
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if self.db_type == 'postgresql':
                query = """
                    SELECT 
                        id, username, full_name, email, role, is_admin, is_active,
                        permissions,
                        (permissions->>'whatsapp')::boolean as has_whatsapp_access,
                        (permissions->>'contacts')::boolean as has_contacts_access,
                        (permissions->>'campaigns')::boolean as has_campaigns_access,
                        (permissions->>'admin')::boolean as has_admin_access,
                        created_at, last_login
                    FROM users
                    ORDER BY created_at DESC
                """
            else:
                query = """
                    SELECT 
                        id, username, full_name, email, role, is_admin, is_active,
                        permissions, created_at, last_login
                    FROM users
                    ORDER BY created_at DESC
                """
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            users = []
            for row in rows:
                if self.db_type == 'postgresql':
                    user = dict(row)
                else:
                    user = dict(zip([col[0] for col in cursor.description], row))
                    # Decode permissions for SQLite
                    if user.get('permissions'):
                        perms = json.loads(user['permissions'])
                        user['has_whatsapp_access'] = perms.get('whatsapp', False)
                        user['has_contacts_access'] = perms.get('contacts', False)
                        user['has_campaigns_access'] = perms.get('campaigns', False)
                        user['has_admin_access'] = perms.get('admin', False)
                
                users.append(user)
            
            return users
            
        finally:
            conn.close()
    
    def verify_user_with_permissions(self, username: str, password: str) -> Optional[Dict]:
        """
        Verify user credentials and return user data with permissions.
        
        Args:
            username: Username
            password: Password
        
        Returns:
            User dictionary with permissions or None if invalid
        """
        from werkzeug.security import check_password_hash
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            query = f"""
                SELECT id, username, password_hash, full_name, email, role, is_admin, is_active, permissions
                FROM users
                WHERE username = {param_placeholder}
            """
            
            cursor.execute(query, (username,))
            row = cursor.fetchone()
            
            if not row:
                return None
            
            if self.db_type == 'postgresql':
                user = dict(row)
            else:
                user = dict(zip([col[0] for col in cursor.description], row))
                # Parse JSON permissions for SQLite
                if user.get('permissions'):
                    user['permissions'] = json.loads(user['permissions'])
            
            # Check password
            if not check_password_hash(user['password_hash'], password):
                return None
            
            # Check if active
            if not user.get('is_active'):
                return None
            
            # Update last login
            update_query = f"""
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = {param_placeholder}
            """
            cursor.execute(update_query, (user['id'],))
            conn.commit()
            
            # Remove password hash from returned data
            del user['password_hash']
            
            # Ensure permissions exist
            if not user.get('permissions'):
                user['permissions'] = {}
            
            # Admins get all permissions
            if user.get('is_admin'):
                user['permissions'] = {
                    'whatsapp': True,
                    'contacts': True,
                    'campaigns': True,
                    'admin': True
                }
            
            return user
            
        finally:
            conn.close()
    
    def get_permission_audit_log(self, user_id: int = None, limit: int = 100) -> List[Dict]:
        """
        Get permission change audit log.
        
        Args:
            user_id: Filter by user (optional)
            limit: Max records to return
        
        Returns:
            List of audit records
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            param_placeholder = "%s" if self.db_type == "postgresql" else "?"
            
            if user_id:
                query = f"""
                    SELECT 
                        pal.*,
                        u.username as affected_user,
                        cb.username as changed_by_username
                    FROM permission_audit_log pal
                    LEFT JOIN users u ON u.id = pal.user_id
                    LEFT JOIN users cb ON cb.id = pal.changed_by
                    WHERE pal.user_id = {param_placeholder}
                    ORDER BY pal.changed_at DESC
                    LIMIT {param_placeholder}
                """
                cursor.execute(query, (user_id, limit))
            else:
                query = f"""
                    SELECT 
                        pal.*,
                        u.username as affected_user,
                        cb.username as changed_by_username
                    FROM permission_audit_log pal
                    LEFT JOIN users u ON u.id = pal.user_id
                    LEFT JOIN users cb ON cb.id = pal.changed_by
                    ORDER BY pal.changed_at DESC
                    LIMIT {param_placeholder}
                """
                cursor.execute(query, (limit,))
            
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                log = dict(row) if self.db_type == 'postgresql' else dict(zip([col[0] for col in cursor.description], row))
                logs.append(log)
            
            return logs
            
        finally:
            conn.close()


# Example usage:
# rbac_db = RBACDatabase()
# permissions = rbac_db.get_user_permissions(user_id=5)
# success = rbac_db.update_user_permissions(user_id=5, permissions={'whatsapp': True, 'contacts': False})

