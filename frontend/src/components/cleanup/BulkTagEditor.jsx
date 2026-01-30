import React, { useState, useEffect } from 'react';
import { FiX, FiCheck, FiAlertTriangle, FiLayers, FiEdit3, FiInfo } from 'react-icons/fi';
import api from '../../services/api';
import { toast } from 'react-hot-toast';
import { useAuthStore } from '../../store/useStore';

const BulkTagWizard = ({ resources, onClose, onSuccess }) => {
    // Modes: 'template' | 'manual'
    const [mode, setMode] = useState('template');
    const [templates, setTemplates] = useState([]);
    const [loadingTemplates, setLoadingTemplates] = useState(false);

    // Selection
    const [selectedTemplateId, setSelectedTemplateId] = useState('');
    const [templateVariables, setTemplateVariables] = useState({});

    // Manual Tags
    const [manualTags, setManualTags] = useState({});

    // Options
    const [collisionMode, setCollisionMode] = useState('merge'); // merge (Skip Existing), replace (Overwrite)
    const [saving, setSaving] = useState(false);
    const { user } = useAuthStore();

    useEffect(() => {
        fetchTemplates();
    }, []);

    const fetchTemplates = async () => {
        try {
            setLoadingTemplates(true);
            const res = await api.get('/api/v1/tags/templates/');
            // Backend returns wrapped object { templates: [], total: ... }
            setTemplates(res.data.templates || []);
        } catch (error) {
            console.error("Failed to load templates", error);
            toast.error("Could not load tag templates");
        } finally {
            setLoadingTemplates(false);
        }
    };

    // Handle Template Selection
    const handleTemplateSelect = (tmplId) => {
        setSelectedTemplateId(tmplId);
        const tmpl = templates.find(t => t.id === tmplId);
        if (!tmpl) return;

        // Parse variables from values
        const vars = {};
        Object.entries(tmpl.tags).forEach(([key, value]) => {
            const matches = value.match(/{{(.*?)}}/g);
            if (matches) {
                matches.forEach(m => {
                    const varName = m.replace(/{{|}}/g, '');
                    // Pre-fill known vars
                    if (varName === 'CURRENT_USER_EMAIL') vars[varName] = user?.email || '';
                    else if (varName === 'DATE') vars[varName] = new Date().toISOString().split('T')[0];
                    else vars[varName] = '';
                });
            }
        });
        setTemplateVariables(vars);
    };

    // Prepare Payload
    const getFinalTags = () => {
        if (mode === 'manual') return manualTags;

        const tmpl = templates.find(t => t.id === selectedTemplateId);
        if (!tmpl) return {};

        const finalTags = {};
        Object.entries(tmpl.tags).forEach(([key, value]) => {
            let processedValue = value;
            // Replace variables
            Object.entries(templateVariables).forEach(([varKey, varVal]) => {
                processedValue = processedValue.replace(new RegExp(`{{${varKey}}}`, 'g'), varVal);
            });
            finalTags[key] = processedValue;
        });
        return finalTags;
    };

    const handleSave = async () => {
        const tagsToApply = getFinalTags();
        if (Object.keys(tagsToApply).length === 0) {
            toast.error('No tags to apply');
            return;
        }

        try {
            setSaving(true);
            const response = await api.post(
                '/api/v1/tags/resources/bulk',
                {
                    resource_ids: resources.map(r => r.id),
                    resource_type: resources[0].type,
                    operation_mode: collisionMode, // 'merge' or 'replace' logic handled by backend
                    tags: tagsToApply,
                    region: resources[0].region || 'us-east-1' // Batch might contain mixed, ideally backend handles per ID
                },
                {
                    params: {
                        account_id: resources[0].account_id
                    }
                }
            );

            toast.success(`Successfully tagged ${response.data.successful} resources`);
            if (onSuccess) onSuccess();
            onClose();
        } catch (error) {
            console.error('Error bulk tagging:', error);
            toast.error('Failed to tag resources: ' + (error.response?.data?.detail || error.message));
        } finally {
            setSaving(false);
        }
    };

    // Manual Handlers
    const handleAddManualTag = () => {
        const key = prompt("Enter tag Key:");
        if (key) setManualTags(prev => ({ ...prev, [key]: '' }));
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 backdrop-blur-sm">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
                {/* Header */}
                <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50">
                    <div>
                        <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                            <FiLayers className="text-indigo-600" /> Bulk Tagging Wizard
                        </h3>
                        <p className="text-xs text-gray-500 mt-1">
                            Applying tags to <span className="font-semibold text-gray-800">{resources.length}</span> resources
                        </p>
                    </div>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
                        <FiX size={20} />
                    </button>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-gray-200">
                    <button
                        onClick={() => setMode('template')}
                        className={`flex-1 py-3 text-sm font-medium text-center transition-colors border-b-2 ${mode === 'template'
                            ? 'border-indigo-600 text-indigo-700 bg-indigo-50/50'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        Use Template
                    </button>
                    <button
                        onClick={() => setMode('manual')}
                        className={`flex-1 py-3 text-sm font-medium text-center transition-colors border-b-2 ${mode === 'manual'
                            ? 'border-indigo-600 text-indigo-700 bg-indigo-50/50'
                            : 'border-transparent text-gray-500 hover:text-gray-700 hover:bg-gray-50'
                            }`}
                    >
                        Manual Entry
                    </button>
                </div>

                {/* Body */}
                <div className="flex-1 overflow-y-auto p-6 bg-white min-h-[300px]">

                    {/* Template Mode */}
                    {mode === 'template' && (
                        <div className="space-y-6">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">Select Template</label>
                                <select
                                    className="w-full rounded-lg border-gray-300 focus:ring-indigo-500 focus:border-indigo-500"
                                    value={selectedTemplateId}
                                    onChange={(e) => handleTemplateSelect(e.target.value)}
                                    disabled={loadingTemplates}
                                >
                                    <option value="">-- Choose a standard tag template --</option>
                                    {templates.map(t => (
                                        <option key={t.id} value={t.id}>{t.name} ({Object.keys(t.tags).length} tags)</option>
                                    ))}
                                </select>
                                {loadingTemplates && <p className="text-xs text-gray-400 mt-1">Loading templates...</p>}
                            </div>

                            {selectedTemplateId && (
                                <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                                    <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-3">Template Variables</h4>

                                    {Object.keys(templateVariables).length === 0 ? (
                                        <p className="text-sm text-gray-500 italic">No variables to configure. This template is static.</p>
                                    ) : (
                                        <div className="space-y-3">
                                            {Object.keys(templateVariables).map(varName => (
                                                <div key={varName}>
                                                    <label className="block text-xs font-medium text-gray-600 mb-1">{varName}</label>
                                                    <input
                                                        type="text"
                                                        value={templateVariables[varName]}
                                                        onChange={(e) => setTemplateVariables(prev => ({ ...prev, [varName]: e.target.value }))}
                                                        className="w-full text-sm rounded-md border-gray-300"
                                                        placeholder={`Enter value for ${varName}`}
                                                    />
                                                </div>
                                            ))}
                                        </div>
                                    )}

                                    <div className="mt-4 pt-4 border-t border-gray-200">
                                        <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">Preview Tags</h4>
                                        <div className="flex flex-wrap gap-2">
                                            {Object.entries(getFinalTags()).map(([k, v]) => (
                                                <span key={k} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                                                    {k}: {v}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Manual Mode */}
                    {mode === 'manual' && (
                        <div className="space-y-4">
                            <div className="flex justify-between items-center">
                                <h4 className="text-sm font-medium text-gray-700">Custom Tags</h4>
                                <button onClick={handleAddManualTag} className="text-sm text-indigo-600 hover:text-indigo-800 font-medium">
                                    + Add Tag
                                </button>
                            </div>

                            {Object.keys(manualTags).length === 0 ? (
                                <div className="text-center py-8 text-gray-400 border-2 border-dashed border-gray-200 rounded-lg">
                                    No tags added yet. Click "+ Add Tag" to start.
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {Object.entries(manualTags).map(([key, val]) => (
                                        <div key={key} className="flex gap-2 items-center">
                                            <div className="w-1/3 bg-gray-100 px-3 py-2 rounded text-sm text-gray-700 font-mono text-right">{key}</div>
                                            <div className="text-gray-400">=</div>
                                            <input
                                                type="text"
                                                value={val}
                                                onChange={(e) => setManualTags(prev => ({ ...prev, [key]: e.target.value }))}
                                                className="flex-1 rounded-md border-gray-300 text-sm"
                                                placeholder="Value"
                                            />
                                            <button
                                                onClick={() => {
                                                    const n = { ...manualTags };
                                                    delete n[key];
                                                    setManualTags(n);
                                                }}
                                                className="text-red-400 hover:text-red-600 p-2"
                                            >
                                                <FiX />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* Collision Handling */}
                    <div className="mt-8 pt-6 border-t border-gray-100">
                        <label className="block text-sm font-medium text-gray-700 mb-3">Collision Handling</label>
                        <div className="grid grid-cols-2 gap-4">
                            <button
                                onClick={() => setCollisionMode('merge')}
                                className={`flex flex-col items-center p-3 rounded-lg border text-left transition-all ${collisionMode === 'merge'
                                    ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500'
                                    : 'border-gray-200 hover:border-gray-300'
                                    }`}
                            >
                                <span className="text-sm font-semibold text-gray-900">Skip / Merge</span>
                                <span className="text-xs text-gray-500 mt-1">Preserve existing tags, only add new ones.</span>
                            </button>
                            <button
                                onClick={() => setCollisionMode('replace')}
                                className={`flex flex-col items-center p-3 rounded-lg border text-left transition-all ${collisionMode === 'replace'
                                    ? 'border-red-500 bg-red-50 ring-1 ring-red-500'
                                    : 'border-gray-200 hover:border-gray-300'
                                    }`}
                            >
                                <span className="text-sm font-semibold text-gray-900">Overwrite</span>
                                <span className="text-xs text-gray-500 mt-1">Replace value if tag key already exists.</span>
                            </button>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="px-6 py-4 bg-gray-50 border-t border-gray-200 flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
                        disabled={saving}
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center justify-center gap-2 px-6 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {saving ? (
                            <>
                                <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                                Applying...
                            </>
                        ) : (
                            <>
                                <FiCheck /> Apply Tags
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default BulkTagWizard;
