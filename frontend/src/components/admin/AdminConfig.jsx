import React, { useState, useEffect } from 'react';
import { Card, Button } from '../shared';
import { FiShield, FiAlertCircle, FiRefreshCw, FiLoader } from 'react-icons/fi';
import { api } from '../../services/api';
import toast from 'react-hot-toast';
import PlatformSettings from './PlatformSettings';

const AdminConfig = () => {
    const [safeMode, setSafeMode] = useState(true);
    const [agentVersion, setAgentVersion] = useState('v1.4.2');
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const response = await api.get('/api/v1/admin/config/SAFE_MODE');
                setSafeMode(response.data.value === true || response.data.value === 'True' || response.data.value === 'true');
            } catch (error) {
                console.error('Failed to fetch Safe Mode status:', error);
                setSafeMode(true);
            } finally { setLoading(false); }
        };
        fetchConfig();
    }, []);

    const handleSafeModeToggle = async () => {
        const newValue = !safeMode;
        if (safeMode && !window.confirm('⚠️ WARNING: Disabling Safe Mode will allow the system to take automated actions on clusters.\n\nAre you sure you want to enable automated actions?')) return;
        setSaving(true);
        try {
            await api.patch('/api/v1/admin/config', { key: 'SAFE_MODE', value: newValue });
            setSafeMode(newValue);
            toast.success(newValue ? 'Safe Mode enabled - Dry run only' : 'Safe Mode disabled - Automated actions enabled');
        } catch (error) {
            console.error('Failed to update Safe Mode:', error);
            toast.error('Failed to update Safe Mode');
        } finally { setSaving(false); }
    };

    if (loading) return (<div className="flex items-center justify-center h-64"><FiLoader className="w-8 h-8 animate-spin text-blue-500" /></div>);

    return (
        <div className="space-y-6">
            {!safeMode && (
                <div className="bg-red-100 border-l-4 border-red-500 p-4 rounded-r-lg shadow-md animate-pulse">
                    <div className="flex items-center"><FiAlertCircle className="w-6 h-6 text-red-600 mr-3" />
                        <div><p className="font-bold text-red-700">⚠️ SAFE MODE IS DISABLED</p><p className="text-red-600 text-sm">The system is actively taking automated actions on clusters. Enable Safe Mode to switch to dry-run only.</p></div>
                    </div>
                </div>
            )}
            <div className="flex justify-between items-center">
                <div><h1 className="text-2xl font-bold text-gray-900">System Configuration</h1><p className="text-gray-600">The Engine Room - Control global variables</p></div>
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                    <Card className="p-6">
                        <div className="flex items-start justify-between">
                            <div className="flex items-center space-x-4">
                                <div className={`p-3 rounded-lg ${safeMode ? 'bg-green-100' : 'bg-red-100'}`}><FiShield className={`w-8 h-8 ${safeMode ? 'text-green-600' : 'text-red-600'}`} /></div>
                                <div><h2 className="text-xl font-bold text-gray-900">Global Safe Mode</h2><p className="text-gray-500 mt-1">{safeMode ? "ON: Recommendations are generated but NO ACTIONS are taken (Dry Run)." : "OFF: The system is taking automated actions on client clusters."}</p></div>
                            </div>
                            <div className="flex items-center">
                                <label className="relative inline-flex items-center cursor-pointer">
                                    <input type="checkbox" className="sr-only peer" checked={safeMode} onChange={handleSafeModeToggle} disabled={saving} />
                                    <div className={`w-14 h-7 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[4px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-6 after:w-6 after:transition-all peer-checked:bg-green-600 ${saving ? 'opacity-50' : ''}`}></div>
                                </label>
                            </div>
                        </div>
                    </Card>
                    <div className="mt-6">
                        <h3 className="text-lg font-semibold text-gray-900 mb-4">Risk Parameters</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <Card className="p-6"><label className="block text-sm font-medium text-gray-700 mb-2">Global Risk TTL (Minutes)</label><div className="flex items-center space-x-2"><input type="number" defaultValue={30} className="w-full border rounded p-2" /><span className="text-gray-400 text-sm">min</span></div><p className="text-xs text-gray-500 mt-2">Time an AZ remains "Dangerous" after interruption.</p></Card>
                            <Card className="p-6"><label className="block text-sm font-medium text-gray-700 mb-2">Optimization Cooldown (Minutes)</label><div className="flex items-center space-x-2"><input type="number" defaultValue={60} className="w-full border rounded p-2" /><span className="text-gray-400 text-sm">min</span></div><p className="text-xs text-gray-500 mt-2">Minimum time between actions on same node group.</p></Card>
                        </div>
                    </div>
                </div>
                <div>
                    <Card className="p-6 h-full">
                        <div className="flex items-center space-x-3 mb-6"><FiRefreshCw className="w-6 h-6 text-blue-600" /><h2 className="text-lg font-bold text-gray-900">Agent Version</h2></div>
                        <div className="space-y-4">
                            <div><label className="block text-sm font-medium text-gray-700 mb-2">Latest Stable Version</label><input type="text" value={agentVersion} onChange={(e) => setAgentVersion(e.target.value)} className="w-full border rounded p-2 text-sm" /></div>
                            <div className="p-4 bg-yellow-50 rounded text-sm text-yellow-800 border border-yellow-200"><div className="flex items-start"><FiAlertCircle className="w-5 h-5 mr-2 flex-shrink-0" /><p>Updating this will trigger an "Update Available" badge on all active client dashboards.</p></div></div>
                            <Button variant="outline" className="w-full">Release New Version</Button>
                        </div>
                    </Card>
                </div>
            </div>
            <div className="mt-8"><h3 className="text-lg font-semibold text-gray-900 mb-4">Platform AWS Identity</h3><PlatformSettings /></div>
        </div>
    );
};

export default AdminConfig;
