"""Verify R-9: Per-node alternatives positive/negative split + Market-view EV ranking."""
import json
import sys
sys.path.insert(0, '/app')

import requests

BASE = 'http://localhost:8000'

# Auth
resp = requests.post(f'{BASE}/api/v1/auth/login', json={"email": "admin@spotoptimizer.com", "password": "admin123"})
if resp.status_code != 200:
    print(f"Auth failed: {resp.status_code}")
    sys.exit(1)
token = resp.json()['access_token']
headers = {"Authorization": f"Bearer {token}"}
print("Auth OK\n")

# Get clusters
from backend.models.base import get_db
from backend.models.cluster import Cluster
db = next(get_db())
clusters = db.query(Cluster).all()
for c in clusters:
    print(f"  Cluster: {c.id} name={c.name} region={c.region}")

# ── Test 1: Market View EV ranking ──────────────────────────────────────
print("\n=== MARKET VIEW (EV Ranking) ===")
for c in clusters[:2]:
    mv = requests.get(f'{BASE}/api/v1/ascpai/clusters/{c.id}/market-view?page_size=10', headers=headers)
    if mv.status_code != 200:
        print(f"  [{c.name}] FAIL: {mv.status_code} {mv.text[:200]}")
        continue
    mvd = mv.json()
    pools = mvd.get('pools', [])
    pag = mvd.get('pagination', {})
    rf = mvd.get('resource_filter', {})
    print(f"\n  [{c.name}] total_valid={pag.get('total_valid_pools')} eliminated={pag.get('gates_eliminated')}")
    print(f"  baseline: ${rf.get('baseline_od_price_hr', 0):.4f}/hr  min_vcpu={rf.get('min_vcpu')} min_mem={rf.get('min_memory_gb')}")
    
    prev_ev = None
    all_positive = True
    ev_monotone = True
    for i, p in enumerate(pools[:10]):
        ev = p.get('expected_value', 'MISSING')
        rp = p.get('risk_probability', 'MISSING')
        csav = p.get('customer_savings_pct', 0)
        fs = p.get('final_score', 0)
        cap = p.get('capacity_status', '?')
        itype = p.get('instance_type', '?')
        az = p.get('az', '?')
        spot = p.get('spot_price', 0)
        print(f"    #{i+1} {itype:20s} {az:15s} spot=${spot:.4f} savings={csav:6.1f}% risk_prob={rp} EV={ev} cap={cap}")
        if csav < 0:
            all_positive = False
        if prev_ev is not None and ev != 'MISSING' and prev_ev != 'MISSING':
            if ev > prev_ev and cap == pools[i-1].get('capacity_status'):
                ev_monotone = False
        prev_ev = ev
    
    print(f"  ✓ All positive savings: {all_positive}")
    print(f"  ✓ EV monotonically decreasing (within capacity group): {ev_monotone}")
    if 'expected_value' in (pools[0] if pools else {}):
        print(f"  ✓ expected_value field present")
    else:
        print(f"  ✗ expected_value field MISSING")

# ── Test 2: Per-Node Alternatives ───────────────────────────────────────
print("\n=== PER-NODE ALTERNATIVES ===")
for c in clusters[:2]:
    # Get node-recommendations to find node IDs
    nr = requests.get(f'{BASE}/api/v1/ascpai/clusters/{c.id}/node-recommendations', headers=headers)
    if nr.status_code != 200:
        print(f"  [{c.name}] node-recommendations FAIL: {nr.status_code}")
        continue
    nrd = nr.json()
    # Debug: print keys
    if isinstance(nrd, dict):
        print(f"  [{c.name}] node-recommendations keys: {list(nrd.keys())[:10]}")
        # Try different possible structures
        nodes_list = nrd.get('nodes', nrd.get('recommendations', nrd.get('items', [])))
        if not nodes_list and 'node_groups' in nrd:
            for grp in nrd.get('node_groups', []):
                for node in grp.get('nodes', []):
                    nodes_list.append(node)
    elif isinstance(nrd, list):
        nodes_list = nrd
    else:
        nodes_list = []
    
    if not nodes_list:
        # Fall back: look at first dict-level keys that might contain node data
        print(f"  [{c.name}] full response sample: {json.dumps(nrd)[:500]}")
        continue
    
    # Debug first node structure
    if nodes_list:
        print(f"  [{c.name}] first recommendation keys: {list(nodes_list[0].keys()) if isinstance(nodes_list[0], dict) else nodes_list[0]}")
    
    # Get first node's ID
    node = nodes_list[0] if isinstance(nodes_list[0], dict) else {"node_id": nodes_list[0]}
    node_id = node.get('instance_id', node.get('node_id', node.get('id', node.get('name', ''))))
    print(f"\n  [{c.name}] Testing node: {node_id} (type={node.get('current_type', '?')})")
    
    alt = requests.get(f'{BASE}/api/v1/ascpai/clusters/{c.id}/nodes/{node_id}/alternatives?limit=15', headers=headers)
    if alt.status_code != 200:
        print(f"    FAIL: {alt.status_code} {alt.text[:300]}")
        continue
    
    altd = alt.json()
    current = altd.get('current_node', {})
    filters = altd.get('filters_applied', {})
    pos_count = altd.get('positive_count', '?')
    neg_shown = altd.get('negative_savings_shown', '?')
    pools = altd.get('alternatives', altd.get('pools', []))
    
    print(f"    current_node: type={current.get('instance_type')} od=${current.get('od_price_hr', 0):.4f} risk={current.get('risk_probability', '?')}")
    print(f"    filters: {json.dumps(filters)}")
    print(f"    positive_count={pos_count} negative_shown={neg_shown} total_returned={len(pools)}")
    
    for i, p in enumerate(pools[:10]):
        ev = p.get('expected_value', 'MISSING')
        rp = p.get('risk_probability', 'MISSING')
        sav = p.get('savings_pct', p.get('customer_savings_pct', 0))
        itype = p.get('instance_type', '?')
        az = p.get('az', '?')
        spot = p.get('spot_price', 0)
        print(f"      #{i+1} {itype:20s} {az:15s} spot=${spot:.4f} savings={sav}% risk={rp} EV={ev}")

db.close()
print("\n=== DONE ===")
