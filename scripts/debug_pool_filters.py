"""Debug: trace exactly where pools are filtered out for t3.medium."""
import json, sys
sys.path.insert(0, '/app')
from backend.core.redis_client import get_redis_client
from backend.workers.tasks.cache_builder import _lookup_specs, _lookup_od_price

redis = get_redis_client()
region = 'ap-south-1'

# 1. How many pools in the cache?
raw = redis.get(f'market_view_cache:{region}')
if not raw:
    raw = redis.get(f'global_pool_rankings:{region}')
if not raw:
    print("NO CACHE FOUND")
    sys.exit(1)

payload = json.loads(raw)
all_pools = payload.get('data', []) if isinstance(payload, dict) else payload
print(f"Total pools in cache for {region}: {len(all_pools)}")

# 2. What meta does the cache have?
if isinstance(payload, dict):
    meta = {k: v for k, v in payload.items() if k != 'data'}
    print(f"Cache meta: {json.dumps(meta, default=str)[:300]}")

# Node specs for t3.medium
node_vcpu, node_mem, node_arch = _lookup_specs('t3.medium')
node_od = _lookup_od_price(redis, region, 't3.medium')
print(f"\nt3.medium: vcpu={node_vcpu} mem={node_mem} arch={node_arch} od=${node_od}")

# 3. Trace each filter
skip_spot = 0
skip_vcpu = 0
skip_mem = 0
skip_arch = 0
skip_risk = 0
skip_price = 0  # spot >= node OD
passed = 0

risk_ceiling = 0.25  # 25%
arch_match = {'amd64', 'x86_64'}

unique_types = set()
for p in all_pools:
    spot = float(p.get('spot_price', 0) or 0)
    vcpu = int(p.get('vcpu', 0) or 0)
    mem = float(p.get('memory_gb', 0) or 0)
    parch = (p.get('architecture') or 'amd64').lower()
    irr = float(p.get('interruption_rate_pct', 15) or 15)
    aws_risk = irr / 100.0
    
    if spot <= 0:
        skip_spot += 1
        continue
    if vcpu > 0 and vcpu < node_vcpu:
        skip_vcpu += 1
        continue
    if mem > 0 and mem < node_mem:
        skip_mem += 1
        continue
    if parch not in arch_match:
        skip_arch += 1
        continue
    if aws_risk > risk_ceiling:
        skip_risk += 1
        continue
    if spot >= node_od:
        skip_price += 1
        continue
    
    passed += 1
    unique_types.add(p.get('instance_type'))

print(f"\n=== Filter breakdown (t3.medium baseline ${node_od}, min {node_vcpu}vCPU/{node_mem}GB) ===")
print(f"  Total in cache:      {len(all_pools)}")
print(f"  Skip spot_price<=0:  {skip_spot}")
print(f"  Skip vcpu<{node_vcpu}:        {skip_vcpu}")
print(f"  Skip mem<{node_mem}GB:       {skip_mem}")
print(f"  Skip arch!=amd64:    {skip_arch}")
print(f"  Skip risk>{risk_ceiling*100}%:     {skip_risk}")
print(f"  Skip spot>=OD:       {skip_price}")
print(f"  PASSED:              {passed}")
print(f"  Unique types passed: {len(unique_types)}")
print(f"  Types: {sorted(unique_types)}")

# 4. Now check: what if we remove the price gate?
print(f"\n=== Without price gate (spot >= OD) ===")
skip2 = {'spot': 0, 'vcpu': 0, 'mem': 0, 'arch': 0, 'risk': 0}
passed2 = 0
for p in all_pools:
    spot = float(p.get('spot_price', 0) or 0)
    vcpu = int(p.get('vcpu', 0) or 0)
    mem = float(p.get('memory_gb', 0) or 0)
    parch = (p.get('architecture') or 'amd64').lower()
    irr = float(p.get('interruption_rate_pct', 15) or 15)
    aws_risk = irr / 100.0
    if spot <= 0: skip2['spot'] += 1; continue
    if vcpu > 0 and vcpu < node_vcpu: skip2['vcpu'] += 1; continue
    if mem > 0 and mem < node_mem: skip2['mem'] += 1; continue
    if parch not in arch_match: skip2['arch'] += 1; continue
    if aws_risk > risk_ceiling: skip2['risk'] += 1; continue
    passed2 += 1
print(f"  Would pass: {passed2}")

# 5. Without vcpu/mem gate?
print(f"\n=== Without vcpu/mem gates ===")
passed3 = 0
for p in all_pools:
    spot = float(p.get('spot_price', 0) or 0)
    parch = (p.get('architecture') or 'amd64').lower()
    irr = float(p.get('interruption_rate_pct', 15) or 15)
    aws_risk = irr / 100.0
    if spot <= 0: continue
    if parch not in arch_match: continue
    if aws_risk > risk_ceiling: continue
    if spot >= node_od: continue
    passed3 += 1
print(f"  Would pass: {passed3}")

# 6. Check how many unique AZs and types in cache
all_types = set()
all_azs = set()
for p in all_pools:
    all_types.add(p.get('instance_type'))
    all_azs.add(p.get('az'))
print(f"\n=== Cache diversity ===")
print(f"  Unique instance types: {len(all_types)}")
print(f"  Unique AZs: {sorted(all_azs)}")
print(f"  Sample types: {sorted(list(all_types))[:20]}")
