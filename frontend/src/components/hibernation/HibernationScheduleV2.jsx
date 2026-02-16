import React, { useState, useEffect } from 'react';
import { toast } from 'react-hot-toast';
import { FiSave, FiX, FiClock, FiCalendar, FiZap, FiAlertTriangle, FiInfo } from 'react-icons/fi';
import HibernationTypeCard from './HibernationTypeCard';
import { hibernationAPI } from '../../services/api';

/**
 * HibernationScheduleV2 - Restructured cluster hibernation management
 *
 * Three hibernation strategies:
 * 1. Namespace Sleep (Gentle Shutdown) - Quick recovery, state preservation
 * 2. Nuclear (Complete Teardown) - Maximum savings, longer recovery
 * 3. Snapshot & Restore (State Preservation) - Guaranteed recovery, compliance
 */
const HibernationScheduleV2 = ({ clusterId, onClose }) => {
    // Strategy definitions
    const strategies = [
        {
            type: 'NAMESPACE_SLEEP',
            name: 'Namespace Sleep',
            subtitle: 'Gentle Shutdown',
            description: 'Scale down workloads within specific namespaces to zero replicas while preserving configurations.',
            wakeTime: '~2 min',
            savingsPercent: 80,
            safetyLevel: 'High',
            features: [
                'Preserves all configurations and PVCs',
                'Graceful pod shutdown with readiness probes',
                'HPA/VPA settings saved and restored',
                'Nodes auto-scale down naturally',
                'Fast recovery with state preservation'
            ],
            useCases: 'Development/staging environments during off-hours where you need quick recovery and state preservation.',
            details: {
                preHibernation: [
                    'Identify target namespaces (dev, staging, qa)',
                    'Query all deployments, statefulsets, daemonsets, HPA/VPA',
                    'Store current state snapshot (replica counts, configs)',
                    'Tag resources with hibernation metadata'
                ],
                hibernation: [
                    'Scale down Deployments to 0 replicas',
                    'Scale down StatefulSets to 0 (preserving PVCs)',
                    'Disable HPA/VPA or set min replicas to 0',
                    'Keep control plane and monitoring running',
                    'Nodes scale down via Cluster Autoscaler'
                ],
                wakeUp: [
                    'Read hibernation annotations from resources',
                    'Restore DaemonSets and uncordon nodes',
                    'Enable HPA/VPA with original settings',
                    'Restore StatefulSets (PVC reattachment)',
                    'Restore Deployments last',
                    'Wait for readiness probes'
                ]
            }
        },
        {
            type: 'NUCLEAR',
            name: 'Nuclear',
            subtitle: 'Complete Teardown',
            description: 'Aggressively remove all nodes while preserving cluster control plane and state definitions.',
            wakeTime: '~10 min',
            savingsPercent: 99,
            safetyLevel: 'Medium',
            features: [
                'Maximum cost savings (99% reduction)',
                'Complete node removal',
                'Preserves cluster control plane',
                'Exports all resource manifests',
                'Optional PV snapshot and deletion'
            ],
            useCases: 'Long-term hibernation (weekends, extended periods), maximum cost savings, when recovery time of 10-15 minutes is acceptable.',
            details: {
                preHibernation: [
                    'Export complete cluster state (CRDs, manifests, configs)',
                    'Store Helm release states and values',
                    'Document network policies and RBAC',
                    'Create snapshot manifest with node groups',
                    'Store in versioned backup (S3/GCS/Git)'
                ],
                hibernation: [
                    'Cordon all nodes (prevent scheduling)',
                    'Drain all nodes gracefully with timeout',
                    'Evict pods respecting PodDisruptionBudgets',
                    'Scale down node groups/pools to 0',
                    'Optional: Snapshot and delete PVs',
                    'Keep control plane running'
                ],
                wakeUp: [
                    'Restore node groups to minimum capacity',
                    'Wait for nodes to become Ready',
                    'Restore PVs from snapshots if deleted',
                    'Re-apply manifests in dependency order',
                    'Restore services and networking',
                    'Validate all pods reach Running state'
                ]
            }
        },
        {
            type: 'SNAPSHOT_RESTORE',
            name: 'Snapshot & Restore',
            subtitle: 'State Preservation',
            description: 'Create point-in-time cluster snapshots including etcd, volumes, and configurations for complete recovery.',
            wakeTime: '~12 min',
            savingsPercent: 90,
            safetyLevel: 'Highest',
            features: [
                'Full etcd snapshot (cluster state database)',
                'All PersistentVolumes snapshotted via CSI',
                'Cluster-wide resource backup',
                'Guaranteed state recovery',
                'Compliance-ready with retention policy'
            ],
            useCases: 'When you need guaranteed state recovery, compliance requirements for backups, or testing disaster recovery scenarios.',
            details: {
                preHibernation: [
                    'Create etcd snapshot (cluster state DB)',
                    'Snapshot all PVs using CSI snapshots',
                    'Backup cluster-wide resources (CRDs, RBAC)',
                    'Document cluster configuration',
                    'Store with metadata and retention policy'
                ],
                hibernation: [
                    'Take full etcd snapshot',
                    'Create PV snapshots in parallel',
                    'Export non-namespaced resources',
                    'Option A: Soft (scale down like Namespace Sleep)',
                    'Option B: Hard (execute Nuclear shutdown)',
                    'Compress and version snapshots'
                ],
                wakeUp: [
                    'Restore etcd from snapshot (if Hard)',
                    'Restore PV snapshots as new volumes',
                    'Recreate cluster from etcd state',
                    'Verify volume bindings',
                    'Update PVC references to new volume IDs',
                    'Validate data integrity with checksums'
                ]
            }
        }
    ];

    const [selectedStrategy, setSelectedStrategy] = useState('NAMESPACE_SLEEP');
    const [scheduleMatrix, setScheduleMatrix] = useState(Array(168).fill(1)); // 7 days × 24 hours
    const [timezone, setTimezone] = useState('America/New_York');
    const [preWarmMinutes, setPreWarmMinutes] = useState(15);
    const [isActive, setIsActive] = useState(true);
    const [loading, setLoading] = useState(false);
    const [existingSchedule, setExistingSchedule] = useState(null);
    const [showDetails, setShowDetails] = useState(null);

    // Common timezones
    const timezones = [
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'Europe/London',
        'Europe/Paris',
        'Asia/Tokyo',
        'Asia/Singapore',
        'UTC'
    ];

    // Load existing schedule
    useEffect(() => {
        const loadSchedule = async () => {
            try {
                const response = await hibernationAPI.getByCluster(clusterId);
                if (response.data && response.data.schedules && response.data.schedules.length > 0) {
                    const schedule = response.data.schedules[0];
                    setExistingSchedule(schedule);
                    setSelectedStrategy(schedule.strategy);
                    setScheduleMatrix(schedule.schedule_matrix);
                    setTimezone(schedule.timezone);
                    setPreWarmMinutes(schedule.pre_warm_minutes);
                    setIsActive(schedule.is_active === 'Y' || schedule.is_active === true);
                }
            } catch (err) {
                console.error('Failed to load schedule:', err);
            }
        };

        if (clusterId) {
            loadSchedule();
        }
    }, [clusterId]);

    // Handle save
    const handleSave = async () => {
        setLoading(true);
        try {
            const scheduleData = {
                cluster_id: clusterId,
                schedule_matrix: scheduleMatrix,
                timezone: timezone,
                pre_warm_minutes: preWarmMinutes,
                strategy: selectedStrategy,
                is_active: isActive
            };

            if (existingSchedule) {
                await hibernationAPI.update(existingSchedule.id, scheduleData);
                toast.success('Hibernation schedule updated successfully');
            } else {
                await hibernationAPI.create(scheduleData);
                toast.success('Hibernation schedule created successfully');
            }

            if (onClose) onClose();
        } catch (err) {
            console.error('Failed to save schedule:', err);
            toast.error(err.response?.data?.detail || 'Failed to save hibernation schedule');
        } finally {
            setLoading(false);
        }
    };

    // Calculate estimated savings
    const calculateSavings = () => {
        const sleepHours = scheduleMatrix.filter(h => h === 0).length;
        const strategy = strategies.find(s => s.type === selectedStrategy);
        const savingsPercent = strategy.savingsPercent / 100;

        // Assume cluster costs $500/month running 24/7
        const monthlyCost = 500;
        const hourlyCost = monthlyCost / 730; // hours per month
        const savings = sleepHours * hourlyCost * savingsPercent * 4.35; // weeks per month

        return savings.toFixed(2);
    };

    // Quick presets
    const applyPreset = (preset) => {
        let matrix = Array(168).fill(1);

        switch(preset) {
            case 'business_hours':
                // Awake Mon-Fri 9am-5pm (EST)
                for (let day = 0; day < 7; day++) {
                    for (let hour = 0; hour < 24; hour++) {
                        const idx = day * 24 + hour;
                        if (day >= 1 && day <= 5 && hour >= 9 && hour < 17) {
                            matrix[idx] = 1; // Awake
                        } else {
                            matrix[idx] = 0; // Sleep
                        }
                    }
                }
                break;

            case 'nights_weekends':
                // Sleep nights (10pm-6am) and weekends
                for (let day = 0; day < 7; day++) {
                    for (let hour = 0; hour < 24; hour++) {
                        const idx = day * 24 + hour;
                        if (day === 0 || day === 6) {
                            matrix[idx] = 0; // Weekend sleep
                        } else if (hour >= 22 || hour < 6) {
                            matrix[idx] = 0; // Night sleep
                        }
                    }
                }
                break;

            case 'all_sleep':
                matrix = Array(168).fill(0);
                break;

            case '24_7':
                matrix = Array(168).fill(1);
                break;

            default:
                break;
        }

        setScheduleMatrix(matrix);
        toast.success(`Applied ${preset.replace('_', ' ')} preset`);
    };

    const selectedStrategyData = strategies.find(s => s.type === selectedStrategy);

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center p-4 overflow-y-auto">
            <div className="bg-white rounded-lg shadow-2xl w-full max-w-7xl max-h-[90vh] overflow-y-auto">
                {/* Header */}
                <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between z-10">
                    <div>
                        <h2 className="text-2xl font-bold text-gray-900">Cluster Hibernation</h2>
                        <p className="text-sm text-gray-500 mt-1">Configure intelligent cluster sleep/wake schedules for cost optimization</p>
                    </div>
                    <button
                        onClick={onClose}
                        className="p-2 hover:bg-gray-100 rounded-full transition-colors"
                    >
                        <FiX className="w-6 h-6 text-gray-500" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-6">
                    {/* Step 1: Choose Strategy */}
                    <div className="mb-8">
                        <div className="flex items-center gap-2 mb-4">
                            <span className="bg-blue-600 text-white rounded-full w-8 h-8 flex items-center justify-center font-bold">1</span>
                            <h3 className="text-lg font-semibold text-gray-900">Choose Hibernation Strategy</h3>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            {strategies.map((strategy) => (
                                <HibernationTypeCard
                                    key={strategy.type}
                                    type={strategy.type}
                                    name={strategy.name}
                                    description={strategy.description}
                                    wakeTime={strategy.wakeTime}
                                    savingsPercent={strategy.savingsPercent}
                                    safetyLevel={strategy.safetyLevel}
                                    features={strategy.features}
                                    useCases={strategy.useCases}
                                    isSelected={selectedStrategy === strategy.type}
                                    onSelect={setSelectedStrategy}
                                />
                            ))}
                        </div>

                        {/* Strategy Details Expandable */}
                        {selectedStrategyData && (
                            <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-6">
                                <div className="flex items-center gap-2 mb-4">
                                    <FiInfo className="w-5 h-5 text-blue-600" />
                                    <h4 className="font-semibold text-blue-900">How {selectedStrategyData.name} Works</h4>
                                </div>

                                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                                    {/* Pre-Hibernation */}
                                    <div>
                                        <h5 className="font-semibold text-sm text-blue-800 mb-2">Pre-Hibernation Phase</h5>
                                        <ul className="space-y-1">
                                            {selectedStrategyData.details.preHibernation.map((step, idx) => (
                                                <li key={idx} className="text-xs text-blue-700 flex items-start gap-2">
                                                    <span className="text-blue-600 mt-0.5">•</span>
                                                    <span>{step}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>

                                    {/* Hibernation */}
                                    <div>
                                        <h5 className="font-semibold text-sm text-blue-800 mb-2">Hibernation Process</h5>
                                        <ul className="space-y-1">
                                            {selectedStrategyData.details.hibernation.map((step, idx) => (
                                                <li key={idx} className="text-xs text-blue-700 flex items-start gap-2">
                                                    <span className="text-blue-600 mt-0.5">•</span>
                                                    <span>{step}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>

                                    {/* Wake-Up */}
                                    <div>
                                        <h5 className="font-semibold text-sm text-blue-800 mb-2">Wake-Up Process</h5>
                                        <ul className="space-y-1">
                                            {selectedStrategyData.details.wakeUp.map((step, idx) => (
                                                <li key={idx} className="text-xs text-blue-700 flex items-start gap-2">
                                                    <span className="text-blue-600 mt-0.5">•</span>
                                                    <span>{step}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Step 2: Configure Schedule */}
                    <div className="mb-8">
                        <div className="flex items-center gap-2 mb-4">
                            <span className="bg-blue-600 text-white rounded-full w-8 h-8 flex items-center justify-center font-bold">2</span>
                            <h3 className="text-lg font-semibold text-gray-900">Configure Sleep/Wake Schedule</h3>
                        </div>

                        {/* Quick Presets */}
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 mb-2">Quick Presets</label>
                            <div className="flex flex-wrap gap-2">
                                <button
                                    onClick={() => applyPreset('business_hours')}
                                    className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm font-medium transition-colors"
                                >
                                    Business Hours (Mon-Fri 9-5)
                                </button>
                                <button
                                    onClick={() => applyPreset('nights_weekends')}
                                    className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm font-medium transition-colors"
                                >
                                    Sleep Nights & Weekends
                                </button>
                                <button
                                    onClick={() => applyPreset('24_7')}
                                    className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm font-medium transition-colors"
                                >
                                    24/7 Awake
                                </button>
                                <button
                                    onClick={() => applyPreset('all_sleep')}
                                    className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-md text-sm font-medium transition-colors"
                                >
                                    All Sleep
                                </button>
                            </div>
                        </div>

                        {/* Weekly Grid - Simplified view */}
                        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                            <div className="text-sm text-gray-600 mb-2">
                                Weekly Schedule Overview (Green = Awake, Gray = Sleep)
                            </div>
                            <div className="grid grid-cols-7 gap-2">
                                {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day, dayIdx) => (
                                    <div key={day} className="text-center">
                                        <div className="text-xs font-semibold text-gray-700 mb-1">{day}</div>
                                        <div className="space-y-1">
                                            {[...Array(24)].map((_, hourIdx) => {
                                                const idx = dayIdx * 24 + hourIdx;
                                                return (
                                                    <div
                                                        key={hourIdx}
                                                        className={`h-2 rounded ${scheduleMatrix[idx] === 1 ? 'bg-green-500' : 'bg-gray-300'}`}
                                                        title={`${day} ${hourIdx}:00`}
                                                    />
                                                );
                                            })}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Step 3: Advanced Settings */}
                    <div className="mb-8">
                        <div className="flex items-center gap-2 mb-4">
                            <span className="bg-blue-600 text-white rounded-full w-8 h-8 flex items-center justify-center font-bold">3</span>
                            <h3 className="text-lg font-semibold text-gray-900">Advanced Settings</h3>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            {/* Timezone */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    <FiCalendar className="inline w-4 h-4 mr-1" />
                                    Timezone
                                </label>
                                <select
                                    value={timezone}
                                    onChange={(e) => setTimezone(e.target.value)}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                                >
                                    {timezones.map(tz => (
                                        <option key={tz} value={tz}>{tz}</option>
                                    ))}
                                </select>
                            </div>

                            {/* Pre-warm Minutes */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    <FiClock className="inline w-4 h-4 mr-1" />
                                    Pre-warm Minutes
                                </label>
                                <input
                                    type="number"
                                    min="0"
                                    max="60"
                                    value={preWarmMinutes}
                                    onChange={(e) => setPreWarmMinutes(parseInt(e.target.value))}
                                    className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500"
                                />
                                <p className="text-xs text-gray-500 mt-1">Wake cluster before scheduled time</p>
                            </div>

                            {/* Estimated Savings */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-2">
                                    <FiZap className="inline w-4 h-4 mr-1" />
                                    Estimated Monthly Savings
                                </label>
                                <div className="text-3xl font-bold text-green-600">
                                    ${calculateSavings()}
                                </div>
                                <p className="text-xs text-gray-500 mt-1">Based on {selectedStrategyData?.savingsPercent}% efficiency</p>
                            </div>
                        </div>
                    </div>

                    {/* Warning Banner */}
                    {selectedStrategy === 'NUCLEAR' && (
                        <div className="mb-6 bg-orange-50 border border-orange-200 rounded-lg p-4 flex items-start gap-3">
                            <FiAlertTriangle className="w-5 h-5 text-orange-600 flex-shrink-0 mt-0.5" />
                            <div>
                                <h4 className="font-semibold text-orange-900 mb-1">Nuclear Shutdown Warning</h4>
                                <p className="text-sm text-orange-700">
                                    This strategy will remove all cluster nodes and may result in longer wake-up times (~10 minutes).
                                    Ensure all critical workloads have proper state management and can tolerate downtime.
                                </p>
                            </div>
                        </div>
                    )}

                    {/* Actions */}
                    <div className="flex items-center justify-between pt-6 border-t border-gray-200">
                        <div className="flex items-center gap-3">
                            <label className="flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    checked={isActive}
                                    onChange={(e) => setIsActive(e.target.checked)}
                                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                                />
                                <span className="text-sm font-medium text-gray-700">Enable Schedule</span>
                            </label>
                        </div>

                        <div className="flex gap-3">
                            <button
                                onClick={onClose}
                                className="px-6 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={loading}
                                className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors flex items-center gap-2 disabled:opacity-50"
                            >
                                <FiSave className="w-4 h-4" />
                                {loading ? 'Saving...' : existingSchedule ? 'Update Schedule' : 'Create Schedule'}
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default HibernationScheduleV2;
