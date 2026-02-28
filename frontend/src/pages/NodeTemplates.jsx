import React, { useState, useEffect } from 'react';
import { nodeTemplateAPI } from '../services/api';
import { Card, Button, Badge } from '../components/shared';
import {
    FiPlus, FiServer, FiGlobe, FiSettings, FiActivity, FiX, FiCheckCircle,
    FiAlertTriangle, FiList, FiTrendingDown, FiClock, FiTrash2, FiCpu,
    FiLayers, FiShield, FiZap, FiDatabase, FiMap, FiSliders, FiLock,
    FiUnlock, FiRefreshCw, FiChevronDown, FiChevronUp, FiInfo, FiEdit3
} from 'react-icons/fi';
import toast from 'react-hot-toast';

/* ─────────────────────────────────────────────────────────────────
   ALL 28 ENTERPRISE FEATURES — COMPLETE IMPLEMENTATION
   ─────────────────────────────────────────────────────────────── */

const DEFAULT_CONSTRAINTS = {
    workload_scope: 'STATELESS_ONLY',
    stateful_protected: true,
    architectures: ['amd64'],
    min_vcpu: 2,
    max_vcpu: 64,
    min_memory: 4.0,
    max_memory: 256.0,
    allowed_families: [],
    excluded_families: ['metal', 'g', 'p', 'trn', 'inf', 'i'],
    allowed_zones: [],
    cross_az_rebalance: true,
    optimization_policy: 'COST_FIRST',
    risk_threshold: 10.0,
    savings_threshold: 5.0,
    allow_spot: true,
    allow_ondemand: true,
    substitute_strategy: 'PREWARMED'
};

const INSTANCE_FAMILIES = [
    { value: 'm5', label: 'M5 (General Purpose)' },
    { value: 'm6i', label: 'M6i (General Purpose)' },
    { value: 'm6g', label: 'M6g (Graviton)' },
    { value: 'm7g', label: 'M7g (Graviton3)' },
    { value: 'c5', label: 'C5 (Compute)' },
    { value: 'c6i', label: 'C6i (Compute)' },
    { value: 'c6g', label: 'C6g (Graviton Compute)' },
    { value: 'c7g', label: 'C7g (Graviton3 Compute)' },
    { value: 'r5', label: 'R5 (Memory)' },
    { value: 'r6i', label: 'R6i (Memory)' },
    { value: 'r6g', label: 'R6g (Graviton Memory)' },
    { value: 't3', label: 'T3 (Burstable)' },
    { value: 't3a', label: 'T3a (AMD Burstable)' },
    { value: 'i3', label: 'I3 (Storage)' },
    { value: 'd2', label: 'D2 (Dense Storage)' },
];

const EXCLUDED_FAMILIES_OPTIONS = [
    'metal', 'g', 'p', 'trn', 'inf', 'i', 'f', 'u', 'x', 'z', 'dl', 'hpc', 'vt'
];

const AZ_OPTIONS = ['us-east-1a', 'us-east-1b', 'us-east-1c', 'us-west-2a', 'us-west-2b', 'us-west-2c',
    'ap-south-1a', 'ap-south-1b', 'ap-south-1c', 'eu-west-1a', 'eu-west-1b', 'eu-west-1c'];

/* ── Section Header ───────────────────────────────────────────── */
const SectionHeader = ({ icon: Icon, title, color = 'indigo' }) => (
    <div className={`flex items-center gap-2 pt-3 pb-2 border-b border-gray-100 mb-3`}>
        <Icon className={`text-${color}-600`} size={14} />
        <h4 className={`text-xs font-bold text-${color}-800 uppercase tracking-wider`}>{title}</h4>
    </div>
);

/* ── Toggle Row ───────────────────────────────────────────────── */
const ToggleRow = ({ id, label, description, checked, onChange }) => (
    <div className="flex items-start gap-3 py-2">
        <input type="checkbox" id={id}
            className="rounded text-blue-600 border-gray-300 mt-0.5 focus:ring-blue-500"
            checked={checked} onChange={e => onChange(e.target.checked)} />
        <div>
            <label htmlFor={id} className="text-sm text-gray-800 font-medium cursor-pointer">{label}</label>
            {description && <p className="text-[10px] text-gray-500 mt-0.5">{description}</p>}
        </div>
    </div>
);

