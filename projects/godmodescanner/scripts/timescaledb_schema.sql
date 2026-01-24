-- TimescaleDB Schema for GODMODESCANNER Historical Data & Trend Analysis
-- This schema enables time-series analysis of token launches, trades, wallet behavior, and alerts

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS timescaledb_toolkit;

-- ========== TIME-SERIES TABLES ==========

-- 1. Token Launch Events (HyperTable with 1-day chunking)
CREATE TABLE IF NOT EXISTS token_launches (
    time TIMESTAMPTZ NOT NULL,
    token_address VARCHAR(44) NOT NULL,
    mint_address VARCHAR(44) NOT NULL,
    creator_address VARCHAR(44) NOT NULL,
    name VARCHAR(50),
    symbol VARCHAR(10),
    initial_liquidity DECIMAL(20, 9),
    initial_price DECIMAL(20, 18),
    launch_timestamp INT,
    metadata JSONB,
    PRIMARY KEY (time, token_address)
);
SELECT create_hypertable('token_launches', 'time', chunk_time_interval => INTERVAL '1 day');

-- Token launch indexes
CREATE INDEX IF NOT EXISTS idx_token_launches_token ON token_launches (token_address);
CREATE INDEX IF NOT EXISTS idx_token_launches_creator ON token_launches (creator_address);
CREATE INDEX IF NOT EXISTS idx_token_launches_time ON token_launches (time DESC);

-- 2. Trade Events (HyperTable)
CREATE TABLE IF NOT EXISTS trades (
    time TIMESTAMPTZ NOT NULL,
    token_address VARCHAR(44) NOT NULL,
    wallet_address VARCHAR(44) NOT NULL,
    signature VARCHAR(88) NOT NULL,
    trade_type VARCHAR(10),  -- 'buy' or 'sell'
    amount_sol DECIMAL(20, 9),
    amount_token DECIMAL(20, 18),
    price DECIMAL(20, 18),
    timestamp_ms BIGINT,
    PRIMARY KEY (time, signature)
);
SELECT create_hypertable('trades', 'time', chunk_time_interval => INTERVAL '1 hour');

CREATE INDEX IF NOT EXISTS idx_trades_token ON trades (token_address);
CREATE INDEX IF NOT EXISTS idx_trades_wallet ON trades (wallet_address);
CREATE INDEX IF NOT EXISTS idx_trades_time ON trades (time DESC);

