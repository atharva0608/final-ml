/**
 * Hibernation Schedule Grid Editor
 * 168-hour schedule matrix (7 days × 24 hours)
 */
import React, { useState, useEffect, useRef } from 'react';
import { hibernationAPI } from '../../services/api';
import { useClusterStore } from '../../store/useStore';
import { Card, Button, Input } from '../shared';
import { FiSave, FiRotateCcw, FiClock, FiSun, FiMoon } from 'react-icons/fi';
import toast from 'react-hot-toast';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

// Common timezones
const TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Australia/Sydney',
];

const HibernationSchedule = ({ clusterId }) => {
  const { clusters } = useClusterStore();
  const [loading, setLoading] = useState(false);
  const [isPainting, setIsPainting] = useState(false);
  const [paintMode, setPaintMode] = useState(null); // 'awake' or 'sleep'

  const [formData, setFormData] = useState({
    cluster_id: clusterId || '',
    schedule_matrix: Array(168).fill(1), // Default: always awake
    timezone: 'UTC',
    pre_warm_minutes: 15,
    is_active: true,
  });

  const [existingSchedule, setExistingSchedule] = useState(null);
  const gridRef = useRef(null);

  useEffect(() => {
    if (clusterId) {
      fetchScheduleForCluster(clusterId);
    }
  }, [clusterId]);

  const fetchScheduleForCluster = async (clusterIdParam) => {
    setLoading(true);
    try {
      const response = await hibernationAPI.getByCluster(clusterIdParam);
      if (response.data.schedule) {
        setExistingSchedule(response.data.schedule);
        setFormData({
          cluster_id: response.data.schedule.cluster_id,
          schedule_matrix: response.data.schedule.schedule_matrix || Array(168).fill(1),
          timezone: response.data.schedule.timezone || 'UTC',
          pre_warm_minutes: response.data.schedule.pre_warm_minutes || 15,
          is_active: response.data.schedule.is_active ?? true,
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

  const handleSave = async (e) => {
    e.preventDefault();

    // Validation
    if (formData.schedule_matrix.length !== 168) {
      toast.error('Schedule matrix must have exactly 168 elements');
      return;
    }

    if (formData.pre_warm_minutes < 0 || formData.pre_warm_minutes > 60) {
      toast.error('Pre-warm minutes must be between 0 and 60');
      return;
    }

    try {
      const schedulePayload = {
        cluster_id: formData.cluster_id,
        schedule_matrix: formData.schedule_matrix,
        timezone: formData.timezone,
        pre_warm_minutes: formData.pre_warm_minutes,
        is_active: formData.is_active,
      };

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

  // Preset functions
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
    // Monday-Friday, 9am-5pm = awake
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

  useEffect(() => {
    // Add global mouse up listener for drag painting
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Hibernation Schedule</h1>
          <p className="text-gray-600 mt-1">Configure when clusters should sleep to save costs</p>
        </div>
        {existingSchedule && (
          <Button
            variant={existingSchedule.is_active ? 'primary' : 'secondary'}
            icon={<FiClock />}
            onClick={handleToggleActive}
          >
            {existingSchedule.is_active ? 'Active' : 'Inactive'}
          </Button>
        )}
      </div>

      <form onSubmit={handleSave}>
        {/* Configuration Section */}
        <Card className="mb-6">
          <div className="space-y-4">
            {/* Cluster Selection */}
            {!clusterId && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Cluster</label>
                <select
                  value={formData.cluster_id}
                  onChange={(e) => {
                    setFormData({ ...formData, cluster_id: e.target.value });
                    if (e.target.value) {
                      fetchScheduleForCluster(e.target.value);
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

            <div className="grid grid-cols-2 gap-4">
              {/* Timezone */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Timezone</label>
                <select
                  value={formData.timezone}
                  onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {TIMEZONES.map((tz) => (
                    <option key={tz} value={tz}>
                      {tz}
                    </option>
                  ))}
                </select>
              </div>

              {/* Pre-warm Minutes */}
              <Input
                label="Pre-warm Minutes"
                type="number"
                value={formData.pre_warm_minutes}
                onChange={(e) => setFormData({ ...formData, pre_warm_minutes: parseInt(e.target.value) })}
                min="0"
                max="60"
                required
                help="Minutes before scheduled wake to start instances"
              />
            </div>

            {/* Preset Buttons */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Quick Presets</label>
              <div className="flex gap-2 flex-wrap">
                <Button type="button" variant="outline" size="sm" onClick={set24x7}>
                  24/7 Uptime
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={setBusinessHours}>
                  Business Hours (M-F 9-5)
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={setAllAwake}>
                  All Awake
                </Button>
                <Button type="button" variant="outline" size="sm" onClick={setAllSleep}>
                  All Sleep
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* Schedule Grid */}
        <Card>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-gray-900">Weekly Schedule Grid</h3>
              <p className="text-sm text-gray-600 mt-1">
                Click or drag to paint. <FiSun className="inline w-4 h-4 text-green-600" /> Awake |{' '}
                <FiMoon className="inline w-4 h-4 text-gray-400" /> Sleep
              </p>
            </div>
          </div>

          <div className="overflow-x-auto" ref={gridRef}>
            <div className="inline-block min-w-full">
              {/* Hour Headers */}
              <div className="flex">
                <div className="w-24 flex-shrink-0"></div>
                {HOURS.map((hour) => (
                  <div
                    key={hour}
                    className="w-8 h-8 flex items-center justify-center text-xs font-medium text-gray-600 border-b"
                  >
                    {hour}
                  </div>
                ))}
              </div>

              {/* Day Rows */}
              {DAYS.map((day, dayIndex) => (
                <div key={day} className="flex">
                  {/* Day Label */}
                  <div className="w-24 h-8 flex items-center justify-start pr-2 text-sm font-medium text-gray-700 flex-shrink-0">
                    {day}
                  </div>

                  {/* Hour Cells */}
                  {HOURS.map((hour) => {
                    const index = dayIndex * 24 + hour;
                    const isAwake = formData.schedule_matrix[index] === 1;

                    return (
                      <div
                        key={hour}
                        onMouseDown={() => handleCellMouseDown(dayIndex, hour)}
                        onMouseEnter={() => handleCellMouseEnter(dayIndex, hour)}
                        className={`w-8 h-8 border border-gray-200 cursor-pointer transition-colors select-none ${
                          isAwake
                            ? 'bg-green-500 hover:bg-green-600'
                            : 'bg-gray-200 hover:bg-gray-300'
                        }`}
                        title={`${day} ${hour}:00 - ${isAwake ? 'Awake' : 'Sleep'}`}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          {/* Legend */}
          <div className="mt-4 flex items-center gap-6 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 bg-green-500 border border-gray-300 rounded"></div>
              <span className="text-gray-700">Awake (instances running)</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-4 bg-gray-200 border border-gray-300 rounded"></div>
              <span className="text-gray-700">Sleep (instances hibernated)</span>
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-end pt-4 border-t mt-6">
            <Button type="submit" variant="primary" icon={<FiSave />}>
              {existingSchedule ? 'Update Schedule' : 'Create Schedule'}
            </Button>
          </div>
        </Card>
      </form>

      {/* Info Card */}
      <Card>
        <div className="text-sm text-gray-600">
          <h4 className="font-medium text-gray-900 mb-2">How Hibernation Works</h4>
          <ul className="list-disc list-inside space-y-1">
            <li>Green cells = cluster stays awake, gray cells = cluster hibernates</li>
            <li>Pre-warm starts instances before the scheduled wake time</li>
            <li>Schedule is evaluated every hour based on the selected timezone</li>
            <li>Hibernation terminates spot instances and stops on-demand instances</li>
            <li>Workloads are automatically rescheduled when cluster wakes up</li>
            <li>Typical savings: 60-70% for dev/test environments</li>
          </ul>
        </div>
      </Card>
    </div>
  );
};

export default HibernationSchedule;
