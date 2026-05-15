import React from 'react';
import ScheduleCalendar from './ScheduleCalendar';

/**
 * Schedule Builder - integrates calendar with form controls
 * Used in Step 4 of ScheduleModal
 */
const ScheduleBuilder = ({
  scheduleMatrix,
  onChange,
  timezone,
  onTimezoneChange,
  preWarmMinutes,
  onPreWarmChange
}) => {
  const mockSchedule = {
    name: 'Preview',
    schedule_matrix: scheduleMatrix,
    timezone: timezone
  };

  return (
    <div className="space-y-6">
      {/* Interactive Calendar */}
      <ScheduleCalendar
        schedule={mockSchedule}
        editable={true}
        onChange={onChange}
      />

      {/* Configuration Options */}
      <div className="grid grid-cols-2 gap-4">
        {/* Timezone Selector */}
        <div>
          <label className="block font-medium mb-2">Timezone</label>
          <select
            value={timezone}
            onChange={(e) => onTimezoneChange(e.target.value)}
            className="w-full px-4 py-2 border rounded-lg"
          >
            <option value="UTC">UTC</option>
            <option value="America/New_York">America/New_York (EST)</option>
            <option value="America/Chicago">America/Chicago (CST)</option>
            <option value="America/Denver">America/Denver (MST)</option>
            <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
            <option value="America/Phoenix">America/Phoenix (MST - no DST)</option>
            <option value="Europe/London">Europe/London (GMT)</option>
            <option value="Europe/Paris">Europe/Paris (CET)</option>
            <option value="Asia/Tokyo">Asia/Tokyo (JST)</option>
            <option value="Asia/Singapore">Asia/Singapore (SGT)</option>
            <option value="Australia/Sydney">Australia/Sydney (AEDT)</option>
          </select>
          <p className="text-xs text-gray-600 mt-1">
            All schedule times are in this timezone
          </p>
        </div>

        {/* Pre-warm Minutes */}
        <div>
          <label className="block font-medium mb-2">Pre-warm Time</label>
          <div className="flex items-center space-x-2">
            <input
              type="number"
              value={preWarmMinutes}
              onChange={(e) => onPreWarmChange(parseInt(e.target.value) || 0)}
              className="w-full px-4 py-2 border rounded-lg"
              min="0"
              max="120"
              step="5"
            />
            <span className="text-gray-600">minutes</span>
          </div>
          <p className="text-xs text-gray-600 mt-1">
            Start waking {preWarmMinutes} min before scheduled time
          </p>
        </div>
      </div>

      {/* Schedule Tips */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <h4 className="font-bold text-blue-900 mb-2">💡 Schedule Tips</h4>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• <strong>Purple cells</strong> = Cluster sleeping (cost savings)</li>
          <li>• <strong>Green cells</strong> = Cluster awake (normal operation)</li>
          <li>• Click individual cells for fine-tuned control</li>
          <li>• Use quick action buttons for common patterns</li>
          <li>• Pre-warm time helps nodes be ready before wake time</li>
          <li>• Recommended: Leave at least 8h awake per day for maintenance</li>
        </ul>
      </div>
    </div>
  );
};

export default ScheduleBuilder;
