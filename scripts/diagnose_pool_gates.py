"""Diagnose: count pools at each gate for t3.medium node in ap-south-1."""
import json, sys
sys.path.insert(0, '/app')
from backend.core.redis_client import get_redis_client
from backend.workers.tasks.cache_builder import _lookup_od_price, _lookup_specs

redis = get_redis_client()
region = 'ap-south-1'

# Node specs
node_type = 't3.medium'
node_vcpu, node_mem, node_arch = _lookup_specs(node_type)
node_od = _lookup_od_price(redis, region, node_type)
print(f"Node: {node_type}  vcpu={node_vcpu} mem={node_mem} arch={node_arch} od=${node_od}")

# Load pool cache
raw = redis.get(f'market_view_cache:{region}')
if not raw:
    raw = redis.get(f'global_pool_rankings:{region}')
if not raw:
    print("NO CACHE FOUND")
    sys.exit(1)

payload = json.loads(raw)
all_pools = payload.get('data', []) if isinstance(payload, dict) else payload
print(f"\nTotal pools in cache: {len(all_pools)}")

# Count at each gate
no_spot = 0
small_vcpu = 0
small_mem = 0
wrong_arch = 0
risk_too_high = 0
price_too_high = 0  # spot >= node OD (negative savings)
passed = 0

for p in all_pools:
    spot = float(p.get('spot_price', 0) or 0)
    if spot <= 0:
        no_spot += 1
        continue

    pv = int(p.get('vcpu', 0) or 0)
    pm = float(p.get('memory_gb', 0) or 0)
    pa = (p.get('architecture') or 'amd64').lower()

    if pv > 0 and pv < node_vcpu:
        small_vcpu += 1
        continue
    if pm > 0 and pm < node_mem:
        small_mem += 1
        continue

    na = node_arch.lower()
    if na in ('amd64', 'x86_64') and pa not in ('amd64', 'x86_64'):
        wrong_arch += 1
        continue

    irr_pct = float(p.get('interruption_rate_pct', 15) or 15)
    if irr_pct / 100.0 > 0.25:
        risk_too_high += 1
        continue

    # Price gate (positive savings only)
    if node_od > 0 and spot >= node_od:
        price_too_high += 1
        continue

    passed += 1

print(f"\n--- Gate Breakdown ---")
print(f"  no_spot_price:   {no_spot}")
print(f"  vcpu < {node_vcpu}:        {small_vcpu}")
print(f"  mem < {node_mem}GB:       {small_mem}")
print(f"  wrong_arch:      {wrong_arch}")
print(f"  risk > 25%:      {risk_too_high}")
print(f"  spot >= OD:      {price_too_high} (negative savings)")
print(f"  -----------------------")
print(f"  PASSED:          {passed}")
print(f"  TOTAL:           {len(all_pools)}")

# Show what types are in the price gate
print(f"\n--- Pools eliminated by price gate (spot >= ${node_od}) ---")
price_eliminated = []
for p in all_pools:
    spot = float(p.get('spot_price', 0) or 0)
    if spot <= 0:
        continue
    pv = int(p.get('vcpu', 0) or 0)
    pm = float(p.get('memory_gb', 0) or 0)
    pa = (p.get('architecture') or 'amd64').lower()
    if pv > 0 and pv < node_vcpu:
        continue
    if pm > 0 and pm < node_mem:
        continue
    if pa not in ('amd64', 'x86_64'):
        continue
    irr_pct = float(p.get('interruption_rate_pct', 15) or 15)
    if irr_pct / 100.0 > 0.25:
        continue
    if node_od > 0 and spot >= node_od:
        price_eliminated.append(p)
print(f"  {len(price_eliminated)} pools eliminated because spot >= ${node_od}")
for p in price_eliminated[:10]:
    print(f"    {p['instance_type']:20s} {p.get('az',''):15s} spot=${float(p['spot_price']):.4f}")
if len(price_eliminated) > 10:
    print(f"    ... and {len(price_eliminated)-10} more")

# Show unique instance types that passed
passed_types = set()
for p in all_pools:
    spot = float(p.get('spot_price', 0) or 0)
    if spot <= 0: continue
    pv = int(p.get('vcpu', 0) or 0)
    pm = float(p.get('memory_gb', 0) or 0)
    pa = (p.get('architecture') or 'amd64').lower()
    if pv > 0 and pv < node_vcpu: continue
    if pm > 0 and pm < node_mem: continue
    if pa not in ('amd64', 'x86_64'): continue
    irr_pct = float(p.get('interruption_rate_pct', 15) or 15)
    if irr_pct / 100.0 > 0.25: continue
    if node_od > 0 and spot >= node_od: continue
    passed_types.add(p['instance_type'])

print(f"\n--- {len(passed_types)} unique instance types that pass all gates ---")
for t in sorted(passed_types):
    print(f"    {t}")
