/**
 * Interactive Weekly Grid for Schedule Management
 */
import React, { useState, useRef, useEffect } from 'react';
import { useHibernationStore } from '../../store/useHibernationStore';
import { Button, Card, Dropdown } from '../shared';
import { FiSave, FiTrash2, FiClock, FiInfo } from 'react-icons/fi';

const DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

const HibernationGrid = () => {
    const { schedule, updateScheduleLocal, saveSchedule, saving } = useHibernationStore();
    const [isPainting, setIsPainting] = useState(false);
    const [paintMode, setPaintMode] = useState(1); // 1 = Awake, 0 = Sleep
    const gridRef = useRef(null);

    // If no schedule loaded yet, don't render
    if (!schedule || !schedule.schedule_matrix) return null;

    // Handlers
    const handleCellMouseDown = (dayIndex, hourIndex) => {
        const index = dayIndex * 24 + hourIndex;
        const currentVal = schedule.schedule_matrix[index];
        const newVal = currentVal === 1 ? 0 : 1;
        setPaintMode(newVal);
        setIsPainting(true);
        updateCell(dayIndex, hourIndex, newVal);
    };

    const handleCellMouseEnter = (dayIndex, hourIndex) => {
        if (isPainting) {
            updateCell(dayIndex, hourIndex, paintMode);
        }
    };

    const handleMouseUp = () => {
        setIsPainting(false);
    };

    const updateCell = (dayIndex, hourIndex, value) => {
        const index = dayIndex * 24 + hourIndex;
        if (schedule.schedule_matrix[index] === value) return; // No change

        const newMatrix = [...schedule.schedule_matrix];
        newMatrix[index] = value;
        updateScheduleLocal({ schedule_matrix: newMatrix });
    };

    useEffect(() => {
        window.addEventListener('mouseup', handleMouseUp);
        return () => window.removeEventListener('mouseup', handleMouseUp);
    }, []);

    return (
        <Card className="border-gray-200">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
                <div>
                    <h3 className="text-lg font-semibold text-gray-900">Weekly Schedule</h3>
                    <p className="text-sm text-gray-500">Click and drag to set awake hours</p>
                </div>

                <div className="flex items-center gap-4 text-sm">
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-green-500 rounded shadow-sm"></div>
                        <span>Awake</span>
                    </div>
                    <div className="flex items-center gap-2">
                        <div className="w-4 h-4 bg-gray-100 border border-gray-200 rounded shadow-sm"></div>
                        <span>Sleep</span>
                    </div>
                    <div className="h-4 w-px bg-gray-300 mx-2"></div>
                    <Button
                        variant="primary"
                        onClick={saveSchedule}
                        loading={saving}
                        icon={<FiSave />}
                    >
                        Save Changes
                    </Button>
                </div>
            </div>

            <div className="overflow-x-auto pb-4" ref={gridRef}>
                <div className="inline-block min-w-[700px] w-full select-none">
                    {/* Header Row (Hours) */}
                    <div className="flex mb-2">
                        <div className="w-28 flex-shrink-0"></div>
                        <div className="flex-1 flex justify-between px-1">
                            {HOURS.filter(h => h % 3 === 0).map(h => (
                                <div key={h} className="text-xs text-gray-400 font-medium w-8 text-center">
                                    {h === 0 ? '12am' : h === 12 ? '12pm' : h > 12 ? `${h - 12}pm` : `${h}am`}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Grid Rows */}
                    <div className="space-y-1">
                        {DAYS.map((day, dayIndex) => (
                            <div key={day} className="flex items-center group">
                                {/* Day Label */}
                                <div className="w-28 flex-shrink-0 text-sm font-medium text-gray-600 pl-2">
                                    {day}
                                </div>

                                {/* Cells */}
                                <div className="flex-1 flex gap-[2px]">
                                    {HOURS.map(hour => {
                                        const index = dayIndex * 24 + hour;
                                        const isAwake = schedule.schedule_matrix[index] === 1;

                                        return (
                                            <div
                                                key={hour}
                                                onMouseDown={() => handleCellMouseDown(dayIndex, hour)}
                                                onMouseEnter={() => handleCellMouseEnter(dayIndex, hour)}
                                                className={`
                                            flex-1 h-10 rounded-sm cursor-pointer transition-all duration-75 relative
                                            ${isAwake
                                                        ? 'bg-green-500 hover:bg-green-400 shadow-sm'
                                                        : 'bg-gray-100 hover:bg-gray-200'
                                                    }
                                        `}
                                                title={`${day} ${hour}:00 - ${isAwake ? 'Awake' : 'Sleep'}`}
                                            >
                                                {/* Hover Tooltip/Time indicator could go here */}
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            <div className="mt-4 flex items-center gap-2 text-xs text-gray-400">
                <FiInfo className="w-3 h-3" />
                <span>Schedule is based on {schedule.timezone} timezone. Drag across cells to paint multiple hours.</span>
            </div>
        </Card>
    );
};

export default HibernationGrid;
