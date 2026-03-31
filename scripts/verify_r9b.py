"""Verify R-9b fix: saving_pct field and spot_advisor_rank in per-node alternatives."""
import json, sys, time
sys.path.insert(0, '/app')
import requests

time.sleep(3)
BASE = 'http://localhost:8000'
resp = requests.post(f'{BASE}/api/v1/auth/login', json={"email": "admin@spotoptimizer.com", "password": "admin123"})
token = resp.json()['access_token']
headers = {"Authorization": f"Bearer {token}"}

for cid, cname in [
    ('ae76e390-1061-4c36-af69-daf4e4522326', 'spot-demo-1'),
    ('c1489801-ce02-4365-8ca7-9842f21d2e8c', 'k8s-cluster'),
]:
    nr = requests.get(f'{BASE}/api/v1/ascpai/clusters/{cid}/node-recommendations', headers=headers)
    recs = nr.json().get('recommendations', [])
    if not recs:
        continue
    node_id = recs[0]['instance_id']
    
    alt = requests.get(f'{BASE}/api/v1/ascpai/clusters/{cid}/nodes/{node_id}/alternatives?page_size=5', headers=headers)
    d = alt.json()
    cn = d.get('current_node', {})
    print(f"=== [{cname}] node={node_id} ({cn.get('instance_type')}) od=${cn.get('od_price')} ===")
    
    for p in d.get('alternatives', [])[:5]:
        print(f"  #{p.get('rank')} {p.get('instance_type'):20s} {p.get('az'):15s}"
              f" spot=${p.get('spot_price',0):.4f}"
              f" saving_pct={p.get('saving_pct')}"
              f" savings_pct={p.get('savings_pct')}"
              f" customer_savings_pct={p.get('customer_savings_pct')}"
              f" spot_advisor_rank={p.get('spot_advisor_rank')}"
              f" EV={p.get('expected_value')}")
