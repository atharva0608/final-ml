-- ============================================================================
-- Production Lab Mode Database Schema
-- ============================================================================
-- This schema defines the production database for the Spot Optimizer Platform
-- with agentless cross-account AWS access and Lab Mode experimentation.
--
-- Key Features:
-- - Multi-tenant user management with role-based access control
-- - Agentless cross-account AWS access via STS AssumeRole
-- - EC2 instance tracking with Lab Mode configuration
-- - ML model registry and version control
-- - Experiment logging with full audit trail
--
-- PostgreSQL 14+
-- ============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- User Management
-- ============================================================================

-- User accounts with JWT authentication
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(50) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role VARCHAR(20) NOT NULL DEFAULT 'user',

    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,

    CONSTRAINT chk_role CHECK (role IN ('admin', 'user', 'lab'))
);

-- Indexes for fast user lookup
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role ON users(role);

COMMENT ON TABLE users IS 'User accounts with role-based access control';
COMMENT ON COLUMN users.role IS 'User role: admin (full access), user (limited), lab (R&D only)';
COMMENT ON COLUMN users.hashed_password IS 'Bcrypt hashed password';

-- ============================================================================
-- AWS Account Management (Cross-Account Access)
-- ============================================================================

-- AWS Account configuration for agentless cross-account access
CREATE TABLE accounts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Account identification
    account_id VARCHAR(12) NOT NULL UNIQUE,  -- AWS Account ID (12 digits)
    account_name VARCHAR(100) NOT NULL,

    -- Environment type
    environment_type VARCHAR(20) NOT NULL DEFAULT 'LAB',  -- PROD or LAB

    -- Cross-account access (STS AssumeRole)
    role_arn VARCHAR(255) NOT NULL,  -- arn:aws:iam::123456789012:role/SpotOptimizerRole
    external_id VARCHAR(255) NOT NULL,  -- Mandatory for confused deputy protection

    -- AWS region
    region VARCHAR(20) NOT NULL DEFAULT 'ap-south-1',

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_environment_type CHECK (environment_type IN ('PROD', 'LAB'))
);

-- Indexes for fast account lookup
CREATE INDEX idx_accounts_user_id ON accounts(user_id);
CREATE INDEX idx_accounts_account_id ON accounts(account_id);
CREATE INDEX idx_accounts_environment_type ON accounts(environment_type);

COMMENT ON TABLE accounts IS 'AWS Account configuration with STS AssumeRole for cross-account access';
COMMENT ON COLUMN accounts.role_arn IS 'AWS IAM Role ARN for STS AssumeRole (agentless access)';
COMMENT ON COLUMN accounts.external_id IS 'ExternalID for confused deputy attack prevention (MANDATORY)';
COMMENT ON COLUMN accounts.environment_type IS 'PROD (production) or LAB (experimental testing)';

-- ============================================================================
-- EC2 Instance Tracking
-- ============================================================================

-- EC2 Instance configuration and tracking for Lab Mode
CREATE TABLE instances (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,

    -- Instance identification
    instance_id VARCHAR(50) NOT NULL UNIQUE,  -- EC2 instance ID (e.g., i-1234567890abcdef0)
    instance_type VARCHAR(20) NOT NULL,  -- e.g., c5.large
    availability_zone VARCHAR(20) NOT NULL,  -- e.g., ap-south-1a

    -- Lab Mode configuration
    assigned_model_version VARCHAR(50),  -- e.g., "v2.1.0", NULL = use default model
    pipeline_mode VARCHAR(20) NOT NULL DEFAULT 'CLUSTER',  -- CLUSTER, LINEAR, or KUBERNETES
    is_shadow_mode BOOLEAN DEFAULT FALSE,  -- Read-only mode (no actual instance switches)

    -- Security Enforcer fields
    auth_status VARCHAR(20) DEFAULT 'AUTHORIZED',  -- AUTHORIZED, UNAUTHORIZED, FLAGGED, TERMINATED

    -- Kubernetes cluster membership
    cluster_membership JSONB,  -- {"cluster_name": "prod-eks", "node_group": "workers", "role": "worker"}

    -- Status and metadata
    is_active BOOLEAN DEFAULT TRUE,
    last_evaluation TIMESTAMP,  -- Last time optimizer ran on this instance
    metadata JSONB,  -- Additional instance metadata (tags, custom config, etc.)
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_pipeline_mode CHECK (pipeline_mode IN ('CLUSTER', 'LINEAR', 'KUBERNETES')),
    CONSTRAINT chk_auth_status CHECK (auth_status IN ('AUTHORIZED', 'UNAUTHORIZED', 'FLAGGED', 'TERMINATED'))
);

