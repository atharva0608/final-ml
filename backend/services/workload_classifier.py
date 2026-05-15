"""Smart Workload Classification Engine — W1

Priority-ordered 8-step classifier that assigns a TIER_0–TIER_4 to
every controller, plus a confidence score and migration policy.

Tier definitions:
  TIER_0  NEVER_MIGRATE      — DaemonSets, system namespaces
  TIER_1  ANCHORED_MANUAL    — Stateful databases (PVC / operator / StatefulSet)
  TIER_2  SPOT_WITH_CAUTION  — KEDA-managed message consumers
  TIER_3  KEDA_GATED         — Batch / queue workers
  TIER_4  SPOT_ELIGIBLE      — Stateless web / API services (default)

Accuracy hardening implemented:
  GAP-1 — Secondary sidecar strip on received images (W1.5a)
  GAP-2 — OPERATOR_DB_OWNER_KINDS + OPERATOR_LABELS detection (W1.5b)
  GAP-3 — compute_classification_confidence() signal-weighted scoring (W1.5c)
  §6    — readiness_initial_delay_s proxy heuristic (W1.5d)
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# ── Tier constants ─────────────────────────────────────────────────────────────

TIER_0 = 0  # NEVER_MIGRATE
TIER_1 = 1  # ANCHORED_MANUAL
TIER_2 = 2  # SPOT_WITH_CAUTION
TIER_3 = 3  # KEDA_GATED
TIER_4 = 4  # SPOT_ELIGIBLE

TIER_NAMES = {
    TIER_0: "NEVER_MIGRATE",
    TIER_1: "ANCHORED_MANUAL",
    TIER_2: "SPOT_WITH_CAUTION",
    TIER_3: "KEDA_GATED",
    TIER_4: "SPOT_ELIGIBLE",
}

# Migration policies aligned to tier
MIGRATION_POLICY = {
    TIER_0: "block",
    TIER_1: "anchored_only",
    TIER_2: "spot_with_keda_gate",
    TIER_3: "spot_with_keda_gate",
    TIER_4: "spot_eligible",
}

# ── Sidecar filter (W1.5a) ─────────────────────────────────────────────────────
# Secondary filter applied on images received from the agent. Mirrors the
# agent-side _SIDECAR_NAMES set for defense-in-depth (old agents may not filter).
_SIDECAR_IMAGE_PATTERNS = re.compile(
    r"(?:istio[-/]proxy|linkerd[-/]proxy|^envoy:|consul[-/]connect|"
    r"datadog[-/]agent|newrelic[-/]infra|splunk|elastic[-/]apm|"
    r"otel[-/]collector|jaeger[-/]agent|zipkin|fluent(?:d|[-/]bit)|"
    r"filebeat|promtail|vector:|vault[-/]agent|aws[-/]xray|cloud[-/]sql[-/]proxy|"
    r"spot[-/]optimizer[-/]agent)",
    re.IGNORECASE,
)


def _strip_sidecars(images: List[str]) -> List[str]:
    """Remove known sidecar images from a container image list (W1.5a)."""
    return [img for img in images if not _SIDECAR_IMAGE_PATTERNS.search(img)]


# ── Image patterns (W1.4) ──────────────────────────────────────────────────────
# Match against container image strings (registry stripped to basename + tag).
# Ordered so the most specific pattern wins first.
IMAGE_PATTERNS: List[Tuple[str, str]] = [
    # Databases — relational
    (r"(?:postgres|postgresql|pgvecto\.rs|pgbouncer|patroni|spilo)",       "postgresql"),
    (r"(?:mysql|mariadb|percona[-/]server)",                                "mysql"),
    (r"(?:oracle[-/]database|oracledb)",                                    "oracle"),
    (r"(?:mssql|sqlserver)",                                                "sqlserver"),

    # Databases — NoSQL / distributed
    (r"(?:mongo(?:db)?|percona[-/]server-mongodb)",                        "mongodb"),
    (r"(?:redis(?:[-/]enterprise)?|keydb|dragonfly)",                      "redis"),
    (r"(?:cassandra|scylladb|datastax[-/]dse)",                            "cassandra"),
    (r"(?:elasticsearch|opensearch|elastic)",                               "elasticsearch"),
    (r"(?:couchdb|couchbase)",                                              "couchdb"),
    (r"(?:influxdb|prometheus(?:\s|:|/|$))",                               "timeseries_db"),
    (r"(?:neo4j|tigergraph|dgraph)",                                       "graph_db"),
    (r"(?:etcd|consul(?:/|:))",                                            "etcd"),
    (r"(?:zookeeper|confluent[-/]zookeeper)",                              "zookeeper"),

    # Message queues / streaming — KEDA hints
    (r"(?:rabbitmq|bitnami/rabbitmq)",                                     "rabbitmq"),
    (r"(?:kafka|confluent[-/]kafka|strimzi)",                              "kafka"),
    (r"(?:natsio|nats[-/]server)",                                         "nats"),
    (r"(?:activemq)",                                                      "activemq"),

    # Worker / batch — TIER_3 hints
    (r"(?:sidekiq)",                                                       "sidekiq_worker"),
    (r"(?:celery(?:[-/]worker)?)",                                         "celery_worker"),
    (r"(?:resque)",                                                        "resque_worker"),
    (r"(?:dramatiq)",                                                      "dramatiq_worker"),
    (r"(?:bull|bullmq)",                                                   "bull_worker"),
    (r"(?:temporal[-/]worker|worker[-/]temporal)",                         "temporal_worker"),

    # Web / API — TIER_4 hints (whitelist, final check)
    (r"(?:nginx|apache|httpd|caddy|traefik(?!/proxy))",                   "web_proxy"),
    (r"(?:node(?:js)?[-/]app|express|next(?:js)?|nuxt)",                  "nodejs_app"),
    (r"(?:django|flask|fastapi(?![-/]app)|gunicorn|uvicorn)",             "python_web"),
    (r"(?:rails|puma|unicorn|passenger)",                                  "rails_app"),
    (r"(?:spring[-/]boot|quarkus|micronaut|helidon)",                     "jvm_web"),
]

_COMPILED_IMAGE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), app_type)
    for pattern, app_type in IMAGE_PATTERNS
]

# Tiers implying stateful behaviour from image match
_DB_APP_TYPES = frozenset({
    "postgresql", "mysql", "oracle", "sqlserver", "mongodb", "redis",
    "cassandra", "elasticsearch", "couchdb", "timeseries_db",
    "graph_db", "etcd", "zookeeper",
})
# Tiers implying queue / messaging
_QUEUE_APP_TYPES = frozenset({"rabbitmq", "kafka", "nats", "activemq"})
# Tiers implying workers
_WORKER_APP_TYPES = frozenset({
    "sidekiq_worker", "celery_worker", "resque_worker",
    "dramatiq_worker", "bull_worker", "temporal_worker",
})

# ── Port patterns (W1.4) ───────────────────────────────────────────────────────
PORT_PATTERNS: Dict[int, str] = {
    5432: "postgresql",  5433: "postgresql",
    3306: "mysql",       3307: "mysql",
    27017: "mongodb",    27018: "mongodb",    27019: "mongodb",
    6379: "redis",       6380: "redis",
    9200: "elasticsearch",   9300: "elasticsearch",
    9042: "cassandra",   7000: "cassandra",
    2181: "zookeeper",   2888: "zookeeper",   3888: "zookeeper",
    2379: "etcd",        2380: "etcd",
    5672: "rabbitmq",    5671: "rabbitmq",    15672: "rabbitmq",
    9092: "kafka",       9093: "kafka",
    4222: "nats",
    8086: "influxdb",    8088: "influxdb",
    7474: "graph_db",    7473: "graph_db",
    1521: "oracle",
    1433: "sqlserver",
}

# Ports for database types that imply TIER_1
_DB_PORTS = frozenset(PORT_PATTERNS.keys()) - {15672}  # exclude management UI

# ── Env-var patterns for leader-election / HA hints (W1.4) ────────────────────
LEADER_ELECTION_ENV_PATTERNS = re.compile(
    r"(?:leader[-_]election|ha[-_]enabled|pg[-_]replication|"
    r"patroni[-_]scope|cluster[-_]mode|redis[-_]sentinel|"
    r"rabbitmq[-_]erlang[-_]cookie|kafka[-_]node[-_]id|"
    r"etcd[-_]initial[-_]cluster)",
    re.IGNORECASE,
)

# ── Operator CRD owner kinds (W1.5b) ──────────────────────────────────────────
# If a pod's owner chain resolves to one of these CRD kinds → TIER_1 (database)
OPERATOR_DB_OWNER_KINDS: Dict[str, str] = {
    "Cluster":               "postgresql",     # CloudNativePG
    "PostgresCluster":       "postgresql",     # CrunchyData Postgres Operator
    "PerconaServerMongoDB":  "mongodb",        # Percona MongoDB Operator
    "PerconaXtraDBCluster":  "mysql",          # Percona XtraDB Cluster
    "postgresql":            "postgresql",     # Zalando Postgres Operator
    "MongoDBCommunity":      "mongodb",        # MongoDB Community Operator
    "MongoDB":               "mongodb",        # MongoDB Enterprise Operator
    "MySQLCluster":          "mysql",          # MySQL Operator
    "RedisFailover":         "redis",          # Spotahome Redis Operator
    "Redis":                 "redis",          # Redis Operator
    "RabbitmqCluster":       "rabbitmq",       # RabbitMQ Cluster Operator
    "Kafka":                 "kafka",          # Strimzi
    "ElasticsearchCluster":  "elasticsearch",  # ECK
    "Kibana":                "elasticsearch",  # ECK (read-only)
    "CassandraDatacenter":   "cassandra",      # DataStax CassandraOperator
    "ScyllaCluster":         "cassandra",      # Scylla Operator
}

# Operator label key patterns that indicate the pod is database-managed (W1.5b)
OPERATOR_LABELS: Dict[str, str] = {
    "cnpg.io/cluster":                                         "postgresql",
    "postgres-operator.crunchydata.com/cluster":              "postgresql",
    "app.kubernetes.io/managed-by=percona-server-mongodb-operator":  "mongodb",
    "app.kubernetes.io/managed-by=strimzi-cluster-operator":  "kafka",
    "app.kubernetes.io/managed-by=rabbitmq-cluster-operator": "rabbitmq",
    "app.kubernetes.io/managed-by=mysql-operator":            "mysql",
    "app.kubernetes.io/managed-by=elastic-operator":          "elasticsearch",
    "app.kubernetes.io/managed-by=scylla-operator":           "cassandra",
    "app.kubernetes.io/managed-by=redis-operator":            "redis",
}

# Namespaces that always → TIER_0
_SYSTEM_NAMESPACES = frozenset({
    "kube-system", "kube-public", "kube-node-lease",
    "karpenter", "spot-optimizer", "cert-manager", "monitoring",
    "istio-system", "linkerd",
})

# KEDA trigger types that imply TIER_2 (queue workers with back-pressure)
_KEDA_QUEUE_TRIGGER_TYPES = frozenset({
    "rabbitmq", "kafka", "sqs", "azure-servicebus", "google-cloud-pubsub",
    "redis", "nats-jetstream", "activemq",
})

# ── Annotation override key ────────────────────────────────────────────────────
_TIER_ANNOTATION = "spot-optimizer/tier"


# ── Confidence signal weights (W1.5c / GAP-3) ─────────────────────────────────
_SIGNAL_WEIGHTS: Dict[str, float] = {
    "annotation_override":  1.0,
    "crd_owner_match":      0.40,
    "label_operator_match": 0.35,
    "pvc_present":          0.20,
    "image_match":          0.30,
    "port_match":           0.15,
    "env_key_match":        0.15,
    "controller_kind":      0.30,
    "namespace_system":     0.50,
    "keda_managed":         0.30,
}


def compute_classification_confidence(
    signals_matched: List[str],
    tier: int,
) -> float:
    """
    Compute a 0.0–1.0 confidence score from matched classification signals.

    Single-signal TIER_1 classifications are penalised by 50% because a lone
    signal (e.g. only controller_kind == StatefulSet) is easy to get wrong.
    """
    if "annotation_override" in signals_matched:
        return 1.0

    total = sum(_SIGNAL_WEIGHTS.get(s, 0.0) for s in signals_matched)
    confidence = min(total, 1.0)

    # Penalise risky low-signal TIER_1 classifications
    if tier <= TIER_1 and len(signals_matched) < 2:
        confidence *= 0.5

    return round(confidence, 2)


# ── Main classifier ────────────────────────────────────────────────────────────


def classify_workload(profile: Dict[str, Any], pod_spec_fields: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Classify a workload controller into one of TIER_0–TIER_4.

    Priority order (first match wins):
      1. Manual annotation override → use directly
      2. DaemonSet → TIER_0
      3. System namespace → TIER_0
      4. StatefulSet + (PVC OR leader_election_env OR CRD owner OR operator label) → TIER_1
      5. StatefulSet + image matches DB pattern → TIER_1
      6. KEDA-managed + trigger_type in queue set → TIER_2
      7. Image matches known worker pattern → TIER_3
      8. Default Deployment → TIER_4

    Args:
        profile:        Dict from build_workload_profile() — must include
                        controller_kind, namespace, pvc_count, keda_managed,
                        keda_trigger_types, crd_owner_kind, pod_labels,
                        readiness_initial_delay_s.
        pod_spec_fields: Optional dict with container_images, container_ports,
                         env_var_keys from agent W1.1/W1.2 payload.
                         When absent (old agents), image/port heuristics are skipped.

    Returns:
        Dict with: tier, tier_name, detected_app_type, migration_policy,
                   classification_reasons, classification_confidence.
    """
    if pod_spec_fields is None:
        pod_spec_fields = {}

    controller_kind  = profile.get("controller_kind", "Deployment")
    namespace        = profile.get("namespace", "default")
    pvc_count        = profile.get("pvc_count", 0) or 0
    volume_claim_templates = profile.get("volume_claim_templates", False)  # Task 3.3
    keda_managed     = profile.get("keda_managed", False)
    keda_triggers    = profile.get("scaled_object_trigger_types") or []
    crd_owner_kind   = profile.get("crd_owner_kind")      # from W1.6a owner resolution
    pod_labels       = profile.get("pod_labels") or {}
    annotations      = profile.get("pod_annotations") or {}
    readiness_delay  = profile.get("readiness_initial_delay_s") or 0
    agent_version    = pod_spec_fields.get("agent_version", "0.0.0")

    # W1.9 — Backward compatibility flag: if agent is old (< 1.2.0), skip
    # image/port heuristics because those fields are absent.
    _have_new_agent_data = _agent_version_gte(agent_version, "1.2.0")
    raw_images = pod_spec_fields.get("container_images") or []
    raw_ports  = pod_spec_fields.get("container_ports") or []
    env_keys   = pod_spec_fields.get("env_var_keys") or []

    # W1.5a — Strip sidecars from images even if agent filtered already.
    images = _strip_sidecars(raw_images) if _have_new_agent_data else []
    port_numbers = {p["container_port"] for p in raw_ports if isinstance(p, dict)} if _have_new_agent_data else set()

    signals: List[str] = []
    reasons: List[str] = []
    detected_app_type: Optional[str] = None
    tier: int = TIER_4

    # ── Step 1: Manual annotation override ─────────────────────────────────────
    annotation_tier_raw = annotations.get(_TIER_ANNOTATION)
    if annotation_tier_raw is not None:
        try:
            annotation_tier = int(annotation_tier_raw)
            if TIER_0 <= annotation_tier <= TIER_4:
                signals.append("annotation_override")
                tier = annotation_tier
                reasons.append(f"Manual annotation {_TIER_ANNOTATION}={annotation_tier}")
                return _build_result(tier, detected_app_type, signals, reasons)
        except (ValueError, TypeError):
            pass  # Invalid annotation value — ignore

    # ── Step 2: DaemonSet → TIER_0 ─────────────────────────────────────────────
    if controller_kind == "DaemonSet":
        signals.append("controller_kind")
        reasons.append("DaemonSet — runs on every node, never migrate")
        return _build_result(TIER_0, "daemonset", signals, reasons)

    # ── Step 3: System namespace → TIER_0 ──────────────────────────────────────
    if namespace in _SYSTEM_NAMESPACES:
        signals.append("namespace_system")
        reasons.append(f"System namespace: {namespace}")
        return _build_result(TIER_0, "system", signals, reasons)

    # ── Step 4: StatefulSet + strong stateful signal → TIER_1 ──────────────────
    if controller_kind in ("StatefulSet", "OperatorStateful"):
        is_tier1 = False

        # Task 3.3: volumeClaimTemplates on the controller spec guarantees statefulness
        if volume_claim_templates:
            signals.append("volumeClaimTemplates")
            detected_app_type = detected_app_type or "stateful_with_pvc"
            reasons.append("StatefulSet has volumeClaimTemplates (guaranteed PVC per replica)")
            return _build_result(TIER_1, detected_app_type, signals, reasons)

        if pvc_count and pvc_count > 0:
            is_tier1 = True
            signals.append("pvc_present")
            detected_app_type = detected_app_type or "stateful_with_pvc"
            reasons.append(f"StatefulSet with {pvc_count} PVC(s)")

        # Leader-election env vars
        matching_env = [k for k in env_keys if LEADER_ELECTION_ENV_PATTERNS.search(k)]
        if matching_env:
            is_tier1 = True
            signals.append("env_key_match")
            detected_app_type = detected_app_type or "stateful_ha"
            reasons.append(f"Leader-election env vars: {matching_env[:3]}")

        # CRD operator owner (W1.5b)
        if crd_owner_kind and crd_owner_kind in OPERATOR_DB_OWNER_KINDS:
            is_tier1 = True
            app_type = OPERATOR_DB_OWNER_KINDS[crd_owner_kind]
            signals.append("crd_owner_match")
            detected_app_type = app_type
            reasons.append(f"Operator CRD owner kind: {crd_owner_kind} → {app_type}")

        # Operator labels on pod (W1.5b)
        label_app = _check_operator_labels(pod_labels)
        if label_app:
            is_tier1 = True
            signals.append("label_operator_match")
            detected_app_type = detected_app_type or label_app
            reasons.append(f"Operator label detected: {label_app}")

        if is_tier1:
            signals.append("controller_kind")
            return _build_result(TIER_1, detected_app_type, signals, reasons)

    # ── Step 5: StatefulSet + image matches DB pattern → TIER_1 ────────────────
    if controller_kind in ("StatefulSet", "OperatorStateful") and images:
        app_type, matched_reason = _match_images(images)
        if app_type and app_type in _DB_APP_TYPES:
            signals += ["controller_kind", "image_match"]
            detected_app_type = app_type
            reasons.append(f"StatefulSet with DB image: {matched_reason}")
            return _build_result(TIER_1, detected_app_type, signals, reasons)

    # ── Deployment: check images/ports for DB indicators → TIER_1 ──────────────
    # A Deployment can run a DB too (unusual but possible with operator-less setups)
    if controller_kind == "Deployment" and images:
        app_type, matched_reason = _match_images(images)
        if app_type and app_type in _DB_APP_TYPES:
            signals.append("image_match")
            detected_app_type = app_type
            reasons.append(f"Deployment with DB image: {matched_reason}")
            # Also require a port or PVC confirmation for Deployment to be TIER_1
            db_port_match = _match_ports(port_numbers)
            pvc_gate = (pvc_count or 0) > 0
            if db_port_match or pvc_gate:
                if db_port_match:
                    signals.append("port_match")
                    reasons.append(f"DB port: {db_port_match}")
                if pvc_gate:
                    signals.append("pvc_present")
                return _build_result(TIER_1, detected_app_type, signals, reasons)

    # ── CRD owner without StatefulSet (e.g. CloudNativePG creates Pods directly)
    if crd_owner_kind and crd_owner_kind in OPERATOR_DB_OWNER_KINDS:
        app_type = OPERATOR_DB_OWNER_KINDS[crd_owner_kind]
        signals.append("crd_owner_match")
        detected_app_type = app_type
        reasons.append(f"DB operator CRD owner: {crd_owner_kind}")
        return _build_result(TIER_1, detected_app_type, signals, reasons)

    # ── Operator labels (non-StatefulSet pod — e.g. operator sidecar) → TIER_1
    label_app = _check_operator_labels(pod_labels)
    if label_app and label_app in _DB_APP_TYPES | _QUEUE_APP_TYPES:
        signals.append("label_operator_match")
        detected_app_type = label_app
        reasons.append(f"DB/queue operator label: {label_app}")
        # Queues get TIER_2, DBs get TIER_1
        out_tier = TIER_2 if label_app in _QUEUE_APP_TYPES else TIER_1
        return _build_result(out_tier, detected_app_type, signals, reasons)

    # ── Step 6: KEDA-managed + queue trigger → TIER_2 ──────────────────────────
    if keda_managed:
        signals.append("keda_managed")
        queue_triggers = [t for t in keda_triggers if t.lower() in _KEDA_QUEUE_TRIGGER_TYPES]
        if queue_triggers:
            reasons.append(f"KEDA-managed with queue triggers: {queue_triggers}")
            detected_app_type = "keda_queue_worker"
            return _build_result(TIER_2, detected_app_type, signals, reasons)
        # KEDA managed but non-queue trigger → still at least TIER_3
        reasons.append("KEDA-managed (non-queue trigger)")
        tier = TIER_3

    # ── Step 7: Image matches known worker pattern → TIER_3 ────────────────────
    if images:
        app_type, matched_reason = _match_images(images)
        if app_type and app_type in _WORKER_APP_TYPES:
            signals.append("image_match")
            detected_app_type = app_type
            reasons.append(f"Worker image: {matched_reason}")
            tier = min(tier, TIER_3)

    # ── Task 1.6 — Init container statefulness detection ───────────────────────
    # Init containers that are DB migration tools (Flyway, Liquibase, Alembic…)
    # indicate the main container uses a database → classify as TIER_1.
    # Requires agent 1.1.8+ which sends init_containers in the pod payload.
    _INIT_DB_PATTERNS = re.compile(
        r"flyway|liquibase|alembic|goose|dbmate|prisma.*migrat|migrate|sqitch",
        re.IGNORECASE,
    )
    init_containers = pod_spec_fields.get("init_containers") or []
    if init_containers and tier > TIER_1:
        for ic in init_containers:
            ic_image = ic.get("image", "") if isinstance(ic, dict) else ""
            if _INIT_DB_PATTERNS.search(ic_image):
                signals.append("init_container_db_migration")
                detected_app_type = detected_app_type or "stateful_with_db_migration"
                reasons.append(f"Init container '{ic_image}' is a DB migration tool → TIER_1")
                return _build_result(TIER_1, detected_app_type, signals, reasons)
            # Also check if init container exposes a known DB port
            for port_entry in (ic.get("ports") or [] if isinstance(ic, dict) else []):
                port_num = port_entry.get("containerPort") if isinstance(port_entry, dict) else None
                if port_num and port_num in _DB_PORTS:
                    signals.append("init_container_db_port")
                    detected_app_type = detected_app_type or "stateful_with_db"
                    reasons.append(f"Init container connects to DB port {port_num} → TIER_1")
                    return _build_result(TIER_1, detected_app_type, signals, reasons)

    # ── W1.5d — §6 readiness_delay heuristic → slow-start upgrades to TIER_3 ───
    # Only promote if the workload also has a stateful indicator (PVC etc.).
    # Pure ML model loading (large model warmup) is stateless slow-start —
    # it should stay TIER_4 to remain spot-eligible.
    if readiness_delay and readiness_delay >= 60 and tier == TIER_4:
        has_stateful_signal = "pvc_present" in signals or pvc_count > 0
        if has_stateful_signal:
            tier = TIER_3
            reasons.append(
                f"Long readiness delay ({readiness_delay}s) with stateful signal → TIER_3 (cautious migration)"
            )
        # else: stateless slow-start (ML model loading) — remain TIER_4

    # ── Step 8: Default ─────────────────────────────────────────────────────────
    if not reasons:
        reasons.append("Default TIER_4 — no stateful signals detected")
    if tier == TIER_4 and not detected_app_type:
        # Try to infer a friendly app type from images
        if images:
            app_type, _ = _match_images(images)
            detected_app_type = app_type or "stateless_service"
        else:
            detected_app_type = "stateless_service"

    return _build_result(tier, detected_app_type, signals, reasons)


