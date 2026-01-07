/**
 * Policy Configuration Component
 */
import React, { useState, useEffect } from 'react';
import { policyAPI } from '../../services/api';
import { usePolicyStore, useClusterStore, useTemplateStore } from '../../store/useStore';
import { Card, Button, Input } from '../shared';
import { FiSave, FiToggleLeft, FiToggleRight, FiInfo, FiLayers, FiShield, FiZap, FiCalendar, FiServer } from 'react-icons/fi';
import toast from 'react-hot-toast';

const PolicyConfig = ({ clusterId }) => {
  const { policies, setPolicies, setLoading, loading } = usePolicyStore();
  const { clusters } = useClusterStore();
  const { templates } = useTemplateStore();

  const [activeTab, setActiveTab] = useState('provisioning');

  const [formData, setFormData] = useState({
    cluster_id: clusterId || '',
    template_id: '',
    is_active: true,
    // Provisioning
    spot_percentage: 70,
    spot_strategy: 'balanced', // lowest_price, capacity_optimized, balanced
    enable_fallback_to_on_demand: true,
    enable_diversification: true,
    // Constraints
    min_nodes: 2,
    max_nodes: 10,
    headroom_cpu_percent: 10,
    headroom_memory_percent: 10,
    allowed_instance_families: ['c5', 'm5', 'r5'],
    excluded_namespaces: ['kube-system', 'monitoring'],
    // Aggressiveness
    utilization_target_cpu: 70,
    utilization_target_memory: 80,
    bin_packing: 'balanced', // passive, balanced, aggressive
    min_node_lifetime_minutes: 55,
    // Scheduling
    optimization_schedule_type: 'always_on', // always_on, maintenance_window
    // Karpenter
    karpenter_settings: {
      consolidation_enabled: true,
      ttl_seconds_after_empty: 30,
      drift_enabled: true,
    }
  });

  const [existingPolicy, setExistingPolicy] = useState(null);

  useEffect(() => {
    if (clusterId) {
      fetchPolicyForCluster(clusterId);
    }
  }, [clusterId]);

  const fetchPolicyForCluster = async (clusterIdParam) => {
    setLoading(true);
    try {
      const response = await policyAPI.getByCluster(clusterIdParam);
      if (response.data.policy) {
        const policy = response.data.policy;
        setExistingPolicy(policy);
        setFormData({
          cluster_id: policy.cluster_id,
          template_id: policy.template_id || '',
          is_active: policy.is_active ?? true,

          spot_percentage: policy.config.spot_percentage || 70,
          spot_strategy: policy.config.spot_strategy || 'balanced',
          enable_fallback_to_on_demand: policy.config.enable_fallback_to_on_demand ?? true,
          enable_diversification: policy.config.enable_diversification ?? true,

          min_nodes: policy.config.min_nodes || 2,
          max_nodes: policy.config.max_nodes || 10,
          headroom_cpu_percent: policy.config.headroom_cpu_percent || 10,
          headroom_memory_percent: policy.config.headroom_memory_percent || 10,
          allowed_instance_families: policy.config.allowed_instance_families || ['c5', 'm5', 'r5'],
          excluded_namespaces: policy.config.excluded_namespaces || ['kube-system', 'monitoring'],

          utilization_target_cpu: policy.config.target_cpu_utilization || 70,
          utilization_target_memory: policy.config.target_memory_utilization || 80,
          bin_packing: policy.config.bin_packing || 'balanced',
          min_node_lifetime_minutes: policy.config.min_node_lifetime_minutes || 55,

          bin_packing: policy.config.bin_packing || 'balanced',
          min_node_lifetime_minutes: policy.config.min_node_lifetime_minutes || 55,

          optimization_schedule_type: policy.config.optimization_schedule_type || 'always_on',

          karpenter_settings: policy.config.karpenter_settings || {
            consolidation_enabled: true,
            ttl_seconds_after_empty: 30,
            drift_enabled: true,
          },
        });
      }
    } catch (error) {
      if (error.response?.status !== 404) {
        toast.error('Failed to load policy');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();

    // Validation
    if (formData.min_nodes < 0 || formData.max_nodes < formData.min_nodes) {
      toast.error('Invalid node range');
      return;
    }

    try {
      const policyPayload = {
        cluster_id: formData.cluster_id,
        template_id: formData.template_id || null,
        is_active: formData.is_active,
        config: {
          spot_percentage: formData.spot_percentage,
          spot_strategy: formData.spot_strategy,
          enable_fallback_to_on_demand: formData.enable_fallback_to_on_demand,
          enable_diversification: formData.enable_diversification,
          min_nodes: formData.min_nodes,
          max_nodes: formData.max_nodes,
          headroom_cpu_percent: formData.headroom_cpu_percent,
          headroom_memory_percent: formData.headroom_memory_percent,
          allowed_instance_families: formData.allowed_instance_families,
          excluded_namespaces: formData.excluded_namespaces,
          target_cpu_utilization: formData.utilization_target_cpu,
          target_memory_utilization: formData.utilization_target_memory,
          bin_packing: formData.bin_packing,
          min_node_lifetime_minutes: formData.min_node_lifetime_minutes,
          min_node_lifetime_minutes: formData.min_node_lifetime_minutes,
          optimization_schedule_type: formData.optimization_schedule_type,
          karpenter_settings: formData.karpenter_settings,
        }
      };

      if (existingPolicy) {
        await policyAPI.update(existingPolicy.id, policyPayload);
        toast.success('Policy updated successfully');
      } else {
        await policyAPI.create(policyPayload);
        toast.success('Policy created successfully');
      }

      fetchPolicyForCluster(formData.cluster_id);
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to save policy');
    }
  };

  const handleToggleActive = async () => {
    if (!existingPolicy) {
      toast.error('Please save the policy first');
      return;
    }

    try {
      await policyAPI.toggle(existingPolicy.id);
      toast.success(`Policy ${existingPolicy.is_active ? 'deactivated' : 'activated'}`);
      fetchPolicyForCluster(formData.cluster_id);
    } catch (error) {
      toast.error('Failed to toggle policy');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const tabs = [
    { id: 'provisioning', label: 'Provisioning', icon: FiLayers },
    { id: 'karpenter', label: 'Karpenter', icon: FiServer },
    { id: 'constraints', label: 'Constraints', icon: FiShield },
    { id: 'aggressiveness', label: 'Aggressiveness', icon: FiZap },
    { id: 'scheduling', label: 'Scheduling', icon: FiCalendar },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Optimization Policy</h1>
          <p className="text-gray-600 mt-1">Configure automation rules and constraints</p>
        </div>
        {existingPolicy && (
          <Button
            variant={existingPolicy.is_active ? 'primary' : 'secondary'}
            icon={existingPolicy.is_active ? <FiToggleRight /> : <FiToggleLeft />}
            onClick={handleToggleActive}
          >
            {existingPolicy.is_active ? 'Active' : 'Inactive'}
          </Button>
        )}
      </div>

      <form onSubmit={handleSave}>
        <div className="flex gap-6">
          {/* Sidebar Tabs */}
          <div className="w-64 flex-shrink-0">
            <Card className="p-2 space-y-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors ${activeTab === tab.id
                    ? 'bg-blue-50 text-blue-700'
                    : 'text-gray-600 hover:bg-gray-50'
                    }`}
                >
                  <tab.icon className="w-5 h-5 mr-3" />
                  {tab.label}
                </button>
              ))}
            </Card>

            {/* Cluster Selector (if not pre-selected) */}
            {!clusterId && (
              <Card className="mt-4 p-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">Target Cluster</label>
                <select
                  value={formData.cluster_id}
                  onChange={(e) => {
                    setFormData({ ...formData, cluster_id: e.target.value });
                    if (e.target.value) fetchPolicyForCluster(e.target.value);
                  }}
                  className="w-full form-select rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                >
                  <option value="">Select Cluster</option>
                  {clusters.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Card>
            )}
          </div>

          {/* Tab Content */}
          <div className="flex-1">
            <Card className="p-6">
              {activeTab === 'provisioning' && (
                <div className="space-y-6">
                  <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Provisioning Strategy</h3>

                  {/* Spot Percentage */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Spot / On-Demand Ratio: {formData.spot_percentage}% Spot
                    </label>
                    <input
                      type="range" min="0" max="100" step="10"
                      value={formData.spot_percentage}
                      onChange={(e) => setFormData({ ...formData, spot_percentage: parseInt(e.target.value) })}
                      className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                    />
                    <div className="flex justify-between text-xs text-gray-500 mt-1">
                      <span>All On-Demand</span>
                      <span>Balanced</span>
                      <span>All Spot</span>
                    </div>
                  </div>

                  {/* Spot Strategy */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Spot Selection Strategy</label>
                    <div className="space-y-2">
                      {['lowest_price', 'capacity_optimized', 'balanced'].map(strategy => (
                        <label key={strategy} className="flex items-center">
                          <input
                            type="radio"
                            name="spot_strategy"
                            value={strategy}
                            checked={formData.spot_strategy === strategy}
                            onChange={() => setFormData({ ...formData, spot_strategy: strategy })}
                            className="focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300"
                          />
                          <span className="ml-2 text-sm text-gray-700 capitalize">
                            {strategy.replace('_', ' ')}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Fallback */}
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">On-Demand Fallback</h4>
                      <p className="text-xs text-gray-500">Launch On-Demand if Spot capacity is unavailable</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({ ...formData, enable_fallback_to_on_demand: !formData.enable_fallback_to_on_demand })}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${formData.enable_fallback_to_on_demand ? 'bg-blue-600' : 'bg-gray-300'}`}
                    >
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${formData.enable_fallback_to_on_demand ? 'translate-x-6' : 'translate-x-1'}`} />
                    </button>
                  </div>
                </div>
              )}

              {activeTab === 'karpenter' && (
                <div className="space-y-6">
                  <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Karpenter Configuration</h3>

                  {/* Consolidation */}
                  <div className="flex items-center justify-between p-4 bg-blue-50 rounded-lg border border-blue-100">
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">Aggressive Consolidation</h4>
                      <p className="text-xs text-gray-500">Actively move pods to cheaper nodes and delete empty nodes (consolidation: true).</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({
                        ...formData,
                        karpenter_settings: {
                          ...formData.karpenter_settings,
                          consolidation_enabled: !formData.karpenter_settings?.consolidation_enabled
                        }
                      })}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${formData.karpenter_settings?.consolidation_enabled ? 'bg-blue-600' : 'bg-gray-300'}`}
                    >
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${formData.karpenter_settings?.consolidation_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                    </button>
                  </div>

                  {/* TTL */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Time-to-Live (TTL) for Empty Nodes</label>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        value={formData.karpenter_settings?.ttl_seconds_after_empty ?? 30}
                        onChange={(e) => setFormData({
                          ...formData,
                          karpenter_settings: {
                            ...formData.karpenter_settings,
                            ttl_seconds_after_empty: parseInt(e.target.value)
                          }
                        })}
                        className="w-32"
                      />
                      <span className="text-gray-500">seconds</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">How long to wait before deleting a node that has no pods.</p>
                  </div>

                  {/* Drift */}
                  <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                    <div>
                      <h4 className="text-sm font-medium text-gray-900">Drift Detection</h4>
                      <p className="text-xs text-gray-500">Replace nodes that have drifted from their provisioner specification.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => setFormData({
                        ...formData,
                        karpenter_settings: {
                          ...formData.karpenter_settings,
                          drift_enabled: !formData.karpenter_settings?.drift_enabled
                        }
                      })}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${formData.karpenter_settings?.drift_enabled ? 'bg-blue-600' : 'bg-gray-300'}`}
                    >
                      <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${formData.karpenter_settings?.drift_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
                    </button>
                  </div>
                </div>
              )}

              {activeTab === 'constraints' && (
                <div className="space-y-6">
                  <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Workload Constraints</h3>

                  {/* Headroom */}
                  <div className="grid grid-cols-2 gap-4">
                    <Input
                      label="CPU Headroom (%)"
                      type="number"
                      value={formData.headroom_cpu_percent}
                      onChange={(e) => setFormData({ ...formData, headroom_cpu_percent: parseInt(e.target.value) })}
                      min="0" max="100"
                    />
                    <Input
                      label="Memory Headroom (%)"
                      type="number"
                      value={formData.headroom_memory_percent}
                      onChange={(e) => setFormData({ ...formData, headroom_memory_percent: parseInt(e.target.value) })}
                      min="0" max="100"
                    />
                  </div>

                  {/* Node Limits */}
                  <div className="grid grid-cols-2 gap-4">
                    <Input
                      label="Min Nodes"
                      type="number"
                      value={formData.min_nodes}
                      onChange={(e) => setFormData({ ...formData, min_nodes: parseInt(e.target.value) })}
                      min="0"
                    />
                    <Input
                      label="Max Nodes"
                      type="number"
                      value={formData.max_nodes}
                      onChange={(e) => setFormData({ ...formData, max_nodes: parseInt(e.target.value) })}
                      min="1"
                    />
                  </div>

                  {/* Exclusions */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Excluded Namespaces</label>
                    <div className="p-3 bg-gray-50 border rounded-lg text-sm text-gray-600">
                      {formData.excluded_namespaces.join(', ')}
                      {/* Placeholder for tag input */}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'aggressiveness' && (
                <div className="space-y-6">
                  <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Aggressiveness Settings</h3>

                  {/* Bin Packing Intensity */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Bin Packing Intensity</label>
                    <div className="grid grid-cols-3 gap-3">
                      {['passive', 'balanced', 'aggressive'].map(level => (
                        <button
                          key={level}
                          type="button"
                          onClick={() => setFormData({ ...formData, bin_packing: level })}
                          className={`p-3 border rounded-lg text-center capitalize text-sm font-medium ${formData.bin_packing === level
                            ? 'border-blue-500 bg-blue-50 text-blue-700'
                            : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                            }`}
                        >
                          {level}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Node Lifetime */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Minimum Node Lifetime</label>
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        value={formData.min_node_lifetime_minutes}
                        onChange={(e) => setFormData({ ...formData, min_node_lifetime_minutes: parseInt(e.target.value) })}
                        className="w-32"
                      />
                      <span className="text-gray-500">minutes</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">Prevent node termination if running for less than this time.</p>
                  </div>

                  {/* Optimization Targets */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Target CPU %</label>
                      <input
                        type="range" min="50" max="100"
                        value={formData.utilization_target_cpu}
                        onChange={(e) => setFormData({ ...formData, utilization_target_cpu: parseInt(e.target.value) })}
                        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-orange-500"
                      />
                      <div className="text-right text-xs font-medium text-gray-600">{formData.utilization_target_cpu}%</div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Target Memory %</label>
                      <input
                        type="range" min="50" max="100"
                        value={formData.utilization_target_memory}
                        onChange={(e) => setFormData({ ...formData, utilization_target_memory: parseInt(e.target.value) })}
                        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-orange-500"
                      />
                      <div className="text-right text-xs font-medium text-gray-600">{formData.utilization_target_memory}%</div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'scheduling' && (
                <div className="space-y-6">
                  <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Optimization Schedule</h3>

                  <div className="space-y-4">
                    <label className="flex items-center p-4 border rounded-lg cursor-pointer hover:bg-gray-50">
                      <input
                        type="radio"
                        name="schedule_type"
                        value="always_on"
                        checked={formData.optimization_schedule_type === 'always_on'}
                        onChange={() => setFormData({ ...formData, optimization_schedule_type: 'always_on' })}
                        className="h-4 w-4 text-blue-600 focus:ring-blue-500"
                      />
                      <div className="ml-3">
                        <span className="block text-sm font-medium text-gray-900">Always On (Continuous)</span>
                        <span className="block text-sm text-gray-500">Optimize cluster 24/7 whenever opportunities are found.</span>
                      </div>
                    </label>

                    <label className="flex items-center p-4 border rounded-lg cursor-pointer hover:bg-gray-50">
                      <input
                        type="radio"
                        name="schedule_type"
                        value="maintenance_window"
                        checked={formData.optimization_schedule_type === 'maintenance_window'}
                        onChange={() => setFormData({ ...formData, optimization_schedule_type: 'maintenance_window' })}
                        className="h-4 w-4 text-blue-600 focus:ring-blue-500"
                      />
                      <div className="ml-3">
                        <span className="block text-sm font-medium text-gray-900">Maintenance Windows Only</span>
                        <span className="block text-sm text-gray-500">Restrict disruptive actions to specific time windows.</span>
                      </div>
                    </label>
                  </div>
                </div>
              )}

              {/* Action Bar */}
              <div className="mt-8 pt-4 border-t flex justify-end">
                <Button type="submit" variant="primary" icon={<FiSave />} size="lg">
                  {existingPolicy ? 'Update Configuration' : 'Create Configuration'}
                </Button>
              </div>
            </Card>
          </div>
        </div>
      </form>
    </div>
  );
};

export default PolicyConfig;