-- Indexes for fast instance lookup
CREATE INDEX idx_instances_account_id ON instances(account_id);
CREATE INDEX idx_instances_instance_id ON instances(instance_id);
CREATE INDEX idx_instances_pipeline_mode ON instances(pipeline_mode);
CREATE INDEX idx_instances_last_evaluation ON instances(last_evaluation);

COMMENT ON TABLE instances IS 'EC2 Instance tracking and Lab Mode configuration';
COMMENT ON COLUMN instances.assigned_model_version IS 'Specific ML model version for A/B testing (NULL = default)';
COMMENT ON COLUMN instances.pipeline_mode IS 'CLUSTER (full optimization) or LINEAR (single-instance)';
COMMENT ON COLUMN instances.is_shadow_mode IS 'If TRUE, pipeline runs but does not execute switches (read-only)';
COMMENT ON COLUMN instances.metadata IS 'JSONB field for flexible additional data (tags, custom config)';

-- ============================================================================
-- ML Model Management
-- ============================================================================

-- ML model version control and registry
CREATE TABLE model_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(50) NOT NULL,  -- e.g., "FamilyStressPredictor"
    version VARCHAR(20) NOT NULL,  -- e.g., "v2.1.0"

    -- Model location
    s3_path VARCHAR(255),  -- S3 URI: s3://bucket/models/model.pkl
    local_path VARCHAR(255),  -- Local filesystem path: /models/production/model.pkl
    description TEXT,

    -- Model metadata
    is_experimental BOOLEAN DEFAULT FALSE,  -- TRUE = testing, FALSE = production-ready
    is_active BOOLEAN DEFAULT TRUE,  -- FALSE = deprecated/archived
    feature_version VARCHAR(20),  -- Feature schema version (e.g., "v2.0")

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by UUID REFERENCES users(id),

    CONSTRAINT uq_model_version UNIQUE (name, version)
);

-- Indexes for model lookup
CREATE INDEX idx_model_registry_name ON model_registry(name);
CREATE INDEX idx_model_registry_version ON model_registry(version);
CREATE INDEX idx_model_registry_is_active ON model_registry(is_active);

COMMENT ON TABLE model_registry IS 'ML model version control and registry';
COMMENT ON COLUMN model_registry.feature_version IS 'Feature schema compatibility (must match FeatureEngine version)';
COMMENT ON COLUMN model_registry.is_experimental IS 'TRUE = Lab testing only, FALSE = production-approved';

-- ============================================================================
-- Experiment Logging
-- ============================================================================

