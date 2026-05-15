import React, { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { clusterAPI, karpenterAPI, ascpaiAPI, kedaAPI } from '../../../services/api';
import { useClusterStore, useHeaderStore } from '../../../store/useStore';
import { formatCurrency } from '../../../utils/formatters';
import toast from 'react-hot-toast';
import ClusterDetails from './ClusterDetails';

// ─── PALETTE ─────────────────────────────────────────────────────────────────
// Philosophy: near-monochrome UI chrome. Color ONLY for data/status indicators.
const C = {
  // Backgrounds & surfaces
  bg: "#f5f6f8",
  surface: "#ffffff",
  surfaceHover: "#fafafa",
  border: "#e4e6ea",
  borderHover: "#c8cdd6",

  // Text — 3-level scale, no colored text in prose/labels
  text: "#111318",
  muted: "#5a6272",
  subtle: "#98a1b0",

  // Single accent for interactive elements only
  accent: "#2563eb",
  accentLight: "#eff6ff",

  // Status indicators — dots, bars, badges ONLY (not font color)
  green: "#16a34a", greenBg: "#f0fdf4", greenBorder: "#bbf7d0",
  amber: "#b45309", amberBg: "#fffbeb", amberBorder: "#fde68a",
  red: "#dc2626", redBg: "#fef2f2", redBorder: "#fecaca",
  purple: "#6d28d9", purpleBg: "#f5f3ff", purpleBorder: "#ddd6fe",
  teal: "#0f766e", tealBg: "#f0fdfa", tealBorder: "#99f6e4",

  // Aliases
  blue: "#2563eb", blueLight: "#eff6ff",
  greenLight: "#f0fdf4", amberLight: "#fffbeb", redLight: "#fef2f2",
  purpleLight: "#f5f3ff", indigo: "#4f46e5",

  spotColor: "#16a34a", spotBg: "#f0fdf4",
  fallbackColor: "#b45309", fallbackBg: "#fffbeb",
  onDemandColor: "#2563eb", onDemandBg: "#eff6ff",
};

// ─── HELPERS ─────────────────────────────────────────────────────────────────
const utilColor = (pct) => {
  if (pct < 60) return C.green;
  if (pct < 85) return C.amber;
  return C.fallbackColor;
};

const utilBg = (pct) => {
  if (pct >= 85) return C.redBg;
  if (pct >= 65) return C.amberBg;
  if (pct >= 30) return C.greenBg;
  return C.accentLight;
};

const typeColor = {
  spot: C.spotColor,
  fallback: C.fallbackColor,
  "on-demand": C.onDemandColor,
  "warm-spare": "#7c3aed",
};

const typeBg = {
  spot: C.spotBg,
  fallback: C.fallbackBg,
  "on-demand": C.onDemandBg,
  "warm-spare": "#f5f3ff",
};

const statusConfig = {
  healthy: { color: C.green, bg: C.greenBg, border: C.greenBorder, label: "Healthy", dot: C.green },
  warning: { color: C.amber, bg: C.amberBg, border: C.amberBorder, label: "Warning", dot: C.amber },
  degraded: { color: "#dc2626", bg: "#fef2f2", border: "#fecaca", label: "Degraded", dot: "#dc2626" },
  "no-agent": { color: C.subtle, bg: "#f3f4f6", border: C.border, label: "No Agent", dot: C.subtle },
};

// ─── MINI COMPONENTS ─────────────────────────────────────────────────────────


const MiniBar = ({ used, total, color, pct, allocatedPct }) => {
  const usagePct = pct !== undefined ? Math.round(pct) : (total > 0 ? Math.round((used / total) * 100) : 0);
  const allocPct = allocatedPct !== undefined ? Math.round(allocatedPct) : 0;
  // When allocation data exists, show it as primary (matches AWS EKS console)
  const primaryPct = allocPct > 0 ? allocPct : usagePct;
  const primaryColor = allocPct > 0 ? C.amber : color;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ flex: 1, height: 5, background: "#f0f0f0", borderRadius: 3, position: "relative" }}>
        {/* Allocated bar (amber) — shows pod request allocation */}
        {allocPct > 0 && (
          <div style={{ position: "absolute", width: `${Math.min(allocPct, 100)}%`, height: 5, background: C.amber + "88", borderRadius: 3, transition: "width 0.4s" }} />
        )}
        {/* Actual usage bar — thin line inside allocation bar */}
        <div style={{ position: "relative", width: `${Math.min(usagePct, 100)}%`, height: 5, background: color, borderRadius: 3, transition: "width 0.4s" }} />
      </div>
      <span style={{ fontSize: 10, color: C.muted, width: 28, textAlign: "right", flexShrink: 0 }}>
        {primaryPct}%
      </span>
    </div>
  );
};

