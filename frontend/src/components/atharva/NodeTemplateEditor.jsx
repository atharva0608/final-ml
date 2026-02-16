import React, { useState } from 'react';
import useAtharvaStore from '../../store/useAtharvaStore';
import { Card } from '../shared';
import {
    FiPlus, FiTrash2, FiEdit2, FiCopy, FiCheck, FiX,
    FiServer, FiCpu, FiHardDrive, FiGlobe, FiZap, FiChevronDown, FiChevronUp
} from 'react-icons/fi';

const NodeTemplateEditor = () => {
    const {
        nodeTemplates, selectedTemplate, selectTemplate,
        createNodeTemplate, updateNodeTemplate, deleteNodeTemplate
    } = useAtharvaStore();

    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState(null);
    const [expandedId, setExpandedId] = useState(null);

    // Form state
    const [formData, setFormData] = useState({
        name: '',
        description: '',
        rules: {
            cpu_architecture: ['x64'],
            vcpu_min: 1,
            vcpu_max: 16,
            memory_min_gib: 2,
            memory_max_gib: 64,
            instance_families_allowed: ['m5', 'm5a', 'm6i', 'c5', 'r5'],
            instance_families_blocked: [],
            instance_sizes_allowed: ['large', 'xlarge', '2xlarge'],
            instance_sizes_blocked: [],
            exclude_burstable: true,
            network_performance_min: 'moderate',
            storage_type_allowed: ['ebs_only'],
            availability_zones_allowed: ['all'],
            availability_zones_excluded: [],
            spot_only: true,
            max_interruption_rate: 0.25
        }
    });

    const resetForm = () => {
        setFormData({
            name: '', description: '',
            rules: {
                cpu_architecture: ['x64'], vcpu_min: 1, vcpu_max: 16,
                memory_min_gib: 2, memory_max_gib: 64,
                instance_families_allowed: ['m5', 'm5a', 'm6i', 'c5', 'r5'],
                instance_families_blocked: [], instance_sizes_allowed: ['large', 'xlarge', '2xlarge'],
                instance_sizes_blocked: [], exclude_burstable: true,
                network_performance_min: 'moderate', storage_type_allowed: ['ebs_only'],
                availability_zones_allowed: ['all'], availability_zones_excluded: [],
                spot_only: true, max_interruption_rate: 0.25
            }
        });
        setEditingId(null);
        setShowForm(false);
    };

    const handleCreate = () => {
        setEditingId(null);
        resetForm();
        setShowForm(true);
    };

    const handleEdit = (tmpl) => {
        setEditingId(tmpl.id);
        setFormData({ name: tmpl.name, description: tmpl.description, rules: { ...tmpl.rules } });
        setShowForm(true);
    };

    const handleClone = (tmpl) => {
        setEditingId(null);
        setFormData({ name: `${tmpl.name} (Copy)`, description: tmpl.description, rules: { ...tmpl.rules } });
        setShowForm(true);
    };

    const handleSubmit = async () => {
        if (!formData.name.trim()) return;
        if (editingId) {
            await updateNodeTemplate(editingId, formData);
        } else {
            await createNodeTemplate(formData);
        }
        resetForm();
    };

    const handleDelete = async (id) => {
        if (window.confirm('Delete this template?')) {
            await deleteNodeTemplate(id);
        }
    };

    const updateRules = (field, value) => {
        setFormData(prev => ({ ...prev, rules: { ...prev.rules, [field]: value } }));
    };

    const FAMILIES = ['m5', 'm5a', 'm5n', 'm6i', 'c5', 'c5a', 'r5', 't3'];
    const SIZES = ['large', 'xlarge', '2xlarge', '4xlarge', '8xlarge'];

    return (
        <Card className="border-gray-200 h-full">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <FiServer className="w-5 h-5 text-indigo-600" />
                    <h3 className="text-lg font-semibold text-gray-900">Node Templates</h3>
                </div>
                <button
                    onClick={handleCreate}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
                >
                    <FiPlus className="w-3.5 h-3.5" /> New
                </button>
            </div>

            {/* Template List */}
            <div className="space-y-2 mb-4">
                {nodeTemplates.map((tmpl) => (
                    <div
                        key={tmpl.id}
                        className={`border rounded-lg transition-all ${selectedTemplate?.id === tmpl.id
                                ? 'border-blue-500 bg-blue-50/50'
                                : 'border-gray-200 hover:border-gray-300'
                            }`}
                    >
                        <div
                            className="flex items-center justify-between p-3 cursor-pointer"
                            onClick={() => selectTemplate(tmpl)}
                        >
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    <p className="text-sm font-semibold text-gray-900 truncate">{tmpl.name}</p>
                                    {tmpl.active && (
                                        <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded font-medium">Active</span>
                                    )}
                                </div>
                                <p className="text-xs text-gray-500 mt-0.5 truncate">{tmpl.description}</p>
                            </div>

                            <div className="flex items-center gap-1 ml-2">
                                <button
                                    onClick={(e) => { e.stopPropagation(); setExpandedId(expandedId === tmpl.id ? null : tmpl.id); }}
                                    className="p-1 text-gray-400 hover:text-gray-600 rounded"
                                >
                                    {expandedId === tmpl.id ? <FiChevronUp className="w-3.5 h-3.5" /> : <FiChevronDown className="w-3.5 h-3.5" />}
                                </button>
                                <button onClick={(e) => { e.stopPropagation(); handleEdit(tmpl); }} className="p-1 text-gray-400 hover:text-blue-600 rounded"><FiEdit2 className="w-3.5 h-3.5" /></button>
                                <button onClick={(e) => { e.stopPropagation(); handleClone(tmpl); }} className="p-1 text-gray-400 hover:text-purple-600 rounded"><FiCopy className="w-3.5 h-3.5" /></button>
                                <button onClick={(e) => { e.stopPropagation(); handleDelete(tmpl.id); }} className="p-1 text-gray-400 hover:text-red-600 rounded"><FiTrash2 className="w-3.5 h-3.5" /></button>
                            </div>
                        </div>

                        {/* Expanded Details */}
                        {expandedId === tmpl.id && (
                            <div className="px-3 pb-3 text-xs text-gray-600 border-t border-gray-100 pt-2 space-y-1">
                                <div className="flex justify-between"><span>Architecture</span><span className="font-medium">{tmpl.rules?.cpu_architecture?.join(', ') || 'x64'}</span></div>
                                <div className="flex justify-between"><span>vCPU Range</span><span className="font-medium">{tmpl.rules?.vcpu_min || 1} – {tmpl.rules?.vcpu_max || 96}</span></div>
                                <div className="flex justify-between"><span>Memory (GiB)</span><span className="font-medium">{tmpl.rules?.memory_min_gib || 1} – {tmpl.rules?.memory_max_gib || 384}</span></div>
                                <div className="flex justify-between"><span>Families</span><span className="font-medium truncate max-w-[140px]">{tmpl.rules?.instance_families_allowed?.join(', ') || '—'}</span></div>
                                <div className="flex justify-between"><span>Max Interrupt Rate</span><span className="font-medium">{((tmpl.rules?.max_interruption_rate || 0.25) * 100).toFixed(0)}%</span></div>
                                <div className="flex justify-between"><span>Spot Only</span><span className="font-medium">{tmpl.rules?.spot_only ? 'Yes' : 'No'}</span></div>
                                {tmpl.applied_clusters?.length > 0 && (
                                    <div className="flex justify-between"><span>Applied to</span><span className="font-medium text-blue-600">{tmpl.applied_clusters.length} cluster(s)</span></div>
                                )}
                            </div>
                        )}
                    </div>
                ))}

                {nodeTemplates.length === 0 && !showForm && (
                    <div className="text-center py-6 text-gray-400 text-sm">
                        <FiServer className="w-6 h-6 mx-auto mb-2" />
                        No templates yet
                    </div>
                )}
            </div>

            {/* Create/Edit Form */}
            {showForm && (
                <div className="border border-blue-200 rounded-lg bg-blue-50/30 p-4 space-y-3">
                    <h4 className="text-sm font-semibold text-gray-900">{editingId ? 'Edit Template' : 'New Template'}</h4>

                    <input
                        type="text"
                        placeholder="Template name"
                        value={formData.name}
                        onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />
                    <input
                        type="text"
                        placeholder="Description"
                        value={formData.description}
                        onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    />

                    {/* Architecture */}
                    <div>
                        <label className="text-[10px] font-bold text-gray-500 uppercase block mb-1">Architecture</label>
                        <div className="flex gap-2">
                            {['x64', 'arm64'].map(arch => (
                                <button
                                    key={arch}
                                    onClick={() => {
                                        const cur = formData.rules.cpu_architecture;
                                        updateRules('cpu_architecture', cur.includes(arch) ? cur.filter(a => a !== arch) : [...cur, arch]);
                                    }}
                                    className={`px-3 py-1.5 text-xs rounded-lg border font-medium transition-colors ${formData.rules.cpu_architecture.includes(arch)
                                            ? 'bg-blue-600 text-white border-blue-700' : 'bg-white text-gray-600 border-gray-300 hover:bg-gray-50'
                                        }`}
                                >
                                    {arch}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* vCPU Range */}
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <label className="text-[10px] font-bold text-gray-500 uppercase block mb-1">Min vCPU</label>
                            <input type="number" value={formData.rules.vcpu_min} onChange={(e) => updateRules('vcpu_min', parseInt(e.target.value))}
                                min="1" max="96" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                        </div>
                        <div>
                            <label className="text-[10px] font-bold text-gray-500 uppercase block mb-1">Max vCPU</label>
                            <input type="number" value={formData.rules.vcpu_max} onChange={(e) => updateRules('vcpu_max', parseInt(e.target.value))}
                                min="1" max="96" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                        </div>
                    </div>

                    {/* Memory Range */}
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <label className="text-[10px] font-bold text-gray-500 uppercase block mb-1">Min Memory (GiB)</label>
                            <input type="number" value={formData.rules.memory_min_gib} onChange={(e) => updateRules('memory_min_gib', parseInt(e.target.value))}
                                min="1" max="384" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                        </div>
                        <div>
                            <label className="text-[10px] font-bold text-gray-500 uppercase block mb-1">Max Memory (GiB)</label>
                            <input type="number" value={formData.rules.memory_max_gib} onChange={(e) => updateRules('memory_max_gib', parseInt(e.target.value))}
                                min="1" max="384" className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
                        </div>
                    </div>

                    {/* Instance Families */}
                    <div>
                        <label className="text-[10px] font-bold text-gray-500 uppercase block mb-1">Instance Families</label>
                        <div className="flex flex-wrap gap-1">
                            {FAMILIES.map(fam => (
                                <button
                                    key={fam}
                                    onClick={() => {
                                        const cur = formData.rules.instance_families_allowed;
                                        updateRules('instance_families_allowed', cur.includes(fam) ? cur.filter(f => f !== fam) : [...cur, fam]);
                                    }}
                                    className={`px-2 py-1 text-[11px] rounded border font-medium transition-colors ${formData.rules.instance_families_allowed.includes(fam)
                                            ? 'bg-blue-600 text-white border-blue-700' : 'bg-white text-gray-600 border-gray-300'
                                        }`}
                                >
                                    {fam}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Instance Sizes */}
                    <div>
                        <label className="text-[10px] font-bold text-gray-500 uppercase block mb-1">Instance Sizes</label>
                        <div className="flex flex-wrap gap-1">
                            {SIZES.map(size => (
                                <button
                                    key={size}
                                    onClick={() => {
                                        const cur = formData.rules.instance_sizes_allowed;
                                        updateRules('instance_sizes_allowed', cur.includes(size) ? cur.filter(s => s !== size) : [...cur, size]);
                                    }}
                                    className={`px-2 py-1 text-[11px] rounded border font-medium transition-colors ${formData.rules.instance_sizes_allowed.includes(size)
                                            ? 'bg-blue-600 text-white border-blue-700' : 'bg-white text-gray-600 border-gray-300'
                                        }`}
                                >
                                    {size}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Max Interruption Rate */}
                    <div>
                        <label className="text-[10px] font-bold text-gray-500 uppercase block mb-1">
                            Max Interruption Rate: {(formData.rules.max_interruption_rate * 100).toFixed(0)}%
                        </label>
                        <input
                            type="range" min="0" max="100" step="5"
                            value={formData.rules.max_interruption_rate * 100}
                            onChange={(e) => updateRules('max_interruption_rate', parseInt(e.target.value) / 100)}
                            className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                        />
                    </div>

                    {/* Toggles */}
                    <div className="flex items-center gap-4">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.rules.spot_only}
                                onChange={(e) => updateRules('spot_only', e.target.checked)}
                                className="rounded border-gray-300 text-blue-600" />
                            <span className="text-xs text-gray-700">Spot Only</span>
                        </label>
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input type="checkbox" checked={formData.rules.exclude_burstable}
                                onChange={(e) => updateRules('exclude_burstable', e.target.checked)}
                                className="rounded border-gray-300 text-blue-600" />
                            <span className="text-xs text-gray-700">Exclude Burstable</span>
                        </label>
                    </div>

                    {/* Form Actions */}
                    <div className="flex gap-2 pt-1">
                        <button onClick={handleSubmit}
                            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-blue-600 text-white text-xs font-semibold rounded-lg hover:bg-blue-700 transition-colors">
                            <FiCheck className="w-3.5 h-3.5" /> {editingId ? 'Update' : 'Create'}
                        </button>
                        <button onClick={resetForm}
                            className="flex items-center justify-center gap-1.5 px-3 py-2 bg-gray-100 text-gray-600 text-xs font-medium rounded-lg hover:bg-gray-200 transition-colors">
                            <FiX className="w-3.5 h-3.5" /> Cancel
                        </button>
                    </div>
                </div>
            )}
        </Card>
    );
};

export default NodeTemplateEditor;