-- Lab Mode experiment logs for R&D analytics
CREATE TABLE experiment_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    instance_id UUID NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    model_id UUID REFERENCES model_registry(id),

    -- Execution metadata
    pipeline_mode VARCHAR(20),  -- CLUSTER or LINEAR
    is_shadow_run BOOLEAN DEFAULT FALSE,  -- Was this a shadow mode run?

    -- ML prediction data
    prediction_score FLOAT,  -- Crash probability (0.0 to 1.0)
    decision VARCHAR(50),  -- SWITCH, STAY, FALLBACK_ONDEMAND
    decision_reason TEXT,

    -- Execution timing
    execution_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    execution_duration_ms INTEGER,  -- Pipeline execution time in milliseconds

    -- Result data (if SWITCH decision)
    candidates_evaluated INTEGER,  -- Number of spot pools evaluated
    selected_instance_type VARCHAR(20),  -- Target instance type
    selected_availability_zone VARCHAR(20),  -- Target AZ
    old_spot_price FLOAT,  -- Previous spot price ($/hr)
    new_spot_price FLOAT,  -- New spot price ($/hr)
    projected_hourly_savings FLOAT,  -- Estimated savings ($/hr)

    -- Feature values (for debugging and audit)
    features_used JSONB,  -- Snapshot of feature vector used for prediction

    -- Error tracking
    error_message TEXT  -- Error details if pipeline failed
);

-- Indexes for experiment analysis
CREATE INDEX idx_experiment_logs_instance_id ON experiment_logs(instance_id);
CREATE INDEX idx_experiment_logs_model_id ON experiment_logs(model_id);
CREATE INDEX idx_experiment_logs_execution_time ON experiment_logs(execution_time);
CREATE INDEX idx_experiment_logs_decision ON experiment_logs(decision);

COMMENT ON TABLE experiment_logs IS 'Lab Mode experiment logs for R&D analytics and model performance tracking';
COMMENT ON COLUMN experiment_logs.is_shadow_run IS 'TRUE = read-only run (no actual switch), FALSE = real execution';
COMMENT ON COLUMN experiment_logs.features_used IS 'JSONB snapshot of feature vector for debugging';
COMMENT ON COLUMN experiment_logs.decision IS 'Pipeline decision: SWITCH (change instance), STAY (keep current), FALLBACK_ONDEMAND';

-- ============================================================================
-- Waste Management (Financial Hygiene)
-- ============================================================================

-- Tracking unused/orphaned AWS resources for automated cleanup
CREATE TABLE waste_resources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,

    -- Resource identification
    resource_type VARCHAR(20) NOT NULL,  -- elastic_ip, ebs_volume, ebs_snapshot, ami
    resource_id VARCHAR(100) NOT NULL,  -- e.g., "eipalloc-abc123", "vol-xyz789"
    region VARCHAR(20) NOT NULL,

    -- Cost data
    monthly_cost FLOAT DEFAULT 0.0,  -- Estimated monthly waste cost
    currency VARCHAR(3) DEFAULT 'USD',

    -- Detection metadata
    detected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    days_unused INTEGER DEFAULT 0,  -- How long has it been unused?

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'DETECTED',  -- DETECTED, FLAGGED, SCHEDULED_DELETE, DELETED
    scheduled_deletion_date TIMESTAMP,  -- Grace period before auto-delete
    deleted_at TIMESTAMP,

    -- Metadata
    metadata JSONB,  -- Additional resource info (tags, attachments, etc.)
    reason TEXT,  -- Why is this considered waste?

    CONSTRAINT chk_waste_resource_type CHECK (resource_type IN ('elastic_ip', 'ebs_volume', 'ebs_snapshot', 'ami')),
    CONSTRAINT chk_waste_status CHECK (status IN ('DETECTED', 'FLAGGED', 'SCHEDULED_DELETE', 'DELETED'))
);

-- Indexes for waste resource tracking
CREATE INDEX idx_waste_resources_account_id ON waste_resources(account_id);
CREATE INDEX idx_waste_resources_resource_type ON waste_resources(resource_type);
CREATE INDEX idx_waste_resources_resource_id ON waste_resources(resource_id);
CREATE INDEX idx_waste_resources_status ON waste_resources(status);
CREATE INDEX idx_waste_resources_detected_at ON waste_resources(detected_at);