-- 3. Wallet Behavior Profiles (Time-series of wallet activities)
CREATE TABLE IF NOT EXISTS wallet_behavior (
    time TIMESTAMPTZ NOT NULL,
    wallet_address VARCHAR(44) NOT NULL,
    activity_count INT,
    total_volume_sol DECIMAL(20, 9),
    total_profit_sol DECIMAL(20, 9),
    win_rate DECIMAL(5, 4),
    avg_holding_time_seconds INT,
    early_buy_count INT,
    coordinated_trades_count INT,
    reputation_score DECIMAL(5, 4),
    risk_score DECIMAL(5, 4),
    PRIMARY KEY (time, wallet_address)
);
SELECT create_hypertable('wallet_behavior', 'time', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX IF NOT EXISTS idx_wallet_behavior_wallet ON wallet_behavior (wallet_address);

-- 4. Risk Scores (Historical tracking for trend analysis)
CREATE TABLE IF NOT EXISTS risk_scores (
    time TIMESTAMPTZ NOT NULL,
    token_address VARCHAR(44),
    wallet_address VARCHAR(44),
    risk_score DECIMAL(5, 4),
    risk_level VARCHAR(20),
    confidence_lower DECIMAL(5, 4),
    confidence_upper DECIMAL(5, 4),
    evidence_count INT,
    factor_scores JSONB,  -- Stores individual factor scores
    PRIMARY KEY (time, token_address, wallet_address)
);
SELECT create_hypertable('risk_scores', 'time', chunk_time_interval => INTERVAL '1 hour');

CREATE INDEX IF NOT EXISTS idx_risk_scores_token ON risk_scores (token_address);
CREATE INDEX IF NOT EXISTS idx_risk_scores_wallet ON risk_scores (wallet_address);

-- 5. Alert History
CREATE TABLE IF NOT EXISTS alert_history (
    time TIMESTAMPTZ NOT NULL,
    alert_id UUID NOT NULL,
    alert_type VARCHAR(50),
    priority VARCHAR(20),
    token_address VARCHAR(44),
    wallet_address VARCHAR(44),
    risk_score DECIMAL(5, 4),
    message TEXT,
    channels JSONB,  -- Delivery channels used
    delivery_status JSONB,  -- Success/failure per channel
    PRIMARY KEY (time, alert_id)
);
SELECT create_hypertable('alert_history', 'time', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX IF NOT EXISTS idx_alert_history_type ON alert_history (alert_type);
CREATE INDEX IF NOT EXISTS idx_alert_history_priority ON alert_history (priority);

-- 6. Pattern Detection Events
CREATE TABLE IF NOT EXISTS pattern_events (
    time TIMESTAMPTZ NOT NULL,
    event_id UUID NOT NULL,
    pattern_type VARCHAR(50),  -- 'coordinated', 'wash_trade', 'sybil', 'bundler', 'insider'
    token_address VARCHAR(44),
    wallet_addresses VARCHAR(44)[],
    confidence DECIMAL(5, 4),
    metadata JSONB,
    PRIMARY KEY (time, event_id)
);
SELECT create_hypertable('pattern_events', 'time', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX IF NOT EXISTS idx_pattern_events_type ON pattern_events (pattern_type);
CREATE INDEX IF NOT EXISTS idx_pattern_events_token ON pattern_events (token_address);

-- 7. Sybil Cluster Graph (for network analysis)
CREATE TABLE IF NOT EXISTS sybil_graph (
    time TIMESTAMPTZ NOT NULL,
    cluster_id UUID NOT NULL,
    node_a VARCHAR(44) NOT NULL,
    node_b VARCHAR(44) NOT NULL,
    edge_weight DECIMAL(5, 4),
    common_funding_source VARCHAR(44),
    confidence DECIMAL(5, 4),
    PRIMARY KEY (time, cluster_id, node_a, node_b)
);
SELECT create_hypertable('sybil_graph', 'time', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX IF NOT EXISTS idx_sybil_graph_cluster ON sybil_graph (cluster_id);
CREATE INDEX IF NOT EXISTS idx_sybil_graph_nodes ON sybil_graph (node_a, node_b);

-- ========== CONTINUOUS AGGREGATES FOR TREND ANALYSIS ==========

-- Hourly token risk trends
CREATE MATERIALIZED VIEW IF NOT EXISTS token_risk_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS hour,
    token_address,
    AVG(risk_score) as avg_risk,
    MAX(risk_score) as max_risk,
    COUNT(*) as sample_count
FROM risk_scores
WHERE token_address IS NOT NULL
GROUP BY hour, token_address
WITH NO DATA;

-- Daily wallet activity trends
CREATE MATERIALIZED VIEW IF NOT EXISTS wallet_activity_daily
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 day', time) AS day,
    wallet_address,
    SUM(activity_count) as total_activities,
    AVG(risk_score) as avg_risk,
    SUM(total_volume_sol) as total_volume
FROM wallet_behavior
GROUP BY day, wallet_address
WITH NO DATA;

-- Hourly alert rates
CREATE MATERIALIZED VIEW IF NOT EXISTS alert_rates_hourly
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', time) AS hour,
    alert_type,
    priority,
    COUNT(*) as alert_count
FROM alert_history
GROUP BY hour, alert_type, priority
WITH NO DATA;

-- ========== RETENTION POLICIES ==========

-- Keep 30 days of raw data
SELECT add_retention_policy('token_launches', INTERVAL '30 days');
SELECT add_retention_policy('trades', INTERVAL '7 days');
SELECT add_retention_policy('wallet_behavior', INTERVAL '30 days');
SELECT add_retention_policy('risk_scores', INTERVAL '14 days');
SELECT add_retention_policy('alert_history', INTERVAL '60 days');
SELECT add_retention_policy('pattern_events', INTERVAL '30 days');
SELECT add_retention_policy('sybil_graph', INTERVAL '30 days');

-- Keep 90 days of aggregated data
SELECT add_retention_policy('token_risk_hourly', INTERVAL '90 days');
SELECT add_retention_policy('wallet_activity_daily', INTERVAL '90 days');
SELECT add_retention_policy('alert_rates_hourly', INTERVAL '90 days');

-- ========== ANALYTICS FUNCTIONS ==========

-- Function to calculate trend direction for a token
CREATE OR REPLACE FUNCTION calculate_token_trend(
    p_token_address VARCHAR(44),
    p_hours INT DEFAULT 24
)
RETURNS TABLE(
    trend_direction VARCHAR(20),
    trend_strength DECIMAL(5, 4),
    change_percent DECIMAL(5, 2),
    avg_risk DECIMAL(5, 4)
) AS $$
BEGIN
    RETURN QUERY
    WITH recent_scores AS (
        SELECT 
            risk_score,
            time
        FROM risk_scores
        WHERE token_address = p_token_address
          AND time >= NOW() - INTERVAL '1 hour' * p_hours
        ORDER BY time
    ),
    trend_calc AS (
        SELECT
            (SELECT risk_score FROM recent_scores ORDER BY time DESC LIMIT 1) as current_risk,
            (SELECT risk_score FROM recent_scores ORDER BY time ASC LIMIT 1) as initial_risk,
            (SELECT AVG(risk_score) FROM recent_scores) as avg_risk_val,
            ((SELECT risk_score FROM recent_scores ORDER BY time DESC LIMIT 1) - 
             (SELECT risk_score FROM recent_scores ORDER BY time ASC LIMIT 1)) as risk_change
    )
    SELECT
        CASE WHEN risk_change > 0 THEN 'increasing'::VARCHAR
             WHEN risk_change < 0 THEN 'decreasing'::VARCHAR
             ELSE 'stable'::VARCHAR
        END as trend_direction,
        ABS(risk_change) / NULLIF(avg_risk_val, 0) as trend_strength,
        (risk_change / NULLIF((SELECT initial_risk FROM trend_calc), 0)) * 100 as change_percent,
        avg_risk_val as avg_risk
    FROM trend_calc;
END;
$$ LANGUAGE plpgsql;

-- Function to identify emerging high-risk tokens
CREATE OR REPLACE FUNCTION find_emerging_risks(
    p_lookback_hours INT DEFAULT 6,
    p_min_risk DECIMAL(5, 4) DEFAULT 0.60
)
RETURNS TABLE(
    token_address VARCHAR(44),
    current_risk DECIMAL(5, 4),
    risk_increase DECIMAL(5, 4),
    sample_size INT,
    confidence DECIMAL(5, 2)
) AS $$
BEGIN
    RETURN QUERY
    WITH recent_risks AS (
        SELECT 
            token_address,
            risk_score,
            time,
            LAG(risk_score) OVER (PARTITION BY token_address ORDER BY time) as prev_risk
        FROM risk_scores
        WHERE token_address IS NOT NULL
          AND time >= NOW() - INTERVAL '1 hour' * p_lookback_hours
    ),
    risk_changes AS (
        SELECT
            token_address,
            risk_score as current_risk,
            risk_score - COALESCE(prev_risk, risk_score) as risk_increase,
            COUNT(*) as sample_size
        FROM recent_risks
        WHERE risk_score >= p_min_risk
        GROUP BY token_address, risk_score
        HAVING COUNT(*) >= 2
    )
    SELECT
        token_address,
        MAX(current_risk) as current_risk,
        AVG(risk_increase) as risk_increase,
        sample_size,
        CASE WHEN sample_size >= 5 THEN 95.00
             WHEN sample_size >= 3 THEN 80.00
             ELSE 60.00
        END as confidence
    FROM risk_changes
    WHERE risk_increase > 0.05  -- At least 5% increase
    GROUP BY token_address, sample_size
    ORDER BY current_risk DESC, risk_increase DESC
    LIMIT 20;
END;
$$ LANGUAGE plpgsql;

-- Function to get wallet risk trend
CREATE OR REPLACE FUNCTION get_wallet_risk_trend(
    p_wallet_address VARCHAR(44),
    p_days INT DEFAULT 7
)
RETURNS TABLE(
    day DATE,
    avg_risk DECIMAL(5, 4),
    max_risk DECIMAL(5, 4),
    activity_count BIGINT,
    trend VARCHAR(20)
) AS $$
BEGIN
    RETURN QUERY
    WITH daily_risks AS (
        SELECT
            DATE(time) as day,
            AVG(risk_score) as avg_risk,
            MAX(risk_score) as max_risk,
            COUNT(*) as activity_count
        FROM risk_scores
        WHERE wallet_address = p_wallet_address
          AND time >= NOW() - INTERVAL '1 day' * p_days
          AND wallet_address IS NOT NULL
        GROUP BY DATE(time)
        ORDER BY day
    ),
    trend_calc AS (
        SELECT
            avg_risk,
            LAG(avg_risk) OVER (ORDER BY day) as prev_risk
        FROM daily_risks
    )
    SELECT
        d.day,
        d.avg_risk,
        d.max_risk,
        d.activity_count,
        CASE WHEN t.avg_risk > t.prev_risk THEN 'increasing'
             WHEN t.avg_risk < t.prev_risk THEN 'decreasing'
             ELSE 'stable'
        END as trend
    FROM daily_risks d
    LEFT JOIN trend_calc t ON d.day = (SELECT day FROM daily_risks ORDER BY day DESC LIMIT 1)  -- Simplified
    ORDER BY d.day DESC;
END;
$$ LANGUAGE plpgsql;

-- ========== DATA QUALITY & MONITORING ==========

-- Insert a check to ensure hypertables are created
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE table_name = 'token_launches') THEN
        RAISE NOTICE 'Token launches hypertable creation failed';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM timescaledb_information.hypertables WHERE table_name = 'trades') THEN
        RAISE NOTICE 'Trades hypertable creation failed';
    END IF;
END $$;

-- Print success message
RAISE NOTICE 'GODMODESCANNER TimescaleDB schema initialized successfully!';
RAISE NOTICE 'Available hypertables: token_launches, trades, wallet_behavior, risk_scores, alert_history, pattern_events, sybil_graph';
RAISE NOTICE 'Available analytics functions: calculate_token_trend, find_emerging_risks, get_wallet_risk_trend';
RAISE NOTICE 'Available materialized views: token_risk_hourly, wallet_activity_daily, alert_rates_hourly';

