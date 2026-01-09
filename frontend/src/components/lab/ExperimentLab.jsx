/**
 * Experiment Lab Component
 * A/B testing and ML model comparison interface
 */
import React, { useState, useEffect } from 'react';
import { labAPI } from '../../services/api';
import { Card, Button, Input, Badge } from '../shared';
import {
  FiPlus,
  FiPlay,
  FiSquare,
  FiTrendingUp,
  FiCheckCircle,
  FiAlertCircle,
  FiClock,
  FiBarChart2,
} from 'react-icons/fi';
import toast from 'react-hot-toast';
import { formatCurrency, formatNumber, formatDate, formatDateTime } from '../../utils/formatters';

const ExperimentLab = () => {
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedExperiment, setSelectedExperiment] = useState(null);
  const [showResultsModal, setShowResultsModal] = useState(false);
  const [results, setResults] = useState(null);

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    control_model_id: '',
    variant_model_id: '',
    control_percentage: 50,
    variant_percentage: 50,
    target_metric: 'cost_savings',
    duration_hours: 24,
  });

  const TARGET_METRICS = [
    { value: 'cost_savings', label: 'Cost Savings' },
    { value: 'instance_stability', label: 'Instance Stability' },
    { value: 'spot_success_rate', label: 'Spot Success Rate' },
    { value: 'cpu_utilization', label: 'CPU Utilization' },
    { value: 'memory_utilization', label: 'Memory Utilization' },
  ];

  useEffect(() => {
    fetchExperiments();
  }, []);

  const fetchExperiments = async () => {
    setLoading(true);
    try {
      const response = await labAPI.list();
      setExperiments(response.data.experiments || []);
    } catch (error) {
      toast.error('Failed to load experiments');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e) => {
    e.preventDefault();

    // Validation
    if (formData.control_percentage + formData.variant_percentage !== 100) {
      toast.error('Traffic allocation must sum to 100%');
      return;
    }

    try {
      await labAPI.create(formData);
      toast.success('Experiment created successfully');
      setShowCreateModal(false);
      resetForm();
      fetchExperiments();
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to create experiment');
    }
  };

  const handleStart = async (experimentId) => {
    try {
      await labAPI.start(experimentId);
      toast.success('Experiment started');
      fetchExperiments();
    } catch (error) {
      toast.error('Failed to start experiment');
    }
  };

  const handleStop = async (experimentId) => {
    try {
      await labAPI.stop(experimentId);
      toast.success('Experiment stopped');
      fetchExperiments();
    } catch (error) {
      toast.error('Failed to stop experiment');
    }
  };

  const handleViewResults = async (experiment) => {
    setSelectedExperiment(experiment);
    setShowResultsModal(true);

    try {
      const response = await labAPI.getResults(experiment.id);
      setResults(response.data.results);
    } catch (error) {
      toast.error('Failed to load results');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      control_model_id: '',
      variant_model_id: '',
      control_percentage: 50,
      variant_percentage: 50,
      target_metric: 'cost_savings',
      duration_hours: 24,
    });
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
        return 'blue';
      case 'completed':
        return 'green';
      case 'draft':
        return 'gray';
      case 'failed':
        return 'red';
      default:
        return 'gray';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return <FiClock className="w-4 h-4" />;
      case 'completed':
        return <FiCheckCircle className="w-4 h-4" />;
      case 'failed':
        return <FiAlertCircle className="w-4 h-4" />;
      default:
        return null;
    }
  };

  if (loading && experiments.length === 0) {
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
          <h1 className="text-3xl font-bold text-gray-900">Experiment Lab</h1>
          <p className="text-gray-600 mt-1">A/B test ML models and optimization strategies</p>
        </div>
        <Button variant="primary" icon={<FiPlus />} onClick={() => setShowCreateModal(true)}>
          New Experiment
        </Button>
      </div>

      {/* Experiments List */}
      {experiments.length === 0 ? (
        <Card>
          <div className="text-center py-12">
            <FiBarChart2 className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 text-lg">No experiments yet</p>
            <p className="text-gray-400 mt-2">Create your first A/B test to compare models</p>
            <Button variant="primary" className="mt-4" onClick={() => setShowCreateModal(true)}>
              Create Experiment
            </Button>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-6">
          {experiments.map((experiment) => (
            <Card key={experiment.id} className="hover:shadow-lg transition-shadow">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-xl font-semibold text-gray-900">{experiment.name}</h3>
                    <Badge color={getStatusColor(experiment.status)} icon={getStatusIcon(experiment.status)}>
                      {experiment.status}
                    </Badge>
                  </div>

                  <p className="text-gray-600 mb-4">{experiment.description}</p>

                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Control Model</div>
                      <div className="text-sm font-mono font-medium text-gray-900">
                        {experiment.control_model_id?.substring(0, 8)}...
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Variant Model</div>
                      <div className="text-sm font-mono font-medium text-gray-900">
                        {experiment.variant_model_id?.substring(0, 8)}...
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Traffic Split</div>
                      <div className="text-sm font-medium text-gray-900">
                        {experiment.control_percentage}% / {experiment.variant_percentage}%
                      </div>
                    </div>
                    <div>
                      <div className="text-sm text-gray-600 mb-1">Target Metric</div>
                      <div className="text-sm font-medium text-gray-900 capitalize">
                        {experiment.target_metric?.replace('_', ' ')}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-6 text-sm text-gray-600">
                    <div>
                      <span className="font-medium">Created:</span> {formatDate(experiment.created_at)}
                    </div>
                    {experiment.started_at && (
                      <div>
                        <span className="font-medium">Started:</span>{' '}
                        {formatDateTime(experiment.started_at)}
                      </div>
                    )}
                    {experiment.ended_at && (
                      <div>
                        <span className="font-medium">Ended:</span> {formatDateTime(experiment.ended_at)}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex flex-col gap-2 ml-4">
                  {experiment.status === 'draft' && (
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<FiPlay />}
                      onClick={() => handleStart(experiment.id)}
                    >
                      Start
                    </Button>
                  )}
                  {experiment.status === 'running' && (
                    <Button
                      variant="secondary"
                      size="sm"
                      icon={<FiSquare />}
                      onClick={() => handleStop(experiment.id)}
                    >
                      Stop
                    </Button>
                  )}
                  {experiment.status === 'completed' && (
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<FiTrendingUp />}
                      onClick={() => handleViewResults(experiment)}
                    >
                      View Results
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Experiment Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-4">Create New Experiment</h2>

            <form onSubmit={handleCreate} className="space-y-4">
              <Input
                label="Experiment Name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                placeholder="Q1 2026 Cost Optimization Test"
              />

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  rows="3"
                  placeholder="Test new spot prediction model against baseline"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Control Model ID"
                  value={formData.control_model_id}
                  onChange={(e) => setFormData({ ...formData, control_model_id: e.target.value })}
                  required
                  placeholder="model-baseline-v1"
                />

                <Input
                  label="Variant Model ID"
                  value={formData.variant_model_id}
                  onChange={(e) => setFormData({ ...formData, variant_model_id: e.target.value })}
                  required
                  placeholder="model-experimental-v2"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <Input
                  label="Control Traffic %"
                  type="number"
                  value={formData.control_percentage}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    setFormData({
                      ...formData,
                      control_percentage: val,
                      variant_percentage: 100 - val,
                    });
                  }}
                  min="0"
                  max="100"
                  required
                />

                <Input
                  label="Variant Traffic %"
                  type="number"
                  value={formData.variant_percentage}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    setFormData({
                      ...formData,
                      variant_percentage: val,
                      control_percentage: 100 - val,
                    });
                  }}
                  min="0"
                  max="100"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Target Metric</label>
                  <select
                    value={formData.target_metric}
                    onChange={(e) => setFormData({ ...formData, target_metric: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {TARGET_METRICS.map((metric) => (
                      <option key={metric.value} value={metric.value}>
                        {metric.label}
                      </option>
                    ))}
                  </select>
                </div>

                <Input
                  label="Duration (hours)"
                  type="number"
                  value={formData.duration_hours}
                  onChange={(e) => setFormData({ ...formData, duration_hours: parseInt(e.target.value) })}
                  min="1"
                  max="720"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setShowCreateModal(false);
                    resetForm();
                  }}
                >
                  Cancel
                </Button>
                <Button type="submit" variant="primary">
                  Create Experiment
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Results Modal */}
      {showResultsModal && selectedExperiment && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg w-full max-w-4xl max-h-[90vh] overflow-y-auto">
            <div className="sticky top-0 bg-white border-b px-6 py-4 flex justify-between items-center">
              <h2 className="text-2xl font-bold text-gray-900">Experiment Results</h2>
              <button
                onClick={() => {
                  setShowResultsModal(false);
                  setSelectedExperiment(null);
                  setResults(null);
                }}
                className="p-2 hover:bg-gray-100 rounded-lg"
              >
                <FiAlertCircle className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Experiment Info */}
              <Card>
                <h3 className="text-lg font-semibold text-gray-900 mb-3">{selectedExperiment.name}</h3>
                <p className="text-gray-600 mb-4">{selectedExperiment.description}</p>
                <div className="grid grid-cols-3 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Status:</span>{' '}
                    <Badge color={getStatusColor(selectedExperiment.status)}>
                      {selectedExperiment.status}
                    </Badge>
                  </div>
                  <div>
                    <span className="text-gray-600">Started:</span>{' '}
                    {formatDateTime(selectedExperiment.started_at)}
                  </div>
                  <div>
                    <span className="text-gray-600">Ended:</span>{' '}
                    {formatDateTime(selectedExperiment.ended_at)}
                  </div>
                </div>
              </Card>

              {/* Winner */}
              {results?.winner && (
                <Card className="bg-green-50 border-green-200">
                  <div className="flex items-center gap-3 mb-3">
                    <FiCheckCircle className="w-6 h-6 text-green-600" />
                    <h3 className="text-lg font-semibold text-green-900">
                      Winner: {results.winner === 'control' ? 'Control Model' : 'Variant Model'}
                    </h3>
                  </div>
                  <p className="text-green-800">
                    The {results.winner} performed {results.improvement_percentage?.toFixed(2)}% better in{' '}
                    {selectedExperiment.target_metric?.replace('_', ' ')}
                  </p>
                </Card>
              )}

              {/* Performance Comparison */}
              {results && (
                <div className="grid grid-cols-2 gap-6">
                  {/* Control Results */}
                  <Card className={results.winner === 'control' ? 'border-green-500 border-2' : ''}>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">
                      Control Model
                      {results.winner === 'control' && (
                        <Badge color="green" className="ml-2">
                          Winner
                        </Badge>
                      )}
                    </h3>
                    <div className="space-y-3">
                      <div>
                        <div className="text-sm text-gray-600">Instances Processed</div>
                        <div className="text-2xl font-bold text-gray-900">
                          {formatNumber(results.control_instances || 0)}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">Metric Score</div>
                        <div className="text-2xl font-bold text-gray-900">
                          {results.control_metric_score?.toFixed(2) || 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">Cost</div>
                        <div className="text-2xl font-bold text-gray-900">
                          {formatCurrency(results.control_cost || 0)}
                        </div>
                      </div>
                    </div>
                  </Card>

                  {/* Variant Results */}
                  <Card className={results.winner === 'variant' ? 'border-green-500 border-2' : ''}>
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">
                      Variant Model
                      {results.winner === 'variant' && (
                        <Badge color="green" className="ml-2">
                          Winner
                        </Badge>
                      )}
                    </h3>
                    <div className="space-y-3">
                      <div>
                        <div className="text-sm text-gray-600">Instances Processed</div>
                        <div className="text-2xl font-bold text-gray-900">
                          {formatNumber(results.variant_instances || 0)}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">Metric Score</div>
                        <div className="text-2xl font-bold text-gray-900">
                          {results.variant_metric_score?.toFixed(2) || 'N/A'}
                        </div>
                      </div>
                      <div>
                        <div className="text-sm text-gray-600">Cost</div>
                        <div className="text-2xl font-bold text-gray-900">
                          {formatCurrency(results.variant_cost || 0)}
                        </div>
                      </div>
                    </div>
                  </Card>
                </div>
              )}
            </div>

            <div className="sticky bottom-0 bg-gray-50 border-t px-6 py-4 flex justify-end">
              <Button
                variant="secondary"
                onClick={() => {
                  setShowResultsModal(false);
                  setSelectedExperiment(null);
                  setResults(null);
                }}
              >
                Close
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ExperimentLab;
