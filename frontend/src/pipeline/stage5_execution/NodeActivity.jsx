import React, { useState, useEffect } from 'react';
import { FiSearch, FiChevronDown, FiChevronUp, FiServer } from 'react-icons/fi';
import useClusters from '../../hooks/useClusters';
import { api } from '../../services/api';

// --- Theme & Styles ---
const T = {
  bg: "#f8f9fb",
  surface: "#ffffff",
  border: "#e5e7eb",
  borderLight: "#f3f4f6",
  text: "#111827",
  textMid: "#374151",
  textMuted: "#6b7280",
  textFaint: "#9ca3af",
  primary: "#4f46e5",
  primaryLight: "#eef2ff",
  green: "#059669",
  greenLight: "#ecfdf5",
  amber: "#d97706",
  amberLight: "#fffbeb",
  red: "#dc2626",
  redLight: "#fef2f2",
  purple: "#7c3aed",
  purpleLight: "#ede9fe",
  gray: "#4b5563",
  grayLight: "#f3f4f6",
  shadow: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
};

// --- Reusable Small Components ---
const Badge = ({ children, color = T.primary, bg = T.primaryLight, style = {} }) => (
  <span style={{ display: "inline-flex", alignItems: "center", background: bg, color, fontSize: 11, fontWeight: 600, padding: "2px 6px", borderRadius: 4, letterSpacing: ".02em", whiteSpace: "nowrap", ...style }}>
    {children}
  </span>
);

const StatusBadge = ({ status }) => {
  const map = {
    QUEUED: { color: T.gray, bg: T.grayLight },
    IN_PROGRESS: { color: T.primary, bg: T.primaryLight },
    VERIFYING: { color: T.amber, bg: T.amberLight },
    RETRYING: { color: T.amber, bg: T.amberLight },
    FAILED: { color: T.red, bg: T.redLight },
    IDLE: { color: T.gray, bg: "transparent", border: `1px solid ${T.border}` }
  };
  const s = map[status] || map.IDLE;
  return (
    <div style={{ display: "inline-flex", alignItems: "center", background: s.bg, color: s.color, border: s.border || 'none', fontSize: 10, fontWeight: 700, padding: "2px 6px", borderRadius: 4 }}>
      {status === 'IN_PROGRESS' && <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse mr-1.5" />}
      {status === 'VERIFYING' && <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse mr-1.5" />}
      {status}
    </div>
  );
};

const CombinedUsageBar = ({ cpuUsed, cpuTotal, memUsed, memTotal }) => {
  const cpuPct = cpuTotal > 0 ? (cpuUsed / cpuTotal) * 100 : 0;
  const memPct = memTotal > 0 ? (memUsed / memTotal) * 100 : 0;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: 140 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: T.textMid, marginBottom: 4 }}>
        CPU {Math.round(cpuPct)}% <span style={{color: T.border, margin: '0 4px'}}>•</span> MEM {Math.round(memPct)}%
      </div>
      <div style={{ display: 'flex', gap: 4 }}>
        <div style={{ flex: 1, height: 4, background: T.borderLight, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ width: `${Math.min(100, cpuPct)}%`, height: '100%', background: cpuPct > 90 ? T.red : cpuPct > 75 ? T.amber : T.primary, borderRadius: 2 }} />
        </div>
        <div style={{ flex: 1, height: 4, background: T.borderLight, borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ width: `${Math.min(100, memPct)}%`, height: '100%', background: memPct > 90 ? T.red : memPct > 75 ? T.amber : T.purple, borderRadius: 2 }} />
        </div>
      </div>
    </div>
  );
};

const InlineProgressBar = ({ progress }) => {
  if (progress === undefined || progress === null) return null;
  return (
    <div style={{ width: 80, display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ flex: 1, height: 4, background: T.borderLight, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ width: `${progress}%`, height: '100%', background: T.primary }} className="animate-pulse" />
      </div>
      <span style={{ fontSize: 10, fontWeight: 600, color: T.textMuted }}>{Math.round(progress)}%</span>
    </div>
  );
};

