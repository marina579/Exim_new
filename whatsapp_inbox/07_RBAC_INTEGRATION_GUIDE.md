# 🔐 Role-Based Access Control (RBAC) Integration Guide

## Complete Guide for Adding Permission-Based User Management

---

## 📦 What This Adds

### **User Roles:**
- **Admin** - Full access to everything
- **User** - Custom permissions

### **Permissions:**
- ✅ **WhatsApp Access** - View/reply to WhatsApp messages
- ✅ **Contacts Access** - Upload files & enrich contacts  
- ✅ **Campaigns Access** - Create/manage email campaigns
- ✅ **Admin Access** - User management & settings

### **Permission Combinations:**
- WhatsApp Only
- Contacts Only
- Both WhatsApp + Contacts
- All except Admin
- Full Admin Access

---

## 🚀 Integration Steps

### **STEP 1: Run Database Schema** (2 min)

```bash
# Connect to Railway PostgreSQL
psql $DATABASE_URL < whatsapp_inbox/06_RBAC_SCHEMA.sql
```

This adds:
- `role` column to users table
- `permissions` JSONB column
- Permission audit log table
- Helper functions

---

### **STEP 2: Copy Files** (1 min)

```bash
cd /Users/sai/Documents/GitHub/Exim_new

# Copy RBAC modules
cp whatsapp_inbox/rbac_middleware.py ./
cp whatsapp_inbox/rbac_database.py ./

# Copy updated admin template
cp whatsapp_inbox/templates/admin_users_rbac.html ./templates/
```

---

### **STEP 3: Update database.py** (5 min)

Add RBAC methods to your existing `database.py`:

```python
# At the top, import RBAC methods
from rbac_database import RBACDatabase

# Make your ContactDatabase inherit from RBACDatabase
class ContactDatabase(RBACDatabase):
    """Manages contact storage and duplicate detection."""
    
    def __init__(self):
        """Initialize database connection."""
        self.db_type = DB_TYPE
        self._init_database()
    
    # ... your existing methods ...

# Now you have all RBAC methods available!
# db.get_user_permissions(user_id)
# db.update_user_permissions(user_id, permissions)
# etc.
```

**Or** if you prefer to keep them separate, you can use rbac_database.py as a standalone module.

---

### **STEP 4: Update Login Process** (10 min)

#### **In app_with_auth.py:**

```python
# Add import at top
from rbac_middleware import require_permission, require_admin, has_permission, get_accessible_routes
from rbac_database import RBACDatabase

# Initialize RBAC database
rbac_db = RBACDatabase()

# Update login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page with RBAC."""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        # Use RBAC-enabled verification
        user = rbac_db.verify_user_with_permissions(username, password)
        
        if user:
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['is_admin'] = user['is_admin']
            session['role'] = user['role']
            session['permissions'] = user['permissions']  # ← ADD THIS
            session['login_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            flash(f'Welcome back, {user["full_name"] or username}!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')
```

---

### **STEP 5: Add Admin Routes** (10 min)

```python
# Add to app_with_auth.py

@app.route('/admin/users-rbac')
@login_required
@require_admin
def admin_users_rbac():
    """Admin panel for user management with RBAC."""
    users = rbac_db.get_all_users_with_permissions()
    return render_template('admin_users_rbac.html', 
                          users=users, 
                          username=session.get('username'))

@app.route('/admin/users/create-rbac', methods=['POST'])
@login_required
@require_admin
def admin_create_user_rbac():
    """Create user with permissions."""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip()
    role = request.form.get('role', 'user')
    
    # Build permissions from form
    if role == 'admin':
        permissions = {
            'whatsapp': True,
            'contacts': True,
            'campaigns': True,
            'admin': True
        }
    else:
        permissions = {
            'whatsapp': request.form.get('permission_whatsapp') == 'on',
            'contacts': request.form.get('permission_contacts') == 'on',
            'campaigns': request.form.get('permission_campaigns') == 'on',
            'admin': request.form.get('permission_admin') == 'on'
        }
    
    user_id = rbac_db.create_user_with_permissions(
        username=username,
        password=password,
        full_name=full_name,
        email=email,
        role=role,
        permissions=permissions,
        created_by=session.get('user_id')
    )
    
    if user_id:
        flash(f'User "{username}" created successfully!', 'success')
    else:
        flash('Failed to create user. Username may already exist.', 'error')
    
    return redirect(url_for('admin_users_rbac'))

@app.route('/admin/users/update-rbac', methods=['POST'])
@login_required
@require_admin
def admin_update_user_rbac():
    """Update user permissions."""
    user_id = request.form.get('user_id')
    full_name = request.form.get('full_name', '')
    email = request.form.get('email', '')
    role = request.form.get('role', 'user')
    
    # Build permissions
    if role == 'admin':
        permissions = {
            'whatsapp': True,
            'contacts': True,
            'campaigns': True,
            'admin': True
        }
    else:
        permissions = {
            'whatsapp': request.form.get('permission_whatsapp') == 'on',
            'contacts': request.form.get('permission_contacts') == 'on',
            'campaigns': request.form.get('permission_campaigns') == 'on',
            'admin': request.form.get('permission_admin') == 'on'
        }
    
    # Update permissions
    success = rbac_db.update_user_permissions(
        user_id=int(user_id),
        permissions=permissions,
        changed_by=session.get('user_id')
    )
    
    if success:
        flash('User updated successfully!', 'success')
    else:
        flash('Failed to update user.', 'error')
    
    return redirect(url_for('admin_users_rbac'))

@app.route('/admin/users/deactivate/<int:user_id>')
@login_required
@require_admin
def admin_deactivate_user(user_id):
    """Deactivate a user."""
    # Add your deactivation logic here
    # (already exists in your database.py)
    
    flash('User deactivated successfully!', 'success')
    return redirect(url_for('admin_users_rbac'))
```

