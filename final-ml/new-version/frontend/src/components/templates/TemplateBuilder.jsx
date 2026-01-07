import React, { useState, useEffect } from 'react';
import { Card, Button, Input } from '../shared';
import { FiSave, FiX, FiCpu, FiHardDrive, FiActivity, FiTag, FiAlertCircle } from 'react-icons/fi';
import toast from 'react-hot-toast';

const TemplateBuilder = ({ template, onSave, onCancel }) => {
    const [activeTab, setActiveTab] = useState('compute');

    const [formData, setFormData] = useState({
        name: '',
        description: '',
        // Compute
        architecture: 'amd64',
        os: 'linux',
        instance_families: ['c5', 'm5', 'r5'],
        excluded_families: [],
        min_cpu: 2,
        min_memory: 4,
        // Storage
        root_volume_type: 'gp3',
        root_volume_size: 20,
        root_volume_iops: 3000,
        root_volume_throughput: 125,
        // Network
        security_groups: [],
        subnets: [],
        // Kubernetes
        taints: [],
        labels: {},
        user_data: ''
    });

    useEffect(() => {
        if (template) {
            setFormData({
                ...formData,
                ...template // Merge existing template data
            });
        }
    }, [template]);

    // Mock Data
    const families = ['t3', 'm5', 'c5', 'r5', 'g4dn', 'p3', 'i3', 'z1d'];

    const handleSave = (e) => {
        e.preventDefault();
        onSave(formData);
    };

    const addTaint = () => {
        setFormData({
            ...formData,
            taints: [...formData.taints, { key: '', value: '', effect: 'NoSchedule' }]
        });
    };

    const removeTaint = (index) => {
        const newTaints = [...formData.taints];
        newTaints.splice(index, 1);
        setFormData({ ...formData, taints: newTaints });
    };

    const updateTaint = (index, field, value) => {
        const newTaints = [...formData.taints];
        newTaints[index][field] = value;
        setFormData({ ...formData, taints: newTaints });
    };

    const tabs = [
        { id: 'compute', label: 'Compute', icon: FiCpu },
        { id: 'storage', label: 'Storage', icon: FiHardDrive },
        { id: 'network', label: 'Network', icon: FiActivity },
        { id: 'k8s', label: 'Kubernetes', icon: FiTag },
    ];

    return (
        <div className="flex flex-col h-full">
            <div className="flex justify-between items-center p-6 border-b">
                <h2 className="text-2xl font-bold text-gray-900">
                    {template ? 'Edit Template' : 'Create Template'}
                </h2>
                <button onClick={onCancel} className="text-gray-500 hover:text-gray-700">
                    <FiX className="w-6 h-6" />
                </button>
            </div>

            <div className="flex flex-1 overflow-hidden">
                {/* Sidebar */}
                <div className="w-64 bg-gray-50 border-r p-4 overflow-y-auto">
                    <div className="space-y-1">
                        {tabs.map(tab => (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`w-full flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors ${activeTab === tab.id ? 'bg-white text-blue-600 shadow-sm' : 'text-gray-600 hover:bg-gray-100'
                                    }`}
                            >
                                <tab.icon className="w-5 h-5 mr-3" />
                                {tab.label}
                            </button>
                        ))}
                    </div>

                    <div className="mt-8">
                        <div className="p-4 bg-blue-50 rounded-lg text-sm text-blue-800">
                            <div className="flex items-center mb-2 font-semibold">
                                <FiAlertCircle className="w-4 h-4 mr-2" />
                                Template Tips
                            </div>
                            <ul className="list-disc list-inside space-y-1 text-xs">
                                <li>Use broad families for better spot availability</li>
                                <li>Add taints to isolate workloads</li>
                                <li>GP3 is recommended for cost/performance</li>
                            </ul>
                        </div>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 p-8 overflow-y-auto">
                    <form id="template-form" onSubmit={handleSave} className="space-y-6 max-w-3xl">

                        {/* Common Info */}
                        <div className="grid grid-cols-2 gap-6">
                            <Input
                                label="Template Name"
                                value={formData.name}
                                onChange={e => setFormData({ ...formData, name: e.target.value })}
                                required
                            />
                            <Input
                                label="Description"
                                value={formData.description}
                                onChange={e => setFormData({ ...formData, description: e.target.value })}
                            />
                        </div>

                        {activeTab === 'compute' && (
                            <div className="space-y-6">
                                <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Compute Configuration</h3>

                                <div className="grid grid-cols-2 gap-6">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">Architecture</label>
                                        <select
                                            value={formData.architecture}
                                            onChange={e => setFormData({ ...formData, architecture: e.target.value })}
                                            className="w-full form-select rounded-lg border-gray-300"
                                        >
                                            <option value="amd64">AMD64 (x86_64)</option>
                                            <option value="arm64">ARM64 (Graviton)</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">OS</label>
                                        <select
                                            value={formData.os}
                                            onChange={e => setFormData({ ...formData, os: e.target.value })}
                                            className="w-full form-select rounded-lg border-gray-300"
                                        >
                                            <option value="linux">Linux</option>
                                            <option value="windows">Windows</option>
                                        </select>
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Allowed Families</label>
                                    <div className="grid grid-cols-4 gap-3">
                                        {families.map(fam => (
                                            <label key={fam} className="flex items-center space-x-2 p-2 border rounded hover:bg-gray-50 cursor-pointer">
                                                <input
                                                    type="checkbox"
                                                    checked={formData.instance_families.includes(fam)}
                                                    onChange={(e) => {
                                                        const newFamilies = e.target.checked
                                                            ? [...formData.instance_families, fam]
                                                            : formData.instance_families.filter(f => f !== fam);
                                                        setFormData({ ...formData, instance_families: newFamilies });
                                                    }}
                                                    className="rounded text-blue-600"
                                                />
                                                <span className="text-sm font-medium uppercase">{fam}</span>
                                            </label>
                                        ))}
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-6">
                                    <Input
                                        label="Min CPUs"
                                        type="number"
                                        value={formData.min_cpu}
                                        onChange={e => setFormData({ ...formData, min_cpu: parseInt(e.target.value) })}
                                    />
                                    <Input
                                        label="Min Memory (GB)"
                                        type="number"
                                        value={formData.min_memory}
                                        onChange={e => setFormData({ ...formData, min_memory: parseInt(e.target.value) })}
                                    />
                                </div>
                            </div>
                        )}

                        {activeTab === 'storage' && (
                            <div className="space-y-6">
                                <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Storage Configuration</h3>

                                <div className="grid grid-cols-2 gap-6">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-700 mb-1">Root Volume Type</label>
                                        <select
                                            value={formData.root_volume_type}
                                            onChange={e => setFormData({ ...formData, root_volume_type: e.target.value })}
                                            className="w-full form-select rounded-lg border-gray-300"
                                        >
                                            <option value="gp2">GP2 (General Purpose)</option>
                                            <option value="gp3">GP3 (General Purpose)</option>
                                            <option value="io1">IO1 (Provisioned IOPS)</option>
                                            <option value="io2">IO2 (Provisioned IOPS)</option>
                                        </select>
                                    </div>
                                    <Input
                                        label="Size (GB)"
                                        type="number"
                                        value={formData.root_volume_size}
                                        onChange={e => setFormData({ ...formData, root_volume_size: parseInt(e.target.value) })}
                                    />
                                </div>

                                {formData.root_volume_type === 'gp3' && (
                                    <div className="grid grid-cols-2 gap-6">
                                        <Input
                                            label="IOPS"
                                            type="number"
                                            value={formData.root_volume_iops}
                                            onChange={e => setFormData({ ...formData, root_volume_iops: parseInt(e.target.value) })}
                                        />
                                        <Input
                                            label="Throughput (MB/s)"
                                            type="number"
                                            value={formData.root_volume_throughput}
                                            onChange={e => setFormData({ ...formData, root_volume_throughput: parseInt(e.target.value) })}
                                        />
                                    </div>
                                )}
                            </div>
                        )}

                        {activeTab === 'network' && (
                            <div className="space-y-6">
                                <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Network Configuration</h3>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Security Groups (Comma separated IDs)</label>
                                    <textarea
                                        className="w-full form-textarea rounded-lg border-gray-300"
                                        rows="3"
                                        placeholder="sg-12345678, sg-87654321"
                                        value={formData.security_groups.join(', ')}
                                        onChange={e => setFormData({ ...formData, security_groups: e.target.value.split(',').map(s => s.trim()) })}
                                    ></textarea>
                                </div>
                            </div>
                        )}

                        {activeTab === 'k8s' && (
                            <div className="space-y-6">
                                <h3 className="text-lg font-medium text-gray-900 border-b pb-2">Kubernetes Settings</h3>

                                <div>
                                    <div className="flex justify-between items-center mb-2">
                                        <label className="block text-sm font-medium text-gray-700">Node Taints</label>
                                        <Button type="button" size="sm" variant="outline" onClick={addTaint}>Add Taint</Button>
                                    </div>
                                    <div className="space-y-2">
                                        {formData.taints.map((taint, idx) => (
                                            <div key={idx} className="flex gap-2">
                                                <input
                                                    placeholder="Key"
                                                    className="flex-1 form-input rounded border-gray-300 text-sm"
                                                    value={taint.key}
                                                    onChange={e => updateTaint(idx, 'key', e.target.value)}
                                                />
                                                <input
                                                    placeholder="Value"
                                                    className="flex-1 form-input rounded border-gray-300 text-sm"
                                                    value={taint.value}
                                                    onChange={e => updateTaint(idx, 'value', e.target.value)}
                                                />
                                                <select
                                                    className="form-select rounded border-gray-300 text-sm"
                                                    value={taint.effect}
                                                    onChange={e => updateTaint(idx, 'effect', e.target.value)}
                                                >
                                                    <option>NoSchedule</option>
                                                    <option>PreferNoSchedule</option>
                                                    <option>NoExecute</option>
                                                </select>
                                                <button type="button" onClick={() => removeTaint(idx)} className="text-red-500 hover:text-red-700 p-2">
                                                    <FiX />
                                                </button>
                                            </div>
                                        ))}
                                        {formData.taints.length === 0 && (
                                            <p className="text-sm text-gray-400 italic">No taints configured.</p>
                                        )}
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">User Data (Base64 or Plain Text)</label>
                                    <textarea
                                        className="w-full form-textarea rounded-lg border-gray-300 font-mono text-xs"
                                        rows="5"
                                        value={formData.user_data}
                                        onChange={e => setFormData({ ...formData, user_data: e.target.value })}
                                    ></textarea>
                                </div>
                            </div>
                        )}

                    </form>
                </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t bg-gray-50 flex justify-end gap-3">
                <Button variant="secondary" onClick={onCancel}>Cancel</Button>
                <Button variant="primary" icon={<FiSave />} onClick={handleSave}>Save Template</Button>
            </div>
        </div>
    );
};

export default TemplateBuilder;
