--
-- PostgreSQL database dump
--

-- Dumped from database version 13.15
-- Dumped by pg_dump version 13.15

--
-- Name: timescaledb; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS timescaledb WITH SCHEMA public;

--
-- Name: accesslevel; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.accesslevel AS ENUM (
    'READ_ONLY',
    'EXECUTION',
    'FULL'
);

--
-- Name: accountstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.accountstatus AS ENUM (
    'PENDING',
    'SCANNING',
    'ACTIVE',
    'ERROR'
);

--
-- Name: agentactionstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.agentactionstatus AS ENUM (
    'PENDING',
    'PICKED_UP',
    'COMPLETED',
    'FAILED',
    'EXPIRED'
);

--
-- Name: agentactiontype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.agentactiontype AS ENUM (
    'EVICT_POD',
    'CORDON_NODE',
    'DRAIN_NODE',
    'LABEL_NODE',
    'UPDATE_DEPLOYMENT',
    'PATCH_KARPENTER_NODEPOOL',
    'INSTALL_KARPENTER',
    'UNINSTALL_KARPENTER',
    'PATCH_CONTAINER_RESOURCES',
    'TERMINATE_NODE',
    'UNCORDON_NODE'
);

--
-- Name: alert_channel_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.alert_channel_enum AS ENUM (
    'EMAIL',
    'SLACK',
    'PAGERDUTY',
    'WEBHOOK'
);

--
-- Name: alert_severity_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.alert_severity_enum AS ENUM (
    'INFO',
    'WARNING',
    'ERROR',
    'CRITICAL'
);

--
-- Name: alert_status_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.alert_status_enum AS ENUM (
    'PENDING',
    'SENT',
    'FAILED',
    'RATE_LIMITED',
    'DEDUPLICATED'
);

--
-- Name: alert_type_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.alert_type_enum AS ENUM (
    'SPOT_INTERRUPTION',
    'CIRCUIT_BREAKER_OPEN',
    'CIRCUIT_BREAKER_CLOSED',
    'PRICING_STALE',
    'VOLATILITY_HIGH',
    'JIT_LIMIT_EXCEEDED',
    'PDB_BLOCKED',
    'EXECUTION_FAILED',
    'KARPENTER_FAILURE',
    'AGENT_DISCONNECTED'
);

--
-- Name: auditoutcome; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.auditoutcome AS ENUM (
    'SUCCESS',
    'FAILURE'
);

--
-- Name: chaos_experiment_status_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.chaos_experiment_status_enum AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'ROLLED_BACK',
    'CANCELLED'
);

--
-- Name: chaos_experiment_type_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.chaos_experiment_type_enum AS ENUM (
    'REDIS_FLUSH',
    'DB_CONNECTION_LOSS',
    'API_LATENCY',
    'SPOT_INTERRUPTION',
    'PRICING_OUTAGE',
    'POOL_BLACKLIST',
    'KARPENTER_SLOW',
    'PDB_DEADLOCK',
    'CELERY_CRASH',
    'NETWORK_PARTITION'
);

--
-- Name: chaosexperimentstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.chaosexperimentstatus AS ENUM (
    'PENDING',
    'RUNNING',
    'COMPLETED',
    'FAILED',
    'ROLLED_BACK',
    'CANCELLED'
);

--
-- Name: chaosexperimenttype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.chaosexperimenttype AS ENUM (
    'REDIS_FLUSH',
    'DB_CONNECTION_LOSS',
    'API_LATENCY',
    'SPOT_INTERRUPTION',
    'PRICING_OUTAGE',
    'POOL_BLACKLIST',
    'KARPENTER_SLOW',
    'PDB_DEADLOCK',
    'CELERY_CRASH',
    'NETWORK_PARTITION'
);

--
-- Name: cleanupactiontype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.cleanupactiontype AS ENUM (
    'AUTHORIZE',
    'UNAUTHORIZE',
    'TERMINATE',
    'DELETE',
    'RELEASE',
    'SNAPSHOT_STOP',
    'DISABLE',
    'NOTIFY'
);

--
-- Name: clusterstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.clusterstatus AS ENUM (
    'PENDING',
    'ACTIVE',
    'INACTIVE',
    'ERROR',
    'active',
    'pending',
    'error',
    'disconnected',
    'DISCOVERED'
);

--
-- Name: clustertype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.clustertype AS ENUM (
    'EKS',
    'ECS',
    'GKE',
    'AKS'
);

--
-- Name: connectionmode; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.connectionmode AS ENUM (
    'READ_ONLY',
    'FULL_ACCESS'
);

--
-- Name: disktype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.disktype AS ENUM (
    'GP3',
    'GP2',
    'IO1',
    'IO2'
);

--
-- Name: execution_state_enum; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.execution_state_enum AS ENUM (
    'PENDING',
    'VALIDATING',
    'PREWARMING',
    'DRAINING',
    'PROVISIONING',
    'READY',
    'COMPLETED',
    'FAILED',
    'ARCHIVED',
    'PDB_BLOCKED',
    'CIRCUIT_OPEN',
    'ROLLBACK'
);

--
-- Name: hygieneactiontype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.hygieneactiontype AS ENUM (
    'AUTHORIZE',
    'UNAUTHORIZE',
    'TERMINATE',
    'DELETE',
    'RELEASE',
    'SNAPSHOT_STOP',
    'DISABLE',
    'NOTIFY'
);

--
-- Name: instancelifecycle; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.instancelifecycle AS ENUM (
    'SPOT',
    'ON_DEMAND'
);

--
-- Name: invitationstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.invitationstatus AS ENUM (
    'PENDING',
    'ACCEPTED',
    'EXPIRED'
);

--
-- Name: jitscope; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.jitscope AS ENUM (
    'SELF',
    'TEAM',
    'ORGANIZATION',
    'GLOBAL'
);

--
-- Name: karpentermode; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.karpentermode AS ENUM (
    'DRY_RUN',
    'AUTO'
);

--
-- Name: mlmodelstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.mlmodelstatus AS ENUM (
    'TESTING',
    'PRODUCTION',
    'DEPRECATED'
);

--
-- Name: onboardingstep; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.onboardingstep AS ENUM (
    'WELCOME',
    'CONNECT_AWS',
    'VERIFYING',
    'COMPLETED'
);

--
-- Name: optimizationjobstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.optimizationjobstatus AS ENUM (
    'QUEUED',
    'RUNNING',
    'COMPLETED',
    'FAILED'
);

--
-- Name: optimizationphase; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.optimizationphase AS ENUM (
    'INITIAL_POOL_OPTIMIZATION',
    'STABILIZATION',
    'RIGHTSIZING_EVALUATION',
    'COMBINED_EXECUTION',
    'COOLDOWN'
);

--
-- Name: proposalstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.proposalstatus AS ENUM (
    'PENDING',
    'APPROVED',
    'REJECTED',
    'EXECUTED',
    'FAILED'
);

--
-- Name: resourcetype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.resourcetype AS ENUM (
    'CLUSTER',
    'INSTANCE',
    'TEMPLATE',
    'POLICY',
    'HIBERNATION',
    'USER',
    'ACCOUNT'
);

--
-- Name: roletype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.roletype AS ENUM (
    'SYSTEM',
    'CUSTOM'
);

--
-- Name: savingsplantype; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.savingsplantype AS ENUM (
    'COMPUTE',
    'EC2_INSTANCE',
    'SAGEMAKER'
);

--
-- Name: syncstatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.syncstatus AS ENUM (
    'HEALTHY',
    'WARNING',
    'FAILED'
);

--
-- Name: templatescope; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.templatescope AS ENUM (
    'GLOBAL',
    'CLUSTER'
);

--
-- Name: templatestatus; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.templatestatus AS ENUM (
    'DRAFT',
    'ACTIVE',
    'ARCHIVED'
);

--
-- Name: templatestrategy; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.templatestrategy AS ENUM (
    'CHEAPEST',
    'BALANCED',
    'PERFORMANCE'
);

--
-- Name: userrole; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.userrole AS ENUM (
    'CLIENT',
    'SUPER_ADMIN',
    'ORG_ADMIN',
    'TEAM_LEAD',
    'MEMBER'
);

--

--
-- Name: pod_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pod_metrics (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    namespace character varying(253) NOT NULL,
    pod_name character varying(253) NOT NULL,
    node_name character varying(253) NOT NULL,
    controller_kind character varying(50),
    controller_name character varying(253),
    cpu_usage_millicores integer NOT NULL,
    cpu_request_millicores integer,
    cpu_limit_millicores integer,
    memory_usage_bytes bigint NOT NULL,
    memory_request_bytes bigint,
    memory_limit_bytes bigint,
    cpu_utilization_pct double precision,
    memory_utilization_pct double precision,
    container_count integer DEFAULT 1 NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    pod_metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
)
WITH (autovacuum_vacuum_scale_factor='0.01', autovacuum_analyze_scale_factor='0.005', autovacuum_vacuum_cost_limit='1000', autovacuum_vacuum_cost_delay='2');

--

--

--

--

--

--

--
-- Name: accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.accounts (
    id character varying(36) NOT NULL,
    user_id character varying(36) NOT NULL,
    aws_account_id character varying(12) NOT NULL,
    role_arn character varying(255) NOT NULL,
    external_id character varying(64),
    status public.accountstatus NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    organization_id character varying(36),
    last_sync_at timestamp without time zone,
    sync_status public.syncstatus DEFAULT 'HEALTHY'::public.syncstatus,
    sync_error text,
    is_default boolean DEFAULT false,
    region character varying(20) DEFAULT 'us-east-1'::character varying
);

--
-- Name: agent_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_actions (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    action_type public.agentactiontype NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    status public.agentactionstatus NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    picked_up_at timestamp without time zone,
    completed_at timestamp without time zone,
    result jsonb,
    error_message character varying(1024),
    CONSTRAINT check_expires_after_created CHECK ((expires_at > created_at)),
    CONSTRAINT chk_action_type_uppercase CHECK (((action_type)::text = upper((action_type)::text)))
);

--
-- Name: agent_identities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.agent_identities (
    id character varying NOT NULL,
    cluster_id character varying NOT NULL,
    oidc_issuer character varying NOT NULL,
    oidc_audience character varying NOT NULL,
    service_account_namespace character varying NOT NULL,
    service_account_name character varying NOT NULL,
    public_key_pem text,
    public_key_algorithm character varying NOT NULL,
    jwks_json json,
    jwks_last_updated timestamp with time zone,
    certificate_thumbprint character varying,
    max_token_age_seconds integer NOT NULL,
    require_nbf_claim boolean NOT NULL,
    require_exp_claim boolean NOT NULL,
    is_active boolean NOT NULL,
    last_token_validated_at timestamp with time zone,
    validation_failure_count integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    metadata json NOT NULL,
    agent_metadata json
);

--

