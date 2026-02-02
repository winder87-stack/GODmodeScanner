
-- Database Reaper Migration Tracking Table
-- Run this on TimescaleDB before starting the Reaper

CREATE TABLE IF NOT EXISTS migrated_profiles (
    wallet_address VARCHAR(44) PRIMARY KEY,
    migrated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_migrated_at ON migrated_profiles(migrated_at);

-- Optional: Create access log table for hot profile tracking
CREATE TABLE IF NOT EXISTS profile_access_log (
    id BIGSERIAL PRIMARY KEY,
    wallet_address VARCHAR(44) NOT NULL,
    accessed_at TIMESTAMPTZ DEFAULT NOW(),
    operation VARCHAR(50),
    INDEX (wallet_address, accessed_at)
);

-- Create index for faster hot profile queries
CREATE INDEX IF NOT EXISTS idx_profile_access_log_wallet_time 
    ON profile_access_log(wallet_address, accessed_at DESC);

-- Optional: Partition access log by time for better performance
-- Uncomment if you have TimescaleDB extension enabled
-- SELECT create_hypertable('profile_access_log', 'accessed_at', 
--     if_not_exists => TRUE);
