/**
 * Hibernation Schedule Grid Editor
 * 168-hour schedule matrix (7 days x 24 hours)
 * With triple-strategy selection (Namespace Sleep, Nuclear, Snapshot & Restore)
 */
import React, { useState, useEffect, useRef } from 'react';
import { hibernationAPI, metricAPI } from '../../services/api';
import { useClusterStore } from '../../store/useStore';
import { Card, Button, Input, Badge } from '../shared';
import { FiSave, FiRotateCcw, FiClock, FiSun, FiMoon, FiDollarSign, FiPlay, FiPower, FiZap, FiShield, FiChevronDown, FiChevronUp, FiServer } from 'react-icons/fi';
import toast from 'react-hot-toast';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

const TIMEZONES = [
  'UTC', 'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'Europe/London', 'Europe/Paris', 'Asia/Tokyo', 'Asia/Shanghai', 'Australia/Sydney',
];

const STRATEGIES = [
  {
    value: 'NAMESPACE_SLEEP',
    label: 'Namespace Sleep',
    icon: FiMoon,
    color: 'blue',
    bgColor: 'bg-blue-50',
    borderColor: 'border-blue-500',
    textColor: 'text-blue-700',
    tagline: '~2 min wake | ~80% savings',
    description: 'Scales workloads to 0 replicas. Cluster Autoscaler drains idle nodes.',
    bestFor: 'Best for stateless dev/test',
    savingsMultiplier: 0.80,
  },
  {
    value: 'NUCLEAR',
    label: 'Nuclear',
    icon: FiZap,
    color: 'red',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-500',
    textColor: 'text-red-700',
    tagline: '~8 min wake | ~99% savings',
    description: 'Scales all ASGs to 0. Maximum cost reduction.',
    bestFor: 'Best for non-critical environments',
    savingsMultiplier: 0.99,
  },
  {
    value: 'SNAPSHOT_RESTORE',
    label: 'Snapshot & Restore',
    icon: FiShield,
    color: 'green',
    bgColor: 'bg-green-50',
    borderColor: 'border-green-500',
    textColor: 'text-green-700',
    tagline: '~12 min wake | ~90% savings',
    description: 'Snapshots EBS volumes before shutdown. Preserves data with AZ affinity.',
    bestFor: 'Best for databases',
    savingsMultiplier: 0.90,
  },
];

