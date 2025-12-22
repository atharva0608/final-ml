import React, { useEffect, useState } from 'react';
import { FlaskConical, Upload, Trash2, CheckCircle2, AlertTriangle, RefreshCw, FileCode, TrendingUp, Activity } from 'lucide-react';
import api from '../../services/api';

const ModelGovernance = () => {
    const [models, setModels] = useState({
        lab_candidates: [],
        production_ready: [],
        active_production_model: null,
        archived_models: []
    });
    const [loading, setLoading] = useState(true);
    const [scanning, setScanning] = useState(false);
    const [showTestModal, setShowTestModal] = useState(false);
    const [selectedTestModel, setSelectedTestModel] = useState(null);

    const refresh = async () => {
        try {
            setLoading(true);
            const data = await api.fetchApi('/api/v1/ai/list');
            setModels(data);
        } catch (err) {
            console.error('Failed to fetch models:', err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        refresh();
    }, []);

    const handleScan = async () => {
        try {
            setScanning(true);
            await api.fetchApi('/api/v1/ai/scan', { method: 'POST' });
            await refresh();
        } catch (err) {
            console.error('Failed to scan models:', err);
            alert('Failed to scan model folder: ' + err.message);
        } finally {
            setScanning(false);
        }
    };
    const handleTest = (model) => {
        setSelectedTestModel(model);
        setShowTestModal(true);
    };

    const handleGraduate = async (id, name) => {
        if (!window.confirm(`Promote "${name}" to Production Ready?\n\nThis will make the model available for deployment but will NOT automatically deploy it.`)) {
            return;
        }

        try {
            await api.fetchApi(`/api/v1/ai/${id}/graduate`, { method: 'POST' });
            await refresh();
        } catch (err) {
            console.error('Failed to graduate model:', err);
            alert('Failed to graduate model: ' + err.message);
        }
    };

    const handleDeploy = async (id, name) => {
        if (!window.confirm(
            `⚠️ WARNING: Deploy "${name}" to Production?\n\n` +
            `This will switch the AI Model for ALL Production Clients immediately.\n\n` +
            `Current active model: ${models.active_production_model?.name || 'None'}\n\n` +
            `Are you sure you want to proceed?`
        )) {
            return;
        }

        try {
            const response = await api.fetchApi(`/api/v1/ai/${id}/deploy`, { method: 'POST' });
            alert(`✓ ${response.message}`);
            await refresh();
        } catch (err) {
            console.error('Failed to deploy model:', err);
            alert('Failed to deploy model: ' + err.message);
        }
    };

    const handleArchive = async (id, name) => {
        if (!window.confirm(`Archive "${name}"?\n\nThe model will be soft-deleted but remain in the database for audit trail.`)) {
            return;
        }

        try {
            await api.fetchApi(`/api/v1/ai/${id}/archive`, { method: 'POST' });
            await refresh();
        } catch (err) {
            console.error('Failed to archive model:', err);
            alert('Failed to archive model: ' + err.message);
        }
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-64">
                <RefreshCw className="w-8 h-8 text-blue-500 animate-spin" />
            </div>
        );
    }

    return (
        <div className="p-6 space-y-8 max-w-7xl mx-auto">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-slate-900 mb-2 flex items-center gap-2">
                    <FlaskConical className="w-6 h-6 text-purple-600" />
                    AI Model Governance
                </h1>
                <p className="text-slate-500">
                    Manage ML model lifecycle: Scan → Test → Graduate → Deploy
                </p>
            </div>

            {/* Production Control Panel */}
            <div className="bg-gradient-to-br from-slate-900 to-slate-800 text-white p-6 rounded-xl border border-indigo-500/30 shadow-lg">
                <div className="flex items-start justify-between mb-6">
                    <div>
                        <h2 className="text-xl font-bold flex items-center gap-2">
                            🏭 Production Engine
                        </h2>
                        <p className="text-sm text-slate-400 mt-1">
                            Active model applied to all production clusters
                        </p>
                    </div>
                    {models.active_production_model && (
                        <div className="flex items-center gap-2 bg-emerald-500/20 border border-emerald-500/50 px-3 py-1.5 rounded-lg">
                            <Activity className="w-4 h-4 text-emerald-400" />
                            <span className="text-xs font-bold text-emerald-400">ACTIVE</span>
                        </div>
                    )}
                </div>

                {models.active_production_model ? (
                    <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700">
                        <div className="flex items-center justify-between">
                            <div className="flex-1">
                                <div className="font-mono text-lg font-bold text-white">
                                    {models.active_production_model.name}
                                </div>
                                <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
                                    <span>Deployed: {new Date(models.active_production_model.deployed_at).toLocaleDateString()}</span>
                                    <span>•</span>
                                    <span>Predictions: {models.active_production_model.total_predictions.toLocaleString()}</span>
                                    {models.active_production_model.success_count > 0 && (
                                        <>
                                            <span>•</span>
                                            <span className="text-emerald-400">
                                                Success Rate: {(models.active_production_model.success_count / models.active_production_model.total_predictions * 100).toFixed(1)}%
                                            </span>
                                        </>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 text-center">
                        <AlertTriangle className="w-8 h-8 text-amber-400 mx-auto mb-2" />
                        <p className="text-sm text-amber-400 font-medium">
                            No production model deployed. Select a graduated model below.
                        </p>
                    </div>
                )}

                {/* Production Ready Models Dropdown */}
                {models.production_ready.length > 0 && (
                    <div className="mt-4">
                        <label className="block text-xs font-bold text-slate-400 uppercase tracking-wider mb-2">
                            Deploy Different Model:
                        </label>
                        <div className="flex gap-2">
                            <select
                                className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-4 py-2.5 text-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
                                defaultValue=""
                                onChange={(e) => {
                                    if (e.target.value) {
                                        const selectedModel = models.production_ready.find(m => m.id === parseInt(e.target.value));
                                        if (selectedModel) {
                                            handleDeploy(selectedModel.id, selectedModel.name);
                                            e.target.value = ''; // Reset dropdown
                                        }
                                    }
                                }}
                            >
                                <option value="" disabled>Select graduated model to deploy...</option>
                                {models.production_ready.map(m => (
                                    <option key={m.id} value={m.id}>
                                        {m.name} (graduated {new Date(m.graduated_at).toLocaleDateString()})
                                    </option>
                                ))}
                            </select>
                        </div>
                        <p className="text-xs text-slate-500 mt-2">
                            Only "Graduated" models appear here. Promote candidates below.
                        </p>
                    </div>
                )}
            </div>

            {/* Lab Candidates */}
            <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <h3 className="font-bold text-slate-900 text-lg flex items-center gap-2">
                            🧪 Lab Candidates
                        </h3>
                        <p className="text-sm text-slate-500 mt-1">
                            New models detected in <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">ml-model/</code> folder
                        </p>
                    </div>
                    <button
                        onClick={handleScan}
                        disabled={scanning}
                        className="px-4 py-2 bg-blue-600 text-white text-sm font-bold rounded-lg hover:bg-blue-700 flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-blue-200"
                    >
                        <RefreshCw className={`w-4 h-4 ${scanning ? 'animate-spin' : ''}`} />
                        {scanning ? 'Scanning...' : 'Scan Folder'}
                    </button>
                </div>

                <div className="space-y-3">
                    {models.lab_candidates.length > 0 ? (
                        models.lab_candidates.map(m => (
                            <div key={m.id} className="flex items-center justify-between p-4 bg-slate-50 rounded-lg border border-slate-200 hover:border-slate-300 transition-all">
                                <div className="flex items-center gap-3 flex-1">
                                    <FileCode className="w-5 h-5 text-slate-400" />
                                    <div>
                                        <div className="font-mono text-sm font-medium text-slate-900">{m.name}</div>
                                        <div className="text-xs text-slate-500">
                                            Uploaded {new Date(m.uploaded_at).toLocaleString()}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => alert("Model Accepted! Available for testing in Lab Instances.")}
                                        className="px-3 py-1.5 text-xs bg-purple-100 text-purple-700 rounded-lg hover:bg-purple-200 transition-colors font-bold flex items-center gap-1"
                                    >
                                        <CheckCircle2 className="w-3 h-3" />
                                        Accept
                                    </button>
                                    <button
                                        onClick={() => handleGraduate(m.id, m.name)}
                                        className="px-3 py-1.5 text-xs bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200 transition-colors font-bold flex items-center gap-1"
                                    >
                                        <CheckCircle2 className="w-3 h-3" />
                                        🎓 Graduate
                                    </button>
                                    <button
                                        onClick={() => handleArchive(m.id, m.name)}
                                        className="px-3 py-1.5 text-xs bg-red-50 text-red-600 rounded-lg hover:bg-red-100 transition-colors font-bold flex items-center gap-1 border border-red-200"
                                    >
                                        <Trash2 className="w-3 h-3" />
                                        Reject
                                    </button>
                                </div>
                            </div>
                        ))
                    ) : (
                        <div className="text-center py-8 text-slate-400">
                            <Upload className="w-12 h-12 mx-auto mb-3 text-slate-300" />
                            <p className="text-sm font-medium">No candidate models found</p>
                            <p className="text-xs mt-1">
                                Drop .pkl files in <code className="bg-slate-100 px-2 py-0.5 rounded">ml-model/</code> folder and click "Scan Folder"
                            </p>
                        </div>
                    )}
                </div>
            </div>

            {/* Production Ready Models */}
            {models.production_ready.length > 0 && (
                <div className="bg-white p-6 rounded-xl border border-emerald-200 shadow-sm">
                    <div className="flex items-center gap-2 mb-4">
                        <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                        <h3 className="font-bold text-slate-900 text-lg">
                            Production Ready Models
                        </h3>
                        <span className="ml-auto text-xs bg-emerald-100 text-emerald-700 px-2 py-1 rounded-full font-bold">
                            {models.production_ready.length} Available
                        </span>
                    </div>

                    <div className="space-y-3">
                        {models.production_ready.map(m => (
                            <div key={m.id} className="flex items-center justify-between p-4 bg-emerald-50 rounded-lg border border-emerald-200">
                                <div className="flex items-center gap-3 flex-1">
                                    <TrendingUp className="w-5 h-5 text-emerald-600" />
                                    <div>
                                        <div className="font-mono text-sm font-medium text-slate-900">{m.name}</div>
                                        <div className="text-xs text-slate-500">
                                            Graduated {new Date(m.graduated_at).toLocaleString()}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => handleDeploy(m.id, m.name)}
                                        className="px-4 py-1.5 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors font-bold shadow-md shadow-indigo-200"
                                    >
                                        🚀 Deploy to Production
                                    </button>
                                    <button
                                        onClick={() => handleArchive(m.id, m.name)}
                                        className="px-3 py-1.5 text-xs bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200 transition-colors"
                                    >
                                        <Trash2 className="w-3 h-3" />
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Workflow Guide */}
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
                <h4 className="font-bold text-blue-900 mb-3 flex items-center gap-2">
                    <FileCode className="w-4 h-4" />
                    MLOps Workflow
                </h4>
                <ol className="space-y-2 text-sm text-blue-800">
                    <li className="flex items-start gap-2">
                        <span className="font-bold">1.</span>
                        <span>Drop <code className="bg-blue-100 px-1.5 py-0.5 rounded text-xs">.pkl</code> files into <code className="bg-blue-100 px-1.5 py-0.5 rounded text-xs">ml-model/</code> folder</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="font-bold">2.</span>
                        <span>Click "Scan Folder" to register as <strong>Lab Candidates</strong></span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="font-bold">3.</span>
                        <span>Test candidates in Lab Mode (click "Test" to try on an instance)</span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="font-bold">4.</span>
                        <span>Click "Graduate" to promote to <strong>Production Ready</strong></span>
                    </li>
                    <li className="flex items-start gap-2">
                        <span className="font-bold">5.</span>
                        <span>Select from dropdown or click "Deploy" to set as <strong>Active Production Model</strong></span>
                    </li>
                </ol>
            </div>

            {/* Test Model Modal */}
            {showTestModal && selectedTestModel && (
                <TestModelModal
                    model={selectedTestModel}
                    onClose={() => setShowTestModal(false)}
                    onSuccess={() => {
                        setShowTestModal(false);
                        refresh();
                    }}
                />
            )}
        </div>
    );
};

// Modal Component for Testing
const TestModelModal = ({ model, onClose, onSuccess }) => {
    const [instances, setInstances] = useState([]);
    const [loading, setLoading] = useState(true);
    const [selectedInstance, setSelectedInstance] = useState('');
    const [assigning, setAssigning] = useState(false);

    useEffect(() => {
        const fetchInstances = async () => {
            try {
                const data = await api.getInstances();
                setInstances(data);
            } catch (e) {
                console.error("Failed to load instances", e);
            } finally {
                setLoading(false);
            }
        };
        fetchInstances();
    }, []);

    const handleAssign = async () => {
        if (!selectedInstance) return;
        setAssigning(true);
        try {
            await api.assignModelToInstance(selectedInstance, model.name);
            alert(`Model assigned to instance ${selectedInstance}`);
            onSuccess();
        } catch (e) {
            alert("Failed to assign model: " + e.message);
        } finally {
            setAssigning(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black/50 z-[100] flex items-center justify-center backdrop-blur-sm animate-in fade-in">
            <div className="bg-white rounded-xl shadow-2xl p-6 w-full max-w-md">
                <h3 className="text-lg font-bold mb-4">Test Model: {model.name}</h3>
                <p className="text-sm text-slate-500 mb-4">Select an active instance to run this model in Shadow or Live mode.</p>

                {loading ? (
                    <div className="text-center py-4 text-slate-400">Loading instances...</div>
                ) : (
                    <div className="space-y-4">
                        <div>
                            <label className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1.5">Target Instance</label>
                            <select
                                className="w-full border rounded-lg px-3 py-2 text-sm"
                                value={selectedInstance}
                                onChange={e => setSelectedInstance(e.target.value)}
                            >
                                <option value="">Select Instance...</option>
                                {instances.map(inst => (
                                    <option key={inst.instance_id} value={inst.instance_id}>
                                        {inst.instance_id} ({inst.instance_type}) - {inst.status}
                                    </option>
                                ))}
                            </select>
                        </div>
                        <div className="flex justify-end gap-2 pt-4 border-t">
                            <button onClick={onClose} className="px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 rounded-lg">Cancel</button>
                            <button
                                disabled={!selectedInstance || assigning}
                                onClick={handleAssign}
                                className="px-4 py-2 text-sm font-bold bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
                            >
                                {assigning ? 'Assigning...' : 'Assign Model'}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default ModelGovernance;