// --- DEMO DATA ---
const DEMO_DATA = {
  nodes: [
    {
      id: "n1",
      node_name: "ip-10-0-12-34.ec2.internal",
      instance_type: "m5.large",
      az: "ap-south-1a",
      capacity_type: "ON_DEMAND",
      lifecycle_state: "REBALANCING",
      cpu: { used: 2.8, total: 4.0 },
      memory: { used: 5.2, total: 8.0 },
      pods: { used: 18, capacity: 29 },
      od_spot_dist: { od: 12, spot: 6 },
      fit: { pods: 11, cpu: 1.2, memory: 2.8 },
      target_plan: { type: "SPOT", instance: "c6a.large", fit: 25, az: "ap-south-1a" },
      action: {
        type: "Rebalancing",
        status: "IN_PROGRESS",
        step: "DRAINING",
        progress: 70,
        duration: "2m 14s",
        pods_evicted: "3 / 5",
        retry_count: 0
      },
      decision_context: { trigger_reason: "Cost Optimization", source_engine: "RebalanceEngine", confidence: "95%" },
      guards: { mutex: "ACTIVE", batch_limit: "2 / 2", cooldown: "ACTIVE", scaling_guard: "ACTIVE" },
      overrides: { od_fallback: "OFF", manual_approval: "OFF", conservative: "OFF" }
    },
    {
      id: "n2",
      node_name: "ip-10-0-15-88.ec2.internal",
      instance_type: "t3.medium",
      az: "ap-south-1b",
      capacity_type: "ON_DEMAND",
      lifecycle_state: "ACTIVE",
      cpu: { used: 0.5, total: 2.0 },
      memory: { used: 1.2, total: 4.0 },
      pods: { used: 4, capacity: 17 },
      od_spot_dist: { od: 4, spot: 0 },
      fit: { pods: 13, cpu: 1.5, memory: 2.8 },
      target_plan: null,
      action: { type: "Idle", status: "IDLE" },
      decision_context: { trigger_reason: "-", source_engine: "-", confidence: "-" },
      guards: { mutex: "FREE", batch_limit: "0 / 2", cooldown: "INACTIVE", scaling_guard: "INACTIVE" },
      overrides: { od_fallback: "OFF", manual_approval: "OFF", conservative: "OFF" }
    },
    {
      id: "n3",
      node_name: "ip-10-0-44-12.ec2.internal",
      instance_type: "r6i.xlarge",
      az: "ap-south-1a",
      capacity_type: "SPOT",
      lifecycle_state: "ACTIVE",
      cpu: { used: 3.8, total: 4.0 },
      memory: { used: 28.5, total: 32.0 },
      pods: { used: 25, capacity: 58 },
      od_spot_dist: { od: 0, spot: 25 },
      fit: { pods: 33, cpu: 0.2, memory: 3.5 },
      target_plan: null,
      action: { type: "Rightsizing", status: "VERIFYING", progress: 90, duration: "45s", step: "Pods stabilizing", retry_count: 0 },
      decision_context: { trigger_reason: "Memory Starvation", source_engine: "RightsizingAgent", confidence: "99%" },
      guards: { mutex: "FREE", batch_limit: "0 / 2", cooldown: "INACTIVE", scaling_guard: "INACTIVE" },
      overrides: { od_fallback: "OFF", manual_approval: "OFF", conservative: "OFF" }
    },
    {
      id: "n4",
      node_name: "ip-10-0-22-99.ec2.internal",
      instance_type: "m5.xlarge",
      az: "ap-south-1c",
      capacity_type: "ON_DEMAND",
      lifecycle_state: "TERMINATING",
      cpu: { used: 0.1, total: 4.0 },
      memory: { used: 0.5, total: 16.0 },
      pods: { used: 2, capacity: 58 },
      od_spot_dist: { od: 2, spot: 0 },
      fit: { pods: 56, cpu: 3.9, memory: 15.5 },
      target_plan: { type: "SPOT", instance: "m6a.xlarge", fit: 50, az: "ap-south-1c" },
      action: { type: "Rebalancing", status: "IN_PROGRESS", step: "TERMINATING", progress: 95, duration: "4m 10s", retry_count: 1 },
      decision_context: { trigger_reason: "Spot Replacement", source_engine: "RebalanceEngine", confidence: "92%" },
      guards: { mutex: "ACTIVE", batch_limit: "2 / 2", cooldown: "ACTIVE", scaling_guard: "INACTIVE" },
      overrides: { od_fallback: "OFF", manual_approval: "OFF", conservative: "OFF" }
    },
    {
      id: "n5",
      node_name: "ip-10-0-33-11.ec2.internal",
      instance_type: "c6a.large",
      az: "ap-south-1a",
      capacity_type: "SPOT",
      lifecycle_state: "PROVISIONING",
      cpu: { used: 0, total: 2.0 },
      memory: { used: 0, total: 4.0 },
      pods: { used: 0, capacity: 29 },
      od_spot_dist: { od: 0, spot: 0 },
      fit: { pods: 29, cpu: 2.0, memory: 4.0 },
      target_plan: null,
      action: { type: "Scaling", status: "IN_PROGRESS", step: "STARTING", progress: 10, duration: "12s", retry_count: 0 },
      decision_context: { trigger_reason: "Scale Up", source_engine: "AutoScaler", confidence: "100%" },
      guards: { mutex: "ACTIVE", batch_limit: "1 / 2", cooldown: "ACTIVE", scaling_guard: "ACTIVE" },
      overrides: { od_fallback: "ON", manual_approval: "OFF", conservative: "OFF" }
    }
  ]
};

