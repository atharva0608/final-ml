import React, { useState, useEffect } from 'react';
import { FiTag, FiX, FiCheck, FiAlertTriangle, FiLayers, FiPlus, FiTrash2 } from 'react-icons/fi';
import api from '../../services/api';
import toast from 'react-hot-toast';

/**
 * BulkTagWizard - Apply Tags to Multiple Resources
 * 
 * From changes.txt Section 3: Bulk Tagging Wizard
 * Location: Resource Hygiene > Tag Management (Modal)
 * 
 * 3-Step Wizard:
 * Step 1: Select template or manual entry
 * Step 2: Handle variable inputs
 * Step 3: Collision handling (Skip Existing / Overwrite)
 * Step 4: Execute and show progress
 */

const BulkTagWizard = ({
    isOpen,
    onClose,
    selectedResources = [],
    onComplete,
    accountId,
    regionId
}) => {
    const [step, setStep] = useState(1);
    const [templates, setTemplates] = useState([]);
    const [loading, setLoading] = useState(false);
    const [executing, setExecuting] = useState(false);
    const [progress, setProgress] = useState(0);
    const [results, setResults] = useState(null);

    // Form state
    const [mode, setMode] = useState('template'); // 'template' or 'manual'
    const [selectedTemplateId, setSelectedTemplateId] = useState('');
    const [selectedTemplate, setSelectedTemplate] = useState(null);
    const [variableInputs, setVariableInputs] = useState({});
    const [collisionMode, setCollisionMode] = useState('skip'); // 'skip' or 'overwrite'
    const [manualTags, setManualTags] = useState([]);
    const [newTagKey, setNewTagKey] = useState('');
    const [newTagValue, setNewTagValue] = useState('');

    // Dynamic variables that need user input
    const PROMPTABLE_VARIABLES = ['{PROJECT_ID}'];

    useEffect(() => {
        if (isOpen) {
            fetchTemplates();
            setStep(1);
            setProgress(0);
            setResults(null);
        }
    }, [isOpen]);

    useEffect(() => {
        if (selectedTemplateId) {
            const template = templates.find(t => t.id === selectedTemplateId);
            setSelectedTemplate(template);

            // Check for variables that need user input
            if (template?.tags) {
                const neededInputs = {};
                Object.values(template.tags).forEach(value => {
                    PROMPTABLE_VARIABLES.forEach(varToken => {
                        if (value.includes(varToken)) {
                            neededInputs[varToken] = '';
                        }
                    });
                });
                setVariableInputs(neededInputs);
            }
        }
    }, [selectedTemplateId, templates]);

    const fetchTemplates = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/tags/templates/');
            setTemplates(response.data.templates || []);

            // Auto-select default template if exists
            const defaultTemplate = response.data.templates?.find(t => t.is_default);
            if (defaultTemplate) {
                setSelectedTemplateId(defaultTemplate.id);
            }
        } catch (error) {
            console.error('Error fetching templates:', error);
        } finally {
            setLoading(false);
        }
    };

    const addManualTag = () => {
        if (!newTagKey.trim()) return;
        if (manualTags.some(t => t.key === newTagKey.trim())) {
            toast.error('Tag key already exists');
            return;
        }
        setManualTags([...manualTags, { key: newTagKey.trim(), value: newTagValue.trim() }]);
        setNewTagKey('');
        setNewTagValue('');
    };

    const removeManualTag = (key) => {
        setManualTags(manualTags.filter(t => t.key !== key));
    };

    const getTagsToApply = () => {
        if (mode === 'manual') {
            const tags = {};
            manualTags.forEach(t => { tags[t.key] = t.value; });
            return tags;
        }

        if (!selectedTemplate?.tags) return {};

        // Resolve dynamic variables
        const tags = {};
        Object.entries(selectedTemplate.tags).forEach(([key, value]) => {
            let resolvedValue = value;

            // Replace user-input variables
            Object.entries(variableInputs).forEach(([varToken, inputValue]) => {
                resolvedValue = resolvedValue.replace(varToken, inputValue);
            });

            tags[key] = resolvedValue;
        });

        return tags;
    };

    const needsVariableInput = () => {
        return mode === 'template' && Object.keys(variableInputs).length > 0;
    };

    const canProceed = () => {
        if (step === 1) {
            if (mode === 'template') return !!selectedTemplateId;
            if (mode === 'manual') return manualTags.length > 0;
        }
        if (step === 2 && needsVariableInput()) {
            return Object.values(variableInputs).every(v => v.trim() !== '');
        }
        return true;
    };

    const handleNext = () => {
        if (step === 1 && needsVariableInput()) {
            setStep(2);
        } else if (step === 1) {
            setStep(3);
        } else if (step === 2) {
            setStep(3);
        } else if (step === 3) {
            executeTagging();
        }
    };

    const handleBack = () => {
        if (step > 1) setStep(step - 1);
    };

    const executeTagging = async () => {
        setExecuting(true);
        setStep(4);
        setProgress(0);

        const tagsToApply = getTagsToApply();
        const total = selectedResources.length;
        let successCount = 0;
        let failedCount = 0;
        const errors = [];

        try {
            for (let i = 0; i < selectedResources.length; i++) {
                const resource = selectedResources[i];

                try {
                    // Determine final tags based on collision mode
                    let finalTags = { ...tagsToApply };

                    if (collisionMode === 'skip' && resource.current_tags) {
                        // Only add tags that don't exist
                        Object.keys(tagsToApply).forEach(key => {
                            if (resource.current_tags[key]) {
                                delete finalTags[key];
                            }
                        });
                    }

                    // Map Frontend Types to Backend Types
                    const RESOURCE_TYPE_MAP = {
                        'INSTANCE': 'EC2',
                        'VOLUME': 'EBS',
                        'S3_BUCKET': 'S3',
                        'RDS_DB': 'RDS'
                    };
                    const backendType = RESOURCE_TYPE_MAP[resource.type] || resource.type;

                    // Only call API if there are tags to apply
                    if (Object.keys(finalTags).length > 0) {
                        await api.post(`/api/v1/tags/resources/${backendType}/${resource.id}/`, {
                            tags: finalTags,
                            overwrite_existing: collisionMode === 'overwrite'
                        }, {
                            params: {
                                account_id: accountId,
                                region: (regionId === 'ALL' ? resource.region : regionId) || 'us-east-1'
                            }
                        });
                        successCount++; // No changes needed, count as success
                    } else {
                        successCount++; // No changes needed, count as success
                    }
                } catch (error) {
                    failedCount++;
                    errors.push({
                        resource_id: resource.resource_id,
                        error: error.response?.data?.detail || error.message
                    });
                }

                setProgress(Math.round(((i + 1) / total) * 100));
            }

            setResults({
                total,
                success: successCount,
                failed: failedCount,
                errors
            });

            if (failedCount === 0) {
                toast.success(`Successfully tagged ${successCount} resources`);
            } else {
                toast.error(`Tagged ${successCount}, failed ${failedCount}`);
            }
        } catch (error) {
            console.error('Bulk tagging error:', error);
            toast.error('Bulk tagging operation failed');
        } finally {
            setExecuting(false);
        }
    };

    const handleClose = () => {
        if (results) {
            onComplete && onComplete(results);
        }
        onClose();
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
                {/* Header */}
                <div className="flex justify-between items-center mb-6">
                    <h3 className="text-xl font-bold flex items-center gap-2">
                        <FiTag className="text-emerald-600" />
                        Tagging {selectedResources.length} Selected Resources
                    </h3>
                    <button
                        onClick={handleClose}
                        className="text-gray-400 hover:text-gray-600"
                    >
                        <FiX className="w-6 h-6" />
                    </button>
                </div>

                {/* Progress Steps */}
                <div className="flex items-center justify-between mb-8">
                    {['Select Tags', 'Variables', 'Collision Handling', 'Execute'].map((label, idx) => {
                        const stepNum = idx + 1;
                        const isActive = step === stepNum;
                        const isComplete = step > stepNum;
                        const shouldShow = !(stepNum === 2 && !needsVariableInput());

                        if (!shouldShow && stepNum === 2) return null;

                        return (
                            <div key={label} className="flex items-center">
                                <div className={`flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium ${isComplete ? 'bg-emerald-600 text-white' :
                                    isActive ? 'bg-emerald-100 text-emerald-700 border-2 border-emerald-600' :
                                        'bg-gray-100 text-gray-400'
                                    }`}>
                                    {isComplete ? <FiCheck className="w-4 h-4" /> : stepNum}
                                </div>
                                <span className={`ml-2 text-sm ${isActive ? 'text-gray-900 font-medium' : 'text-gray-500'}`}>
                                    {label}
                                </span>
                                {idx < 3 && (
                                    <div className={`w-12 h-0.5 mx-3 ${step > stepNum ? 'bg-emerald-600' : 'bg-gray-200'}`} />
                                )}
                            </div>
                        );
                    })}
                </div>

                {/* Step 1: Select Tags */}
                {step === 1 && (
                    <div className="space-y-6">
                        {/* Mode Selection */}
                        <div className="flex gap-4">
                            <button
                                onClick={() => setMode('template')}
                                className={`flex-1 p-4 rounded-lg border-2 text-left transition-all ${mode === 'template'
                                    ? 'border-emerald-600 bg-emerald-50'
                                    : 'border-gray-200 hover:border-gray-300'
                                    }`}
                            >
                                <FiLayers className={`w-6 h-6 mb-2 ${mode === 'template' ? 'text-emerald-600' : 'text-gray-400'}`} />
                                <div className="font-medium">Use Template</div>
                                <div className="text-sm text-gray-500">Quick apply from saved presets</div>
                            </button>
                            <button
                                onClick={() => setMode('manual')}
                                className={`flex-1 p-4 rounded-lg border-2 text-left transition-all ${mode === 'manual'
                                    ? 'border-emerald-600 bg-emerald-50'
                                    : 'border-gray-200 hover:border-gray-300'
                                    }`}
                            >
                                <FiTag className={`w-6 h-6 mb-2 ${mode === 'manual' ? 'text-emerald-600' : 'text-gray-400'}`} />
                                <div className="font-medium">Manual Entry</div>
                                <div className="text-sm text-gray-500">Add custom key-value pairs</div>
                            </button>
                        </div>

                        {/* Template Selection */}
                        {mode === 'template' && (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    Select Template
                                </label>
                                {loading ? (
                                    <div className="text-center py-4">Loading templates...</div>
                                ) : templates.length > 0 ? (
                                    <select
                                        value={selectedTemplateId}
                                        onChange={(e) => setSelectedTemplateId(e.target.value)}
                                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                    >
                                        <option value="">Select a template...</option>
                                        {templates.map(t => (
                                            <option key={t.id} value={t.id}>
                                                {t.name} {t.is_default ? '(Default)' : ''} - {Object.keys(t.tags || {}).length} tags
                                            </option>
                                        ))}
                                    </select>
                                ) : (
                                    <div className="text-center py-4 text-gray-500">
                                        No templates available. Create one in Settings &gt; Governance.
                                    </div>
                                )}

                                {/* Preview Selected Template */}
                                {selectedTemplate && (
                                    <div className="mt-4 p-4 bg-gray-50 rounded-lg">
                                        <div className="text-sm font-medium text-gray-700 mb-2">Tags to Apply:</div>
                                        <div className="flex flex-wrap gap-2">
                                            {Object.entries(selectedTemplate.tags || {}).map(([key, value]) => (
                                                <span key={key} className="text-xs px-2 py-1 bg-white border rounded">
                                                    <span className="font-medium">{key}</span>
                                                    <span className="text-gray-400 mx-1">=</span>
                                                    <span className="text-emerald-600">{value}</span>
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Manual Tag Entry */}
                        {mode === 'manual' && (
                            <div className="bg-gray-50 rounded-lg p-4">
                                <label className="block text-sm font-medium text-gray-700 mb-3">
                                    Add Tags
                                </label>

                                {manualTags.length > 0 && (
                                    <div className="space-y-2 mb-4">
                                        {manualTags.map(tag => (
                                            <div key={tag.key} className="flex items-center gap-2 bg-white p-2 rounded border">
                                                <span className="font-medium text-gray-700 w-32">{tag.key}</span>
                                                <span className="text-gray-400">=</span>
                                                <span className="flex-1 text-emerald-600">{tag.value}</span>
                                                <button onClick={() => removeManualTag(tag.key)} className="text-red-500">
                                                    <FiTrash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                <div className="flex gap-2">
                                    <input
                                        type="text"
                                        value={newTagKey}
                                        onChange={(e) => setNewTagKey(e.target.value)}
                                        placeholder="Key"
                                        className="w-32 px-2 py-2 border rounded-lg"
                                    />
                                    <span className="self-center text-gray-400">=</span>
                                    <input
                                        type="text"
                                        value={newTagValue}
                                        onChange={(e) => setNewTagValue(e.target.value)}
                                        placeholder="Value"
                                        className="flex-1 px-2 py-2 border rounded-lg"
                                        onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addManualTag())}
                                    />
                                    <button
                                        type="button"
                                        onClick={addManualTag}
                                        className="px-3 py-2 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200"
                                    >
                                        <FiPlus className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        )}
                    </div>
                )}

                {/* Step 2: Variable Input */}
                {step === 2 && (
                    <div className="space-y-6">
                        <div className="text-center text-gray-600 mb-4">
                            The selected template contains variables that need your input:
                        </div>

                        {Object.keys(variableInputs).map(varToken => (
                            <div key={varToken}>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    {varToken.replace(/[{}]/g, '')}
                                </label>
                                <input
                                    type="text"
                                    value={variableInputs[varToken]}
                                    onChange={(e) => setVariableInputs({
                                        ...variableInputs,
                                        [varToken]: e.target.value
                                    })}
                                    placeholder={`Enter value for ${varToken}`}
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                />
                            </div>
                        ))}
                    </div>
                )}

                {/* Step 3: Collision Handling */}
                {step === 3 && (
                    <div className="space-y-6">
                        <div className="text-center text-gray-600 mb-4">
                            Some resources may already have these tags. How should we handle them?
                        </div>

                        <div className="space-y-3">
                            <label
                                className={`flex items-start gap-3 p-4 border-2 rounded-lg cursor-pointer transition-all ${collisionMode === 'skip'
                                    ? 'border-emerald-600 bg-emerald-50'
                                    : 'border-gray-200 hover:border-gray-300'
                                    }`}
                            >
                                <input
                                    type="radio"
                                    name="collision"
                                    checked={collisionMode === 'skip'}
                                    onChange={() => setCollisionMode('skip')}
                                    className="mt-1"
                                />
                                <div>
                                    <div className="font-medium text-gray-900">Skip Existing</div>
                                    <div className="text-sm text-gray-500">
                                        If a tag key already exists on the resource, keep the existing value. Only add missing tags.
                                    </div>
                                </div>
                            </label>

                            <label
                                className={`flex items-start gap-3 p-4 border-2 rounded-lg cursor-pointer transition-all ${collisionMode === 'overwrite'
                                    ? 'border-emerald-600 bg-emerald-50'
                                    : 'border-gray-200 hover:border-gray-300'
                                    }`}
                            >
                                <input
                                    type="radio"
                                    name="collision"
                                    checked={collisionMode === 'overwrite'}
                                    onChange={() => setCollisionMode('overwrite')}
                                    className="mt-1"
                                />
                                <div>
                                    <div className="font-medium text-gray-900 flex items-center gap-2">
                                        Overwrite (Force)
                                        <FiAlertTriangle className="text-yellow-500 w-4 h-4" />
                                    </div>
                                    <div className="text-sm text-gray-500">
                                        Update all selected resources to match this template exactly, replacing existing tag values.
                                    </div>
                                </div>
                            </label>
                        </div>

                        {/* Preview Summary */}
                        <div className="bg-gray-50 rounded-lg p-4">
                            <div className="text-sm font-medium text-gray-700 mb-2">Summary:</div>
                            <div className="text-sm text-gray-600">
                                <p>• {selectedResources.length} resources selected</p>
                                <p>• {Object.keys(getTagsToApply()).length} tags will be applied</p>
                                <p>• Mode: {collisionMode === 'skip' ? 'Skip existing tags' : 'Overwrite existing values'}</p>
                            </div>
                        </div>
                    </div>
                )}

                {/* Step 4: Execution */}
                {step === 4 && (
                    <div className="space-y-6">
                        {executing ? (
                            <div className="text-center py-8">
                                <div className="text-lg font-medium text-gray-900 mb-4">
                                    Updating {selectedResources.length} resources...
                                </div>
                                <div className="w-full bg-gray-200 rounded-full h-4 mb-2">
                                    <div
                                        className="bg-emerald-600 h-4 rounded-full transition-all duration-300"
                                        style={{ width: `${progress}%` }}
                                    />
                                </div>
                                <div className="text-sm text-gray-500">{progress}% complete</div>
                            </div>
                        ) : results ? (
                            <div className="text-center py-8">
                                <div className={`text-5xl mb-4 ${results.failed === 0 ? 'text-emerald-600' : 'text-yellow-500'}`}>
                                    {results.failed === 0 ? <FiCheck /> : <FiAlertTriangle />}
                                </div>
                                <div className="text-lg font-medium text-gray-900 mb-2">
                                    {results.failed === 0 ? 'All Done!' : 'Completed with Errors'}
                                </div>
                                <div className="text-gray-600">
                                    <p>✅ Success: {results.success} Updated</p>
                                    {results.failed > 0 && (
                                        <p className="text-red-600">❌ Failed: {results.failed} (Insufficient Permissions)</p>
                                    )}
                                </div>
                            </div>
                        ) : null}
                    </div>
                )}

                {/* Navigation Buttons */}
                <div className="flex justify-between pt-6 border-t mt-6">
                    {step > 1 && step < 4 && (
                        <button
                            onClick={handleBack}
                            className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                        >
                            Back
                        </button>
                    )}
                    <div className="flex-1" />

                    {step < 4 ? (
                        <button
                            onClick={handleNext}
                            disabled={!canProceed()}
                            className="px-6 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                        >
                            {step === 3 ? 'Apply Tags' : 'Next'}
                        </button>
                    ) : (
                        <button
                            onClick={handleClose}
                            disabled={executing}
                            className="px-6 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                        >
                            {executing ? 'Please wait...' : 'Done'}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default BulkTagWizard;
