-- Check what tables actually exist in your database
-- Run this in Railway PostgreSQL Query tab

SELECT 
    table_name,
    table_type
FROM information_schema.tables 
WHERE table_schema = 'public'
ORDER BY table_name;

-- Also check for case-sensitive table names
SELECT 
    tablename as exact_table_name
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY tablename;