const useNodeActivity = (clusterId) => {
  const [data, setData] = useState({ nodes: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!clusterId) return;

    if (clusterId === 'demo-cluster') {
      setData(DEMO_DATA);
      setLoading(false);
      setError(null);
      return;
    }
    
    let isMounted = true;
    let ws = null;
    let pollInterval = null;

    const fetchData = async () => {
      try {
        const res = await api.get('/api/v1/nodes/activity', { params: { cluster_id: clusterId } });
        if (isMounted) {
          setData(res.data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          console.warn("Failed to fetch node activity:", err);
          setError(err.message || 'Failed to fetch node activity');
          setLoading(false);
        }
      }
    };

    fetchData();

    const setupWebSocket = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/cluster/${clusterId}`;
      try {
        ws = new WebSocket(wsUrl);
        ws.onmessage = (event) => {
          if (isMounted) {
            try {
              const msg = JSON.parse(event.data);
              if (msg.type === 'NODE_ACTIVITY_UPDATE') setData(msg.data);
            } catch(e) { console.error("WS Parse Error", e); }
          }
        };
        ws.onerror = () => {
          if (isMounted && !pollInterval) pollInterval = setInterval(fetchData, 5000);
        };
        ws.onclose = () => {
          if (isMounted && !pollInterval) pollInterval = setInterval(fetchData, 5000);
        };
      } catch (e) {
        if (isMounted && !pollInterval) pollInterval = setInterval(fetchData, 5000);
      }
    };

    setupWebSocket();

    return () => {
      isMounted = false;
      if (ws) ws.close();
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [clusterId]);

  return { data, loading, error };
};

// --- Expandable Row Component ---
const ExpandableRow = ({ node, isExpanded, onToggle }) => {
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer', background: isExpanded ? T.primaryLight : T.surface, borderBottom: `1px solid ${T.borderLight}`, transition: 'background 0.2s' }} className="hover:bg-gray-50">
        <td style={{ padding: '8px 12px', fontSize: 13 }}>
           <div style={{ fontWeight: 600, color: T.text, display: 'flex', alignItems: 'center', gap: 6 }}>
             {isExpanded ? <FiChevronUp size={14} className="text-gray-400"/> : <FiChevronDown size={14} className="text-gray-400"/>}
             {node.node_name}
           </div>
           <div style={{ fontSize: 11, color: T.textMuted, marginLeft: 20 }}>{node.instance_type} | {node.az}</div>
        </td>
        <td style={{ padding: '8px 12px' }}>
           <Badge bg={node.capacity_type === 'SPOT' ? T.purpleLight : T.bg} color={node.capacity_type === 'SPOT' ? T.purple : T.textMid}>
             {node.capacity_type === 'SPOT' ? 'SPOT' : 'ON-DEMAND'}
           </Badge>
        </td>
        <td style={{ padding: '8px 12px', fontSize: 12, fontWeight: 500, color: T.textMid }}>
           {node.lifecycle_state}
        </td>
        <td style={{ padding: '8px 12px' }}>
           <CombinedUsageBar cpuUsed={node.cpu.used} cpuTotal={node.cpu.total} memUsed={node.memory.used} memTotal={node.memory.total} />
        </td>
        <td style={{ padding: '8px 12px', fontSize: 12, color: T.textMid, fontWeight: 500 }}>
          {node.pods.used} <span style={{ color: T.textFaint }}>/ {node.pods.capacity}</span>
        </td>
        <td style={{ padding: '8px 12px' }}>
           <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
             <div>
               <div style={{ fontSize: 12, fontWeight: 600, color: T.text }}>
                 {node.action.type} {node.action.step && <span style={{ color: T.textMuted, fontWeight: 400 }}>• {node.action.step}</span>}
               </div>
               <div style={{ marginTop: 2 }}>
                 <InlineProgressBar progress={node.action.progress} />
               </div>
             </div>
             <StatusBadge status={node.action.status} />
           </div>
        </td>
      </tr>
      {isExpanded && (
        <tr style={{ background: T.bg }}>
          <td colSpan={6} style={{ padding: 0, borderBottom: `1px solid ${T.border}` }}>
            <div style={{ padding: '24px 32px', display: 'flex', flexWrap: 'wrap', gap: 32 }}>
               
               {/* Execution Details */}
               <div style={{ flex: '1 1 200px' }}>
                 <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em' }}>Execution</div>
                 <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12, color: T.textMid, display: 'flex', flexDirection: 'column', gap: 6 }}>
                   <li>Action: <strong style={{ color: T.text }}>{node.action.type}</strong></li>
                   <li>Step: <strong style={{ color: T.text }}>{node.action.step || '-'}</strong></li>
                   {node.action.progress !== undefined && <li>Progress: <strong style={{ color: T.text }}>{node.action.progress}%</strong></li>}
                   {node.action.duration && <li>Duration: <strong style={{ color: T.text }}>{node.action.duration}</strong></li>}
                   <li>Retries: <strong style={{ color: T.text }}>{node.action.retry_count ?? 0}</strong></li>
                 </ul>
               </div>

               {/* Decision Context */}
               <div style={{ flex: '1 1 200px' }}>
                 <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em' }}>Decision Context</div>
                 <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12, color: T.textMid, display: 'flex', flexDirection: 'column', gap: 6 }}>
                   <li>Reason: <strong style={{ color: T.text }}>{node.decision_context.trigger_reason}</strong></li>
                   <li>Engine: <strong style={{ color: T.text }}>{node.decision_context.source_engine}</strong></li>
                   <li>Confidence: <strong style={{ color: T.text }}>{node.decision_context.confidence}</strong></li>
                 </ul>
               </div>

               {/* Capacity Snapshot */}
               <div style={{ flex: '1 1 200px' }}>
                 <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em' }}>Capacity Snapshot</div>
                 <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12, color: T.textMid, display: 'flex', flexDirection: 'column', gap: 6 }}>
                   <li>CPU: <strong>{node.cpu.used} / {node.cpu.total}</strong> <span style={{ color: T.textMuted }}>(+{node.fit.cpu} free)</span></li>
                   <li>Memory: <strong>{node.memory.used} / {node.memory.total} GB</strong> <span style={{ color: T.textMuted }}>(+{node.fit.memory} free)</span></li>
                   <li>Pods: <strong>{node.pods.used} / {node.pods.capacity}</strong> <span style={{ color: T.textMuted }}>(+{node.fit.pods} free)</span></li>
                 </ul>
               </div>

               {/* Placement Impact */}
               <div style={{ flex: '1 1 200px' }}>
                 <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em' }}>Placement Impact</div>
                 <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12, color: T.textMid, display: 'flex', flexDirection: 'column', gap: 6 }}>
                   <li>Current OD Pods: <strong style={{ color: T.text }}>{node.od_spot_dist.od}</strong></li>
                   <li>Current SPOT Pods: <strong style={{ color: T.text }}>{node.od_spot_dist.spot}</strong></li>
                   {node.target_plan && <li>Target OD Pods: <strong style={{ color: T.text }}>0</strong></li>}
                   {node.target_plan && <li>Target SPOT Pods: <strong style={{ color: T.text }}>{node.target_plan.fit}</strong></li>}
                 </ul>
               </div>

               {/* Target Plan */}
               <div style={{ flex: '1 1 200px' }}>
                 <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em' }}>Target Plan</div>
                 {node.target_plan ? (
                   <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12, color: T.textMid, display: 'flex', flexDirection: 'column', gap: 6 }}>
                     <li>Type: <strong style={{ color: T.purple }}>{node.target_plan.type}</strong></li>
                     <li>Instance: <strong style={{ color: T.text }}>{node.target_plan.instance}</strong></li>
                     <li>AZ: <strong style={{ color: T.text }}>{node.target_plan.az}</strong></li>
                     <li>Expected Fit: <strong style={{ color: T.text }}>{node.target_plan.fit} pods</strong></li>
                   </ul>
                 ) : <span style={{ fontSize: 12, color: T.textFaint }}>No active target.</span>}
               </div>

               {/* Guards & Overrides */}
               <div style={{ flex: '1 1 200px' }}>
                 <div style={{ fontSize: 11, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', marginBottom: 8, letterSpacing: '0.05em' }}>Guards & Overrides</div>
                 <ul style={{ listStyle: 'none', padding: 0, margin: 0, fontSize: 12, color: T.textMid, display: 'flex', flexDirection: 'column', gap: 6 }}>
                   <li>Mutex: <strong style={{ color: node.guards.mutex === 'ACTIVE' ? T.amber : T.green }}>{node.guards.mutex}</strong></li>
                   <li>Batch Limit: <strong style={{ color: T.text }}>{node.guards.batch_limit}</strong></li>
                   <li>Cooldown: <strong style={{ color: node.guards.cooldown === 'ACTIVE' ? T.amber : T.text }}>{node.guards.cooldown}</strong></li>
                   <li>Scaling Guard: <strong style={{ color: node.guards.scaling_guard === 'ACTIVE' ? T.amber : T.text }}>{node.guards.scaling_guard}</strong></li>
                   <li style={{ marginTop: 4, paddingTop: 4, borderTop: `1px solid ${T.borderLight}` }}>OD Fallback: <strong style={{ color: T.text }}>{node.overrides.od_fallback}</strong></li>
                   <li>Conservative: <strong style={{ color: T.text }}>{node.overrides.conservative}</strong></li>
                 </ul>
               </div>

            </div>
          </td>
        </tr>
      )}
    </>
  );
};

// --- Main Component ---
const NodeActivity = () => {
  const { clusters: apiClusters, selectedId: realSelectedId, setSelectedId } = useClusters();
  
  // Inject demo cluster natively
  const clusters = [{ id: 'demo-cluster', name: 'Demo Cluster (All Features)' }, ...apiClusters];
  const [localClusterId, setLocalClusterId] = useState('demo-cluster');
  
  const handleClusterChange = (e) => {
    const val = e.target.value;
    setLocalClusterId(val);
    if (val !== 'demo-cluster') setSelectedId(val);
  };

  const { data, loading } = useNodeActivity(localClusterId);
  const [filter, setFilter] = useState('All');
  const [search, setSearch] = useState('');
  const [expandedRows, setExpandedRows] = useState({});

  const toggleRow = (id) => {
    setExpandedRows(prev => ({ ...prev, [id]: !prev[id] }));
  };

  // Groupings logic
  const nodes = data.nodes || [];
  
  // Filter and Search
  const filteredNodes = nodes.filter(n => {
    const matchesSearch = n.node_name.toLowerCase().includes(search.toLowerCase()) || n.instance_type.toLowerCase().includes(search.toLowerCase());
    const matchesFilter = 
      filter === 'All' || 
      (filter === 'Spot' && n.capacity_type === 'SPOT') ||
      (filter === 'On-Demand' && n.capacity_type === 'ON_DEMAND') ||
      (filter === 'Rebalancing' && n.action.type === 'Rebalancing') ||
      (filter === 'Idle' && n.action.type === 'Idle');
    return matchesSearch && matchesFilter;
  });

  const rebalancingNodes = filteredNodes.filter(n => n.lifecycle_state === 'REBALANCING' || n.lifecycle_state === 'TERMINATING' || n.lifecycle_state === 'PROVISIONING');
  const spotNodes = filteredNodes.filter(n => n.capacity_type === 'SPOT' && !rebalancingNodes.find(r => r.id === n.id));
  const odNodes = filteredNodes.filter(n => n.capacity_type === 'ON_DEMAND' && !rebalancingNodes.find(r => r.id === n.id));

  const renderTableSection = (title, count, sectionNodes) => {
    if (sectionNodes.length === 0) return null;
    return (
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12, paddingBottom: 8, borderBottom: `2px solid ${T.border}` }}>
          {title} ({count})
        </div>
        <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8, overflow: 'hidden', boxShadow: T.shadow }}>
          <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: T.bg, borderBottom: `1px solid ${T.borderLight}` }}>
                <th style={{ padding: '8px 12px', fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase' }}>Node</th>
                <th style={{ padding: '8px 12px', fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase' }}>Type</th>
                <th style={{ padding: '8px 12px', fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase' }}>State</th>
                <th style={{ padding: '8px 12px', fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase' }}>Utilization</th>
                <th style={{ padding: '8px 12px', fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase' }}>Pods</th>
                <th style={{ padding: '8px 12px', fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase' }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {sectionNodes.map(node => (
                <ExpandableRow key={node.id} node={node} isExpanded={!!expandedRows[node.id]} onToggle={() => toggleRow(node.id)} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div className="max-w-[1500px] mx-auto space-y-6">
        
        {/* Header Controls */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 32 }}>
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-50 rounded-lg">
                <FiServer className="w-5 h-5 text-indigo-600" />
              </div>
              <h1 className="text-2xl font-bold text-gray-900 m-0">Node Activity</h1>
            </div>
            <p className="text-sm text-gray-500 mt-2">Dense operator view of real-time node states, capacity, and execution activity.</p>
            
            <div style={{ marginTop: 16 }}>
              <select 
                value={localClusterId} 
                onChange={handleClusterChange}
                style={{ padding: '8px 12px', borderRadius: 8, border: `1px solid ${T.border}`, background: T.surface, fontSize: 14, fontWeight: 500, color: T.text, minWidth: 250, outline: 'none', boxShadow: T.shadow }}
              >
                {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 16 }}>
             <div style={{ position: 'relative' }}>
                <FiSearch style={{ position: 'absolute', left: 12, top: 10, color: T.textMuted }} />
                <input 
                  type="text" 
                  placeholder="Search nodes..." 
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  style={{ padding: '8px 12px 8px 36px', borderRadius: 8, border: `1px solid ${T.border}`, background: T.surface, fontSize: 13, width: 250, outline: 'none' }}
                />
             </div>
            <div style={{ display: 'flex', background: T.borderLight, padding: 4, borderRadius: 8 }}>
              {['All', 'Spot', 'On-Demand', 'Rebalancing', 'Idle'].map(f => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  style={{
                    padding: '6px 16px',
                    borderRadius: 6,
                    fontSize: 13,
                    fontWeight: 600,
                    border: 'none',
                    cursor: 'pointer',
                    background: filter === f ? T.surface : 'transparent',
                    color: filter === f ? T.text : T.textMuted,
                    boxShadow: filter === f ? T.shadow : 'none',
                    transition: 'all 0.2s'
                  }}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Node Table Sections */}
        {loading ? (
          <div className="text-center p-12 text-gray-500 text-sm">Connecting to Node Activity Stream...</div>
        ) : (
          <div>
            {renderTableSection('Rebalancing', rebalancingNodes.length, rebalancingNodes)}
            {renderTableSection('Spot Nodes', spotNodes.length, spotNodes)}
            {renderTableSection('On-Demand Nodes', odNodes.length, odNodes)}
            
            {filteredNodes.length === 0 && (
               <div style={{ padding: 48, textAlign: 'center', background: T.surface, border: `1px dashed ${T.border}`, borderRadius: 12 }}>
                 <p style={{ fontSize: 14, color: T.textMuted, margin: 0 }}>No nodes found matching your filters.</p>
               </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default NodeActivity;
