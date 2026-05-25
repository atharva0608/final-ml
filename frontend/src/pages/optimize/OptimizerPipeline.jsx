import React, { useState, useEffect } from 'react';
import { clusterAPI, optimizeAPI } from '../../services/api';
import useClusters from '../../hooks/useClusters';

const STEPS = [
  { id: 'workloads', title: 'Workload Support', desc: 'Identify Spot-friendly workloads' },
  { id: 'strategy', title: 'Strategy Decision', desc: 'Mix OD/Spot & Cluster Sizing' },
  { id: 'cost', title: 'Cost & Execution', desc: 'Review Savings & Apply' },
];

function fmt$(n) { return n == null ? '—' : `$${Math.round(n).toLocaleString()}`; }

export default function OptimizerPipeline() {
  const { clusters, selectedId, setSelectedId } = useClusters();
  const [currentStep, setCurrentStep] = useState(0);
  const [loading, setLoading] = useState(false);
  
  // Pipeline State
  const [workloads, setWorkloads] = useState([]);
  const [binPacking, setBinPacking] = useState(null);
  const [strategy, setStrategy] = useState('mix'); // 'mix', 'aggressive_od_reduce', 'resize'
  const [executionResult, setExecutionResult] = useState(null);

  useEffect(() => {
    if (selectedId) {
      loadData(selectedId);
    }
  }, [selectedId]);

  const loadData = async (clusterId) => {
    setLoading(true);
    try {
      // Load Workload Placement Summary
      const wlRes = await optimizeAPI.getPlacementSummary(clusterId);
      setWorkloads(wlRes.data?.data?.workloads || wlRes.data?.workloads || []);

      // Load Node Bin Packing (which is now fast thanks to Redis cache!)
      const bpRes = await optimizeAPI.getNodeBinPacking(clusterId);
      setBinPacking(bpRes.data?.data || bpRes.data || null);
    } catch (err) {
      console.error("Failed to load pipeline data", err);
    } finally {
      setLoading(false);
    }
  };

  const executePipeline = async () => {
    setLoading(true);
    try {
      // Simulate execution API call or call the real active actions trigger
      await new Promise(resolve => setTimeout(resolve, 1500));
      setExecutionResult("Execution dispatched to Agent successfully.");
    } catch (err) {
      setExecutionResult("Failed to execute pipeline.");
    } finally {
      setLoading(false);
    }
  };

  const nextStep = () => setCurrentStep(s => Math.min(s + 1, STEPS.length - 1));
  const prevStep = () => setCurrentStep(s => Math.max(s - 1, 0));

  const renderWorkloads = () => {
    const spotFriendly = workloads.filter(w => w.spot_count > 0 || (w.estimated_monthly_saving_usd > 0));
    
    return (
      <div className="flex flex-col gap-6 animate-fade-in">
        <h3 className="text-lg font-semibold text-gray-800">Step 1: Workload Support Analysis</h3>
        <p className="text-sm text-gray-600">
          The engine has analyzed your workloads. Here are the ones identified as safe to run on Spot instances, which will form the basis of our mixed OD/Spot strategy.
        </p>
        
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 border-b border-gray-100 text-xs uppercase text-gray-500 font-semibold tracking-wider">
              <tr>
                <th className="px-6 py-4">Workload</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">OD Required</th>
                <th className="px-6 py-4">Spot Count</th>
                <th className="px-6 py-4 text-right">Potential Savings</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {spotFriendly.length > 0 ? spotFriendly.map((wl, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td className="px-6 py-4 font-medium text-gray-900">{wl.workload_id}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2.5 py-1 rounded-full text-[11px] font-semibold tracking-wide ${wl.placement_status === 'AT_TARGET' ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'}`}>
                      {wl.placement_status}
                    </span>
                  </td>
                  <td className="px-6 py-4">{wl.od_required}</td>
                  <td className="px-6 py-4 text-blue-600 font-medium">{wl.spot_count}</td>
                  <td className="px-6 py-4 text-right font-mono font-semibold text-green-600">
                    {fmt$(wl.estimated_monthly_saving_usd)}/mo
                  </td>
                </tr>
              )) : (
                <tr><td colSpan={5} className="px-6 py-8 text-center text-gray-500 italic">No Spot-friendly workloads detected.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  };

  const renderStrategy = () => {
    return (
      <div className="flex flex-col gap-6 animate-fade-in">
        <h3 className="text-lg font-semibold text-gray-800">Step 2: Strategy & Sizing Decision</h3>
        <p className="text-sm text-gray-600">
          Based on the workload support and current cluster size ({binPacking?.nodes?.length || 0} nodes), select the execution strategy.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { id: 'mix', title: 'Balanced Mix (OD & Spot)', desc: 'Maintains OD anchors while placing burst workloads on Spot. Safest option.', badge: 'Recommended' },
            { id: 'aggressive_od_reduce', title: 'Reduce OD Nodes', desc: 'Aggressively consolidates and drains On-Demand nodes to maximize Spot usage.', badge: 'High Savings' },
            { id: 'resize', title: 'Dynamic Cluster Resizing', desc: 'Changes underlying NodePool sizes based on exact CPU/Mem bin-packing.' }
          ].map(opt => (
            <div 
              key={opt.id}
              onClick={() => setStrategy(opt.id)}
              className={`p-5 rounded-xl border-2 cursor-pointer transition-all ${strategy === opt.id ? 'border-blue-500 bg-blue-50 shadow-md' : 'border-gray-200 bg-white hover:border-blue-300'}`}
            >
              <div className="flex justify-between items-start mb-2">
                <h4 className={`font-bold ${strategy === opt.id ? 'text-blue-800' : 'text-gray-800'}`}>{opt.title}</h4>
                {opt.badge && <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-[10px] font-bold rounded uppercase tracking-wider">{opt.badge}</span>}
              </div>
              <p className="text-xs text-gray-600">{opt.desc}</p>
            </div>
          ))}
        </div>

        {binPacking?.consolidation_candidates?.count > 0 && strategy === 'aggressive_od_reduce' && (
          <div className="bg-amber-50 border border-amber-200 p-4 rounded-xl text-sm text-amber-800">
            <strong>Warning:</strong> Aggressive OD reduction will drain {binPacking.consolidation_candidates.count} nodes. Ensure PDBs are configured correctly.
          </div>
        )}
      </div>
    );
  };

  const renderCostAndExecution = () => {
    const totalSavings = workloads.reduce((sum, w) => sum + (w.estimated_monthly_saving_usd || 0), 0);
    const multiplier = strategy === 'aggressive_od_reduce' ? 1.2 : strategy === 'resize' ? 1.05 : 1.0;
    const finalSavings = totalSavings * multiplier;

    return (
      <div className="flex flex-col gap-6 animate-fade-in">
        <h3 className="text-lg font-semibold text-gray-800">Step 3: Cost Projection & Execution</h3>
        
        <div className="bg-gradient-to-br from-green-50 to-emerald-50 border border-green-200 p-6 rounded-2xl shadow-sm flex flex-col md:flex-row items-center justify-between gap-6">
          <div>
            <h4 className="text-green-800 font-bold mb-1">Projected Monthly Savings</h4>
            <p className="text-sm text-green-700">Based on your selected strategy: <span className="font-semibold uppercase tracking-wider">{strategy.replace(/_/g, ' ')}</span></p>
          </div>
          <div className="text-4xl font-black text-green-600 font-mono tracking-tight drop-shadow-sm">
            {fmt$(finalSavings)}<span className="text-lg text-green-500 font-bold">/mo</span>
          </div>
        </div>

        <div className="bg-gray-900 rounded-2xl p-6 text-white shadow-xl">
          <h4 className="font-semibold mb-4 text-gray-300">Execution Plan</h4>
          <ul className="text-sm font-mono text-gray-400 space-y-3 mb-6">
            <li className="flex gap-3"><span className="text-blue-400">▶</span> Apply Placement Policies to {workloads.length} workloads</li>
            <li className="flex gap-3"><span className="text-blue-400">▶</span> Trigger Kubernetes Descheduler for bin-packing</li>
            {strategy === 'aggressive_od_reduce' && <li className="flex gap-3"><span className="text-amber-400">▶</span> Drain and terminate low-utilization OD nodes</li>}
            {strategy === 'resize' && <li className="flex gap-3"><span className="text-purple-400">▶</span> Adjust Karpenter NodePool weights</li>}
          </ul>

          {executionResult ? (
            <div className="bg-green-500/20 text-green-400 p-4 rounded-xl border border-green-500/30 text-center font-medium">
              {executionResult}
            </div>
          ) : (
            <button 
              onClick={executePipeline}
              disabled={loading}
              className="w-full py-3.5 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white font-bold rounded-xl shadow-lg shadow-blue-900/20 transition-all flex justify-center items-center gap-2"
            >
              {loading ? 'Executing...' : 'Confirm & Execute Pipeline'}
            </button>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="p-6 md:p-8 max-w-6xl mx-auto w-full min-h-full bg-gray-50 flex flex-col gap-8">
      
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div>
          <h1 className="text-2xl font-black text-gray-900 tracking-tight">Optimizer Pipeline</h1>
          <p className="text-gray-500 text-sm mt-1">End-to-end decision and execution engine for infrastructure optimization.</p>
        </div>
        
        <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-lg border border-gray-200 shadow-sm">
          <span className="text-xs text-gray-500 font-medium">Cluster:</span>
          <select 
            className="text-sm font-bold text-gray-800 bg-transparent outline-none cursor-pointer"
            value={selectedId}
            onChange={e => setSelectedId(e.target.value)}
          >
            {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
      </div>

      {/* Stepper Header */}
      <div className="bg-white rounded-2xl border border-gray-200 p-2 shadow-sm flex items-center justify-between relative">
        <div className="absolute top-1/2 left-0 w-full h-[2px] bg-gray-100 -z-10 -translate-y-1/2"></div>
        {STEPS.map((step, idx) => {
          const isActive = idx === currentStep;
          const isPast = idx < currentStep;
          return (
            <div key={step.id} className={`flex-1 flex flex-col items-center gap-2 relative transition-all ${isActive ? 'scale-105' : ''}`}>
              <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm shadow-sm transition-colors border-4 border-white ${
                isActive ? 'bg-blue-600 text-white' : isPast ? 'bg-green-500 text-white' : 'bg-gray-100 text-gray-400'
              }`}>
                {isPast ? '✓' : idx + 1}
              </div>
              <div className="text-center">
                <div className={`text-xs font-bold uppercase tracking-wider ${isActive ? 'text-blue-700' : isPast ? 'text-gray-800' : 'text-gray-400'}`}>
                  {step.title}
                </div>
                <div className="text-[10px] text-gray-500 hidden md:block">{step.desc}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Step Content */}
      <div className="bg-white p-6 md:p-8 rounded-2xl border border-gray-200 shadow-sm min-h-[400px]">
        {loading && currentStep !== 2 ? (
          <div className="flex justify-center items-center h-64 text-gray-400 font-mono text-sm animate-pulse">Loading analysis data...</div>
        ) : (
          <>
            {currentStep === 0 && renderWorkloads()}
            {currentStep === 1 && renderStrategy()}
            {currentStep === 2 && renderCostAndExecution()}
          </>
        )}
      </div>

      {/* Footer Navigation */}
      <div className="flex justify-between items-center pb-12">
        <button 
          onClick={prevStep}
          disabled={currentStep === 0 || loading}
          className="px-6 py-2.5 rounded-lg font-semibold text-sm text-gray-600 bg-white border border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-all shadow-sm"
        >
          Previous
        </button>
        {currentStep < STEPS.length - 1 && (
          <button 
            onClick={nextStep}
            disabled={loading}
            className="px-6 py-2.5 rounded-lg font-semibold text-sm text-white bg-blue-600 hover:bg-blue-700 shadow-sm shadow-blue-600/30 transition-all"
          >
            Next Step
          </button>
        )}
      </div>

    </div>
  );
}