COMMENT ON TABLE waste_resources IS 'Tracking unused AWS resources for automated cleanup (EIPs, volumes, snapshots)';
COMMENT ON COLUMN waste_resources.monthly_cost IS 'Estimated monthly cost of this wasted resource';
COMMENT ON COLUMN waste_resources.days_unused IS 'Number of days resource has been unused';
COMMENT ON COLUMN waste_resources.scheduled_deletion_date IS 'Grace period expiration - resource will be deleted after this';

-- ============================================================================
-- Global Risk Contagion (Hive Intelligence)
-- ============================================================================

-- Global spot pool risk tracking (hive intelligence across all customers)
CREATE TABLE spot_pool_risks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Spot pool identification (unique combination)
    region VARCHAR(20) NOT NULL,
    availability_zone VARCHAR(20) NOT NULL,
    instance_type VARCHAR(20) NOT NULL,

    -- Risk tracking
    is_poisoned BOOLEAN NOT NULL DEFAULT FALSE,  -- Is this pool blocked?
    interruption_count INTEGER DEFAULT 0,  -- Total interruptions observed
    last_interruption TIMESTAMP,  -- Most recent interruption
    poisoned_at TIMESTAMP,  -- When was it marked as poisoned?
    poison_expires_at TIMESTAMP,  -- 15-day cooldown

    -- Metadata
    triggering_customer_id UUID,  -- Which customer experienced the interruption?
    metadata JSONB,  -- Additional context (rebalance event, price spike, etc.)

    -- Audit
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Unique constraint on pool identification
    CONSTRAINT uq_spot_pool UNIQUE (region, availability_zone, instance_type)
);

-- Indexes for spot pool risk queries
CREATE INDEX idx_spot_pool_risks_region ON spot_pool_risks(region);
CREATE INDEX idx_spot_pool_risks_az ON spot_pool_risks(availability_zone);
CREATE INDEX idx_spot_pool_risks_instance_type ON spot_pool_risks(instance_type);
CREATE INDEX idx_spot_pool_risks_is_poisoned ON spot_pool_risks(is_poisoned);
CREATE INDEX idx_spot_pool_risks_last_interruption ON spot_pool_risks(last_interruption);

COMMENT ON TABLE spot_pool_risks IS 'Global spot pool risk tracking (hive intelligence) - blocks poisoned pools across all customers';
COMMENT ON COLUMN spot_pool_risks.is_poisoned IS 'TRUE = pool is blocked for 15 days due to interruption';
COMMENT ON COLUMN spot_pool_risks.poison_expires_at IS 'Pool will be unblocked after this timestamp (15-day cooldown)';
COMMENT ON COLUMN spot_pool_risks.triggering_customer_id IS 'Customer who experienced the interruption that poisoned this pool';

-- ============================================================================
-- Approval Workflow
-- ============================================================================

-- Manual approval gates for high-risk production actions
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    instance_id UUID NOT NULL REFERENCES instances(id) ON DELETE CASCADE,
    requester_id UUID NOT NULL REFERENCES users(id),
    approver_id UUID REFERENCES users(id),

    -- Request details
    action_type VARCHAR(50) NOT NULL,  -- "SWITCH_INSTANCE", "TERMINATE_ROGUE", "DELETE_WASTE"
    action_description TEXT,  -- Human-readable description of what will happen
    risk_level VARCHAR(20) DEFAULT 'MEDIUM',  -- LOW, MEDIUM, HIGH, CRITICAL

    -- Decision metadata (what will be executed if approved)
    action_payload JSONB NOT NULL,  -- Contains all details needed to execute action

    -- Status tracking
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, approved, rejected, expired
    rejection_reason TEXT,

    -- Timing
    requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,  -- Auto-reject if not approved in time
    decided_at TIMESTAMP,  -- When was approve/reject decision made?
    executed_at TIMESTAMP,  -- When was the action actually executed (if approved)?

    CONSTRAINT chk_approval_status CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    CONSTRAINT chk_risk_level CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))
);

