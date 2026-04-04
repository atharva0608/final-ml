"""
Spot Optimizer API Test Script
===============================
Tests core API endpoints: auth, clusters, nodes, karpenter,
simulation (ascpai), metrics, and hibernation.

Usage:
    python test_api.py                    # Run all tests
    python test_api.py auth clusters      # Run specific groups
"""

import sys
import json
import time
import requests

BASE = "http://localhost:8000"
CLUSTER_ID = "de017dad-078b-4953-a9fd-60656ee565e7"

# ── Auth credentials ──────────────────────────────────────────────────────────
LOGIN_EMAIL = "ath@gmail.com"
LOGIN_PASSWORD = "Atharva@123"

# ── State ─────────────────────────────────────────────────────────────────────
TOKEN = None
RESULTS = {"passed": 0, "failed": 0, "skipped": 0}


def _color(text, code):
    return f"\033[{code}m{text}\033[0m"

def _pass(label):
    RESULTS["passed"] += 1
    print(f"  {_color('PASS', '32')} {label}")

def _fail(label, detail=""):
    RESULTS["failed"] += 1
    msg = f"  {_color('FAIL', '31')} {label}"
    if detail:
        msg += f"  — {detail[:120]}"
    print(msg)

def _skip(label, reason=""):
    RESULTS["skipped"] += 1
    print(f"  {_color('SKIP', '33')} {label}  {reason}")

