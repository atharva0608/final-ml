-- EMA migration
CREATE TABLE IF NOT EXISTS global_pool_ema (
    pool_key VARCHAR(120) NOT NULL PRIMARY KEY,
    instance_type VARCHAR(60) NOT NULL,
    az VARCHAR(30) NOT NULL,
    region VARCHAR(20) NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    rate NUMERIC(5,2) NOT NULL DEFAULT 0,
    peak_rate NUMERIC(5,2) NOT NULL DEFAULT 0,
    sample_clusters INTEGER NOT NULL DEFAULT 0,
    last_event TIMESTAMP,
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_global_pool_ema_region ON global_pool_ema(region);
CREATE INDEX IF NOT EXISTS idx_global_pool_ema_last_event ON global_pool_ema(last_event);

CREATE TABLE IF NOT EXISTS global_pool_ema_history (
    id SERIAL PRIMARY KEY,
    pool_key VARCHAR(120) NOT NULL,
    rate NUMERIC(5,2) NOT NULL,
    count INTEGER NOT NULL,
    snapshot_at TIMESTAMP DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_global_pool_ema_history_pool_key ON global_pool_ema_history(pool_key);

-- Cluster dismissed + DEGRADED migration
ALTER TABLE clusters ADD COLUMN IF NOT EXISTS is_dismissed BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_clusters_is_dismissed ON clusters(is_dismissed);

-- Update alembic version
UPDATE alembic_version SET version_num = '20260327_cluster_dismissed';
