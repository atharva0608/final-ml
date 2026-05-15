import React, { useState } from 'react';
import { Card, Button } from '../shared';
import { FiPlus, FiGlobe, FiClock, FiTrash2, FiUsers } from 'react-icons/fi';

const MultiTimezone = () => {
    const [teams, setTeams] = useState([
        { id: 1, name: 'US Engineering', timezone: 'America/Los_Angeles', start: '09:00', end: '18:00' },
        { id: 2, name: 'EMEA Ops', timezone: 'Europe/London', start: '09:00', end: '17:00' },
    ]);

    return (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Team List */}
            <div className="lg:col-span-2 space-y-4">
                <div className="flex justify-between items-center mb-2">
                    <h3 className="text-lg font-semibold text-gray-900">Team Schedules</h3>
                    <Button variant="outline" size="sm" icon={<FiPlus />}>Add Team</Button>
                </div>

                {teams.map((team) => (
                    <Card key={team.id} className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
                        <div className="p-3 bg-indigo-50 rounded-full text-indigo-600">
                            <FiUsers className="w-5 h-5" />
                        </div>
                        <div className="flex-1">
                            <h4 className="font-semibold text-gray-900">{team.name}</h4>
                            <div className="flex items-center gap-2 text-sm text-gray-600 mt-1">
                                <FiGlobe className="w-3 h-3" />
                                <span>{team.timezone}</span>
                                <span className="mx-1">•</span>
                                <FiClock className="w-3 h-3" />
                                <span>{team.start} - {team.end}</span>
                            </div>
                        </div>

                        <div className="text-right text-sm">
                            <div className="text-gray-500">Current Time</div>
                            <div className="font-mono font-medium text-gray-900">
                                {new Date().toLocaleTimeString('en-US', { timeZone: team.timezone, hour: '2-digit', minute: '2-digit' })}
                            </div>
                        </div>

                        <button className="text-gray-400 hover:text-red-500 p-2">
                            <FiTrash2 />
                        </button>
                    </Card>
                ))}
            </div>

            {/* Aggregation Strategy */}
            <div>
                <Card className="sticky top-24">
                    <h3 className="text-md font-semibold text-gray-900 mb-4">Merge Strategy</h3>

                    <div className="space-y-4">
                        <label className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50">
                            <input type="radio" name="strategy" className="mt-1" defaultChecked />
                            <div>
                                <span className="font-medium text-gray-900 block">Conservative (Union)</span>
                                <span className="text-xs text-gray-500 block mt-1">
                                    Wake if ANY team is active. Safest for availability.
                                </span>
                            </div>
                        </label>

                        <label className="flex items-start gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50">
                            <input type="radio" name="strategy" className="mt-1" />
                            <div>
                                <span className="font-medium text-gray-900 block">Optimized (Intersection)</span>
                                <span className="text-xs text-gray-500 block mt-1">
                                    Wake only when ALL teams overlap (Aggressive savings).
                                </span>
                            </div>
                        </label>
                    </div>

                    <div className="mt-6 pt-6 border-t border-gray-100">
                        <div className="flex justify-between items-center mb-2">
                            <span className="text-sm text-gray-600">Effective Active Hours</span>
                            <span className="text-sm font-medium">14h / day</span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                            <div className="bg-green-500 h-full w-[60%]"></div>
                        </div>
                        <p className="text-xs text-gray-500 mt-2 text-center">
                            Cluster will be awake from 4am to 6pm UTC
                        </p>
                    </div>

                    <Button variant="primary" className="w-full mt-6">Apply Team Schedule</Button>
                </Card>
            </div>
        </div>
    );
};

export default MultiTimezone;
