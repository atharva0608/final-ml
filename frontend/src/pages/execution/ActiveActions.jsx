import React, { useState, useEffect } from 'react';
import { FiZap, FiCheckCircle, FiAlertTriangle, FiClock, FiActivity, FiChevronDown, FiChevronUp, FiFilter, FiAlertCircle } from 'react-icons/fi';
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
  shadow: "0 1px 3px rgba(0,0,0,.06), 0 1px 2px rgba(0,0,0,.04)",
};

const STATUS_COLORS = {
  QUEUED:     { color: T.gray,    bg: T.grayLight },
  PENDING:    { color: T.primary, bg: T.primaryLight },  // DB: dispatched, waiting for agent
  PICKED_UP:  { color: T.primary, bg: T.primaryLight },  // DB: agent executing
  STARTING:   { color: T.primary, bg: T.primaryLight },
  IN_PROGRESS:{ color: T.primary, bg: T.primaryLight },
  VERIFYING:  { color: T.amber,   bg: T.amberLight },
  RETRYING:   { color: T.amber,   bg: T.amberLight },
  FAILED:     { color: T.red,     bg: T.redLight },
  BLOCKED:    { color: T.purple,  bg: T.purpleLight },
  COMPLETED:  { color: T.green,   bg: T.greenLight },
  DONE:       { color: T.green,   bg: T.greenLight },
  EXPIRED:    { color: T.gray,    bg: T.grayLight },
};

const statusToProgress = (status, observed) => {
  if (status === 'COMPLETED') return observed ? 100 : 90;  // 90 if agent reported but validator not yet confirmed
  if (status === 'PICKED_UP') return 60;
  if (status === 'PENDING')   return 20;
  if (status === 'FAILED')    return 100;
  if (status === 'IN_PROGRESS') return 70;
  return 40;
};

// --- Demo Data ---
const DEMO_DATA = {
  cluster_state: {
    active_count: 5,
    batch_limit: 10,
    mutex: true
  },
  agent_actions: [
    {
      id: "a1",
      action_type: "EMERGENCY_SHUTDOWN",
      status: "IN_PROGRESS",
      priority: "high",
      payload: { reason: "OOM killer detected on critical system nodes. Mitigating." },
      created_at: new Date().toISOString()
    },
    {
      id: "a2",
      action_type: "CORDON_NODE",
      status: "COMPLETED",
      payload: { node_name: "ip-10-0-12-34.ec2.internal", rebalancing_action_id: "ra1" }
    },
    {
      id: "a3",
      action_type: "DRAIN_NODE",
      status: "IN_PROGRESS",
      payload: { node_name: "ip-10-0-12-34.ec2.internal", rebalancing_action_id: "ra1" }
    },
    {
      id: "a4",
      action_type: "EVICT_POD",
      status: "IN_PROGRESS",
      payload: { workload_name: "payments-service", current_od: 2, target_od: 0, current_spot: 8, target_spot: 10 }
    },
    {
      id: "a5",
      action_type: "EVICT_POD",
      status: "FAILED",
      retry_count: 2,
      error_message: "PodDisruptionBudget prevented eviction",
      payload: { workload_name: "checkout-api", current_od: 1, target_od: 0, current_spot: 4, target_spot: 5 }
    },
    {
      id: "a6",
      action_type: "RIGHTSIZE_POD",
      status: "PENDING",
      payload: { workload_name: "recommendation-engine", current_resources: "4 CPU, 8GB", target_resources: "2 CPU, 4GB", pods_updated: 2, total_pods: 5, estimated_savings: 450 }
    },
    {
      id: "a7",
      action_type: "RIGHTSIZE_POD",
      status: "COMPLETED",
      payload: { workload_name: "search-api", current_resources: "8 CPU, 16GB", target_resources: "4 CPU, 8GB", pods_updated: 10, total_pods: 10, estimated_savings: 1200 }
    },
    {
      id: "a8",
      action_type: "PREFETCH_IMAGE",
      status: "QUEUED",
      created_at: new Date(Date.now() - 10000).toISOString()
    },
    {
      id: "a9",
      action_type: "UPDATE_SCALED_OBJECT",
      status: "QUEUED",
      created_at: new Date(Date.now() - 15000).toISOString()
    }
  ],
  rebalancing_actions: [
    {
      id: "ra1",
      source_node_name: "ip-10-0-12-34.ec2.internal",
      status: "IN_PROGRESS",
      progress: 66,
      engine_source: "karpenter",
      state_machine_stage: "DRAINING",
      duration: "45s"
    }
  ]
};

