import React, { useState } from 'react';

/**
 * ScheduleMatrix - 168-hour grid (7 days × 24 hours)
 *
 * Allows selecting continuous time periods across days.
 * Example: Saturday 9am to Sunday 9pm = mark hours continuously
 */
const ScheduleMatrix = ({ value, onChange }) => {
  const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const HOURS = Array.from({ length: 24 }, (_, i) => i);

  // Value is a 168-bit string: '1' = sleep, '0' = awake
  // Index = (day * 24) + hour
  const matrix = value || '0'.repeat(168);

  const [isDragging, setIsDragging] = useState(false);
  const [dragMode, setDragMode] = useState(null); // 'sleep' or 'awake'

  const getCellIndex = (day, hour) => (day * 24) + hour;

  const isSleeping = (day, hour) => {
    const idx = getCellIndex(day, hour);
    return matrix[idx] === '1';
  };

  const toggleCell = (day, hour) => {
    const idx = getCellIndex(day, hour);
    const newMatrix = matrix.split('');
    newMatrix[idx] = matrix[idx] === '1' ? '0' : '1';
    onChange(newMatrix.join(''));
  };

  const handleMouseDown = (day, hour) => {
    setIsDragging(true);
    const currentState = isSleeping(day, hour);
    setDragMode(currentState ? 'awake' : 'sleep');
    toggleCell(day, hour);
  };

  const handleMouseEnter = (day, hour) => {
    if (isDragging) {
      const idx = getCellIndex(day, hour);
      const newMatrix = matrix.split('');
      newMatrix[idx] = dragMode === 'sleep' ? '1' : '0';
      onChange(newMatrix.join(''));
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
    setDragMode(null);
  };

  // Quick presets
  const applyPreset = (preset) => {
    let newMatrix = '0'.repeat(168);

    if (preset === 'weeknights') {
      // Mon-Fri 8pm-8am (12 hours × 5 days = 60 hours)
      for (let day = 0; day < 5; day++) {
        for (let hour = 20; hour < 24; hour++) {
          const idx = getCellIndex(day, hour);
          newMatrix = newMatrix.substring(0, idx) + '1' + newMatrix.substring(idx + 1);
        }
        for (let hour = 0; hour < 8; hour++) {
          const idx = getCellIndex(day, hour);
          newMatrix = newMatrix.substring(0, idx) + '1' + newMatrix.substring(idx + 1);
        }
      }
    } else if (preset === 'weekends') {
      // Sat-Sun full days (48 hours)
      for (let day = 5; day < 7; day++) {
        for (let hour = 0; hour < 24; hour++) {
          const idx = getCellIndex(day, hour);
          newMatrix = newMatrix.substring(0, idx) + '1' + newMatrix.substring(idx + 1);
        }
      }
    } else if (preset === 'nights') {
      // All nights 10pm-6am (8 hours × 7 days = 56 hours)
      for (let day = 0; day < 7; day++) {
        for (let hour = 22; hour < 24; hour++) {
          const idx = getCellIndex(day, hour);
          newMatrix = newMatrix.substring(0, idx) + '1' + newMatrix.substring(idx + 1);
        }
        for (let hour = 0; hour < 6; hour++) {
          const idx = getCellIndex(day, hour);
          newMatrix = newMatrix.substring(0, idx) + '1' + newMatrix.substring(idx + 1);
        }
      }
    }

    onChange(newMatrix);
  };

  const clearAll = () => onChange('0'.repeat(168));
  const fillAll = () => onChange('1'.repeat(168));

  // Calculate stats
  const sleepHours = (matrix.match(/1/g) || []).length;
  const awakeHours = 168 - sleepHours;
  const savingsPercent = Math.round((sleepHours / 168) * 100);

  return (
    <div className="space-y-4">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-indigo-50 border border-indigo-200 rounded-lg p-3">
          <div className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">Sleep Hours</div>
          <div className="text-2xl font-bold text-indigo-900">{sleepHours}h</div>
          <div className="text-xs text-indigo-600">of 168h/week</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg p-3">
          <div className="text-xs font-semibold text-green-600 uppercase tracking-wide">Est. Savings</div>
          <div className="text-2xl font-bold text-green-900">{savingsPercent}%</div>
          <div className="text-xs text-green-600">per week</div>
        </div>
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
          <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Awake Hours</div>
          <div className="text-2xl font-bold text-gray-900">{awakeHours}h</div>
          <div className="text-xs text-gray-600">cluster active</div>
        </div>
      </div>

      {/* Quick Presets */}
      <div className="flex gap-2">
        <button onClick={() => applyPreset('weeknights')} className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-md transition-colors">
          Business Hours (M-F 8pm-8am)
        </button>
        <button onClick={() => applyPreset('weekends')} className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-md transition-colors">
          Weekends (Sat-Sun)
        </button>
        <button onClick={() => applyPreset('nights')} className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-md transition-colors">
          Nights Only (10pm-6am)
        </button>
        <button onClick={clearAll} className="px-3 py-1.5 text-xs font-medium bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-md transition-colors ml-auto">
          Clear All
        </button>
      </div>

      {/* Matrix Grid */}
      <div className="border border-gray-200 rounded-lg overflow-hidden bg-white" onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp}>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className="sticky left-0 z-10 bg-gray-50 border-b border-r border-gray-200 p-2 text-xs font-semibold text-gray-700 w-20"></th>
                {HOURS.map(hour => (
                  <th key={hour} className="bg-gray-50 border-b border-gray-200 p-1 text-xs font-medium text-gray-600 min-w-[28px]">
                    {hour.toString().padStart(2, '0')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DAYS.map((day, dayIdx) => (
                <tr key={day}>
                  <td className="sticky left-0 z-10 bg-gray-50 border-r border-gray-200 p-2 text-xs font-semibold text-gray-700">
                    {day}
                  </td>
                  {HOURS.map(hour => {
                    const sleeping = isSleeping(dayIdx, hour);
                    return (
                      <td
                        key={hour}
                        className={`border border-gray-100 cursor-pointer transition-colors select-none ${
                          sleeping
                            ? 'bg-indigo-500 hover:bg-indigo-600'
                            : 'bg-gray-50 hover:bg-gray-200'
                        }`}
                        style={{ width: '28px', height: '28px' }}
                        onMouseDown={() => handleMouseDown(dayIdx, hour)}
                        onMouseEnter={() => handleMouseEnter(dayIdx, hour)}
                      >
                        <div className="w-full h-full" />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-6 text-xs text-gray-600">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-indigo-500 border border-indigo-600 rounded"></div>
          <span>Cluster Sleeping</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-gray-50 border border-gray-300 rounded"></div>
          <span>Cluster Awake</span>
        </div>
        <div className="ml-auto text-gray-500">
          Click and drag to paint schedule
        </div>
      </div>
    </div>
  );
};

export default ScheduleMatrix;
