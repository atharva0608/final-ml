/**
 * Unified Schedule Grid Component
 *
 * Supports 4 scheduling modes:
 * 1. WEEKLY - 7 days × 24 hours (168 values)
 * 2. DAILY - 31 days on/off (31 values)
 * 3. MONTHLY - 31 days × 24 hours (744 values)
 * 4. HYBRID - Weekly pattern + date overrides
 */
import React, { useState, useRef, useEffect } from 'react';
import { useHibernationStore } from '../../store/useHibernationStore';
import { Button, Card } from '../shared';
import { FiSave, FiCalendar, FiClock, FiLayers, FiZap } from 'react-icons/fi';

const DAYS_SHORT = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const MONTHS_DAYS = Array.from({ length: 31 }, (_, i) => i + 1);

const UnifiedScheduleGrid = () => {
    const { schedule, updateScheduleLocal, saveSchedule, saving } = useHibernationStore();
    const [scheduleType, setScheduleType] = useState('WEEKLY');
    const [isPainting, setIsPainting] = useState(false);
    const [paintMode, setPaintMode] = useState(1);
    const gridRef = useRef(null);

    // Initialize schedule type from store
    useEffect(() => {
        if (schedule?.schedule_type) {
            setScheduleType(schedule.schedule_type);
        }
    }, [schedule?.schedule_type]);

    // Debug logging - only log on mount and when scheduleType changes
    useEffect(() => {
        console.log('UnifiedScheduleGrid - schedule:', schedule);
        console.log('UnifiedScheduleGrid - scheduleType:', scheduleType);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [scheduleType]); // Only depend on scheduleType, not schedule

    // Mouse up listener for painting — MUST be before any early returns
    useEffect(() => {
        const handleMouseUp = () => setIsPainting(false);
        window.addEventListener('mouseup', handleMouseUp);
        return () => window.removeEventListener('mouseup', handleMouseUp);
    }, []);

    if (!schedule || !schedule.schedule_matrix) {
        console.log('UnifiedScheduleGrid - No schedule or schedule_matrix, returning null');
        return (
            <Card className="border-gray-200">
                <div className="p-8 text-center text-gray-500">
                    <p>No schedule data available. Please select a cluster.</p>
                </div>
            </Card>
        );
    }

    // Handle schedule type change
    const handleTypeChange = (newType) => {
        let newMatrix = [];
        switch (newType) {
            case 'WEEKLY':
                newMatrix = Array(168).fill(1);
                break;
            case 'DAILY':
                newMatrix = Array(31).fill(1);
                break;
            case 'MONTHLY':
                newMatrix = Array(744).fill(1);
                break;
            case 'HYBRID':
                newMatrix = Array(168).fill(1);
                break;
            default:
                newMatrix = Array(168).fill(1);
        }
        setScheduleType(newType);
        updateScheduleLocal({
            schedule_type: newType,
            schedule_matrix: newMatrix,
            date_overrides: newType === 'HYBRID' ? {} : undefined
        });
    };

    // Painting handlers
    const handleCellMouseDown = (index) => {
        const currentVal = schedule.schedule_matrix[index];
        const newVal = currentVal === 1 ? 0 : 1;
        setPaintMode(newVal);
        setIsPainting(true);
        updateCell(index, newVal);
    };

    const handleCellMouseEnter = (index) => {
        if (isPainting) {
            updateCell(index, paintMode);
        }
    };

    const handleMouseUp = () => {
        setIsPainting(false);
    };

    const updateCell = (index, value) => {
        if (schedule.schedule_matrix[index] === value) return;
        const newMatrix = [...schedule.schedule_matrix];
        newMatrix[index] = value;
        updateScheduleLocal({ schedule_matrix: newMatrix });
    };

    // Render different grid types
    const renderWeeklyGrid = () => (
        <div className="overflow-x-auto">
            <div className="inline-block min-w-full">
                {/* Hour labels */}
                <div className="flex mb-2">
                    <div className="w-20 flex-shrink-0"></div>
                    <div className="flex-1 flex justify-between px-1">
                        {Array.from({ length: 8 }, (_, i) => i * 3).map(h => (
                            <div key={h} className="text-xs text-gray-400 font-medium w-8 text-center">
                                {h === 0 ? '12am' : h === 12 ? '12pm' : h > 12 ? `${h - 12}pm` : `${h}am`}
                            </div>
                        ))}
                    </div>
                </div>

                {/* Grid rows */}
                <div className="space-y-1">
                    {DAYS_SHORT.map((day, dayIndex) => (
                        <div key={day} className="flex items-center">
                            <div className="w-20 flex-shrink-0 text-sm font-medium text-gray-600">
                                {day}
                            </div>
                            <div className="flex-1 flex gap-[2px]">
                                {Array.from({ length: 24 }, (_, hour) => {
                                    const index = dayIndex * 24 + hour;
                                    const isAwake = schedule.schedule_matrix[index] === 1;
                                    return (
                                        <div
                                            key={hour}
                                            onMouseDown={() => handleCellMouseDown(index)}
                                            onMouseEnter={() => handleCellMouseEnter(index)}
                                            className={`flex-1 h-8 rounded-sm cursor-pointer transition-all duration-75 ${isAwake ? 'bg-green-500 hover:bg-green-400' : 'bg-gray-200 hover:bg-gray-300'
                                                }`}
                                            title={`${day} ${hour}:00 - ${isAwake ? 'Awake' : 'Sleep'}`}
                                        />
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );

    const renderDailyGrid = () => (
        <div className="grid grid-cols-7 gap-2">
            {MONTHS_DAYS.map((day, index) => {
                if (index >= schedule.schedule_matrix.length) return null;
                const isAwake = schedule.schedule_matrix[index] === 1;
                return (
                    <div
                        key={day}
                        onMouseDown={() => handleCellMouseDown(index)}
                        onMouseEnter={() => handleCellMouseEnter(index)}
                        className={`h-16 rounded-lg cursor-pointer transition-all flex flex-col items-center justify-center ${isAwake ? 'bg-green-500 text-white hover:bg-green-400' : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
                            }`}
                        title={`Day ${day} - ${isAwake ? 'Awake' : 'Sleep'}`}
                    >
                        <div className="text-2xl font-bold">{day}</div>
                        <div className="text-xs">{isAwake ? 'ON' : 'OFF'}</div>
                    </div>
                );
            })}
        </div>
    );

    const renderMonthlyGrid = () => {
        const hoursPerDay = 24;
        return (
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
                <div className="inline-block min-w-full">
                    {/* Hour labels */}
                    <div className="flex mb-2 sticky top-0 bg-white z-10">
                        <div className="w-12 flex-shrink-0"></div>
                        <div className="flex-1 flex justify-between px-1">
                            {Array.from({ length: 6 }, (_, i) => i * 4).map(h => (
                                <div key={h} className="text-xs text-gray-400 font-medium text-center">
                                    {h === 0 ? '12am' : h === 12 ? '12pm' : h > 12 ? `${h - 12}pm` : `${h}am`}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Grid rows */}
                    <div className="space-y-1">
                        {MONTHS_DAYS.map((day, dayIndex) => (
                            <div key={day} className="flex items-center">
                                <div className="w-12 flex-shrink-0 text-xs font-medium text-gray-600">
                                    Day {day}
                                </div>
                                <div className="flex-1 flex gap-[1px]">
                                    {Array.from({ length: hoursPerDay }, (_, hour) => {
                                        const index = dayIndex * hoursPerDay + hour;
                                        if (index >= schedule.schedule_matrix.length) return null;
                                        const isAwake = schedule.schedule_matrix[index] === 1;
                                        return (
                                            <div
                                                key={hour}
                                                onMouseDown={() => handleCellMouseDown(index)}
                                                onMouseEnter={() => handleCellMouseEnter(index)}
                                                className={`flex-1 h-6 rounded-sm cursor-pointer transition-all duration-75 ${isAwake ? 'bg-green-500 hover:bg-green-400' : 'bg-gray-200 hover:bg-gray-300'
                                                    }`}
                                                title={`Day ${day}, ${hour}:00 - ${isAwake ? 'Awake' : 'Sleep'}`}
                                            />
                                        );
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        );
    };

    const renderHybridGrid = () => (
        <div>
            {/* Weekly base pattern */}
            <div className="mb-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Base Weekly Pattern</h4>
                {renderWeeklyGrid()}
            </div>

            {/* Date overrides */}
            <div className="border-t pt-4">
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Date-Specific Overrides</h4>
                <p className="text-xs text-gray-500 mb-3">
                    Add specific dates that override the weekly pattern (e.g., holidays, maintenance windows)
                </p>
                {/* TODO: Add date picker for overrides */}
                <div className="text-center text-sm text-gray-400 py-4 border-2 border-dashed border-gray-200 rounded-lg">
                    Date override picker coming soon
                </div>
            </div>
        </div>
    );

    const scheduleTypes = [
        { value: 'WEEKLY', label: 'Weekly', icon: FiClock, desc: '7 days × 24 hours' },
        { value: 'DAILY', label: 'Daily', icon: FiCalendar, desc: '31 days on/off' },
        { value: 'MONTHLY', label: 'Monthly', icon: FiLayers, desc: '31 days × 24 hours' },
        { value: 'HYBRID', label: 'Hybrid', icon: FiZap, desc: 'Weekly + overrides' }
    ];

    return (
        <Card className="border-gray-200">
            {/* Header with type selector */}
            <div className="mb-6">
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900">Schedule Configuration</h3>
                        <p className="text-sm text-gray-500">Define when your cluster should be awake or asleep</p>
                    </div>
                    <Button
                        variant="primary"
                        onClick={saveSchedule}
                        loading={saving}
                        icon={<FiSave />}
                        disabled={!schedule}
                    >
                        Save Schedule
                    </Button>
                </div>

                {/* Schedule Type Selector */}
                <div className="grid grid-cols-4 gap-3">
                    {scheduleTypes.map(type => {
                        const Icon = type.icon;
                        const isSelected = scheduleType === type.value;
                        return (
                            <button
                                key={type.value}
                                onClick={() => handleTypeChange(type.value)}
                                className={`p-3 rounded-lg border-2 transition-all text-left ${isSelected
                                        ? 'border-blue-500 bg-blue-50 shadow-sm'
                                        : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
                                    }`}
                            >
                                <div className="flex items-center gap-2 mb-1">
                                    <Icon className={`w-4 h-4 ${isSelected ? 'text-blue-600' : 'text-gray-500'}`} />
                                    <span className={`font-semibold text-sm ${isSelected ? 'text-blue-900' : 'text-gray-900'}`}>
                                        {type.label}
                                    </span>
                                </div>
                                <p className={`text-xs ${isSelected ? 'text-blue-700' : 'text-gray-500'}`}>
                                    {type.desc}
                                </p>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Legend */}
            <div className="flex items-center gap-4 mb-4 text-sm">
                <div className="flex items-center gap-2">
                    <div className="w-4 h-4 bg-green-500 rounded shadow-sm"></div>
                    <span>Awake</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-4 h-4 bg-gray-200 border border-gray-300 rounded shadow-sm"></div>
                    <span>Sleep</span>
                </div>
                <div className="ml-auto text-xs text-gray-500">
                    Click and drag to paint schedule
                </div>
            </div>

            {/* Grid based on selected type */}
            <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
                {scheduleType === 'WEEKLY' && renderWeeklyGrid()}
                {scheduleType === 'DAILY' && renderDailyGrid()}
                {scheduleType === 'MONTHLY' && renderMonthlyGrid()}
                {scheduleType === 'HYBRID' && renderHybridGrid()}
            </div>

            {/* Stats */}
            <div className="mt-4 flex items-center justify-between text-sm">
                <div className="text-gray-600">
                    <span className="font-semibold">
                        {schedule.schedule_matrix.filter(h => h === 1).length}
                    </span>
                    {' / '}
                    <span>{schedule.schedule_matrix.length}</span>
                    {' hours active'}
                </div>
                <div className="text-gray-500">
                    Timezone: <span className="font-semibold">{schedule.timezone}</span>
                </div>
            </div>
        </Card>
    );
};

export default UnifiedScheduleGrid;
