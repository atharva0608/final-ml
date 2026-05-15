#!/usr/bin/env python3
"""
P-25: Phase 3 Definition-of-Done Validation Runner
====================================================
Checks all P-task contracts against a live backend.

Usage:
    python scripts/validate_plan_phase3.py --cluster-id <uuid> [--base-url http://localhost:8000] [--token <jwt>]

Exit 0 on all pass, exit 1 on any failure.
"""
import argparse
import json
import sys
import requests

CHECKS_PASSED = []
CHECKS_FAILED = []


def _ok(label):
    CHECKS_PASSED.append(label)
    print(f"  PASS  {label}")


def _fail(label, reason=""):
    CHECKS_FAILED.append(label)
    print(f"  FAIL  {label}" + (f" — {reason}" if reason else ""))


def get(base, path, token, params=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = requests.get(f"{base}{path}", headers=headers, params=params, timeout=10)
        return r.status_code, r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    except Exception as exc:
        return 0, {"error": str(exc)}


def check_freshness_fields(label, body):
    data = body.get("data", body)
    for field in ("data_updated_at", "data_age_seconds", "is_stale"):
        if field not in data:
            _fail(label, f"missing field '{field}'")
            return
    _ok(label)


def check_data_ready(label, body):
    data = body.get("data", body)
    if "data_ready" not in data:
        _fail(label, "missing 'data_ready'")
    else:
        _ok(label)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cluster-id", required=True)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    base = args.base_url.rstrip("/") + "/api/v1"
    cid = args.cluster_id
    tok = args.token

    print(f"\n=== Phase 3 Validation  cluster={cid}  base={base} ===\n")

    # P-01/P-02: freshness + data_ready on bin-packing
    print("[P-01/P-02] Freshness + data_ready fields")
    status, body = get(base, "/optimize/nodes/bin-packing", tok, {"cluster_id": cid})
    if status != 200:
        _fail("P-01 bin-packing 200", f"HTTP {status}")
    else:
        check_freshness_fields("P-01 bin-packing freshness", body)
        check_data_ready("P-02 bin-packing data_ready", body)

    # P-04: invalid cluster_id returns 400/422
    print("\n[P-04] Validation guard — invalid cluster_id")
    status, _ = get(base, "/optimize/nodes/bin-packing", tok, {"cluster_id": "bad!"})
    if status in (400, 422):
        _ok("P-04 invalid cluster_id => 400/422")
    else:
        _fail("P-04 invalid cluster_id", f"got HTTP {status}")

    # P-09: state machine values in placement/summary
    print("\n[P-09] Placement state machine values")
    status, body = get(base, "/optimize/workloads/placement/summary", tok, {"cluster_id": cid})
    if status != 200:
        _fail("P-09 placement summary 200", f"HTTP {status}")
    else:
        data = body.get("data", body)
        workloads = data.get("workloads", [])
        valid_states = {"AT_TARGET", "CONVERGING", "DRIFTING", "UNKNOWN"}
        if workloads:
            sample = workloads[0]
            ps = sample.get("placement_status", "")
            if ps in valid_states:
                _ok(f"P-09 placement_status value='{ps}'")
            else:
                _fail("P-09 placement_status", f"unexpected value '{ps}'")
        else:
            _ok("P-09 placement summary (no workloads to check)")

    # P-12: circuit breaker key present in system health
    print("\n[P-12] Circuit breaker field in system/health")
    status, body = get(base, "/optimize/system/health", tok, {"cluster_id": cid})
    if status != 200:
        _fail("P-12 system/health 200", f"HTTP {status}")
    else:
        data = body.get("data", body)
        if "circuit_breaker_active" in data:
            _ok("P-12 circuit_breaker_active present")
        else:
            _fail("P-12 circuit_breaker_active", "field missing from /system/health")

    # P-19: system health endpoint fields
    print("\n[P-19] System health endpoint shape")
    status, body = get(base, "/optimize/system/health", tok, {"cluster_id": cid})
    if status != 200:
        _fail("P-19 /system/health 200", f"HTTP {status}")
    else:
        data = body.get("data", body)
        for field in ("eviction_success_rate_24h", "total_evictions_24h", "drift_resolution_rate",
                      "pc_cycle_count", "circuit_breaker_trips_24h"):
            if field not in data:
                _fail(f"P-19 field '{field}'", "missing")
            else:
                _ok(f"P-19 {field} present")

    # P-23: rate limit (11 rapid requests → 429)
    print("\n[P-23] Rate limit — 11 rapid bin-packing requests")
    last_status = 0
    for _ in range(11):
        last_status, _ = get(base, "/optimize/nodes/bin-packing", tok, {"cluster_id": cid})
    if last_status == 429:
        _ok("P-23 rate limit 429 on 11th request")
    else:
        _fail("P-23 rate limit", f"11th request returned HTTP {last_status}")

    # Summary
    print(f"\n=== Results: {len(CHECKS_PASSED)} passed, {len(CHECKS_FAILED)} failed ===\n")
    if CHECKS_FAILED:
        print("Failed checks:")
        for f in CHECKS_FAILED:
            print(f"  - {f}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
