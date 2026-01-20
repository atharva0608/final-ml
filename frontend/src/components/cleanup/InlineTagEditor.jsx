import React, { useState } from 'react';
import { FiX, FiPlus, FiCheck, FiAlertCircle } from 'react-icons/fi';
import api from '../../services/api';

const InlineTagEditor = ({ resource, onClose, onSuccess }) => {
    const [tags, setTags] = useState(resource.tags || {});
    const [saving, setSaving] = useState(false);
    const [suggestions, setSuggestions] = useState([]);

    const handleAddTag = () => {
        const key = prompt('Enter tag key:');
        if (key) {
            setTags({ ...tags, [key]: '' });
        }
    };

    const handleRemoveTag = (key) => {
        const newTags = { ...tags };
        delete newTags[key];
        setTags(newTags);
    };

    const handleTagChange = (key, value) => {
        setTags({ ...tags, [key]: value });
    };

    const handleSave = async () => {
        try {
            setSaving(true);

            await api.post(
                `/api/v1/tags/resources/${resource.type}/${resource.id}`,
                {
                    tags,
                    propagate_to_related: false,
                    overwrite_existing: false
                },
                {
                    params: {
                        account_id: resource.account_id,
                        region: resource.region || 'us-east-1'
                    }
                }
            );

            if (onSuccess) onSuccess();
            onClose();
        } catch (error) {
            console.error('Error saving tags:', error);
            alert('Failed to save tags: ' + (error.response?.data?.detail || error.message));
        } finally {
            setSaving(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
                <div className="p-6">
                    {/* Header */}
                    <div className="flex justify-between items-center mb-6">
                        <div>
                            <h3 className="text-xl font-bold text-gray-900">
                                Edit Tags
                            </h3>
                            <p className="text-sm text-gray-600 mt-1">
                                {resource.type}: {resource.name || resource.id}
                            </p>
                        </div>
                        <button
                            onClick={onClose}
                            className="text-gray-400 hover:text-gray-600"
                        >
                            <FiX size={24} />
                        </button>
                    </div>

                    {/* Compliance Status */}
                    {resource.is_compliant === false && (
                        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
                            <FiAlertCircle className="text-red-600 mt-0.5" />
                            <div className="text-sm">
                                <p className="font-medium text-red-900">Missing Required Tags</p>
                                <p className="text-red-700 mt-1">
                                    {resource.missing_tags?.join(', ')}
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Tag Editor */}
                    <div className="space-y-3 mb-6">
                        {Object.entries(tags).map(([key, value]) => (
                            <div key={key} className="flex gap-2">
                                <input
                                    type="text"
                                    value={key}
                                    readOnly
                                    className="w-1/3 px-3 py-2 border rounded-lg bg-gray-50"
                                />
                                <input
                                    type="text"
                                    value={value}
                                    onChange={(e) => handleTagChange(key, e.target.value)}
                                    placeholder="Tag value"
                                    className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                />
                                <button
                                    onClick={() => handleRemoveTag(key)}
                                    className="p-2 text-red-600 hover:bg-red-50 rounded-lg"
                                >
                                    <FiX size={20} />
                                </button>
                            </div>
                        ))}
                    </div>

                    {/* Add Tag Button */}
                    <button
                        onClick={handleAddTag}
                        className="flex items-center gap-2 text-emerald-600 hover:text-emerald-700 mb-6"
                    >
                        <FiPlus /> Add Tag
                    </button>

                    {/* Suggestions */}
                    {suggestions.length > 0 && (
                        <div className="mb-6 p-4 bg-blue-50 rounded-lg">
                            <h4 className="font-medium text-blue-900 mb-2">Suggestions</h4>
                            <div className="space-y-2">
                                {suggestions.map((suggestion, idx) => (
                                    <div key={idx} className="flex justify-between items-center">
                                        <div>
                                            <span className="font-medium">{suggestion.key}:</span> {suggestion.value}
                                            <span className="text-xs text-blue-600 ml-2">({suggestion.reason})</span>
                                        </div>
                                        <button
                                            onClick={() => handleTagChange(suggestion.key, suggestion.value)}
                                            className="text-blue-600 hover:text-blue-700 text-sm"
                                        >
                                            Apply
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Footer */}
                    <div className="flex justify-end gap-3">
                        <button
                            onClick={onClose}
                            className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                            disabled={saving}
                        >
                            Cancel
                        </button>
                        <button
                            onClick={handleSave}
                            disabled={saving}
                            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                        >
                            {saving ? (
                                <>
                                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                                    Saving...
                                </>
                            ) : (
                                <>
                                    <FiCheck /> Save Changes
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default InlineTagEditor;
