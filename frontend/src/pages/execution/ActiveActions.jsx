import React, { useState, useEffect } from 'react';
import { FiZap, FiCheckCircle, FiAlertTriangle, FiClock, FiActivity, FiChevronDown, FiChevronUp, FiAlertCircle } from 'react-icons/fi';
import useClusters from '../../hooks/useClusters';
import { api } from '../../services/api';

const T = {
  bg: "#f8f9fb", surface: "#ffffff", border: "#e5e7eb",
  borderLight: "#f3f4f6", text: "#111827", textMid: "#374151",
  textMuted: "#6b7280", textFaint: "#9ca3af", primary: "#4f46e5",
  primaryLight: "#eef2ff", green: "#059669", greenLight: "#ecfdf5",
  amber: "#d97706", amberLight: "#fffbeb", red: "#dc2626",
  redLight: "#fef2f2", shadow: "0 1px 3px rgba(0,0,0,.06)",
};

// Pod lifecycle phases in execution order
const POD_PHASES = [
  { key: "PATCHING_AFFINITY",    label: "New pod scheduled",         desc: "Node affinity patched — Kubernetes scheduler targets destination node" },
  { key: "WAITING_NEW_POD",      label: "New pod starting",          desc: "Waiting for replacement pod to reach Running state on target node" },
  { key: "SHIFTING_TRAFFIC",     label: "Traffic shifting",          desc: "Service selector updated — new pod begins accepting live requests" },
  { key: "OBSERVING_STABILITY",  label: "Stability window",          desc: "Observing new pod health for stability window before draining old pod" },
  { key: "EVICTING_OLD_POD",     label: "Old pod evicting",          desc: "New pod verified healthy — old pod gracefully evicted from source node" },
  { key: "COMPLETED",            label: "Migration complete",        desc: "Pod successfully migrated with zero downtime" },
];

// Node drain lifecycle
const NODE_PHASES = [
  { key: "CORDON_NODE",          label: "Cordoning node",            desc: "Node marked unschedulable — no new pods will be placed here" },
  { key: "DRAIN_NODE",           label: "Draining pods",             desc: "All pods gracefully evicted; requests completed before termination" },
  { key: "TERMINATE_NODE",       label: "Terminating node",          desc: "Node removed from cluster and EC2 instance terminated" },
];

const STATUS_COLORS = {
  QUEUED:      { color: T.textMuted,   bg: "#f9fafb" },
  PENDING:     { color: T.primary,     bg: T.primaryLight },
  PICKED_UP:   { color: T.primary,     bg: T.primaryLight },
  IN_PROGRESS: { color: T.amber,       bg: T.amberLight },
  VERIFYING:   { color: T.amber,       bg: T.amberLight },
  FAILED:      { color: T.red,         bg: T.redLight },
  COMPLETED:   { color: T.green,       bg: T.greenLight },
  DONE:        { color: T.green,       bg: T.greenLight },
};

const Badge = ({ children, color = T.primary, bg = T.primaryLight, style = {} }) => (
  <span style={{ display:"inline-flex", alignItems:"center", background:bg, color,
    fontSize:11, fontWeight:600, padding:"3px 8px", borderRadius:4,
    letterSpacing:".02em", whiteSpace:"nowrap", ...style }}>
    {children}
  </span>
);

const StatusBadge = ({ status }) => {
  const s = STATUS_COLORS[status] || STATUS_COLORS.QUEUED;
  return <Badge color={s.color} bg={s.bg}>{status}</Badge>;
};

const LiveIndicator = () => (
  <div style={{ display:"flex", alignItems:"center", gap:6,
    background:T.greenLight, padding:"4px 10px", borderRadius:12,
    border:`1px solid ${T.border}` }}>
    <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
    <span style={{ fontSize:11, fontWeight:700, color:T.green,
      textTransform:"uppercase", letterSpacing:"0.05em" }}>Live</span>
  </div>
);

const ProgressBar = ({ progress }) => (
  <div style={{ width:"100%", height:6, background:T.borderLight, borderRadius:3, overflow:"hidden" }}>
    <div style={{ height:"100%", width:`${Math.max(0,Math.min(100,progress))}%`,
      background:`linear-gradient(90deg,#6366f1,#4f46e5)`, borderRadius:3, transition:"width 0.5s ease" }} />
  </div>
);