-- Indexes for approval workflow
CREATE INDEX idx_approval_requests_instance_id ON approval_requests(instance_id);
CREATE INDEX idx_approval_requests_requester_id ON approval_requests(requester_id);
CREATE INDEX idx_approval_requests_approver_id ON approval_requests(approver_id);
CREATE INDEX idx_approval_requests_status ON approval_requests(status);
CREATE INDEX idx_approval_requests_requested_at ON approval_requests(requested_at);

COMMENT ON TABLE approval_requests IS 'Manual approval gates for high-risk production actions';
COMMENT ON COLUMN approval_requests.action_payload IS 'JSONB containing all parameters needed to execute the action';
COMMENT ON COLUMN approval_requests.expires_at IS 'Approval window expiration - auto-reject after this time';

-- ============================================================================
-- Triggers for automatic timestamp updates
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to tables with updated_at column
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_accounts_updated_at
    BEFORE UPDATE ON accounts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_instances_updated_at
    BEFORE UPDATE ON instances
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_spot_pool_risks_updated_at
    BEFORE UPDATE ON spot_pool_risks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- Views for common queries
-- ============================================================================

-- Active instances with account and model information
CREATE VIEW v_active_instances AS
SELECT
    i.id,
    i.instance_id,
    i.instance_type,
    i.availability_zone,
    i.pipeline_mode,
    i.is_shadow_mode,
    i.assigned_model_version,
    i.last_evaluation,
    a.account_id AS aws_account_id,
    a.account_name,
    a.environment_type,
    a.region,
    u.email AS user_email,
    u.username,
    mr.name AS model_name,
    mr.version AS model_version
FROM instances i
JOIN accounts a ON i.account_id = a.id
JOIN users u ON a.user_id = u.id
LEFT JOIN model_registry mr ON mr.version = i.assigned_model_version
WHERE i.is_active = TRUE AND a.is_active = TRUE;

COMMENT ON VIEW v_active_instances IS 'Active instances with joined account and model information';

-- Recent experiment logs with instance details
CREATE VIEW v_recent_experiments AS
SELECT
    el.id,
    el.execution_time,
    el.decision,
    el.prediction_score,
    el.is_shadow_run,
    el.execution_duration_ms,
    i.instance_id,
    i.instance_type,
    i.pipeline_mode,
    a.account_id AS aws_account_id,
    a.account_name,
    mr.name AS model_name,
    mr.version AS model_version,
    el.selected_instance_type,
    el.projected_hourly_savings
FROM experiment_logs el
JOIN instances i ON el.instance_id = i.id
JOIN accounts a ON i.account_id = a.id
LEFT JOIN model_registry mr ON el.model_id = mr.id
ORDER BY el.execution_time DESC
LIMIT 1000;

COMMENT ON VIEW v_recent_experiments IS 'Recent 1000 experiment logs with instance and model details';

-- ============================================================================
-- Initial Data (Optional)
-- ============================================================================

-- Create default admin user
-- Password: admin (hashed with bcrypt)
-- IMPORTANT: Change this password in production!
INSERT INTO users (email, username, hashed_password, full_name, role)
VALUES (
    'admin@spotoptimizer.local',
    'admin',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5hFQJXnJvyDYm',  -- bcrypt hash of "admin"
    'System Administrator',
    'admin'
) ON CONFLICT (email) DO NOTHING;

-- ============================================================================
-- Grants and Permissions
-- ============================================================================

-- Grant appropriate permissions to application user
-- Uncomment and modify as needed for your environment

-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO spot_optimizer_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO spot_optimizer_app;
-- GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO spot_optimizer_app;

-- ============================================================================
-- Database Information
-- ============================================================================

COMMENT ON DATABASE current_database() IS 'Spot Optimizer Platform - Production Lab Mode Database';

-- ============================================================================
-- End of Schema
-- ============================================================================