--
-- Name: alert_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_config (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    alert_type public.alert_type_enum NOT NULL,
    severity public.alert_severity_enum NOT NULL,
    channel public.alert_channel_enum NOT NULL,
    enabled boolean NOT NULL,
    channel_config json NOT NULL,
    threshold_value double precision,
    threshold_duration_seconds integer,
    target_regions character varying[],
    target_clusters character varying[],
    cooldown_seconds integer NOT NULL,
    max_alerts_per_hour integer NOT NULL,
    webhook_secret character varying(64),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    cluster_id character varying(36),
    channels json,
    email_recipients json,
    slack_webhook_url character varying(500),
    slack_channel character varying(100),
    pagerduty_integration_key character varying(255),
    webhook_url character varying(500),
    webhook_hmac_secret character varying(255),
    threshold_window_minutes integer,
    region_scope character varying(50),
    dedup_window_minutes integer,
    rate_limit_per_minute integer,
    max_retries integer,
    retry_backoff_seconds integer,
    alert_metadata json,
    created_by character varying(36),
    updated_by character varying(36)
);

--
-- Name: alert_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_history (
    id character varying(36) NOT NULL,
    alert_config_id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    alert_type public.alert_type_enum NOT NULL,
    severity public.alert_severity_enum NOT NULL,
    channel public.alert_channel_enum NOT NULL,
    status public.alert_status_enum NOT NULL,
    title character varying(500) NOT NULL,
    message text NOT NULL,
    metadata json NOT NULL,
    retry_count integer NOT NULL,
    last_retry_at timestamp without time zone,
    error_message text,
    deduplication_key character varying(64) NOT NULL,
    hmac_signature character varying(128),
    sent_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    cluster_id character varying(36),
    fingerprint character varying(64),
    region character varying(50),
    channels_attempted json,
    channels_succeeded json,
    channels_failed json,
    email_sent boolean,
    email_error text,
    slack_sent boolean,
    slack_error text,
    pagerduty_sent boolean,
    pagerduty_error text,
    pagerduty_incident_key character varying(255),
    webhook_sent boolean,
    webhook_error text,
    webhook_signature character varying(128),
    max_retries integer,
    next_retry_at timestamp without time zone,
    rate_limit_window_start timestamp without time zone,
    rate_limit_count integer,
    event_data json,
    context json,
    completed_at timestamp without time zone
);

--
-- Name: api_keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.api_keys (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    key_hash character varying(64) NOT NULL,
    key_prefix character varying(8) NOT NULL,
    description character varying(255),
    last_used_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    expires_at timestamp without time zone
);

--
-- Name: approval_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approval_requests (
    id character varying(36) NOT NULL,
    requester_id character varying(36),
    organization_id character varying(36),
    resource_type character varying(100),
    action character varying(100),
    status character varying(50) DEFAULT 'PENDING'::character varying,
    execution_payload json,
    reviewer_id character varying(36),
    reviewed_at timestamp without time zone,
    rejection_reason text,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now()
);

--
-- Name: approvals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.approvals (
    id character varying NOT NULL,
    user_id character varying NOT NULL,
    organization_id character varying NOT NULL,
    approver_id character varying,
    parent_id character varying,
    type character varying,
    resource_id character varying,
    action_type character varying,
    reason_category character varying,
    reason_text text,
    duration_hours integer,
    status character varying,
    created_at timestamp without time zone,
    approved_at timestamp without time zone,
    activated_at timestamp without time zone,
    expires_at timestamp without time zone,
    updated_at timestamp without time zone,
    feature_id character varying(100),
    jit_scope public.jitscope DEFAULT 'TEAM'::public.jitscope,
    jit_metadata json,
    auto_approved boolean DEFAULT false
);

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_logs (
    id character varying(36) NOT NULL,
    "timestamp" timestamp with time zone DEFAULT now() NOT NULL,
    actor_id character varying(36) NOT NULL,
    actor_name character varying(255) NOT NULL,
    event character varying(255) NOT NULL,
    resource character varying(255) NOT NULL,
    resource_type public.resourcetype NOT NULL,
    outcome public.auditoutcome NOT NULL,
    ip_address character varying(45),
    user_agent character varying(512),
    diff_before jsonb,
    diff_after jsonb,
    checksum character varying(64)
);

--
-- Name: authorized_resources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.authorized_resources (
    id character varying(36) NOT NULL,
    resource_id character varying NOT NULL,
    account_id character varying(36) NOT NULL,
    region character varying NOT NULL,
    resource_type character varying NOT NULL,
    notes text,
    created_at timestamp without time zone,
    created_by_id character varying(36)
);

--
-- Name: auto_tag_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.auto_tag_rules (
    id character varying NOT NULL,
    cluster_id character varying,
    tag_key character varying,
    tag_value character varying,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    dynamic_tags json,
    resource_scope character varying(50) DEFAULT 'all'::character varying,
    override_behavior character varying(20) DEFAULT 'skip_existing'::character varying,
    inject_system_tags boolean DEFAULT true,
    organization_id character varying(36),
    name character varying(255),
    description text,
    resource_types json,
    regions json,
    name_pattern character varying(500),
    pattern_type character varying(20),
    tags_to_apply json,
    run_mode character varying(20),
    priority integer,
    last_run_at timestamp without time zone,
    last_run_matched integer,
    last_run_tagged integer,
    total_resources_tagged integer,
    created_by character varying(36)
);

