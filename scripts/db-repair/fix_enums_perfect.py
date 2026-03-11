import re

with open('./migrations/versions/20260307_0439_827fea8cbdd0_final_missing_tables.py', 'r') as f:
    content = f.read()

# 1. Strip any existing botched additions so the file is pristine
content = content.replace("sa.Enum(create_type=False, ", "sa.Enum(")
content = content.replace("postgresql.ENUM(create_type=False, ", "postgresql.ENUM(")
content = content.replace(", create_type=False, name=", ", name=")

# 2. Extract values for the missing ENUMs to inject idempotent creations
blocks = [
    "DO $$ BEGIN CREATE TYPE templatestatus AS ENUM ('DRAFT', 'ACTIVE', 'ARCHIVED'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE roletype AS ENUM ('SYSTEM', 'CUSTOM'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE onboardingstep AS ENUM ('WELCOME', 'CONNECT_AWS', 'VERIFYING', 'COMPLETED'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE connectionmode AS ENUM ('READ_ONLY', 'FULL_ACCESS'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE invitationstatus AS ENUM ('PENDING', 'ACCEPTED', 'EXPIRED'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE savingsplantype AS ENUM ('COMPUTE', 'EC2_INSTANCE', 'SAGEMAKER'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE chaosexperimenttype AS ENUM ('REDIS_FLUSH', 'DB_CONNECTION_LOSS', 'API_LATENCY', 'SPOT_INTERRUPTION', 'PRICING_OUTAGE', 'POOL_BLACKLIST', 'KARPENTER_SLOW', 'PDB_DEADLOCK', 'CELERY_CRASH', 'NETWORK_PARTITION'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE chaosexperimentstatus AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'ROLLED_BACK', 'CANCELLED'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE proposalstatus AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED', 'FAILED'); EXCEPTION WHEN duplicate_object THEN null; END $$;",
    "DO $$ BEGIN CREATE TYPE optimizationphase AS ENUM ('INITIAL_POOL_OPTIMIZATION', 'STABILIZATION', 'RIGHTSIZING_EVALUATION', 'COMBINED_EXECUTION', 'COOLDOWN'); EXCEPTION WHEN duplicate_object THEN null; END $$;"
]

# 3. Inject the raw SQL executions right after the def upgrade() definition
upgrade_injection = "def upgrade() -> None:\n"
for block in blocks:
    upgrade_injection += f"    op.execute(\"{block}\")\n"

content = content.replace("def upgrade() -> None:", upgrade_injection)

# 4. Now safely force create_type=False across all ENUM references 
#    Since we manually created them above, they are guaranteed to exist when the table maps them!
content = content.replace(", name=", ", create_type=False, name=")
content = content.replace("sa.Enum(", "postgresql.ENUM(")

with open('./migrations/versions/20260307_0439_827fea8cbdd0_final_missing_tables.py', 'w') as f:
    f.write(content)
