import React, { useState, useEffect } from 'react';
import { Card, Button, Badge } from '../shared';
import { nodeTemplateAPI } from '../../services/api';
import { FiCheck, FiServer, FiShield, FiLink, FiActivity } from 'react-icons/fi';
import toast from 'react-hot-toast';

const NodeTemplateTab = ({ clusterId }) => {
    const [loading, setLoading] = useState(true);
    const [templates, setTemplates] = useState([]);

    // Active mapping
    const [activeMapping, setActiveMapping] = useState(null);
    const [activeConstraints, setActiveConstraints] = useState(null);

    // Selection state
    const [selectedTemplateId, setSelectedTemplateId] = useState('');
    const [assigning, setAssigning] = useState(false);

    useEffect(() => {
        if (clusterId) {
            fetchData();
        }
    }, [clusterId]);

    const fetchData = async () => {
        setLoading(true);
        try {
            const [templatesRes, mappingRes] = await Promise.allSettled([
                nodeTemplateAPI.getGlobalTemplates(),
                nodeTemplateAPI.getActiveMapping(clusterId)
            ]);

            if (templatesRes.status === 'fulfilled') {
                setTemplates(templatesRes.value.data.templates || []);
            }

            if (mappingRes.status === 'fulfilled' && mappingRes.value.data) {
                const mapping = mappingRes.value.data;
                setActiveMapping(mapping);
                if (mapping.version && mapping.version.constraints_json) {
                    setActiveConstraints(mapping.version.constraints_json);
                }
            } else {
                setActiveMapping(null);
                setActiveConstraints(null);
            }

        } catch (err) {
            console.error(err);
            toast.error('Failed to load template assignment data');
        } finally {
            setLoading(false);
        }
    };

    const handleAssign = async () => {
        if (!selectedTemplateId) return;
        setAssigning(true);
        try {
            await nodeTemplateAPI.assignToCluster(clusterId, selectedTemplateId, null);
            toast.success('Successfully assigned enterprise template to cluster');
            fetchData();
            setSelectedTemplateId('');
        } catch (err) {
            console.error(err);
            toast.error('Failed to assign template');
        } finally {
            setAssigning(false);
        }
    };

    if (loading) {
        return <div className="py-12 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>;
    }

    return (
        <div className="space-y-6">
            <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 border-blue-100">
                <div className="flex items-center justify-between">
                    <div>
                        <h3 className="text-lg font-bold text-gray-900 flex items-center gap-2">
                            <FiLink /> Enterprise Template Assignment
                        </h3>
                        <p className="text-sm text-gray-600 mt-1">Assign an authoritative constraint wrapper to guide ML candidate filtering.</p>
                    </div>
                    <div className="text-right flex items-center gap-4">
                        {activeMapping ? (
                            <Badge color="green" size="lg" className="flex items-center gap-1">
                                <FiCheck /> ACTIVE MAPPING
                            </Badge>
                        ) : (
                            <Badge color="gray" size="lg">NO TEMPLATE ASSIGNED</Badge>
                        )}
                    </div>
                </div>
            </Card>

            <Card className="border-indigo-100 shadow-sm border p-5 bg-white">
                <h4 className="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wider">Set Cluster Default Template</h4>
                <div className="flex gap-4 items-end">
                    <div className="flex-1">
                        <label className="block text-sm font-medium text-gray-700 mb-1">Select Global Template <span className="text-red-500">*</span></label>
                        <select
                            className="w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500"
                            value={selectedTemplateId}
                            onChange={(e) => setSelectedTemplateId(e.target.value)}
                            disabled={assigning}
                        >
                            <option value="">-- Choose a template from the Global Registry --</option>
                            {templates.map(t => (
                                <option key={t.id} value={t.id}>{t.name} (Global)</option>
                            ))}
                        </select>
                    </div>
                    <Button
                        variant="primary"
                        onClick={handleAssign}
                        disabled={!selectedTemplateId || assigning}
                        className="bg-indigo-600 hover:bg-indigo-700"
                    >
                        {assigning ? 'Assigning...' : 'Set as Cluster Default'}
                    </Button>
                </div>
            </Card>

            {/* Current Assignment Details */}
            {activeMapping && activeConstraints ? (
                <Card className="border-green-100 shadow-sm border p-5 bg-white relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-1 h-full bg-green-500"></div>
                    <div className="flex justify-between items-start mb-6">
                        <div>
                            <h4 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">Active Configuration</h4>
                            <p className="text-sm text-gray-500 mt-1">This cluster is currently governed by the constraints below.</p>
                        </div>
                        <div className="text-right">
                            <div className="text-lg font-bold text-gray-900">{activeMapping.template?.name || 'Unknown Template'}</div>
                            <div className="text-xs text-gray-500 font-mono mt-1">Version ID: {activeMapping.version_id.split('-')[0]}</div>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-gray-50 rounded-lg p-4 border border-gray-100">
                        <div>
                            <div className="text-xs text-gray-500 mb-1">Workload Scope</div>
                            <div className="text-sm font-semibold text-gray-900">{activeConstraints.workload_scope}</div>
                        </div>
                        <div>
                            <div className="text-xs text-gray-500 mb-1">Policy Objective</div>
                            <div className="text-sm font-semibold text-gray-900">{activeConstraints.optimization_policy.replace('_', ' ')}</div>
                        </div>
                        <div>
                            <div className="text-xs text-gray-500 mb-1">Max Interruption Risk</div>
                            <div className="text-sm font-bold text-orange-600">{activeConstraints.risk_threshold}%</div>
                        </div>
                        <div>
                            <div className="text-xs text-gray-500 mb-1">Min Expected Savings</div>
                            <div className="text-sm font-bold text-green-600">{activeConstraints.savings_threshold}%</div>
                        </div>

                        <div className="col-span-2 pt-3 border-t border-gray-200 mt-1">
                            <div className="text-xs text-gray-500 mb-1">vCPU Bounds</div>
                            <div className="text-sm font-semibold text-gray-900">{activeConstraints.min_vcpu} - {activeConstraints.max_vcpu} Cores</div>
                        </div>
                        <div className="col-span-2 pt-3 border-t border-gray-200 mt-1">
                            <div className="text-xs text-gray-500 mb-1">Memory Bounds</div>
                            <div className="text-sm font-semibold text-gray-900">{activeConstraints.min_memory} - {activeConstraints.max_memory} GiB</div>
                        </div>

                        <div className="col-span-4 pt-3 border-t border-gray-200 mt-1">
                            <div className="text-xs text-gray-500 mb-1">Provisioning Strategy</div>
                            <div className="text-sm font-semibold text-gray-900">{activeConstraints.substitute_strategy}</div>
                        </div>
                    </div>
                </Card>
            ) : (
                <Card className="p-12 text-center text-gray-500 border border-dashed border-gray-300">
                    <FiShield className="mx-auto text-gray-300 mb-4" size={48} />
                    <h3 className="text-lg font-semibold text-gray-600 mb-2">Cluster Unprotected</h3>
                    <p className="text-sm mb-4 max-w-md mx-auto">This cluster cannot enter optimization mode because it does not have an active template assigned. Please select a template above.</p>
                </Card>
            )}
        </div>
    );
};

export default NodeTemplateTab;
