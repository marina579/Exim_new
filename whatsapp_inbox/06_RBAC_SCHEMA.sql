-- ============================================
-- Role-Based Access Control (RBAC) Schema
-- Add to existing database
-- ============================================

-- Update users table with role-based permissions
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('admin', 'user'));

ALTER TABLE users 
ADD COLUMN IF NOT EXISTS permissions JSONB DEFAULT '{"whatsapp": false, "contacts": false}'::jsonb;

-- Example permissions JSON structure:
-- {
--   "whatsapp": true,      -- Access to WhatsApp inbox
--   "contacts": true,      -- Access to contact enrichment
--   "campaigns": false,    -- Access to email campaigns (optional)
--   "admin": false         -- Admin panel access
-- }

-- Update existing admin user with full permissions
UPDATE users 
SET role = 'admin',
    permissions = '{"whatsapp": true, "contacts": true, "campaigns": true, "admin": true}'::jsonb
WHERE username = 'admin';

-- Create index on permissions for faster queries
CREATE INDEX IF NOT EXISTS idx_users_permissions ON users USING gin (permissions);
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);

-- Helper function to check user permission
CREATE OR REPLACE FUNCTION has_permission(user_id INTEGER, permission_key TEXT)
RETURNS BOOLEAN AS $$
BEGIN
    RETURN (
        SELECT COALESCE(
            (permissions->permission_key)::boolean,
            false
        )
        FROM users
        WHERE id = user_id
    );
END;
$$ LANGUAGE plpgsql;

-- Helper function to get user permissions
CREATE OR REPLACE FUNCTION get_user_permissions(username_param VARCHAR)
RETURNS JSONB AS $$
BEGIN
    RETURN (
        SELECT COALESCE(permissions, '{}'::jsonb)
        FROM users
        WHERE username = username_param
        AND is_active = true
    );
END;
$$ LANGUAGE plpgsql;

-- Create view for user list with decoded permissions
CREATE OR REPLACE VIEW v_users_with_permissions AS
SELECT 
    u.id,
    u.username,
    u.full_name,
    u.email,
    u.role,
    u.is_admin,
    u.is_active,
    u.permissions,
    (u.permissions->>'whatsapp')::boolean as has_whatsapp_access,
    (u.permissions->>'contacts')::boolean as has_contacts_access,
    (u.permissions->>'campaigns')::boolean as has_campaigns_access,
    (u.permissions->>'admin')::boolean as has_admin_access,
    u.created_at,
    u.last_login
FROM users u
ORDER BY u.created_at DESC;

-- Audit log for permission changes
CREATE TABLE IF NOT EXISTS permission_audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    changed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    old_permissions JSONB,
    new_permissions JSONB,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_user ON permission_audit_log(user_id);
CREATE INDEX idx_audit_changed_by ON permission_audit_log(changed_by);

-- Function to log permission changes
CREATE OR REPLACE FUNCTION log_permission_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.permissions IS DISTINCT FROM NEW.permissions THEN
        INSERT INTO permission_audit_log (user_id, changed_by, old_permissions, new_permissions)
        VALUES (NEW.id, CURRENT_SETTING('app.current_user_id', true)::INTEGER, OLD.permissions, NEW.permissions);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to log permission changes
DROP TRIGGER IF EXISTS trg_log_permission_change ON users;
CREATE TRIGGER trg_log_permission_change
AFTER UPDATE ON users
FOR EACH ROW
WHEN (OLD.permissions IS DISTINCT FROM NEW.permissions)
EXECUTE FUNCTION log_permission_change();

-- Sample permission sets (optional - for quick setup)
COMMENT ON COLUMN users.permissions IS 'JSON permissions: {"whatsapp": bool, "contacts": bool, "campaigns": bool, "admin": bool}';

-- Quick permission check queries (examples)
-- Check if user has WhatsApp access:
-- SELECT has_permission(user_id, 'whatsapp');

-- Get all users with WhatsApp access:
-- SELECT * FROM v_users_with_permissions WHERE has_whatsapp_access = true;

-- Update user permissions:
-- UPDATE users 
-- SET permissions = jsonb_set(permissions, '{whatsapp}', 'true', true)
-- WHERE username = 'user123';

COMMENT ON TABLE permission_audit_log IS 'Tracks all permission changes for security audit';

