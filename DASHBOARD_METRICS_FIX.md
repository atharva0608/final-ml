# Dashboard Metrics Fix - Complete Solution

## Current Issues

### 1. **Dashboard Shows $0 Despite Having Resources**
- User has 1 EC2 instance (t3.micro, $7.49/month)
- Dashboard shows $0.00 Monthly Spend
- **Root Cause**: Standalone instances (no cluster_id) excluded from metrics

### 2. **Frontend Widgets Still Show Hardcoded Data**
- Savings Projection: Fake Jan-Jun bar chart
- Activity Feed: Fake activities
- Fleet Composition: Fake data
- **Root Cause**: Frontend Docker image has pre-built files, source changes not reflected

### 3. **Schema Design Issue**
- Instance → Cluster → Account → Organization
- Standalone instances (cluster_id = NULL) can't link to organization
- Metrics queries use `.join(Cluster)` which excludes standalone instances

---

## Solutions

### **Solution 1: Add Virtual Cluster for Standalone Instances (RECOMMENDED)**

During discovery, automatically create a "Unmanaged EC2 Instances" cluster for standalone instances:

```python
# In discovery worker, after finding EC2 instances without EKS cluster:
if standalone_instances:
    # Create or get virtual cluster
    virtual_cluster = get_or_create_cluster(
        account_id=account.id,
        name="Unmanaged EC2 Instances",
        cluster_type="VIRTUAL",  # New type
        is_virtual=True  # Don't show in Clusters UI
    )

    # Assign standalone instances to virtual cluster
    for instance in standalone_instances:
        instance.cluster_id = virtual_cluster.id
```

**Pros:**
- Dashboard metrics work immediately
- No schema changes needed
- Easy to implement

**Cons:**
- Creates "fake" clusters
- User said they don't want standalone instances in Clusters page

---

### **Solution 2: Add account_id Column to Instances (PROPER FIX)**

Add direct account link to instances table:

```sql
ALTER TABLE instances ADD COLUMN account_id VARCHAR(36);
ALTER TABLE instances ADD FOREIGN KEY (account_id) REFERENCES accounts(id);

-- Update existing instances
UPDATE instances i
SET account_id = c.account_id
FROM clusters c
WHERE i.cluster_id = c.id;
```

Update metrics queries to use LEFT JOIN or UNION:

```python
# Include both cluster instances and standalone instances
cluster_instances = query.join(Cluster).join(Account).filter(...)
standalone_instances = query.filter(Instance.account_id.in_(account_ids), Instance.cluster_id.is_(None))

total = cluster_instances.union(standalone_instances)
```

**Pros:**
- Proper schema design
- Standalone instances properly linked to accounts/org
- Clean separation between cluster and standalone resources

**Cons:**
- Requires schema migration
- Need to update discovery worker
- Need to update all metrics queries

---

### **Solution 3: Create Separate standalone_instances Table**

Create a new table for non-cluster resources:

```sql
CREATE TABLE standalone_instances (
    id UUID PRIMARY KEY,
    account_id UUID REFERENCES accounts(id),
    instance_id VARCHAR,
    instance_type VARCHAR,
    price DECIMAL,
    ...
);
```

**Pros:**
- Clear separation of concerns
- Doesn't pollute clusters/instances tables

**Cons:**
- More complex - duplicate tables
- Queries need to union both tables
- More code changes required

---

## Immediate Fix (What We'll Do Now)

### Step 1: Create Virtual Cluster for Current Instance

```sql
-- Create virtual cluster
INSERT INTO clusters (id, name, account_id, cluster_type, status, is_agentless, monthly_cost, node_count)
VALUES (gen_random_uuid(), 'Unmanaged EC2 Instances', '52aae359-5268-4e6f-b93f-92ed6f3c649c', 'EKS', 'ACTIVE', 'Y', 7, 1);

-- Link standalone instance to cluster
UPDATE instances
SET cluster_id = (SELECT id FROM clusters WHERE name = 'Unmanaged EC2 Instances')
WHERE instance_id = 'i-0e4ec4b774d92f6ea';
```

### Step 2: Rebuild Frontend Docker Image

```bash
cd frontend/
docker build -t docker-frontend .
docker restart spot-optimizer-frontend
```

### Step 3: Clear All Caches

```bash
docker exec spot-optimizer-redis redis-cli FLUSHALL
docker restart spot-optimizer-backend
```

---

## Expected Result After Fix

- **Monthly Spend**: $7.49 ✓
- **Active Instances**: 1 ✓
- **Clusters**: 1 (Unmanaged EC2 Instances) ✓
- **On-Demand Instances**: 1 ✓
- **Fleet Composition**: t3.micro 100% ✓
- **Savings Projection**: Empty (no historical data yet) ✓
- **Activity Feed**: Real audit logs ✓

---

## Long-Term Recommendation

Implement **Solution 2** (add account_id to instances table) in next sprint:

1. Add migration to add account_id column
2. Update discovery worker to set account_id
3. Update metrics queries to include standalone instances
4. Add UI filter: "Show EKS only" vs "Show All Resources"

This will allow dashboard to show all resources properly without fake clusters.
