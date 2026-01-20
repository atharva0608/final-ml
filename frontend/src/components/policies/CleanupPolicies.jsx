/**
 * Cleanup Policies Management Component
 */
import React, { useState, useEffect } from 'react';
import {
    FiPlus, FiTrash2, FiEdit2, FiSave, FiX, FiCheck, FiAlertTriangle, FiFilter
} from 'react-icons/fi';
import { Card, Button, Input, Modal, Badge } from '../shared';
import api from '../../services/api';
import toast from 'react-hot-toast';

const RESOURCE_TYPES = [
    'VOLUME', 'SNAPSHOT', 'ELASTIC_IP', 'LOAD_BALANCER', 'RDS_DB', 'S3_BUCKET'
];

const CleanupPolicies = () => {
    const [policies, setPolicies] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingPolicy, setEditingPolicy] = useState(null);

    // Form State
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        resource_type: 'VOLUME',
        priority: 100,
        action: 'NOTIFY',
        conditions: {
            operator: 'AND',
            rules: [{ field: 'age_days', op: 'gt', value: 30 }]
        }
    });

    useEffect(() => {
        fetchPolicies();
    }, []);

    const fetchPolicies = async () => {
        try {
            setLoading(true);
            const res = await api.get('/cleanup-policies/');
            setPolicies(res.data);
        } catch (error) {
            toast.error('Failed to load policies');
            console.error(error);
        } finally {
            setLoading(false);
        }
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        try {
            if (editingPolicy) {
                await api.patch(`/cleanup-policies/${editingPolicy.id}`, formData);
                toast.success('Policy updated');
            } else {
                await api.post('/cleanup-policies/', formData);
                toast.success('Policy created');
            }
            setShowModal(false);
            fetchPolicies();
            setEditingPolicy(null);
            resetForm();
        } catch (error) {
            toast.error('Failed to save policy');
            console.error(error);
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm('Are you sure you want to delete this policy?')) return;
        try {
            await api.delete(`/cleanup-policies/${id}`);
            toast.success('Policy deleted');
            fetchPolicies();
        } catch (error) {
            toast.error('Failed to delete policy');
        }
    };

    const resetForm = () => {
        setFormData({
            name: '',
            description: '',
            resource_type: 'VOLUME',
            priority: 100,
            action: 'NOTIFY',
            conditions: { operator: 'AND', rules: [{ field: 'age_days', op: 'gt', value: 30 }] }
        });
    };

    const handleEdit = (policy) => {
        setEditingPolicy(policy);
        setFormData({
            name: policy.name,
            description: policy.description,
            resource_type: policy.resource_type,
            priority: policy.priority,
            action: policy.action,
            conditions: policy.conditions
        });
        setShowModal(true);
    };

    const addRule = () => {
        setFormData({
            ...formData,
            conditions: {
                ...formData.conditions,
                rules: [...formData.conditions.rules, { field: 'age_days', op: 'gt', value: 0 }]
            }
        });
    };

    const removeRule = (index) => {
        const newRules = [...formData.conditions.rules];
        newRules.splice(index, 1);
        setFormData({
            ...formData,
            conditions: { ...formData.conditions, rules: newRules }
        });
    };

    const updateRule = (index, field, value) => {
        const newRules = [...formData.conditions.rules];
        newRules[index][field] = value;
        setFormData({
            ...formData,
            conditions: { ...formData.conditions, rules: newRules }
        });
    };

    return (
        <div className="space-y-6">
            <div className="flex justify-between items-center">
                <div>
                    <h2 className="text-xl font-semibold text-gray-900">Cleanup Policies</h2>
                    <p className="text-sm text-gray-500">Define automated rules for resource hygiene</p>
                </div>
                <Button
                    variant="primary"
                    icon={<FiPlus />}
                    onClick={() => { resetForm(); setShowModal(true); }}
                >
                    Create Policy
                </Button>
            </div>

            {loading ? (
                <div className="text-center py-8">Loading policies...</div>
            ) : (
                <div className="grid grid-cols-1 gap-4">
                    {policies.map(policy => (
                        <Card key={policy.id} className="hover:shadow-md transition-shadow">
                            <div className="flex justify-between items-start">
                                <div>
                                    <div className="flex items-center gap-2">
                                        <h3 className="font-medium text-gray-900">{policy.name}</h3>
                                        <Badge variant={policy.is_active ? 'success' : 'secondary'}>
                                            {policy.is_active ? 'Active' : 'Disabled'}
                                        </Badge>
                                        <Badge variant="blue">{policy.resource_type}</Badge>
                                    </div>
                                    <p className="text-sm text-gray-600 mt-1">{policy.description}</p>

                                    {/* Conditions Display */}
                                    <div className="mt-3 flex flex-wrap gap-2">
                                        {policy.conditions.rules.map((rule, idx) => (
                                            <span key={idx} className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                                                {rule.field} {rule.op} {rule.value}
                                            </span>
                                        ))}
                                        <span className="text-xs text-gray-500 self-center">
                                            Action: <span className="font-semibold text-red-600">{policy.action}</span>
                                        </span>
                                    </div>
                                </div>

                                <div className="flex gap-2">
                                    <button
                                        onClick={() => handleEdit(policy)}
                                        className="p-2 text-gray-400 hover:text-blue-600 transition-colors"
                                    >
                                        <FiEdit2 />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(policy.id)}
                                        className="p-2 text-gray-400 hover:text-red-600 transition-colors"
                                    >
                                        <FiTrash2 />
                                    </button>
                                </div>
                            </div>
                        </Card>
                    ))}

                    {policies.length === 0 && (
                        <div className="text-center py-12 bg-gray-50 rounded-lg border-2 border-dashed border-gray-200">
                            <p className="text-gray-500">No policies defined yet.</p>
                            <Button
                                variant="outline"
                                className="mt-4"
                                onClick={() => { resetForm(); setShowModal(true); }}
                            >
                                Create your first policy
                            </Button>
                        </div>
                    )}
                </div>
            )}

            {/* Create/Edit Modal */}
            {showModal && (
                <div className="fixed inset-0 z-50 overflow-y-auto">
                    <div className="flex items-center justify-center min-h-screen pt-4 px-4 pb-20 text-center sm:block sm:p-0">
                        <div className="fixed inset-0 transition-opacity" onClick={() => setShowModal(false)}>
                            <div className="absolute inset-0 bg-gray-500 opacity-75"></div>
                        </div>

                        <div className="inline-block align-bottom bg-white rounded-lg text-left overflow-hidden shadow-xl transform transition-all sm:my-8 sm:align-middle sm:max-w-lg sm:w-full">
                            <form onSubmit={handleSubmit}>
                                <div className="bg-white px-4 pt-5 pb-4 sm:p-6 sm:pb-4">
                                    <h3 className="text-lg leading-6 font-medium text-gray-900 mb-4">
                                        {editingPolicy ? 'Edit Policy' : 'Create New Policy'}
                                    </h3>

                                    <div className="space-y-4">
                                        <Input
                                            label="Policy Name"
                                            value={formData.name}
                                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                            required
                                        />

                                        <Input
                                            label="Description"
                                            value={formData.description}
                                            onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                        />

                                        <div className="grid grid-cols-2 gap-4">
                                            <div>
                                                <label className="block text-sm font-medium text-gray-700 mb-1">Resource Type</label>
                                                <select
                                                    className="w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                                                    value={formData.resource_type}
                                                    onChange={(e) => setFormData({ ...formData, resource_type: e.target.value })}
                                                >
                                                    {RESOURCE_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                                                </select>
                                            </div>

                                            <div>
                                                <label className="block text-sm font-medium text-gray-700 mb-1">Action</label>
                                                <select
                                                    className="w-full border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                                                    value={formData.action}
                                                    onChange={(e) => setFormData({ ...formData, action: e.target.value })}
                                                >
                                                    <option value="NOTIFY">Notify Only</option>
                                                    <option value="DELETE">Delete</option>
                                                    <option value="SNAPSHOT_STOP">Snapshot & Delete</option>
                                                </select>
                                            </div>
                                        </div>

                                        {/* Rules Builder */}
                                        <div className="bg-gray-50 p-4 rounded-md">
                                            <div className="flex justify-between items-center mb-2">
                                                <label className="block text-sm font-medium text-gray-700">Conditions (AND)</label>
                                                <button type="button" onClick={addRule} className="text-xs text-blue-600 hover:text-blue-800">
                                                    + Add Condition
                                                </button>
                                            </div>

                                            <div className="space-y-2">
                                                {formData.conditions.rules.map((rule, idx) => (
                                                    <div key={idx} className="flex gap-2 items-center">
                                                        <input
                                                            type="text"
                                                            placeholder="Field (e.g. age_days)"
                                                            className="flex-1 text-sm border-gray-300 rounded-md"
                                                            value={rule.field}
                                                            onChange={(e) => updateRule(idx, 'field', e.target.value)}
                                                        />
                                                        <select
                                                            className="w-24 text-sm border-gray-300 rounded-md"
                                                            value={rule.op}
                                                            onChange={(e) => updateRule(idx, 'op', e.target.value)}
                                                        >
                                                            <option value="gt">&gt;</option>
                                                            <option value="lt">&lt;</option>
                                                            <option value="eq">=</option>
                                                            <option value="exists">Exists</option>
                                                            <option value="missing">Missing</option>
                                                        </select>
                                                        <input
                                                            type="text"
                                                            placeholder="Value"
                                                            className="w-20 text-sm border-gray-300 rounded-md"
                                                            value={rule.value}
                                                            onChange={(e) => updateRule(idx, 'value', e.target.value)}
                                                        />
                                                        <button
                                                            type="button"
                                                            onClick={() => removeRule(idx)}
                                                            className="text-red-500 hover:text-red-700"
                                                        >
                                                            <FiX />
                                                        </button>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>

                                        <div className="flex items-center">
                                            <input
                                                type="checkbox"
                                                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                                                checked={formData.is_active}
                                                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                            />
                                            <label className="ml-2 block text-sm text-gray-900">
                                                Enable Policy
                                            </label>
                                        </div>
                                    </div>
                                </div>

                                <div className="bg-gray-50 px-4 py-3 sm:px-6 sm:flex sm:flex-row-reverse">
                                    <Button type="submit" variant="primary">
                                        Save Policy
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="white"
                                        className="mr-3"
                                        onClick={() => setShowModal(false)}
                                    >
                                        Cancel
                                    </Button>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default CleanupPolicies;
