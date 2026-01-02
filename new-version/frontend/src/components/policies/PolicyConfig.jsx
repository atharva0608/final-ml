/**
 * Policy Configuration Component
 */
import React, { useState, useEffect } from 'react';
import { policyAPI } from '../../services/api';
import { usePolicyStore, useClusterStore, useTemplateStore } from '../../store/useStore';
import { Card, Button, Input } from '../shared';
import { FiSave, FiToggleLeft, FiToggleRight, FiInfo } from 'react-icons/fi';
import toast from 'react-hot-toast';

const PolicyConfig = ({ clusterId }) => {
  const { policies, setPolicies, setLoading, loading } = usePolicyStore();
  const { clusters } = useClusterStore();
  const { templates } = useTemplateStore();

  const [formData, setFormData] = useState({
    cluster_id: clusterId || '',
    spot_percentage: 70,
    min_nodes: 2,
    max_nodes: 10,
    target_cpu_utilization: 70,
    target_memory_utilization: 80,
    enable_fallback_to_on_demand: true,
    enable_diversification: true,
    template_id: '',
    is_active: true,
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
        setExistingPolicy(response.data.policy);
        setFormData({
          cluster_id: response.data.policy.cluster_id,
          spot_percentage: response.data.policy.config.spot_percentage || 70,
          min_nodes: response.data.policy.config.min_nodes || 2,
          max_nodes: response.data.policy.config.max_nodes || 10,
          target_cpu_utilization: response.data.policy.config.target_cpu_utilization || 70,
          target_memory_utilization: response.data.policy.config.target_memory_utilization || 80,
          enable_fallback_to_on_demand: response.data.policy.config.enable_fallback_to_on_demand ?? true,
          enable_diversification: response.data.policy.config.enable_diversification ?? true,
          template_id: response.data.policy.template_id || '',
          is_active: response.data.policy.is_active ?? true,
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
    if (formData.spot_percentage < 0 || formData.spot_percentage > 100) {
      toast.error('Spot percentage must be between 0 and 100');
      return;
    }

    if (formData.min_nodes < 0) {
      toast.error('Min nodes cannot be negative');
      return;
    }

    if (formData.max_nodes < formData.min_nodes) {
      toast.error('Max nodes must be greater than or equal to min nodes');
      return;
    }

    if (formData.target_cpu_utilization < 1 || formData.target_cpu_utilization > 100) {
      toast.error('CPU utilization must be between 1 and 100');
      return;
    }

    if (formData.target_memory_utilization < 1 || formData.target_memory_utilization > 100) {
      toast.error('Memory utilization must be between 1 and 100');
      return;
    }

    try {
      const policyPayload = {
        cluster_id: formData.cluster_id,
        template_id: formData.template_id || null,
        config: {
          spot_percentage: formData.spot_percentage,
          min_nodes: formData.min_nodes,
          max_nodes: formData.max_nodes,
          target_cpu_utilization: formData.target_cpu_utilization,
          target_memory_utilization: formData.target_memory_utilization,
          enable_fallback_to_on_demand: formData.enable_fallback_to_on_demand,
          enable_diversification: formData.enable_diversification,
        },
        is_active: formData.is_active,
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Optimization Policy</h1>
          <p className="text-gray-600 mt-1">Configure instance optimization preferences</p>
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
        <Card>
          <div className="space-y-6">
            {/* Cluster Selection */}
            {!clusterId && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Cluster
                </label>
                <select
                  value={formData.cluster_id}
                  onChange={(e) => {
                    setFormData({ ...formData, cluster_id: e.target.value });
                    if (e.target.value) {
                      fetchPolicyForCluster(e.target.value);
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                >
                  <option value="">Select a cluster</option>
                  {clusters.map((cluster) => (
                    <option key={cluster.id} value={cluster.id}>
                      {cluster.name} - {cluster.region}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Template Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Node Template (Optional)
              </label>
              <select
                value={formData.template_id}
                onChange={(e) => setFormData({ ...formData, template_id: e.target.value })}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Use default template</option>
                {templates.map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
              </select>
            </div>

            {/* Spot Percentage Slider */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Spot Instance Target: {formData.spot_percentage}%
              </label>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={formData.spot_percentage}
                onChange={(e) => setFormData({ ...formData, spot_percentage: parseInt(e.target.value) })}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>0% (All On-Demand)</span>
                <span>50% (Balanced)</span>
                <span>100% (All Spot)</span>
              </div>
            </div>

            {/* Node Count Range */}
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Min Nodes"
                type="number"
                value={formData.min_nodes}
                onChange={(e) => setFormData({ ...formData, min_nodes: parseInt(e.target.value) })}
                min="0"
                max="100"
                required
              />
              <Input
                label="Max Nodes"
                type="number"
                value={formData.max_nodes}
                onChange={(e) => setFormData({ ...formData, max_nodes: parseInt(e.target.value) })}
                min="1"
                max="1000"
                required
              />
            </div>

            {/* Target Utilization */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Target CPU: {formData.target_cpu_utilization}%
                </label>
                <input
                  type="range"
                  min="10"
                  max="100"
                  step="5"
                  value={formData.target_cpu_utilization}
                  onChange={(e) => setFormData({ ...formData, target_cpu_utilization: parseInt(e.target.value) })}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Target Memory: {formData.target_memory_utilization}%
                </label>
                <input
                  type="range"
                  min="10"
                  max="100"
                  step="5"
                  value={formData.target_memory_utilization}
                  onChange={(e) => setFormData({ ...formData, target_memory_utilization: parseInt(e.target.value) })}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                />
              </div>
            </div>

            {/* Toggle Options */}
            <div className="space-y-3">
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-start">
                  <FiInfo className="w-5 h-5 text-blue-600 mr-2 mt-0.5" />
                  <div>
                    <h4 className="text-sm font-medium text-gray-900">Fallback to On-Demand</h4>
                    <p className="text-xs text-gray-600 mt-0.5">
                      Launch on-demand instances when spot capacity is unavailable
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setFormData({ ...formData, enable_fallback_to_on_demand: !formData.enable_fallback_to_on_demand })
                  }
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    formData.enable_fallback_to_on_demand ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      formData.enable_fallback_to_on_demand ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-start">
                  <FiInfo className="w-5 h-5 text-blue-600 mr-2 mt-0.5" />
                  <div>
                    <h4 className="text-sm font-medium text-gray-900">Instance Diversification</h4>
                    <p className="text-xs text-gray-600 mt-0.5">
                      Spread instances across multiple families and AZs
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() =>
                    setFormData({ ...formData, enable_diversification: !formData.enable_diversification })
                  }
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    formData.enable_diversification ? 'bg-blue-600' : 'bg-gray-300'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      formData.enable_diversification ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
            </div>

            {/* Save Button */}
            <div className="flex justify-end pt-4 border-t">
              <Button type="submit" variant="primary" icon={<FiSave />}>
                {existingPolicy ? 'Update Policy' : 'Create Policy'}
              </Button>
            </div>
          </div>
        </Card>
      </form>

      {/* Info Card */}
      <Card>
        <div className="flex items-start">
          <FiInfo className="w-5 h-5 text-blue-600 mr-3 mt-0.5" />
          <div className="text-sm text-gray-600">
            <h4 className="font-medium text-gray-900 mb-2">Policy Behavior</h4>
            <ul className="list-disc list-inside space-y-1">
              <li>Policies are applied to all nodes in the selected cluster</li>
              <li>Changes take effect within 5 minutes via agent synchronization</li>
              <li>Spot percentage is a target - actual ratio may vary based on availability</li>
              <li>Node count auto-scales based on CPU/memory utilization targets</li>
              <li>Only one policy can be active per cluster at a time</li>
            </ul>
          </div>
        </div>
      </Card>
    </div>
  );
};

export default PolicyConfig;
