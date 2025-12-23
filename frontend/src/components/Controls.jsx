import React, { useState } from 'react';
import { useModel } from '../context/ModelContext';
import { CheckCircle2, UploadCloud, RefreshCw, AlertOctagon } from 'lucide-react';
import api from '../services/api';
import DragDropUpload from './Lab/DragDropUpload';

const Controls = () => {
    const [isDragging, setIsDragging] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);
    // Spot Disable State
    const [showSpotConfirm, setShowSpotConfirm] = useState(false);
    const [isSpotDisabled, setIsSpotDisabled] = useState(false);
    const { getProdModels, getActiveProdModel, setActiveProdModelId, uploadModel } = useModel();

    // Prod History State
    const [historyType, setHistoryType] = useState('audit'); // 'audit' | 'logs'

    const prodModels = getProdModels();
    const activeModel = getActiveProdModel();

    // Local state for dropdown selection (pending application)
    const [pendingModelId, setPendingModelId] = useState(activeModel?.id || '');

    // Filter for only ENABLED models for the dropdown
    const availableModels = prodModels.filter(m => m.status === 'enabled' || m.id === activeModel?.id);

    // Sync pending state when active model loads/changes externally, or default to first available
    // Sync pending state only when active model ID actually changes (external update)
    // We intentionally exclude pendingModelId to avoid resetting user selection
    React.useEffect(() => {
        if (activeModel?.id) {
            setPendingModelId(activeModel.id);
        } else if (availableModels.length > 0 && !activeModel) {
            // Only default if no active model is known yet
            setPendingModelId(availableModels[0].id);
        }
    }, [activeModel?.id]);

    return (
        <div className="space-y-6 max-w-4xl mx-auto">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 mb-2">System Controls</h1>
                <p className="text-slate-500">Manual overrides and production configuration</p>
            </div>

            {/* Production Model Configuration */}
            <div className="bg-white border border-slate-200 rounded-xl p-8 shadow-sm">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-lg font-bold text-slate-900 mb-1">Production Model Configuration</h2>
                        <p className="text-sm text-slate-500">Select the active inference engine for the fleet.</p>
                    </div>
                </div>

                {/* Current Active Model Display */}
                {activeModel && (
                    <div className="bg-emerald-50 border border-emerald-100 rounded-lg p-4 mb-6 flex items-center justify-between">
                        <div className="flex items-center space-x-3">
                            <div className="p-2 bg-emerald-100 rounded text-emerald-600">
                                <CheckCircle2 className="w-5 h-5" />
                            </div>
                            <div>
                                <div className="text-xs font-bold text-emerald-600 uppercase tracking-wider">Current Active Model</div>
                                <div className="text-lg font-bold text-slate-900">{activeModel.name}</div>
                                <div className="text-xs text-slate-500 font-mono">Version: {activeModel.version} • ID: {activeModel.id}</div>
                            </div>
                        </div>
                        <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse"></div>
                    </div>
                )}

                <div className="flex items-start space-x-6 border-b border-slate-100 pb-6 mb-6">
                    {/* Model Dropdown */}
                    <div className="flex-1">
                        <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">Active Model Version</label>
                        <select
                            className="w-full bg-slate-50 border border-slate-200 text-slate-700 rounded-lg px-4 py-2.5 shadow-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                            value={pendingModelId}
                            onChange={(e) => setPendingModelId(e.target.value)}
                            disabled={availableModels.length === 0}
                        >
                            {availableModels.length === 0 && <option value="">No Enabled Models Available</option>}
                            {availableModels.map(m => (
                                <option key={m.id} value={m.id}>
                                    {m.name} {m.version}
                                </option>
                            ))}
                        </select>
                        <p className="text-xs text-slate-400 mt-2">
                            Only "Enabled" production models appear here.
                        </p>
                    </div>

                    {/* Quick Upload */}
                    <div className="flex-1 border-l border-slate-100 pl-6">
                        <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">Upload Hotfix Model</label>
                        <DragDropUpload onUpload={(file) => uploadModel(file, 'prod')} className="min-h-[100px]" />
                        <p className="text-xs text-slate-400 mt-2">
                            Direct upload to production (use with caution)
                        </p>
                    </div>
                </div>

                {/* Manual Overrides Section */}
                <div className="mb-6">
                    <h3 className="text-sm font-bold text-slate-900 mb-4">Manual Overrides</h3>
                    <div className="grid grid-cols-1 gap-4">

                        {/* Disable Spot Market Control */}
                        <div className="relative bg-slate-50 rounded-lg border border-slate-100 p-4 transition-all">
                            <div className="flex items-center justify-between">
                                <div>
                                    <div className="text-sm font-bold text-slate-700">Disable Spot Market</div>
                                    <div className="text-xs text-slate-500">Force all workloads to On-Demand instances</div>
                                </div>

                                {/* Toggle Switch */}
                                <div
                                    onClick={() => {
                                        if (isSpotDisabled) {
                                            setIsSpotDisabled(false);
                                        } else {
                                            setShowSpotConfirm(true);
                                        }
                                    }}
                                    className={`w-12 h-6 rounded-full relative cursor-pointer transition-colors duration-300 ${isSpotDisabled ? 'bg-indigo-600' : 'bg-slate-300 hover:bg-slate-400'}`}
                                >
                                    <div className={`w-4 h-4 bg-white rounded-full shadow-sm absolute top-1 transition-all duration-300 ${isSpotDisabled ? 'left-7' : 'left-1'}`}></div>
                                </div>
                            </div>

                            {/* Fixed Modal Overlay for Scalable Visibility */}
                            {showSpotConfirm && (
                                <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/20 backdrop-blur-sm animate-in fade-in duration-200">
                                    <div className="bg-white rounded-xl shadow-2xl border border-slate-200 p-6 max-w-sm w-full text-center space-y-4 animate-in zoom-in-95 duration-200" onClick={(e) => e.stopPropagation()}>
                                        <div className="mx-auto w-12 h-12 bg-amber-50 rounded-full flex items-center justify-center mb-2">
                                            <AlertOctagon className="w-6 h-6 text-amber-500" />
                                        </div>
                                        <div>
                                            <h3 className="text-lg font-bold text-slate-900">Disable Spot Market?</h3>
                                            <p className="text-sm text-slate-500 mt-1">This will revert all nodes to On-Demand pricing. Costs may increase significantly.</p>
                                        </div>
                                        <div className="flex flex-col gap-2 pt-2">
                                            <button
                                                onClick={async (e) => {
                                                    e.stopPropagation();
                                                    try {
                                                        await api.setSpotMarketStatus(true);
                                                        setIsSpotDisabled(true);
                                                        setShowSpotConfirm(false);
                                                    } catch (err) {
                                                        console.error('Failed to disable spot:', err);
                                                        alert('Failed to disable Spot Market: ' + err.message);
                                                    }
                                                }}
                                                className="w-full py-2.5 bg-slate-900 text-white font-bold rounded-lg hover:bg-slate-800 transition-colors shadow-lg shadow-slate-200"
                                            >
                                                Confirm Disable
                                            </button>
                                            <button
                                                onClick={(e) => { e.stopPropagation(); setShowSpotConfirm(false); }}
                                                className="w-full py-2.5 bg-white border border-slate-200 text-slate-700 font-bold rounded-lg hover:bg-slate-50 transition-colors"
                                            >
                                                Cancel
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Apply Button */}
                <div className="flex justify-end">
                    <button
                        onClick={() => {
                            setActiveProdModelId(pendingModelId);
                            alert("Changes Applied Successfully to Production Fleet!");
                        }}
                        disabled={!pendingModelId}
                        className="px-6 py-2.5 bg-blue-600 text-white text-sm font-bold rounded-lg hover:bg-blue-700 shadow-md shadow-blue-200 transition-all active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none"
                    >
                        Apply Changes
                    </button>
                </div>
            </div>

            {/* System Actions */}
            <div className="grid grid-cols-1 gap-6">
                <div className="bg-red-50 border border-red-100 rounded-xl p-6 shadow-sm flex flex-col justify-between relative overflow-visible">
                    <div className="absolute top-0 right-0 p-32 bg-red-100 rounded-full blur-3xl opacity-20 -mr-16 -mt-16 pointer-events-none"></div>
                    <div>
                        <div className="flex items-center space-x-2 text-red-700 mb-4">
                            <AlertOctagon className="w-6 h-6" />
                            <span className="font-bold">Emergency Fallback</span>
                        </div>
                        <p className="text-sm text-red-800 mb-6">
                            IMMEDIATELY stop all spot requests and revert to On-Demand. Use only in critical outages.
                        </p>
                    </div>

                    {/* Confirmation State */}
                    {showConfirm ? (
                        <div className="absolute inset-0 bg-white/95 backdrop-blur-sm z-20 flex flex-col items-center justify-center p-6 text-center animate-in fade-in duration-200 rounded-xl">
                            <AlertOctagon className="w-8 h-8 text-red-600 mb-2 animate-bounce" />
                            <h3 className="text-lg font-bold text-slate-900 mb-1">Confirm Emergency?</h3>
                            <p className="text-xs text-slate-500 mb-4">This action can increase costs by up to 60%.</p>
                            <div className="flex space-x-3 w-full">
                                <button
                                    onClick={() => { console.log("GLOBAL FALLBACK"); setShowConfirm(false); }}
                                    className="flex-1 py-2 bg-red-600 text-white font-bold rounded shadow hover:bg-red-700"
                                >
                                    CONFIRM
                                </button>
                                <button
                                    onClick={() => setShowConfirm(false)}
                                    className="flex-1 py-2 bg-slate-100 text-slate-600 font-bold rounded hover:bg-slate-200"
                                >
                                    CANCEL
                                </button>
                            </div>
                        </div>
                    ) : (
                        <button
                            onClick={() => setShowConfirm(true)}
                            className="w-full py-2.5 bg-red-600 text-white font-bold rounded-lg hover:bg-red-700 transition-colors shadow-sm border border-red-700 relative z-10"
                        >
                            ACTIVATE FALLBACK
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Controls;
