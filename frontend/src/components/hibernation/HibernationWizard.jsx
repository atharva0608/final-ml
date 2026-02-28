import React, { useState, useEffect } from 'react';
import { FiX, FiCheck, FiCpu, FiClock, FiCalendar, FiActivity, FiAlertTriangle, FiArrowRight, FiArrowLeft, FiSave } from 'react-icons/fi';
import { toast } from 'react-hot-toast';
import { hibernationAPI } from '../../services/api';
import HibernationTypeCard from './HibernationTypeCard';

const STEPS = [
    { id: 1, name: "Select Clusters" },
    { id: 2, name: "Choose Strategy" },
    { id: 3, name: "Configure Schedule" },
    { id: 4, name: "Review & Save" }
];

const HibernationWizard = ({ schedule, clusters, onClose }) => {
    const [currentStep, setCurrentStep] = useState(1);
    const [loading, setLoading] = useState(false);

    // Form State
    const [formData, setFormData] = useState({
        name: "",
        description: "",
        cluster_ids: [],
        strategy: "NAMESPACE_SLEEP",
        schedule_matrix: Array(168).fill(1), // Default awake
        timezone: "UTC",
        pre_warm_minutes: 15,
        is_active: true
    });

    // Load existing data if editing
    useEffect(() => {
        if (schedule) {
            setFormData({
                name: schedule.name,
                description: schedule.description || "",
                cluster_ids: schedule.cluster_ids || [],
                strategy: schedule.strategy,
                schedule_matrix: schedule.schedule_matrix,
                timezone: schedule.timezone,
                pre_warm_minutes: schedule.pre_warm_minutes,
                is_active: schedule.is_active
            });
        }
    }, [schedule]);

    const updateField = (field, value) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    const toggleCluster = (clusterId) => {
        setFormData(prev => {
            const ids = prev.cluster_ids.includes(clusterId)
                ? prev.cluster_ids.filter(id => id !== clusterId)
                : [...prev.cluster_ids, clusterId];
            return { ...prev, cluster_ids: ids };
        });
    };

    const applyPreset = (preset) => {
        let matrix = Array(168).fill(1);
        switch (preset) {
            case 'business': // Mon-Fri 9-5
                for (let d = 0; d < 7; d++) {
                    for (let h = 0; h < 24; h++) {
                        matrix[d * 24 + h] = (d >= 1 && d <= 5 && h >= 9 && h < 17) ? 1 : 0;
                    }
                }
                break;
            case 'nights_weekends': // Sleep nights/weekends
                for (let d = 0; d < 7; d++) {
                    for (let h = 0; h < 24; h++) {
                        if (d === 0 || d === 6) matrix[d * 24 + h] = 0;
                        else matrix[d * 24 + h] = (h >= 6 && h < 22) ? 1 : 0;
                    }
                }
                break;
            case 'always_on': matrix.fill(1); break;
            case 'always_off': matrix.fill(0); break;
        }
        updateField('schedule_matrix', matrix);
    };

    const handleSave = async () => {
        if (!formData.name) return toast.error("Schedule name is required");
        if (formData.cluster_ids.length === 0) return toast.error("Select at least one cluster");

        setLoading(true);
        try {
            if (schedule) {
                await hibernationAPI.update(schedule.id, formData);
                toast.success("Schedule updated successfully");
            } else {
                await hibernationAPI.create(formData);
                toast.success("Schedule created successfully");
            }
            onClose();
        } catch (err) {
            console.error(err);
            toast.error(err.response?.data?.detail || "Failed to save schedule");
        } finally {
            setLoading(false);
        }
    };

    const nextStep = () => setCurrentStep(prev => Math.min(prev + 1, 4));
    const prevStep = () => setCurrentStep(prev => Math.max(prev - 1, 1));

    // Render Steps
    const renderStep1 = () => (
        <div className="space-y-6">
            <div>
                <label className="block text-sm font-medium text-gray-700">Schedule Name</label>
                <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => updateField('name', e.target.value)}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                    placeholder="e.g., Weekend Dev Environment Shutdown"
                />
            </div>
            <div>
                <label className="block text-sm font-medium text-gray-700">Description</label>
                <textarea
                    value={formData.description}
                    onChange={(e) => updateField('description', e.target.value)}
                    className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:ring-blue-500 focus:border-blue-500"
                    placeholder="Optional description..."
                    rows={2}
                />
            </div>
            <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Select Target Clusters</label>
                {!clusters?.length ? (
                    <div className="p-4 bg-yellow-50 text-yellow-700 rounded-md text-sm">
                        No clusters found. Please connect a cluster first.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-60 overflow-y-auto p-1">
                        {clusters.map(cluster => (
                            <div
                                key={cluster.id}
                                onClick={() => toggleCluster(cluster.id)}
                                className={`flex items-center p-3 rounded-lg border cursor-pointer transition-colors ${formData.cluster_ids.includes(cluster.id)
                                    ? 'bg-blue-50 border-blue-500'
                                    : 'bg-white border-gray-200 hover:border-blue-300'
                                    }`}
                            >
                                <div className={`w-5 h-5 rounded border flex items-center justify-center mr-3 ${formData.cluster_ids.includes(cluster.id) ? 'bg-blue-600 border-blue-600' : 'border-gray-300'
                                    }`}>
                                    {formData.cluster_ids.includes(cluster.id) && <FiCheck className="text-white w-3 h-3" />}
                                </div>
                                <div>
                                    <div className="font-medium text-gray-900">{cluster.name}</div>
                                    <div className="text-xs text-gray-500">{cluster.region} • {cluster.status}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );

    const renderStep2 = () => (
        <div className="space-y-4">

            <div className="grid grid-cols-3 gap-4">
                {['NAMESPACE_SLEEP', 'NUCLEAR', 'SNAPSHOT_RESTORE'].map(type => (
                    <div
                        key={type}
                        onClick={() => updateField('strategy', type)}
                        className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${formData.strategy === type
                            ? 'border-blue-600 bg-blue-50 transform scale-[1.02]'
                            : 'border-gray-200 hover:border-gray-300'
                            }`}
                    >
                        <div className="flex items-center justify-between mb-3">
                            <h4 className="font-bold text-gray-900">
                                {type === 'NAMESPACE_SLEEP' && 'Namespace Sleep'}
                                {type === 'NUCLEAR' && 'Nuclear'}
                                {type === 'SNAPSHOT_RESTORE' && 'Snapshot & Restore'}
                            </h4>
                            {formData.strategy === type && <FiCheck className="text-blue-600 w-5 h-5" />}
                        </div>
                        <p className="text-sm text-gray-600 mb-4 h-16">
                            {type === 'NAMESPACE_SLEEP' && 'Scales down workloads to zero replicas. Preserves configs and PVCs. Fast wake-up.'}
                            {type === 'NUCLEAR' && 'Aggressively removes nodes. Highest savings but slower recovery (~10m).'}
                            {type === 'SNAPSHOT_RESTORE' && 'Takes full snapshots of state and volumes before teardown. Best for compliance.'}
                        </p>
                        <div className="flex items-center gap-2 text-xs font-medium bg-white p-2 rounded border border-gray-100">
                            <span className="text-gray-500">Savings:</span>
                            <span className="text-green-600">{type === 'NUCLEAR' ? '99%' : type === 'SNAPSHOT_RESTORE' ? '90%' : '80%'}</span>
                        </div>
                    </div>
                ))}
            </div>
            {formData.strategy === 'NUCLEAR' && (
                <div className="flex items-start gap-3 p-4 bg-orange-50 border border-orange-200 rounded-md text-orange-800 text-sm">
                    <FiAlertTriangle className="w-5 h-5 flex-shrink-0" />
                    <p>Nuclear strategy will terminate all worker nodes. Ensure workloads are stateless or have proper PVC retention policies.</p>
                </div>
            )}
        </div>
    );

    const renderStep3 = () => (
        <div className="space-y-6">
            <div className="flex justify-between items-center bg-gray-50 p-3 rounded-lg">
                <div className="flex gap-2">
                    <button onClick={() => applyPreset('business')} className="px-3 py-1 text-sm bg-white border rounded hover:bg-gray-50">Business Hours</button>
                    <button onClick={() => applyPreset('nights_weekends')} className="px-3 py-1 text-sm bg-white border rounded hover:bg-gray-50">Nights & Weekends</button>
                    <button onClick={() => applyPreset('always_on')} className="px-3 py-1 text-sm bg-white border rounded hover:bg-gray-50">Always On</button>
                </div>
                <div className="flex items-center gap-2">
                    <label className="text-sm text-gray-600">Timezone:</label>
                    <select
                        value={formData.timezone}
                        onChange={(e) => updateField('timezone', e.target.value)}
                        className="text-sm border-gray-300 rounded-md"
                    >
                        <option value="UTC">UTC</option>
                        <option value="America/New_York">New York</option>
                        <option value="America/Chicago">Chicago</option>
                        <option value="America/Los_Angeles">Los Angeles</option>
                        <option value="Europe/London">London</option>
                        <option value="Asia/Tokyo">Tokyo</option>
                    </select>
                </div>
            </div>

            <div className="border rounded-lg overflow-hidden">
                <div className="grid grid-cols-8 border-b bg-gray-50 text-xs font-semibold text-gray-500">
                    <div className="p-2 text-center">Day</div>
                    {[...Array(24)].map((_, i) => (
                        <div key={i} className="p-2 text-center col-span-1" style={{ width: '3%' }}>{i}</div>
                    ))}
                    <div className="col-span-23"></div> {/* Spacer fix for grid layout if needed, actually doing simple map */}
                </div>
                {/* Custom Grid Layout */}
                <div className="flex flex-col">
                    {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day, d) => (
                        <div key={day} className="flex border-b last:border-0 h-10 items-center">
                            <div className="w-16 flex-shrink-0 text-center text-sm font-medium text-gray-600 border-r bg-gray-50 h-full flex items-center justify-center">{day}</div>
                            <div className="flex-1 flex h-full">
                                {[...Array(24)].map((_, h) => {
                                    const idx = d * 24 + h;
                                    const isAwake = formData.schedule_matrix[idx] === 1;
                                    return (
                                        <div
                                            key={h}
                                            onClick={() => {
                                                const newMatrix = [...formData.schedule_matrix];
                                                newMatrix[idx] = isAwake ? 0 : 1;
                                                updateField('schedule_matrix', newMatrix);
                                            }}
                                            className={`flex-1 border-r last:border-0 cursor-pointer transition-colors hover:bg-opacity-80 ${isAwake ? 'bg-green-500 border-green-600' : 'bg-gray-200'
                                                }`}
                                            title={`${day} ${h}:00 - ${isAwake ? 'Awake' : 'Sleep'}`}
                                        />
                                    );
                                })}
                            </div>
                        </div>
                    ))}
                </div>
            </div>
            <div className="flex justify-end items-center gap-2 text-xs text-gray-500">
                <div className="flex items-center gap-1"><div className="w-3 h-3 bg-green-500 rounded"></div> Awake</div>
                <div className="flex items-center gap-1"><div className="w-3 h-3 bg-gray-200 rounded"></div> Sleep</div>
            </div>
        </div>
    );

    const renderStep4 = () => (
        <div className="space-y-6">
            <h3 className="text-lg font-medium text-gray-900">Review Schedule Details</h3>

            <div className="bg-gray-50 rounded-lg p-6 space-y-4">
                <div className="grid grid-cols-2 gap-4">
                    <div>
                        <span className="text-sm text-gray-500 block">Name</span>
                        <span className="font-medium text-gray-900">{formData.name}</span>
                    </div>
                    <div>
                        <span className="text-sm text-gray-500 block">Strategy</span>
                        <span className="font-medium text-gray-900">{formData.strategy.replace('_', ' ')}</span>
                    </div>
                    <div>
                        <span className="text-sm text-gray-500 block">Timezone</span>
                        <span className="font-medium text-gray-900">{formData.timezone}</span>
                    </div>
                    <div>
                        <span className="text-sm text-gray-500 block">Pre-warm</span>
                        <span className="font-medium text-gray-900">{formData.pre_warm_minutes} min</span>
                    </div>
                    <div className="col-span-2">
                        <span className="text-sm text-gray-500 block">Selected Clusters ({formData.cluster_ids.length})</span>
                        <div className="flex flex-wrap gap-2 mt-1">
                            {formData.cluster_ids.map(id => {
                                const c = clusters.find(cl => cl.id === id);
                                return (
                                    <span key={id} className="px-2 py-1 bg-white border rounded text-xs text-gray-700">
                                        {c?.name || id}
                                    </span>
                                );
                            })}
                        </div>
                    </div>
                </div>
            </div>

            <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3">
                <FiActivity className="text-green-600 w-5 h-5" />
                <div>
                    <p className="text-sm text-green-800 font-medium">Estimated Impact</p>
                    <p className="text-xs text-green-700">This schedule will reduce uptime by approx {Math.round((formData.schedule_matrix.filter(x => x === 0).length / 168) * 100)}%, generating significant cost savings.</p>
                </div>
            </div>
        </div>
    );

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="px-8 py-5 border-b flex justify-between items-center bg-gray-50 rounded-t-xl">
                    <h2 className="text-xl font-bold text-gray-900">
                        {schedule ? 'Edit Schedule' : 'Create New Schedule'}
                    </h2>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
                        <FiX className="w-6 h-6" />
                    </button>
                </div>

                {/* Progress Bar */}
                <div className="px-8 py-4 border-b">
                    <div className="flex items-center justify-between relative">
                        {/* Line */}
                        <div className="absolute left-0 right-0 top-1/2 h-0.5 bg-gray-200 -z-10" />

                        {STEPS.map((step) => {
                            const isCompleted = step.id < currentStep;
                            const isCurrent = step.id === currentStep;
                            return (
                                <div key={step.id} className="flex flex-col items-center bg-white px-2">
                                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold transition-colors ${isCompleted ? 'bg-green-500 text-white' :
                                        isCurrent ? 'bg-blue-600 text-white shadow-lg shadow-blue-200' :
                                            'bg-gray-100 text-gray-400 border border-gray-200'
                                        }`}>
                                        {isCompleted ? <FiCheck className="w-5 h-5" /> : step.id}
                                    </div>
                                    <span className={`text-xs mt-2 font-medium ${isCurrent ? 'text-blue-600' : 'text-gray-500'}`}>
                                        {step.name}
                                    </span>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8">
                    {currentStep === 1 && renderStep1()}
                    {currentStep === 2 && renderStep2()}
                    {currentStep === 3 && renderStep3()}
                    {currentStep === 4 && renderStep4()}
                </div>

                {/* Footer */}
                <div className="px-8 py-5 border-t bg-gray-50 rounded-b-xl flex justify-between items-center">
                    <button
                        onClick={prevStep}
                        disabled={currentStep === 1}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-colors ${currentStep === 1
                            ? 'text-gray-300 cursor-not-allowed'
                            : 'text-gray-700 bg-white border border-gray-300 hover:bg-gray-50 hover:shadow-sm'
                            }`}
                    >
                        <FiArrowLeft className="w-4 h-4" /> Back
                    </button>

                    {currentStep < 4 ? (
                        <button
                            onClick={nextStep}
                            disabled={currentStep === 1 && formData.cluster_ids.length === 0}
                            className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 shadow-md shadow-blue-200 disabled:opacity-50 disabled:shadow-none"
                        >
                            Next Step <FiArrowRight className="w-4 h-4" />
                        </button>
                    ) : (
                        <button
                            onClick={handleSave}
                            disabled={loading}
                            className="flex items-center gap-2 px-6 py-2.5 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700 shadow-md shadow-green-200 disabled:opacity-50"
                        >
                            {loading ? (
                                <span className="flex items-center gap-2">Saving...</span>
                            ) : (
                                <>
                                    <FiSave className="w-4 h-4" /> Save Schedule
                                </>
                            )}
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default HibernationWizard;