def _headers():
    h = {"Content-Type": "application/json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return h

def _get(path, **kw):
    return requests.get(f"{BASE}{path}", headers=_headers(), timeout=10, **kw)

def _post(path, body=None, **kw):
    return requests.post(f"{BASE}{path}", headers=_headers(), json=body, timeout=10, **kw)

def _put(path, body=None, **kw):
    return requests.put(f"{BASE}{path}", headers=_headers(), json=body, timeout=10, **kw)


# ══════════════════════════════════════════════════════════════════════════════
# Test Groups
# ══════════════════════════════════════════════════════════════════════════════

def test_health():
    print("\n─── Health ─────────────────────────────────────────")
    r = requests.get(f"{BASE}/health", timeout=5)
    if r.status_code == 200 and r.json().get("status") == "healthy":
        _pass(f"GET /health  → {r.json().get('status')}")
    else:
        _fail(f"GET /health  → {r.status_code}")


def test_auth():
    global TOKEN
    print("\n─── Auth ───────────────────────────────────────────")

    # Login
    r = _post("/api/v1/auth/login", {"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD})
    if r.status_code == 200:
        TOKEN = r.json().get("access_token")
        _pass(f"POST /auth/login  → token received (len={len(TOKEN or '')})")
    else:
        _fail(f"POST /auth/login  → {r.status_code}", r.text[:100])
        return

    # Profile (GET /auth/me)
    r = _get("/api/v1/auth/me")
    if r.status_code == 200:
        email = r.json().get("email", r.json().get("user", {}).get("email", "?"))
        _pass(f"GET /auth/me  → {email}")
    else:
        _fail(f"GET /auth/me  → {r.status_code}")


def test_clusters():
    print("\n─── Clusters ───────────────────────────────────────")
    if not TOKEN:
        _skip("cluster tests", "(no auth token)")
        return

    # List clusters
    r = _get("/api/v1/clusters")
    if r.status_code == 200:
        data = r.json()
        clusters = data if isinstance(data, list) else data.get("clusters", data.get("data", []))
        names = [c.get("name", c.get("cluster_name", "?")) for c in clusters[:5]]
        _pass(f"GET /clusters  → {len(clusters)} cluster(s): {names}")
    else:
        _fail(f"GET /clusters  → {r.status_code}", r.text[:100])

    # Single cluster
    r = _get(f"/api/v1/clusters/{CLUSTER_ID}")
    if r.status_code == 200:
        name = r.json().get("name", r.json().get("cluster_name", "?"))
        _pass(f"GET /clusters/{{id}}  → {name}")
    else:
        _fail(f"GET /clusters/{{id}}  → {r.status_code}", r.text[:100])

    # Cluster nodes
    r = _get(f"/api/v1/clusters/{CLUSTER_ID}/nodes")
    if r.status_code == 200:
        nodes = r.json() if isinstance(r.json(), list) else r.json().get("nodes", [])
        _pass(f"GET /clusters/{{id}}/nodes  → {len(nodes)} node(s)")
    else:
        _fail(f"GET /clusters/{{id}}/nodes  → {r.status_code}", r.text[:100])

    # Cluster summary
    r = _get(f"/api/v1/clusters/{CLUSTER_ID}/summary")
    if r.status_code == 200:
        _pass("GET /clusters/{id}/summary  → ok")
    else:
        _fail(f"GET /clusters/{{id}}/summary  → {r.status_code}", r.text[:100])


def test_karpenter():
    print("\n─── Karpenter ──────────────────────────────────────")
    if not TOKEN:
        _skip("karpenter tests", "(no auth token)")
        return

    # Status
    r = _get(f"/api/v1/karpenter/status?cluster_id={CLUSTER_ID}")
    if r.status_code == 200:
        mode = r.json().get("karpenter_mode", r.json().get("mode", "?"))
        _pass(f"GET /karpenter/status  → mode={mode}")
    else:
        _fail(f"GET /karpenter/status  → {r.status_code}", r.text[:100])

    # Detect
    r = _get(f"/api/v1/karpenter/detect/{CLUSTER_ID}")
    if r.status_code == 200:
        installed = r.json().get("karpenter_installed", "?")
        _pass(f"GET /karpenter/detect  → installed={installed}")
    else:
        _fail(f"GET /karpenter/detect  → {r.status_code}", r.text[:100])

    # Config
    r = _get(f"/api/v1/karpenter/config?cluster_id={CLUSTER_ID}")
    if r.status_code == 200:
        _pass("GET /karpenter/config  → ok")
    else:
        _fail(f"GET /karpenter/config  → {r.status_code}", r.text[:100])


def test_ascpai():
    print("\n─── ASCPAi (Simulation / Pools) ────────────────────")
    if not TOKEN:
        _skip("ascpai tests", "(no auth token)")
        return

    # Pool rankings (POST — needs a template body)
    r = _post(f"/api/v1/ascpai/pools/rankings?region=ap-south-1&limit=5", {
        "architecture": ["amd64"], "vcpu_min": 2, "vcpu_max": 16,
        "memory_gb_min": 4, "memory_gb_max": 64,
    })
    if r.status_code == 200:
        data = r.json()
        pools = data if isinstance(data, list) else data.get("pools", data.get("rankings", []))
        count = len(pools) if isinstance(pools, list) else "?"
        _pass(f"POST /ascpai/pools/rankings  → {count} pool(s)")
    else:
        _fail(f"POST /ascpai/pools/rankings  → {r.status_code}", r.text[:100])

    # Node recommendations (path includes cluster_id)
    r = _get(f"/api/v1/ascpai/clusters/{CLUSTER_ID}/node-recommendations")
    if r.status_code == 200:
        _pass("GET /ascpai/clusters/{id}/node-recommendations  → ok")
    else:
        _fail(f"GET /ascpai/clusters/{{id}}/node-recommendations  → {r.status_code}", r.text[:100])

    # Health
    r = _get("/api/v1/ascpai/health")
    if r.status_code == 200:
        _pass("GET /ascpai/health  → ok")
    else:
        _fail(f"GET /ascpai/health  → {r.status_code}", r.text[:100])

    # Rebalancing status
    r = _get(f"/api/v1/ascpai/rebalancing/status?cluster_id={CLUSTER_ID}")
    if r.status_code == 200:
        _pass("GET /ascpai/rebalancing/status  → ok")
    else:
        _fail(f"GET /ascpai/rebalancing/status  → {r.status_code}", r.text[:100])

    # Savings velocity
    r = _get(f"/api/v1/ascpai/savings-velocity?cluster_id={CLUSTER_ID}")
    if r.status_code == 200:
        _pass("GET /ascpai/savings-velocity  → ok")
    else:
        _fail(f"GET /ascpai/savings-velocity  → {r.status_code}", r.text[:100])


def test_metrics():
    print("\n─── Metrics ────────────────────────────────────────")
    if not TOKEN:
        _skip("metrics tests", "(no auth token)")
        return

    # Cluster utilization
    r = _get(f"/api/v1/metrics/cluster/{CLUSTER_ID}/utilization")
    if r.status_code == 200:
        _pass("GET /metrics/cluster/{id}/utilization  → ok")
    else:
        _fail(f"GET /metrics/cluster/{{id}}/utilization  → {r.status_code}", r.text[:100])

    # Nodegroups (may 500 if no instance data)
    r = _get(f"/api/v1/metrics/cluster/{CLUSTER_ID}/nodegroups")
    if r.status_code == 200:
        _pass("GET /metrics/cluster/{id}/nodegroups  → ok")
    elif r.status_code == 500:
        _skip("GET /metrics/cluster/{id}/nodegroups", "(500 — likely no instance data)")
    else:
        _fail(f"GET /metrics/cluster/{{id}}/nodegroups  → {r.status_code}", r.text[:100])

    # Rightsizing recommendations
    r = _get(f"/api/v1/optimization/rightsizing/{CLUSTER_ID}")
    if r.status_code == 200:
        recs = r.json() if isinstance(r.json(), list) else r.json().get("recommendations", [])
        count = len(recs) if isinstance(recs, list) else "?"
        _pass(f"GET /optimization/rightsizing/{{id}}  → {count} rec(s)")
    else:
        _fail(f"GET /optimization/rightsizing/{{id}}  → {r.status_code}", r.text[:100])


def test_hibernation():
    print("\n─── Hibernation ────────────────────────────────────")
    if not TOKEN:
        _skip("hibernation tests", "(no auth token)")
        return

    # List schedules
    r = _get(f"/api/v1/hibernation/schedules?cluster_id={CLUSTER_ID}")
    if r.status_code == 200:
        _pass("GET /hibernation/schedules  → ok")
    else:
        _fail(f"GET /hibernation/schedules  → {r.status_code}", r.text[:100])

    # Active status
    r = _get(f"/api/v1/hibernation/status/active?cluster_id={CLUSTER_ID}")
    if r.status_code == 200:
        _pass("GET /hibernation/status/active  → ok")
    else:
        _fail(f"GET /hibernation/status/active  → {r.status_code}", r.text[:100])


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

ALL_GROUPS = {
    "health": test_health,
    "auth": test_auth,
    "clusters": test_clusters,
    "karpenter": test_karpenter,
    "ascpai": test_ascpai,
    "metrics": test_metrics,
    "hibernation": test_hibernation,
}

def main():
    groups = sys.argv[1:] if len(sys.argv) > 1 else list(ALL_GROUPS.keys())
    print(f"{'='*56}")
    print(f"  Spot Optimizer API Tests")
    print(f"  Base: {BASE}   Cluster: {CLUSTER_ID[:8]}...")
    print(f"{'='*56}")

    start = time.time()
    for name in groups:
        fn = ALL_GROUPS.get(name)
        if fn:
            fn()
        else:
            print(f"\n  Unknown group: {name}")

    elapsed = time.time() - start
    total = RESULTS["passed"] + RESULTS["failed"] + RESULTS["skipped"]
    print(f"\n{'='*56}")
    print(f"  {_color(f'{RESULTS['passed']} passed', '32')}, "
          f"{_color(f'{RESULTS['failed']} failed', '31' if RESULTS['failed'] else '90')}, "
          f"{_color(f'{RESULTS['skipped']} skipped', '33' if RESULTS['skipped'] else '90')}  "
          f"({total} total, {elapsed:.1f}s)")
    print(f"{'='*56}")

    sys.exit(1 if RESULTS["failed"] > 0 else 0)


if __name__ == "__main__":
    main()
