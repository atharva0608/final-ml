import React, { useState } from 'react';
import { Card, Button, Input, Dropdown } from '../shared';
import { FiPlus, FiTrash2, FiClock, FiAlertCircle } from 'react-icons/fi';

const TimeBasedRules = () => {
    const [rules, setRules] = useState([
        { id: 1, type: 'WAKE', day: 'mon-fri', time: '08:00', priority: 'HIGH', active: true },
        { id: 2, type: 'SLEEP', day: 'mon-fri', time: '20:00', priority: 'MEDIUM', active: true },
    ]);

    const addRule = () => {
        const newRule = {
            id: Date.now(),
            type: 'WAKE',
            day: 'daily',
            time: '09:00',
            priority: 'MEDIUM',
            active: true
        };
        setRules([...rules, newRule]);
    };

    const removeRule = (id) => {
        setRules(rules.filter(r => r.id !== id));
    };

    return (
        <div className="space-y-6">
            <Card className="border-l-4 border-l-blue-500">
                <div className="flex items-start gap-4">
                    <FiAlertCircle className="w-5 h-5 text-blue-500 mt-1" />
                    <div>
                        <h4 className="font-medium text-gray-900">Rule-Based Scheduling</h4>
                        <p className="text-sm text-gray-500 mt-1">
                            Rules are evaluated in order. Higher priority rules override lower priority ones.
                            Use this for complex patterns that don't fit the weekly grid.
                        </p>
                    </div>
                </div>
            </Card>

            <div className="flex justify-end">
                <Button variant="outline" icon={<FiPlus />} onClick={addRule}>
                    Add Rule
                </Button>
            </div>

            <div className="space-y-3">
                {rules.map((rule) => (
                    <div key={rule.id} className="flex items-center gap-4 bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
                        <div className={`p-2 rounded-lg ${rule.type === 'WAKE' ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-700'}`}>
                            {rule.type === 'WAKE' ? <FiClock className="w-5 h-5" /> : <FiClock className="w-5 h-5" />}
                        </div>

                        <div className="flex-1 grid grid-cols-1 md:grid-cols-4 gap-4">
                            <div>
                                <label className="text-xs text-gray-500 block mb-1">Action</label>
                                <select
                                    className="w-full text-sm border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                    value={rule.type}
                                    onChange={(e) => {
                                        const newRules = rules.map(r => r.id === rule.id ? { ...r, type: e.target.value } : r);
                                        setRules(newRules);
                                    }}
                                >
                                    <option value="WAKE">Wake Cluster</option>
                                    <option value="SLEEP">Hibernate Cluster</option>
                                </select>
                            </div>

                            <div>
                                <label className="text-xs text-gray-500 block mb-1">When</label>
                                <select
                                    className="w-full text-sm border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                    value={rule.day}
                                    onChange={(e) => {
                                        const newRules = rules.map(r => r.id === rule.id ? { ...r, day: e.target.value } : r);
                                        setRules(newRules);
                                    }}
                                >
                                    <option value="daily">Every Day</option>
                                    <option value="mon-fri">Weekdays (Mon-Fri)</option>
                                    <option value="sat-sun">Weekends (Sat-Sun)</option>
                                    <option value="custom">Custom...</option>
                                </select>
                            </div>

                            <div>
                                <label className="text-xs text-gray-500 block mb-1">Time</label>
                                <Input
                                    type="time"
                                    value={rule.time}
                                    onChange={(e) => {
                                        const newRules = rules.map(r => r.id === rule.id ? { ...r, time: e.target.value } : r);
                                        setRules(newRules);
                                    }}
                                    className="h-9 text-sm"
                                />
                            </div>

                            <div>
                                <label className="text-xs text-gray-500 block mb-1">Priority</label>
                                <select
                                    className="w-full text-sm border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                    value={rule.priority}
                                    onChange={(e) => {
                                        const newRules = rules.map(r => r.id === rule.id ? { ...r, priority: e.target.value } : r);
                                        setRules(newRules);
                                    }}
                                >
                                    <option value="HIGH">High (Blocking)</option>
                                    <option value="MEDIUM">Medium</option>
                                    <option value="LOW">Low</option>
                                </select>
                            </div>
                        </div>

                        <button
                            onClick={() => removeRule(rule.id)}
                            className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                        >
                            <FiTrash2 className="w-5 h-5" />
                        </button>
                    </div>
                ))}
            </div>

            <div className="flex justify-end mt-6">
                <Button variant="primary">Apply Rules to Grid</Button>
            </div>
        </div>
    );
};

export default TimeBasedRules;