---

### **STEP 6: Protect Routes with Permissions** (5 min)

#### **Protect WhatsApp Routes:**

```python
# Update whatsapp_routes.py
from rbac_middleware import require_permission

@app.route('/whatsapp/inbox')
@login_required
@require_permission('whatsapp')  # ← ADD THIS
def whatsapp_inbox():
    """WhatsApp inbox - requires WhatsApp permission."""
    # ... existing code ...

@app.route('/whatsapp/conversation/<conversation_id>')
@login_required
@require_permission('whatsapp')  # ← ADD THIS
def whatsapp_conversation(conversation_id):
    """Chat view - requires WhatsApp permission."""
    # ... existing code ...
```

#### **Protect Contact Enrichment Routes:**

```python
# In app_with_auth.py
from rbac_middleware import require_permission

@app.route('/')
@login_required
@require_permission('contacts')  # ← ADD THIS
def index():
    """Dashboard - upload contacts."""
    # ... existing code ...

@app.route('/upload', methods=['POST'])
@login_required
@require_permission('contacts')  # ← ADD THIS
def upload_file():
    """File upload - requires contacts permission."""
    # ... existing code ...
```

#### **Protect Campaign Routes:**

```python
@app.route('/campaigns')
@login_required
@require_permission('campaigns')  # ← ADD THIS
def campaigns():
    """Campaigns page."""
    # ... existing code ...
```

---

### **STEP 7: Update Navbar** (3 min)

Update your navbar to show/hide links based on permissions:

```html
<!-- In your navbar template -->
<nav class="navbar navbar-expand-lg navbar-dark bg-dark">
    <div class="container-fluid">
        <a class="navbar-brand" href="/">Marineco AI Labs</a>
        <div class="navbar-nav">
            {% if session.permissions.contacts or session.is_admin %}
            <a class="nav-link" href="/">
                <i class="fas fa-address-book"></i> Contacts
            </a>
            {% endif %}
            
            {% if session.permissions.whatsapp or session.is_admin %}
            <a class="nav-link" href="/whatsapp/inbox">
                <i class="fab fa-whatsapp"></i> WhatsApp
            </a>
            {% endif %}
            
            {% if session.permissions.campaigns or session.is_admin %}
            <a class="nav-link" href="/campaigns">
                <i class="fas fa-envelope"></i> Campaigns
            </a>
            {% endif %}
            
            {% if session.is_admin %}
            <a class="nav-link" href="/admin/users-rbac">
                <i class="fas fa-users"></i> Users
            </a>
            {% endif %}
        </div>
        <!-- ... rest of navbar ... -->
    </div>
</nav>
```

---

### **STEP 8: Deploy** (2 min)

```bash
git add .
git commit -m "Add role-based access control (RBAC)"
git push origin main
```

Railway will auto-deploy.

---

## ✅ Testing

### **1. Login as Admin**
```
Username: admin
Password: admin123
```

Should see all features.

### **2. Create Test Users**

Go to: `/admin/users-rbac`

**User 1: WhatsApp Only**
- Username: `whatsapp_agent`
- Password: `test123`
- Permissions: ✅ WhatsApp only

**User 2: Contacts Only**
- Username: `contacts_agent`
- Password: `test123`
- Permissions: ✅ Contacts only

**User 3: Both**
- Username: `full_agent`
- Password: `test123`
- Permissions: ✅ WhatsApp + ✅ Contacts

### **3. Test Access**

