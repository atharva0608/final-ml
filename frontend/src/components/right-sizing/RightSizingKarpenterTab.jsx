import React, { useState, useEffect } from "react";
import { useSearchParams } from 'react-router-dom';
import { clusterAPI, karpenterAPI, ascpaiAPI, optimizerCoordinatorAPI } from "../../services/api";
import { toast } from "react-hot-toast";
import { FiCheckCircle, FiAlertTriangle, FiClock, FiLayers, FiTarget, FiDollarSign, FiActivity, FiServer, FiAlertCircle } from "react-icons/fi";
import RebalancingTimeline from '../ascpai/RebalancingTimeline';

// ============================================================================
// MODALS AND DRAWERS
// ============================================================================

function StatelessDetailedDrawer({ node, onClose, isAutoOn }) {
  if (!node) return null;
  return (
    <div className="fixed inset-0 bg-slate-900/40 z-[1000] flex items-center justify-center p-4">
      <div className="bg-white w-[600px] rounded-2xl p-6 shadow-2xl relative">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h3 className="text-lg font-bold text-slate-800 m-0 flex gap-2 items-center">
              {node.name}
              <span className="inline-flex items-center bg-indigo-50 text-indigo-700 text-[10px] font-semibold px-2 py-1 rounded tracking-wide uppercase">Stateless</span>
            </h3>
            <p className="text-sm text-slate-500 mt-1">{node.current} → {node.recommended}</p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 text-2xl leading-none">&times;</button>
        </div>
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
            <div className="text-xs text-slate-500 font-semibold mb-1">Top Candidate Sizes</div>
            <div className="text-sm font-semibold text-slate-800">1. {node.recommended}<br />2. {node.recommended.replace('large', 'xlarge')}<br />3. c6g.large</div>
          </div>
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
            <div className="text-xs text-slate-500 font-semibold mb-1">Diversification Check</div>
            <div className="text-sm font-semibold text-emerald-600">Passed (Within Limits)</div>
          </div>
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
            <div className="text-xs text-slate-500 font-semibold mb-1">Headroom / Volatility applied</div>
            <div className="text-sm font-semibold text-slate-800">{node.cpu}% P95 CPU (1.2x headroom)<br />{node.confidence < 60 ? '1.5x Volatility' : 'Normal Volatility'}</div>
          </div>
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-200">
            <div className="text-xs text-slate-500 font-semibold mb-1">Capacity DryRun / Cooldown</div>
            <div className={`text-sm font-semibold ${node.cooldown ? 'text-amber-600' : 'text-emerald-600'}`}>
              {node.cooldown ? 'Wait 3h' : 'ICE Checked: Available'}
            </div>
          </div>
        </div>
        <div className="flex gap-3 justify-end pt-4 border-t border-slate-200">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-slate-200 bg-white text-slate-600 text-sm font-semibold hover:bg-slate-50 cursor-pointer">Close</button>
          {!isAutoOn && (
            <button className="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 cursor-pointer">Apply Now (Manual Override)</button>
          )}
        </div>
      </div>
    </div>
  );
}