--
-- Name: chaos_experiment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chaos_experiment (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    experiment_type public.chaos_experiment_type_enum NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    config json NOT NULL,
    requires_approval boolean NOT NULL,
    approved_by character varying(36),
    approved_at timestamp without time zone,
    production_enabled boolean NOT NULL,
    status public.chaos_experiment_status_enum NOT NULL,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    error_rate_before double precision,
    error_rate_during double precision,
    error_rate_after double precision,
    latency_p50_before double precision,
    latency_p50_during double precision,
    latency_p50_after double precision,
    latency_p99_before double precision,
    latency_p99_during double precision,
    latency_p99_after double precision,
    auto_rolled_back boolean NOT NULL,
    rollback_reason text,
    rollback_at timestamp without time zone,
    metrics_snapshot json,
    logs_url character varying(500),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: chaos_experiments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chaos_experiments (
    id character varying NOT NULL,
    cluster_id character varying,
    organization_id character varying NOT NULL,
    experiment_type public.chaosexperimenttype NOT NULL,
    status public.chaosexperimentstatus,
    is_production_enabled boolean,
    requires_manual_approval boolean,
    approved_by_user_id character varying,
    approved_at timestamp without time zone,
    max_affected_clusters integer,
    max_error_rate_threshold double precision,
    max_duration_minutes integer,
    parameters json,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    duration_seconds double precision,
    result_summary json,
    metrics_snapshot json,
    rollback_triggered boolean,
    rollback_reason text,
    rollback_completed_at timestamp without time zone,
    error_logs json,
    execution_logs json,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);

--
-- Name: circuit_breaker_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.circuit_breaker_state (
    id character varying(36) NOT NULL,
    service_name character varying(255) NOT NULL,
    state character varying(20) NOT NULL,
    failure_count integer NOT NULL,
    last_failure_at timestamp without time zone,
    trip_count integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: cleanup_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cleanup_policies (
    id uuid NOT NULL,
    name character varying NOT NULL,
    description character varying,
    resource_type public.resourcetype NOT NULL,
    region character varying,
    conditions json NOT NULL,
    action public.cleanupactiontype NOT NULL,
    priority integer,
    is_active boolean,
    organization_id character varying,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone
);

--
-- Name: cluster_cooldowns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cluster_cooldowns (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    last_switch_timestamp timestamp without time zone NOT NULL,
    created_at timestamp without time zone
);

--
-- Name: cluster_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cluster_metrics (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    metric_type character varying(50) NOT NULL,
    metric_data jsonb NOT NULL,
    "timestamp" timestamp without time zone NOT NULL
);

--
-- Name: cluster_optimization_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cluster_optimization_settings (
    cluster_id character varying NOT NULL,
    auto_rebalance_enabled boolean DEFAULT false,
    auto_rightsizing_enabled boolean DEFAULT false,
    cooldown_override_minutes integer,
    conservative_mode_enabled boolean DEFAULT true,
    manual_approval_required boolean DEFAULT false,
    target_spot_exposure_pct integer DEFAULT 100,
    maintain_standby boolean DEFAULT false,
    diversify_pools boolean DEFAULT false,
    failure_cooldown_minutes integer DEFAULT 30,
    updated_at timestamp without time zone,
    optimization_target character varying(20) DEFAULT 'spot'::character varying NOT NULL,
    instance_aware_rightsizing boolean DEFAULT false
);

--
-- Name: cluster_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cluster_policies (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    config jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);

--
-- Name: cluster_template_mappings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cluster_template_mappings (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    template_id character varying(36) NOT NULL,
    version_id character varying(36) NOT NULL,
    is_default boolean NOT NULL,
    assigned_at timestamp without time zone
);

--
-- Name: clusters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clusters (
    id character varying(36) NOT NULL,
    account_id character varying(36) NOT NULL,
    name character varying(255) NOT NULL,
    region character varying(50) NOT NULL,
    vpc_id character varying(50),
    api_endpoint character varying(255),
    k8s_version character varying(20),
    status public.clusterstatus NOT NULL,
    agent_installed character varying(1) DEFAULT 'N'::character varying NOT NULL,
    last_heartbeat timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    arn character varying,
    cluster_type public.clustertype,
    is_agentless character varying,
    aws_role_arn character varying,
    aws_external_id character varying,
    tags json,
    monthly_cost integer DEFAULT 0,
    estimated_savings integer DEFAULT 0,
    is_hibernating boolean DEFAULT false NOT NULL,
    hibernation_state json,
    hibernation_lock character varying(255),
    hibernation_lock_acquired_at timestamp without time zone,
    optimization_mode character varying(20) DEFAULT 'BALANCED'::character varying NOT NULL,
    model_version character varying(10) DEFAULT '6'::character varying,
    workload_type character varying(10) DEFAULT 'STATELESS'::character varying NOT NULL,
    version character varying,
    endpoint character varying,
    ca_data text,
    api_key character varying,
    last_cost_update timestamp without time zone,
    potential_savings_monthly double precision,
    realized_savings_monthly double precision,
    on_demand_node_count integer,
    last_assessed timestamp without time zone,
    inventory_summary json,
    node_count integer,
    spot_count integer,
    cpu_total integer,
    mem_total integer,
    cpu_usage_pct double precision,
    mem_usage_pct double precision,
    karpenter_mode public.karpentermode,
    auto_rebalance_enabled boolean,
    rightsizing_enabled boolean
);

--
-- Name: cost_explorer_sync_status; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cost_explorer_sync_status (
    id character varying NOT NULL,
    account_id character varying NOT NULL,
    last_sync_at timestamp without time zone NOT NULL,
    last_synced_date date NOT NULL,
    status character varying DEFAULT 'SUCCESS'::character varying NOT NULL,
    error_message character varying,
    records_synced double precision DEFAULT '0'::double precision NOT NULL,
    updated_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);

--
-- Name: credential_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credential_cache (
    id character varying(36) NOT NULL,
    account_id character varying(36) NOT NULL,
    user_id character varying(36) NOT NULL,
    approval_id character varying(36),
    encrypted_access_key text NOT NULL,
    encrypted_secret_key text NOT NULL,
    encrypted_session_token text NOT NULL,
    role_arn character varying(255) NOT NULL,
    session_name character varying(128) NOT NULL,
    region character varying(20) NOT NULL,
    issued_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    rotation_threshold_at timestamp without time zone NOT NULL,
    last_used_at timestamp without time zone,
    request_ip character varying(45),
    request_user_agent character varying(500),
    created_at timestamp without time zone NOT NULL,
    last_rotated_at timestamp without time zone,
    rotation_count integer,
    is_active character varying(10),
    revoked_at timestamp without time zone,
    revoked_by character varying(36),
    updated_at timestamp without time zone,
    last_accessed_at timestamp without time zone,
    access_count integer
);

--
-- Name: daily_cluster_stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_cluster_stats (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    date_stamp date NOT NULL,
    total_cost double precision,
    total_savings double precision,
    spot_nodes integer,
    on_demand_nodes integer,
    total_nodes integer,
    spot_ratio double precision,
    avg_cpu_utilization double precision,
    avg_memory_utilization double precision
);

--
-- Name: daily_costs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.daily_costs (
    id character varying NOT NULL,
    account_id character varying NOT NULL,
    date date NOT NULL,
    service_name character varying NOT NULL,
    cost_amount double precision DEFAULT '0'::double precision NOT NULL,
    currency character varying DEFAULT 'USD'::character varying NOT NULL,
    cost_type character varying DEFAULT 'Usage'::character varying NOT NULL,
    updated_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);

--
-- Name: data_transfer_analysis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_transfer_analysis (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    account_id character varying(36) NOT NULL,
    region character varying(50) NOT NULL,
    transfer_type character varying(100) NOT NULL,
    total_bytes_gb double precision,
    monthly_cost double precision,
    source_resource_id character varying(100),
    recommendation_type character varying(50),
    estimated_savings double precision,
    recommendation_detail json,
    last_analyzed_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    traffic_direction character varying(50),
    free_tier_consumed integer,
    lookback_days integer
);

--
-- Name: execution_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.execution_state (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    state public.execution_state_enum NOT NULL,
    last_transition_at timestamp without time zone NOT NULL,
    retry_count integer NOT NULL,
    idempotency_key character varying(255) NOT NULL,
    error_message text,
    archived_at timestamp without time zone,
    target_node_name character varying(255),
    substitute_instance_id character varying(255),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: family_hour_baselines; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.family_hour_baselines (
    id character varying(36) NOT NULL,
    instance_family character varying(50) NOT NULL,
    region character varying(50) NOT NULL,
    date date NOT NULL,
    hour integer NOT NULL,
    mean_price double precision NOT NULL,
    min_price double precision NOT NULL,
    max_price double precision NOT NULL,
    stddev_price double precision NOT NULL,
    sample_count integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: hibernation_schedule_clusters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hibernation_schedule_clusters (
    schedule_id character varying NOT NULL,
    cluster_id character varying NOT NULL
);

--
-- Name: hibernation_schedules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hibernation_schedules (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    schedule_matrix text NOT NULL,
    timezone character varying(50) DEFAULT 'UTC'::character varying NOT NULL,
    prewarm_enabled character varying(1) DEFAULT 'N'::character varying NOT NULL,
    prewarm_minutes integer DEFAULT 30 NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    is_active character varying(1),
    strategy character varying(20) DEFAULT 'NAMESPACE_SLEEP'::character varying,
    saved_state json DEFAULT '{}'::json,
    az_affinity json DEFAULT '{}'::json,
    last_action character varying(20),
    last_action_at timestamp without time zone,
    schedule_type character varying(20) DEFAULT 'WEEKLY'::character varying NOT NULL,
    date_overrides json DEFAULT '{}'::json,
    name character varying,
    description character varying,
    pre_warm_minutes integer
);

--
-- Name: instance_catalog; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instance_catalog (
    id character varying(36) NOT NULL,
    instance_type character varying(50) NOT NULL,
    region character varying(50) NOT NULL,
    current_generation boolean NOT NULL,
    architecture character varying(20) NOT NULL,
    supported_architectures character varying(100),
    vcpus integer NOT NULL,
    cores integer NOT NULL,
    threads_per_core integer NOT NULL,
    memory_mib integer NOT NULL,
    memory_gb double precision NOT NULL,
    network_performance character varying(100),
    max_network_interfaces integer NOT NULL,
    ipv4_addresses_per_interface integer NOT NULL,
    ipv6_supported boolean NOT NULL,
    ena_support character varying(20),
    ebs_optimized character varying(20),
    ebs_encryption_support character varying(20),
    instance_storage_supported boolean NOT NULL,
    instance_storage_type character varying(20),
    instance_storage_total_gb integer NOT NULL,
    hypervisor character varying(20),
    processor_manufacturer character varying(50),
    sustained_clock_speed_ghz double precision,
    gpu_count integer NOT NULL,
    gpu_manufacturer character varying(50),
    gpu_memory_mib integer NOT NULL,
    burstable_performance_supported boolean NOT NULL,
    auto_recovery_supported boolean NOT NULL,
    hibernation_supported boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_updated_at timestamp without time zone NOT NULL
);

--
-- Name: instances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instances (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    instance_id character varying(20) NOT NULL,
    instance_type character varying(50) NOT NULL,
    lifecycle public.instancelifecycle NOT NULL,
    az character varying(50) NOT NULL,
    price double precision,
    cpu_util double precision,
    memory_util double precision,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    account_id character varying(36),
    node_name character varying(255),
    standby boolean DEFAULT false NOT NULL,
    state character varying(20),
    status character varying(20),
    status_message character varying(255),
    architecture character varying(20),
    last_heartbeat timestamp without time zone
);

--
-- Name: lab_experiments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lab_experiments (
    id character varying(36) NOT NULL,
    model_id character varying(36) NOT NULL,
    instance_id character varying(20) NOT NULL,
    test_type character varying(50) NOT NULL,
    telemetry jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    cluster_id character varying(36)
);

--
-- Name: ml_models; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ml_models (
    id character varying(36) NOT NULL,
    version character varying(50) NOT NULL,
    file_path character varying(512) NOT NULL,
    status public.mlmodelstatus NOT NULL,
    performance_metrics jsonb,
    uploaded_at timestamp without time zone DEFAULT now() NOT NULL,
    validated_at timestamp without time zone,
    promoted_at timestamp without time zone
);

--
-- Name: model_registry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_registry (
    id character varying(36) NOT NULL,
    model_version character varying(10) NOT NULL,
    model_name character varying(255) NOT NULL,
    feature_schema_version character varying(10) NOT NULL,
    onnx_path character varying(500) NOT NULL,
    is_active boolean NOT NULL,
    deployed_at timestamp without time zone,
    deprecated_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: node_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_metrics (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    node_name character varying(256) NOT NULL,
    cpu_usage_millicores double precision,
    cpu_capacity_millicores double precision,
    memory_usage_bytes double precision,
    memory_capacity_bytes double precision,
    disk_usage_bytes double precision,
    disk_capacity_bytes double precision,
    instance_id character varying(64),
    instance_type character varying(64),
    az character varying(32),
    "timestamp" timestamp without time zone NOT NULL
);

--
-- Name: node_template_versions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_template_versions (
    id character varying(36) NOT NULL,
    template_id character varying(36) NOT NULL,
    version_number integer NOT NULL,
    status public.templatestatus NOT NULL,
    constraints_json json NOT NULL
);

--
-- Name: node_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_templates (
    id character varying(36) NOT NULL,
    user_id character varying(36) NOT NULL,
    name character varying(255) NOT NULL,
    families character varying[] NOT NULL,
    architecture character varying(20) DEFAULT 'x86_64'::character varying NOT NULL,
    strategy public.templatestrategy NOT NULL,
    disk_type public.disktype NOT NULL,
    disk_size integer DEFAULT 100 NOT NULL,
    is_default character varying(1) DEFAULT 'N'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    last_used_by_atharva_at timestamp without time zone,
    atharva_rankings_count integer DEFAULT 0 NOT NULL,
    scope public.templatescope,
    created_by character varying(255)
);

--
-- Name: onboarding_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.onboarding_states (
    id uuid NOT NULL,
    user_id character varying(36) NOT NULL,
    current_step public.onboardingstep,
    external_id character varying NOT NULL,
    aws_role_arn character varying,
    aws_account_id character varying,
    connection_mode public.connectionmode,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);

--
-- Name: ondemand_pricing; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ondemand_pricing (
    id integer NOT NULL,
    instance_type character varying,
    region character varying,
    price numeric(10,4),
    updated_at timestamp without time zone
);

--
-- Name: ondemand_pricing_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ondemand_pricing_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: ondemand_pricing_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ondemand_pricing_id_seq OWNED BY public.ondemand_pricing.id;

--
-- Name: optimization_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.optimization_jobs (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    status public.optimizationjobstatus NOT NULL,
    results jsonb,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    started_at timestamp without time zone,
    completed_at timestamp without time zone
);

--
-- Name: optimization_strategy; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.optimization_strategy (
    cluster_id character varying NOT NULL,
    strategy_type character varying,
    risk_ceiling_percent integer,
    min_savings_percent integer,
    volatility_tolerance_percent integer,
    migration_penalty_multiplier double precision,
    diversity_strictness_level character varying,
    updated_at timestamp without time zone
);

--
-- Name: optimizer_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.optimizer_states (
    id character varying NOT NULL,
    cluster_id character varying NOT NULL,
    current_phase public.optimizationphase NOT NULL,
    phase_started_at timestamp without time zone NOT NULL,
    last_pool_optimization_at timestamp without time zone,
    last_rightsizing_check_at timestamp without time zone,
    last_combined_evaluation_at timestamp without time zone,
    pending_rightsizing_proposal_id character varying,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: organization_invitations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_invitations (
    id character varying(36) NOT NULL,
    email character varying(255) NOT NULL,
    token character varying(255) NOT NULL,
    status public.invitationstatus NOT NULL,
    role public.userrole NOT NULL,
    access_level public.accesslevel NOT NULL,
    organization_id character varying(36) NOT NULL,
    created_by character varying(36),
    created_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: organizations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organizations (
    id character varying(36) NOT NULL,
    name character varying(255) NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    is_governance_enabled boolean DEFAULT false,
    is_strict_approval_mode boolean DEFAULT false,
    governance_config json DEFAULT '{}'::json,
    required_tags json DEFAULT '["Owner", "Environment"]'::json,
    automation_config json DEFAULT '{}'::json,
    owner_user_id character varying(36),
    slug character varying(255),
    external_id character varying(36),
    billing_email character varying(255),
    stripe_customer_id character varying(255),
    status character varying(50) DEFAULT 'active'::character varying,
    require_automation_approval boolean DEFAULT true
);

--
-- Name: permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.permissions (
    id character varying(36) NOT NULL,
    slug character varying(100) NOT NULL,
    name character varying(200) NOT NULL,
    module character varying(50) NOT NULL,
    description text
);

--
-- Name: platform_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.platform_settings (
    id integer NOT NULL,
    maintenance_mode boolean,
    global_signup_enabled boolean,
    default_trial_days integer,
    active_ml_model_version character varying,
    pricing_api_url character varying,
    updated_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now()
);

--
-- Name: platform_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.platform_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: platform_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.platform_settings_id_seq OWNED BY public.platform_settings.id;

--
-- Name: pod_metrics_daily; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.pod_metrics_daily AS

--
-- Name: pod_metrics_monthly; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.pod_metrics_monthly AS

--
-- Name: pod_metrics_old; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pod_metrics_old (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    namespace character varying(253) NOT NULL,
    pod_name character varying(253) NOT NULL,
    node_name character varying(253) NOT NULL,
    controller_kind character varying(50),
    controller_name character varying(253),
    cpu_usage_millicores integer NOT NULL,
    cpu_request_millicores integer,
    cpu_limit_millicores integer,
    memory_usage_bytes bigint NOT NULL,
    memory_request_bytes bigint,
    memory_limit_bytes bigint,
    cpu_utilization_pct double precision,
    memory_utilization_pct double precision,
    container_count integer DEFAULT 1 NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    metadata jsonb DEFAULT '{}'::jsonb
);

--
-- Name: pool_cooldowns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pool_cooldowns (
    id character varying(36) NOT NULL,
    pool_id character varying(100) NOT NULL,
    last_failure_timestamp timestamp without time zone NOT NULL,
    region character varying(20) NOT NULL,
    created_at timestamp without time zone
);

--
-- Name: pool_risk_scores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pool_risk_scores (
    id integer NOT NULL,
    instance_type character varying(50) NOT NULL,
    az character varying(20) NOT NULL,
    region character varying(20) NOT NULL,
    historical_zero_rate numeric(5,4) DEFAULT 0.05 NOT NULL,
    interruption_count integer DEFAULT 0 NOT NULL,
    total_hours integer DEFAULT 0 NOT NULL,
    last_interruption_at timestamp without time zone,
    last_updated timestamp without time zone DEFAULT now()
);

--
-- Name: pool_risk_scores_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pool_risk_scores_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: pool_risk_scores_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pool_risk_scores_id_seq OWNED BY public.pool_risk_scores.id;

--
-- Name: rds_instance_analysis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rds_instance_analysis (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    account_id character varying(36) NOT NULL,
    db_instance_identifier character varying(100) NOT NULL,
    engine character varying(50) NOT NULL,
    instance_class character varying(50) NOT NULL,
    multi_az boolean,
    status character varying(50),
    environment_tag character varying(50),
    is_production boolean,
    avg_cpu_utilization double precision,
    max_cpu_utilization double precision,
    avg_db_connections double precision,
    current_monthly_cost double precision,
    estimated_savings double precision,
    recommendation_type character varying(50),
    recommendation_impact character varying(20),
    last_analyzed_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: rebalancing_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rebalancing_actions (
    id integer NOT NULL,
    cluster_id character varying(100) NOT NULL,
    trigger character varying(20) NOT NULL,
    source_pool character varying(100) NOT NULL,
    target_pool character varying(100) NOT NULL,
    status character varying(20) NOT NULL,
    nodes_affected integer,
    pods_migrated integer,
    started_at timestamp without time zone NOT NULL,
    completed_at timestamp without time zone,
    duration_seconds integer,
    error_message text,
    metadata jsonb,
    created_at timestamp without time zone DEFAULT now()
);

--
-- Name: rebalancing_actions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.rebalancing_actions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: rebalancing_actions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.rebalancing_actions_id_seq OWNED BY public.rebalancing_actions.id;

--
-- Name: ri_utilization; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ri_utilization (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    account_id character varying(36) NOT NULL,
    reservation_id character varying(100) NOT NULL,
    instance_type character varying(50) NOT NULL,
    platform character varying(50),
    region character varying(50) NOT NULL,
    availability_zone character varying(50),
    offering_class character varying(20),
    scope character varying(20),
    instance_count integer,
    upfront_cost double precision,
    hourly_cost double precision,
    monthly_cost double precision,
    utilization_percentage double precision,
    utilized_hours double precision,
    total_hours double precision,
    monthly_waste double precision,
    annual_waste double precision,
    unused_days integer,
    estimated_resale_value double precision,
    resale_percentage double precision,
    start_date timestamp without time zone,
    end_date timestamp without time zone,
    days_remaining integer,
    last_analyzed_at timestamp without time zone,
    analysis_period_days integer,
    recommendation_type character varying(50),
    recommendation_detail json,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: rightsizing_proposals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rightsizing_proposals (
    id character varying NOT NULL,
    cluster_id character varying NOT NULL,
    current_instance_type character varying NOT NULL,
    current_vcpu integer NOT NULL,
    current_memory_gb double precision NOT NULL,
    current_pool character varying NOT NULL,
    current_hourly_cost double precision NOT NULL,
    proposed_instance_type character varying NOT NULL,
    proposed_vcpu integer NOT NULL,
    proposed_memory_gb double precision NOT NULL,
    proposed_hourly_cost double precision NOT NULL,
    estimated_hourly_savings double precision NOT NULL,
    estimated_monthly_savings double precision NOT NULL,
    savings_percentage double precision NOT NULL,
    avg_cpu_utilization_pct double precision NOT NULL,
    p95_cpu_utilization_pct double precision NOT NULL,
    avg_memory_utilization_pct double precision NOT NULL,
    p95_memory_utilization_pct double precision NOT NULL,
    metric_sample_count integer NOT NULL,
    metric_window_hours double precision NOT NULL,
    status public.proposalstatus NOT NULL,
    created_at timestamp without time zone NOT NULL,
    evaluated_at timestamp without time zone,
    executed_at timestamp without time zone,
    combined_ev_option_a double precision,
    combined_ev_option_b double precision,
    combined_ev_option_c double precision,
    selected_option character varying,
    best_pool_for_new_size character varying,
    best_pool_hourly_cost double precision,
    best_pool_risk_score double precision,
    rejection_reason text,
    evaluation_breakdown json,
    ev_breakdown json,
    net_ev double precision
);

--
-- Name: role_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_permissions (
    role_id character varying(36) NOT NULL,
    permission_id character varying(36) NOT NULL
);

--
-- Name: roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.roles (
    id character varying(36) NOT NULL,
    name character varying(100) NOT NULL,
    type public.roletype NOT NULL,
    organization_id character varying(36),
    description character varying(500),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: s3_bucket_analysis; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.s3_bucket_analysis (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    account_id character varying(36) NOT NULL,
    bucket_name character varying(255) NOT NULL,
    region character varying(50) NOT NULL,
    total_size_bytes double precision,
    object_count integer,
    size_standard double precision,
    size_ia double precision,
    size_glacier double precision,
    size_deep_archive double precision,
    size_intelligent double precision,
    monthly_cost double precision,
    estimated_savings double precision,
    has_lifecycle_policy boolean,
    is_versioning_enabled boolean,
    last_accessed_date timestamp without time zone,
    size_hot double precision,
    size_warm double precision,
    size_cold double precision,
    size_frozen double precision,
    recommendation_type character varying(50),
    recommendation_detail json,
    last_analyzed_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    analysis_method character varying(50),
    pricing_source character varying(50),
    storage_lens_config_arn character varying(512)
);

--
-- Name: savings_plan_utilization; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.savings_plan_utilization (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    account_id character varying(36) NOT NULL,
    savings_plan_id character varying(255) NOT NULL,
    savings_plan_arn character varying(512),
    plan_type public.savingsplantype NOT NULL,
    hourly_commitment double precision NOT NULL,
    monthly_commitment double precision NOT NULL,
    utilization_percentage double precision,
    utilized_commitment double precision,
    unused_commitment double precision,
    actual_savings double precision,
    potential_savings double precision,
    coverage_percentage double precision,
    on_demand_spend double precision,
    lookback_days integer,
    start_date timestamp without time zone,
    end_date timestamp without time zone,
    payment_option character varying(50),
    recommendation_type character varying(50),
    recommendation_detail json,
    is_underutilized boolean,
    is_expiring_soon boolean,
    last_analyzed_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: spot_advisor_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.spot_advisor_data (
    id integer NOT NULL,
    instance_type character varying,
    region character varying,
    os_type character varying,
    interruption_frequency character varying,
    interruption_index integer,
    savings_percentage integer,
    updated_at timestamp without time zone
);

--
-- Name: spot_advisor_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.spot_advisor_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: spot_advisor_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.spot_advisor_data_id_seq OWNED BY public.spot_advisor_data.id;

--
-- Name: spot_price_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.spot_price_history (
    id integer NOT NULL,
    instance_type character varying(50) NOT NULL,
    az character varying(20) NOT NULL,
    region character varying(20) NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    spot_price numeric(10,6) NOT NULL,
    ondemand_price numeric(10,6) NOT NULL,
    savings numeric(5,4),
    created_at timestamp without time zone DEFAULT now(),
    availability_zone character varying,
    product_description character varying,
    price numeric(10,4)
);

--
-- Name: spot_price_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.spot_price_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: spot_price_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.spot_price_history_id_seq OWNED BY public.spot_price_history.id;

--
-- Name: stateful_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stateful_rules (
    cluster_id character varying NOT NULL,
    manual_resize_allowed boolean,
    show_ondemand_only boolean,
    require_approval boolean,
    block_spot_for_stateful boolean,
    max_downscale_percent integer,
    updated_at timestamp without time zone
);

--
-- Name: stateless_runtime_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stateless_runtime_rules (
    cluster_id character varying NOT NULL,
    instance_diversification_enabled boolean,
    respect_pdb_enabled boolean,
    prewarm_minutes integer,
    substitute_strategy character varying,
    max_rebalances_per_24h integer,
    resize_cooldown_minutes integer,
    resize_headroom_multiplier double precision,
    volatility_safety_multiplier double precision,
    fresh_cluster_stabilization_minutes integer,
    updated_at timestamp without time zone
);

--
-- Name: substitute_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.substitute_states (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    substitute_type character varying(20) NOT NULL,
    instance_type character varying(50),
    active_since timestamp without time zone NOT NULL,
    cost_impact double precision,
    status character varying(20),
    created_at timestamp without time zone
);

--
-- Name: system_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_configs (
    id character varying(36) NOT NULL,
    key character varying(100) NOT NULL,
    value character varying(500),
    description character varying(500),
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);

--
-- Name: tag_automation_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag_automation_logs (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    rule_id character varying(36) NOT NULL,
    resource_id character varying(100) NOT NULL,
    resource_type character varying(50) NOT NULL,
    action_taken character varying(20) NOT NULL,
    reason text NOT NULL,
    monthly_cost numeric(10,2),
    outcome character varying(20) NOT NULL,
    error_message text,
    executed_at timestamp without time zone NOT NULL
);

--
-- Name: tag_automation_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag_automation_rules (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    name character varying(255) NOT NULL,
    trigger_expr character varying(100) NOT NULL,
    resource_types json NOT NULL,
    grace_days smallint NOT NULL,
    action character varying(20) NOT NULL,
    notification_channels json NOT NULL,
    safety_conditions json NOT NULL,
    enabled boolean NOT NULL,
    last_run_at timestamp without time zone,
    created_by character varying(36) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: tag_compliance_scores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag_compliance_scores (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    resource_id character varying(100) NOT NULL,
    resource_name character varying(255),
    resource_type character varying(50) NOT NULL,
    environment character varying(50),
    team character varying(100),
    score smallint NOT NULL,
    status character varying(20) NOT NULL,
    tags_present integer NOT NULL,
    monthly_cost numeric(10,2) NOT NULL,
    grace_deadline timestamp without time zone,
    scanned_at timestamp without time zone NOT NULL
);

--
-- Name: tag_policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag_policies (
    id character varying NOT NULL,
    name character varying,
    description text,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    dynamic_tags json,
    resource_scope character varying(50) DEFAULT 'all'::character varying,
    override_behavior character varying(20) DEFAULT 'skip_existing'::character varying,
    inject_system_tags boolean DEFAULT true,
    organization_id character varying(36),
    tag_key character varying(255),
    value_mode character varying(20),
    allowed_values json,
    validation_regex character varying(500),
    enforcement_level character varying(20),
    resource_types json,
    regions json,
    resource_count integer
);

--
-- Name: tag_scoring_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag_scoring_configs (
    id character varying(36) NOT NULL,
    organization_id character varying(36) NOT NULL,
    mode character varying(20) NOT NULL,
    threshold smallint NOT NULL,
    required_keys json NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);

--
-- Name: tag_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag_templates (
    id character varying NOT NULL,
    name character varying,
    description text,
    tags json,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    resource_scope character varying(50) DEFAULT 'all'::character varying NOT NULL,
    organization_id character varying(36)
);

--
-- Name: teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teams (
    id character varying(36) NOT NULL,
    name character varying(100) NOT NULL,
    organization_id character varying(36) NOT NULL,
    created_at timestamp without time zone,
    governance_config json
);

--
-- Name: termination_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.termination_events (
    id integer NOT NULL,
    instance_type character varying(50) NOT NULL,
    az character varying(20) NOT NULL,
    region character varying(20) NOT NULL,
    cluster_id character varying(100),
    instance_id character varying(50),
    node_name character varying(100),
    detected_at timestamp without time zone NOT NULL,
    source character varying(20) NOT NULL,
    action_taken character varying(50),
    metadata jsonb,
    created_at timestamp without time zone DEFAULT now()
);

--
-- Name: termination_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.termination_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

--
-- Name: termination_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.termination_events_id_seq OWNED BY public.termination_events.id;

--
-- Name: user_permissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_permissions (
    user_id character varying(36) NOT NULL,
    permission_id character varying(36) NOT NULL
);

--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id character varying(36) NOT NULL,
    organization_id character varying(36),
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    role public.userrole NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    team_id character varying(36),
    team_member_permissions json,
    is_active character varying(1) DEFAULT 'Y'::character varying NOT NULL,
    access_level public.accesslevel DEFAULT 'READ_ONLY'::public.accesslevel,
    full_name character varying(100),
    role_id character varying(36),
    must_reset_password boolean DEFAULT false NOT NULL,
    status character varying(20) DEFAULT 'ACTIVE'::character varying NOT NULL,
    preferences json,
    onboarding_completed boolean DEFAULT false
);

--
-- Name: worker_registrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.worker_registrations (
    id character varying(36) NOT NULL,
    cluster_id character varying(36) NOT NULL,
    node_name character varying(256) NOT NULL,
    instance_id character varying(64),
    instance_type character varying(64),
    az character varying(32),
    lifecycle character varying(16),
    status character varying(16) NOT NULL,
    registered_at timestamp without time zone NOT NULL,
    last_heartbeat timestamp without time zone NOT NULL
);

--
-- Name: ondemand_pricing id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ondemand_pricing ALTER COLUMN id SET DEFAULT nextval('public.ondemand_pricing_id_seq'::regclass);

--
-- Name: platform_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_settings ALTER COLUMN id SET DEFAULT nextval('public.platform_settings_id_seq'::regclass);

--
-- Name: pool_risk_scores id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pool_risk_scores ALTER COLUMN id SET DEFAULT nextval('public.pool_risk_scores_id_seq'::regclass);

--
-- Name: rebalancing_actions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rebalancing_actions ALTER COLUMN id SET DEFAULT nextval('public.rebalancing_actions_id_seq'::regclass);

--
-- Name: spot_advisor_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spot_advisor_data ALTER COLUMN id SET DEFAULT nextval('public.spot_advisor_data_id_seq'::regclass);

--
-- Name: spot_price_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spot_price_history ALTER COLUMN id SET DEFAULT nextval('public.spot_price_history_id_seq'::regclass);

--
-- Name: termination_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.termination_events ALTER COLUMN id SET DEFAULT nextval('public.termination_events_id_seq'::regclass);

--
-- Name: accounts accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_pkey PRIMARY KEY (id);

--
-- Name: agent_actions agent_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_actions
    ADD CONSTRAINT agent_actions_pkey PRIMARY KEY (id);

--
-- Name: agent_identities agent_identities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_identities
    ADD CONSTRAINT agent_identities_pkey PRIMARY KEY (id);

--

--
-- Name: alert_config alert_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_config
    ADD CONSTRAINT alert_config_pkey PRIMARY KEY (id);

--
-- Name: alert_history alert_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_history
    ADD CONSTRAINT alert_history_pkey PRIMARY KEY (id);

--
-- Name: api_keys api_keys_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);

--
-- Name: approval_requests approval_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_pkey PRIMARY KEY (id);

--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (id);

--
-- Name: authorized_resources authorized_resources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorized_resources
    ADD CONSTRAINT authorized_resources_pkey PRIMARY KEY (id);

--
-- Name: auto_tag_rules auto_tag_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.auto_tag_rules
    ADD CONSTRAINT auto_tag_rules_pkey PRIMARY KEY (id);

--
-- Name: chaos_experiment chaos_experiment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chaos_experiment
    ADD CONSTRAINT chaos_experiment_pkey PRIMARY KEY (id);

--
-- Name: chaos_experiments chaos_experiments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chaos_experiments
    ADD CONSTRAINT chaos_experiments_pkey PRIMARY KEY (id);

--
-- Name: circuit_breaker_state circuit_breaker_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.circuit_breaker_state
    ADD CONSTRAINT circuit_breaker_state_pkey PRIMARY KEY (id);

--
-- Name: cleanup_policies cleanup_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cleanup_policies
    ADD CONSTRAINT cleanup_policies_pkey PRIMARY KEY (id);

--
-- Name: cluster_cooldowns cluster_cooldowns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_cooldowns
    ADD CONSTRAINT cluster_cooldowns_pkey PRIMARY KEY (id);

--
-- Name: cluster_metrics cluster_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_metrics
    ADD CONSTRAINT cluster_metrics_pkey PRIMARY KEY (id, "timestamp");

--
-- Name: cluster_optimization_settings cluster_optimization_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_optimization_settings
    ADD CONSTRAINT cluster_optimization_settings_pkey PRIMARY KEY (cluster_id);

--
-- Name: cluster_policies cluster_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_policies
    ADD CONSTRAINT cluster_policies_pkey PRIMARY KEY (id);

--
-- Name: cluster_template_mappings cluster_template_mappings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_template_mappings
    ADD CONSTRAINT cluster_template_mappings_pkey PRIMARY KEY (id);

--
-- Name: clusters clusters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clusters
    ADD CONSTRAINT clusters_pkey PRIMARY KEY (id);

--
-- Name: cost_explorer_sync_status cost_explorer_sync_status_account_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_explorer_sync_status
    ADD CONSTRAINT cost_explorer_sync_status_account_id_key UNIQUE (account_id);

--
-- Name: cost_explorer_sync_status cost_explorer_sync_status_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_explorer_sync_status
    ADD CONSTRAINT cost_explorer_sync_status_pkey PRIMARY KEY (id);

--
-- Name: credential_cache credential_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credential_cache
    ADD CONSTRAINT credential_cache_pkey PRIMARY KEY (id);

--
-- Name: daily_cluster_stats daily_cluster_stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_cluster_stats
    ADD CONSTRAINT daily_cluster_stats_pkey PRIMARY KEY (id);

--
-- Name: daily_costs daily_costs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_costs
    ADD CONSTRAINT daily_costs_pkey PRIMARY KEY (id);

--
-- Name: data_transfer_analysis data_transfer_analysis_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_transfer_analysis
    ADD CONSTRAINT data_transfer_analysis_pkey PRIMARY KEY (id);

--
-- Name: execution_state execution_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_state
    ADD CONSTRAINT execution_state_pkey PRIMARY KEY (id);

--
-- Name: family_hour_baselines family_hour_baselines_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.family_hour_baselines
    ADD CONSTRAINT family_hour_baselines_pkey PRIMARY KEY (id);

--
-- Name: hibernation_schedule_clusters hibernation_schedule_clusters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hibernation_schedule_clusters
    ADD CONSTRAINT hibernation_schedule_clusters_pkey PRIMARY KEY (schedule_id, cluster_id);

--
-- Name: hibernation_schedules hibernation_schedules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hibernation_schedules
    ADD CONSTRAINT hibernation_schedules_pkey PRIMARY KEY (id);

--
-- Name: instance_catalog instance_catalog_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instance_catalog
    ADD CONSTRAINT instance_catalog_pkey PRIMARY KEY (id);

--
-- Name: instances instances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instances
    ADD CONSTRAINT instances_pkey PRIMARY KEY (id);

--
-- Name: lab_experiments lab_experiments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lab_experiments
    ADD CONSTRAINT lab_experiments_pkey PRIMARY KEY (id);

--
-- Name: ml_models ml_models_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ml_models
    ADD CONSTRAINT ml_models_pkey PRIMARY KEY (id);

--
-- Name: model_registry model_registry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_registry
    ADD CONSTRAINT model_registry_pkey PRIMARY KEY (id);

--
-- Name: node_metrics node_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_metrics
    ADD CONSTRAINT node_metrics_pkey PRIMARY KEY (id, "timestamp");

--
-- Name: node_template_versions node_template_versions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_template_versions
    ADD CONSTRAINT node_template_versions_pkey PRIMARY KEY (id);

--
-- Name: node_templates node_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_templates
    ADD CONSTRAINT node_templates_pkey PRIMARY KEY (id);

--
-- Name: onboarding_states onboarding_states_external_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.onboarding_states
    ADD CONSTRAINT onboarding_states_external_id_key UNIQUE (external_id);

--
-- Name: onboarding_states onboarding_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.onboarding_states
    ADD CONSTRAINT onboarding_states_pkey PRIMARY KEY (id);

--
-- Name: onboarding_states onboarding_states_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.onboarding_states
    ADD CONSTRAINT onboarding_states_user_id_key UNIQUE (user_id);

--
-- Name: ondemand_pricing ondemand_pricing_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ondemand_pricing
    ADD CONSTRAINT ondemand_pricing_pkey PRIMARY KEY (id);

--
-- Name: optimization_jobs optimization_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_jobs
    ADD CONSTRAINT optimization_jobs_pkey PRIMARY KEY (id);

--
-- Name: optimization_strategy optimization_strategy_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_strategy
    ADD CONSTRAINT optimization_strategy_pkey PRIMARY KEY (cluster_id);

--
-- Name: optimizer_states optimizer_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimizer_states
    ADD CONSTRAINT optimizer_states_pkey PRIMARY KEY (id);

--
-- Name: organization_invitations organization_invitations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_invitations
    ADD CONSTRAINT organization_invitations_pkey PRIMARY KEY (id);

--
-- Name: organizations organizations_external_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_external_id_key UNIQUE (external_id);

--
-- Name: organizations organizations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);

--
-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);

--
-- Name: platform_settings platform_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.platform_settings
    ADD CONSTRAINT platform_settings_pkey PRIMARY KEY (id);

--
-- Name: pod_metrics pod_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pod_metrics
    ADD CONSTRAINT pod_metrics_pkey PRIMARY KEY (id, "timestamp");

--
-- Name: pool_cooldowns pool_cooldowns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pool_cooldowns
    ADD CONSTRAINT pool_cooldowns_pkey PRIMARY KEY (id);

--
-- Name: pool_risk_scores pool_risk_scores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pool_risk_scores
    ADD CONSTRAINT pool_risk_scores_pkey PRIMARY KEY (id);

--
-- Name: rds_instance_analysis rds_instance_analysis_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rds_instance_analysis
    ADD CONSTRAINT rds_instance_analysis_pkey PRIMARY KEY (id);

--
-- Name: rebalancing_actions rebalancing_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rebalancing_actions
    ADD CONSTRAINT rebalancing_actions_pkey PRIMARY KEY (id);

--
-- Name: ri_utilization ri_utilization_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ri_utilization
    ADD CONSTRAINT ri_utilization_pkey PRIMARY KEY (id);

--
-- Name: rightsizing_proposals rightsizing_proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rightsizing_proposals
    ADD CONSTRAINT rightsizing_proposals_pkey PRIMARY KEY (id);

--
-- Name: role_permissions role_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (role_id, permission_id);

--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);

--
-- Name: s3_bucket_analysis s3_bucket_analysis_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.s3_bucket_analysis
    ADD CONSTRAINT s3_bucket_analysis_pkey PRIMARY KEY (id);

--
-- Name: savings_plan_utilization savings_plan_utilization_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.savings_plan_utilization
    ADD CONSTRAINT savings_plan_utilization_pkey PRIMARY KEY (id);

--
-- Name: spot_advisor_data spot_advisor_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spot_advisor_data
    ADD CONSTRAINT spot_advisor_data_pkey PRIMARY KEY (id);

--
-- Name: spot_price_history spot_price_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spot_price_history
    ADD CONSTRAINT spot_price_history_pkey PRIMARY KEY (id);

--
-- Name: stateful_rules stateful_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stateful_rules
    ADD CONSTRAINT stateful_rules_pkey PRIMARY KEY (cluster_id);

--
-- Name: stateless_runtime_rules stateless_runtime_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stateless_runtime_rules
    ADD CONSTRAINT stateless_runtime_rules_pkey PRIMARY KEY (cluster_id);

--
-- Name: substitute_states substitute_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.substitute_states
    ADD CONSTRAINT substitute_states_pkey PRIMARY KEY (id);

--
-- Name: system_configs system_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_configs
    ADD CONSTRAINT system_configs_pkey PRIMARY KEY (id);

--
-- Name: tag_automation_logs tag_automation_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_automation_logs
    ADD CONSTRAINT tag_automation_logs_pkey PRIMARY KEY (id);

--
-- Name: tag_automation_rules tag_automation_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_automation_rules
    ADD CONSTRAINT tag_automation_rules_pkey PRIMARY KEY (id);

--
-- Name: tag_compliance_scores tag_compliance_scores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_compliance_scores
    ADD CONSTRAINT tag_compliance_scores_pkey PRIMARY KEY (id);

--
-- Name: tag_policies tag_policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_policies
    ADD CONSTRAINT tag_policies_pkey PRIMARY KEY (id);

--
-- Name: tag_scoring_configs tag_scoring_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_scoring_configs
    ADD CONSTRAINT tag_scoring_configs_pkey PRIMARY KEY (id);

--
-- Name: tag_templates tag_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_templates
    ADD CONSTRAINT tag_templates_pkey PRIMARY KEY (id);

--
-- Name: teams teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (id);

--
-- Name: termination_events termination_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.termination_events
    ADD CONSTRAINT termination_events_pkey PRIMARY KEY (id);

--
-- Name: approvals tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT tickets_pkey PRIMARY KEY (id);

--
-- Name: cluster_template_mappings uq_cluster_default_template; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_template_mappings
    ADD CONSTRAINT uq_cluster_default_template UNIQUE (cluster_id, is_default);

--
-- Name: execution_state uq_execution_state_cluster_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.execution_state
    ADD CONSTRAINT uq_execution_state_cluster_id UNIQUE (cluster_id);

--
-- Name: pool_risk_scores uq_pool_risk_score; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pool_risk_scores
    ADD CONSTRAINT uq_pool_risk_score UNIQUE (instance_type, az);

--
-- Name: spot_price_history uq_spot_price_history; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spot_price_history
    ADD CONSTRAINT uq_spot_price_history UNIQUE (instance_type, az, "timestamp");

--
-- Name: node_templates uq_user_template_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_templates
    ADD CONSTRAINT uq_user_template_name UNIQUE (user_id, name);

--
-- Name: user_permissions user_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_permissions
    ADD CONSTRAINT user_permissions_pkey PRIMARY KEY (user_id, permission_id);

--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

--
-- Name: worker_registrations worker_registrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.worker_registrations
    ADD CONSTRAINT worker_registrations_pkey PRIMARY KEY (id);

--

--

--

--

--

--

--

--

--

--

--
-- Name: idx_account_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_account_date ON public.daily_costs USING btree (account_id, date);

--
-- Name: idx_account_date_service; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_account_date_service ON public.daily_costs USING btree (account_id, date, service_name);

--
-- Name: idx_active_executions; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_active_executions ON public.execution_state USING btree (state, last_transition_at);

--
-- Name: idx_active_models; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_active_models ON public.model_registry USING btree (is_active, deployed_at);

--
-- Name: idx_agent_action_cluster_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_action_cluster_status ON public.agent_actions USING btree (cluster_id, status);

--
-- Name: idx_agent_action_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_agent_action_expires ON public.agent_actions USING btree (expires_at);

--
-- Name: idx_alert_config_org_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_config_org_enabled ON public.alert_config USING btree (organization_id, enabled);

--
-- Name: idx_alert_config_type_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_config_type_severity ON public.alert_config USING btree (alert_type, severity);

--
-- Name: idx_alert_history_dedup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_history_dedup ON public.alert_history USING btree (deduplication_key, created_at);

--
-- Name: idx_alert_history_status_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_alert_history_status_created ON public.alert_history USING btree (status, created_at);

--
-- Name: idx_audit_actor_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_actor_timestamp ON public.audit_logs USING btree (actor_id, "timestamp" DESC);

--
-- Name: idx_audit_resource_type_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_resource_type_timestamp ON public.audit_logs USING btree (resource_type, "timestamp" DESC);

--
-- Name: idx_audit_timestamp_desc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_audit_timestamp_desc ON public.audit_logs USING btree ("timestamp" DESC);

--
-- Name: idx_chaos_experiment_cluster_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chaos_experiment_cluster_status ON public.chaos_experiment USING btree (cluster_id, status);

--
-- Name: idx_chaos_experiment_type_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_chaos_experiment_type_created ON public.chaos_experiment USING btree (experiment_type, created_at);

--
-- Name: idx_cluster_instance_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cluster_instance_type ON public.instances USING btree (cluster_id, instance_type);

--
-- Name: idx_cluster_lifecycle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cluster_lifecycle ON public.instances USING btree (cluster_id, lifecycle);

--
-- Name: idx_cluster_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cluster_state ON public.execution_state USING btree (cluster_id, state);

--
-- Name: idx_credential_cache_expires; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credential_cache_expires ON public.credential_cache USING btree (expires_at);

--
-- Name: idx_credential_cache_user_account; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credential_cache_user_account ON public.credential_cache USING btree (user_id, account_id);

--
-- Name: idx_date_service; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_date_service ON public.daily_costs USING btree (date, service_name);

--
-- Name: idx_family_region_date_hour; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_family_region_date_hour ON public.family_hour_baselines USING btree (instance_family, region, date, hour);

--
-- Name: idx_family_region_hour; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_family_region_hour ON public.family_hour_baselines USING btree (instance_family, region, hour);

--
-- Name: idx_instance_type_region; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_instance_type_region ON public.instance_catalog USING btree (instance_type, region);

--
-- Name: idx_model_version_schema; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_model_version_schema ON public.model_registry USING btree (model_version, feature_schema_version);

--
-- Name: idx_optimization_cluster_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_optimization_cluster_status ON public.optimization_jobs USING btree (cluster_id, status);

--
-- Name: idx_optimization_created_desc; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_optimization_created_desc ON public.optimization_jobs USING btree (created_at DESC);

--
-- Name: idx_pod_metric_cluster_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pod_metric_cluster_time ON public.pod_metrics_old USING btree (cluster_id, "timestamp");

--
-- Name: idx_pod_metric_controller; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pod_metric_controller ON public.pod_metrics_old USING btree (cluster_id, namespace, controller_kind, controller_name, "timestamp");

--
-- Name: idx_pod_metric_node_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pod_metric_node_time ON public.pod_metrics_old USING btree (cluster_id, node_name, "timestamp");

--
-- Name: idx_pod_metric_pod_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pod_metric_pod_time ON public.pod_metrics_old USING btree (cluster_id, namespace, pod_name, "timestamp");

--
-- Name: idx_pod_metrics_ts_cluster_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pod_metrics_ts_cluster_time ON public.pod_metrics USING btree (cluster_id, "timestamp");

--
-- Name: idx_pod_metrics_ts_controller; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pod_metrics_ts_controller ON public.pod_metrics USING btree (cluster_id, namespace, controller_kind, controller_name, "timestamp");

--
-- Name: idx_pod_metrics_ts_id_time; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_pod_metrics_ts_id_time ON public.pod_metrics USING btree (id, "timestamp");

--
-- Name: idx_pod_metrics_ts_node_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pod_metrics_ts_node_time ON public.pod_metrics USING btree (cluster_id, node_name, "timestamp");

--
-- Name: idx_pod_metrics_ts_pod_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pod_metrics_ts_pod_time ON public.pod_metrics USING btree (cluster_id, namespace, pod_name, "timestamp");

--
-- Name: idx_pool_risk_scores_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_pool_risk_scores_lookup ON public.pool_risk_scores USING btree (instance_type, az);

--
-- Name: idx_rebalancing_actions_cluster; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rebalancing_actions_cluster ON public.rebalancing_actions USING btree (cluster_id, started_at);

--
-- Name: idx_rebalancing_actions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rebalancing_actions_status ON public.rebalancing_actions USING btree (status, started_at);

--
-- Name: idx_region_arch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_region_arch ON public.instance_catalog USING btree (region, architecture);

--
-- Name: idx_region_current_gen; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_region_current_gen ON public.instance_catalog USING btree (region, current_generation);

--
-- Name: idx_region_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_region_date ON public.family_hour_baselines USING btree (region, date);

--
-- Name: idx_service_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_service_state ON public.circuit_breaker_state USING btree (service_name, state);

--
-- Name: idx_spot_price_history_lookup; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spot_price_history_lookup ON public.spot_price_history USING btree (instance_type, az, "timestamp" DESC);

--
-- Name: idx_state_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_state_archived ON public.execution_state USING btree (state, archived_at);

--
-- Name: idx_termination_events_cluster; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_termination_events_cluster ON public.termination_events USING btree (cluster_id, detected_at);

--
-- Name: idx_termination_events_pool; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_termination_events_pool ON public.termination_events USING btree (instance_type, az, detected_at);

--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_email ON public.users USING btree (email);

--
-- Name: idx_vcpus_memory; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_vcpus_memory ON public.instance_catalog USING btree (vcpus, memory_gb);

--
-- Name: ix_accounts_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_accounts_status ON public.accounts USING btree (status);

--
-- Name: ix_accounts_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_accounts_user_id ON public.accounts USING btree (user_id);

--
-- Name: ix_agent_actions_action_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_actions_action_type ON public.agent_actions USING btree (action_type);

--
-- Name: ix_agent_actions_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_actions_cluster_id ON public.agent_actions USING btree (cluster_id);

--
-- Name: ix_agent_actions_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_actions_created_at ON public.agent_actions USING btree (created_at);

--
-- Name: ix_agent_actions_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_actions_expires_at ON public.agent_actions USING btree (expires_at);

--
-- Name: ix_agent_actions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_actions_status ON public.agent_actions USING btree (status);

--
-- Name: ix_agent_identities_certificate_thumbprint; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_agent_identities_certificate_thumbprint ON public.agent_identities USING btree (certificate_thumbprint);

--
-- Name: ix_agent_identities_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_agent_identities_cluster_id ON public.agent_identities USING btree (cluster_id);

--
-- Name: ix_alert_config_alert_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_config_alert_type ON public.alert_config USING btree (alert_type);

--
-- Name: ix_alert_config_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_config_channel ON public.alert_config USING btree (channel);

--
-- Name: ix_alert_config_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_config_enabled ON public.alert_config USING btree (enabled);

--
-- Name: ix_alert_config_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_config_organization_id ON public.alert_config USING btree (organization_id);

--
-- Name: ix_alert_history_alert_config_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_history_alert_config_id ON public.alert_history USING btree (alert_config_id);

--
-- Name: ix_alert_history_alert_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_history_alert_type ON public.alert_history USING btree (alert_type);

--
-- Name: ix_alert_history_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_history_created_at ON public.alert_history USING btree (created_at);

--
-- Name: ix_alert_history_deduplication_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_history_deduplication_key ON public.alert_history USING btree (deduplication_key);

--
-- Name: ix_alert_history_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_history_organization_id ON public.alert_history USING btree (organization_id);

--
-- Name: ix_alert_history_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alert_history_status ON public.alert_history USING btree (status);

--
-- Name: ix_api_keys_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_keys_cluster_id ON public.api_keys USING btree (cluster_id);

--
-- Name: ix_api_keys_key_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_api_keys_key_hash ON public.api_keys USING btree (key_hash);

--
-- Name: ix_api_keys_key_prefix; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_api_keys_key_prefix ON public.api_keys USING btree (key_prefix);

--
-- Name: ix_audit_logs_actor_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_actor_id ON public.audit_logs USING btree (actor_id);

--
-- Name: ix_audit_logs_event; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_event ON public.audit_logs USING btree (event);

--
-- Name: ix_audit_logs_resource_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_resource_type ON public.audit_logs USING btree (resource_type);

--
-- Name: ix_audit_logs_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_logs_timestamp ON public.audit_logs USING btree ("timestamp");

--
-- Name: ix_chaos_experiment_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chaos_experiment_cluster_id ON public.chaos_experiment USING btree (cluster_id);

--
-- Name: ix_chaos_experiment_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chaos_experiment_created_at ON public.chaos_experiment USING btree (created_at);

--
-- Name: ix_chaos_experiment_experiment_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chaos_experiment_experiment_type ON public.chaos_experiment USING btree (experiment_type);

--
-- Name: ix_chaos_experiment_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chaos_experiment_organization_id ON public.chaos_experiment USING btree (organization_id);

--
-- Name: ix_chaos_experiment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chaos_experiment_status ON public.chaos_experiment USING btree (status);

--
-- Name: ix_circuit_breaker_state_service_name; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_circuit_breaker_state_service_name ON public.circuit_breaker_state USING btree (service_name);

--
-- Name: ix_circuit_breaker_state_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_circuit_breaker_state_state ON public.circuit_breaker_state USING btree (state);

--
-- Name: ix_cluster_policies_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_cluster_policies_cluster_id ON public.cluster_policies USING btree (cluster_id);

--
-- Name: ix_clusters_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clusters_account_id ON public.clusters USING btree (account_id);

--
-- Name: ix_clusters_arn; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clusters_arn ON public.clusters USING btree (arn);

--
-- Name: ix_clusters_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clusters_name ON public.clusters USING btree (name);

--
-- Name: ix_clusters_region; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clusters_region ON public.clusters USING btree (region);

--
-- Name: ix_clusters_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_clusters_status ON public.clusters USING btree (status);

--
-- Name: ix_credential_cache_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credential_cache_account_id ON public.credential_cache USING btree (account_id);

--
-- Name: ix_credential_cache_approval_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credential_cache_approval_id ON public.credential_cache USING btree (approval_id);

--
-- Name: ix_credential_cache_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credential_cache_expires_at ON public.credential_cache USING btree (expires_at);

--
-- Name: ix_credential_cache_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_credential_cache_user_id ON public.credential_cache USING btree (user_id);

--
-- Name: ix_daily_costs_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_daily_costs_account_id ON public.daily_costs USING btree (account_id);

--
-- Name: ix_daily_costs_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_daily_costs_date ON public.daily_costs USING btree (date);

--
-- Name: ix_daily_costs_service_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_daily_costs_service_name ON public.daily_costs USING btree (service_name);

--
-- Name: ix_data_transfer_analysis_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_transfer_analysis_account_id ON public.data_transfer_analysis USING btree (account_id);

--
-- Name: ix_data_transfer_analysis_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_transfer_analysis_id ON public.data_transfer_analysis USING btree (id);

--
-- Name: ix_data_transfer_analysis_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_data_transfer_analysis_organization_id ON public.data_transfer_analysis USING btree (organization_id);

--
-- Name: ix_execution_state_archived_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_state_archived_at ON public.execution_state USING btree (archived_at);

--
-- Name: ix_execution_state_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_state_cluster_id ON public.execution_state USING btree (cluster_id);

--
-- Name: ix_execution_state_idempotency_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_execution_state_idempotency_key ON public.execution_state USING btree (idempotency_key);

--
-- Name: ix_execution_state_state; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_execution_state_state ON public.execution_state USING btree (state);

--
-- Name: ix_family_hour_baselines_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_family_hour_baselines_date ON public.family_hour_baselines USING btree (date);

--
-- Name: ix_family_hour_baselines_hour; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_family_hour_baselines_hour ON public.family_hour_baselines USING btree (hour);

--
-- Name: ix_family_hour_baselines_instance_family; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_family_hour_baselines_instance_family ON public.family_hour_baselines USING btree (instance_family);

--
-- Name: ix_family_hour_baselines_region; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_family_hour_baselines_region ON public.family_hour_baselines USING btree (region);

--
-- Name: ix_hibernation_schedules_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_hibernation_schedules_cluster_id ON public.hibernation_schedules USING btree (cluster_id);

--
-- Name: ix_instance_catalog_architecture; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instance_catalog_architecture ON public.instance_catalog USING btree (architecture);

--
-- Name: ix_instance_catalog_current_generation; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instance_catalog_current_generation ON public.instance_catalog USING btree (current_generation);

--
-- Name: ix_instance_catalog_instance_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instance_catalog_instance_type ON public.instance_catalog USING btree (instance_type);

--
-- Name: ix_instance_catalog_memory_gb; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instance_catalog_memory_gb ON public.instance_catalog USING btree (memory_gb);

--
-- Name: ix_instance_catalog_region; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instance_catalog_region ON public.instance_catalog USING btree (region);

--
-- Name: ix_instance_catalog_vcpus; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instance_catalog_vcpus ON public.instance_catalog USING btree (vcpus);

--
-- Name: ix_instances_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instances_account_id ON public.instances USING btree (account_id);

--
-- Name: ix_instances_az; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instances_az ON public.instances USING btree (az);

--
-- Name: ix_instances_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instances_cluster_id ON public.instances USING btree (cluster_id);

--
-- Name: ix_instances_instance_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_instances_instance_id ON public.instances USING btree (instance_id);

--
-- Name: ix_instances_instance_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instances_instance_type ON public.instances USING btree (instance_type);

--
-- Name: ix_instances_lifecycle; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instances_lifecycle ON public.instances USING btree (lifecycle);

--
-- Name: ix_instances_node_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instances_node_name ON public.instances USING btree (node_name);

--
-- Name: ix_instances_standby; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_instances_standby ON public.instances USING btree (standby);

--
-- Name: ix_lab_experiments_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lab_experiments_created_at ON public.lab_experiments USING btree (created_at);

--
-- Name: ix_lab_experiments_model_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lab_experiments_model_id ON public.lab_experiments USING btree (model_id);

--
-- Name: ix_ml_models_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ml_models_status ON public.ml_models USING btree (status);

--
-- Name: ix_ml_models_version; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_ml_models_version ON public.ml_models USING btree (version);

--
-- Name: ix_model_registry_feature_schema_version; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_registry_feature_schema_version ON public.model_registry USING btree (feature_schema_version);

--
-- Name: ix_model_registry_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_registry_is_active ON public.model_registry USING btree (is_active);

--
-- Name: ix_model_registry_model_version; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_model_registry_model_version ON public.model_registry USING btree (model_version);

--
-- Name: ix_node_templates_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_node_templates_user_id ON public.node_templates USING btree (user_id);

--
-- Name: ix_optimization_jobs_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_jobs_cluster_id ON public.optimization_jobs USING btree (cluster_id);

--
-- Name: ix_optimization_jobs_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_jobs_created_at ON public.optimization_jobs USING btree (created_at);

--
-- Name: ix_optimization_jobs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_optimization_jobs_status ON public.optimization_jobs USING btree (status);

--
-- Name: ix_pod_metrics_cluster_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pod_metrics_cluster_id ON public.pod_metrics_old USING btree (cluster_id);

--
-- Name: ix_pod_metrics_controller_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pod_metrics_controller_kind ON public.pod_metrics_old USING btree (controller_kind);

--
-- Name: ix_pod_metrics_controller_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pod_metrics_controller_name ON public.pod_metrics_old USING btree (controller_name);

--
-- Name: ix_pod_metrics_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pod_metrics_id ON public.pod_metrics_old USING btree (id);

--
-- Name: ix_pod_metrics_namespace; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pod_metrics_namespace ON public.pod_metrics_old USING btree (namespace);

--
-- Name: ix_pod_metrics_node_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pod_metrics_node_name ON public.pod_metrics_old USING btree (node_name);

--
-- Name: ix_pod_metrics_pod_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pod_metrics_pod_name ON public.pod_metrics_old USING btree (pod_name);

--
-- Name: ix_pod_metrics_timestamp; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pod_metrics_timestamp ON public.pod_metrics_old USING btree ("timestamp");

--
-- Name: ix_rds_instance_analysis_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rds_instance_analysis_account_id ON public.rds_instance_analysis USING btree (account_id);

--
-- Name: ix_rds_instance_analysis_db_instance_identifier; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rds_instance_analysis_db_instance_identifier ON public.rds_instance_analysis USING btree (db_instance_identifier);

--
-- Name: ix_rds_instance_analysis_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rds_instance_analysis_id ON public.rds_instance_analysis USING btree (id);

--
-- Name: ix_rds_instance_analysis_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rds_instance_analysis_organization_id ON public.rds_instance_analysis USING btree (organization_id);

--
-- Name: ix_ri_utilization_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ri_utilization_account_id ON public.ri_utilization USING btree (account_id);

--
-- Name: ix_ri_utilization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ri_utilization_id ON public.ri_utilization USING btree (id);

--
-- Name: ix_ri_utilization_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ri_utilization_organization_id ON public.ri_utilization USING btree (organization_id);

--
-- Name: ix_ri_utilization_reservation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_ri_utilization_reservation_id ON public.ri_utilization USING btree (reservation_id);

--
-- Name: ix_s3_bucket_analysis_account_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_s3_bucket_analysis_account_id ON public.s3_bucket_analysis USING btree (account_id);

--
-- Name: ix_s3_bucket_analysis_bucket_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_s3_bucket_analysis_bucket_name ON public.s3_bucket_analysis USING btree (bucket_name);

--
-- Name: ix_s3_bucket_analysis_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_s3_bucket_analysis_id ON public.s3_bucket_analysis USING btree (id);

--
-- Name: ix_s3_bucket_analysis_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_s3_bucket_analysis_organization_id ON public.s3_bucket_analysis USING btree (organization_id);

--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);

--
-- Name: ix_users_organization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_organization_id ON public.users USING btree (organization_id);

--
-- Name: pod_metrics_ts_timestamp_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX pod_metrics_ts_timestamp_idx ON public.pod_metrics USING btree ("timestamp" DESC);

--

--

--

--
-- Name: pod_metrics ts_cagg_invalidation_trigger; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER ts_cagg_invalidation_trigger AFTER INSERT OR DELETE OR UPDATE ON public.pod_metrics FOR EACH ROW EXECUTE FUNCTION _timescaledb_functions.continuous_agg_invalidation_trigger('1');

--
-- Name: pod_metrics ts_insert_blocker; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER ts_insert_blocker BEFORE INSERT ON public.pod_metrics FOR EACH ROW EXECUTE FUNCTION _timescaledb_functions.insert_blocker();

--
-- Name: accounts accounts_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.accounts
    ADD CONSTRAINT accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

--
-- Name: agent_actions agent_actions_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_actions
    ADD CONSTRAINT agent_actions_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: api_keys api_keys_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: approval_requests approval_requests_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);

--
-- Name: approval_requests approval_requests_requester_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_requester_id_fkey FOREIGN KEY (requester_id) REFERENCES public.users(id);

--
-- Name: approval_requests approval_requests_reviewer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_reviewer_id_fkey FOREIGN KEY (reviewer_id) REFERENCES public.users(id);

--
-- Name: approvals approvals_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT approvals_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.approvals(id);

--
-- Name: authorized_resources authorized_resources_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorized_resources
    ADD CONSTRAINT authorized_resources_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id);

--
-- Name: authorized_resources authorized_resources_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.authorized_resources
    ADD CONSTRAINT authorized_resources_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public.users(id);

--
-- Name: chaos_experiments chaos_experiments_approved_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chaos_experiments
    ADD CONSTRAINT chaos_experiments_approved_by_user_id_fkey FOREIGN KEY (approved_by_user_id) REFERENCES public.users(id);

--
-- Name: chaos_experiments chaos_experiments_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chaos_experiments
    ADD CONSTRAINT chaos_experiments_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: chaos_experiments chaos_experiments_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chaos_experiments
    ADD CONSTRAINT chaos_experiments_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);

--
-- Name: cluster_cooldowns cluster_cooldowns_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_cooldowns
    ADD CONSTRAINT cluster_cooldowns_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: cluster_metrics cluster_metrics_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_metrics
    ADD CONSTRAINT cluster_metrics_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: cluster_optimization_settings cluster_optimization_settings_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_optimization_settings
    ADD CONSTRAINT cluster_optimization_settings_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: cluster_policies cluster_policies_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_policies
    ADD CONSTRAINT cluster_policies_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: cluster_template_mappings cluster_template_mappings_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_template_mappings
    ADD CONSTRAINT cluster_template_mappings_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: cluster_template_mappings cluster_template_mappings_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_template_mappings
    ADD CONSTRAINT cluster_template_mappings_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.node_templates(id) ON DELETE CASCADE;

--
-- Name: cluster_template_mappings cluster_template_mappings_version_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cluster_template_mappings
    ADD CONSTRAINT cluster_template_mappings_version_id_fkey FOREIGN KEY (version_id) REFERENCES public.node_template_versions(id) ON DELETE CASCADE;

--
-- Name: clusters clusters_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clusters
    ADD CONSTRAINT clusters_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: cost_explorer_sync_status cost_explorer_sync_status_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cost_explorer_sync_status
    ADD CONSTRAINT cost_explorer_sync_status_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: daily_cluster_stats daily_cluster_stats_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_cluster_stats
    ADD CONSTRAINT daily_cluster_stats_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: daily_costs daily_costs_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.daily_costs
    ADD CONSTRAINT daily_costs_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: data_transfer_analysis data_transfer_analysis_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_transfer_analysis
    ADD CONSTRAINT data_transfer_analysis_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: data_transfer_analysis data_transfer_analysis_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_transfer_analysis
    ADD CONSTRAINT data_transfer_analysis_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: agent_identities fk_agent_identities_cluster_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.agent_identities
    ADD CONSTRAINT fk_agent_identities_cluster_id FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: hibernation_schedule_clusters hibernation_schedule_clusters_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hibernation_schedule_clusters
    ADD CONSTRAINT hibernation_schedule_clusters_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: hibernation_schedule_clusters hibernation_schedule_clusters_schedule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hibernation_schedule_clusters
    ADD CONSTRAINT hibernation_schedule_clusters_schedule_id_fkey FOREIGN KEY (schedule_id) REFERENCES public.hibernation_schedules(id);

--
-- Name: hibernation_schedules hibernation_schedules_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hibernation_schedules
    ADD CONSTRAINT hibernation_schedules_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: instances instances_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instances
    ADD CONSTRAINT instances_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: instances instances_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instances
    ADD CONSTRAINT instances_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: lab_experiments lab_experiments_model_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lab_experiments
    ADD CONSTRAINT lab_experiments_model_id_fkey FOREIGN KEY (model_id) REFERENCES public.ml_models(id) ON DELETE CASCADE;

--
-- Name: node_template_versions node_template_versions_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_template_versions
    ADD CONSTRAINT node_template_versions_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.node_templates(id) ON DELETE CASCADE;

--
-- Name: node_templates node_templates_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_templates
    ADD CONSTRAINT node_templates_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

--
-- Name: onboarding_states onboarding_states_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.onboarding_states
    ADD CONSTRAINT onboarding_states_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

--
-- Name: optimization_jobs optimization_jobs_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_jobs
    ADD CONSTRAINT optimization_jobs_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: optimization_strategy optimization_strategy_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimization_strategy
    ADD CONSTRAINT optimization_strategy_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: optimizer_states optimizer_states_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimizer_states
    ADD CONSTRAINT optimizer_states_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: optimizer_states optimizer_states_pending_rightsizing_proposal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.optimizer_states
    ADD CONSTRAINT optimizer_states_pending_rightsizing_proposal_id_fkey FOREIGN KEY (pending_rightsizing_proposal_id) REFERENCES public.rightsizing_proposals(id);

--
-- Name: organization_invitations organization_invitations_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_invitations
    ADD CONSTRAINT organization_invitations_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);

--
-- Name: organization_invitations organization_invitations_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_invitations
    ADD CONSTRAINT organization_invitations_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);

--
-- Name: pod_metrics_old pod_metrics_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pod_metrics_old
    ADD CONSTRAINT pod_metrics_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id) ON DELETE CASCADE;

