import React, { useState, useEffect } from 'react';
import { FiPlus, FiEdit2, FiTrash2, FiTag, FiX, FiCheck, FiCopy, FiLayers, FiInfo } from 'react-icons/fi';
import api from '../../services/api';
import toast from 'react-hot-toast';

/**
 * TagTemplateManager - Template-Based Bulk Tagging System
 * 
 * From changes.txt Section 2: Tag Template Management
 * Location: Settings > Governance > Tag Templates
 * 
 * Allows users to define standard sets of tags (presets) with:
 * - Template Name (e.g., "Production Standard", "Dev Team Alpha")
 * - Resource Scope (All, EC2 Only, S3 Only, etc.)
 * - Tag Builder with dynamic variables like {CURRENT_USER_EMAIL}
 */

// Available dynamic variables for tag values
const DYNAMIC_VARIABLES = [
    { token: '{CURRENT_USER_EMAIL}', label: 'User Email', description: 'Email of the user applying tags' },
    { token: '{CURRENT_USER_NAME}', label: 'User Name', description: 'Full name of the user' },
    { token: '{CURRENT_DATE}', label: 'Current Date', description: 'Date when tags are applied (YYYY-MM-DD)' },
    { token: '{CURRENT_ORG}', label: 'Organization', description: 'Name of the organization' },
    { token: '{PROJECT_ID}', label: 'Project ID', description: 'Prompt user to input when applying' }
];

const RESOURCE_SCOPES = [
    { value: 'all', label: 'All Resources' },
    { value: 'ec2', label: 'EC2 Only' },
    { value: 's3', label: 'S3 Only' },
    { value: 'rds', label: 'RDS Only' },
    { value: 'ebs', label: 'EBS Only' },
    { value: 'elb', label: 'Load Balancers Only' }
];