// --- Reusable Components ---
const Card = ({ children, style = {}, className = "" }) => (
  <div className={`bg-white rounded-2xl shadow-sm border border-gray-200 ${className}`} style={{ ...style }}>
    {children}
  </div>
);

const Badge = ({ children, color = T.primary, bg = T.primaryLight, style = {} }) => (
  <span style={{ display: "inline-flex", alignItems: "center", background: bg, color, fontSize: 11, fontWeight: 600, padding: "3px 8px", borderRadius: 4, letterSpacing: ".02em", whiteSpace: "nowrap", ...style }}>
    {children}
  </span>
);

const StatusBadge = ({ status }) => {
  const mappedStatus = STATUS_COLORS[status] || STATUS_COLORS.QUEUED;
  return <Badge color={mappedStatus.color} bg={mappedStatus.bg}>{status}</Badge>;
};

const ProgressBar = ({ progress, animated = true, showPercentage = true }) => (
  <div style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 12 }}>
    <div style={{ flex: 1, height: 6, background: T.borderLight, borderRadius: 3, overflow: 'hidden' }}>
      <div style={{
        height: '100%',
        width: `${Math.max(0, Math.min(100, progress))}%`,
        background: T.primary,
        borderRadius: 3,
        transition: 'width 0.5s ease',
      }} className={animated && progress < 100 ? "animate-pulse" : ""} />
    </div>
    {showPercentage && <span style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, width: 35, textAlign: 'right' }}>{Math.round(progress)}%</span>}
  </div>
);

const ExpandableCard = ({ title, children, defaultExpanded = true, badge = null, borderHighlight = null }) => {
  const [expanded, setExpanded] = useState(defaultExpanded);
  return (
    <Card style={borderHighlight ? { border: `1px solid ${borderHighlight}` } : {}} className="mb-4 overflow-hidden">
      <div 
        onClick={() => setExpanded(!expanded)}
        style={{ padding: '16px 20px', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: expanded ? `1px solid ${T.borderLight}` : 'none', background: expanded ? T.bg : T.surface }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, color: T.text, margin: 0 }}>{title}</h3>
          {badge}
        </div>
        <div style={{ color: T.textFaint }}>
          {expanded ? <FiChevronUp size={18} /> : <FiChevronDown size={18} />}
        </div>
      </div>
      {expanded && <div style={{ padding: '20px' }}>{children}</div>}
    </Card>
  );
};

