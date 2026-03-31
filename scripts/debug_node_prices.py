"""Debug: check OD prices and risk data for nodes in both clusters."""
import json, sys
sys.path.insert(0, '/app')
from backend.core.redis_client import get_redis_client
from backend.models.base import get_db
from backend.models.instance import Instance
from backend.workers.tasks.cache_builder import _lookup_od_price, _lookup_specs

redis = get_redis_client()
db = next(get_db())

# spot-demo-1
print("=== spot-demo-1 (ap-south-1) ===")
insts = db.query(Instance).filter_by(cluster_id='ae76e390-1061-4c36-af69-daf4e4522326').all()
for inst in insts:
    it = inst.instance_type
    region = 'ap-south-1'
    od_redis = redis.get(f'ondemand_price:{region}:{it}')
    od_redis2 = redis.get(f'od_price:{region}:{it}')
    od_lookup = _lookup_od_price(redis, region, it)
    vcpu, mem, arch = _lookup_specs(it)
    risk_raw = redis.get(f'spot_advisor:{region}:{it}:Linux')
    risk_parsed = None
    if risk_raw:
        rd = json.loads(risk_raw)
        risk_parsed = rd.get('interruption_index')
    print(f"  {inst.instance_id} type={it} az={inst.az} lifecycle={getattr(inst, 'lifecycle', '?')}")
    print(f"    OD: ondemand_price key={od_redis}, od_price key={od_redis2}, _lookup_od={od_lookup}")
    print(f"    specs: vcpu={vcpu} mem={mem} arch={arch}")
    print(f"    risk: index={risk_parsed}")

print()

# k8s-cluster
print("=== k8s-cluster (us-east-1) ===")
insts2 = db.query(Instance).filter_by(cluster_id='c1489801-ce02-4365-8ca7-9842f21d2e8c').all()
for inst in insts2:
    it = inst.instance_type
    region = 'us-east-1'
    od_lookup = _lookup_od_price(redis, region, it)
    vcpu, mem, arch = _lookup_specs(it)
    print(f"  {inst.instance_id} type={it} az={inst.az} lifecycle={getattr(inst, 'lifecycle', '?')}")
    print(f"    OD: _lookup_od={od_lookup}, specs: vcpu={vcpu} mem={mem} arch={arch}")

print()

# Now test via the actual API
import requests
resp = requests.post('http://localhost:8000/api/v1/auth/login', json={"email": "admin@spotoptimizer.com", "password": "admin123"})
token = resp.json()['access_token']
headers = {"Authorization": f"Bearer {token}"}

for cid, cname, region in [
    ('ae76e390-1061-4c36-af69-daf4e4522326', 'spot-demo-1', 'ap-south-1'),
    ('c1489801-ce02-4365-8ca7-9842f21d2e8c', 'k8s-cluster', 'us-east-1'),
]:
    # Get node-recommendations for node IDs
    nr = requests.get(f'http://localhost:8000/api/v1/ascpai/clusters/{cid}/node-recommendations', headers=headers)
    if nr.status_code != 200:
        print(f"[{cname}] recommendations FAIL: {nr.status_code}")
        continue
    recs = nr.json().get('recommendations', [])
    if not recs:
        print(f"[{cname}] no recommendations")
        continue
    
    node_id = recs[0].get('instance_id', '')
    print(f"=== Per-node alternatives: [{cname}] node={node_id} ===")
    alt = requests.get(f'http://localhost:8000/api/v1/ascpai/clusters/{cid}/nodes/{node_id}/alternatives?page_size=5', headers=headers)
    if alt.status_code != 200:
        print(f"  FAIL: {alt.status_code} {alt.text[:300]}")
        continue
    
    d = alt.json()
    cn = d.get('current_node', {})
    print(f"  current_node: type={cn.get('instance_type')} od_price={cn.get('od_price')} risk={cn.get('risk')} vcpu={cn.get('vcpu')} mem={cn.get('memory_gb')}")
    print(f"  positive_count={d.get('positive_count')} total={d.get('total_alternatives')}")
    
    for p in d.get('alternatives', [])[:5]:
        print(f"    #{p.get('rank')} {p.get('instance_type'):20s} {p.get('az'):15s} spot=${p.get('spot_price', 0):.4f} savings={p.get('savings_pct')}% EV={p.get('expected_value')} baseline=${p.get('node_od_baseline', 0)}")

db.close()