const TagTemplateManager = () => {
    const [templates, setTemplates] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingTemplate, setEditingTemplate] = useState(null);
    const [saving, setSaving] = useState(false);

    const [formData, setFormData] = useState({
        name: '',
        description: '',
        resource_scope: 'all',
        tags: [],  // Array of {key, value} pairs
        is_default: false
    });

    // Temp state for adding new tag rows
    const [newTagKey, setNewTagKey] = useState('');
    const [newTagValue, setNewTagValue] = useState('');

    useEffect(() => {
        fetchTemplates();
    }, []);

    const fetchTemplates = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/tags/templates/');
            setTemplates(response.data.templates || []);
        } catch (error) {
            console.error('Error fetching templates:', error);
            toast.error('Failed to load templates');
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        if (formData.tags.length === 0) {
            toast.error('Please add at least one tag');
            return;
        }

        setSaving(true);

        try {
            // Convert tags array to JSON object for backend
            const tagsJson = {};
            formData.tags.forEach(tag => {
                tagsJson[tag.key] = tag.value;
            });

            const payload = {
                name: formData.name,
                description: formData.description,
                resource_scope: formData.resource_scope,
                tags: tagsJson,
                is_default: formData.is_default
            };

            if (editingTemplate) {
                await api.put(`/api/v1/tags/templates/${editingTemplate.id}`, payload);
                toast.success('Template updated successfully');
            } else {
                await api.post('/api/v1/tags/templates/', payload);
                toast.success('Template created successfully');
            }

            setShowModal(false);
            resetForm();
            fetchTemplates();
        } catch (error) {
            console.error('Error saving template:', error);
            toast.error('Failed to save template: ' + (error.response?.data?.detail || error.message));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (templateId) => {
        if (!window.confirm('Are you sure you want to delete this template?')) return;

        try {
            await api.delete(`/api/v1/tags/templates/${templateId}`);
            toast.success('Template deleted');
            fetchTemplates();
        } catch (error) {
            console.error('Error deleting template:', error);
            toast.error('Failed to delete template');
        }
    };

    const resetForm = () => {
        setFormData({
            name: '',
            description: '',
            resource_scope: 'all',
            tags: [],
            is_default: false
        });
        setNewTagKey('');
        setNewTagValue('');
        setEditingTemplate(null);
    };

    const openEditModal = (template) => {
        setEditingTemplate(template);

        // Convert tags object back to array
        const tagsArray = Object.entries(template.tags || {}).map(([key, value]) => ({
            key,
            value
        }));

        setFormData({
            name: template.name,
            description: template.description || '',
            resource_scope: template.resource_scope || 'all',
            tags: tagsArray,
            is_default: template.is_default || false
        });
        setShowModal(true);
    };

    const addTag = () => {
        if (!newTagKey.trim()) {
            toast.error('Tag key is required');
            return;
        }
        if (formData.tags.some(t => t.key === newTagKey.trim())) {
            toast.error('Tag key already exists');
            return;
        }
        setFormData({
            ...formData,
            tags: [...formData.tags, { key: newTagKey.trim(), value: newTagValue.trim() }]
        });
        setNewTagKey('');
        setNewTagValue('');
    };

    const removeTag = (key) => {
        setFormData({
            ...formData,
            tags: formData.tags.filter(t => t.key !== key)
        });
    };

    const updateTagValue = (key, newValue) => {
        setFormData({
            ...formData,
            tags: formData.tags.map(t => t.key === key ? { ...t, value: newValue } : t)
        });
    };

    const insertVariable = (variable) => {
        setNewTagValue(prev => prev + variable.token);
    };

    const hasVariable = (value) => {
        return DYNAMIC_VARIABLES.some(v => value.includes(v.token));
    };

    return (
        <div className="p-6">
            {/* Header */}
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                        <FiLayers className="text-emerald-600" />
                        Tag Templates
                    </h2>
                    <p className="text-gray-600 mt-1">
                        Create reusable tag presets for quick bulk tagging operations
                    </p>
                </div>
                <button
                    onClick={() => { resetForm(); setShowModal(true); }}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 shadow-lg transition-all"
                >
                    <FiPlus /> Create Template
                </button>
            </div>

            {/* Info Banner */}
            <div className="mb-6 p-4 bg-emerald-50 border border-emerald-200 rounded-lg flex items-start gap-3">
                <FiInfo className="text-emerald-600 w-5 h-5 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-emerald-800">
                    <strong>Tag Templates</strong> are reusable tag presets that can be applied to multiple resources at once.
                    <ul className="mt-2 list-disc list-inside space-y-1">
                        <li>Use <strong>dynamic variables</strong> like <code className="bg-emerald-100 px-1 rounded">{'{CURRENT_USER_EMAIL}'}</code> for auto-filled values</li>
                        <li>Templates follow your organization's <strong>Tag Policies</strong> for validation</li>
                        <li>Apply templates via the <strong>Bulk Tag Wizard</strong> in Resource Hygiene</li>
                    </ul>
                </div>
            </div>

            {loading ? (
                <div className="text-center py-12">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600 mx-auto"></div>
                </div>
            ) : templates.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {templates.map((template) => (
                        <div
                            key={template.id}
                            className={`bg-white rounded-lg shadow-lg border-l-4 p-5 transition-all hover:shadow-xl ${template.is_default ? 'border-emerald-500' : 'border-gray-300'
                                }`}
                        >
                            <div className="flex justify-between items-start mb-3">
                                <div>
                                    <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                                        {template.name}
                                        {template.is_default && (
                                            <span className="text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded">
                                                Default
                                            </span>
                                        )}
                                    </h3>
                                    <p className="text-sm text-gray-500 mt-1">
                                        {template.description || 'No description'}
                                    </p>
                                </div>
                                <div className="flex gap-1">
                                    <button
                                        onClick={() => openEditModal(template)}
                                        className="p-1.5 text-gray-400 hover:text-blue-600 transition-colors"
                                    >
                                        <FiEdit2 className="w-4 h-4" />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(template.id)}
                                        className="p-1.5 text-gray-400 hover:text-red-600 transition-colors"
                                    >
                                        <FiTrash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>

                            <div className="mb-3">
                                <span className="text-xs text-gray-500">Resource Scope:</span>
                                <span className="ml-1 text-xs font-medium text-gray-700">
                                    {RESOURCE_SCOPES.find(s => s.value === template.resource_scope)?.label || 'All'}
                                </span>
                            </div>

                            <div className="space-y-1">
                                <span className="text-xs text-gray-500">Tags ({Object.keys(template.tags || {}).length}):</span>
                                <div className="flex flex-wrap gap-1 mt-1">
                                    {Object.entries(template.tags || {}).slice(0, 3).map(([key, value]) => (
                                        <span
                                            key={key}
                                            className={`text-xs px-2 py-1 rounded ${hasVariable(value)
                                                ? 'bg-blue-100 text-blue-700'
                                                : 'bg-gray-100 text-gray-700'
                                                }`}
                                        >
                                            {key}={hasVariable(value) ? '⚡' : ''}{value.slice(0, 15)}{value.length > 15 ? '...' : ''}
                                        </span>
                                    ))}
                                    {Object.keys(template.tags || {}).length > 3 && (
                                        <span className="text-xs px-2 py-1 bg-gray-100 text-gray-500 rounded">
                                            +{Object.keys(template.tags).length - 3} more
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="text-center py-12 bg-white rounded-lg border border-gray-200">
                    <FiLayers className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                    <p className="text-gray-500">No templates defined yet.</p>
                    <button
                        onClick={() => { resetForm(); setShowModal(true); }}
                        className="mt-4 text-emerald-600 hover:underline"
                    >
                        Create your first template
                    </button>
                </div>
            )}

            {/* Create/Edit Template Modal */}
            {showModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-xl font-bold flex items-center gap-2">
                                <FiLayers className="text-emerald-600" />
                                {editingTemplate ? 'Edit Template' : 'Create Tag Template'}
                            </h3>
                            <button
                                onClick={() => { setShowModal(false); resetForm(); }}
                                className="text-gray-400 hover:text-gray-600"
                            >
                                <FiX className="w-6 h-6" />
                            </button>
                        </div>

                        <form onSubmit={handleSubmit} className="space-y-5">
                            {/* Template Name */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Template Name *
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="e.g., Production Standard, Dev Team Alpha"
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
                                />
                            </div>

                            {/* Description */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Description
                                </label>
                                <textarea
                                    value={formData.description}
                                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                    placeholder="Brief description of when to use this template"
                                    rows="2"
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                />
                            </div>

                            {/* Resource Scope */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Resource Scope
                                </label>
                                <select
                                    value={formData.resource_scope}
                                    onChange={(e) => setFormData({ ...formData, resource_scope: e.target.value })}
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                >
                                    {RESOURCE_SCOPES.map(scope => (
                                        <option key={scope.value} value={scope.value}>{scope.label}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Tag Builder */}
                            <div className="bg-gray-50 rounded-lg p-4 border">
                                <label className="block text-sm font-medium text-gray-700 mb-3">
                                    Tag Builder *
                                </label>

                                {/* Existing Tags */}
                                {formData.tags.length > 0 && (
                                    <div className="space-y-2 mb-4">
                                        {formData.tags.map((tag) => (
                                            <div key={tag.key} className="flex items-center gap-2 bg-white p-2 rounded border">
                                                <span className="font-medium text-gray-700 w-32 truncate">{tag.key}</span>
                                                <span className="text-gray-400">=</span>
                                                <input
                                                    type="text"
                                                    value={tag.value}
                                                    onChange={(e) => updateTagValue(tag.key, e.target.value)}
                                                    className={`flex-1 px-2 py-1 border rounded text-sm ${hasVariable(tag.value) ? 'bg-blue-50 border-blue-200' : ''
                                                        }`}
                                                />
                                                <button
                                                    type="button"
                                                    onClick={() => removeTag(tag.key)}
                                                    className="p-1 text-red-500 hover:text-red-700"
                                                >
                                                    <FiTrash2 className="w-4 h-4" />
                                                </button>
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Add New Tag */}
                                <div className="flex items-center gap-2">
                                    <input
                                        type="text"
                                        value={newTagKey}
                                        onChange={(e) => setNewTagKey(e.target.value)}
                                        placeholder="Key"
                                        className="w-32 px-2 py-2 border rounded-lg text-sm"
                                    />
                                    <span className="text-gray-400">=</span>
                                    <input
                                        type="text"
                                        value={newTagValue}
                                        onChange={(e) => setNewTagValue(e.target.value)}
                                        placeholder="Value (or use variable)"
                                        className="flex-1 px-2 py-2 border rounded-lg text-sm"
                                        onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
                                    />
                                    <button
                                        type="button"
                                        onClick={addTag}
                                        className="px-3 py-2 bg-emerald-100 text-emerald-700 rounded-lg hover:bg-emerald-200"
                                    >
                                        <FiPlus className="w-4 h-4" />
                                    </button>
                                </div>

                                {/* Dynamic Variables Helper */}
                                <div className="mt-4 pt-4 border-t border-gray-200">
                                    <p className="text-xs text-gray-500 mb-2">
                                        Click to insert dynamic variable:
                                    </p>
                                    <div className="flex flex-wrap gap-2">
                                        {DYNAMIC_VARIABLES.map((variable) => (
                                            <button
                                                key={variable.token}
                                                type="button"
                                                onClick={() => insertVariable(variable)}
                                                className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition-colors"
                                                title={variable.description}
                                            >
                                                {variable.token}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Default Toggle */}
                            <label className="flex items-center gap-3 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={formData.is_default}
                                    onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                                    className="w-4 h-4 text-emerald-600 rounded focus:ring-emerald-500"
                                />
                                <span className="text-sm text-gray-700">Set as default template</span>
                            </label>

                            {/* Action Buttons */}
                            <div className="flex gap-4 justify-end pt-4 border-t">
                                <button
                                    type="button"
                                    onClick={() => { setShowModal(false); resetForm(); }}
                                    className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    disabled={saving || formData.tags.length === 0}
                                    className="px-6 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 shadow-lg disabled:opacity-50"
                                >
                                    {saving ? 'Saving...' : (editingTemplate ? 'Update Template' : 'Create Template')}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default TagTemplateManager;
