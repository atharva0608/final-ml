-- Lab Mode Database Schema
-- Real execution on single instances with simplified pipeline

-- ============================================================================
-- 1. Account Environment Types
-- ============================================================================

-- Add environment flag to track account types
ALTER TABLE IF EXISTS accounts
ADD COLUMN IF NOT EXISTS environment_type VARCHAR(20) DEFAULT 'PRODUCTION';
-- Values: 'PRODUCTION', 'LAB_INTERNAL'

COMMENT ON COLUMN accounts.environment_type IS 'Environment type: PRODUCTION (full pipeline) or LAB_INTERNAL (simplified pipeline)';

-- ============================================================================
-- 2. Model Registry (Version Control for AI Models)
-- ============================================================================

CREATE TABLE IF NOT EXISTS model_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) NOT NULL,           -- e.g., "FamilyStressPredictor"
    version VARCHAR(20) NOT NULL,        -- e.g., "v2.1.0-beta"
    s3_path VARCHAR(255),                -- Location of .pkl file
    local_path VARCHAR(255),             -- Local file path (alternative to S3)
    description TEXT,                    -- Model description
    is_experimental BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by UUID,                     -- User who registered the model

    UNIQUE(name, version)
);

COMMENT ON TABLE model_registry IS 'Registry of ML model versions for experimentation';

-- Index for active models
CREATE INDEX IF NOT EXISTS idx_model_registry_active
ON model_registry(is_active, created_at DESC);

-- ============================================================================
-- 3. Instance Configuration (Override Table)
-- ============================================================================

-- This tells the backend: "For Instance X, use Model Y"
CREATE TABLE IF NOT EXISTS instance_config (
    instance_id VARCHAR(50) PRIMARY KEY,
    account_id UUID,                    -- References accounts(id) if accounts table exists

    -- PIPELINE CONFIG
    pipeline_mode VARCHAR(20) DEFAULT 'CLUSTER_FULL',  -- 'CLUSTER_FULL' or 'SINGLE_LINEAR'

    -- MODEL ASSIGNMENT
    assigned_model_id UUID REFERENCES model_registry(id),

    -- FEATURE FLAGS (Disable specific steps for Lab Mode)
    enable_bin_packing BOOLEAN DEFAULT TRUE,
    enable_right_sizing BOOLEAN DEFAULT TRUE,
    enable_family_stress BOOLEAN DEFAULT TRUE,

    -- REGION CONFIG
    aws_region VARCHAR(20) DEFAULT 'ap-south-1',

    -- TIMESTAMPS
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE instance_config IS 'Per-instance pipeline configuration for Lab Mode';
COMMENT ON COLUMN instance_config.pipeline_mode IS 'CLUSTER_FULL: full production pipeline, SINGLE_LINEAR: simplified Lab pipeline';

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_instance_config_mode
ON instance_config(pipeline_mode);

CREATE INDEX IF NOT EXISTS idx_instance_config_model
ON instance_config(assigned_model_id)
WHERE assigned_model_id IS NOT NULL;

-- ============================================================================
-- 4. Experiment Logs (Audit Trail for R&D)
-- ============================================================================

CREATE TABLE IF NOT EXISTS experiment_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id VARCHAR(50) NOT NULL,
    model_id UUID REFERENCES model_registry(id),
    model_version VARCHAR(20),

    -- PREDICTION DATA
    prediction_score FLOAT,              -- Risk score from ML model
    decision VARCHAR(50),                -- 'SWITCH', 'HOLD', 'FAILED'

    -- EXECUTION DATA
    execution_time TIMESTAMP DEFAULT NOW(),
    execution_duration_ms INTEGER,       -- How long the pipeline took

    -- RESULT DATA
    candidates_evaluated INTEGER,        -- Number of spot pools evaluated
    selected_instance_type VARCHAR(20),  -- Target instance type
    selected_availability_zone VARCHAR(20),
    spot_price DECIMAL(10, 6),
    on_demand_price DECIMAL(10, 6),
    projected_savings DECIMAL(10, 4),

    -- ERROR TRACKING
    error_message TEXT,

    -- METADATA
    pipeline_mode VARCHAR(20),
    metadata JSONB                       -- Flexible field for additional data
);

COMMENT ON TABLE experiment_logs IS 'Audit trail for Lab Mode experiments and model predictions';

-- Indexes for analytics
CREATE INDEX IF NOT EXISTS idx_experiment_logs_instance
ON experiment_logs(instance_id, execution_time DESC);

CREATE INDEX IF NOT EXISTS idx_experiment_logs_model
ON experiment_logs(model_id, execution_time DESC);

CREATE INDEX IF NOT EXISTS idx_experiment_logs_decision
ON experiment_logs(decision, execution_time DESC);

-- ============================================================================
-- 5. Sample Data (For Testing)
-- ============================================================================

-- Register default production model
INSERT INTO model_registry (id, name, version, local_path, description, is_experimental)
VALUES (
    gen_random_uuid(),
    'FamilyStressPredictor',
    'v2.1.0',
    '../models/production/family_stress_model.pkl',
    'Production LightGBM model with hardware contagion features',
    FALSE
) ON CONFLICT (name, version) DO NOTHING;

-- Register experimental model
INSERT INTO model_registry (id, name, version, local_path, description, is_experimental)
VALUES (
    gen_random_uuid(),
    'FamilyStressPredictor',
    'v2.2.0-beta',
    '../models/experimental/family_stress_v2.2.pkl',
    'Experimental model with enhanced temporal features',
    TRUE
) ON CONFLICT (name, version) DO NOTHING;
