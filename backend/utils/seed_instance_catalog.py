"""
Seed the instance_catalog table from Redis spot_price keys.

Reads all unique instance types collected by the pricing scraper,
resolves their vCPU/memory specs from a built-in lookup, and
upserts rows so PoolRankingService uses the full candidate pool
instead of the 35-entry hardcoded fallback.

Run once (or after wiping the table):
    docker exec spot-optimizer-backend python3 backend/utils/seed_instance_catalog.py
"""
import os
import re
import uuid
import logging

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Spec resolution
# ---------------------------------------------------------------------------

_T_MEM = {
    "nano": 0.5, "micro": 1.0, "small": 2.0, "medium": 4.0,
    "large": 8.0, "xlarge": 16.0, "2xlarge": 32.0,
}

_SIZE_VCPU = {
    "nano": 2, "micro": 2, "small": 2, "medium": 2,
    "large": 2, "xlarge": 4, "2xlarge": 8, "4xlarge": 16,
    "8xlarge": 32, "9xlarge": 36, "10xlarge": 40, "12xlarge": 48,
    "16xlarge": 64, "18xlarge": 72, "24xlarge": 96, "32xlarge": 128,
    "48xlarge": 192, "56xlarge": 224, "112xlarge": 448,
    "metal": 96,
}

_ARM_FAMILIES = frozenset({
    "t4g", "m6g", "m6gd", "m7g", "m7gd", "m8g",
    "c6g", "c6gd", "c6gn", "c7g", "c7gd", "c8g", "c8gn",
    "r6g", "r6gd", "r7g", "r7gd", "r8g",
    "i8g", "a1", "im4gn", "is4gen", "gr6", "gr6f",
})

_AMD_FAMILIES = frozenset({
    "t3a", "m5a", "m5ad", "m6a", "r5a", "r5ad", "c5a", "c6a", "r6a",
})


def _resolve_vcpu(size: str) -> int:
    if size in _SIZE_VCPU:
        return _SIZE_VCPU[size]
    m = re.match(r"^(\d+)xlarge$", size)
    if m:
        return int(m.group(1)) * 4
    if "metal" in size:
        m2 = re.match(r"metal-(\d+)xl", size)
        return int(m2.group(1)) * 4 if m2 else 96
    return 0


def resolve_specs(instance_type: str):
    """Return (vcpu, memory_gb, arch, manufacturer) or None if unresolvable."""
    try:
        family, size = instance_type.split(".", 1)
    except ValueError:
        return None

    vcpu = _resolve_vcpu(size)
    if vcpu == 0:
        return None

    # Memory per vCPU ratio by instance family category
    f = family.lower()
    if f.startswith("t"):
        mem_gb = _T_MEM.get(size, vcpu * 4.0)
    elif any(f.startswith(p) for p in ("r", "x", "z", "u")):
        mem_gb = vcpu * 8.0
    elif any(f.startswith(p) for p in ("c",)):
        mem_gb = vcpu * 2.0
    elif any(f.startswith(p) for p in ("p", "g", "inf", "trn", "dl", "vt", "f")):
        mem_gb = vcpu * 8.0
    elif any(f.startswith(p) for p in ("i", "d", "h")):
        mem_gb = vcpu * 8.0
    else:
        mem_gb = vcpu * 4.0  # general purpose default

    arch = "arm64" if family in _ARM_FAMILIES else "x86_64"

    if family in _AMD_FAMILIES:
        mfr = "AMD"
    elif family in _ARM_FAMILIES:
        mfr = "AWS"
    else:
        mfr = "Intel"

    return vcpu, mem_gb, arch, mfr


# ---------------------------------------------------------------------------
# Main seeder
# ---------------------------------------------------------------------------

def seed(region: str = "ap-south-1"):
    db_url = os.environ.get(
        "DATABASE_URL", "postgresql://spot_user:spot_pass@db:5432/spot_optimizer"
    )
    engine = create_engine(db_url)

    # 1. Collect unique instance types from Redis
    from backend.core.redis_client import get_redis_client
    redis = get_redis_client()
    instance_types: set = set()
    cursor = 0
    while True:
        cursor, keys = redis.scan(cursor, match=f"spot_price:{region}:*", count=500)
        for k in keys:
            key_str = k.decode() if isinstance(k, bytes) else k
            parts = key_str.split(":")
            if len(parts) >= 4:
                instance_types.add(":".join(parts[3:]))
        if cursor == 0:
            break

    log.info(f"Found {len(instance_types)} unique instance types in Redis for {region}")

    # 2. Upsert into instance_catalog
    inserted = updated = skipped = 0
    with engine.begin() as conn:
        for itype in sorted(instance_types):
            result = resolve_specs(itype)
            if result is None:
                skipped += 1
                continue
            vcpu, mem_gb, arch, mfr = result

            existing = conn.execute(
                text("SELECT id FROM instance_catalog WHERE instance_type=:t AND region=:r"),
                {"t": itype, "r": region},
            ).fetchone()

            if existing:
                conn.execute(
                    text("""
                        UPDATE instance_catalog
                           SET vcpus=:vcpu, memory_gb=:mem_gb, memory_mib=:mem_mib,
                               cores=:cores, architecture=:arch,
                               processor_manufacturer=:mfr,
                               burstable_performance_supported=:burst,
                               last_updated_at=now()
                         WHERE instance_type=:t AND region=:r
                    """),
                    {
                        "vcpu": vcpu, "mem_gb": mem_gb,
                        "mem_mib": int(mem_gb * 1024),
                        "cores": max(1, vcpu // 2),
                        "arch": arch, "mfr": mfr,
                        "burst": itype.startswith("t"),
                        "t": itype, "r": region,
                    },
                )
                updated += 1
            else:
                conn.execute(
                    text("""
                        INSERT INTO instance_catalog
                          (id, instance_type, region, current_generation, architecture,
                           vcpus, cores, threads_per_core, memory_mib, memory_gb,
                           processor_manufacturer, hypervisor, created_at, last_updated_at,
                           network_performance, max_network_interfaces,
                           ipv4_addresses_per_interface, ipv6_supported,
                           ebs_optimized, ebs_encryption_support,
                           instance_storage_supported, instance_storage_total_gb,
                           gpu_count, gpu_memory_mib,
                           burstable_performance_supported, auto_recovery_supported,
                           hibernation_supported)
                        VALUES
                          (:id, :itype, :region, true, :arch,
                           :vcpu, :cores, 2, :mem_mib, :mem_gb,
                           :mfr, 'nitro', now(), now(),
                           'Up to 10 Gigabit', 3, 6,
                           false, 'default', 'supported',
                           false, 0,
                           0, 0,
                           :burst, false, false)
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "itype": itype, "region": region,
                        "arch": arch,
                        "vcpu": vcpu, "cores": max(1, vcpu // 2),
                        "mem_mib": int(mem_gb * 1024), "mem_gb": mem_gb,
                        "mfr": mfr,
                        "burst": itype.startswith("t"),
                    },
                )
                inserted += 1

    total = inserted + updated
    log.info(
        f"Done — inserted={inserted}, updated={updated}, skipped={skipped}, total={total}"
    )

    # Verify
    with engine.connect() as conn:
        cnt = conn.execute(
            text("SELECT COUNT(*) FROM instance_catalog WHERE region=:r"),
            {"r": region},
        ).scalar()
        log.info(f"instance_catalog rows for {region}: {cnt}")

    return {"inserted": inserted, "updated": updated, "skipped": skipped}


if __name__ == "__main__":
    import sys
    region = sys.argv[1] if len(sys.argv) > 1 else "ap-south-1"
    seed(region)