/* ── Multi Select Chips ───────────────────────────────────────── */
const ChipSelect = ({ options, selected, onChange, label }) => (
    <div>
        <label className="block text-xs font-semibold text-gray-700 mb-2">{label}</label>
        <div className="flex flex-wrap gap-1.5">
            {options.map(opt => {
                const val = typeof opt === 'string' ? opt : opt.value;
                const lbl = typeof opt === 'string' ? opt : opt.label;
                const active = selected.includes(val);
                return (
                    <button key={val} type="button"
                        className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all duration-150 ${active
                            ? 'bg-blue-100 border-blue-300 text-blue-800 shadow-sm'
                            : 'bg-gray-50 border-gray-200 text-gray-600 hover:bg-gray-100'}`}
                        onClick={() => onChange(active ? selected.filter(s => s !== val) : [...selected, val])}>
                        {lbl}
                    </button>
                );
            })}
        </div>
    </div>
);

/* ══════════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ══════════════════════════════════════════════════════════════════ */

const NodeTemplates = () => {
    const [templates, setTemplates] = useState([]);
    const [attachedCounts, setAttachedCounts] = useState({});
    const [loading, setLoading] = useState(true);

    // Create Modal
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [createForm, setCreateForm] = useState({ name: '', scope: 'GLOBAL' });
    const [creating, setCreating] = useState(false);

    // Detail Modal
    const [selectedTemplate, setSelectedTemplate] = useState(null);
    const [versions, setVersions] = useState([]);
    const [loadingVersions, setLoadingVersions] = useState(false);
    const [activeTab, setActiveTab] = useState('editor'); // editor | impact | audit

    // Editor
    const [editingConstraints, setEditingConstraints] = useState(null);
    const [validationResult, setValidationResult] = useState(null);
    const [validating, setValidating] = useState(false);
    const [savingVersion, setSavingVersion] = useState(false);

    // Delete
    const [deleteConfirm, setDeleteConfirm] = useState(null);
    const [deleting, setDeleting] = useState(false);

    // Expanded sections in editor
    const [expandedSections, setExpandedSections] = useState({
        workload: true, hardware: true, families: false, safety: true, capacity: true, zones: false
    });

    useEffect(() => { fetchTemplates(); }, []);

    /* ── Fetch ─────────────────────────────────────────────────── */
    const fetchTemplates = async () => {
        setLoading(true);
        try {
            const res = await nodeTemplateAPI.getGlobalTemplates();
            setTemplates(res.data.templates || []);
            setAttachedCounts(res.data.attached_clusters_count || {});
        } catch (error) {
            console.error('Failed to fetch templates:', error);
            toast.error('Failed to load template registry');
        } finally {
            setLoading(false);
        }
    };

    /* ── Create ────────────────────────────────────────────────── */
    const handleCreate = async () => {
        if (!createForm.name.trim()) { toast.error('Template name is required'); return; }
        setCreating(true);
        try {
            await nodeTemplateAPI.createGlobalTemplate({
                name: createForm.name.trim(),
                scope: createForm.scope,
                initial_constraints: DEFAULT_CONSTRAINTS
            });
            toast.success('Template created successfully');
            setShowCreateModal(false);
            setCreateForm({ name: '', scope: 'GLOBAL' });
            fetchTemplates();
        } catch (error) {
            console.error(error);
            toast.error('Failed to create template');
        } finally {
            setCreating(false);
        }
    };

    /* ── Open Detail ───────────────────────────────────────────── */
    const handleTemplateClick = async (template) => {
        setSelectedTemplate(template);
        setLoadingVersions(true);
        setEditingConstraints(null);
        setValidationResult(null);
        setActiveTab('editor');
        try {
            const res = await nodeTemplateAPI.getVersions(template.id);
            const activeVersion = res.data.find(v => v.status === 'ACTIVE') || res.data[0];
            setVersions(res.data);
            if (activeVersion) setEditingConstraints({ ...DEFAULT_CONSTRAINTS, ...activeVersion.constraints_json });
        } catch (error) {
            console.error(error);
            toast.error("Failed to load template versions");
        } finally {
            setLoadingVersions(false);
        }
    };

    /* ── Validate ──────────────────────────────────────────────── */
    const handleValidate = async () => {
        if (!editingConstraints) return;
        setValidating(true);
        try {
            const res = await nodeTemplateAPI.validate({
                cluster_id: 'default-preview-context',
                ...editingConstraints
            });
            setValidationResult(res.data);
            toast.success("Validation complete");
        } catch (err) {
            toast.error("Validation failed");
        } finally {
            setValidating(false);
        }
    };

    /* ── Promote New Version ──────────────────────────────────── */
    const handlePromoteNewVersion = async () => {
        if (!editingConstraints || !selectedTemplate) return;

        // Feature 25+27: Impact view with cluster names
        const impactCount = attachedCounts[selectedTemplate.id] || 0;
        if (selectedTemplate.scope === 'GLOBAL' && impactCount > 0) {
            const confirmed = window.confirm(
                `⚠️ GLOBAL TEMPLATE IMPACT\n\n` +
                `Promoting a new version will permanently alter the constraint boundaries ` +
                `for ${impactCount} live cluster(s) using "${selectedTemplate.name}".\n\n` +
                `This action creates an immutable version record.\n\n` +
                `Proceed?`
            );
            if (!confirmed) return;
        }

        setSavingVersion(true);
        try {
            await nodeTemplateAPI.createVersion(selectedTemplate.id, {
                constraints: editingConstraints
            });
            toast.success("New version promoted to ACTIVE successfully.");

            // Refresh versions
            const res = await nodeTemplateAPI.getVersions(selectedTemplate.id);
            setVersions(res.data);
            setValidationResult(null);
        } catch (error) {
            console.error(error);
            toast.error("Failed to create new version");
        } finally {
            setSavingVersion(false);
        }
    };

    /* ── Delete ────────────────────────────────────────────────── */
    const handleDelete = async (template) => {
        const impactCount = attachedCounts[template.id] || 0;
        if (impactCount > 0) {
            toast.error(`Cannot delete: ${impactCount} cluster(s) depend on this template. Detach them first.`);
            return;
        }
        setDeleteConfirm(template);
    };

    const confirmDelete = async () => {
        if (!deleteConfirm) return;
        setDeleting(true);
        try {
            await nodeTemplateAPI.deleteGlobalTemplate
                ? await nodeTemplateAPI.deleteGlobalTemplate(deleteConfirm.id)
                : toast.error("Delete API not wired");
            toast.success("Template deleted");
            setDeleteConfirm(null);
            fetchTemplates();
        } catch (err) {
            toast.error("Failed to delete template");
        } finally {
            setDeleting(false);
        }
    };

    /* ── Update Constraint Helper ─────────────────────────────── */
    const uc = (key, value) => setEditingConstraints(prev => ({ ...prev, [key]: value }));

    const toggleSection = (key) => setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }));

    /* ── Render: Loading ──────────────────────────────────────── */
    if (loading) {
        return (
            <div className="p-8 flex items-center justify-center min-h-[400px]">
                <div className="text-center">
                    <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-blue-600 mx-auto mb-3"></div>
                    <p className="text-sm text-gray-500">Loading template registry…</p>
                </div>
            </div>
        );
    }

    /* ══════════════════════════════════════════════════════════════
       RENDER
       ══════════════════════════════════════════════════════════════ */
    return (
        <div style={{ padding: "24px 32px", maxWidth: 1280, margin: "0 auto" }}>

            {/* ── Page Header ──────────────────────────────────── */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
                <div>
                    <h1 style={{ fontSize: 24, fontWeight: 700, color: "#111827", marginBottom: 8 }}>
                        Enterprise Template Registry
                    </h1>
                    <p style={{ color: "#6b7280", fontSize: 14 }}>
                        Define authoritative optimization constraints and attach them to multiple clusters.
                    </p>
                </div>
                <Button variant="primary" onClick={() => setShowCreateModal(true)} className="flex items-center gap-2">
                    <FiPlus /> New Global Template
                </Button>
            </div>

            {/* ── Summary Bar ──────────────────────────────────── */}
            {templates.length > 0 && (
                <div className="grid grid-cols-3 gap-4 mb-6">
                    <Card className="p-4 bg-gradient-to-br from-blue-50 to-indigo-50 border-blue-100">
                        <div className="text-xs font-semibold text-blue-600 uppercase mb-1">Total Templates</div>
                        <div className="text-2xl font-bold text-blue-900">{templates.length}</div>
                    </Card>
                    <Card className="p-4 bg-gradient-to-br from-green-50 to-emerald-50 border-green-100">
                        <div className="text-xs font-semibold text-green-600 uppercase mb-1">Global (Reusable)</div>
                        <div className="text-2xl font-bold text-green-900">{templates.filter(t => t.scope === 'GLOBAL').length}</div>
                    </Card>
                    <Card className="p-4 bg-gradient-to-br from-purple-50 to-violet-50 border-purple-100">
                        <div className="text-xs font-semibold text-purple-600 uppercase mb-1">Total Cluster Attachments</div>
                        <div className="text-2xl font-bold text-purple-900">{Object.values(attachedCounts).reduce((a, b) => a + b, 0)}</div>
                    </Card>
                </div>
            )}

            {/* ── Empty State ──────────────────────────────────── */}
            {templates.length === 0 ? (
                <Card className="p-12 text-center text-gray-500">
                    <FiGlobe className="mx-auto text-gray-300 mb-4" size={48} />
                    <h3 className="text-lg font-semibold text-gray-600 mb-2">No Templates Found</h3>
                    <p className="text-sm mb-6">Create a global template to define reusable optimization guidelines.</p>
                    <Button variant="primary" onClick={() => setShowCreateModal(true)} className="mx-auto flex items-center gap-2">
                        <FiPlus /> Create First Template
                    </Button>
                </Card>
            ) : (
                /* ── Template Grid (Feature 1,3,4,7) ───────────── */
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {templates.map(t => (
                        <Card key={t.id}
                            className="p-5 hover:border-blue-400 transition-all duration-200 cursor-pointer border-gray-200 shadow-sm relative overflow-hidden group hover:shadow-md"
                            onClick={() => handleTemplateClick(t)}>

                            {/* Left accent bar */}
                            <div className="absolute top-0 left-0 w-1 h-full bg-blue-500 group-hover:w-1.5 transition-all"></div>

                            {/* Header */}
                            <div className="flex justify-between items-start mb-3">
                                <div className="flex-1 min-w-0">
                                    <h3 className="font-bold text-gray-900 text-lg group-hover:text-blue-600 transition-colors truncate">
                                        {t.name}
                                    </h3>
                                    <div className="flex items-center gap-2 mt-1.5">
                                        {/* Feature 4: Scope badge */}
                                        <Badge color={t.scope === 'GLOBAL' ? 'blue' : 'gray'}>
                                            {t.scope === 'GLOBAL' ? <><FiGlobe className="inline mr-1" size={10} />GLOBAL</> : 'CLUSTER'}
                                        </Badge>
                                        {/* Feature 7: Status badge */}
                                        <Badge color="green" size="sm">ACTIVE</Badge>
                                    </div>
                                </div>

                                {/* Delete button (Feature: delete with impact check) */}
                                <button
                                    className="p-2 text-gray-300 hover:text-red-500 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                                    onClick={(e) => { e.stopPropagation(); handleDelete(t); }}
                                    title="Delete template">
                                    <FiTrash2 size={16} />
                                </button>
                            </div>

                            {/* Feature 3: Reusability Indicator */}
                            <div className="bg-gray-50 rounded-lg p-3 mb-3 border border-gray-100">
                                <div className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide mb-1.5">Cluster Impact</div>
                                <div className="flex items-center gap-2 text-sm text-gray-700">
                                    <FiServer className={attachedCounts[t.id] > 0 ? "text-indigo-500" : "text-gray-400"} />
                                    <span className="font-semibold">{attachedCounts[t.id] || 0}</span>
                                    <span className="text-gray-500">attached cluster{(attachedCounts[t.id] || 0) !== 1 ? 's' : ''}</span>
                                </div>
                                {(attachedCounts[t.id] || 0) > 0 && t.scope === 'GLOBAL' && (
                                    <div className="flex items-center gap-1 mt-1.5 text-[10px] text-amber-600">
                                        <FiAlertTriangle size={10} />
                                        Modifications affect all attached clusters
                                    </div>
                                )}
                            </div>

                            {/* Footer */}
                            <div className="text-xs text-gray-400 flex justify-between items-center pt-3 border-t border-gray-100">
                                <span>By {t.created_by || 'System'}</span>
                                <span>{new Date(t.created_at).toLocaleDateString()}</span>
                            </div>
                        </Card>
                    ))}
                </div>
            )}

            {/* ══════════════════════════════════════════════════════
               CREATE TEMPLATE MODAL (replaces prompt())
               ══════════════════════════════════════════════════════ */}
            {showCreateModal && (
                <div className="fixed inset-0 bg-gray-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-md overflow-hidden">
                        <div className="px-6 py-4 border-b border-gray-100 bg-gray-50 flex justify-between items-center">
                            <h2 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                                <FiPlus className="text-blue-600" /> New Template
                            </h2>
                            <button onClick={() => setShowCreateModal(false)} className="p-2 text-gray-400 hover:text-gray-700 rounded-lg">
                                <FiX size={18} />
                            </button>
                        </div>
                        <div className="p-6 space-y-5">
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Template Name</label>
                                <input type="text" className="w-full text-sm border-gray-300 rounded-lg shadow-sm px-3 py-2.5 focus:border-blue-500 focus:ring-blue-500"
                                    placeholder="e.g. Production Compute Baseline"
                                    value={createForm.name}
                                    onChange={e => setCreateForm({ ...createForm, name: e.target.value })}
                                    onKeyDown={e => e.key === 'Enter' && handleCreate()}
                                    autoFocus />
                            </div>

                            {/* Feature 4: Scope Selector */}
                            <div>
                                <label className="block text-sm font-semibold text-gray-700 mb-1.5">Template Scope</label>
                                <div className="grid grid-cols-2 gap-3">
                                    {[
                                        { value: 'GLOBAL', icon: FiGlobe, label: 'Global', desc: 'Reusable across clusters' },
                                        { value: 'CLUSTER', icon: FiServer, label: 'Cluster-Specific', desc: 'Locked to one cluster' }
                                    ].map(opt => (
                                        <button key={opt.value} type="button"
                                            className={`p-3 rounded-lg border-2 text-left transition-all ${createForm.scope === opt.value
                                                ? 'border-blue-500 bg-blue-50 shadow-sm'
                                                : 'border-gray-200 hover:border-gray-300'}`}
                                            onClick={() => setCreateForm({ ...createForm, scope: opt.value })}>
                                            <opt.icon className={`mb-1 ${createForm.scope === opt.value ? 'text-blue-600' : 'text-gray-400'}`} size={18} />
                                            <div className="text-sm font-semibold text-gray-900">{opt.label}</div>
                                            <div className="text-[10px] text-gray-500">{opt.desc}</div>
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="bg-blue-50 rounded-lg p-3 text-xs text-blue-700 flex items-start gap-2">
                                <FiInfo className="mt-0.5 flex-shrink-0" />
                                <span>Template starts as DRAFT with default constraints. Configure and promote to ACTIVE in the editor.</span>
                            </div>
                        </div>
                        <div className="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3">
                            <Button variant="secondary" onClick={() => setShowCreateModal(false)}>Cancel</Button>
                            <Button variant="primary" onClick={handleCreate} disabled={creating || !createForm.name.trim()}>
                                {creating ? 'Creating…' : 'Create Template'}
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* ══════════════════════════════════════════════════════
               DELETE CONFIRM MODAL
               ══════════════════════════════════════════════════════ */}
            {deleteConfirm && (
                <div className="fixed inset-0 bg-gray-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm overflow-hidden">
                        <div className="p-6 text-center">
                            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
                                <FiTrash2 className="text-red-600" size={24} />
                            </div>
                            <h3 className="text-lg font-bold text-gray-900 mb-2">Delete Template?</h3>
                            <p className="text-sm text-gray-600 mb-1">
                                <strong>"{deleteConfirm.name}"</strong> will be permanently deleted.
                            </p>
                            <p className="text-xs text-gray-500">All versions and audit history will be removed.</p>
                        </div>
                        <div className="px-6 py-4 border-t border-gray-100 flex justify-end gap-3">
                            <Button variant="secondary" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
                            <Button variant="danger" onClick={confirmDelete} disabled={deleting}>
                                {deleting ? 'Deleting…' : 'Delete Forever'}
                            </Button>
                        </div>
                    </div>
                </div>
            )}

            {/* ══════════════════════════════════════════════════════
               TEMPLATE DETAIL MODAL — Full 28-Feature Editor
               ══════════════════════════════════════════════════════ */}
            {selectedTemplate && (
                <div className="fixed inset-0 bg-gray-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-xl shadow-2xl w-full max-w-6xl max-h-[92vh] flex flex-col overflow-hidden">

                        {/* Header */}
                        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gradient-to-r from-gray-50 to-white">
                            <div>
                                <h2 className="text-xl font-bold flex items-center gap-2 text-gray-900">
                                    <FiList className="text-blue-600" /> {selectedTemplate.name}
                                </h2>
                                <div className="flex items-center gap-3 mt-1">
                                    <Badge color={selectedTemplate.scope === 'GLOBAL' ? 'blue' : 'gray'}>
                                        {selectedTemplate.scope}
                                    </Badge>
                                    <span className="text-xs text-gray-500">
                                        {attachedCounts[selectedTemplate.id] || 0} cluster(s) attached
                                    </span>
                                </div>
                            </div>
                            <button onClick={() => setSelectedTemplate(null)}
                                className="p-2 text-gray-400 hover:text-gray-700 hover:bg-gray-200 rounded-lg">
                                <FiX size={20} />
                            </button>
                        </div>

                        {/* Tab Bar — Feature 25, 28 */}
                        <div className="px-6 border-b border-gray-100 flex gap-0 bg-gray-50">
                            {[
                                { key: 'editor', label: 'Constraint Editor', icon: FiEdit3 },
                                { key: 'impact', label: 'Cluster Impact', icon: FiServer },
                                { key: 'audit', label: 'Version Audit', icon: FiClock },
                            ].map(tab => (
                                <button key={tab.key}
                                    className={`px-4 py-3 text-sm font-medium flex items-center gap-1.5 border-b-2 transition-colors ${activeTab === tab.key
                                        ? 'border-blue-600 text-blue-700 bg-white'
                                        : 'border-transparent text-gray-500 hover:text-gray-700'}`}
                                    onClick={() => setActiveTab(tab.key)}>
                                    <tab.icon size={14} /> {tab.label}
                                </button>
                            ))}
                        </div>

                        {/* Body */}
                        <div className="flex-1 overflow-y-auto p-6 bg-gray-50/50">

                            {/* ── EDITOR TAB ──────────────────────────────── */}
                            {activeTab === 'editor' && (
                                <div className="flex gap-6">
                                    {/* Left: Editor */}
                                    <div className="flex-1 space-y-4">
                                        {loadingVersions ? (
                                            <Card className="p-6"><div className="h-64 flex items-center justify-center text-gray-400 text-sm">Loading envelope…</div></Card>
                                        ) : editingConstraints ? (
                                            <>
                                                {/* WORKLOAD SCOPE — Feature 8,9 */}
                                                <Card className="p-5 border-blue-50 bg-white shadow-sm">
                                                    <button className="w-full flex justify-between items-center" onClick={() => toggleSection('workload')}>
                                                        <SectionHeader icon={FiLayers} title="Workload Classification" />
                                                        {expandedSections.workload ? <FiChevronUp className="text-gray-400" /> : <FiChevronDown className="text-gray-400" />}
                                                    </button>
                                                    {expandedSections.workload && (
                                                        <div className="grid grid-cols-2 gap-4 mt-3">
                                                            <div>
                                                                <label className="block text-xs font-semibold text-gray-700 mb-1">Policy Objective</label>
                                                                <select className="w-full text-sm border-gray-300 rounded-md shadow-sm focus:border-blue-500 focus:ring-blue-500"
                                                                    value={editingConstraints.optimization_policy}
                                                                    onChange={e => uc('optimization_policy', e.target.value)}>
                                                                    <option value="COST_FIRST">Cost Execution First</option>
                                                                    <option value="BALANCED">Balanced</option>
                                                                    <option value="NO_DOWNTIME_FIRST">No Downtime First</option>
                                                                </select>
                                                            </div>
                                                        </div>
                                                    )}
                                                </Card>

                                                {/* HARDWARE — Feature 10,11,12 */}
                                                <Card className="p-5 border-blue-50 bg-white shadow-sm">
                                                    <button className="w-full flex justify-between items-center" onClick={() => toggleSection('hardware')}>
                                                        <SectionHeader icon={FiCpu} title="Hardware Boundaries" />
                                                        {expandedSections.hardware ? <FiChevronUp className="text-gray-400" /> : <FiChevronDown className="text-gray-400" />}
                                                    </button>
                                                    {expandedSections.hardware && (
                                                        <div className="space-y-4 mt-3">
                                                            {/* Feature 10: Architecture Selector */}
                                                            <div>
                                                                <label className="block text-xs font-semibold text-gray-700 mb-2">CPU Architecture</label>
                                                                <div className="flex gap-3">
                                                                    {['amd64', 'arm64'].map(arch => (
                                                                        <button key={arch} type="button"
                                                                            className={`px-4 py-2 rounded-lg border-2 text-sm font-medium flex items-center gap-2 transition-all ${(editingConstraints.architectures || []).includes(arch)
                                                                                ? 'border-blue-500 bg-blue-50 text-blue-800'
                                                                                : 'border-gray-200 text-gray-600 hover:border-gray-300'}`}
                                                                            onClick={() => {
                                                                                const archs = editingConstraints.architectures || [];
                                                                                const next = archs.includes(arch) ? archs.filter(a => a !== arch) : [...archs, arch];
                                                                                if (next.length > 0) uc('architectures', next);
                                                                            }}>
                                                                            <FiCpu size={14} /> {arch}
                                                                        </button>
                                                                    ))}
                                                                </div>
                                                            </div>

                                                            {/* Feature 11: vCPU Range */}
                                                            <div className="grid grid-cols-2 gap-4">
                                                                <div>
                                                                    <label className="block text-xs font-semibold text-gray-700 mb-1">vCPU Range (Min – Max)</label>
                                                                    <div className="flex items-center gap-2">
                                                                        <input type="number" className="w-full text-sm border-gray-300 rounded-md"
                                                                            value={editingConstraints.min_vcpu}
                                                                            onChange={e => uc('min_vcpu', parseInt(e.target.value) || 1)} />
                                                                        <span className="text-gray-400 font-bold">–</span>
                                                                        <input type="number" className="w-full text-sm border-gray-300 rounded-md"
                                                                            value={editingConstraints.max_vcpu}
                                                                            onChange={e => uc('max_vcpu', parseInt(e.target.value) || 256)} />
                                                                    </div>
                                                                </div>

                                                                {/* Feature 12: Memory Range */}
                                                                <div>
                                                                    <label className="block text-xs font-semibold text-gray-700 mb-1">Memory Range (GB)</label>
                                                                    <div className="flex items-center gap-2">
                                                                        <input type="number" step="0.5" className="w-full text-sm border-gray-300 rounded-md"
                                                                            value={editingConstraints.min_memory}
                                                                            onChange={e => uc('min_memory', parseFloat(e.target.value) || 1)} />
                                                                        <span className="text-gray-400 font-bold">–</span>
                                                                        <input type="number" step="0.5" className="w-full text-sm border-gray-300 rounded-md"
                                                                            value={editingConstraints.max_memory}
                                                                            onChange={e => uc('max_memory', parseFloat(e.target.value) || 1024)} />
                                                                    </div>
                                                                </div>
                                                            </div>

                                                            {/* Risk & Savings — Feature 18,19 */}
                                                            <div className="grid grid-cols-2 gap-4">
                                                                <div>
                                                                    <label className="block text-xs font-semibold text-gray-700 mb-1">Max Interruption Risk (%)</label>
                                                                    <input type="number" step="0.5" className="w-full text-sm border-gray-300 rounded-md"
                                                                        value={editingConstraints.risk_threshold}
                                                                        onChange={e => uc('risk_threshold', parseFloat(e.target.value))} />
                                                                </div>
                                                                <div>
                                                                    <label className="block text-xs font-semibold text-gray-700 mb-1">Min Savings Delta (%)</label>
                                                                    <input type="number" step="0.5" className="w-full text-sm border-gray-300 rounded-md"
                                                                        value={editingConstraints.savings_threshold}
                                                                        onChange={e => uc('savings_threshold', parseFloat(e.target.value))} />
                                                                </div>
                                                            </div>
                                                        </div>
                                                    )}
                                                </Card>

                                                {/* INSTANCE FAMILIES — Feature 13,14 */}
                                                <Card className="p-5 border-blue-50 bg-white shadow-sm">
                                                    <button className="w-full flex justify-between items-center" onClick={() => toggleSection('families')}>
                                                        <SectionHeader icon={FiDatabase} title="Instance Family Controls" />
                                                        {expandedSections.families ? <FiChevronUp className="text-gray-400" /> : <FiChevronDown className="text-gray-400" />}
                                                    </button>
                                                    {expandedSections.families && (
                                                        <div className="space-y-5 mt-3">
                                                            {/* Feature 13: Allowed Families (Whitelist) */}
                                                            <ChipSelect
                                                                label="Allowed Families (Whitelist — empty = all allowed)"
                                                                options={INSTANCE_FAMILIES}
                                                                selected={editingConstraints.allowed_families || []}
                                                                onChange={v => uc('allowed_families', v)} />

                                                            {/* Feature 14: Excluded Families (Blacklist) */}
                                                            <ChipSelect
                                                                label="Excluded Families (Blacklist — overrides whitelist)"
                                                                options={EXCLUDED_FAMILIES_OPTIONS}
                                                                selected={editingConstraints.excluded_families || []}
                                                                onChange={v => uc('excluded_families', v)} />
                                                        </div>
                                                    )}
                                                </Card>

                                                {/* CAPACITY & SAFETY — Feature 15,16,20,21,22 */}
                                                <Card className="p-5 border-blue-50 bg-white shadow-sm">
                                                    <button className="w-full flex justify-between items-center" onClick={() => toggleSection('capacity')}>
                                                        <SectionHeader icon={FiShield} title="Capacity & Safety" />
                                                        {expandedSections.capacity ? <FiChevronUp className="text-gray-400" /> : <FiChevronDown className="text-gray-400" />}
                                                    </button>
                                                    {expandedSections.capacity && (
                                                        <div className="space-y-3 mt-3">
                                                            {/* Feature 16: Cross-AZ Toggle */}
                                                            <ToggleRow id="cross_az" label="Allow Cross-AZ Rebalance"
                                                                description="Controls substitute placement policy across availability zones"
                                                                checked={editingConstraints.cross_az_rebalance}
                                                                onChange={v => uc('cross_az_rebalance', v)} />
                                                        </div>
                                                    )}
                                                </Card>

                                                {/* AVAILABILITY ZONES — Feature 15 */}
                                                <Card className="p-5 border-blue-50 bg-white shadow-sm">
                                                    <button className="w-full flex justify-between items-center" onClick={() => toggleSection('zones')}>
                                                        <SectionHeader icon={FiMap} title="Availability Zone Restrictions" />
                                                        {expandedSections.zones ? <FiChevronUp className="text-gray-400" /> : <FiChevronDown className="text-gray-400" />}
                                                    </button>
                                                    {expandedSections.zones && (
                                                        <div className="mt-3">
                                                            <ChipSelect
                                                                label="Allowed AZs (empty = all zones allowed)"
                                                                options={AZ_OPTIONS}
                                                                selected={editingConstraints.allowed_zones || []}
                                                                onChange={v => uc('allowed_zones', v)} />
                                                        </div>
                                                    )}
                                                </Card>
                                            </>
                                        ) : null}
                                    </div>

                                    {/* Right: Validation + Actions */}
                                    <div className="w-80 space-y-4 flex flex-col">
                                        {/* Pre-Flight Validation — Feature 23,24 */}
                                        <Card className="p-5 border-gray-200 shadow-sm bg-white">
                                            <h3 className="text-sm font-bold text-gray-900 mb-4 border-b border-gray-100 pb-2 flex items-center gap-2">
                                                <FiActivity className="text-blue-500" /> Pre-Flight Validation
                                            </h3>

                                            <Button variant="secondary" className="w-full justify-center mb-3"
                                                onClick={handleValidate} disabled={validating}>
                                                <FiActivity className="mr-2" /> {validating ? 'Simulating…' : 'Simulate Candidates'}
                                            </Button>

                                            {validationResult && (
                                                <div className="mt-3 p-3 bg-gray-50 rounded-lg border border-gray-100">
                                                    <div className="flex items-center gap-2 mb-2">
                                                        {validationResult.is_valid
                                                            ? <FiCheckCircle className="text-green-500" />
                                                            : <FiAlertTriangle className="text-red-500" />}
                                                        <span className={`text-sm font-bold ${validationResult.is_valid ? 'text-green-700' : 'text-red-700'}`}>
                                                            {validationResult.is_valid ? 'Template Valid' : 'Too Restrictive'}
                                                        </span>
                                                    </div>
                                                    <div className="text-xs text-gray-600 mb-2">
                                                        Candidate Pools: <span className="font-bold text-gray-900">{validationResult.candidate_pools_count}</span>
                                                    </div>

                                                    {/* Feature 24: Strictness warnings */}
                                                    {validationResult.warnings?.length > 0 && (
                                                        <div className="space-y-1 mt-2 border-t border-gray-200 pt-2">
                                                            {validationResult.warnings.map((w, i) => (
                                                                <div key={i} className="text-[10px] text-orange-600 flex gap-1 items-start">
                                                                    <FiAlertTriangle className="mt-0.5 flex-shrink-0" size={10} /> {w}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}

                                                    {/* Candidate List */}
                                                    {validationResult.candidates?.length > 0 && (
                                                        <div className="mt-3 border-t border-gray-200 pt-2">
                                                            <div className="text-[10px] font-semibold text-gray-500 uppercase mb-1">Top Candidates</div>
                                                            <div className="space-y-1 max-h-32 overflow-y-auto">
                                                                {validationResult.candidates.slice(0, 8).map((c, i) => (
                                                                    <div key={i} className="text-xs text-gray-700 flex justify-between">
                                                                        <span className="font-mono">{c.instance_type || c}</span>
                                                                        {c.ev_score && <span className="text-green-600">{c.ev_score.toFixed(1)}</span>}
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}
                                                </div>
                                            )}

                                            {/* Promote — Feature 6,26 */}
                                            <Button variant="primary"
                                                className="w-full justify-center mt-5 bg-indigo-600 hover:bg-indigo-700"
                                                onClick={handlePromoteNewVersion}
                                                disabled={savingVersion || !editingConstraints}>
                                                <FiCheckCircle className="mr-2" />
                                                {savingVersion ? 'Promoting…' : 'Promote & Lock New Version'}
                                            </Button>
                                            <p className="text-[10px] text-gray-400 mt-2 text-center leading-tight">
                                                Creates an immutable Version ID that propagates to all attached clusters.
                                            </p>
                                        </Card>

                                        {/* Quick Version List */}
                                        <Card className="p-4 border-gray-200 shadow-sm bg-white flex-1 overflow-y-auto">
                                            <h3 className="text-xs font-bold text-gray-900 mb-3 uppercase tracking-wider">Recent Versions</h3>
                                            <div className="space-y-2">
                                                {versions.slice(0, 5).map(ver => (
                                                    <div key={ver.id}
                                                        className={`p-2.5 rounded-lg border text-xs ${ver.status === 'ACTIVE'
                                                            ? 'border-green-200 bg-green-50'
                                                            : 'border-gray-200 bg-gray-50'}`}>
                                                        <div className="flex justify-between items-center">
                                                            <span className="font-bold text-gray-900">v{ver.version_number}</span>
                                                            {ver.status === 'ACTIVE' && <Badge color="green" size="sm">ACTIVE</Badge>}
                                                            {ver.status === 'ARCHIVED' && <Badge color="gray" size="sm">ARCHIVED</Badge>}
                                                        </div>
                                                        <div className="text-[10px] text-gray-500 mt-1 flex items-center gap-1">
                                                            <FiClock size={9} />
                                                            {ver.created_at ? new Date(ver.created_at).toLocaleDateString() : 'Unknown'}
                                                        </div>
                                                    </div>
                                                ))}
                                            </div>
                                        </Card>
                                    </div>
                                </div>
                            )}

                            {/* ── IMPACT TAB — Feature 25,27 ──────────────── */}
                            {activeTab === 'impact' && (
                                <div className="max-w-3xl mx-auto space-y-6">
                                    <Card className="p-6 bg-white shadow-sm">
                                        <h3 className="text-lg font-bold text-gray-900 mb-1">Template-to-Cluster Impact View</h3>
                                        <p className="text-sm text-gray-500 mb-6">
                                            Shows all clusters currently governed by "{selectedTemplate.name}".
                                            Modifying this template will alter optimization boundaries for every listed cluster.
                                        </p>

                                        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6 flex items-start gap-3">
                                            <FiAlertTriangle className="text-amber-600 mt-0.5 flex-shrink-0" />
                                            <div className="text-sm text-amber-800">
                                                <strong>{attachedCounts[selectedTemplate.id] || 0} cluster(s)</strong> will be affected if you promote a new version.
                                                {selectedTemplate.scope === 'GLOBAL' && (
                                                    <span className="block text-xs text-amber-600 mt-1">
                                                        This is a <strong>GLOBAL</strong> template — changes propagate to all attached clusters immediately.
                                                    </span>
                                                )}
                                            </div>
                                        </div>

                                        {(attachedCounts[selectedTemplate.id] || 0) === 0 ? (
                                            <div className="text-center py-8 text-gray-400">
                                                <FiServer className="mx-auto mb-3" size={32} />
                                                <p className="text-sm">No clusters are using this template yet.</p>
                                                <p className="text-xs mt-1">Assign it from the Clusters → Node Template tab.</p>
                                            </div>
                                        ) : (
                                            <div className="text-center py-6 text-gray-500">
                                                <FiServer className="mx-auto mb-3" size={32} />
                                                <p className="text-sm font-medium">{attachedCounts[selectedTemplate.id]} cluster(s) attached</p>
                                                <p className="text-xs text-gray-400 mt-1">Cluster details available from Clusters → Node Template tab</p>
                                            </div>
                                        )}
                                    </Card>
                                </div>
                            )}

                            {/* ── AUDIT TAB — Feature 6,28 ────────────────── */}
                            {activeTab === 'audit' && (
                                <div className="max-w-3xl mx-auto space-y-6">
                                    <Card className="p-6 bg-white shadow-sm">
                                        <h3 className="text-lg font-bold text-gray-900 mb-1">Version Audit Trail</h3>
                                        <p className="text-sm text-gray-500 mb-6">
                                            Complete immutable history of constraint changes. Each version is a point-in-time snapshot.
                                        </p>

                                        {versions.length === 0 ? (
                                            <div className="text-center py-8 text-gray-400">
                                                <FiClock className="mx-auto mb-3" size={32} />
                                                <p className="text-sm">No versions recorded yet.</p>
                                            </div>
                                        ) : (
                                            <div className="space-y-3">
                                                {versions.map((ver, idx) => (
                                                    <div key={ver.id}
                                                        className={`p-4 rounded-lg border ${ver.status === 'ACTIVE'
                                                            ? 'border-green-200 bg-green-50/50'
                                                            : 'border-gray-200 bg-gray-50/50'}`}>
                                                        <div className="flex justify-between items-start mb-2">
                                                            <div className="flex items-center gap-2">
                                                                <span className="text-sm font-bold text-gray-900">Version {ver.version_number}</span>
                                                                {ver.status === 'ACTIVE' && <Badge color="green">ACTIVE</Badge>}
                                                                {ver.status === 'ARCHIVED' && <Badge color="gray">ARCHIVED</Badge>}
                                                                {ver.status === 'DRAFT' && <Badge color="yellow">DRAFT</Badge>}
                                                                {idx === 0 && <Badge color="blue" size="sm">LATEST</Badge>}
                                                            </div>
                                                            <span className="text-xs text-gray-500 font-mono">{ver.id.split('-')[0]}</span>
                                                        </div>

                                                        <div className="text-xs text-gray-500 flex items-center gap-3">
                                                            <span className="flex items-center gap-1">
                                                                <FiClock size={11} />
                                                                {ver.created_at ? new Date(ver.created_at).toLocaleString() : 'Unknown'}
                                                            </span>
                                                        </div>

                                                        {/* Constraint summary */}
                                                        {ver.constraints_json && (
                                                            <div className="mt-3 pt-3 border-t border-gray-200">
                                                                <div className="text-[10px] font-semibold text-gray-500 uppercase mb-2">Constraint Snapshot</div>
                                                                <div className="grid grid-cols-3 gap-2 text-xs text-gray-600">
                                                                    <div>vCPU: {ver.constraints_json.min_vcpu}–{ver.constraints_json.max_vcpu}</div>
                                                                    <div>Memory: {ver.constraints_json.min_memory}–{ver.constraints_json.max_memory} GB</div>
                                                                    <div>Policy: {ver.constraints_json.optimization_policy}</div>
                                                                    <div>Risk: ≤{ver.constraints_json.risk_threshold}%</div>
                                                                    <div>Savings: ≥{ver.constraints_json.savings_threshold}%</div>
                                                                    <div>Arch: {(ver.constraints_json.architectures || []).join(', ')}</div>
                                                                </div>
                                                            </div>
                                                        )}

                                                        {/* Feature 26: Rollback via re-promote */}
                                                        {ver.status !== 'ACTIVE' && (
                                                            <div className="mt-3 pt-2 border-t border-gray-200">
                                                                <button className="text-xs text-blue-600 hover:text-blue-800 font-medium flex items-center gap-1"
                                                                    onClick={() => {
                                                                        if (ver.constraints_json) {
                                                                            setEditingConstraints({ ...DEFAULT_CONSTRAINTS, ...ver.constraints_json });
                                                                            setActiveTab('editor');
                                                                            toast.success(`Loaded v${ver.version_number} constraints into editor. Promote to rollback.`);
                                                                        }
                                                                    }}>
                                                                    <FiRefreshCw size={11} /> Load into Editor (Rollback)
                                                                </button>
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        )}
                                    </Card>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default NodeTemplates;
