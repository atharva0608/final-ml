import React, { useState, useEffect } from 'react';

/**
 * Visual Schedule Calendar - displays weekly hibernation schedule
 * Shows 168-hour matrix (7 days × 24 hours) with sleep/awake states
 */
const ScheduleCalendar = ({ schedule, editable = false, onChange }) => {
  const [matrix, setMatrix] = useState(new Array(168).fill('0'));
  const [hoveredCell, setHoveredCell] = useState(null);
  const [weekOffset, setWeekOffset] = useState(0);
  const [viewMode, setViewMode] = useState('week'); // week | compact

  useEffect(() => {
    if (schedule?.schedule_matrix) {
      setMatrix(schedule.schedule_matrix.split(''));
    } else {
      setMatrix(new Array(168).fill('0'));
    }
  }, [schedule]);

  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const hours = Array.from({ length: 24 }, (_, i) => i);

  const getCellState = (day, hour) => {
    const index = day * 24 + hour;
    return matrix[index];
  };

  const toggleCell = (day, hour) => {
    if (!editable) return;

    const index = day * 24 + hour;
    const newMatrix = [...matrix];
    newMatrix[index] = newMatrix[index] === '0' ? '1' : '0';
    setMatrix(newMatrix);

    if (onChange) {
      onChange(newMatrix.join(''));
    }
  };

  const fillBlock = (startDay, startHour, endDay, endHour, value) => {
    if (!editable) return;

    const newMatrix = [...matrix];
    for (let d = startDay; d <= endDay; d++) {
      const startH = d === startDay ? startHour : 0;
      const endH = d === endDay ? endHour : 23;
      for (let h = startH; h <= endH; h++) {
        newMatrix[d * 24 + h] = value;
      }
    }
    setMatrix(newMatrix);
    if (onChange) {
      onChange(newMatrix.join(''));
    }
  };

  const calculateStats = () => {
    const sleepCount = matrix.filter(c => c === '1').length;
    const awakeCount = 168 - sleepCount;
    const sleepPercentage = Math.round((sleepCount / 168) * 100);

    return {
      sleepHours: sleepCount,
      awakeHours: awakeCount,
      sleepPercentage,
      awakePercentage: 100 - sleepPercentage
    };
  };

  const stats = calculateStats();

  const getCellColor = (state) => {
    if (state === '1') {
      return 'bg-purple-600 border-purple-700'; // Sleeping
    }
    return 'bg-green-100 border-green-300'; // Awake
  };

  const formatHour = (hour) => {
    if (hour === 0) return '12a';
    if (hour < 12) return `${hour}a`;
    if (hour === 12) return '12p';
    return `${hour - 12}p`;
  };

  const getHoverInfo = (day, hour) => {
    const state = getCellState(day, hour);
    const dayName = days[day];
    const timeStr = `${String(hour).padStart(2, '0')}:00`;
    const status = state === '1' ? 'Sleeping 💤' : 'Awake 🟢';
    return `${dayName} ${timeStr} - ${status}`;
  };

  return (
    <div className="bg-white rounded-lg shadow-lg p-6 space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h3 className="text-xl font-bold">📅 Schedule Calendar</h3>
          {schedule && (
            <p className="text-sm text-gray-600 mt-1">
              {schedule.name} • {schedule.timezone}
            </p>
          )}
        </div>

        {/* Stats Summary */}
        <div className="flex space-x-4 text-sm">
          <div className="text-center">
            <div className="text-2xl font-bold text-purple-600">{stats.sleepHours}h</div>
            <div className="text-gray-600">Sleep ({stats.sleepPercentage}%)</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-green-600">{stats.awakeHours}h</div>
            <div className="text-gray-600">Awake ({stats.awakePercentage}%)</div>
          </div>
        </div>
      </div>

      {/* View Mode Selector */}
      <div className="flex space-x-2">
        <button
          onClick={() => setViewMode('week')}
          className={`px-3 py-1 rounded ${viewMode === 'week'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-700'
            }`}
        >
          Week View
        </button>
        <button
          onClick={() => setViewMode('compact')}
          className={`px-3 py-1 rounded ${viewMode === 'compact'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-200 text-gray-700'
            }`}
        >
          Compact View
        </button>
      </div>

      {/* Legend */}
      <div className="flex items-center space-x-4 text-sm p-3 bg-gray-50 rounded">
        <div className="flex items-center space-x-2">
          <div className="w-6 h-6 bg-green-100 border-2 border-green-300 rounded"></div>
          <span>Awake 🟢</span>
        </div>
        <div className="flex items-center space-x-2">
          <div className="w-6 h-6 bg-purple-600 border-2 border-purple-700 rounded"></div>
          <span>Sleeping 💤</span>
        </div>
        {editable && (
          <span className="text-gray-600 ml-auto">
            💡 Click cells to toggle, or use quick templates above
          </span>
        )}
      </div>

      {/* Calendar Grid - Week View */}
      {viewMode === 'week' && (
        <div className="overflow-x-auto">
          <div className="inline-block min-w-full">
            {/* Hour Headers */}
            <div className="flex">
              <div className="w-24 flex-shrink-0"></div>
              <div className="flex">
                {hours.map(hour => (
                  <div
                    key={hour}
                    className="w-8 text-xs text-center text-gray-600 font-medium"
                    title={`${String(hour).padStart(2, '0')}:00`}
                  >
                    {hour % 6 === 0 ? formatHour(hour) : ''}
                  </div>
                ))}
              </div>
            </div>

            {/* Day Rows */}
            {days.map((day, dayIndex) => (
              <div key={day} className="flex items-center mt-1">
                {/* Day Label */}
                <div className="w-24 flex-shrink-0 text-sm font-medium text-gray-700">
                  {day.substring(0, 3)}
                </div>

                {/* Hour Cells */}
                <div className="flex">
                  {hours.map(hour => {
                    const state = getCellState(dayIndex, hour);
                    return (
                      <div
                        key={hour}
                        className={`
                          w-8 h-8 border cursor-pointer transition-all
                          ${getCellColor(state)}
                          ${hoveredCell === `${dayIndex}-${hour}` ? 'ring-2 ring-blue-400 scale-110 z-10' : ''}
                          ${editable ? 'hover:opacity-70' : ''}
                        `}
                        onClick={() => toggleCell(dayIndex, hour)}
                        onMouseEnter={() => setHoveredCell(`${dayIndex}-${hour}`)}
                        onMouseLeave={() => setHoveredCell(null)}
                        title={getHoverInfo(dayIndex, hour)}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Compact View - Shows daily summary */}
      {viewMode === 'compact' && (
        <div className="space-y-2">
          {days.map((day, dayIndex) => {
            const daySleepHours = hours.filter(h => getCellState(dayIndex, h) === '1').length;
            const dayAwakeHours = 24 - daySleepHours;
            const sleepPercentage = Math.round((daySleepHours / 24) * 100);

            return (
              <div key={day} className="flex items-center space-x-3">
                <div className="w-24 text-sm font-medium">{day}</div>

                {/* Progress Bar */}
                <div className="flex-1 h-8 bg-gray-200 rounded overflow-hidden flex">
                  {hours.map(hour => {
                    const state = getCellState(dayIndex, hour);
                    return (
                      <div
                        key={hour}
                        className={`flex-1 ${state === '1' ? 'bg-purple-600' : 'bg-green-400'}`}
                        title={getHoverInfo(dayIndex, hour)}
                      />
                    );
                  })}
                </div>

                {/* Stats */}
                <div className="text-sm text-gray-700 w-32 text-right">
                  <span className="text-purple-600 font-bold">{daySleepHours}h</span>
                  {' / '}
                  <span className="text-green-600 font-bold">{dayAwakeHours}h</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Quick Actions (if editable) */}
      {editable && (
        <div className="border-t pt-4">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => fillBlock(5, 0, 6, 23, '1')}
              className="px-3 py-1 bg-blue-100 text-blue-800 rounded hover:bg-blue-200 text-sm"
            >
              ☕ Sleep Weekends
            </button>
            <button
              onClick={() => fillBlock(0, 0, 4, 7, '1')}
              className="px-3 py-1 bg-purple-100 text-purple-800 rounded hover:bg-purple-200 text-sm"
            >
              🌙 Sleep Weeknight Nights (00:00-08:00)
            </button>
            <button
              onClick={() => fillBlock(0, 18, 4, 23, '1')}
              className="px-3 py-1 bg-purple-100 text-purple-800 rounded hover:bg-purple-200 text-sm"
            >
              🌙 Sleep Weeknight Evenings (18:00-00:00)
            </button>
            <button
              onClick={() => setMatrix(new Array(168).fill('0'))}
              className="px-3 py-1 bg-green-100 text-green-800 rounded hover:bg-green-200 text-sm"
            >
              🟢 Clear All (Always Awake)
            </button>
            <button
              onClick={() => setMatrix(new Array(168).fill('1'))}
              className="px-3 py-1 bg-gray-100 text-gray-800 rounded hover:bg-gray-200 text-sm"
            >
              💤 Fill All (Always Sleep)
            </button>
          </div>
        </div>
      )}

      {/* Timezone Warning */}
      {schedule?.timezone && schedule.timezone !== 'UTC' && (
        <div className="text-xs text-amber-700 bg-amber-50 p-2 rounded">
          ⚠️ Times shown are in <strong>{schedule.timezone}</strong> timezone
        </div>
      )}
    </div>
  );
};

export default ScheduleCalendar;