# ── Private helpers ────────────────────────────────────────────────────────────


def _build_result(
    tier: int,
    detected_app_type: Optional[str],
    signals: List[str],
    reasons: List[str],
) -> Dict[str, Any]:
    confidence = compute_classification_confidence(signals, tier)
    return {
        "tier":                     tier,
        "tier_name":               TIER_NAMES[tier],
        "detected_app_type":       detected_app_type or "unknown",
        "migration_policy":        MIGRATION_POLICY[tier],
        "classification_reasons":  reasons,
        "classification_confidence": confidence,
    }


def _match_images(images: List[str]) -> Tuple[Optional[str], Optional[str]]:
    """Return (app_type, reason_string) for the first matched image pattern."""
    for image in images:
        # Strip registry prefix for cleaner matching: "registry.io/org/name:tag" → "name:tag"
        parts = image.split("/")
        image_short = parts[-1] if parts else image
        # Also match against full image in case of multi-part names
        for pattern, app_type in _COMPILED_IMAGE_PATTERNS:
            if pattern.search(image_short) or pattern.search(image):
                return app_type, f"{image_short} matched /{pattern.pattern}/"
    return None, None


def _match_ports(port_numbers: set) -> Optional[int]:
    """Return the first known DB port found, or None."""
    for port in port_numbers:
        if port in _DB_PORTS:
            return port
    return None


def _check_operator_labels(pod_labels: Dict[str, str]) -> Optional[str]:
    """
    Check pod labels against OPERATOR_LABELS to detect operator-managed databases.
    Handles both bare key matching ('cnpg.io/cluster') and key=value matching.
    """
    for label_pattern, app_type in OPERATOR_LABELS.items():
        if "=" in label_pattern:
            key, val = label_pattern.split("=", 1)
            if pod_labels.get(key) == val:
                return app_type
        else:
            if label_pattern in pod_labels:
                return app_type
    return None


def _agent_version_gte(version_str: str, min_version: str) -> bool:
    """Return True if version_str >= min_version (simple 3-part semver compare)."""
    def _parts(v: str):
        try:
            return tuple(int(x) for x in v.split(".")[:3])
        except (ValueError, AttributeError):
            return (0, 0, 0)

    return _parts(version_str) >= _parts(min_version)
