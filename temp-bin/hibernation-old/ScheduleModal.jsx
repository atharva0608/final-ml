import React, { useState, useEffect } from 'react';
import { hibernationApi, generateScheduleMatrix } from '../../services/hibernationApi';
import StrategySelector from './StrategySelector';
import ScheduleBuilder from './ScheduleBuilder';

const ScheduleModal = ({ isOpen, onClose, schedule = null, clusters = [] }) => {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    strategy: 'NAMESPACE_SLEEP',
    cluster_ids: [],
    schedule_type: 'WEEKLY',
    schedule_matrix: generateScheduleMatrix('weekends'),
    timezone: 'UTC',
    pre_warm_minutes: 30,
    is_active: true
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (schedule) {
      setFormData({
        name: schedule.name,
        description: schedule.description || '',
        strategy: schedule.strategy,
        cluster_ids: schedule.clusters?.map(c => c.id) || [],
        schedule_type: schedule.schedule_type,
        schedule_matrix: schedule.schedule_matrix,
        timezone: schedule.timezone,
        pre_warm_minutes: schedule.pre_warm_minutes,
        is_active: schedule.is_active === 'Y'
      });
    }
  }, [schedule]);

  const handleSave = async () => {
    try {
      setLoading(true);
      setError(null);

      if (schedule) {
        await hibernationApi.updateSchedule(schedule.id, formData);
      } else {
        await hibernationApi.createSchedule(formData);
      }

      onClose(true); // true = refresh list
    } catch (err) {
      setError(err.response?.data?.message || 'Failed to save schedule');
    } finally {
      setLoading(false);
    }
  };

  const handleNext = () => {
    if (step < 4) setStep(step + 1);
    else handleSave();
  };

  const handleBack = () => {
    if (step > 1) setStep(step - 1);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="p-6 border-b flex justify-between items-center sticky top-0 bg-white">
          <h2 className="text-2xl font-bold">
            {schedule ? 'Edit' : 'New'} Hibernation Schedule
          </h2>
          <button onClick={() => onClose(false)} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        {/* Progress Steps */}
        <div className="p-6 border-b bg-gray-50">
          <div className="flex items-center justify-between">
            {['Basic Info', 'Strategy', 'Clusters', 'Schedule'].map((label, idx) => (
              <div key={idx} className="flex items-center">
                <div className={`
                  w-10 h-10 rounded-full flex items-center justify-center font-bold
                  ${step > idx + 1 ? 'bg-green-500 text-white' :
                    step === idx + 1 ? 'bg-blue-500 text-white' :
                    'bg-gray-300 text-gray-600'}
                `}>
                  {step > idx + 1 ? '✓' : idx + 1}
                </div>
                <span className="ml-2 font-medium">{label}</span>
                {idx < 3 && <div className="w-12 h-1 bg-gray-300 mx-4" />}
              </div>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="p-6">
          {error && (
            <div className="mb-4 p-4 bg-red-100 text-red-800 rounded">
              {error}
            </div>
          )}

          {/* Step 1: Basic Info */}
          {step === 1 && (
            <div className="space-y-4">
              <div>
                <label className="block font-medium mb-2">Schedule Name *</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                  className="w-full px-4 py-2 border rounded-lg"
                  placeholder="Weekend Shutdown"
                />
              </div>
              <div>
                <label className="block font-medium mb-2">Description (optional)</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  className="w-full px-4 py-2 border rounded-lg"
                  rows="3"
                  placeholder="Hibernate prod clusters on weekends"
                />
              </div>
            </div>
          )}

          {/* Step 2: Strategy */}
          {step === 2 && (
            <StrategySelector
              selected={formData.strategy}
              onSelect={(strategy) => setFormData(prev => ({ ...prev, strategy }))}
            />
          )}

          {/* Step 3: Clusters */}
          {step === 3 && (
            <div className="space-y-4">
              <h3 className="font-bold">Select Clusters to Hibernate</h3>
              {clusters.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  No clusters available. Please add clusters first.
                </div>
              ) : (
                <div className="space-y-2">
                  {clusters.map(cluster => (
                    <label key={cluster.id} className="flex items-center p-3 border rounded hover:bg-gray-50 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.cluster_ids.includes(cluster.id)}
                        onChange={(e) => {
                          const checked = e.target.checked;
                          setFormData(prev => ({
                            ...prev,
                            cluster_ids: checked
                              ? [...prev.cluster_ids, cluster.id]
                              : prev.cluster_ids.filter(id => id !== cluster.id)
                          }));
                        }}
                        className="mr-3"
                      />
                      <div>
                        <div className="font-medium">{cluster.name}</div>
                        <div className="text-sm text-gray-600">
                          {cluster.region} • {cluster.node_count || 0} nodes
                        </div>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Step 4: Schedule */}
          {step === 4 && (
            <ScheduleBuilder
              scheduleMatrix={formData.schedule_matrix}
              onChange={(matrix) => setFormData(prev => ({ ...prev, schedule_matrix: matrix }))}
              timezone={formData.timezone}
              onTimezoneChange={(tz) => setFormData(prev => ({ ...prev, timezone: tz }))}
              preWarmMinutes={formData.pre_warm_minutes}
              onPreWarmChange={(mins) => setFormData(prev => ({ ...prev, pre_warm_minutes: mins }))}
            />
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t flex justify-between">
          <button
            onClick={handleBack}
            disabled={step === 1}
            className="px-6 py-2 border rounded-lg disabled:opacity-50"
          >
            Back
          </button>
          <div className="space-x-2">
            <button
              onClick={() => onClose(false)}
              className="px-6 py-2 border rounded-lg"
            >
              Cancel
            </button>
            <button
              onClick={handleNext}
              disabled={loading || (step === 3 && formData.cluster_ids.length === 0)}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {loading ? 'Saving...' : step === 4 ? 'Save Schedule' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ScheduleModal;
