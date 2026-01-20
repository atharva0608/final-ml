import React, { useState } from 'react';
import { FiX, FiCheck, FiAlertTriangle } from 'react-icons/fi';
import api from '../../services/api';

const BulkTagEditor = ({ resources, onClose, onSuccess }) => {
    const [operationMode, setOperationMode] = useState('merge');
    const [tags, setTags] = useState({});
    const [saving, setSaving] = useState(false);

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
        if (Object.keys(tags).length === 0) {
            alert('Please add at least one tag');
            return;
        }

        try {
            setSaving(true);

            const response = await api.post(
                '/api/v1/tags/resources/bulk',
                {
                    resource_ids: resources.map(r => r.id),
                    resource_type: resources[0].type,
                    operation_mode: operationMode,
                    tags: tags,
                    region: resources[0].region || 'us-east-1'
                },
                {
                    params: {
                        account_id: resources[0].account_id
                    }
                }
            );

            alert(`Successfully tagged ${response.data.successful} of ${response.data.total_requested} resources`);

            if (onSuccess) onSuccess();
            onClose();
        } catch (error) {
            console.error('Error bulk tagging:', error);
            alert('Failed to tag resources: ' + (error.response?.data?.detail || error.message));
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
                                Bulk Tagging
                            </h3>
                            <p className="text-sm text-gray-600 mt-1">
                                {resources.length} resource{resources.length > 1 ? 's' : ''} selected
                            </p>
                        </div>
                        <button
                            onClick={onClose}
                            className="text-gray-400 hover:text-gray-600"
                        >
                            <FiX size={24} />
                        </button>
                    </div>

                    {/* Operation Mode */}
                    <div className="mb-6">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Operation Mode
                        </label>
                        <div className="flex gap-4">
                            <label className="flex items-center">
                                <input
                                    type="radio"
                                    value="merge"
                                    checked={operationMode === 'merge'}
                                    onChange={(e) => setOperationMode(e.target.value)}
                                    className="mr-2"
                                />
                                <span className="text-sm">Merge (Add/Update tags)</span>
                            </label>
                            <label className="flex items-center">
                                <input
                                    type="radio"
                                    value="replace"
                                    checked={operationMode === 'replace'}
                                    onChange={(e) => setOperationMode(e.target.value)}
                                    className="mr-2"
                                />
                                <span className="text-sm">Replace All (Remove existing)</span>
                            </label>
                        </div>
                        {operationMode === 'replace' && (
                            <div className="mt-2 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-2">
                                <FiAlertTriangle className="text-yellow-600 mt-0.5" />
                                <p className="text-sm text-yellow-800">
                                    Warning: This will remove ALL existing tags and replace with only the tags you specify here.
                                </p>
                            </div>
                        )}
                    </div>

                    {/* Tag Editor */}
                    <div className="mb-6">
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Tags to Apply
                        </label>
                        <div className="space-y-3">
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

                        <button
                            onClick={handleAddTag}
                            className="mt-3 text-sm text-emerald-600 hover:text-emerald-700"
                        >
                            + Add Tag
                        </button>
                    </div>

                    {/* Preview */}
                    {Object.keys(tags).length > 0 && (
                        <div className="mb-6 p-4 bg-gray-50 rounded-lg">
                            <h4 className="font-medium text-gray-900 mb-2">Preview</h4>
                            <p className="text-sm text-gray-600">
                                This will {operationMode === 'merge' ? 'add/update' : 'replace all tags with'}:{' '}
                                <span className="font-medium">
                                    {Object.entries(tags).map(([k, v]) => `${k}: ${v || '(empty)'}`).join(', ')}
                                </span>
                                {' '}on {resources.length} resource{resources.length > 1 ? 's' : ''}.
                            </p>
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
                            disabled={saving || Object.keys(tags).length === 0}
                            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50"
                        >
                            {saving ? (
                                <>
                                    <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
                                    Applying Tags...
                                </>
                            ) : (
                                <>
                                    <FiCheck /> Apply Tags to {resources.length} Resources
                                </>
                            )}
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default BulkTagEditor;