// ── Detailed pod lifecycle stepper ──────────────────────────────────────
const PodLifecycleStepper = ({ phase, status, podName, fromNode, toNode }) => {
  const currentIdx = POD_PHASES.findIndex(p => p.key === phase);
  const isFailed = status === "FAILED";
  return (
    <div style={{ background:"#fafafa", border:`1px solid ${T.borderLight}`,
      borderRadius:8, padding:"12px 16px", marginTop:8 }}>
      <div style={{ fontSize:10, fontWeight:700, color:T.textFaint,
        textTransform:"uppercase", marginBottom:10, letterSpacing:"0.05em" }}>
        Pod Migration Lifecycle · <span style={{ color:T.primary, fontFamily:"monospace" }}>{podName}</span>
      </div>
      <div style={{ fontSize:10, color:T.textMuted, marginBottom:10 }}>
        <span style={{ fontFamily:"monospace" }}>{fromNode || "source"}</span>
        <span style={{ margin:"0 6px" }}>→</span>
        <span style={{ fontFamily:"monospace", color:T.primary }}>{toNode || "target"}</span>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
        {POD_PHASES.map((ph, idx) => {
          const isActive  = ph.key === phase && !isFailed;
          const isDone    = currentIdx > idx || (ph.key === "COMPLETED" && status === "COMPLETED");
          const isCurrent = ph.key === phase;
          const color     = isFailed && isCurrent ? T.red : isDone ? T.green : isActive ? T.primary : T.textFaint;
          const icon      = isFailed && isCurrent ? "✗" : isDone ? "✓" : isActive ? "◉" : "○";
          return (
            <div key={ph.key} style={{ display:"flex", alignItems:"flex-start", gap:10 }}>
              <div style={{ fontSize:13, fontWeight:700, color, minWidth:16, paddingTop:1 }}>{icon}</div>
              <div style={{ flex:1 }}>
                <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                  <span style={{ fontSize:12, fontWeight: isCurrent ? 700 : 500,
                    color: isCurrent ? color : isDone ? T.textMid : T.textFaint }}>
                    {ph.label}
                  </span>
                  {isActive && (
                    <span style={{ fontSize:10, color:T.primary, fontWeight:600 }}
                      className="animate-pulse">● In progress</span>
                  )}
                </div>
                {isCurrent && (
                  <div style={{ fontSize:11, color:T.textMuted, marginTop:1 }}>{ph.desc}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── Node drain stepper ──────────────────────────────────────────────────
const NodeDrainStepper = ({ relatedActions, nodeName }) => {
  if (!relatedActions || relatedActions.length === 0) return null;
  const byType = {};
  relatedActions.forEach(a => { byType[a.action_type] = a; });
  return (
    <div style={{ background:"#fafafa", border:`1px solid ${T.borderLight}`,
      borderRadius:8, padding:"12px 16px", marginTop:8 }}>
      <div style={{ fontSize:10, fontWeight:700, color:T.textFaint,
        textTransform:"uppercase", marginBottom:10, letterSpacing:"0.05em" }}>
        Node Drain Sequence · <span style={{ fontFamily:"monospace", color:T.textMid }}>{nodeName}</span>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
        {NODE_PHASES.map((ph, idx) => {
          const action = byType[ph.key];
          const st = action?.status || "QUEUED";
          const isDone = st === "COMPLETED";
          const isFail = st === "FAILED";
          const isActive = st === "PICKED_UP" || st === "PENDING";
          const color = isFail ? T.red : isDone ? T.green : isActive ? T.primary : T.textFaint;
          const icon  = isFail ? "✗" : isDone ? "✓" : isActive ? "◉" : "○";
          return (
            <div key={ph.key} style={{ display:"flex", gap:10 }}>
              <div style={{ fontSize:13, fontWeight:700, color, minWidth:16, paddingTop:1 }}>{icon}</div>
              <div style={{ flex:1 }}>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                  <span style={{ fontSize:12, fontWeight: isActive ? 700 : 500,
                    color: isFail ? T.red : isActive || isDone ? T.textMid : T.textFaint }}>
                    {ph.label}
                  </span>
                  {action && <StatusBadge status={st} />}
                </div>
                {(isActive || isFail) && (
                  <div style={{ fontSize:11, color: isFail ? T.red : T.textMuted, marginTop:2 }}>
                    {isFail ? (action?.error_message || ph.desc) : ph.desc}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── Custom hook ─────────────────────────────────────────────────────────
const useActiveActions = (clusterId) => {
  const [data, setData] = useState({
    agent_actions:[], rebalancing_actions:[], cluster_state:{active_count:0,batch_limit:10,mutex:false}
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!clusterId) return;
    let alive = true;
    const fetch = async () => {
      try {
        const res = await api.get('/api/v1/actions/active', { params:{ cluster_id:clusterId } });
        if (alive) { setData(res.data); setError(null); setLoading(false); }
      } catch(e) {
        if (alive) { setError(e.message); setLoading(false); }
      }
    };
    fetch();
    const iv = setInterval(fetch, 5000);
    return () => { alive=false; clearInterval(iv); };
  }, [clusterId]);

  return { data, loading, error };
};

// ── Main Component ──────────────────────────────────────────────────────
const ActiveActions = () => {
  const { clusters, selectedId, setSelectedId } = useClusters();
  const [clusterId, setClusterId] = useState(selectedId || clusters[0]?.id || '');
  const [filter, setFilter] = useState('All');
  const [expanded, setExpanded] = useState({});

  useEffect(() => { if (selectedId && selectedId !== clusterId) setClusterId(selectedId); }, [selectedId]);

  const { data, loading, error } = useActiveActions(clusterId);

  const actions       = data.agent_actions || [];
  const rebalActions  = data.rebalancing_actions || [];
  const scheduled     = data.scheduled_actions || [];
  const state         = data.cluster_state || {};

  const nodeActionTypes = ["CORDON_NODE","DRAIN_NODE","TERMINATE_NODE"];
  const nodeActions   = actions.filter(a => nodeActionTypes.includes(a.action_type));
  const evictActions  = actions.filter(a => a.action_type === "EVICT_POD" || a.action_type === "PATCH_AFFINITY");
  const failedActions = actions.filter(a => a.status === "FAILED");
  const activeCount   = actions.filter(a => ["PENDING","PICKED_UP","IN_PROGRESS"].includes(a.status)).length;

  // Group node actions by rebalancing_action_id
  const nodeGroups = rebalActions.map(ra => ({
    ...ra,
    relatedActions: nodeActions.filter(a => a.payload?.rebalancing_action_id === ra.id),
  }));

  const toggle = (id) => setExpanded(e => ({ ...e, [id]: !e[id] }));

  const Card = ({ id, title, badge, borderColor, children, defaultOpen=true }) => {
    const open = expanded[id] ?? defaultOpen;
    return (
      <div style={{ background:T.surface, border:`1px solid ${borderColor||T.border}`,
        borderRadius:12, overflow:"hidden", marginBottom:12,
        boxShadow:T.shadow }}>
        <div onClick={() => toggle(id)} style={{ padding:"14px 20px", cursor:"pointer",
          display:"flex", justifyContent:"space-between", alignItems:"center",
          background: open ? T.bg : T.surface, borderBottom: open ? `1px solid ${T.borderLight}` : "none" }}>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <span style={{ fontSize:15, fontWeight:700, color:T.text }}>{title}</span>
            {badge}
          </div>
          {open ? <FiChevronUp size={16} color={T.textFaint}/> : <FiChevronDown size={16} color={T.textFaint}/>}
        </div>
        {open && <div style={{ padding:20 }}>{children}</div>}
      </div>
    );
  };

  return (
    <div className="min-h-full bg-gray-50 p-6">
      <div style={{ maxWidth:1300, margin:"0 auto" }}>

        {/* Header */}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:24 }}>
          <div>
            <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:6 }}>
              <div style={{ padding:8, background:T.primaryLight, borderRadius:8 }}>
                <FiActivity color={T.primary} size={18}/>
              </div>
              <h1 style={{ fontSize:22, fontWeight:800, color:T.text, margin:0 }}>Live Execution Inspector</h1>
            </div>
            <p style={{ fontSize:13, color:T.textMuted, margin:0 }}>
              Real-time pod lifecycle tracking — new pod created → ready → traffic shifted → old pod drained → node terminated
            </p>
            <select value={clusterId}
              onChange={e => { setClusterId(e.target.value); setSelectedId(e.target.value); }}
              style={{ marginTop:12, padding:"8px 12px", borderRadius:8, border:`1px solid ${T.border}`,
                fontSize:14, fontWeight:500, color:T.text, minWidth:240, outline:"none" }}>
              {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div style={{ display:"flex", flexDirection:"column", alignItems:"flex-end", gap:12 }}>
            <LiveIndicator/>
            <div style={{ display:"flex", background:T.borderLight, padding:4, borderRadius:8 }}>
              {["All","Node","Pod","Attention"].map(f => (
                <button key={f} onClick={() => setFilter(f)} style={{
                  padding:"6px 14px", borderRadius:6, fontSize:13, fontWeight:600,
                  border:"none", cursor:"pointer",
                  background: filter===f ? T.surface : "transparent",
                  color: filter===f ? T.text : T.textMuted,
                  boxShadow: filter===f ? T.shadow : "none", transition:"all 0.2s" }}>
                  {f}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Stats row */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:14, marginBottom:24 }}>
          {[
            { label:"Active Actions", value:activeCount, color:T.primary },
            { label:"Node Operations", value:nodeGroups.length, color:T.textMid },
            { label:"Pod Migrations", value:evictActions.length, color:T.amber },
            { label:"Failures", value:failedActions.length, color:failedActions.length>0?T.red:T.textMid },
          ].map(s => (
            <div key={s.label} style={{ background:T.surface, border:`1px solid ${T.border}`,
              borderRadius:10, padding:16, boxShadow:T.shadow }}>
              <div style={{ fontSize:11, fontWeight:600, color:T.textMuted, textTransform:"uppercase", marginBottom:4 }}>{s.label}</div>
              <div style={{ fontSize:26, fontWeight:800, color:s.color }}>{s.value}</div>
            </div>
          ))}
        </div>

        {error && (
          <div style={{ padding:12, background:T.redLight, border:`1px solid ${T.red}`,
            borderRadius:8, color:T.red, fontSize:13, display:"flex", gap:8, marginBottom:16 }}>
            <FiAlertTriangle/> {error}
          </div>
        )}

        {loading && <div style={{ textAlign:"center", padding:48, color:T.textMuted }}>Connecting to execution stream...</div>}

        {!loading && (
          <div>

            {/* NODE OPERATIONS */}
            {(filter==="All"||filter==="Node") && (nodeGroups.length>0||nodeActions.length>0) && (
              <Card id="nodes" title="Node Operations"
                badge={<Badge>{nodeGroups.length>0?`${nodeGroups.length} nodes`:`${nodeActions.length} actions`}</Badge>}>
                {nodeGroups.length===0 && nodeActions.map(a => (
                  <div key={a.id} style={{ padding:"12px 0", borderBottom:`1px solid ${T.borderLight}` }}>
                    <div style={{ display:"flex", justifyContent:"space-between" }}>
                      <span style={{ fontWeight:600, fontSize:13 }}>{a.payload?.node_name||"Node"}</span>
                      <StatusBadge status={a.status}/>
                    </div>
                    <div style={{ fontSize:11, color:T.textMuted, marginTop:2 }}>{a.action_type}</div>
                    {a.error_message && <div style={{ fontSize:11, color:T.red, marginTop:4 }}>{a.error_message}</div>}
                  </div>
                ))}
                {nodeGroups.map(ng => {
                  const STATE_PROGRESS = {
                    pending:10, waiting_agent:20, in_progress:55,
                    SOURCE_CORDONED:35, SOURCE_DRAINED:65,
                    REPLACEMENT_READY:80, SOURCE_TERMINATING:90,
                    completed:100, failed:100,
                  };
                  const prog = STATE_PROGRESS[ng.current_state||ng.status] ?? 33;
                  const isFail = ng.status==="failed";
                  const isDone = ng.status==="completed";
                  return (
                    <div key={ng.id} style={{ border:`1px solid ${isFail?T.red:isDone?T.green:T.border}`,
                      borderRadius:10, padding:16, marginBottom:12,
                      background: isFail?T.redLight:isDone?"#f0fdf4":T.surface }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:10 }}>
                        <div>
                          <div style={{ fontSize:14, fontWeight:700, color:T.text }}>
                            {ng.source_node_name||ng.node_name||ng.source_pool||"Node"}
                          </div>
                          <div style={{ fontSize:12, color:T.textMuted, marginTop:2 }}>
                            {ng.engine_source==="consolidation"?"→ Consolidating onto existing nodes":`→ ${ng.target_pool||"spot"}`}
                          </div>
                        </div>
                        <StatusBadge status={(ng.status||"pending").toUpperCase()}/>
                      </div>
                      <ProgressBar progress={prog}/>
                      <NodeDrainStepper relatedActions={ng.relatedActions} nodeName={ng.source_node_name||ng.node_name}/>
                      {isFail && ng.error_message && (
                        <div style={{ fontSize:11, color:T.red, marginTop:8, padding:"6px 10px",
                          background:"#fff", border:`1px solid ${T.red}`, borderRadius:6 }}>
                          {ng.error_message}
                        </div>
                      )}
                      <div style={{ display:"flex", gap:16, marginTop:10, fontSize:11, color:T.textMuted }}>
                        <span>Duration: <strong>{ng.started_at?`${Math.round((Date.now()-new Date(ng.started_at))/1000)}s`:"—"}</strong></span>
                        {ng.pods_migrated!=null && <span>Pods migrated: <strong style={{color:T.green}}>{ng.pods_migrated}</strong></span>}
                      </div>
                    </div>
                  );
                })}
              </Card>
            )}

            {/* POD MIGRATIONS with lifecycle stepper */}
            {(filter==="All"||filter==="Pod") && evictActions.length>0 && (
              <Card id="pods" title="Pod Migrations"
                badge={<Badge color={T.amber} bg={T.amberLight}>{evictActions.length} pods</Badge>}>
                <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                  {evictActions.map(a => {
                    const ph = a.phase || (a.status==="COMPLETED"?"COMPLETED":a.status==="FAILED"?"EVICTING_OLD_POD":"WAITING_NEW_POD");
                    return (
                      <div key={a.id} style={{ border:`1px solid ${T.borderLight}`, borderRadius:10,
                        padding:14, background:T.surface }}>
                        <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
                          <div>
                            <span style={{ fontSize:13, fontWeight:700, color:T.text }}>
                              {a.payload?.pod_name||"Pod migration"}
                            </span>
                            <span style={{ fontSize:11, color:T.textMuted, marginLeft:8 }}>{a.action_type}</span>
                          </div>
                          <StatusBadge status={a.status}/>
                        </div>
                        <PodLifecycleStepper
                          phase={ph}
                          status={a.status}
                          podName={a.payload?.pod_name||""}
                          fromNode={a.payload?.node_name||a.payload?.from_node}
                          toNode={a.payload?.target_node||a.payload?.to_node}
                        />
                        {a.error_message && (
                          <div style={{ fontSize:11, color:T.red, marginTop:8,
                            padding:"4px 8px", background:T.redLight, borderRadius:6 }}>
                            {a.error_message}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </Card>
            )}

            {/* ATTENTION REQUIRED */}
            {(filter==="All"||filter==="Attention") && failedActions.length>0 && (
              <Card id="attention" title="Attention Required"
                borderColor={T.amber}
                badge={<Badge color={T.amber} bg={T.amberLight}>{failedActions.length} items</Badge>}>
                <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                  {failedActions.map(a => (
                    <div key={a.id} style={{ display:"flex", gap:12, padding:12,
                      background:T.redLight, border:`1px solid ${T.red}`, borderRadius:8 }}>
                      <FiAlertCircle color={T.red} size={18} style={{ flexShrink:0, marginTop:2 }}/>
                      <div style={{ flex:1 }}>
                        <div style={{ fontSize:13, fontWeight:600, color:T.red }}>{a.action_type}</div>
                        <div style={{ fontSize:11, color:T.red, opacity:0.8, marginTop:2 }}>
                          {a.error_message||"Timeout or validation error during execution"}
                        </div>
                        {a.payload?.node_name && (
                          <div style={{ fontSize:11, color:T.textMuted, fontFamily:"monospace", marginTop:4 }}>
                            {a.payload.node_name}
                          </div>
                        )}
                      </div>
                      <StatusBadge status={a.status}/>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* SCHEDULED */}
            {scheduled.length>0 && (filter==="All") && (
              <Card id="scheduled" title="Scheduled Rightsizing" defaultOpen={false}
                badge={<Badge color={T.amber} bg={T.amberLight}>{scheduled.length} pending</Badge>}>
                <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:14 }}>
                  {scheduled.map(s => (
                    <div key={s.id} style={{ border:`1px solid ${T.border}`, borderRadius:8, padding:12 }}>
                      <div style={{ fontWeight:600, fontSize:13, marginBottom:4 }}>
                        {s.payload?.workload_name||"Rightsizing"}
                      </div>
                      <div style={{ fontSize:11, color:T.textMuted }}>
                        {s.payload?.current_resources} → {s.payload?.target_resources}
                      </div>
                      {s.payload?.estimated_savings>0 && (
                        <div style={{ fontSize:11, color:T.green, fontWeight:600, marginTop:4 }}>
                          Est savings: ${s.payload.estimated_savings}/mo
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* Empty state */}
            {filter==="All" && nodeGroups.length===0 && nodeActions.length===0
              && evictActions.length===0 && failedActions.length===0 && scheduled.length===0 && (
              <div style={{ padding:48, textAlign:"center", background:T.surface,
                border:`1px dashed ${T.border}`, borderRadius:12 }}>
                <FiCheckCircle size={32} style={{ margin:"0 auto 16px", color:T.green }}/>
                <h3 style={{ fontSize:16, fontWeight:600, color:T.text, margin:"0 0 4px" }}>System Stable</h3>
                <p style={{ fontSize:13, color:T.textMuted, margin:0 }}>No active migrations or drain operations.</p>
              </div>
            )}

          </div>
        )}
      </div>
    </div>
  );
};

export default ActiveActions;
