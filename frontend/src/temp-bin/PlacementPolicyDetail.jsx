import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { usePlacementPolicyDetail } from '../../hooks/usePlacementPolicies';
import { Card, Badge, Button, EmptyState } from '../shared';
import { 
  ArrowLeft, 
  Server, 
  Activity, 
  Network, 
  ShieldCheck, 
  RefreshCw,
  GitPullRequest
} from 'lucide-react';
import { formatCurrency, formatPercentage } from '../../utils/formatters';

const PlacementPolicyDetail = ({ clusterId: propClusterId }) => {
  const { clusterId: paramClusterId, workloadId } = useParams();
  const clusterId = propClusterId || paramClusterId;
  const navigate = useNavigate();

  // Handle URL encoding if workloadId is passed in URL
  const decodedWorkloadId = workloadId ? decodeURIComponent(workloadId) : null;
  const { policy, loading, error, refresh } = usePlacementPolicyDetail(clusterId, decodedWorkloadId);

  if (loading && !policy) {
    return <div className="p-8 flex justify-center"><RefreshCw className="w-8 h-8 animate-spin text-gray-400" /></div>;
  }

  if (error || (!loading && !policy)) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate(-1)}><ArrowLeft className="w-4 h-4 mr-2" /> Back</Button>
        <EmptyState 
          icon={Server} 
          title="Policy not found" 
          description={error || "Could not load details for this placement policy."}
        />
      </div>
    );
  }

  const getTierColor = (tier) => {
    switch(tier) {
      case 'Platinum': return 'purple';
      case 'Gold': return 'yellow';
      case 'Silver': return 'gray';
      case 'Bronze': return 'amber';
      default: return 'gray';
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Button variant="ghost" onClick={() => navigate(-1)} className="text-gray-400 hover:text-white">
          <ArrowLeft className="w-4 h-4 mr-2" /> Back to Dashboard
        </Button>
        <Button variant="secondary" onClick={refresh} isLoading={loading}>
          <RefreshCw className="w-4 h-4 mr-2" /> Refresh
        </Button>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
        <div className="flex justify-between items-start">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-white">{policy.name}</h1>
              <Badge variant={getTierColor(policy.criticality_tier)}>{policy.criticality_tier}</Badge>
              {policy.actionable ? (
                <Badge variant="success">Actionable</Badge>
              ) : (
                <Badge variant="gray">Not Actionable</Badge>
              )}
            </div>
            <p className="text-gray-400 font-mono text-sm">{policy.namespace} • {policy.workload_id}</p>
          </div>
          <div className="text-right">
            <p className="text-sm text-gray-400 mb-1">Est. Savings</p>
            <p className="text-2xl font-bold text-green-400">
              {formatCurrency(policy.estimated_monthly_saving_usd)} <span className="text-sm font-normal">/mo</span>
            </p>
            <p className="text-sm text-green-500">{formatPercentage(policy.estimated_savings_pct)}</p>
          </div>
        </div>

        {policy.schema_warning && (
          <div className="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/50 rounded-lg flex items-start gap-2">
            <Activity className="w-5 h-5 text-yellow-500 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-yellow-200">
              This policy was generated using an older schema version ({policy.schema_version}). 
              Some fields may be unavailable until the next advisor cycle.
            </p>
          </div>
        )}
        
        {(!policy.actionable && policy.actionable_blocked_reason) && (
          <div className="mt-4 p-3 bg-gray-800 border border-gray-700 rounded-lg flex items-start gap-2">
            <ShieldCheck className="w-5 h-5 text-gray-400 flex-shrink-0 mt-0.5" />
            <p className="text-sm text-gray-300">
              <span className="font-semibold text-white">Actionability Blocked: </span>
              {policy.actionable_blocked_reason}
            </p>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="bg-gray-900 border-gray-800 p-6">
          <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
            <Server className="w-5 h-5 text-blue-400" /> Allocation Targets
          </h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center py-2 border-b border-gray-800">
              <span className="text-gray-400">Total Observed Replicas</span>
              <span className="text-white font-mono">{policy.observed_replicas}</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-gray-800">
              <span className="text-gray-400">On-Demand Target (Floor)</span>
              <span className="text-blue-400 font-mono font-medium">{policy.ondemand_target}</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-gray-800">
              <span className="text-gray-400">Spot Target (Burst)</span>
              <span className="text-purple-400 font-mono font-medium">
                {policy.spot_target}
                {policy.spot_target < policy.spot_target_raw && (
                  <span className="text-xs text-gray-500 ml-2" title={`Capped from ${policy.spot_target_raw}`}>
                    (Raw: {policy.spot_target_raw})
                  </span>
                )}
              </span>
            </div>
            <div className="flex justify-between items-center py-2">
              <span className="text-gray-400">Target NodePool</span>
              <Badge variant="outline" className="font-mono">{policy.assigned_nodepool_class}</Badge>
            </div>
            {policy.keda_min_replicas !== null && (
              <div className="flex justify-between items-center py-2 border-t border-gray-800 mt-2">
                <span className="text-gray-400">KEDA Integration</span>
                <span className="text-white text-sm">
                  min: {policy.keda_min_replicas} / max: {policy.keda_max_replicas || '∞'}
                </span>
              </div>
            )}
          </div>
        </Card>

        <Card className="bg-gray-900 border-gray-800 p-6">
          <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-green-400" /> Constraints & Health
          </h3>
          <div className="space-y-4">
            <div className="flex justify-between items-center py-2 border-b border-gray-800">
              <span className="text-gray-400">Confidence State</span>
              <span className={`font-medium ${policy.confidence_state === 'CONFIRMED' ? 'text-green-400' : 'text-yellow-400'}`}>
                {policy.confidence_state}
              </span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-gray-800">
              <span className="text-gray-400">Spot Friendly</span>
              <span className="text-white">{policy.spot_friendly ? 'Yes' : 'No'}</span>
            </div>
            <div className="flex justify-between items-center py-2 border-b border-gray-800">
              <span className="text-gray-400 flex items-center gap-2">
                Traffic Skew Detection
                {policy.traffic_skew_detected && <Badge variant="warning">Detected</Badge>}
              </span>
              <span className="text-white text-sm">
                {policy.skew_signal_source ? `Source: ${policy.skew_signal_source}` : 'Normal'}
              </span>
            </div>
            <div className="flex justify-between items-center py-2">
              <span className="text-gray-400">Rollout Status</span>
              <span className="text-white flex items-center gap-2">
                {policy.rollout_eligible ? (
                  <Badge variant="success">Eligible</Badge>
                ) : (
                  <Badge variant="gray">Not Eligible</Badge>
                )}
                {!policy.rollout_eligible && policy.rollout_blocked_reason && (
                  <span className="text-xs text-gray-500 ml-1">({policy.rollout_blocked_reason})</span>
                )}
              </span>
            </div>
            <div className="flex justify-between items-center py-2 border-t border-gray-800">
              <span className="text-gray-400">Spread Tier</span>
              <span className="text-white font-mono">T{policy.spread_relaxation_tier}</span>
            </div>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card className="bg-gray-900 border-gray-800 p-6 flex flex-col h-full">
          <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
            <Network className="w-5 h-5 text-yellow-400" /> Selected Instance Families
          </h3>
          <div className="flex flex-wrap gap-2 mb-4">
            {policy.spot_instance_families?.map((family) => (
              <Badge key={family} variant="secondary" className="font-mono">
                {family}
              </Badge>
            ))}
            {(!policy.spot_instance_families || policy.spot_instance_families.length === 0) && (
              <span className="text-gray-500 italic text-sm">No specific families</span>
            )}
          </div>
          <div className="mt-2 pt-4 border-t border-gray-800">
             <h4 className="text-sm font-medium text-gray-400 mb-2">Instance Types</h4>
             <div className="flex flex-wrap gap-1 max-h-32 overflow-y-auto pr-2 custom-scrollbar">
               {policy.spot_instance_types?.map((type) => (
                 <span key={type} className="text-xs bg-gray-800 text-gray-300 px-2 py-1 rounded">
                   {type}
                 </span>
               ))}
               {(!policy.spot_instance_types || policy.spot_instance_types.length === 0) && (
                 <span className="text-gray-500 italic text-sm">No types discovered</span>
               )}
             </div>
          </div>
        </Card>

        <Card className="bg-gray-900 border-gray-800 p-6 flex flex-col h-full">
          <h3 className="text-lg font-medium text-white mb-4 flex items-center gap-2">
            <GitPullRequest className="w-5 h-5 text-pink-400" /> Signals Audit Trail
          </h3>
          <div className="space-y-2 max-h-48 overflow-y-auto pr-2 custom-scrollbar">
            {policy.signals_used?.map((signal, i) => (
              <div key={i} className="flex items-start gap-2 bg-gray-800/50 p-2 rounded">
                <div className="w-1.5 h-1.5 rounded-full bg-blue-500 mt-2 flex-shrink-0" />
                <span className="text-sm text-gray-300 font-mono">{signal}</span>
              </div>
            ))}
            {(!policy.signals_used || policy.signals_used.length === 0) && (
              <div className="text-gray-500 text-sm italic">No signals recorded</div>
            )}
          </div>
        </Card>
      </div>

      <Card className="bg-gray-900 border-gray-800 p-6">
        <h3 className="text-lg font-medium text-white mb-4">Affinity & Topology Preview</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <h4 className="text-sm font-medium text-blue-400 mb-2 flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-blue-400"/> Baseline Affinity (Floor)
            </h4>
            <pre className="bg-gray-950 p-4 rounded-lg overflow-x-auto text-xs text-gray-300 border border-gray-800 max-h-64 custom-scrollbar">
              {JSON.stringify(policy.baseline_affinity, null, 2)}
            </pre>
          </div>
          <div>
            <h4 className="text-sm font-medium text-purple-400 mb-2 flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-purple-400"/> Burst Affinity (Spot)
            </h4>
            <pre className="bg-gray-950 p-4 rounded-lg overflow-x-auto text-xs text-gray-300 border border-gray-800 max-h-64 custom-scrollbar">
              {JSON.stringify(policy.burst_affinity, null, 2)}
            </pre>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default PlacementPolicyDetail;
