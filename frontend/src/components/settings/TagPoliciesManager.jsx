import React, { useState, useEffect } from 'react';
import { FiPlus, FiEdit2, FiTrash2, FiCheck, FiAlertCircle } from 'react-icons/fi';
import api from '../../services/api';

const TagPoliciesManager = () => {
    const [policies, setPolicies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingPolicy, setEditingPolicy] = useState(null);

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
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        try {
            if (editingPolicy) {
                await api.put(`/api/v1/tags/policies/${editingPolicy.id}`, formData);
            } else {
                await api.post('/api/v1/tags/policies', formData);
            }

            setShowModal(false);
            resetForm();
            fetchPolicies();
        } catch (error) {
            console.error('Error saving policy:', error);
            alert('Failed to save policy: ' + (error.response?.data?.detail || error.message));
        }
    };

    const handleDelete = async (policyId) => {
        if (!window.confirm('Are you sure you want to delete this policy?')) return;

        try {
            await api.delete(`/api/v1/tags/policies/${policyId}`);
            fetchPolicies();
        } catch (error) {
            console.error('Error deleting policy:', error);
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
        setEditingPolicy(null);
    };

    const openEditModal = (policy) => {
        setEditingPolicy(policy);
        setFormData({
            tag_key: policy.tag_key,
            description: policy.description || '',
            value_mode: policy.value_mode,
            allowed_values: policy.allowed_values || [],
            validation_regex: policy.validation_regex || '',
            enforcement_level: policy.enforcement_level,
            resource_types: policy.resource_types || ['*'],
            regions: policy.regions || ['*']
        });
        setShowModal(true);
    };

    const getEnforcementBadge = (level) => {
        const colors = {
            advisory: 'bg-yellow-100 text-yellow-800',
            required: 'bg-red-100 text-red-800',
            strict: 'bg-gray-900 text-white'
        };
        return (
            <span className={`px-2 py-1 rounded text-xs font-medium ${colors[level]}`}>
                {level.toUpperCase()}
            </span>
        );
    };

    return (
        <div className="p-6">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-2xl font-bold text-gray-900">Tag Policies</h2>
                    <p className="text-gray-600 mt-1">Define and enforce tagging standards</p>
                </div>
                <button
                    onClick={() => { resetForm(); setShowModal(true); }}
                    className="flex items-center gap-2 px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
                >
                    <FiPlus /> Create Policy
                </button>
            </div>

            {loading ? (
                <div className="text-center py-12">
                    <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-600 mx-auto"></div>
                </div>
            ) : (
                <div className="bg-white rounded-lg shadow overflow-hidden">
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Tag Key</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Enforcement</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Scope</th>
                                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Value Mode</th>
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {policies.map((policy) => (
                                <tr key={policy.id} className="hover:bg-gray-50">
                                    <td className="px-6 py-4">
                                        <div className="text-sm font-medium text-gray-900">{policy.tag_key}</div>
                                        <div className="text-sm text-gray-500">{policy.description}</div>
                                    </td>
                                    <td className="px-6 py-4">
                                        {getEnforcementBadge(policy.enforcement_level)}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500">
                                        {policy.resource_types?.join(', ') || '*'}
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500">
                                        {policy.value_mode}
                                    </td>
                                    <td className="px-6 py-4 text-right text-sm font-medium">
                                        <button
                                            onClick={() => openEditModal(policy)}
                                            className="text-emerald-600 hover:text-emerald-900 mr-3"
                                        >
                                            <FiEdit2 className="inline" />
                                        </button>
                                        <button
                                            onClick={() => handleDelete(policy.id)}
                                            className="text-red-600 hover:text-red-900"
                                        >
                                            <FiTrash2 className="inline" />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>

                    {policies.length === 0 && (
                        <div className="text-center py-12 text-gray-500">
                            No tag policies defined yet. Create one to get started.
                        </div>
                    )}
                </div>
            )}

            {/* Modal */}
            {showModal && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
                        <h3 className="text-xl font-bold mb-4">
                            {editingPolicy ? 'Edit Policy' : 'Create Tag Policy'}
                        </h3>

                        <form onSubmit={handleSubmit} className="space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Tag Key *
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={formData.tag_key}
                                    onChange={(e) => setFormData({ ...formData, tag_key: e.target.value })}
                                    placeholder="e.g., Owner, Environment"
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Description
                                </label>
                                <textarea
                                    value={formData.description}
                                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                    placeholder="Help text for users"
                                    rows="2"
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                />
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Enforcement Level *
                                </label>
                                <select
                                    value={formData.enforcement_level}
                                    onChange={(e) => setFormData({ ...formData, enforcement_level: e.target.value })}
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                >
                                    <option value="advisory">Advisory (Warning only)</option>
                                    <option value="required">Required (Blocks cleanup)</option>
                                    <option value="strict">Strict (Blocks all operations)</option>
                                </select>
                            </div>

                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">
                                    Value Mode
                                </label>
                                <select
                                    value={formData.value_mode}
                                    onChange={(e) => setFormData({ ...formData, value_mode: e.target.value })}
                                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-emerald-500"
                                >
                                    <option value="free_text">Free Text</option>
                                    <option value="predefined">Predefined Values</option>
                                </select>
                            </div>

                            <div className="flex gap-4 justify-end pt-4">
                                <button
                                    type="button"
                                    onClick={() => { setShowModal(false); resetForm(); }}
                                    className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                                >
                                    Cancel
                                </button>
                                <button
                                    type="submit"
                                    className="px-4 py-2 bg-emerald-600 text-white rounded-lg hover:bg-emerald-700"
                                >
                                    {editingPolicy ? 'Update Policy' : 'Create Policy'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
};

export default TagPoliciesManager;
