import React, { useState, useEffect } from 'react';
import { FiPlus, FiEdit2, FiTrash2, FiShield, FiAlertTriangle, FiCheck, FiX, FiInfo } from 'react-icons/fi';
import api from '../../services/api';
import toast from 'react-hot-toast';

/**
 * TagPoliciesManager - Governance Rules Management
 * 
 * This component manages TAG POLICIES which are ENFORCEMENT RULES.
 * Policies define which tags are required/advisory and how to validate them.
 * 
 * NOT to be confused with TagTemplates (reusable presets for bulk tagging).
 */
const TagPoliciesList = () => {
    const [policies, setPolicies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingPolicy, setEditingPolicy] = useState(null);
    const [saving, setSaving] = useState(false);

    const [formData, setFormData] = useState({
        tag_key: '',
        description: '',
        value_mode: 'free_text',
        allowed_values: [],
        validation_regex: '',
        enforcement_level: 'advisory',
        resource_types: ['*'],
        regions: ['*']
    });

    // Temp state for allowed values input
    const [allowedValueInput, setAllowedValueInput] = useState('');

    useEffect(() => {
        fetchPolicies();
    }, []);

    const fetchPolicies = async () => {
        try {
            setLoading(true);
            const response = await api.get('/api/v1/tags/policies');
            setPolicies(response.data.policies || []);
        } catch (error) {
            console.error('Error fetching tag policies:', error);
            toast.error('Failed to load tag policies');
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);

        try {
            if (editingPolicy) {
                await api.put(`/api/v1/tags/policies/${editingPolicy.id}`, formData);
                toast.success('Policy updated successfully');
            } else {
                await api.post('/api/v1/tags/policies', formData);
                toast.success('Policy created successfully');
            }

            setShowModal(false);
            resetForm();
            fetchPolicies();
        } catch (error) {
            console.error('Error saving policy:', error);
            toast.error('Failed to save policy: ' + (error.response?.data?.detail || error.message));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async (policyId) => {
        if (!window.confirm('Are you sure you want to delete this policy?')) return;

        try {
            await api.delete(`/api/v1/tags/policies/${policyId}`);
            toast.success('Policy deleted');
            fetchPolicies();
        } catch (error) {
            console.error('Error deleting policy:', error);
            toast.error('Failed to delete policy');
        }
    };

    const resetForm = () => {
        setFormData({
            tag_key: '',
            description: '',
            value_mode: 'free_text',
            allowed_values: [],
            validation_regex: '',
            enforcement_level: 'advisory',
            resource_types: ['*'],
            regions: ['*']
        });
        setAllowedValueInput('');
        setEditingPolicy(null);
    };

    const openEditModal = (policy) => {
        setEditingPolicy(policy);
        setFormData({
            tag_key: policy.tag_key,
            description: policy.description || '',
            value_mode: policy.value_mode || 'free_text',
            allowed_values: policy.allowed_values || [],
            validation_regex: policy.validation_regex || '',
            enforcement_level: policy.enforcement_level,
            resource_types: policy.resource_types || ['*'],
            regions: policy.regions || ['*']
        });
        setShowModal(true);
    };

    const addAllowedValue = () => {
        if (allowedValueInput.trim() && !formData.allowed_values.includes(allowedValueInput.trim())) {
            setFormData({
                ...formData,
                allowed_values: [...formData.allowed_values, allowedValueInput.trim()]
            });
            setAllowedValueInput('');
        }
    };

    const removeAllowedValue = (value) => {
        setFormData({
            ...formData,
            allowed_values: formData.allowed_values.filter(v => v !== value)
        });
    };

    const getEnforcementBadge = (level) => {
        const config = {
            advisory: { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300', icon: FiInfo, label: 'ADVISORY' },
            required: { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300', icon: FiAlertTriangle, label: 'REQUIRED' },
            strict: { bg: 'bg-gray-900', text: 'text-white', border: 'border-gray-700', icon: FiShield, label: 'STRICT' }
        };
        const c = config[level] || config.advisory;
        const Icon = c.icon;
        return (
            <span className={`inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-medium border ${c.bg} ${c.text} ${c.border}`}>
                <Icon className="w-3 h-3" />
                {c.label}
            </span>
        );
    };

    // Group policies by enforcement level for visual separation
    const requiredPolicies = policies.filter(p => p.enforcement_level === 'required' || p.enforcement_level === 'strict');
    const advisoryPolicies = policies.filter(p => p.enforcement_level === 'advisory');

    return (
        <div className="p-6">
            {/* Header */}
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
                        <FiShield className="text-red-600" />
                        Tag Policies
                    </h2>
                    <p className="text-gray-600 mt-1">
                        Define enforcement rules for resource tags. Required policies block operations on non-compliant resources.
                    </p>
                </div>
                <button
                    onClick={() => { resetForm(); setShowModal(true); }}
                    className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 shadow-lg transition-all"
                >
                    <FiPlus /> Create Policy
                </button>
            </div>

            {/* Info Banner */}
            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-3">
                <FiInfo className="text-blue-600 w-5 h-5 mt-0.5 flex-shrink-0" />
                <div className="text-sm text-blue-800">
                    <strong>Tag Policies</strong> are governance rules that enforce tagging compliance.
                    <ul className="mt-2 list-disc list-inside space-y-1">
                        <li><strong>Advisory</strong>: Shows warnings but doesn't block actions</li>
                        <li><strong>Required</strong>: Blocks cleanup/delete actions on non-compliant resources</li>
                        <li><strong>Strict</strong>: Blocks ALL operations including authorization</li>
                    </ul>
                    <p className="mt-2">Need to apply tags in bulk? Use <strong>Tag Templates</strong> instead.</p>
                </div>
            </div>

            {loading ? (
                <div className="text-center py-12">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-600 mx-auto"></div>
                </div>
            ) : (
                <div className="space-y-6">
                    {/* Required/Strict Policies Section */}
                    {requiredPolicies.length > 0 && (
                        <div>
                            <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                                <FiAlertTriangle className="text-red-600" />
                                Blocking Policies ({requiredPolicies.length})
                            </h3>
                            <div className="bg-white rounded-lg shadow-lg overflow-hidden border border-red-200">
                                <table className="min-w-full divide-y divide-gray-200">
                                    <thead className="bg-red-50">
                                        <tr>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tag Key</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Value Mode</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Enforcement</th>
                                            <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody className="bg-white divide-y divide-gray-200">
                                        {requiredPolicies.map((policy) => (
                                            <tr key={policy.id} className="hover:bg-gray-50 transition-colors">
                                                <td className="px-6 py-4">
                                                    <div className="text-sm font-medium text-gray-900">{policy.tag_key}</div>
                                                </td>
                                                <td className="px-6 py-4 text-sm text-gray-500">
                                                    {policy.description || '—'}
                                                </td>
                                                <td className="px-6 py-4 text-sm text-gray-500">
                                                    {policy.value_mode === 'predefined' ? (
                                                        <span className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded">
                                                            {policy.allowed_values?.length || 0} values
                                                        </span>
                                                    ) : (
                                                        <span className="text-xs text-gray-500">Free text</span>
                                                    )}
                                                </td>
                                                <td className="px-6 py-4">
                                                    {getEnforcementBadge(policy.enforcement_level)}
                                                </td>
                                                <td className="px-6 py-4 text-right text-sm font-medium">
                                                    <button
                                                        onClick={() => openEditModal(policy)}
                                                        className="text-blue-600 hover:text-blue-900 mr-3"
                                                    >
                                                        <FiEdit2 className="inline w-4 h-4" />
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(policy.id)}
                                                        className="text-red-600 hover:text-red-900"
                                                    >
                                                        <FiTrash2 className="inline w-4 h-4" />
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Advisory Policies Section */}
                    <div>
                        <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                            <FiInfo className="text-yellow-600" />
                            Advisory Policies ({advisoryPolicies.length})
                        </h3>
                        {advisoryPolicies.length > 0 ? (
                            <div className="bg-white rounded-lg shadow-lg overflow-hidden border border-gray-200">
                                <table className="min-w-full divide-y divide-gray-200">
                                    <thead className="bg-gray-50">
                                        <tr>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tag Key</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Value Mode</th>
                                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Enforcement</th>
                                            <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                                        </tr>
                                    </thead>
                                    <tbody className="bg-white divide-y divide-gray-200">
                                        {advisoryPolicies.map((policy) => (
                                            <tr key={policy.id} className="hover:bg-gray-50 transition-colors">
                                                <td className="px-6 py-4">
                                                    <div className="text-sm font-medium text-gray-900">{policy.tag_key}</div>
                                                </td>
                                                <td className="px-6 py-4 text-sm text-gray-500">
                                                    {policy.description || '—'}
                                                </td>
                                                <td className="px-6 py-4 text-sm text-gray-500">
                                                    {policy.value_mode === 'predefined' ? (
                                                        <span className="text-xs bg-purple-100 text-purple-700 px-2 py-1 rounded">
                                                            {policy.allowed_values?.length || 0} values
                                                        </span>
                                                    ) : (
                                                        <span className="text-xs text-gray-500">Free text</span>
                                                    )}
                                                </td>
                                                <td className="px-6 py-4">
                                                    {getEnforcementBadge(policy.enforcement_level)}
                                                </td>
                                                <td className="px-6 py-4 text-right text-sm font-medium">
                                                    <button
                                                        onClick={() => openEditModal(policy)}
                                                        className="text-blue-600 hover:text-blue-900 mr-3"
                                                    >
                                                        <FiEdit2 className="inline w-4 h-4" />
                                                    </button>
                                                    <button
                                                        onClick={() => handleDelete(policy.id)}
                                                        className="text-red-600 hover:text-red-900"
                                                    >
                                                        <FiTrash2 className="inline w-4 h-4" />
                                                    </button>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        ) : (
                            <div className="text-center py-8 bg-white rounded-lg border border-gray-200">
                                <FiShield className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                                <p className="text-gray-500">No advisory policies defined yet.</p>
                                <button
                                    onClick={() => { resetForm(); setShowModal(true); }}
                                    className="mt-4 text-red-600 hover:underline"
                                >
                                    Create your first policy
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            )}

            {/* Create/Edit Policy Modal */}
            {showModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-xl p-6 w-full max-w-xl max-h-[90vh] overflow-y-auto shadow-2xl">
                        <div className="flex justify-between items-center mb-6">
                            <h3 className="text-xl font-bold flex items-center gap-2">
                                <FiShield className="text-red-600" />
                                {editingPolicy ? 'Edit Policy' : 'Create Tag Policy'}
                            </h3>
                            <button
                                onClick={() => { setShowModal(false); resetForm(); }}
                                className="text-gray-400 hover:text-gray-600"
                            >
                                <FiX className="w-6 h-6" />
                            </button>
                        </div>

                        <form onSubmit={handleSubmit} className="space-y-4">
                            {/* Tag Key */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Tag Key *
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={formData.tag_key}
                                    onChange={(e) => setFormData({ ...formData, tag_key: e.target.value })}
                                    placeholder="e.g., Owner, Environment, CostCenter"
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-red-500 focus:border-red-500"
                                    disabled={!!editingPolicy}
                                />
                                {editingPolicy && (
                                    <p className="text-xs text-gray-500 mt-1">Tag key cannot be changed after creation</p>
                                )}
                            </div>

                            {/* Description */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Description
                                </label>
                                <textarea
                                    value={formData.description}
                                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                    placeholder="Help text for users (e.g., 'Enter your team email address')"
                                    rows="2"
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-red-500"
                                />
                            </div>

                            {/* Enforcement Level */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Enforcement Level *
                                </label>
                                <select
                                    value={formData.enforcement_level}
                                    onChange={(e) => setFormData({ ...formData, enforcement_level: e.target.value })}
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-red-500"
                                >
                                    <option value="advisory">⚠️ Advisory - Warning only, no blocking</option>
                                    <option value="required">🛑 Required - Blocks cleanup/delete actions</option>
                                    <option value="strict">🔒 Strict - Blocks ALL operations including authorization</option>
                                </select>
                            </div>

                            {/* Value Mode */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Value Mode
                                </label>
                                <select
                                    value={formData.value_mode}
                                    onChange={(e) => setFormData({ ...formData, value_mode: e.target.value })}
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-red-500"
                                >
                                    <option value="free_text">Free Text - Any value allowed</option>
                                    <option value="predefined">Predefined - Must match allowed values</option>
                                </select>
                            </div>

                            {/* Allowed Values (only for predefined mode) */}
                            {formData.value_mode === 'predefined' && (
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">
                                        Allowed Values
                                    </label>
                                    <div className="flex gap-2">
                                        <input
                                            type="text"
                                            value={allowedValueInput}
                                            onChange={(e) => setAllowedValueInput(e.target.value)}
                                            placeholder="Add allowed value..."
                                            className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-red-500"
                                            onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addAllowedValue())}
                                        />
                                        <button
                                            type="button"
                                            onClick={addAllowedValue}
                                            className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
                                        >
                                            Add
                                        </button>
                                    </div>
                                    {formData.allowed_values.length > 0 && (
                                        <div className="mt-2 flex flex-wrap gap-2">
                                            {formData.allowed_values.map((value) => (
                                                <span
                                                    key={value}
                                                    className="inline-flex items-center gap-1 px-2 py-1 bg-purple-100 text-purple-700 rounded text-sm"
                                                >
                                                    {value}
                                                    <button
                                                        type="button"
                                                        onClick={() => removeAllowedValue(value)}
                                                        className="hover:text-purple-900"
                                                    >
                                                        <FiX className="w-3 h-3" />
                                                    </button>
                                                </span>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            )}

                            {/* Validation Regex */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Validation Regex (optional)
                                </label>
                                <input
                                    type="text"
                                    value={formData.validation_regex}
                                    onChange={(e) => setFormData({ ...formData, validation_regex: e.target.value })}
                                    placeholder="e.g., ^CC-\d{4}$ for CostCenter format"
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-red-500 font-mono text-sm"
                                />
                                <p className="text-xs text-gray-500 mt-1">
                                    Regular expression to validate tag values (e.g., ^[a-z]+@company\.com$ for emails)
                                </p>
                            </div>

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
                                    disabled={saving}
                                    className="px-6 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 shadow-lg disabled:opacity-50"
                                >
                                    {saving ? 'Saving...' : (editingPolicy ? 'Update Policy' : 'Create Policy')}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default TagPoliciesList;