--
-- Name: rds_instance_analysis rds_instance_analysis_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rds_instance_analysis
    ADD CONSTRAINT rds_instance_analysis_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: rds_instance_analysis rds_instance_analysis_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rds_instance_analysis
    ADD CONSTRAINT rds_instance_analysis_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: ri_utilization ri_utilization_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ri_utilization
    ADD CONSTRAINT ri_utilization_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: ri_utilization ri_utilization_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ri_utilization
    ADD CONSTRAINT ri_utilization_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: rightsizing_proposals rightsizing_proposals_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rightsizing_proposals
    ADD CONSTRAINT rightsizing_proposals_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: role_permissions role_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;

--
-- Name: role_permissions role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;

--
-- Name: roles roles_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: s3_bucket_analysis s3_bucket_analysis_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.s3_bucket_analysis
    ADD CONSTRAINT s3_bucket_analysis_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: s3_bucket_analysis s3_bucket_analysis_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.s3_bucket_analysis
    ADD CONSTRAINT s3_bucket_analysis_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: savings_plan_utilization savings_plan_utilization_account_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.savings_plan_utilization
    ADD CONSTRAINT savings_plan_utilization_account_id_fkey FOREIGN KEY (account_id) REFERENCES public.accounts(id) ON DELETE CASCADE;