const HibernationSchedule = ({ clusterId }) => {
  const { clusters } = useClusterStore();
  const [loading, setLoading] = useState(false);
  const [isPainting, setIsPainting] = useState(false);
  const [paintMode, setPaintMode] = useState(null);
  const [hourlyCost, setHourlyCost] = useState(0);
  const [showComparison, setShowComparison] = useState(false);
  const [showPresetModal, setShowPresetModal] = useState(false);
  const [editingPreset, setEditingPreset] = useState(null);
  const [customPresets, setCustomPresets] = useState([]);
  const [schedulingMode, setSchedulingMode] = useState('grid'); // 'preset' or 'grid' - default to grid

  const [formData, setFormData] = useState({
    cluster_id: clusterId || '',
    schedule_matrix: Array(168).fill(1),
    timezone: 'UTC',
    pre_warm_minutes: 15,
    is_active: true,
    strategy: 'NAMESPACE_SLEEP',
  });

  const [existingSchedule, setExistingSchedule] = useState(null);
  const [savings, setSavings] = useState(0);
  const gridRef = useRef(null);

  useEffect(() => {
    if (clusterId) {
      fetchScheduleForCluster(clusterId);
      fetchClusterCost(clusterId);
    }
    // Load custom presets from localStorage
    const savedPresets = localStorage.getItem('hibernation_custom_presets');
    if (savedPresets) {
      try {
        setCustomPresets(JSON.parse(savedPresets));
      } catch (e) {
        console.error('Failed to load custom presets', e);
      }
    }
  }, [clusterId]);

  useEffect(() => {
    calculateSavings();
  }, [formData.schedule_matrix, formData.strategy, hourlyCost]);

  const fetchClusterCost = async (clusterIdParam) => {
    try {
      const response = await metricAPI.getClusterMetrics(clusterIdParam);
      if (response.data) {
        const estimatedHourly = (response.data.total_instances || 0) * 0.12;
        setHourlyCost(estimatedHourly);
      }
    } catch (error) {
      console.warn('Failed to fetch hourly cost, using default', error);
      setHourlyCost(2.45);
    }
  };

  const fetchScheduleForCluster = async (clusterIdParam) => {
    setLoading(true);
    try {
      const response = await hibernationAPI.getByCluster(clusterIdParam);
      const schedules = response.data?.schedules || [];
      if (schedules.length > 0) {
        const schedule = schedules[0];
        setExistingSchedule(schedule);
        setFormData({
          cluster_id: schedule.cluster_id,
          schedule_matrix: schedule.schedule_matrix || Array(168).fill(1),
          timezone: schedule.timezone || 'UTC',
          pre_warm_minutes: schedule.pre_warm_minutes || 15,
          is_active: schedule.is_active ?? true,
          strategy: schedule.strategy || 'NAMESPACE_SLEEP',
        });
      }
    } catch (error) {
      if (error.response?.status !== 404) {
        toast.error('Failed to load schedule');
      }
    } finally {
      setLoading(false);
    }
  };

  const calculateSavings = () => {
    const sleepHours = formData.schedule_matrix.filter(h => h === 0).length;
    const strategyConfig = STRATEGIES.find(s => s.value === formData.strategy) || STRATEGIES[0];
    const monthlySavings = (sleepHours / 168) * (hourlyCost * 24 * 30) * strategyConfig.savingsMultiplier;
    setSavings(monthlySavings);
  };

  const handleSave = async (e) => {
    e.preventDefault();

    if (formData.schedule_matrix.length !== 168) {
      toast.error('Schedule matrix must have exactly 168 elements');
      return;
    }

    try {
      const schedulePayload = { ...formData };

      if (existingSchedule) {
        await hibernationAPI.update(existingSchedule.id, schedulePayload);
        toast.success('Schedule updated successfully');
      } else {
        await hibernationAPI.create(schedulePayload);
        toast.success('Schedule created successfully');
      }

      fetchScheduleForCluster(formData.cluster_id);
    } catch (error) {
      toast.error(error.response?.data?.message || 'Failed to save schedule');
    }
  };

  const handleToggleActive = async () => {
    if (!existingSchedule) {
      toast.error('Please save the schedule first');
      return;
    }

    try {
      await hibernationAPI.toggle(existingSchedule.id);
      toast.success(`Schedule ${existingSchedule.is_active ? 'deactivated' : 'activated'}`);
      fetchScheduleForCluster(formData.cluster_id);
    } catch (error) {
      toast.error('Failed to toggle schedule');
    }
  };

  const handleWakeUpNow = async () => {
    if (!existingSchedule) return;
    try {
      await hibernationAPI.override(existingSchedule.id, { action: 'WAKE', duration_minutes: 120 });
      toast.success('Cluster wake-up queued');
    } catch (error) {
      toast.error('Failed to wake cluster');
    }
  };

  const handleSleepNow = async () => {
    if (!existingSchedule) return;
    try {
      await hibernationAPI.override(existingSchedule.id, { action: 'SLEEP' });
      toast.success('Cluster sleep queued');
    } catch (error) {
      toast.error('Failed to sleep cluster');
    }
  };

  // Grid cell interaction handlers
  const handleCellMouseDown = (dayIndex, hourIndex) => {
    const index = dayIndex * 24 + hourIndex;
    const newValue = formData.schedule_matrix[index] === 1 ? 0 : 1;
    setPaintMode(newValue === 1 ? 'awake' : 'sleep');
    setIsPainting(true);
    updateCell(dayIndex, hourIndex, newValue);
  };

  const handleCellMouseEnter = (dayIndex, hourIndex) => {
    if (isPainting && paintMode !== null) {
      const newValue = paintMode === 'awake' ? 1 : 0;
      updateCell(dayIndex, hourIndex, newValue);
    }
  };

  const handleMouseUp = () => {
    setIsPainting(false);
    setPaintMode(null);
  };

  const updateCell = (dayIndex, hourIndex, value) => {
    const index = dayIndex * 24 + hourIndex;
    const newMatrix = [...formData.schedule_matrix];
    newMatrix[index] = value;
    setFormData({ ...formData, schedule_matrix: newMatrix });
  };

  const setAllAwake = () => {
    setFormData({ ...formData, schedule_matrix: Array(168).fill(1) });
    toast.success('All hours set to awake');
  };

  const setAllSleep = () => {
    setFormData({ ...formData, schedule_matrix: Array(168).fill(0) });
    toast.success('All hours set to sleep');
  };

  const setBusinessHours = () => {
    const matrix = Array(168).fill(0);
    for (let day = 0; day < 5; day++) {
      for (let hour = 9; hour < 17; hour++) {
        matrix[day * 24 + hour] = 1;
      }
    }
    setFormData({ ...formData, schedule_matrix: matrix });
    toast.success('Business hours preset applied');
  };

  const set24x7 = () => {
    setFormData({ ...formData, schedule_matrix: Array(168).fill(1) });
    toast.success('24/7 uptime preset applied');
  };

  // Save custom preset
  const saveCustomPreset = (preset) => {
    let updatedPresets;
    if (editingPreset) {
      // Update existing preset
      updatedPresets = customPresets.map(p => p.id === editingPreset.id ? { ...preset, id: editingPreset.id } : p);
      toast.success('Preset updated successfully');
    } else {
      // Create new preset
      const newPreset = {
        ...preset,
        id: Date.now().toString(),
        created_at: new Date().toISOString(),
      };
      updatedPresets = [...customPresets, newPreset];
      toast.success('Custom preset created');
    }

    setCustomPresets(updatedPresets);
    localStorage.setItem('hibernation_custom_presets', JSON.stringify(updatedPresets));
    setShowPresetModal(false);
    setEditingPreset(null);
  };

  // Delete custom preset
  const deleteCustomPreset = (presetId) => {
    const updatedPresets = customPresets.filter(p => p.id !== presetId);
    setCustomPresets(updatedPresets);
    localStorage.setItem('hibernation_custom_presets', JSON.stringify(updatedPresets));
    toast.success('Preset deleted');
  };

  // Apply custom preset
  const applyCustomPreset = (preset) => {
    const matrix = Array(168).fill(0);
    const [startHour] = preset.startTime.split(':').map(Number);
    const [endHour] = preset.endTime.split(':').map(Number);

    preset.selectedDays.forEach(dayIndex => {
      for (let hour = startHour; hour < endHour; hour++) {
        matrix[dayIndex * 24 + hour] = 1;
      }
    });

    setFormData({
      ...formData,
      schedule_matrix: matrix,
      strategy: preset.strategy || 'NAMESPACE_SLEEP'
    });
    toast.success(`Applied preset: ${preset.name}`);
  };

  // Toggle preset favorite/star
  const togglePresetStar = (presetId) => {
    const updatedPresets = customPresets.map(p =>
      p.id === presetId ? { ...p, isFavorite: !p.isFavorite } : p
    );
    setCustomPresets(updatedPresets);
    localStorage.setItem('hibernation_custom_presets', JSON.stringify(updatedPresets));

    const preset = updatedPresets.find(p => p.id === presetId);
    toast.success(preset.isFavorite ? 'Added to Quick Presets' : 'Removed from Quick Presets');
  };

  useEffect(() => {
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  const selectedStrategy = STRATEGIES.find(s => s.value === formData.strategy) || STRATEGIES[0];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Hibernation Schedule</h1>
          <p className="text-gray-600 mt-1">Configure when clusters should sleep to save costs</p>
        </div>
        <div className="flex gap-2">
          {existingSchedule && (
            <>
              <Button
                variant="outline"
                icon={<FiMoon />}
                onClick={handleSleepNow}
                title="Put cluster to sleep immediately"
              >
                Sleep Now
              </Button>
              <Button
                variant="outline"
                icon={<FiPlay />}
                onClick={handleWakeUpNow}
                title="Wake up cluster for 2 hours immediately"
              >
                Wake Up Now
              </Button>
              <Button
                variant={existingSchedule.is_active ? 'primary' : 'secondary'}
                icon={<FiPower />}
                onClick={handleToggleActive}
              >
                {existingSchedule.is_active ? 'Active' : 'Inactive'}
              </Button>
            </>
          )}
        </div>
      </div>

      <form onSubmit={handleSave}>
        {/* Common Configuration - Always Visible */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
          <Card className="lg:col-span-2">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Configuration</h3>
            <div className="space-y-4">
              {!clusterId && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Cluster</label>
                  <select
                    value={formData.cluster_id}
                    onChange={(e) => {
                      setFormData({ ...formData, cluster_id: e.target.value });
                      if (e.target.value) fetchScheduleForCluster(e.target.value);
                    }}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    required
                  >
                    <option value="">Select a cluster</option>
                    {clusters.map((cluster) => (
                      <option key={cluster.id} value={cluster.id}>{cluster.name} - {cluster.region}</option>
                    ))}
                  </select>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
                  <select
                    value={formData.timezone}
                    onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    {TIMEZONES.map((tz) => <option key={tz} value={tz}>{tz}</option>)}
                  </select>
                </div>
                <Input
                  label="Pre-warm Minutes"
                  type="number"
                  value={formData.pre_warm_minutes}
                  onChange={(e) => setFormData({ ...formData, pre_warm_minutes: parseInt(e.target.value) })}
                  min="0" max="60" required
                />
              </div>
            </div>
          </Card>

          <Card className="bg-gradient-to-br from-green-50 to-white flex flex-col justify-center">
            <div className="text-center">
              <div className="p-3 bg-green-100 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-3 text-green-600">
                <FiDollarSign className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-medium text-gray-900">Estimated Monthly Savings</h3>
              <p className="text-3xl font-bold text-green-600 mt-2">
                ${savings.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {selectedStrategy.label} strategy ({Math.round(selectedStrategy.savingsMultiplier * 100)}% efficiency)
              </p>
            </div>
          </Card>
        </div>

        {/* Hibernation Strategy Selection */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">Hibernation Strategy</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {STRATEGIES.map((strategy) => {
              const Icon = strategy.icon;
              const isSelected = formData.strategy === strategy.value;
              return (
                <div
                  key={strategy.value}
                  onClick={() => setFormData({ ...formData, strategy: strategy.value })}
                  className={`relative cursor-pointer rounded-lg border-2 p-4 transition-all ${
                    isSelected
                      ? `${strategy.borderColor} ${strategy.bgColor} shadow-md`
                      : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
                  }`}
                >
                  {isSelected && (
                    <div className={`absolute top-2 right-2 w-5 h-5 rounded-full ${strategy.borderColor.replace('border', 'bg')} flex items-center justify-center`}>
                      <svg className="w-3 h-3 text-white" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                      </svg>
                    </div>
                  )}
                  <div className="flex items-center gap-3 mb-2">
                    <div className={`p-2 rounded-lg ${isSelected ? strategy.bgColor : 'bg-gray-100'}`}>
                      <Icon className={`w-5 h-5 ${isSelected ? strategy.textColor : 'text-gray-500'}`} />
                    </div>
                    <div>
                      <h4 className={`font-semibold ${isSelected ? strategy.textColor : 'text-gray-900'}`}>
                        {strategy.label}
                      </h4>
                      <p className="text-xs text-gray-500">{strategy.tagline}</p>
                    </div>
                  </div>
                  <p className="text-sm text-gray-600">{strategy.description}</p>
                  <p className={`text-xs mt-2 font-medium ${isSelected ? strategy.textColor : 'text-gray-400'}`}>
                    {strategy.bestFor}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Collapsible Comparison Table */}
          <button
            type="button"
            onClick={() => setShowComparison(!showComparison)}
            className="mt-3 flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            {showComparison ? <FiChevronUp /> : <FiChevronDown />}
            {showComparison ? 'Hide' : 'Show'} strategy comparison
          </button>

          {showComparison && (
            <div className="mt-2 overflow-hidden rounded-lg border border-gray-200">
              <table className="min-w-full divide-y divide-gray-200 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium text-gray-500">Strategy</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-500">Wake Time</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-500">Savings</th>
                    <th className="px-4 py-2 text-center font-medium text-gray-500">Safety</th>
                    <th className="px-4 py-2 text-left font-medium text-gray-500">Best For</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 bg-white">
                  {STRATEGIES.map(s => (
                    <tr key={s.value} className={formData.strategy === s.value ? s.bgColor : ''}>
                      <td className="px-4 py-2 font-medium text-gray-900">{s.label}</td>
                      <td className="px-4 py-2 text-center text-gray-600">{s.tagline.split('|')[0].trim()}</td>
                      <td className="px-4 py-2 text-center text-gray-600">{Math.round(s.savingsMultiplier * 100)}%</td>
                      <td className="px-4 py-2 text-center">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          s.value === 'NUCLEAR' ? 'bg-yellow-100 text-yellow-700' : 'bg-green-100 text-green-700'
                        }`}>
                          {s.value === 'NUCLEAR' ? 'Medium' : 'High'}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-gray-600">{s.bestFor}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Scheduling Mode Tabs */}
        <div className="mb-6">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
              <button
                type="button"
                onClick={() => setSchedulingMode('preset')}
                className={`${
                  schedulingMode === 'preset'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors flex items-center gap-2`}
              >
                <FiClock className="w-4 h-4" />
                Preset Schedule
              </button>
              <button
                type="button"
                onClick={() => setSchedulingMode('grid')}
                className={`${
                  schedulingMode === 'grid'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                } whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors flex items-center gap-2`}
              >
                <FiServer className="w-4 h-4" />
                Weekly Grid
              </button>
            </nav>
          </div>
        </div>

        {/* Preset Scheduling Mode */}
        {schedulingMode === 'preset' && (
          <>
            {/* Quick Presets - Starred/Favorited Presets */}
            {customPresets.filter(p => p.isFavorite).length > 0 && (
              <Card className="mb-6">
                <h3 className="text-lg font-semibold text-gray-900 mb-4">Quick Presets</h3>
                <div className="flex gap-2 flex-wrap">
                  {customPresets.filter(p => p.isFavorite).map(preset => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => applyCustomPreset(preset)}
                      className="px-4 py-2 bg-blue-50 text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-100 text-sm font-medium transition-colors flex items-center gap-2"
                    >
                      <svg className="w-4 h-4 fill-current text-yellow-500" viewBox="0 0 20 20">
                        <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                      </svg>
                      {preset.name}
                    </button>
                  ))}
                </div>
              </Card>
            )}

            {/* All Custom Presets */}
            <Card className="mb-6">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-gray-900">Custom Presets</h3>
                  <p className="text-sm text-gray-500 mt-1">Create and manage your schedule presets</p>
                </div>
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    setEditingPreset(null);
                    setShowPresetModal(true);
                  }}
                  icon={<FiClock />}
                >
                  Create Preset
                </Button>
              </div>

              {customPresets.length === 0 ? (
                <div className="text-center py-8 bg-gray-50 rounded-lg border-2 border-dashed border-gray-300">
                  <FiClock className="w-12 h-12 text-gray-400 mx-auto mb-3" />
                  <p className="text-sm text-gray-600 mb-2">No custom presets yet</p>
                  <p className="text-xs text-gray-500">Create a preset to quickly apply repeating schedules</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {customPresets.map(preset => {
                    const presetStrategy = STRATEGIES.find(s => s.value === preset.strategy) || STRATEGIES[0];
                    return (
                      <div
                        key={preset.id}
                        className="relative group border border-gray-200 rounded-lg p-4 hover:border-blue-300 hover:shadow-md transition-all cursor-pointer bg-white"
                        onClick={() => applyCustomPreset(preset)}
                      >
                        {/* Star Icon */}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            togglePresetStar(preset.id);
                          }}
                          className="absolute top-3 left-3 p-1 hover:bg-gray-100 rounded transition-colors"
                          title={preset.isFavorite ? "Remove from Quick Presets" : "Add to Quick Presets"}
                        >
                          <svg className={`w-5 h-5 ${preset.isFavorite ? 'fill-current text-yellow-500' : 'stroke-current text-gray-400'}`} viewBox="0 0 20 20">
                            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                          </svg>
                        </button>

                        <div className="flex items-start justify-between mb-2 ml-8">
                          <h4 className="font-semibold text-gray-900 text-sm pr-2">{preset.name}</h4>
                          <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setEditingPreset(preset);
                                setShowPresetModal(true);
                              }}
                              className="p-1 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded"
                              title="Edit preset"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                              </svg>
                            </button>
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                if (window.confirm(`Delete preset "${preset.name}"?`)) {
                                  deleteCustomPreset(preset.id);
                                }
                              }}
                              className="p-1 text-red-600 hover:text-red-800 hover:bg-red-50 rounded"
                              title="Delete preset"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                            </button>
                          </div>
                        </div>

                        {/* Strategy Badge */}
                        <div className="ml-8 mb-2">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 ${presetStrategy.bgColor} ${presetStrategy.textColor} text-xs font-medium rounded`}>
                            {React.createElement(presetStrategy.icon, { className: 'w-3 h-3' })}
                            {presetStrategy.label}
                          </span>
                        </div>

                        <div className="flex items-center gap-2 mb-2 ml-8">
                          <FiClock className="w-4 h-4 text-gray-400" />
                          <span className="text-xs text-gray-600">{preset.startTime} - {preset.endTime}</span>
                        </div>
                        <div className="flex flex-wrap gap-1 ml-8">
                          {preset.selectedDays.map(d => (
                            <span key={d} className="inline-block px-2 py-0.5 bg-blue-100 text-blue-700 text-xs font-medium rounded">
                              {DAYS[d].substring(0, 3)}
                            </span>
                          ))}
                        </div>
                        <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <span className="text-xs text-blue-600 font-medium">Click to apply</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </Card>
          </>
        )}

        {/* Weekly Grid Mode */}
        {schedulingMode === 'grid' && (
          <Card className="mb-6">
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Manual Schedule Grid</h3>
              <p className="text-sm text-gray-500 mb-3">Click or drag to paint custom schedules</p>
              <div className="flex gap-2 flex-wrap mb-4">
                <Button type="button" variant="outline" size="sm" onClick={set24x7}>24/7 Uptime</Button>
                <Button type="button" variant="outline" size="sm" onClick={setBusinessHours}>Business Hours</Button>
                <Button type="button" variant="outline" size="sm" onClick={setAllAwake}>All Awake</Button>
                <Button type="button" variant="outline" size="sm" onClick={setAllSleep}>All Sleep</Button>
              </div>
            </div>
            <div className="flex items-center justify-between mb-4">
              <div className="flex gap-4 text-sm">
                <div className="flex items-center gap-1"><div className="w-3 h-3 bg-green-500 rounded"></div> Awake</div>
                <div className="flex items-center gap-1"><div className="w-3 h-3 bg-gray-200 rounded"></div> Sleep</div>
              </div>
            </div>

            <div className="overflow-x-auto select-none" ref={gridRef}>
            <div className="inline-block min-w-full">
              <div className="flex">
                <div className="w-24 flex-shrink-0"></div>
                {HOURS.map(hour => (
                  <div key={hour} className="w-8 h-8 flex items-center justify-center text-xs font-medium text-gray-500 border-b">
                    {hour}
                  </div>
                ))}
              </div>

              {DAYS.map((day, dayIndex) => (
                <div key={day} className="flex">
                  <div className="w-24 h-8 flex items-center justify-start pr-2 text-sm font-medium text-gray-700 flex-shrink-0">
                    {day}
                  </div>
                  {HOURS.map(hour => {
                    const index = dayIndex * 24 + hour;
                    const isAwake = formData.schedule_matrix[index] === 1;
                    return (
                      <div
                        key={hour}
                        onMouseDown={() => handleCellMouseDown(dayIndex, hour)}
                        onMouseEnter={() => handleCellMouseEnter(dayIndex, hour)}
                        className={`w-8 h-8 border border-white cursor-pointer transition-colors ${isAwake ? 'bg-green-500 hover:bg-green-600' : 'bg-gray-200 hover:bg-gray-300'
                          }`}
                        title={`${day} ${hour}:00 - ${isAwake ? 'Awake' : 'Sleep'}`}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
            </div>
          </Card>
        )}

        {/* Save Button */}
        <div className="flex justify-end pt-4">
          <Button type="submit" variant="primary" icon={<FiSave />} size="lg">
            {existingSchedule ? 'Update Schedule' : 'Create Schedule'}
          </Button>
        </div>
      </form>

      {/* Custom Preset Modal */}
      {showPresetModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full p-6">
            <h2 className="text-xl font-bold text-gray-900 mb-4">
              {editingPreset ? 'Edit Preset' : 'Create Custom Preset'}
            </h2>
            <PresetForm
              initialData={editingPreset}
              onSave={saveCustomPreset}
              onCancel={() => {
                setShowPresetModal(false);
                setEditingPreset(null);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
};

// Preset Form Component
const PresetForm = ({ initialData, onSave, onCancel }) => {
  const [presetData, setPresetData] = useState({
    name: initialData?.name || '',
    selectedDays: initialData?.selectedDays || [1, 2, 3, 4, 5],
    startTime: initialData?.startTime || '09:00',
    endTime: initialData?.endTime || '17:00',
    strategy: initialData?.strategy || 'NAMESPACE_SLEEP',
    isFavorite: initialData?.isFavorite || false,
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!presetData.name.trim()) {
      toast.error('Please enter a preset name');
      return;
    }
    if (presetData.selectedDays.length === 0) {
      toast.error('Please select at least one day');
      return;
    }
    onSave(presetData);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Preset Name</label>
        <input
          type="text"
          value={presetData.name}
          onChange={(e) => setPresetData({ ...presetData, name: e.target.value })}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="e.g., Dev Environment Schedule"
          required
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Hibernation Strategy</label>
        <div className="grid grid-cols-3 gap-2">
          {STRATEGIES.map((strategy) => {
            const Icon = strategy.icon;
            const isSelected = presetData.strategy === strategy.value;
            return (
              <button
                key={strategy.value}
                type="button"
                onClick={() => setPresetData({ ...presetData, strategy: strategy.value })}
                className={`p-2 border rounded-lg text-center transition-all ${
                  isSelected
                    ? `${strategy.borderColor} ${strategy.bgColor}`
                    : 'border-gray-200 bg-white hover:border-gray-300'
                }`}
              >
                <Icon className={`w-5 h-5 mx-auto mb-1 ${isSelected ? strategy.textColor : 'text-gray-400'}`} />
                <span className={`block text-xs font-medium ${isSelected ? strategy.textColor : 'text-gray-600'}`}>
                  {strategy.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-2">Active Days</label>
        <div className="flex gap-2 flex-wrap">
          {DAYS.map((day, index) => {
            const isSelected = presetData.selectedDays.includes(index);
            return (
              <button
                key={day}
                type="button"
                onClick={() => {
                  setPresetData(prev => ({
                    ...prev,
                    selectedDays: isSelected
                      ? prev.selectedDays.filter(d => d !== index)
                      : [...prev.selectedDays, index].sort()
                  }));
                }}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  isSelected
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {day.substring(0, 3)}
              </button>
            );
          })}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Start Time</label>
          <input
            type="time"
            value={presetData.startTime}
            onChange={(e) => setPresetData({ ...presetData, startTime: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">End Time</label>
          <input
            type="time"
            value={presetData.endTime}
            onChange={(e) => setPresetData({ ...presetData, endTime: e.target.value })}
            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-4 border-t">
        <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
        <Button type="submit" variant="primary">
          {initialData ? 'Update Preset' : 'Create Preset'}
        </Button>
      </div>
    </form>
  );
};

export default HibernationSchedule;
