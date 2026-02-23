import os

TARGET_FILE = "frontend/src/components/cleanup/CleanupDashboard.jsx"
SOURCE_FILE = "changelogic.md"

def build():
    try:
        with open(SOURCE_FILE, "r") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: {SOURCE_FILE} not found")
        return

    # Extract the JSX from the markdown
    # It starts at the first line of the file in changelogic.md (which is an import)
    # Actually changelogic.md doesn't have markdown codeblocks, it's just raw raw code!
    raw_code = content

    # 1. ADD MISSING IMPORTS
    imports = """import React, { useState, useEffect, useMemo } from 'react';
import { hygieneAPI, accountsAPI } from '../../services/api';
import toast from 'react-hot-toast';

// Wizards
import RIWizard from './wizards/RIWizard';
import S3Wizard from './wizards/S3Wizard';
import RDSWizard from './wizards/RDSWizard';
import BulkTagWizard from './BulkTagWizard';

// Filter Panel
import FilterPanel from './layout/FilterPanel';
import SavingsGauge from './summary/SavingsGauge';
"""
    # Replace the existing import
    raw_code = raw_code.replace('import { useState, useMemo } from "react";', imports)

    # 2. REMOVE MOCK DATA
    # We will slice out MOCK_RESOURCES and aggregate KPIs up to TINY COMPONENTS
    start_mock = raw_code.find('// ─── MOCK DATA')
    end_mock = raw_code.find('// ─── TINY COMPONENTS')
    if start_mock != -1 and end_mock != -1:
        raw_code = raw_code[:start_mock] + raw_code[end_mock:]


    # 3. FIX ResourceHygiene Component signature
    # Replace the export default function ResourceHygiene() with the API-connected one
    main_comp = """export default function CleanupDashboard() {
  const [activeType, setActiveType]     = useState("instance");
  const [selected, setSelected]         = useState(new Set());
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [search, setSearch]             = useState("");
  
  // -- API State --
  const [loading, setLoading] = useState(false);
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [selectedRegion, setSelectedRegion] = useState('ALL');
  const [scanResult, setScanResult] = useState(null);
  
  const [totalCost, setTotalCost] = useState(null);
  const [totalCostLoading, setTotalCostLoading] = useState(false);
  
  // -- Wizards --
  const [showRIWizard, setShowRIWizard] = useState(false);
  const [showS3Wizard, setShowS3Wizard] = useState(false);
  const [showRDSWizard, setShowRDSWizard] = useState(false);
  const [showBulkTagWizard, setShowBulkTagWizard] = useState(false);

  const regionsList = [
      { id: 'ALL', name: 'All Regions (Global)' },
      { id: 'us-east-1', name: 'US East (N. Virginia)' },
      { id: 'us-east-2', name: 'US East (Ohio)' },
      { id: 'us-west-1', name: 'US West (N. California)' },
      { id: 'us-west-2', name: 'US West (Oregon)' },
      { id: 'eu-west-1', name: 'Europe (Ireland)' },
      { id: 'eu-central-1', name: 'Europe (Frankfurt)' },
      { id: 'ap-south-1', name: 'Asia Pacific (Mumbai)' },
      { id: 'ap-northeast-1', name: 'Asia Pacific (Tokyo)' },
      { id: 'ap-southeast-1', name: 'Asia Pacific (Singapore)' },
      { id: 'ap-southeast-2', name: 'Asia Pacific (Sydney)' },
      { id: 'sa-east-1', name: 'South America (São Paulo)' },
  ];

  // -- Effects --
  useEffect(() => {
    fetchAccounts();
    fetchTotalCost();
  }, []);

  useEffect(() => {
    if (selectedAccount) {
        handleScan(false);
        fetchTotalCost();
    }
  }, [selectedAccount, selectedRegion]);

  // -- API Calls --
  const fetchAccounts = async () => {
    try {
        const res = await accountsAPI.list();
        setAccounts(res.data);
        if (res.data.length > 0) setSelectedAccount(res.data[0].id);
    } catch (err) { console.error("Failed to load accounts", err); }
  };

  const handleScan = async (forceRefresh = false) => {
    if (!selectedAccount) return;
    setLoading(true);
    try {
        const res = await hygieneAPI.scan(selectedAccount, {
            regions: selectedRegion === 'ALL' ? ['ALL'] : [selectedRegion],
            force_refresh: forceRefresh
        });
        setScanResult(res.data);
        setSelected(new Set());
        if (forceRefresh) {
            toast.success("Scan refreshed successfully");
            fetchTotalCost();
        }
    } catch (err) {
        console.error("Scan failed", err);
        if (!scanResult) setScanResult(null);
    } finally {
        setLoading(false);
    }
  };

  const fetchTotalCost = async () => {
    setTotalCostLoading(true);
    try {
        const res = await hygieneAPI.getTotalCost(selectedAccount || undefined);
        setTotalCost(res.data);
    } catch (err) {
        console.error("Failed to fetch total cost", err);
        setTotalCost(null);
    } finally {
        setTotalCostLoading(false);
    }
  };
  
  const handleAction = async (actionType) => {
    if (selected.size === 0) return;
    try {
        await hygieneAPI.execute({
            action_type: actionType,
            resource_ids: Array.from(selected),
            region: selectedRegion === 'ALL' ? 'global' : selectedRegion
        }, selectedAccount);
        toast.success(`Action ${actionType} initiated`);
        handleScan(true);
        setSelected(new Set());
    } catch(e) {
        toast.error(`Failed to execute ${actionType}`);
    }
  };

  // Convert API resources to flat list for table UI
  const rawResources = scanResult?.resources || [];
  
  // Transform API data to match frontend requirements
  const allResources = useMemo(() => {
      return rawResources.map(r => ({
          ...r,
          id: r.id,
          name: r.name || '-',
          type: r.type,
          region: r.region,
          status: r.status,
          cost: r.cost_per_month || 0,
          authorized: r.is_authorized,
          reason: r.reason || '',
          tags: r.metadata?.tags ? Object.keys(r.metadata.tags).length : 0,
          missingTags: r.missing_tags || []
      }));
  }, [rawResources]);

  const filteredResources = useMemo(() => {
    return allResources.filter(r => {
      // Filter by active type mapped from Sidebar to API ResourceType
      const typeMap = {
          'instance': 'INSTANCE',
          'reserved': 'RI_WASTE',
          'eks': 'EKS_CLUSTER',
          'ecs': 'ECS_CLUSTER',
          'asg': 'AUTO_SCALING_GROUP',
          'volume': 'VOLUME',
          'snapshot': 'SNAPSHOT',
          's3': 'S3_BUCKET',
          's3lc': 'S3_LIFECYCLE',
          'efs': 'EFS_FILE_SYSTEM',
          'eip': 'ELASTIC_IP',
          'lb': 'LOAD_BALANCER',
          'nat': 'NAT_GATEWAY',
          'eni': 'NETWORK_INTERFACE',
          'rds': 'RDS_DB',
          'dynamo': 'DYNAMODB_TABLE',
          'elastic': 'ELASTICACHE_CLUSTER',
          'kms': 'KMS_KEY',
          'secrets': 'SECRETS_MANAGER',
          'cwlg': 'CLOUDWATCH_LOG_GROUP',
          'cwa': 'CLOUDWATCH_ALARM',
          'lambda': 'LAMBDA_FUNCTION',
          'eb': 'EVENTBRIDGE_RULE',
          'iam': 'IAM_USER',
          'iamkey': 'IAM_KEY'
      };
      if (typeMap[activeType] && r.type !== typeMap[activeType]) return false;
      
      if (statusFilter !== "ALL" && r.status !== statusFilter) return false;
      if (search && !r.name.toLowerCase().includes(search.toLowerCase()) &&
          !r.id.toLowerCase().includes(search.toLowerCase())) return false;
      return true;
    });
  }, [allResources, statusFilter, search, activeType]);

  const handleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const handleSelectAll = (ids) => {
    setSelected(new Set(ids));
  };
  
  const selectedCount = selected.size;
  const selectedCost = filteredResources.filter(r => selected.has(r.id)).reduce((s, r) => s + r.cost, 0);
  const selectedResourceObjects = allResources.filter(r => selected.has(r.id));

  const STATUS_FILTERS = [
    { key: "ALL",           label: "All" },
    { key: "SAFE_TO_DELETE",label: "Safe to Delete" },
    { key: "ORPHANED",      label: "Orphaned" },
    { key: "STOPPED",       label: "Stopped" },
    { key: "RISK",          label: "Risk" },
    { key: "NOT_COMPLIANT", label: "Not Compliant" },
  ];
  
  // Aggregate KPIs based on API data
  const TOTAL_DISCOVERED = totalCost?.total_cost ? Number(totalCost.total_cost.toFixed(2)) : 0;
  const TOTAL_POTENTIAL  = scanResult?.summary?.total_potential_savings ? Number(scanResult.summary.total_potential_savings.toFixed(2)) : 0;
  const UNTAGGED         = allResources.filter(r => r.missingTags.length > 0).length;
  const TAG_HEALTH_PCT   = allResources.length > 0 ? Math.round((1 - UNTAGGED / allResources.length) * 100) : 100;
  const SAFETY_SAFE      = allResources.filter(r => r.status === "SAFE_TO_DELETE" || r.status === "STOPPED").length;
  const SAFETY_REVIEW    = allResources.filter(r => r.status === "ORPHANED" || r.status === "NOT_COMPLIANT").length;
  const SAFETY_RISKY     = allResources.filter(r => r.status === "RISK" || r.status === "UNAUTHORIZED").length;
  
  const SIDEBAR_CATEGORIES = [
      {
        id: "compute", label: "Compute", expanded: true,
        types: [
          { id: "instance",  label: "Instances",          count: allResources.filter(r=>r.type==="INSTANCE").length,  cost: allResources.filter(r=>r.type==="INSTANCE").reduce((s,r)=>s+r.cost,0) },
          { id: "reserved",  label: "Reserved Instances",  count: allResources.filter(r=>r.type==="RI_WASTE").length,  cost: allResources.filter(r=>r.type==="RI_WASTE").reduce((s,r)=>s+r.cost,0)   },
          { id: "eks",       label: "EKS Clusters",        count: allResources.filter(r=>r.type==="EKS_CLUSTER").length,  cost: allResources.filter(r=>r.type==="EKS_CLUSTER").reduce((s,r)=>s+r.cost,0)  },
          { id: "ecs",       label: "ECS Clusters",        count: allResources.filter(r=>r.type==="ECS_CLUSTER").length,  cost: allResources.filter(r=>r.type==="ECS_CLUSTER").reduce((s,r)=>s+r.cost,0)  },
          { id: "asg",       label: "Auto Scaling Groups", count: allResources.filter(r=>r.type==="AUTO_SCALING_GROUP").length,  cost: allResources.filter(r=>r.type==="AUTO_SCALING_GROUP").reduce((s,r)=>s+r.cost,0)   },
        ],
      },
      {
        id: "storage", label: "Storage", expanded: true,
        types: [
          { id: "volume",    label: "EBS Volumes",         count: allResources.filter(r=>r.type==="VOLUME").length, cost: allResources.filter(r=>r.type==="VOLUME").reduce((s,r)=>s+r.cost,0)  },
          { id: "snapshot",  label: "Snapshots",           count: allResources.filter(r=>r.type==="SNAPSHOT").length, cost: allResources.filter(r=>r.type==="SNAPSHOT").reduce((s,r)=>s+r.cost,0)  },
          { id: "s3",        label: "S3 Buckets",          count: allResources.filter(r=>r.type==="S3_BUCKET").length,  cost: allResources.filter(r=>r.type==="S3_BUCKET").reduce((s,r)=>s+r.cost,0)  },
          { id: "s3lc",      label: "S3 Lifecycle",        count: allResources.filter(r=>r.type==="S3_LIFECYCLE").length,  cost: allResources.filter(r=>r.type==="S3_LIFECYCLE").reduce((s,r)=>s+r.cost,0)   },
          { id: "efs",       label: "EFS File Systems",    count: allResources.filter(r=>r.type==="EFS_FILE_SYSTEM").length,  cost: allResources.filter(r=>r.type==="EFS_FILE_SYSTEM").reduce((s,r)=>s+r.cost,0)  },
        ],
      },
      {
        id: "network", label: "Network", expanded: false,
        types: [
          { id: "eip",       label: "Elastic IPs",         count: allResources.filter(r=>r.type==="ELASTIC_IP").length,  cost: allResources.filter(r=>r.type==="ELASTIC_IP").reduce((s,r)=>s+r.cost,0)  },
          { id: "lb",        label: "Load Balancers",       count: allResources.filter(r=>r.type==="LOAD_BALANCER").length,  cost: allResources.filter(r=>r.type==="LOAD_BALANCER").reduce((s,r)=>s+r.cost,0)  },
          { id: "nat",       label: "NAT Gateways",         count: allResources.filter(r=>r.type==="NAT_GATEWAY").length,  cost: allResources.filter(r=>r.type==="NAT_GATEWAY").reduce((s,r)=>s+r.cost,0)  },
          { id: "eni",       label: "Network Interfaces",   count: allResources.filter(r=>r.type==="NETWORK_INTERFACE").length,  cost: allResources.filter(r=>r.type==="NETWORK_INTERFACE").reduce((s,r)=>s+r.cost,0)   },
        ],
      },
      {
        id: "database", label: "Databases", expanded: false,
        types: [
          { id: "rds",       label: "RDS Instances",        count: allResources.filter(r=>r.type==="RDS_DB").length,  cost: allResources.filter(r=>r.type==="RDS_DB").reduce((s,r)=>s+r.cost,0) },
          { id: "dynamo",    label: "DynamoDB Tables",       count: allResources.filter(r=>r.type==="DYNAMODB_TABLE").length,  cost: allResources.filter(r=>r.type==="DYNAMODB_TABLE").reduce((s,r)=>s+r.cost,0)   },
          { id: "elastic",   label: "ElastiCache",          count: allResources.filter(r=>r.type==="ELASTICACHE_CLUSTER").length,  cost: allResources.filter(r=>r.type==="ELASTICACHE_CLUSTER").reduce((s,r)=>s+r.cost,0)  },
        ],
      },
      {
        id: "security", label: "Security", expanded: false,
        types: [
          { id: "kms",       label: "KMS Keys",             count: allResources.filter(r=>r.type==="KMS_KEY").length,  cost: allResources.filter(r=>r.type==="KMS_KEY").reduce((s,r)=>s+r.cost,0)   },
          { id: "secrets",   label: "Secrets Manager",      count: allResources.filter(r=>r.type==="SECRETS_MANAGER").length,  cost: allResources.filter(r=>r.type==="SECRETS_MANAGER").reduce((s,r)=>s+r.cost,0)  },
        ],
      },
      {
        id: "mgmt", label: "Management", expanded: false,
        types: [
          { id: "cwlg",      label: "CW Log Groups",        count: allResources.filter(r=>r.type==="CLOUDWATCH_LOG_GROUP").length, cost: allResources.filter(r=>r.type==="CLOUDWATCH_LOG_GROUP").reduce((s,r)=>s+r.cost,0)   },
          { id: "cwa",       label: "CW Alarms",            count: allResources.filter(r=>r.type==="CLOUDWATCH_ALARM").length,  cost: allResources.filter(r=>r.type==="CLOUDWATCH_ALARM").reduce((s,r)=>s+r.cost,0)   },
          { id: "lambda",    label: "Lambda Functions",     count: allResources.filter(r=>r.type==="LAMBDA_FUNCTION").length,  cost: allResources.filter(r=>r.type==="LAMBDA_FUNCTION").reduce((s,r)=>s+r.cost,0)   },
          { id: "eb",        label: "EventBridge Rules",    count: allResources.filter(r=>r.type==="EVENTBRIDGE_RULE").length,  cost: allResources.filter(r=>r.type==="EVENTBRIDGE_RULE").reduce((s,r)=>s+r.cost,0)   },
        ],
      },
      {
        id: "identity", label: "Identity", expanded: false,
        types: [
          { id: "iam",       label: "IAM Users",            count: allResources.filter(r=>r.type==="IAM_USER").length,  cost: allResources.filter(r=>r.type==="IAM_USER").reduce((s,r)=>s+r.cost,0)   },
          { id: "iamkey",    label: "IAM Keys",             count: allResources.filter(r=>r.type==="IAM_KEY").length,  cost: allResources.filter(r=>r.type==="IAM_KEY").reduce((s,r)=>s+r.cost,0)   },
        ],
      },
  ];
"""
    raw_code = raw_code.replace('export default function ResourceHygiene() {', main_comp, 1)

    # Replace the mocked const states that were inside with nothing, as they are now in the main replacement
    raw_code = raw_code.replace('const [activeType, setActiveType]     = useState("instance");', '')
    raw_code = raw_code.replace('const [selected, setSelected]         = useState(new Set());', '')
    raw_code = raw_code.replace('const [statusFilter, setStatusFilter] = useState("ALL");', '')
    raw_code = raw_code.replace('const [search, setSearch]             = useState("");', '')
    raw_code = raw_code.replace('const [sidebarCats, setSidebarCats]   = useState(\n    Object.fromEntries(SIDEBAR_CATEGORIES.map(c => [c.id, c.expanded]))\n  );', '')
    
    # Remove the mock memo
    remove_mock_memo_start = raw_code.find('const filteredResources = useMemo(() => {')
    remove_mock_memo_end = raw_code.find('const handleSelect = (id) => {', remove_mock_memo_start)
    if remove_mock_memo_start != -1 and remove_mock_memo_end != -1:
         raw_code = raw_code[:remove_mock_memo_start] + raw_code[remove_mock_memo_end:]

    # Remove the handleSelectAll, selectedCount etc that are mocked
    remove_mock_handlers_start = raw_code.find('const handleSelectAll = (ids) => {')
    remove_mock_handlers_end = raw_code.find('return (', remove_mock_handlers_start)
    if remove_mock_handlers_start != -1 and remove_mock_handlers_end != -1:
         raw_code = raw_code[:remove_mock_handlers_start] + raw_code[remove_mock_handlers_end:]

    # Fix Sidebar dynamic rendering references
    raw_code = raw_code.replace('<Sidebar activeType={activeType} onSelect={setActiveType} />', '<Sidebar activeType={activeType} onSelect={setActiveType} categories={SIDEBAR_CATEGORIES} />')

    replace_sidebar = """const Sidebar = ({ activeType, onSelect, categories }) => {
  const [expanded, setExpanded] = useState(
    Object.fromEntries(categories.map(c => [c.id, c.expanded]))
  );

  const totalCost = categories.flatMap(c => c.types).reduce((s, t) => s + t.cost, 0);"""
    
    raw_code = raw_code.replace("""const Sidebar = ({ activeType, onSelect }) => {
  const [expanded, setExpanded] = useState(
    Object.fromEntries(SIDEBAR_CATEGORIES.map(c => [c.id, c.expanded]))
  );

  const totalCost = SIDEBAR_CATEGORIES.flatMap(c => c.types).reduce((s, t) => s + t.cost, 0);""", replace_sidebar)

    raw_code = raw_code.replace('SIDEBAR_CATEGORIES.map(cat =>', 'categories.map(cat =>')

    # Fix the actions top bar replacements
    replace_top_bar = """{/* Replace the hardcoded topbar UI with FilterPanel */}
      <div style={{ position: "sticky", top: 0, zIndex: 20 }}>
          <FilterPanel
              accounts={accounts}
              selectedAccount={selectedAccount}
              onAccountChange={setSelectedAccount}
              selectedRegion={selectedRegion}
              onRegionChange={setSelectedRegion}
              regionsList={regionsList}
              onRefresh={() => handleScan(true)}
              loading={loading}
              lastScan={scanResult?.metadata?.scan_time}
          />
      </div>"""
      
    start_top_bar = raw_code.find('{/* ── TOP BAR ── */}')
    end_top_bar = raw_code.find('{/* ── KPI STRIP ── */}')
    raw_code = raw_code[:start_top_bar] + replace_top_bar + "\n\n      " + raw_code[end_top_bar:]

    # Hook up bulk actions
    action_replace = """{
                label: "Authorize",   
                color: C.green,
                onClick: () => handleAction('AUTHORIZE')
              },
              { 
                label: "Unauthorize", 
                color: C.muted,
                onClick: () => handleAction('UNAUTHORIZE')
              },
              { 
                label: "Tag",         
                color: C.accent,
                onClick: () => setShowBulkTagWizard(true)
              },
              { 
                label: "Cleanup",     
                color: C.red,
                onClick: () => handleAction('TERMINATE')
              },
            ].map(a => (
              <button key={a.label} onClick={a.onClick} style={{"""
              
    raw_code = raw_code.replace("""{ label: "Authorize",   color: C.green  },
                { label: "Unauthorize", color: C.muted  },
                { label: "Tag",         color: C.accent },
                { label: "Cleanup",     color: C.red    },
              ].map(a => (
                <button key={a.label} style={{""", action_replace)
                
    # Fix the missing resources from MOCK_RESOURCES string template
    raw_code = raw_code.replace('Showing {filteredResources.length} of {MOCK_RESOURCES.length} resources', 'Showing {filteredResources.length} of {allResources.length} resources')

    # Add Modals to the end of component
    modals = """
            <RIWizard
                isOpen={showRIWizard}
                onClose={() => setShowRIWizard(false)}
                selectedResources={selectedResourceObjects}
            />
            <S3Wizard
                isOpen={showS3Wizard}
                onClose={() => setShowS3Wizard(false)}
                selectedResources={selectedResourceObjects}
            />
            <RDSWizard
                isOpen={showRDSWizard}
                onClose={() => setShowRDSWizard(false)}
                selectedResources={selectedResourceObjects}
            />
            {showBulkTagWizard && (
                <BulkTagWizard
                    isOpen={showBulkTagWizard}
                    onClose={() => setShowBulkTagWizard(false)}
                    selectedResources={selectedResourceObjects}
                    onComplete={() => handleScan(true)}
                    accountId={selectedAccount}
                    regionId={selectedRegion}
                />
            )}
    </div>
  );
}"""
    raw_code = raw_code.rsplit('</div>\n  );\n}', 1)[0] + modals

    with open(TARGET_FILE, "w") as f:
        f.write(raw_code)
    print(f"Successfully generated {TARGET_FILE}!")

if __name__ == "__main__":
    build()
