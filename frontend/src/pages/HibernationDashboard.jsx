import React, { useState, useEffect } from 'react';
import { FiPlus, FiCalendar, FiClock, FiLayers, FiActivity, FiPause, FiPlay, FiTrash2, FiEdit2, FiCheckCircle } from 'react-icons/fi';
import { hibernationAPI, clusterAPI } from '../services/api';
import { toast } from 'react-hot-toast';
import HibernationWizard from '../components/hibernation/HibernationWizard';
import HistoryLog from '../components/hibernation/HistoryLog';

const HibernationDashboard = () => {
    const [schedules, setSchedules] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showWizard, setShowWizard] = useState(false);
    const [editingSchedule, setEditingSchedule] = useState(null);
    const [clusters, setClusters] = useState([]);

    // Fetch data
    const fetchData = async () => {
        setLoading(true);
        try {
            const [schedulesRes, clustersRes] = await Promise.all([
                hibernationAPI.list(),
                clusterAPI.list()
            ]);
            setSchedules(schedulesRes.data.schedules || []);
            setClusters(clustersRes.data || []);
        } catch (err) {
            console.error("Failed to load data:", err);
            toast.error("Failed to load hibernation schedules");
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchData();
    }, []);

    const handleCreateClick = () => {
        setEditingSchedule(null);
        setShowWizard(true);
    };

    const handleEditClick = (schedule) => {
        setEditingSchedule(schedule);
        setShowWizard(true);
    };

    const handleDeleteClick = async (id) => {
        if (!window.confirm("Are you sure you want to delete this schedule?")) return;
        try {
            await hibernationAPI.delete(id);
            toast.success("Schedule deleted");
            fetchData();
        } catch (err) {
            toast.error("Failed to delete schedule");
        }
    };

    const handleToggleClick = async (id) => {
        try {
            await hibernationAPI.toggle(id);
            toast.success("Schedule status updated");
            fetchData();
        } catch (err) {
            toast.error("Failed to toggle schedule");
        }
    };

    const getClusterNames = (ids) => {
        if (!ids || ids.length === 0) return "No clusters";
        const names = ids.map(id => clusters.find(c => c.id === id)?.name || "Unknown");
        if (names.length <= 3) return names.join(", ");
        return `${names.slice(0, 3).join(", ")} +${names.length - 3} more`;
    };

    const formatScheduleType = (type) => {
        return type.charAt(0).toUpperCase() + type.slice(1).toLowerCase();
    };

    return (
        <div className="p-6 max-w-7xl mx-auto">
            <div className="flex justify-between items-center mb-8">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Hibernation Schedules</h1>
                    <p className="text-gray-500 mt-1">Manage sleep/wake schedules across your clusters to optimize costs.</p>
                </div>
                <button
                    onClick={handleCreateClick}
                    className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
                >
                    <FiPlus className="w-5 h-5" />
                    Create Schedule
                </button>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-blue-100 text-blue-600 rounded-full">
                            <FiLayers className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Active Schedules</p>
                            <p className="text-2xl font-bold text-gray-900">
                                {schedules.filter(s => s.is_active).length}
                            </p>
                        </div>
                    </div>
                </div>
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-green-100 text-green-600 rounded-full">
                            <FiCheckCircle className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Managed Clusters</p>
                            <p className="text-2xl font-bold text-gray-900">
                                {new Set(schedules.flatMap(s => s.cluster_ids || [])).size}
                            </p>
                        </div>
                    </div>
                </div>
                {/* Placeholder for Savings */}
                <div className="bg-white p-6 rounded-lg shadow-sm border border-gray-200">
                    <div className="flex items-center gap-4">
                        <div className="p-3 bg-purple-100 text-purple-600 rounded-full">
                            <FiActivity className="w-6 h-6" />
                        </div>
                        <div>
                            <p className="text-sm text-gray-500">Est. Monthly Savings</p>
                            <p className="text-2xl font-bold text-gray-900">$1,250</p>
                        </div>
                    </div>
                </div>
            </div>

            {/* Schedules List */}
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
                <div className="px-6 py-4 border-b border-gray-200 bg-gray-50">
                    <h2 className="text-lg font-semibold text-gray-800">All Schedules</h2>
                </div>

                {loading ? (
                    <div className="p-8 text-center text-gray-500">Loading schedules...</div>
                ) : schedules.length === 0 ? (
                    <div className="p-12 text-center">
                        <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
                            <FiCalendar className="w-8 h-8 text-gray-400" />
                        </div>
                        <h3 className="text-lg font-medium text-gray-900 mb-2">No schedules found</h3>
                        <p className="text-gray-500 mb-6">Create your first hibernation schedule to start saving costs.</p>
                        <button
                            onClick={handleCreateClick}
                            className="inline-flex items-center gap-2 px-4 py-2 border border-blue-600 text-blue-600 rounded-md hover:bg-blue-50 transition-colors"
                        >
                            <FiPlus className="w-4 h-4" />
                            Create Schedule
                        </button>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="w-full text-left">
                            <thead className="bg-gray-50 text-gray-500 text-xs uppercase font-medium">
                                <tr>
                                    <th className="px-6 py-3">Name</th>
                                    <th className="px-6 py-3">Clusters</th>
                                    <th className="px-6 py-3">Type</th>
                                    <th className="px-6 py-3">Strategy</th>
                                    <th className="px-6 py-3">Status</th>
                                    <th className="px-6 py-3 text-right">Actions</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-200">
                                {schedules.map((schedule) => (
                                    <tr key={schedule.id} className="hover:bg-gray-50">
                                        <td className="px-6 py-4">
                                            <div className="font-medium text-gray-900">{schedule.name}</div>
                                            <div className="text-sm text-gray-500 truncate max-w-xs">{schedule.description}</div>
                                        </td>
                                        <td className="px-6 py-4 text-sm text-gray-600">
                                            {getClusterNames(schedule.cluster_ids)}
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                                {formatScheduleType(schedule.schedule_type)}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-sm text-gray-600">
                                            {schedule.strategy.replace('_', ' ')}
                                        </td>
                                        <td className="px-6 py-4">
                                            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${schedule.is_active
                                                ? 'bg-green-100 text-green-800'
                                                : 'bg-gray-100 text-gray-800'
                                                }`}>
                                                {schedule.is_active ? 'Active' : 'Paused'}
                                            </span>
                                        </td>
                                        <td className="px-6 py-4 text-right">
                                            <div className="flex items-center justify-end gap-3">
                                                <button
                                                    onClick={() => handleToggleClick(schedule.id)}
                                                    className={`p-1 rounded-full hover:bg-gray-200 ${schedule.is_active ? 'text-green-600' : 'text-gray-400'}`}
                                                    title={schedule.is_active ? "Pause Schedule" : "Resume Schedule"}
                                                >
                                                    {schedule.is_active ? <FiPause className="w-4 h-4" /> : <FiPlay className="w-4 h-4" />}
                                                </button>
                                                <button
                                                    onClick={() => handleEditClick(schedule)}
                                                    className="p-1 text-blue-600 rounded-full hover:bg-blue-100"
                                                    title="Edit"
                                                >
                                                    <FiEdit2 className="w-4 h-4" />
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteClick(schedule.id)}
                                                    className="p-1 text-red-600 rounded-full hover:bg-red-100"
                                                    title="Delete"
                                                >
                                                    <FiTrash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            {showWizard && (
                <HibernationWizard
                    schedule={editingSchedule}
                    clusters={clusters}
                    onClose={() => {
                        setShowWizard(false);
                        fetchData();
                    }}
                />
            )}

            {/* Global History Log */}
            <div className="mt-8">
                <HistoryLog />
            </div>
        </div>
    );
};

export default HibernationDashboard;
