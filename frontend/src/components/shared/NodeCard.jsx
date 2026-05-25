import React from 'react';
import { FiTool } from 'react-icons/fi';

const STEP_ORDER = [
  'step_1_spot_provisioning',
  'step_4_new_node_joined',
  'step_2_cordon',
  'step_3_draining_pods',
  'step_7_pods_rescheduled',
  'step_5_old_node_terminated',
  'step_6_optimization_complete',
];

const STEP_LABELS = {
  step_1_spot_provisioning:     'NodePool Updated',
  step_4_new_node_joined:       'Node Joined',
  step_2_cordon:                'Cordoned',
  step_3_draining_pods:         'Pods Drained',
  step_7_pods_rescheduled:      'Rescheduled',
  step_5_old_node_terminated:   'Terminated',
  step_6_optimization_complete: 'Complete',
};

/** Returns completion percentage for a rebalancing action based on its step flags.
 *  Step values are ISO timestamp strings (truthy = done) on the action object directly. */
export const getRebalancingProgress = (action) => {
  const done = STEP_ORDER.filter(k => Boolean(action[k])).length;
  return Math.round((done / STEP_ORDER.length) * 100);
};

/** Returns the label of the current (first incomplete) rebalancing step. */
export const getCurrentRebalancingStep = (action) => {
  const pending = STEP_ORDER.find(k => !action[k]);
  return pending ? (STEP_LABELS[pending] || pending.replace(/_/g, ' ')) : 'Complete';
};

/**
 * Card for a rebalancing action that is BLOCKED.
 * Shows error type, reason, and pod eviction progress if available.
 */
export const BlockedNodeCard = ({ action }) => {
  const nodeId    = action.node_id || action.target_node || action.action_id || '—';
  const errorType = action.error_type || action.block_type || action.block_reason || 'Blocked';
  const errorMsg  = action.error_message || action.block_detail || action.reason
    || 'Unable to proceed with eviction.';
  const podsEvicted = action.pods_evicted ?? action.evicted_pods ?? null;
  const podsTotal   = action.pods_total   ?? action.total_pods   ?? null;

  return (
    <div className="bg-white rounded-lg border border-red-200 p-5 flex flex-col gap-3">
      <div className="flex justify-between items-start">
        <div>
          <p className="text-base font-bold text-gray-900">{nodeId}</p>
          <span className="text-xs font-bold uppercase tracking-wider text-red-600">
            {String(errorType).replace(/_/g, ' ')}
          </span>
        </div>
        <button className="text-indigo-600 hover:text-indigo-800 transition-colors" title="Diagnose">
          <FiTool className="w-4 h-4" />
        </button>
      </div>
      <p className="text-sm text-gray-500 leading-relaxed">{errorMsg}</p>
      {podsEvicted !== null && podsTotal !== null && (
        <div className="flex items-center justify-between pt-2 mt-auto border-t border-gray-100">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Pods</span>
          <span className="text-sm font-medium text-gray-700">{podsEvicted}/{podsTotal} evicted</span>
        </div>
      )}
    </div>
  );
};

/**
 * Card for a rebalancing action that is RUNNING or PENDING.
 * Shows step progress bar, current step label, and pod eviction progress if available.
 */
export const RunningNodeCard = ({ action }) => {
  const progress  = getRebalancingProgress(action);
  const stepLabel = getCurrentRebalancingStep(action);
  const nodeId    = action.node_id || action.target_node || action.action_id || '—';
  const podsEvicted = action.pods_evicted ?? action.evicted_pods ?? null;
  const podsTotal   = action.pods_total   ?? action.total_pods   ?? null;

  return (
    <div className="bg-white rounded-lg border border-gray-200 hover:border-indigo-200 p-5 flex flex-col gap-3 cursor-pointer transition-colors relative overflow-hidden">
      <div className="absolute inset-0 bg-indigo-500/[0.03] pointer-events-none" />
      <div className="flex justify-between items-center relative z-10">
        <span className="text-base font-bold text-gray-900">{nodeId}</span>
        <span className="text-xs font-bold uppercase tracking-wider text-indigo-500">{stepLabel}</span>
      </div>
      <div className="flex flex-col gap-1.5 relative z-10">
        <div className="flex justify-between text-sm">
          <span className="text-gray-500">Progress</span>
          <span className="font-medium text-gray-700">{progress}%</span>
        </div>
        <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full bg-indigo-500 rounded-full transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>
      {podsEvicted !== null && podsTotal !== null && (
        <div className="flex items-center justify-between pt-2 mt-auto border-t border-gray-100 relative z-10">
          <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">Pods</span>
          <span className="text-sm font-medium text-gray-700">{podsEvicted}/{podsTotal} evicted</span>
        </div>
      )}
    </div>
  );
};
