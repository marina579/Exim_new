"""
Role-Based Access Control (RBAC) Middleware
Handles permission checking for routes
"""

from functools import wraps
from flask import session, redirect, url_for, flash, abort
import logging

logger = logging.getLogger(__name__)


def get_user_permissions():
    """
    Get current user's permissions from session.
    
    Returns:
        dict: Permissions dictionary or empty dict if not logged in
    """
    if 'permissions' not in session:
        return {}
    return session.get('permissions', {})


def has_permission(permission_key):
    """
    Check if current user has a specific permission.
    
    Args:
        permission_key: Permission name ('whatsapp', 'contacts', 'campaigns', 'admin')
    
    Returns:
        bool: True if user has permission
    """
    permissions = get_user_permissions()
    
    # Admins have all permissions
    if session.get('is_admin'):
        return True
    
    return permissions.get(permission_key, False)


def require_permission(permission_key, redirect_to='index'):
    """
    Decorator to require specific permission for a route.
    
    Usage:
        @app.route('/whatsapp/inbox')
        @login_required
        @require_permission('whatsapp')
        def whatsapp_inbox():
            ...
    
    Args:
        permission_key: Permission required ('whatsapp', 'contacts', 'campaigns', 'admin')
        redirect_to: Route to redirect to if permission denied
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check if user is logged in
            if 'logged_in' not in session:
                flash('Please login to access this page', 'warning')
                return redirect(url_for('login'))
            
            # Check permission
            if not has_permission(permission_key):
                flash(f'Access denied. You do not have permission to access this feature.', 'error')
                logger.warning(f"User {session.get('username')} denied access to {permission_key}")
                
                # Redirect to appropriate page
                return redirect(url_for(redirect_to))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_admin(f):
    """
    Decorator to require admin role.
    
    Usage:
        @app.route('/admin/users')
        @login_required
        @require_admin
        def admin_users():
            ...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            flash('Please login to access this page', 'warning')
            return redirect(url_for('login'))
        
        if not session.get('is_admin'):
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


def get_accessible_routes():
    """
    Get list of routes accessible to current user based on permissions.
    
    Returns:
        dict: Routes accessible to user
    """
    permissions = get_user_permissions()
    is_admin = session.get('is_admin', False)
    
    routes = {
        'dashboard': True,  # Everyone can access dashboard
        'whatsapp': permissions.get('whatsapp', False) or is_admin,
        'contacts': permissions.get('contacts', False) or is_admin,
        'campaigns': permissions.get('campaigns', False) or is_admin,
        'admin': permissions.get('admin', False) or is_admin,
    }
    
    return routes


# Permission constants
PERMISSION_WHATSAPP = 'whatsapp'
PERMISSION_CONTACTS = 'contacts'
PERMISSION_CAMPAIGNS = 'campaigns'
PERMISSION_ADMIN = 'admin'

# Permission descriptions
PERMISSION_DESCRIPTIONS = {
    'whatsapp': 'Access WhatsApp inbox and reply to messages',
    'contacts': 'Upload files and enrich contacts',
    'campaigns': 'Create and manage email campaigns',
    'admin': 'Manage users and system settings'
}

# Default permission sets
DEFAULT_PERMISSIONS = {
    'admin': {
        'whatsapp': True,
        'contacts': True,
        'campaigns': True,
        'admin': True
    },
    'whatsapp_only': {
        'whatsapp': True,
        'contacts': False,
        'campaigns': False,
        'admin': False
    },
    'contacts_only': {
        'whatsapp': False,
        'contacts': True,
        'campaigns': False,
        'admin': False
    },
    'whatsapp_and_contacts': {
        'whatsapp': True,
        'contacts': True,
        'campaigns': False,
        'admin': False
    },
    'all_except_admin': {
        'whatsapp': True,
        'contacts': True,
        'campaigns': True,
        'admin': False
    }
}


def get_permission_preset(preset_name):
    """
    Get a predefined permission set.
    
    Args:
        preset_name: Name of preset ('admin', 'whatsapp_only', etc.)
    
    Returns:
        dict: Permission dictionary
    """
    return DEFAULT_PERMISSIONS.get(preset_name, {
        'whatsapp': False,
        'contacts': False,
        'campaigns': False,
        'admin': False
    })