const MetricBox = ({ label, value, sub, icon, style = {} }) => (
  <div style={{
    background: C.surface, border: `1px solid ${C.border}`,
    borderRadius: 10, padding: "12px 14px", ...style
  }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div style={{ fontSize: 11, color: C.muted, marginBottom: 4, fontWeight: 500 }}>{label}</div>
      {icon && <span style={{ fontSize: 13, opacity: 0.5 }}>{icon}</span>}
    </div>
    <div style={{ fontSize: 19, fontWeight: 700, letterSpacing: "-0.4px", color: C.text }}>{value}</div>
    {sub && <div style={{ fontSize: 11, color: C.subtle, marginTop: 3 }}>{sub}</div>}
  </div>
);

const ClusterListItem = ({ cluster, selected, onClick }) => {
  const sc = statusConfig[cluster.status];
  return (
    <div
      onClick={onClick}
      style={{
        padding: "12px 14px",
        borderRadius: 10,
        border: `1.5px solid ${selected ? C.accent : C.border}`,
        background: selected ? C.accentLight : C.surface,
        cursor: "pointer",
        transition: "all 0.15s",
        marginBottom: 6,
      }}
      onMouseEnter={e => { if (!selected) { e.currentTarget.style.borderColor = C.borderHover; e.currentTarget.style.background = C.surfaceHover; } }}
      onMouseLeave={e => { if (!selected) { e.currentTarget.style.borderColor = C.border; e.currentTarget.style.background = C.surface; } }}
    >
      {/* Row 1: name + status dot */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <div style={{
            width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
            background: sc.dot,
          }} />
          <span style={{
            fontWeight: 600, fontSize: 12.5,
            color: selected ? C.accent : C.text,
            letterSpacing: "-0.2px", maxWidth: 130,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>{cluster.name}</span>
          {cluster.health_score && (
            <span style={{
              fontSize: 9, fontWeight: 700, lineHeight: 1,
              padding: "2px 5px", borderRadius: 4, flexShrink: 0,
              background: cluster.health_score === "A" ? "#dcfce7"
                        : cluster.health_score === "B" ? "#dbeafe"
                        : cluster.health_score === "C" ? "#fef9c3"
                        : "#fee2e2",
              color:      cluster.health_score === "A" ? "#166534"
                        : cluster.health_score === "B" ? "#1e40af"
                        : cluster.health_score === "C" ? "#854d0e"
                        : "#991b1b",
            }}>{cluster.health_score}</span>
          )}
        </div>
        {/* Status as neutral pill, color only on the dot inside */}
        <div style={{
          display: "flex", alignItems: "center", gap: 4,
          padding: "2px 7px", borderRadius: 5,
          background: "#f0f1f3", border: `1px solid ${C.border}`,
          fontSize: 10, fontWeight: 500, color: C.muted,
        }}>
          <div style={{ width: 5, height: 5, borderRadius: "50%", background: sc.dot }} />
          {sc.label}
        </div>
      </div>

      {/* Row 2: region chip + quick stats */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
        <span style={{ fontSize: 10, color: C.subtle, background: "#f0f1f3", padding: "2px 6px", borderRadius: 4 }}>
          {cluster.region}
        </span>
        <span style={{ fontSize: 10, color: C.subtle }}>{cluster._nodeCountPending ? '…' : cluster.nodes.total} nodes</span>
        <span style={{ fontSize: 10, color: cluster.agentInstalled ? C.green : C.subtle, fontWeight: cluster.agentInstalled ? 600 : 400 }}>
          {cluster.agentInstalled ? "● Agent" : "○ No Agent"}
        </span>
      </div>

      {/* Row 3: mini bars */}
      {cluster.agentInstalled && (
        <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 6 }}>
          {[
            { key: "CPU", used: cluster.cpu.used, total: cluster.cpu.total, requested: cluster.cpu.requested },
            { key: "MEM", used: cluster.memory.used, total: cluster.memory.total, requested: cluster.memory.requested },
          ].map(r => {
            const allocPct = r.total > 0 && r.requested > 0 ? Math.round((r.requested / r.total) * 100) : 0;
            return (
              <div key={r.key} style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span style={{ fontSize: 9, color: C.subtle, width: 26, textTransform: "uppercase", letterSpacing: "0.04em" }}>{r.key}</span>
                <div style={{ flex: 1 }}>
                  <MiniBar used={r.used} total={r.total} color={utilColor(Math.round(r.used / r.total * 100))} allocatedPct={allocPct} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Row 4: cost */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 11, color: C.muted, fontWeight: 500 }}>${cluster.cost.monthly.toLocaleString()}/mo</span>
        {cluster.cost.savings > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{ width: 5, height: 5, borderRadius: "50%", background: C.green }} />
            <span style={{ fontSize: 10, color: C.muted }}>
              ${cluster.cost.savings.toLocaleString()} saved
            </span>
          </div>
        )}
      </div>
    </div>
  );
};

const NoAgentDetail = ({ cluster, onClose }) => {
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDeleteCluster = () => {
    setDeleting(true);
    clusterAPI.deleteCluster(cluster.id)
      .then(() => {
        toast.success(`Cluster "${cluster.name}" removed.`);
        setDeleting(false);
        setShowDeleteModal(false);
        if (onClose) onClose();
        window.dispatchEvent(new Event('refresh-clusters'));
      })
      .catch((err) => {
        toast.error(`Failed: ${err.response?.data?.detail || err.message}`);
        setDeleting(false);
      });
  };

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 40, textAlign: "center" }}>
      <div style={{ fontSize: 40, marginBottom: 16, opacity: 0.25 }}>⬡</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: C.text, marginBottom: 6 }}>{cluster.name}</div>
      <div style={{ fontSize: 13, color: C.muted, maxWidth: 340, lineHeight: 1.7, marginBottom: 24 }}>
        This cluster doesn't have the Balancekube agent installed. Install it to unlock real-time metrics, Balancekube.ai ML optimization, and savings tracking.
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            toast.loading(`Installing agent on ${cluster.name}...`, { id: 'inject' });
            clusterAPI.autoInstallAgent(cluster.id)
              .then(() => {
                toast.success(`Agent installation queued for ${cluster.name}. It will be active in ~30s.`, { id: 'inject', duration: 5000 });
                setTimeout(() => window.dispatchEvent(new Event('refresh-clusters')), 8000);
              })
              .catch((error) => {
                toast.error('Failed to install agent: ' + (error.response?.data?.detail || error.message), { id: 'inject' });
              });
          }}
          style={{
            padding: "9px 20px", borderRadius: 10,
            background: "linear-gradient(135deg, #2563eb, #4f46e5)",
            border: "none", color: "#fff", fontSize: 13, fontWeight: 600,
            cursor: "pointer", fontFamily: "inherit",
            boxShadow: "0 2px 10px rgba(37,99,235,0.3)",
            position: "relative", zIndex: 9999,
          }}
          type="button"
        >Install Agent</button>
        <button style={{
          padding: "9px 20px", borderRadius: 10,
          border: `1px solid ${C.border}`, background: C.surface,
          color: C.muted, fontSize: 13, cursor: "pointer", fontFamily: "inherit",
        }}>View Docs</button>
        <button
          onClick={() => setShowDeleteModal(true)}
          style={{
            padding: "9px 20px", borderRadius: 10,
            background: "#fef2f2", border: "1px solid #fecaca",
            color: "#dc2626", fontSize: 13, fontWeight: 600,
            cursor: "pointer", fontFamily: "inherit",
          }}
        >Remove Cluster</button>
      </div>
      <div style={{ marginTop: 32, display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, width: "100%", maxWidth: 640 }}>
        <MetricBox label="Region" value={cluster.region} />
        <MetricBox label="K8s Version" value={cluster.k8sVersion} />
        <MetricBox label="Total Nodes" value={cluster._nodeCountPending ? '…' : cluster.nodes.total} />
        <MetricBox label="Est. Cost" value={`$${cluster.cost.monthly}/mo`} sub="on-demand pricing" />
        <MetricBox label="Est. Savings" value={`$${cluster.cost.potential || 0}/mo`} sub="potential" />
      </div>

      {showDeleteModal && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999,
        }}>
          <div style={{
            background: "#fff", borderRadius: 14, padding: "28px 32px",
            maxWidth: 420, width: "100%", margin: "0 16px", boxShadow: "0 20px 60px rgba(0,0,0,0.25)",
          }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: "#dc2626", marginBottom: 10 }}>Remove Cluster?</div>
            <div style={{ fontSize: 13, color: "#374151", marginBottom: 16, lineHeight: 1.7 }}>
              Permanently delete <strong>{cluster.name}</strong> and all associated data? This cannot be undone.
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
                style={{ padding: "8px 18px", borderRadius: 8, border: "1px solid #d1d5db", background: "#fff", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}
              >Cancel</button>
              <button
                onClick={handleDeleteCluster}
                disabled={deleting}
                style={{ padding: "8px 18px", borderRadius: 8, border: "none", background: "#dc2626", color: "#fff", fontSize: 13, fontWeight: 600, cursor: deleting ? "not-allowed" : "pointer", fontFamily: "inherit", opacity: deleting ? 0.7 : 1 }}
              >{deleting ? "Removing..." : "Remove Cluster"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── MAIN COMPONENT ───────────────────────────────────────────────────────────
export default function ClustersPage() {
  const { clusters, setClusters, setLoading, loading } = useClusterStore();
  const headerStore = useHeaderStore();
  // Persist selected cluster across page refreshes (survives F5 but clears on tab close)
  const [selected, setSelected] = useState(() => sessionStorage.getItem('clusters_selected_id') || null);
  const setSelectedAndPersist = React.useCallback((id) => {
    if (id) sessionStorage.setItem('clusters_selected_id', id);
    else sessionStorage.removeItem('clusters_selected_id');
    setSelected(id);
  }, []);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [karpenterModeFilter, setKarpenterModeFilter] = useState("ALL");

  const [refreshing, setRefreshing] = useState(false);
  const [nodeDetails, setNodeDetails] = useState({});
  // RC4 fix: track clusters whose first nodeDetails fetch is in-flight
  // so we can show a loading indicator instead of stale summary counts.
  const [nodeDetailsPending, setNodeDetailsPending] = useState(new Set());
  const [rightsizingData, setRightsizingData] = useState({});

  // Ref so the node-details interval can access the latest mappedClusters
  // without being in the effect dependency array (avoids infinite fetch loop).
  const mappedClustersRef = useRef([]);
  // Track whether first fetch has completed — avoids reading `clusters` state
  // inside fetchData (which would recreate the callback on every poll and cause
  // an infinite re-render loop via the useEffect([fetchData]) below).
  const hasInitialDataRef = useRef(false);

  const fetchData = useCallback(async () => {
    // Only show loading spinner on initial empty load — background polls
    // must NOT blank out the existing cluster list.
    if (!hasInitialDataRef.current) setLoading(true);
    try {
      const clusterRes = await clusterAPI.list({});
      const newClusters = clusterRes.data.clusters || [];
      hasInitialDataRef.current = true;
      setClusters(newClusters);
      // Clear selected panel if the selected cluster was deleted
      setSelected(prev => {
        if (prev && !newClusters.find(c => c.id === prev)) {
          sessionStorage.removeItem('clusters_selected_id');
          return null;
        }
        return prev;
      });
    } catch (error) {
      toast.error('Failed to load clusters');
    } finally {
      setLoading(false);
    }
  }, [setClusters, setLoading]);

  const handleRefresh = useCallback(() => {
    // Don't clear nodeDetails — keep showing stale data while new data loads
    // to avoid blanking the detail panel on every refresh.
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    fetchData();
    window.addEventListener('refresh-clusters', handleRefresh);
    const interval = setInterval(fetchData, 30000); // Keep agent heartbeat + cluster state fresh
    return () => {
      window.removeEventListener('refresh-clusters', handleRefresh);
      clearInterval(interval);
    };
  }, [fetchData, handleRefresh]);

  // Fetch rightsizing recommendations for agent-connected clusters only (background, non-blocking)
  // Dep: cluster IDs string — avoids re-firing on every clusters array reference change (30s poll)
  const _agentClusterIds = useMemo(
    () => clusters.filter(c => c.agent_installed === 'Y' || c.agent_installed === true).map(c => c.id).sort().join(','),
    [clusters]
  );
  useEffect(() => {
    if (!_agentClusterIds) return;
    const agentClusters = clusters.filter(c => c.agent_installed === 'Y' || c.agent_installed === true);
    Promise.allSettled(
      agentClusters.map(c =>
        karpenterAPI.getRecommendations(c.id)
          .then(res => ({ id: c.id, recs: res.data?.recommendations || [] }))
          .catch(() => ({ id: c.id, recs: [] }))
      )
    ).then(results => {
      const rd = {};
      results.forEach(r => {
        if (r.status === 'fulfilled') {
          const recs = r.value.recs;
          rd[r.value.id] = {
            overProvisioned: recs.length,
            savingsPotential: Math.round(recs.reduce((s, rec) => s + (rec.potential_savings || 0), 0)),
          };
        }
      });
      setRightsizingData(rd);
    });
  }, [_agentClusterIds]); // eslint-disable-line react-hooks/exhaustive-deps

  // Map API clusters to UI expected format
  const mappedClusters = useMemo(() => {
    return clusters.map(c => {
      // Determine precise health status
      // Check agent_installed field directly (Y/N string or boolean)
      let agentInstalled = (c.agent_installed === 'Y' || c.agent_installed === true);
      let agentHealthy = false;
      let mappedStatus = "no-agent";

      // Backend DEGRADED status = agent installed but cluster no longer found in AWS
      if (c.status === 'DEGRADED') {
        mappedStatus = "degraded";
        agentInstalled = true;
        agentHealthy = false;
      } else if (agentInstalled) {
        // Three-tier heartbeat freshness check:
        //   < 90s  → healthy (agent sends every 30s; allow 2 missed beats)
        //   90s–5m → warning (degraded / slow heartbeat)
        //   > 5m   → offline (treat as no-agent; backend will auto-reset)
        if (c.last_heartbeat) {
          const lastHB = new Date(c.last_heartbeat);
          const now = Date.now();
          const ageMs = now - lastHB.getTime();
          if (ageMs < 90 * 1000) {
            agentHealthy = true;
            mappedStatus = "healthy";
          } else if (ageMs < 5 * 60 * 1000) {
            agentHealthy = false;
            mappedStatus = "warning";
          } else {
            // >5 min with no heartbeat → agent is offline but still installed
            agentHealthy = false;
            mappedStatus = "warning";
          }
        } else {
          mappedStatus = "warning";
        }
      } else if (c.status === 'DISCOVERED') {
        mappedStatus = "no-agent";
      }

      const totalNodes = c.node_count || 0;
      const spotNodes = c.spot_count || 0;
      // Use the explicit on_demand_node_count from the API when available;
      // fall back to subtraction clamped to 0 to prevent negative display
      // when stale fallback values are inconsistent (e.g., node_count=0, spot_count=1).
      const onDemandNodes = (c.on_demand_node_count != null)
        ? c.on_demand_node_count
        : Math.max(0, totalNodes - spotNodes);
      // nodeListTotals will override these with accurate running counts once detailed data loads

      let lastSeenText = "Never";
      if (c.last_heartbeat) {
        const diffMs = Date.now() - new Date(c.last_heartbeat).getTime();
        const diffMins = Math.floor(diffMs / 60000);
        lastSeenText = diffMins < 1 ? "Just now" : `${diffMins} min ago`;
      }

      // Get node details if available
      const clusterNodeDetails = nodeDetails[c.id];
      // RC4 fix: is this cluster's first node-details fetch still in flight?
      const _nodeCountPending = nodeDetailsPending.has(c.id);
      let nodeList = [];

      if (clusterNodeDetails && clusterNodeDetails.nodes) {
        // Transform detailed nodes to NodeTreemap format
        nodeList = clusterNodeDetails.nodes.map((node, idx) => {
          // Calculate overall utilization (use the max of CPU and memory bottlenecks)
          const util = Math.round(Math.max(node.cpu_utilization_pct, node.memory_utilization_pct));
          // Determine node type — default to on-demand when lifecycle is unknown/null
          // (RC1 fix: previously defaulted to "spot", which caused OD nodes to appear as Spot
          // whenever the backend returned null, "none", or any non-standard lifecycle value)
          let nodeType = "on-demand";
          if (node._isWarmSpare) {
            nodeType = "warm-spare";
          } else if (node.lifecycle === "spot") {
            nodeType = "spot";
          } else if (node.lifecycle === "on-demand" || node.lifecycle === "on_demand") {
            nodeType = "on-demand";
          }
          // null / undefined / "none" / unknown → stays "on-demand" (conservative)

          // Calculate age
          const ageText = "N/A"; // Could calculate from node timestamp if available

          const cpuCores = node.cpu_capacity_cores || 2;
          const memGib = node.memory_capacity_gb || 16;
          return {
            id: node.instance_id || `node-${idx}`,
            name: node.node_name || node.instance_id || `node-${idx}`,
            instanceType: node.instance_type || "unknown",
            type: nodeType,
            utilization: util,
            cpuPct: node.cpu_utilization_pct,
            memPct: node.memory_utilization_pct,
            cpuReqPct: node.cpu_request_pct || 0,
            memReqPct: node.memory_request_pct || 0,
            classification: node.classification || 'UNKNOWN',
            cpu: {
              used: Math.round((node.cpu_utilization_pct / 100) * cpuCores * 100) / 100,
              total: cpuCores,
              requested: node.total_cpu_request_millicores
                ? Math.round(node.total_cpu_request_millicores / 100) / 10
                : 0,
            },
            memory: {
              used: Math.round((node.memory_utilization_pct / 100) * memGib * 100) / 100,
              total: memGib,
              requested: node.total_memory_request_mb
                ? Math.round(node.total_memory_request_mb / 1024 * 100) / 100
                : 0,
            },
            pods: node.pod_count || 0,
            maxPods: 110, // Default K8s limit
            ready: node.status === 'ready' || true,
            age: ageText,
          };
        });
      }

      return {
        id: c.id,
        cluster_uid: c.cluster_uid || null,
        name: c.name,
        region: c.region || "us-east-1",
        provider: c.provider || "AWS",
        agentInstalled,
        agentVersion: c.agent_version || "v1.1.2",
        agentHealthy,
        lastSeen: c.last_heartbeat ? lastSeenText : "Unknown",
        status: mappedStatus,
        // If detailed node data is available, use it as the source of truth for counts.
        // The summary API includes terminated instances in node_count; the detailed API
        // only returns running instances which is what we want to display.
        ...(nodeList.length > 0 ? {
          spotRatio: Math.round((nodeList.filter(n => n.type === 'spot').length / nodeList.length) * 100),
          nodes: {
            total: nodeList.length,
            spot: nodeList.filter(n => n.type === 'spot').length,
            fallback: nodeList.filter(n => n.type === 'fallback').length,
            onDemand: nodeList.filter(n => n.type === 'on-demand').length,
          },
          // RC4 fix: real data loaded — no pending flag needed
          _nodeCountPending: false,
        } : _nodeCountPending ? {
          // RC4 fix: first fetch in flight — don't show stale summary counts.
          // Render null so the UI can display a loading indicator instead.
          spotRatio: null,
          nodes: { total: null, spot: null, fallback: null, onDemand: null },
          _nodeCountPending: true,
        } : {
          spotRatio: totalNodes > 0 ? Math.round((spotNodes / totalNodes) * 100) : 0,
          nodes: {
            total: totalNodes,
            spot: spotNodes,
            fallback: 0,
            onDemand: onDemandNodes,
          },
          _nodeCountPending: false,
        }),
        // Use real per-node data when available (weighted sum across all nodes),
        // so CPU/MEM % reflects actual live utilization vs total capacity —
        // making it easy to spot overprovisioned clusters.
        // Falls back to stale cluster-level metric fields when node data isn't loaded yet.
        cpu: nodeList.length > 0
          ? {
              used: Math.round(nodeList.reduce((s, n) => s + n.cpu.used, 0) * 100) / 100,
              total: nodeList.reduce((s, n) => s + n.cpu.total, 0),
              requested: Math.round(nodeList.reduce((s, n) => s + (n.cpu.requested || 0), 0) * 100) / 100,
            }
          : { used: Math.round((c.cpu_total * Math.round(c.cpu_usage_pct))) / 100, total: c.cpu_total, requested: 0 },
        memory: nodeList.length > 0
          ? {
              used: Math.round(nodeList.reduce((s, n) => s + n.memory.used, 0) * 100) / 100,
              total: nodeList.reduce((s, n) => s + n.memory.total, 0),
              requested: Math.round(nodeList.reduce((s, n) => s + (n.memory.requested || 0), 0) * 100) / 100,
            }
          : { used: Math.round((c.mem_total * Math.round(c.mem_usage_pct))) / 100, total: c.mem_total, requested: 0 },
        cpuUsagePct: c.cpu_usage_pct || 0,
        memUsagePct: c.mem_usage_pct || 0,
        workloadType: c.workload_type || null, // 'stateless' | 'stateful' | null
        cost: {
          monthly: c.monthly_cost || 0,
          savings: c.realized_savings_monthly || 0,
          potential: c.potential_savings_monthly || 0
        },
        atharva: { active: agentHealthy, realized: c.realized_savings_monthly || 0, potential: c.potential_savings_monthly || 0 },
        policies: { active: c.policy_count || 0, total: 5 },
        hibernation: { schedules: c.hibernation_schedules || 0, savedHrs: 0 },
        rightsizing: rightsizingData[c.id] || { overProvisioned: 0, savingsPotential: 0 },
        k8sVersion: c.version || "1.28",
        nodeGroups: c.node_pool_count || 2,
        nodeList,
        agent_installed: c.agent_installed // Pass through for banner check
      };
    });
  }, [clusters, nodeDetails, nodeDetailsPending, rightsizingData]);

  // Keep ref in sync so the interval below always reads the latest mapped clusters
  // without triggering a re-run of the node-details effect on every render.
  useEffect(() => {
    mappedClustersRef.current = mappedClusters;
  });

  // Fetch detailed nodes when a cluster is selected, then refresh every 60s for live metrics
  const fetchNodeDetailsForCluster = (clusterId, clusterList) => {
    const selectedCluster = clusterList.find(c => c.id === clusterId);
    if (!selectedCluster || !selectedCluster.agentInstalled) return;
    // RC4 fix: mark this cluster as pending ONLY on first fetch (no prior data)
    setNodeDetailsPending(prev => {
      if (!nodeDetails[clusterId]) {
        const next = new Set(prev);
        next.add(clusterId);
        return next;
      }
      return prev;
    });
    Promise.all([
      clusterAPI.getNodesDetailed(clusterId),
      clusterAPI.getWarmSpareStatus(clusterId).catch(() => null),
    ]).then(([nodesRes, subRes]) => {
      const data = { ...nodesRes.data };
      // Only inject warm spare node when it is ACTUALLY spinning up (PREWARMING) or
      // already running and ready to swap (ACTIVE). READY means a candidate pool was
      // pre-selected by DryRun — no actual EC2 instance is running yet, so don't show it.
      const sub = subRes?.data;
      if (sub && sub.is_warm_spare && sub.state && ['PREWARMING', 'ACTIVE'].includes(sub.state)) {
        const spareNode = {
          instance_id: 'warm-spare',
          node_name: 'Warm Spare',
          instance_type: sub.spare_instance_type || 'spot',
          lifecycle: 'spot',
          classification: 'WARM_SPARE',
          cpu_utilization_pct: 0,
          memory_utilization_pct: 0,
          cpu_capacity_cores: sub.target_vcpu || 2,
          memory_capacity_gb: sub.target_memory_gb || 4,
          pod_count: 0,
          status: sub.state === 'READY' ? 'ready' : 'prewarming',
          _isWarmSpare: true,
          _spareState: sub.state,
          _spareAz: sub.spare_az,
          _sparePrice: sub.spot_price_hourly,
        };
        data.nodes = [...(data.nodes || []), spareNode];
      }
      setNodeDetails(prev => ({ ...prev, [clusterId]: data }));
      // RC4 fix: clear pending flag once real data has arrived
      setNodeDetailsPending(prev => { const next = new Set(prev); next.delete(clusterId); return next; });
    }).catch((err) => {
      console.error('Failed to fetch node details:', err);
      // Clear pending on error too so we don't show spinner forever
      setNodeDetailsPending(prev => { const next = new Set(prev); next.delete(clusterId); return next; });
    });
  };

  useEffect(() => {
    if (!selected) return;
    // Use the ref so this effect only re-runs when `selected` changes,
    // not every time mappedClusters recomputes (which caused an infinite loop).
    fetchNodeDetailsForCluster(selected, mappedClustersRef.current);
    const interval = setInterval(() => {
      fetchNodeDetailsForCluster(selected, mappedClustersRef.current);
    }, 15000); // 15s — real-time metrics polling
    return () => clearInterval(interval);
  }, [selected]); // eslint-disable-line react-hooks/exhaustive-deps

  // Re-fetch node details when clusters reload (e.g. after Refresh clears nodeDetails)
  useEffect(() => {
    if (!selected || clusters.length === 0) return;
    if (!nodeDetails[selected]) {
      fetchNodeDetailsForCluster(selected, mappedClustersRef.current);
    }
  }, [clusters, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() =>
    mappedClusters.filter(c => {
      const matchSearch = c.name.toLowerCase().includes(search.toLowerCase()) || c.region.toLowerCase().includes(search.toLowerCase());
      const matchStatus = statusFilter === "All" || (c.status.toLowerCase() === statusFilter.toLowerCase().replace(" ", "-"));
      const matchKarpenter = karpenterModeFilter === "ALL"
        || (karpenterModeFilter === "KARPENTER" && c.karpenter_mode)
        || (karpenterModeFilter === "LEGACY" && !c.karpenter_mode);
      return matchSearch && matchStatus && matchKarpenter;
    }), [mappedClusters, search, statusFilter, karpenterModeFilter]);

  // Set selected if not set and we have clusters
  useEffect(() => {
    if (!selected && filtered.length > 0) {
      setSelected(filtered[0].id);
    }
  }, [filtered, selected]);

  const cluster = filtered.find(c => c.id === selected) || mappedClusters[0] || null;

  // Summary stats for top bar
  // RC4 fix: null-safe reduce — pending clusters contribute 0 to the top-bar total
  const totalNodes = mappedClusters.reduce((s, c) => s + (c.nodes.total ?? 0), 0);
  const totalSpot = mappedClusters.reduce((s, c) => s + (c.nodes.spot ?? 0), 0);
  const totalCost = mappedClusters.reduce((s, c) => s + c.cost.monthly, 0);
  const totalSavings = mappedClusters.reduce((s, c) => s + c.cost.savings, 0);
  const withAgent = mappedClusters.filter(c => c.agentInstalled).length;

  const handleRefreshDiscovery = async () => {
    setRefreshing(true);
    toast.loading('Scanning all regions for clusters...', { id: 'discovery' });
    try {
      await clusterAPI.discover();

      // Poll every 2s for up to 30s — discovery scans 14 regions so takes a bit longer
      let foundNew = false;
      const initialCount = clusters.length;

      for (let i = 0; i < 15; i++) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        try {
          const pollRes = await clusterAPI.list();
          // Fix: response is { clusters: [...], total: N } — check .clusters.length
          const newCount = pollRes.data?.clusters?.length ?? pollRes.data?.length ?? 0;
          if (newCount > initialCount) {
            foundNew = true;
            break;
          }
        } catch (e) {
          // ignore polling errors
        }
      }

      await fetchData(); // Final sync — always refresh after discovery

      if (foundNew) {
        toast.success('New clusters discovered!', { id: 'discovery' });
      } else {
        toast.success('Discovery scan complete', { id: 'discovery' });
      }
    } catch (error) {
      toast.error('Failed to start discovery: ' + (error.response?.data?.detail || error.message), { id: 'discovery' });
    } finally {
      setRefreshing(false);
    }
  };

  // Push to Global Navbar
  useEffect(() => {
    headerStore.setRefreshAction({
      onClick: handleRefreshDiscovery,
      loading: refreshing,
    });
    headerStore.setRightContent(
      <>
        {/* Quick stats */}
        {[
          { label: `${mappedClusters.length} clusters` },
          { label: `${withAgent}/${mappedClusters.length} with agent`, dot: C.green },
          { label: `${totalNodes} nodes` },
          { label: `${totalNodes > 0 ? Math.round(totalSpot / totalNodes * 100) : 0}% spot`, dot: C.green },
        ].map((s, i) => (
          <div key={i} className="hidden lg:flex" style={{ padding: "4px 12px", borderRight: i < 3 ? `1px solid #f0f0f0` : "none", alignItems: "center", gap: 5, flexShrink: 0 }}>
            {s.dot && <div style={{ width: 5, height: 5, borderRadius: "50%", background: s.dot }} />}
            <span style={{ fontSize: 12, color: C.muted }}>{s.label}</span>
          </div>
        ))}
        {/* Cost summary */}
        <div className="hidden lg:flex" style={{ gap: 6, paddingLeft: 6, paddingRight: 6, alignItems: "center" }}>
          <div style={{ padding: "5px 12px", borderRadius: 8, background: "#f0f1f3", fontSize: 12, color: C.muted }}>
            Total: <strong style={{ color: C.text, fontWeight: 700 }}>${totalCost.toLocaleString()}/mo</strong>
          </div>
          <div style={{ padding: "5px 12px", borderRadius: 8, background: C.surface, border: `1px solid ${C.border}`, fontSize: 12, color: C.muted, display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: C.green }} />
            ${totalSavings.toLocaleString()} saved
          </div>
        </div>
      </>
    );

    return () => headerStore.clearHeader();
  }, [mappedClusters, withAgent, totalNodes, totalSpot, totalCost, totalSavings, refreshing]);

  if (loading && mappedClusters.length === 0) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div style={{
      minHeight: "100vh",
      background: C.bg,
      fontFamily: "'DM Sans', system-ui, sans-serif",
      color: C.text,
      display: "flex",
      flexDirection: "column",
    }}>

      {/* ── TOP BAR IS NOW GLOBAL HEADER ── */}

      {/* ── MASTER-DETAIL LAYOUT ── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", height: "calc(100vh - 72px)" }}>

        {/* LEFT: Cluster list */}
        <div style={{
          width: 260,
          flexShrink: 0,
          borderRight: `1px solid ${C.border}`,
          background: "#fafafa",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}>
          {/* Search */}
          <div style={{ padding: "12px 12px 8px" }}>
            <div style={{
              display: "flex", alignItems: "center", gap: 8,
              background: C.surface, border: `1px solid ${C.border}`,
              borderRadius: 9, padding: "7px 10px",
            }}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <circle cx="6.5" cy="6.5" r="5" stroke="#9ca3af" strokeWidth="1.5" />
                <path d="M10.5 10.5L14 14" stroke="#9ca3af" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Search clusters..."
                style={{
                  border: "none", outline: "none", background: "transparent",
                  fontSize: 12, color: C.text, width: "100%", fontFamily: "inherit",
                }}
              />
            </div>
          </div>

          {/* Status filter chips */}
          <div style={{ padding: "0 12px 10px", display: "flex", gap: 4 }}>
            {["All", "Healthy", "Warning", "No Agent"].map(f => (
              <button
                key={f}
                onClick={() => setStatusFilter(f)}
                style={{
                  padding: "3px 8px", borderRadius: 6, border: `1px solid ${C.border}`,
                  background: statusFilter === f ? "#0f1117" : C.surface,
                  color: statusFilter === f ? "#fff" : C.muted,
                  fontSize: 10, cursor: "pointer", fontFamily: "inherit", fontWeight: statusFilter === f ? 600 : 400,
                }}>{f}</button>
            ))}
          </div>

          {/* Karpenter mode selector */}
          <div style={{ padding: "0 12px 10px" }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: C.subtle, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
              Karpenter Mode
            </div>
            <select
              value={karpenterModeFilter}
              onChange={e => setKarpenterModeFilter(e.target.value)}
              style={{
                width: "100%", padding: "5px 8px", borderRadius: 7, border: `1px solid ${C.border}`,
                background: C.surface, color: C.text, fontSize: 11, fontFamily: "inherit", cursor: "pointer",
              }}
            >
              <option value="ALL">All</option>
              <option value="KARPENTER">Karpenter</option>
              <option value="LEGACY">Legacy (non-Karpenter)</option>
            </select>
          </div>

          {/* List */}
          <div style={{ flex: 1, overflowY: "auto", padding: "0 12px 12px" }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: C.subtle, letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: 8 }}>
              {filtered.length} cluster{filtered.length !== 1 ? "s" : ""}
            </div>
            {filtered.map(c => (
              <ClusterListItem
                key={c.id}
                cluster={c}
                selected={selected === c.id}
                onClick={() => setSelectedAndPersist(c.id)}
              />
            ))}
            {filtered.length === 0 && (
              <div style={{ textAlign: "center", color: C.subtle, fontSize: 12, paddingTop: 24 }}>No clusters match</div>
            )}
          </div>
        </div>

        {/* RIGHT: Detail */}
        <div style={{ flex: 1, overflowY: "auto", background: C.bg, display: 'flex', flexDirection: 'column' }}>
          {cluster ? (
            cluster.agentInstalled
              ? <ClusterDetails clusterId={cluster.id} onClose={() => setSelectedAndPersist(null)} />
              : <NoAgentDetail cluster={cluster} onClose={() => setSelectedAndPersist(null)} />
          ) : (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: C.muted, fontSize: 14 }}>
              No cluster selected. Connect your AWS Account to generate clusters.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
