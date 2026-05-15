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

-- WIE v4.3 migration (009_add_workload_classifications)
CREATE TABLE IF NOT EXISTS workload_classifications (
    id                  VARCHAR(36)     PRIMARY KEY,
    cluster_id          VARCHAR(36)     NOT NULL
        REFERENCES clusters(id) ON DELETE CASCADE,
    workload_id         VARCHAR(512)    NOT NULL,
    namespace           VARCHAR(253)    NOT NULL,
    name                VARCHAR(253)    NOT NULL,
    controller_kind     VARCHAR(50)     NOT NULL,

    role                VARCHAR(20)     NOT NULL,
    criticality_score   INTEGER         NOT NULL,
    tier                VARCHAR(20)     NOT NULL,
    spot_score          INTEGER         NOT NULL,
    spot_friendly       BOOLEAN         NOT NULL,
    confidence_score    INTEGER         NOT NULL,
    confidence_state    VARCHAR(20)     NOT NULL,
    data_safety         VARCHAR(20)     NOT NULL,

    signals_fired       JSONB           NOT NULL DEFAULT '[]',
    override_active     BOOLEAN         NOT NULL DEFAULT FALSE,
    override_reason     VARCHAR(512),
    input_hash          VARCHAR(100)    NOT NULL DEFAULT '',
    schema_version      VARCHAR(10)     NOT NULL DEFAULT '4.3',

    classified_at       TIMESTAMP       NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
    ALTER TABLE workload_classifications
        ADD CONSTRAINT uq_workload_classification_cluster_workload
            UNIQUE (cluster_id, workload_id);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS ix_wc_cluster_tier
    ON workload_classifications (cluster_id, tier);
CREATE INDEX IF NOT EXISTS ix_wc_cluster_confidence
    ON workload_classifications (cluster_id, confidence_state);
CREATE INDEX IF NOT EXISTS ix_wc_cluster_spot
    ON workload_classifications (cluster_id, spot_friendly, confidence_state);
CREATE INDEX IF NOT EXISTS ix_wc_workload_id
    ON workload_classifications (workload_id);
