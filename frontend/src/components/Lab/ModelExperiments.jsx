import React, { useState } from 'react';
import { Search, FlaskConical, Play, Pause, Activity, Rocket, History, MonitorPlay } from 'lucide-react';
import PipelineVisualizer from './PipelineVisualizer';
import ShadowGraph from './ShadowGraph';
import DecisionLog from './DecisionLog';
import LabInstanceDetails from './LabInstanceDetails';
import DragDropUpload from './DragDropUpload';
import { cn } from '../../lib/utils';
import { useModel } from '../../context/ModelContext';

import api from '../../services/api';
import { useEffect } from 'react';

// Real Data Integration
const ModelExperiments = () => {
    const { models, getLabModels, graduateModel, rejectModel } = useModel();
    const [historyType, setHistoryType] = useState('live'); // 'live' | 'historical'

    const [testSubjects, setTestSubjects] = useState([]);

    // Filter only Lab models for this view
    const visibleModels = models.filter(m => m.scope === 'lab' || m.status === 'rejected' || m.status === 'graduated');

    // Fetch instances on mount
    useEffect(() => {
        const fetchInstances = async () => {
            try {
                // Fetch instances (filtered by account if needed, currently fetching all user has access to)
                const data = await api.getInstances();
                // Filter for instances in Lab mode (LINEAR) or Shadow mode
                const subjects = data.filter(i => i.pipeline_mode === 'LINEAR' || i.is_shadow_mode).map(i => ({
                    id: i.instance_id,
                    type: i.instance_type,
                    currentModel: i.assigned_model_version || 'Default',
                    status: i.is_active ? 'active' : 'standby',
                    lastSwitch: i.last_evaluation ? new Date(i.last_evaluation).toLocaleTimeString() : 'Never'
                }));
                setTestSubjects(subjects);
            } catch (e) {
                console.error("Failed to fetch test subjects", e);
            }
        };
        fetchInstances();
        const interval = setInterval(fetchInstances, 10000); // Poll every 10s
        return () => clearInterval(interval);
    }, []);

    // Derive active model for graph/logs
    const activeTestingModel = visibleModels.find(m => m.status === 'testing') || { name: 'No Active Model' };

    // View State for Drill-down
    const [selectedModel, setSelectedModel] = useState(null);





    const updateStatus = async (id, newStatus) => {
        if (newStatus === 'graduated') {
            await graduateModel(id);
        } else if (newStatus === 'rejected') {
            await rejectModel(id);
        }
    };

    const handleUseInProd = (model) => {
        // This effectively "Graduates" it to the Prod Dropdown context
        graduateModel(model.id);
        alert(`Model "${model.name}" is now available in Production Controls!`);
    };

    // If Drill-down view is active
    if (selectedModel) {
        return <LabInstanceDetails instance={selectedModel} onBack={() => setSelectedModel(null)} />;
    }

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 flex items-center">
                        <FlaskConical className="w-6 h-6 mr-3 text-purple-600" />
                        Model Experiments
                    </h1>
                    <p className="text-slate-500 mt-1">Manage, validate, and promote experimental inference models.</p>
                </div>
                <div className="px-3 py-1 bg-purple-50 border border-purple-100 rounded-full flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-purple-600 animate-pulse"></span>
                    <span className="text-xs font-bold text-purple-700 uppercase tracking-wide">R&D Environment Link Active</span>
                </div>
            </div>

            {/* 1. Active Pipeline Visualizer (Top) */}
            <div className="grid grid-cols-1">
                <PipelineVisualizer activeModel={activeTestingModel.name} />
            </div>

            {/* 2. Test Subject Instances (New) */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center">
                        <Activity className="w-4 h-4 mr-2 text-slate-400" />
                        Test Subject Instances
                    </h3>
                </div>
                <table className="w-full text-sm text-left">
                    <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-200">
                        <tr>
                            <th className="px-6 py-3">Instance ID</th>
                            <th className="px-6 py-3">Type</th>
                            <th className="px-6 py-3">Current Model</th>
                            <th className="px-6 py-3">Status</th>
                            <th className="px-6 py-3 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {testSubjects.map(instance => (
                            <tr key={instance.id} className="hover:bg-slate-50 transition-colors group cursor-pointer" onClick={() => setSelectedModel({ ...instance, name: instance.id, accuracy: 'N/A' })}>
                                <td className="px-6 py-4 font-mono font-medium text-slate-900">{instance.id}</td>
                                <td className="px-6 py-4 text-slate-500">{instance.type}</td>
                                <td className="px-6 py-4 text-purple-600 font-medium">{instance.currentModel}</td>
                                <td className="px-6 py-4">
                                    <span className={cn(
                                        "px-2 py-0.5 rounded text-xs font-bold border",
                                        instance.status === 'active' && "bg-emerald-50 text-emerald-600 border-emerald-100",
                                        instance.status === 'warning' && "bg-amber-50 text-amber-600 border-amber-100",
                                        instance.status === 'standby' && "bg-slate-100 text-slate-500 border-slate-200"
                                    )}>
                                        {instance.status.toUpperCase()}
                                    </span>
                                </td>
                                <td className="px-6 py-4 text-right">
                                    <button className="text-purple-600 hover:text-purple-800 text-xs font-bold flex items-center justify-end w-full">
                                        View Details <Search className="w-3 h-3 ml-1" />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* 3. Model Registry (Existing) */}
            <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
                    <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center">
                        <History className="w-4 h-4 mr-2 text-slate-400" />
                        Model Registry
                    </h3>
                </div>
                <table className="w-full text-sm text-left">
                    <thead className="bg-slate-50 text-slate-500 font-medium border-b border-slate-200">
                        <tr>
                            <th className="px-6 py-3">Model Name</th>
                            <th className="px-6 py-3 text-center">Status</th>
                            <th className="px-6 py-3">Accuracy (Shadow)</th>
                            <th className="px-6 py-3 text-right">Actions</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {visibleModels.map(model => (
                            <tr key={model.id} className="hover:bg-slate-50 transition-colors group">
                                <td className="px-6 py-4 font-medium text-slate-900">
                                    <div className="flex items-center">
                                        <div className="w-8 h-8 rounded bg-slate-100 flex items-center justify-center mr-3 text-slate-400 group-hover:bg-purple-100 group-hover:text-purple-600 transition-all border border-transparent group-hover:border-purple-200">
                                            <Search className="w-4 h-4" />
                                        </div>
                                        <div>
                                            <div className="font-bold">{model.name}</div>
                                            <div className="text-xs text-slate-400">{model.uploadedAt}</div>
                                        </div>
                                    </div>
                                </td>
                                <td className="px-6 py-4 text-center">
                                    <span className={cn(
                                        "px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wide border",
                                        model.status === 'testing' && "bg-blue-50 text-blue-700 border-blue-200",
                                        model.status === 'graduated' && "bg-emerald-50 text-emerald-700 border-emerald-200",
                                        model.status === 'rejected' && "bg-slate-100 text-slate-500 border-slate-200",
                                        model.status === 'enabled' && "bg-purple-50 text-purple-700 border-purple-200"
                                    )}>
                                        {model.status === 'enabled' ? 'In Production' : model.status}
                                    </span>
                                </td>
                                <td className="px-6 py-4 font-mono text-slate-600">
                                    {model.accuracy}
                                </td>
                                <td className="px-6 py-4 text-right">
                                    <div className="flex items-center justify-end gap-2">
                                        {/* Workflow Buttons */}
                                        {model.status === 'testing' && (
                                            <>
                                                <button
                                                    onClick={() => updateStatus(model.id, 'rejected')}
                                                    className="px-3 py-1.5 text-xs font-bold text-red-600 bg-red-50 hover:bg-red-100 rounded border border-red-200 transition-colors"
                                                >
                                                    Reject
                                                </button>
                                                <button
                                                    onClick={() => updateStatus(model.id, 'graduated')}
                                                    className="px-3 py-1.5 text-xs font-bold text-emerald-600 bg-emerald-50 hover:bg-emerald-100 rounded border border-emerald-200 transition-colors flex items-center"
                                                >
                                                    <Rocket className="w-3 h-3 mr-1" />
                                                    Graduate
                                                </button>
                                            </>
                                        )}

                                        {model.status === 'graduated' && (
                                            <button
                                                onClick={() => { updateStatus(model.id, 'enabled'); handleUseInProd(model); }}
                                                className="px-3 py-1.5 text-xs font-bold text-white bg-purple-600 hover:bg-purple-700 rounded shadow-sm hover:shadow transition-all flex items-center"
                                            >
                                                Enable for Prod
                                            </button>
                                        )}

                                        {model.status === 'enabled' && (
                                            <span className="text-xs font-medium text-slate-400 italic">Available in Controls</span>
                                        )}

                                        {model.status === 'rejected' && (
                                            <button className="text-slate-400 hover:text-red-500 transition-colors p-1">
                                                <History className="w-4 h-4" />
                                            </button>
                                        )}
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {/* 4. Upload Section (Bottom) */}
            <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
                <h3 className="text-sm font-bold text-slate-900 mb-4 px-1">Upload New Candidate</h3>
                {/* We pass the context's uploadModel function directly if DragDropUpload supports it, 
                    or we need to wrap it. DragDropUpload likely expects a file. 
                    Context uploadModel takes (file, scope). 
                */}
                <DragDropUpload onUpload={(file) => useModel().uploadModel(file, 'lab')} className="bg-slate-50 border-slate-200 hover:bg-white" />
            </div>

            {/* 5. Metrics & Logs */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                    <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm min-h-[350px] flex flex-col h-full">
                        {/* Shadow Graph Container - ShadowGraph internal layout handles headers */}
                        <ShadowGraph activeModel={activeTestingModel.name} />
                    </div>
                </div>
                <div className="h-full flex flex-col">
                    {/* Log View Toggle */}
                    <div className="bg-slate-50 border border-b-0 border-slate-200 p-2 flex items-center justify-end rounded-t-xl gap-2 text-slate-600">
                        <button
                            onClick={() => setHistoryType('live')}
                            className={cn(
                                "px-3 py-1.5 text-xs font-bold rounded-md flex items-center transition-all",
                                historyType === 'live' ? "bg-white text-purple-700 shadow-sm border border-purple-100" : "text-slate-500 hover:text-slate-700"
                            )}
                        >
                            <MonitorPlay className="w-3 h-3 mr-1.5" />
                            Live Stream
                        </button>
                        <button
                            onClick={() => setHistoryType('historical')}
                            className={cn(
                                "px-3 py-1.5 text-xs font-bold rounded-md flex items-center transition-all",
                                historyType === 'historical' ? "bg-slate-200 text-slate-900 border border-slate-300 shadow-sm" : "text-slate-500 hover:text-slate-700"
                            )}
                        >
                            <History className="w-3 h-3 mr-1.5" />
                            Historical Runs
                        </button>
                    </div>
                    <div className="flex-1 -mt-px">
                        <DecisionLog activeModel={activeTestingModel.name} historyType={historyType} />
                    </div>
                </div>
            </div>

        </div>
    );
};

export default ModelExperiments;
