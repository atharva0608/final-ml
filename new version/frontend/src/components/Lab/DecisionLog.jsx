import React, { useState, useEffect } from 'react';
import { ScrollText, Terminal, AlignJustify, AlertCircle } from 'lucide-react';
import api from '../../services/api';

const DecisionLog = ({ activeModel, historyType, instanceId }) => {
    const isLive = historyType === 'live';
    const [experiments, setExperiments] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!isLive && instanceId) {
            const fetchExperiments = async () => {
                try {
                    setLoading(true);
                    const data = await api.getExperimentLogs(instanceId, 10);
                    setExperiments(data || []);
                } catch (error) {
                    console.error('Failed to fetch experiments:', error);
                    setExperiments([]);
                } finally {
                    setLoading(false);
                }
            };
            fetchExperiments();
        }
    }, [isLive, instanceId]);

    return (
        <div className="bg-slate-900 border border-slate-800 border-t-0 rounded-b-xl p-6 shadow-sm min-h-[300px] flex flex-col pt-2">
            {!isLive && (
                <div className="mb-4">
                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2">Past Experiments</h4>
                    {loading ? (
                        <div className="text-slate-400 text-xs py-4">Loading experiments...</div>
                    ) : experiments.length > 0 ? (
                        <table className="w-full text-xs text-left">
                            <thead className="text-slate-500 font-medium border-b border-slate-700">
                                <tr>
                                    <th className="pb-2">Time</th>
                                    <th className="pb-2">Model</th>
                                    <th className="pb-2">Outcome</th>
                                </tr>
                            </thead>
                            <tbody className="text-slate-400">
                                {experiments.map((exp, idx) => (
                                    <tr key={exp.id || idx}>
                                        <td className="py-2">{new Date(exp.created_at).toLocaleString()}</td>
                                        <td>{exp.model_version || 'Default'}</td>
                                        <td className={exp.cost_savings > 0 ? "text-emerald-600" : "text-slate-400"}>
                                            {exp.cost_savings > 0 ? `Saved $${exp.cost_savings.toFixed(2)}` : 'No savings'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : (
                        <div className="flex items-center gap-2 text-slate-500 text-xs py-4">
                            <AlertCircle className="w-4 h-4" />
                            <span>No experiment history available</span>
                        </div>
                    )}
                </div>
            )}

            {isLive && (
                <div className="flex-1 bg-slate-950 rounded-lg p-4 font-mono text-xs overflow-y-auto border border-slate-800 shadow-inner">
                    <div className="space-y-2">
                        <div className="text-slate-500 border-b border-slate-800 pb-2 mb-2 flex justify-between">
                            <span>Audit Stream: {activeModel}</span>
                            <span className="text-emerald-500 animate-pulse">● LIVE</span>
                        </div>
                        <div className="flex">
                            <span className="text-slate-500 w-20">10:00:05</span>
                            <span className="text-blue-400 font-bold mr-2">[Filter]</span>
                            <span className="text-slate-300">Found 3 candidate Spot types.</span>
                        </div>
                        <div className="flex">
                            <span className="text-slate-500 w-20">10:00:06</span>
                            <span className="text-purple-400 font-bold mr-2">[Model]</span>
                            <span className="text-slate-300">Predicted Risk 0.15 (Safe).</span>
                        </div>
                        <div className="flex">
                            <span className="text-slate-500 w-20">10:00:06</span>
                            <span className="text-emerald-400 font-bold mr-2">[Switch]</span>
                            <span className="text-slate-300">Triggering Spot Request...</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default DecisionLog;