--
-- Name: savings_plan_utilization savings_plan_utilization_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.savings_plan_utilization
    ADD CONSTRAINT savings_plan_utilization_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: stateful_rules stateful_rules_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stateful_rules
    ADD CONSTRAINT stateful_rules_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: stateless_runtime_rules stateless_runtime_rules_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stateless_runtime_rules
    ADD CONSTRAINT stateless_runtime_rules_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: substitute_states substitute_states_cluster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.substitute_states
    ADD CONSTRAINT substitute_states_cluster_id_fkey FOREIGN KEY (cluster_id) REFERENCES public.clusters(id);

--
-- Name: tag_automation_logs tag_automation_logs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_automation_logs
    ADD CONSTRAINT tag_automation_logs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: tag_automation_logs tag_automation_logs_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_automation_logs
    ADD CONSTRAINT tag_automation_logs_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.tag_automation_rules(id) ON DELETE CASCADE;

--
-- Name: tag_automation_rules tag_automation_rules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_automation_rules
    ADD CONSTRAINT tag_automation_rules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);

--
-- Name: tag_automation_rules tag_automation_rules_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_automation_rules
    ADD CONSTRAINT tag_automation_rules_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: tag_compliance_scores tag_compliance_scores_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_compliance_scores
    ADD CONSTRAINT tag_compliance_scores_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: tag_scoring_configs tag_scoring_configs_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag_scoring_configs
    ADD CONSTRAINT tag_scoring_configs_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- Name: teams teams_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);

--
-- Name: approvals tickets_approver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT tickets_approver_id_fkey FOREIGN KEY (approver_id) REFERENCES public.users(id);

--
-- Name: approvals tickets_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT tickets_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id);

--
-- Name: approvals tickets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.approvals
    ADD CONSTRAINT tickets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

--
-- Name: user_permissions user_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_permissions
    ADD CONSTRAINT user_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;

--
-- Name: user_permissions user_permissions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_permissions
    ADD CONSTRAINT user_permissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

--
-- Name: users users_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;

--
-- PostgreSQL database dump complete
--

