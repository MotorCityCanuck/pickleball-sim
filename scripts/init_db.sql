-- Initialize pickleball_sim database
-- This script runs automatically when the PostgreSQL container first starts

-- The database 'pickleball_sim' is already created by POSTGRES_DB env var
-- This script can be used for additional initialization if needed

-- Ensure we're using the correct database
\c pickleball_sim;

-- Create any extensions we might need
-- (We'll add these as needed in the future)