const LiveIndicator = () => (
  <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: T.greenLight, padding: '4px 10px', borderRadius: 12, border: `1px solid ${T.borderLight}` }}>
    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
    <span style={{ fontSize: 11, fontWeight: 700, color: T.green, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Live</span>
  </div>
);

// --- Custom Hook for Live Data ---
const useActiveActions = (clusterId) => {
  const [data, setData] = useState({ agent_actions: [], rebalancing_actions: [], cluster_state: { active_count: 0, batch_limit: 10, mutex: false } });
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
        const res = await api.get('/api/v1/actions/active', { params: { cluster_id: clusterId } });
        if (isMounted) {
          setData(res.data);
          setError(null);
          setLoading(false);
        }
      } catch (err) {
        if (isMounted) {
          console.warn("Failed to fetch active actions:", err);
          setError(err.message || 'Failed to fetch active actions');
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
              if (msg.type === 'ACTION_UPDATE') {
                setData(msg.data);
              }
            } catch(e) { console.error("WS Parse Error", e); }
          }
        };
        ws.onerror = (e) => {
          console.warn("WebSocket error, falling back to polling");
          if (isMounted && !pollInterval) {
            pollInterval = setInterval(fetchData, 5000);
          }
        };
        ws.onclose = () => {
          if (isMounted && !pollInterval) {
             pollInterval = setInterval(fetchData, 5000);
          }
        };
      } catch (e) {
        if (isMounted && !pollInterval) {
           pollInterval = setInterval(fetchData, 5000);
        }
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


// --- Main Page Component ---
const ActiveActions = () => {
  const { clusters: apiClusters, selectedId: realSelectedId, setSelectedId } = useClusters();
  
  // Inject demo cluster
  const clusters = [{ id: 'demo-cluster', name: 'Demo Cluster (All Features)' }, ...apiClusters];
  
  // Set default selection to demo-cluster if not set or not in apiClusters
  const [localClusterId, setLocalClusterId] = useState('demo-cluster');
  
  const clusterId = localClusterId;
  
  const handleClusterChange = (e) => {
    const val = e.target.value;
    setLocalClusterId(val);
    if (val !== 'demo-cluster') {
      setSelectedId(val);
    }
  };

  const { data, loading, error } = useActiveActions(clusterId);
  const [filter, setFilter] = useState('All'); // 'All', 'Node', 'Pod', 'Rightsizing', 'Emergency'

  // --- Derived Data ---
  const actions = data.agent_actions || [];
  const rebalActions = data.rebalancing_actions || [];
  const state = data.cluster_state || { batch_limit: 0, mutex: false };

  const activeCount = actions.filter(a => ['PENDING', 'PICKED_UP', 'IN_PROGRESS'].includes(a.status)).length;
  const failureCount = actions.filter(a => a.status === 'FAILED').length;
  
  // Groupings based on spec
  const emergencyActions = actions.filter(a => a.priority === 'high' || a.action_type?.includes('EMERGENCY'));
  
  const nodeActions = actions.filter(a => a.action_type === 'CORDON_NODE' || a.action_type === 'DRAIN_NODE' || a.action_type === 'TERMINATE_NODE');
  const nodeGroups = rebalActions.map(ra => {
     const relatedActions = nodeActions.filter(a => a.payload?.rebalancing_action_id === ra.id);
     return { ...ra, relatedActions };
  });

  const workloadActions = actions.filter(a => a.action_type === 'EVICT_POD' || a.payload?.workload_name && !a.action_type.includes('RIGHTSIZE'));
  const rightsizingActions = actions.filter(a => a.action_type === 'RIGHTSIZE_POD' || a.payload?.is_rightsizing);
  const queuedActions = actions.filter(a => a.status === 'PENDING' || a.status === 'QUEUED');
  const attentionActions = actions.filter(a => a.status === 'FAILED' || (a.retry_count && a.retry_count > 0));

  // Handlers
  const handleFilter = (f) => setFilter(f);
  const shouldShow = (type) => filter === 'All' || filter === type;

  // Renderers
  const renderStatsRow = () => (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
      <Card style={{ padding: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase', marginBottom: 4 }}>Active Actions</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: T.primary }}>{activeCount}</div>
      </Card>
      <Card style={{ padding: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase', marginBottom: 4 }}>Batch Limit</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: T.text }}>{state.batch_limit}</div>
      </Card>
      <Card style={{ padding: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase', marginBottom: 4 }}>Mutex Status</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: state.mutex ? T.amber : T.green }}>{state.mutex ? 'LOCKED' : 'FREE'}</div>
      </Card>
      <Card style={{ padding: 16 }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase', marginBottom: 4 }}>Failures (24h)</div>
        <div style={{ fontSize: 24, fontWeight: 800, color: failureCount > 0 ? T.red : T.text }}>{failureCount}</div>
      </Card>
    </div>
  );

  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div className="max-w-[1400px] mx-auto space-y-6">
        
        {/* Header Controls */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 }}>
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-50 rounded-lg">
                <FiActivity className="w-5 h-5 text-indigo-600" />
              </div>
              <h1 className="text-2xl font-bold text-gray-900 m-0">Live Execution Inspector</h1>
            </div>
            <p className="text-sm text-gray-500 mt-2">Displaying in-flight system actions with real-time status and progress.</p>
            
            <div style={{ marginTop: 16 }}>
              <select 
                value={clusterId} 
                onChange={handleClusterChange}
                style={{ padding: '8px 12px', borderRadius: 8, border: `1px solid ${T.border}`, background: T.surface, fontSize: 14, fontWeight: 500, color: T.text, minWidth: 250, outline: 'none', boxShadow: T.shadow }}
              >
                {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 16 }}>
            <LiveIndicator />
            <div style={{ display: 'flex', background: T.borderLight, padding: 4, borderRadius: 8 }}>
              {['All', 'Node', 'Pod', 'Rightsizing', 'Emergency'].map(f => (
                <button
                  key={f}
                  onClick={() => handleFilter(f)}
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

        {error && clusterId !== 'demo-cluster' && (
           <div style={{ padding: 12, background: T.redLight, border: `1px solid ${T.red}`, borderRadius: 8, color: T.red, fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
             <FiAlertTriangle /> {error}. Showing fallback or stale data.
           </div>
        )}

        {/* Execution Summary Bar */}
        {renderStatsRow()}

        {loading && <div className="text-center p-12 text-gray-500 text-sm">Connecting to Execution Stream...</div>}

        {!loading && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            
            {/* EMERGENCY GROUP */}
            {shouldShow('Emergency') && emergencyActions.length > 0 && (
              <ExpandableCard title="Emergency Actions" badge={<Badge color={T.red} bg={T.redLight}>High Priority</Badge>} borderHighlight={T.red}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {emergencyActions.map(a => (
                    <div key={a.id} style={{ display: 'flex', justifyContent: 'space-between', padding: 12, border: `1px solid ${T.borderLight}`, borderRadius: 8, background: T.surface }}>
                       <div>
                         <div style={{ fontSize: 13, fontWeight: 600, color: T.text }}>{a.action_type}</div>
                         <div style={{ fontSize: 11, color: T.textMuted }}>{a.payload?.reason || 'System mitigation'}</div>
                       </div>
                       <StatusBadge status={a.status} />
                    </div>
                  ))}
                </div>
              </ExpandableCard>
            )}

            {/* NODE REBALANCING GROUP */}
            {shouldShow('Node') && (nodeGroups.length > 0 || nodeActions.length > 0) && (
              <ExpandableCard title="Node Rebalancing" badge={<Badge>{nodeGroups.length} Active</Badge>}>
                {nodeGroups.length === 0 && nodeActions.map(a => (
                  <div key={a.id} style={{ padding: 12, borderBottom: `1px solid ${T.borderLight}` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{a.payload?.node_name || 'Unknown Node'}</span>
                      <StatusBadge status={a.status} />
                    </div>
                    <div style={{ fontSize: 11, color: T.textMuted, marginBottom: 8 }}>{a.action_type}</div>
                  </div>
                ))}
                {nodeGroups.map(ng => (
                   <div key={ng.id} style={{ padding: 16, border: `1px solid ${T.border}`, borderRadius: 8, marginBottom: 12, background: T.bg }}>
                     <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                        <div>
                          <div style={{ fontSize: 14, fontWeight: 700, color: T.text }}>{ng.source_node_name}</div>
                          <div style={{ fontSize: 12, color: T.textMid, marginTop: 4 }}>
                             <span style={{ fontWeight: 600 }}>ON-DEMAND</span> → <span style={{ fontWeight: 600, color: T.primary }}>SPOT</span>
                          </div>
                        </div>
                        <StatusBadge status={ng.status || 'IN_PROGRESS'} />
                     </div>
                     <ProgressBar progress={ng.progress || 33} animated={ng.status !== 'FAILED'} />
                     <div style={{ display: 'flex', gap: 16, marginTop: 12, fontSize: 11, color: T.textMuted }}>
                        <span>Engine: <strong style={{color: T.textMid}}>{ng.engine_source || 'karpenter'}</strong></span>
                        <span>Stage: <strong style={{color: T.textMid}}>{ng.state_machine_stage || 'CORDONED'}</strong></span>
                        <span>Duration: <strong style={{color: T.textMid}}>{ng.duration || '0s'}</strong></span>
                     </div>
                   </div>
                ))}
              </ExpandableCard>
            )}

            {/* WORKLOAD REDISTRIBUTION GROUP */}
            {shouldShow('Pod') && workloadActions.length > 0 && (
              <ExpandableCard title="Workload Redistribution" badge={<Badge>{workloadActions.length} Pods</Badge>}>
                <table style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${T.border}`, fontSize: 11, color: T.textFaint, textTransform: 'uppercase' }}>
                      <th style={{ padding: '8px 12px' }}>Workload</th>
                      <th style={{ padding: '8px 12px' }}>Placement Drift (OD vs Spot)</th>
                      <th style={{ padding: '8px 12px' }}>Progress</th>
                      <th style={{ padding: '8px 12px' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workloadActions.map(a => (
                      <tr key={a.id} style={{ borderBottom: `1px solid ${T.borderLight}`, fontSize: 13 }}>
                        <td style={{ padding: '12px', fontWeight: 500 }}>{a.payload?.workload_name || 'Unknown Pod'}</td>
                        <td style={{ padding: '12px', color: T.textMid }}>
                           OD: {a.payload?.current_od || 0} → {a.payload?.target_od || 0}, SPOT: {a.payload?.current_spot || 0} → {a.payload?.target_spot || 0}
                        </td>
                        <td style={{ padding: '12px', width: '30%' }}>
                           <ProgressBar progress={statusToProgress(a.status, a.observed)} showPercentage={false} />
                        </td>
                        <td style={{ padding: '12px' }}>
                           <StatusBadge status={a.status} />
                           {a.observed && <span style={{ fontSize: 10, color: T.green, marginLeft: 8, fontWeight: 700 }}>✓ Verified</span>}
                           {a.failure_reason === 'deadline_exceeded' && <span style={{ fontSize: 10, color: T.red, marginLeft: 8 }}>Timeout</span>}
                           {a.retry_count > 0 && <span style={{ fontSize: 10, color: T.amber, marginLeft: 8 }}>Retry {a.retry_count}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ExpandableCard>
            )}

            {/* RIGHTSIZING GROUP */}
            {shouldShow('Rightsizing') && rightsizingActions.length > 0 && (
              <ExpandableCard title="Rightsizing Proposals" badge={<Badge>{rightsizingActions.length} Active</Badge>}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                  {rightsizingActions.map(a => (
                    <div key={a.id} style={{ padding: 12, border: `1px solid ${T.border}`, borderRadius: 8, background: T.surface }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                         <span style={{ fontSize: 13, fontWeight: 600 }}>{a.payload?.workload_name || 'Pod Rightsizing'}</span>
                         <StatusBadge status={a.status} />
                      </div>
                      <div style={{ fontSize: 12, color: T.textMid, marginBottom: 12 }}>
                         {a.payload?.current_resources} → {a.payload?.target_resources}
                      </div>
                      <ProgressBar progress={Math.min(100, (a.payload?.pods_updated || 0) / (a.payload?.total_pods || 1) * 100)} />
                      <div style={{ fontSize: 11, color: T.green, fontWeight: 600, marginTop: 8 }}>
                        Est Savings: ${a.payload?.estimated_savings || 0}/mo
                      </div>
                    </div>
                  ))}
                </div>
              </ExpandableCard>
            )}

            {/* QUEUED ACTIONS */}
            {queuedActions.length > 0 && (
              <ExpandableCard title="Queued Actions" defaultExpanded={false} badge={<Badge color={T.gray} bg={T.grayLight}>{queuedActions.length} Pending</Badge>}>
                <div style={{ fontSize: 12, color: T.textMid }}>
                  {queuedActions.slice(0, 5).map(a => (
                    <div key={a.id} style={{ padding: '8px 0', borderBottom: `1px solid ${T.borderLight}` }}>
                       <span style={{ fontWeight: 600, marginRight: 8 }}>{a.action_type}</span>
                       <span style={{ color: T.textMuted }}>{new Date(a.created_at || Date.now()).toLocaleTimeString()}</span>
                    </div>
                  ))}
                  {queuedActions.length > 5 && <div style={{ paddingTop: 8, color: T.textMuted, fontStyle: 'italic' }}>+ {queuedActions.length - 5} more queued...</div>}
                </div>
              </ExpandableCard>
            )}

            {/* ATTENTION REQUIRED */}
            {attentionActions.length > 0 && (
              <ExpandableCard title="Attention Required" borderHighlight={T.amber} defaultExpanded={true} badge={<Badge color={T.amber} bg={T.amberLight}>{attentionActions.length} Items</Badge>}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {attentionActions.map(a => (
                    <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 12, background: T.redLight, border: `1px solid ${T.red}`, borderRadius: 8 }}>
                      <FiAlertCircle className="text-red-600" size={18} />
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: T.red }}>Action {a.action_type} Failed/Retrying</div>
                        <div style={{ fontSize: 11, color: T.red, opacity: 0.8 }}>{a.error_message || 'Timeout or validation error during execution'}</div>
                      </div>
                      <StatusBadge status={a.status} />
                    </div>
                  ))}
                </div>
              </ExpandableCard>
            )}

            {/* Empty State if absolutely nothing is active */}
            {filter === 'All' && emergencyActions.length===0 && nodeGroups.length===0 && nodeActions.length===0 && workloadActions.length===0 && rightsizingActions.length===0 && queuedActions.length===0 && attentionActions.length===0 && (
              <div style={{ padding: 48, textAlign: 'center', background: T.surface, border: `1px dashed ${T.border}`, borderRadius: 12 }}>
                <FiCheckCircle size={32} style={{ margin: '0 auto 16px', color: T.green }} />
                <h3 style={{ fontSize: 16, fontWeight: 600, color: T.text, margin: '0 0 4px' }}>System Stable</h3>
                <p style={{ fontSize: 13, color: T.textMuted, margin: 0 }}>No active actions or rebalancing operations are currently in flight.</p>
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  );
};

export default ActiveActions;