**Login as `whatsapp_agent`:**
- ✅ Can access /whatsapp/inbox
- ❌ Cannot access / (contacts)
- ❌ Cannot access /admin

**Login as `contacts_agent`:**
- ✅ Can access / (contacts)
- ❌ Cannot access /whatsapp/inbox
- ❌ Cannot access /admin

**Login as `full_agent`:**
- ✅ Can access both
- ❌ Cannot access /admin

---

## 🎯 Permission Matrix

| User Type | WhatsApp | Contacts | Campaigns | Admin |
|-----------|----------|----------|-----------|-------|
| **Admin** | ✅ | ✅ | ✅ | ✅ |
| **WhatsApp Only** | ✅ | ❌ | ❌ | ❌ |
| **Contacts Only** | ❌ | ✅ | ❌ | ❌ |
| **WhatsApp + Contacts** | ✅ | ✅ | ❌ | ❌ |
| **All Except Admin** | ✅ | ✅ | ✅ | ❌ |

---

## 🔒 Security Features

### **Audit Log:**
Every permission change is logged:
```sql
SELECT * FROM permission_audit_log
WHERE user_id = 5
ORDER BY changed_at DESC;
```

### **Permission Checks:**
```python
# In your code
from rbac_middleware import has_permission

if has_permission('whatsapp'):
    # Show WhatsApp features
    pass

if has_permission('contacts'):
    # Show contact features
    pass
```

### **Session Storage:**
Permissions stored in session after login - no database query on every request.

---

## 📊 Admin Panel Features

### **User Management UI:**
- ✅ Create users with custom permissions
- ✅ Edit existing user permissions
- ✅ Quick permission presets
- ✅ Visual permission badges
- ✅ Deactivate users
- ✅ View user statistics
- ✅ See last login times

### **Quick Presets:**
- **WhatsApp Only** - Only WhatsApp access
- **Contacts Only** - Only contact enrichment
- **Both** - WhatsApp + Contacts
- **All Access** - Everything except admin

---

## 🆘 Troubleshooting

### **"Access denied" message:**
- Check user permissions in admin panel
- Verify session has 'permissions' key
- Check decorator order (login_required BEFORE require_permission)

### **Permissions not working after login:**
- Clear browser cache/cookies
- Re-login to refresh session
- Check database permissions column

### **Admin can't access features:**
- Verify `is_admin = true` in database
- Check `@require_admin` decorator is used
- Admins always have all permissions

---

## 📝 Code Examples

### **Check Permission in Template:**
```html
{% if session.permissions.whatsapp or session.is_admin %}
    <button>Send WhatsApp</button>
{% endif %}
```

### **Check Permission in Python:**
```python
from rbac_middleware import has_permission

if has_permission('whatsapp'):
    # User has WhatsApp access
    pass
```

### **Get All Accessible Routes:**
```python
from rbac_middleware import get_accessible_routes

routes = get_accessible_routes()
# {'dashboard': True, 'whatsapp': True, 'contacts': False, ...}
```

---

## 🎨 Customization

### **Add New Permission:**

1. Update DEFAULT_PERMISSIONS in `rbac_middleware.py`:
```python
PERMISSION_REPORTS = 'reports'
PERMISSION_DESCRIPTIONS['reports'] = 'View analytics and reports'
```

2. Add to database schema:
```sql
-- Users will have: {"whatsapp": bool, "contacts": bool, "reports": bool}
```

3. Protect routes:
```python
@app.route('/reports')
@login_required
@require_permission('reports')
def reports():
    pass
```

4. Add to admin UI checkboxes in template.

---

## ✅ Integration Checklist

- [ ] Database schema executed (06_RBAC_SCHEMA.sql)
- [ ] Files copied (rbac_middleware.py, rbac_database.py)
- [ ] database.py updated to include RBAC methods
- [ ] Login process updated to load permissions
- [ ] Admin routes added
- [ ] Routes protected with @require_permission
- [ ] Navbar updated to show/hide based on permissions
- [ ] Admin template copied (admin_users_rbac.html)
- [ ] Deployed to Railway
- [ ] Tested all permission combinations
- [ ] Created test users
- [ ] Verified access restrictions work

---

## 🚀 Done!

You now have complete role-based access control:

✅ **Admin can:**
- Create users with custom permissions
- Grant/revoke access to features
- View audit logs
- Manage all users

✅ **Users can:**
- Only access features they have permission for
- See only relevant navbar links
- Get clear "Access denied" messages

✅ **System provides:**
- Audit trail of permission changes
- Session-based performance
- Flexible permission combinations
- Easy to add new permissions

---

**Next:** Customize permissions for your team structure!

