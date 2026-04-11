-- Create root user for CVAT with password 'postgres'
DO
$$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'root') THEN
      CREATE ROLE root WITH SUPERUSER LOGIN PASSWORD 'postgres';
   ELSE
      ALTER ROLE root WITH PASSWORD 'postgres';
   END IF;
END
$$;

-- Create cvat database owned by root
SELECT 'CREATE DATABASE cvat OWNER root'
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'cvat')\gexec

-- Grant all on visiox_db to root as well (for cross-db introspection if needed)
GRANT ALL PRIVILEGES ON DATABASE visiox_db TO root;
