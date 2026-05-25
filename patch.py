import sys
import re

file_path = "backend/api/optimize_routes.py"
with open(file_path, "r") as f:
    content = f.read()

new_func = """@router.get("/nodes/bin-packing", summary="Per-node CPU/memory packing density")
async def get_node_bin_packing(
    cluster_id: str = Query(...),
    db: Session = Depends(get_db),
):
    validate_cluster_id(cluster_id)
    assert_cluster_access(cluster_id, db)

    from backend.core.redis_client import get_redis_client as _rl_rc
    _rl_redis = _safe_fetch(_rl_rc, None, "rate_limit_redis_bin_packing")
    check_rate_limit(_rl_redis, f"spot:ratelimit:bin_packing:{cluster_id}", 10, 60)

    if _rl_redis:
        import json
        cached = _rl_redis.get(f"spot:bin_packing:{cluster_id}")
        if cached:
            return ok(json.loads(cached).get("data", {}))

    return not_ready(
        "node_allocatable_data_pending",
        partial_data={"cluster_id": cluster_id, "nodes": [], "stale_nodes_excluded": 0, "consolidation_candidates": None},
    )
"""

pattern = re.compile(
    r'@router\.get\("/nodes/bin-packing", summary="Per-node CPU/memory packing density"\)\nasync def get_node_bin_packing\((?:.*?)\n    \)(?:.*?)return ok\((?:.*?)\)\n',
    re.DOTALL
)

if pattern.search(content):
    content = pattern.sub(new_func + "\n", content)
    with open(file_path, "w") as f:
        f.write(content)
    print("Patched successfully")
else:
    print("Could not find pattern")