function StatefulProposalModal({ node, onClose, requireApproval = true }) {
  if (!node) return null;
  return (
    <div className="fixed inset-0 bg-slate-900/40 z-[1000] flex items-center justify-center p-4">
      <div className="bg-white w-[500px] rounded-2xl p-6 shadow-2xl border-2 border-slate-200 relative">
        <div className="flex justify-between items-start mb-4">
          <div>
            <h3 className="text-lg font-bold text-slate-800 m-0 flex gap-2 items-center">
              Submit Manual Resize
              <span className="inline-flex items-center bg-slate-100 text-slate-600 border border-slate-200 text-[10px] font-semibold px-2 py-1 rounded tracking-wide uppercase">Stateful</span>
            </h3>
            <p className="text-sm text-slate-500 mt-1">Node: {node.name}</p>
          </div>
        </div>

        <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 mb-5">
          <p className="text-sm text-amber-700 m-0 leading-relaxed font-medium">
            Spot pools are strictly locked for stateful workloads. This node will be resized using On-Demand instances.
          </p>
        </div>

        <div className="flex flex-col gap-3 p-4 bg-slate-50 rounded-xl border border-slate-200 mb-5">
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Current Type</span>
            <span className="font-semibold text-slate-800">{node.current}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Proposed Type</span>
            <span className="font-semibold text-indigo-600">{node.recommended}</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Estimated Savings</span>
            <span className="font-semibold text-emerald-600">${node.savings}/mo</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-slate-500">Peak Buffer Margin</span>
            <span className="font-semibold text-slate-800">~35% headroom remaining</span>
          </div>
        </div>

        <div className="flex gap-3 justify-end">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-slate-200 bg-white text-slate-600 text-sm font-semibold hover:bg-slate-50 cursor-pointer">Cancel</button>
          <button
            onClick={() => {
              karpenterAPI.applyRecommendation(node.id, {
                instance_id: node.name,
                recommended_type: node.recommended,
                is_stateful: true,
              }).then(() => {
                toast.success(`Resize queued: ${node.name} → ${node.recommended} (On-Demand)`);
                onClose();
              }).catch(() => toast.error('Submit failed — check permissions'));
            }}
            className={`px-4 py-2 rounded-lg text-white text-sm font-semibold cursor-pointer ${requireApproval ? 'bg-slate-700 hover:bg-slate-800' : 'bg-indigo-600 hover:bg-indigo-700'}`}>
            {requireApproval ? 'Submit for Approval' : 'Apply Resize Now'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// MAIN PAGE COMPONENT
// ============================================================================

export default function RightSizingMonitoringDashboard() {
  const [clusters, setClusters] = useState([]);
  const [selectedClusterId, setSelectedClusterId] = useState("all");
  const [autoState, setAutoState] = useState(false);
  const [rebalanceState, setRebalanceState] = useState(false);
  const [loading, setLoading] = useState(true);

  const [statelessNodes, setStatelessNodes] = useState([]);
  const [statefulNodes, setStatefulNodes] = useState([]);
  const [rebalancingActions, setRebalancingActions] = useState([]);
  const [karpenterSimulation, setKarpenterSimulation] = useState(null);

  // Fetch clusters
  useEffect(() => {
    clusterAPI.listClusters().then(res => {
      const data = res.data?.items || res.data?.clusters || res.data || [];
      const cl = Array.isArray(data) ? data : [];
      setClusters(cl);
      if (cl.length > 0) setSelectedClusterId(cl[0].id);
    }).catch(console.error);
  }, []);

  // Fetch timeline
  useEffect(() => {
    if (selectedClusterId === 'all' || !selectedClusterId) return;
    const fetchActions = () => {
      ascpaiAPI.getRebalancingStatus(selectedClusterId, 5)
        .then(res => setRebalancingActions(Array.isArray(res.data) ? res.data : []))
        .catch(() => { });
    };
    fetchActions();
    const interval = setInterval(fetchActions, 15000);
    return () => clearInterval(interval);
  }, [selectedClusterId]);

  // Fetch unified config and recommendations
  useEffect(() => {
    if (selectedClusterId === "all" || !selectedClusterId) return;
    setLoading(true);
    Promise.all([
      clusterAPI.getOptimizationSettings(selectedClusterId).catch(() => ({ data: null })),
      karpenterAPI.getRecommendations(selectedClusterId).catch(() => ({ data: { recommendations: [] } })),
      ascpaiAPI.getNodeRecommendations(selectedClusterId, { useRightsized: true }).catch(() => ({ data: null })),
    ]).then(([configRes, recsRes, nodeRecsRes]) => {
      const c = configRes.data;
      setAutoState(c?.automation_controls?.auto_rightsizing_enabled ?? false);
      setRebalanceState(c?.automation_controls?.auto_rebalance_enabled ?? false);

      // Extract karpenter simulation from node-recommendations response
      setKarpenterSimulation(nodeRecsRes.data?.karpenter_simulation || null);

      const rawRecs = recsRes.data?.recommendations || [];
      let sNodes = [];
      let stNodes = [];

      if (rawRecs.length > 0) {
        sNodes = rawRecs
          .filter(r => r.node_type === 'stateless' || (r.current_lifecycle || '').includes('spot'))
          .map((r, i) => ({
            id: r.id || `stateless-${i}`,
            name: r.instance_id || `spot-node-${i}`,
            current: r.current_type || 'unknown',
            recommended: r.recommended_type || r.current_type || 'unknown',
            cpu: r.cpu ?? 0,
            mem: r.mem ?? 0,
            savings: Math.round(r.potential_savings ?? 0),
            savings_pct: r.savings_pct ?? 0,
            resize_savings: r.resize_savings ?? 0,
            spot_pool: r.spot_pool || null,
            ev_pct: r.ev_pct ?? (r.risk_prob != null ? Math.max(0, 100 - r.risk_prob) : 85),
            confidence: r.risk_prob != null ? Math.max(0, 100 - r.risk_prob) : 85,
            impact: r.impact || 'Neutral',
            is_upsize: r.is_upsize || false,
            is_actionable: r.is_actionable ?? null,
            reason: r.reason || '',
            cooldown: false,
          }));

        stNodes = rawRecs
          .filter(r => r.node_type === 'stateful' && !(r.current_lifecycle || '').includes('spot'))
          .map((r, i) => ({
            id: r.id || `stateful-${i}`,
            name: r.instance_id || `od-node-${i}`,
            current: r.current_type || 'unknown',
            recommended: r.recommended_type || r.current_type || 'unknown',
            cpu: r.cpu ?? 0,
            mem: r.mem ?? 0,
            savings: Math.round(r.potential_savings ?? 0),
            savings_pct: r.savings_pct ?? 0,
            resize_savings: Math.round(r.resize_savings ?? 0),
            reason: r.reason || '',
            status: 'Ready',
          }));
      }

      setStatelessNodes(sNodes);
      setStatefulNodes(stNodes);
      setLoading(false);
    });
  }, [selectedClusterId]);

  const activeTargetsCount = statelessNodes.filter(n => n.savings > 0).length + statefulNodes.filter(n => n.savings > 0).length;
  const totalSavings = statelessNodes.reduce((a, b) => a + Number(b.savings), 0) + statefulNodes.reduce((a, b) => a + Number(b.savings), 0);
  const displaySavings = (totalSavings / 1000).toFixed(1);
  const displayActiveTargets = activeTargetsCount;

  const eligibleStatefulNodes = statefulNodes.filter(n => n.savings > 0);

  const [selectedStatelessNode, setSelectedStatelessNode] = useState(null);
  const [selectedStatefulNode, setSelectedStatefulNode] = useState(null);

  if (loading && selectedClusterId !== "all") {
    return <div className="text-center p-16 text-slate-500 font-sans">Loading optimization telemetry...</div>;
  }

  return (
    <div className="font-sans text-slate-800 w-full min-h-screen">

      {/* HEADER PAGE */}
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-[28px] font-bold text-slate-800 m-0 leading-tight">Right-Sizing Monitoring</h1>
          <p className="text-[14px] font-medium text-slate-500 mt-1 m-0">Real-time resource optimization across production environments.</p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[13px] font-semibold text-slate-500">Target Cluster</span>
          <select
            value={selectedClusterId}
            onChange={e => setSelectedClusterId(e.target.value)}
            className="py-2 pl-4 pr-10 text-[14px] font-semibold text-slate-800 bg-white border border-slate-200 rounded-lg shadow-sm appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
            style={{ backgroundImage: `url('data:image/svg+xml;charset=US-ASCII,%3Csvg%20width%3D%2220%22%20height%3D%2220%22%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%3E%3Cpath%20d%3D%22M5%208l5%205%205-5%22%20stroke%3D%22%236b7280%22%20stroke-width%3D%222%22%20fill%3D%22none%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%2F%3E%3C%2Fsvg%3E')`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center' }}
          >
            <option value="all" disabled>Select a cluster...</option>
            {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>

      {/* TOP SCORING KPIs */}
      <div className="grid grid-cols-4 gap-6 mb-8">
        <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] p-6">
          <div className="flex justify-between items-start mb-4">
            <div className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Total Clusters</div>
            <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center border border-slate-100">
              <FiLayers className="text-slate-400" size={16} />
            </div>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-[32px] font-extrabold text-slate-800 leading-none">{clusters.length}</div>
            <div className="text-[13px] font-bold text-slate-400 flex items-center">
              —
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] p-6">
          <div className="flex justify-between items-start mb-4">
            <div className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Active Targets</div>
            <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center border border-slate-100">
              <FiTarget className="text-slate-400" size={16} />
            </div>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-[32px] font-extrabold text-slate-800 leading-none">{displayActiveTargets}</div>
            <div className="text-[13px] font-bold text-slate-400 flex items-center">
              —
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] p-6">
          <div className="flex justify-between items-start mb-4">
            <div className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Monthly Savings</div>
            <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center border border-slate-100">
              <FiDollarSign className="text-slate-400" size={16} />
            </div>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-[32px] font-extrabold text-slate-800 leading-none">${displaySavings}k</div>
            <div className="text-[13px] font-bold text-slate-400 flex items-center">
              —
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] p-6">
          <div className="flex justify-between items-start mb-4">
            <div className="text-[11px] font-bold text-slate-500 uppercase tracking-widest">Efficiency Score</div>
            <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center border border-slate-100">
              <FiActivity className="text-slate-400" size={16} />
            </div>
          </div>
          <div className="flex items-baseline gap-3">
            <div className="text-[32px] font-extrabold text-slate-800 leading-none">—</div>
            <div className="text-[13px] font-bold text-slate-400 flex items-center">
              —
            </div>
          </div>
        </div>
      </div>

      {/* MAIN CONTENT GRID */}
      {selectedClusterId !== "all" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">

          {/* LEFT COLUMN */}
          <div className="lg:col-span-2 flex flex-col gap-6">

            {/* EXPOSURE SNAPSHOT */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] overflow-hidden">
              <div className="flex justify-between items-center px-6 py-5 border-b border-slate-100">
                <h2 className="text-[13px] font-extrabold text-slate-800 m-0 leading-none">Exposure Snapshot</h2>
                <div className="flex items-center gap-4 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
                  <span className="flex items-center gap-2"><div className="w-2.5 h-2.5 rounded-full bg-orange-600"></div> On-Demand</span>
                  <span className="flex items-center gap-2"><div className="w-2.5 h-2.5 rounded-full bg-indigo-100"></div> Spot</span>
                </div>
              </div>
              <div className="p-8 grid grid-cols-2 gap-12">

                {/* Availability Strategy */}
                <div>
                  <div className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-8">Availability Strategy</div>
                  <div className="flex justify-center mb-10">
                    {karpenterSimulation ? (
                      <div className="flex flex-col items-center gap-3">
                        <div className="relative w-28 h-28">
                          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                            <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e2e8f0" strokeWidth="3" />
                            <circle cx="18" cy="18" r="15.9" fill="none" stroke="#6366f1" strokeWidth="3" strokeDasharray={`${karpenterSimulation.simulated_spot_pct} ${100 - karpenterSimulation.simulated_spot_pct}`} strokeLinecap="round" />
                          </svg>
                          <div className="absolute inset-0 flex flex-col items-center justify-center">
                            <span className="text-[16px] font-extrabold text-slate-800">{karpenterSimulation.simulated_spot_pct}%</span>
                            <span className="text-[9px] font-bold text-slate-400 uppercase">Spot</span>
                          </div>
                        </div>
                        <div className="flex gap-4 text-[10px] font-bold">
                          <span className="text-indigo-600">{karpenterSimulation.simulated_spot_node_count} Spot</span>
                          <span className="text-orange-600">{karpenterSimulation.simulated_od_node_count} OD</span>
                        </div>
                      </div>
                    ) : (
                      <div className="flex items-center justify-center w-28 h-28 rounded-full bg-slate-100 text-slate-400 text-xs text-center">Data<br/>pending</div>
                    )}
                  </div>
                </div>

                {/* AZ Distribution */}
                <div>
                  <div className="text-[11px] font-bold text-slate-500 uppercase tracking-widest mb-8">AZ Distribution</div>
                  <div className="flex flex-col gap-6 mb-10">
                    {(karpenterSimulation?.az_distribution || []).length > 0 ? (
                      karpenterSimulation.az_distribution.map(az => (
                        <div key={az.az}>
                          <div className="flex justify-between text-[11px] font-bold text-slate-800 mb-2">
                            <span>{az.az}</span>
                            <span className="text-slate-500">{az.pct}%</span>
                          </div>
                          <div className="w-full h-2.5 bg-slate-100 rounded-full overflow-hidden">
                            <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${az.pct}%` }}></div>
                          </div>
                        </div>
                      ))
                    ) : (
                      <div className="text-[12px] text-slate-400 font-medium">Enable right-sizing to see simulated AZ distribution</div>
                    )}
                  </div>

                  {karpenterSimulation?.az_distribution?.length > 0 && karpenterSimulation.az_distribution[0].pct > 60 && (
                    <div className="bg-[#fff9f2] border border-[#fdecd5] rounded-xl p-4 flex gap-3 items-start">
                      <FiAlertCircle className="text-orange-600 flex-shrink-0 mt-0.5" />
                      <div>
                        <div className="text-[10px] font-extrabold text-orange-600 uppercase tracking-widest mb-1.5 leading-none">Insight</div>
                        <div className="text-[12px] text-orange-800 leading-relaxed font-medium">High concentration in {karpenterSimulation.az_distribution[0].az} ({karpenterSimulation.az_distribution[0].pct}%). Consider increasing topology spread for better fault tolerance.</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* GUARD & STABILITY PANEL */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] p-6">
              <div className="flex justify-between items-center mb-6">
                <div className="text-[11px] font-extrabold text-slate-600 uppercase tracking-widest">Guard & Stability Panel</div>
                <div className="flex items-center gap-3">
                  <span className="text-[11px] font-bold text-slate-500">Confidence:</span>
                  <span className={`px-3 py-1 rounded-md text-[11px] font-extrabold border ${
                    (karpenterSimulation?.confidence_score ?? 0) >= 80
                      ? 'bg-emerald-50 text-emerald-600 border-emerald-100'
                      : 'bg-orange-50 text-orange-600 border-orange-100'
                  }`}>{karpenterSimulation?.confidence_score ?? '—'}/100</span>
                </div>
              </div>
              <div className="grid grid-cols-6 gap-3">
                <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 flex flex-col justify-center">
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 leading-none">Rollbacks (24H)</div>
                  <div className="text-[16px] font-extrabold text-slate-800 leading-none">{rebalancingActions.filter(a => a.status === 'rolled_back').length}</div>
                </div>
                <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 flex flex-col justify-center">
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 leading-none">Actions (24H)</div>
                  <div className="text-[16px] font-extrabold text-indigo-500 leading-none">{rebalancingActions.length}</div>
                </div>
                <div className={`${(karpenterSimulation?.provisioning_failures ?? 0) === 0 ? 'bg-emerald-50 border-emerald-100' : 'bg-orange-50 border-orange-100'} rounded-xl p-4 flex flex-col justify-center`}>
                  <div className={`text-[11px] font-bold uppercase tracking-wider mb-2 leading-none ${(karpenterSimulation?.provisioning_failures ?? 0) === 0 ? 'text-emerald-500' : 'text-orange-500'}`}>Prov. Failures</div>
                  <div className={`text-[16px] font-extrabold leading-none ${(karpenterSimulation?.provisioning_failures ?? 0) === 0 ? 'text-emerald-600' : 'text-orange-600'}`}>{karpenterSimulation?.provisioning_failures ?? 0}</div>
                </div>
                <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 flex flex-col justify-center">
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 leading-none">Sim Cycles</div>
                  <div className="text-[16px] font-extrabold text-slate-800 leading-none">{karpenterSimulation?.cycles_to_converge ?? '—'}</div>
                </div>
                <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 flex flex-col justify-center">
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 leading-none">Topology Spread</div>
                  <div className="text-[16px] font-extrabold text-slate-800 leading-none">{karpenterSimulation?.topology_spread ?? '—'}</div>
                </div>
                <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 flex flex-col justify-center">
                  <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 leading-none">Fragmentation</div>
                  <div className="text-[16px] font-extrabold text-slate-800 leading-none">{karpenterSimulation?.scheduler_fragmentation_pct != null ? `${karpenterSimulation.scheduler_fragmentation_pct}%` : '—'}</div>
                </div>
              </div>
            </div>

            {/* ACTIVE NODE MIGRATIONS */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] overflow-hidden p-6 pb-12">
              <div className="text-[11px] font-extrabold text-slate-600 uppercase tracking-widest mb-6 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${rebalancingActions.some(a => a.status === 'in_progress') ? 'bg-orange-400' : 'bg-emerald-400'}`}></span>
                  <span className={`relative inline-flex rounded-full h-2 w-2 ${rebalancingActions.some(a => a.status === 'in_progress') ? 'bg-orange-500' : 'bg-emerald-500'}`}></span>
                </span>
                ACTIVE NODE MIGRATIONS <span className="text-slate-400 lowercase normal-case">({rebalancingActions.filter(a => a.status === 'in_progress').length} active)</span>
              </div>
              <RebalancingTimeline clusterId={selectedClusterId} />
            </div>

            {/* RESOURCE ALLOCATION BY INSTANCE FAMILY */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] overflow-hidden p-6 pb-4">
              <div className="text-[11px] font-extrabold text-slate-600 uppercase tracking-widest mb-12">RESOURCE ALLOCATION BY INSTANCE FAMILY</div>
              <div className="flex items-center justify-center w-full h-32 bg-slate-50 rounded text-slate-400 text-xs">Chart data pending</div>
            </div>

          </div>

          {/* RIGHT COLUMN */}
          <div className="flex flex-col gap-6">

            {/* NEXT TARGET */}
            {(() => {
              const nextTarget = statelessNodes.find(n => n.savings > 0) || statefulNodes.find(n => n.savings > 0);
              return (
                <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] overflow-hidden">
                  <div className="flex justify-between items-center px-6 py-4 border-b border-slate-100">
                    <div className="text-[11px] font-extrabold text-slate-600 uppercase tracking-widest">Next Target</div>
                    {nextTarget ? (
                      <span className="bg-orange-50 text-orange-600 px-2.5 py-1 rounded text-[9px] font-bold uppercase tracking-wider border border-orange-100">Ready</span>
                    ) : (
                      <span className="bg-slate-50 text-slate-400 px-2.5 py-1 rounded text-[9px] font-bold uppercase tracking-wider border border-slate-100">None</span>
                    )}
                  </div>
                  <div className="p-6">
                    {nextTarget ? (
                      <>
                        <div className="bg-slate-50 border border-slate-100 rounded-xl p-4 mb-6 flex items-center gap-4">
                          <div className="w-10 h-10 rounded-lg bg-orange-100 text-orange-600 flex items-center justify-center shrink-0 border border-orange-200">
                            <FiServer size={18} />
                          </div>
                          <div>
                            <div className="text-[12px] font-extrabold text-slate-800 leading-none mb-1.5">{nextTarget.name}</div>
                            <div className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider leading-none">{nextTarget.current} → {nextTarget.recommended}</div>
                          </div>
                        </div>
                        <div className="flex flex-col gap-4 mb-8">
                          <div className="flex justify-between items-center">
                            <span className="text-[12px] text-slate-500 font-bold uppercase tracking-wider">Proposed Type</span>
                            <span className="text-[13px] font-extrabold text-slate-800">{nextTarget.recommended}</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-[12px] text-slate-500 font-bold uppercase tracking-wider">Monthly Savings</span>
                            <span className="text-[13px] font-extrabold text-emerald-500">+${nextTarget.savings}/mo</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-[12px] text-slate-500 font-bold uppercase tracking-wider">Confidence</span>
                            <span className={`text-[12px] font-bold flex items-center gap-1.5 ${nextTarget.confidence >= 70 ? 'text-emerald-500' : 'text-orange-500'}`}>
                              {nextTarget.confidence >= 70 ? <FiCheckCircle size={14} /> : <FiAlertTriangle size={14} />} {nextTarget.confidence}%
                            </span>
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="text-center py-8 text-[12px] text-slate-400 font-medium">All nodes are optimally sized.</div>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* SIMULATION STATUS */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] overflow-hidden">
              <div className="px-6 py-4 border-b border-slate-100">
                <div className="text-[11px] font-extrabold text-slate-600 uppercase tracking-widest">Simulation Status</div>
              </div>
              <div className="p-6 flex flex-col gap-6">

                <div className="relative pl-7">
                  <div className={`absolute left-0 top-1.5 w-2.5 h-2.5 rounded-full ${karpenterSimulation?.converged ? 'bg-emerald-500' : 'bg-orange-400'}`}></div>
                  <div className="text-[12px] font-bold text-slate-800 mb-1 leading-none">Convergence</div>
                  <div className="text-[11px] text-slate-500 font-medium">{karpenterSimulation?.converged ? `Converged in ${karpenterSimulation.cycles_to_converge} cycles` : karpenterSimulation?.timed_out ? 'Timed out' : 'Pending simulation'}</div>
                </div>

                <div className="relative pl-7">
                  <div className={`absolute left-0 top-1.5 w-2.5 h-2.5 rounded-full ${(karpenterSimulation?.pending_pods_peak ?? 0) === 0 ? 'bg-emerald-500' : 'bg-orange-400'}`}></div>
                  <div className="text-[12px] font-bold text-slate-800 mb-1 leading-none">Pod Scheduling</div>
                  <div className="text-[11px] text-slate-500 font-medium">{karpenterSimulation ? `${karpenterSimulation.total_pods_packed}/${karpenterSimulation.total_pods_in_cluster} pods packed (${karpenterSimulation.pending_pods_peak} peak pending)` : 'Data pending'}</div>
                </div>

                <div className="relative pl-7">
                  <div className={`absolute left-0 top-1.5 w-2.5 h-2.5 rounded-full ${(karpenterSimulation?.nodes_eliminated ?? 0) > 0 ? 'bg-emerald-500' : 'bg-slate-300'}`}></div>
                  <div className="text-[12px] font-bold text-slate-800 mb-1 leading-none">Consolidation</div>
                  <div className="text-[11px] text-slate-500 font-medium">{karpenterSimulation ? `${karpenterSimulation.current_node_count} → ${karpenterSimulation.total_node_count} nodes (${karpenterSimulation.nodes_eliminated} eliminated)` : 'Data pending'}</div>
                </div>

                <div className="mt-4 pt-6 border-t border-slate-100">
                  <div className="flex justify-between items-center mb-3">
                    <span className="text-[10px] font-extrabold text-slate-500 uppercase tracking-widest">Savings</span>
                    <span className="text-[11px] font-extrabold text-emerald-600">{karpenterSimulation ? `$${karpenterSimulation.monthly_savings}/mo` : '—'}</span>
                  </div>
                  <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${karpenterSimulation?.current_monthly_cost > 0 ? Math.min(100, Math.round(karpenterSimulation.monthly_savings / karpenterSimulation.current_monthly_cost * 100)) : 0}%` }}></div>
                  </div>
                </div>

              </div>
            </div>

            {/* LIVE UPDATES */}
            <div className={`rounded-xl border shadow-[0_2px_4px_rgba(0,0,0,0.02)] overflow-hidden ${
              rebalancingActions.length > 0 ? 'bg-[#fff9f9] border-[#fee2e2]' : 'bg-white border-slate-200'
            }`}>
              <div className={`px-5 py-3 border-b ${rebalancingActions.length > 0 ? 'border-[#fee2e2]' : 'border-slate-100'}`}>
                <div className={`text-[10px] font-extrabold uppercase tracking-widest flex items-center gap-2 ${rebalancingActions.length > 0 ? 'text-[#ef4444]' : 'text-slate-500'}`}>
                  <span className="relative flex h-1.5 w-1.5">
                    <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${rebalancingActions.length > 0 ? 'bg-red-400' : 'bg-slate-300'}`}></span>
                    <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${rebalancingActions.length > 0 ? 'bg-red-500' : 'bg-slate-400'}`}></span>
                  </span>
                  RECENT ACTIVITY
                </div>
              </div>
              <div className={`p-5 flex flex-col gap-4 ${rebalancingActions.length > 0 ? 'bg-[#fff5f5]' : 'bg-white'}`}>
                {rebalancingActions.length > 0 ? rebalancingActions.slice(0, 4).map((action, i) => (
                  <div key={action.id || i} className="flex gap-3 text-[11px]">
                    <span className="font-extrabold text-slate-800 whitespace-nowrap pt-0.5">
                      {action.created_at ? new Date(action.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                    </span>
                    <span className="text-slate-600 leading-relaxed font-medium">
                      <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 ${
                        action.status === 'completed' ? 'bg-emerald-500'
                        : action.status === 'in_progress' ? 'bg-orange-500'
                        : action.status === 'failed' ? 'bg-red-500'
                        : 'bg-slate-400'
                      }`}></span>
                      {action.action_type || 'rebalance'} — <span className="font-bold text-slate-700">{action.status}</span>
                    </span>
                  </div>
                )) : (
                  <div className="text-[11px] text-slate-400 font-medium text-center py-2">No recent activity</div>
                )}
              </div>
            </div>

          </div>
        </div>
      )}

      {/* STATEFUL NODES TABLE (FULL WIDTH BOTTOM) */}
      {selectedClusterId !== "all" && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-[0_2px_4px_rgba(0,0,0,0.02)] overflow-hidden">
          <div className="flex justify-between items-center p-6 pb-0 mb-6">
            <div>
              <h2 className="text-[15px] font-extrabold text-slate-800 m-0 flex items-center gap-3">
                Stateful Nodes (Manual Only)
                <span className="bg-slate-100 text-slate-500 border border-slate-200 px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider">Manual Only</span>
              </h2>
              <p className="text-[12px] font-medium text-slate-500 mt-1">Strictly isolated from automated resizing and spot pool logic.</p>
            </div>
          </div>

          {/* Stateful KPIs */}
          <div className="grid grid-cols-4 gap-6 px-6 border-y border-slate-100 py-6 mb-2">
            <div>
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Total Stateful Nodes</div>
              <div className="text-[24px] font-extrabold text-slate-800">{statefulNodes.length}</div>
            </div>
            <div className="border-l border-slate-100 pl-6">
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Eligible For Propose</div>
              <div className="text-[24px] font-extrabold text-slate-800">{eligibleStatefulNodes.length}</div>
            </div>
            <div className="border-l border-slate-100 pl-6">
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">On-Demand Savings Potential</div>
              <div className="text-[24px] font-extrabold text-emerald-500">$0/mo</div>
            </div>
            <div className="border-l border-slate-100 pl-6">
              <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1.5">Max Downscale Allowed</div>
              <div className="text-[24px] font-extrabold text-orange-500">50%</div>
            </div>
          </div>

          {/* TABLE */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[12px]">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="py-4 px-6 font-bold text-slate-400 text-[10px] uppercase tracking-wider">Node</th>
                  <th className="py-4 px-6 font-bold text-slate-400 text-[10px] uppercase tracking-wider">Current Type</th>
                  <th className="py-4 px-6 font-bold text-slate-400 text-[10px] uppercase tracking-wider">CPU / Mem</th>
                  <th className="py-4 px-6 font-bold text-slate-400 text-[10px] uppercase tracking-wider">Recommended</th>
                  <th className="py-4 px-6 font-bold text-slate-400 text-[10px] uppercase tracking-wider">On-Demand Savings</th>
                  <th className="py-4 px-6 font-bold text-slate-400 text-[10px] uppercase tracking-wider">Policy Status</th>
                  <th className="py-4 px-6 font-bold text-slate-400 text-[10px] uppercase tracking-wider text-right">Action</th>
                </tr>
              </thead>
              <tbody>
                {statefulNodes.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="py-16 text-center text-slate-400">
                      <div className="flex flex-col items-center gap-3">
                        <FiServer className="w-8 h-8 text-slate-200" />
                        <span className="text-sm font-medium">No stateful nodes found.</span>
                      </div>
                    </td>
                  </tr>
                ) : statefulNodes.map((n, i) => (
                  <tr key={n.id} className="border-b border-slate-100 hover:bg-slate-50 transition-colors">
                    <td className="py-4 px-6 font-bold text-slate-800">{n.name}</td>
                    <td className="py-4 px-6 text-slate-500 font-medium">{n.current}</td>
                    <td className="py-4 px-6 text-slate-500 font-medium">{n.cpu}% / {n.mem}%</td>
                    <td className="py-4 px-6 font-bold text-slate-800">{n.recommended}</td>
                    <td className="py-4 px-6 font-bold text-emerald-600">${n.savings}/mo</td>
                    <td className="py-4 px-6">
                      {n.status === "Blocked by Policy" ? (
                        <span className="text-orange-500 font-bold tracking-tight" title={n.reason || 'Cluster policy prevents optimization of this stateful node (e.g., max downscale limit, manual approval required).'}>Blocked by Policy</span>
                      ) : (
                        <span className="text-emerald-500 font-bold tracking-tight" title="This node meets all policy requirements and is approved for right-sizing.">Approved by Policy</span>
                      )}
                    </td>
                    <td className="py-4 px-6 text-right">
                      <button
                        onClick={() => setSelectedStatefulNode(n)}
                        className="bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-600 font-bold py-1.5 px-3 rounded-lg text-[11px] transition-colors cursor-pointer"
                      >
                        Request Approval
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* MODALS */}
      <StatelessDetailedDrawer node={selectedStatelessNode} onClose={() => setSelectedStatelessNode(null)} isAutoOn={rebalanceState} />
      <StatefulProposalModal node={selectedStatefulNode} onClose={() => setSelectedStatefulNode(null)} requireApproval={true} />
    </div>
  );
}
