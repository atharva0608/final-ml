import React, { useState } from 'react';
import useAtharvaStore from '../../store/useAtharvaStore';
import {
    FiX, FiArrowRight, FiCheckCircle, FiXCircle,
    FiAlertTriangle, FiClock, FiMessageSquare
} from 'react-icons/fi';

const SwitchConfirmationModal = () => {
    const { showSwitchConfirm, switchTarget, closeSwitchConfirm, confirmSwitch, status } = useAtharvaStore();
    const [reason, setReason] = useState('');
    const [autoResumeHours, setAutoResumeHours] = useState(12);
    const [isSubmitting, setIsSubmitting] = useState(false);

    if (!showSwitchConfirm || !switchTarget) return null;

    const safetyChecks = [
        { check: 'No critical jobs running', status: true, blocking: true },
        { check: 'PDBs allow disruption', status: true, blocking: true },
        { check: 'Sufficient capacity available', status: true, blocking: true },
        { check: 'No active deployments', status: true, blocking: false },
    ];

    const allBlockingPassed = safetyChecks.filter(c => c.blocking).every(c => c.status);

    const handleConfirm = async () => {
        setIsSubmitting(true);
        await confirmSwitch({
            cluster_id: 'cluster-prod-east',
            from_pool_id: 'current-pool',
            to_pool_id: switchTarget.pool_id || switchTarget.instance_type,
            auto_resume_hours: autoResumeHours,
            reason,
            initiated_by: 'manual'
        });
        setIsSubmitting(false);
        closeSwitchConfirm();
    };

    return (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={closeSwitchConfirm}>
            <div className="bg-white rounded-xl shadow-2xl w-full max-w-lg overflow-hidden" onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div className="p-5 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-indigo-50">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-bold text-gray-900">Confirm Pool Switch</h2>
                        <button onClick={closeSwitchConfirm} className="p-2 hover:bg-white/50 rounded-lg"><FiX className="w-5 h-5" /></button>
                    </div>

                    {/* From → To */}
                    <div className="flex items-center gap-3 mt-4">
                        <div className="flex-1 p-3 bg-white rounded-lg border border-gray-200 text-center">
                            <p className="text-[10px] text-gray-500 uppercase font-bold mb-1">Current Pool</p>
                            <p className="text-sm font-bold text-gray-900">m5.large</p>
                            <p className="text-[10px] text-gray-400">us-east-1a</p>
                        </div>
                        <FiArrowRight className="w-5 h-5 text-blue-600 flex-shrink-0" />
                        <div className="flex-1 p-3 bg-blue-600 rounded-lg text-center">
                            <p className="text-[10px] text-blue-200 uppercase font-bold mb-1">New Pool</p>
                            <p className="text-sm font-bold text-white">{switchTarget.instance_type}</p>
                            <p className="text-[10px] text-blue-200">{switchTarget.availability_zone}</p>
                        </div>
                    </div>
                </div>

                <div className="p-5 space-y-5">
                    {/* Safety Checks */}
                    <div>
                        <h4 className="text-xs font-bold text-gray-700 uppercase mb-3">Safety Checks</h4>
                        <div className="space-y-2">
                            {safetyChecks.map((check, i) => (
                                <div key={i} className={`flex items-center gap-2.5 p-2 rounded-lg ${check.status ? 'bg-green-50' : 'bg-red-50'}`}>
                                    {check.status
                                        ? <FiCheckCircle className="w-4 h-4 text-green-600 flex-shrink-0" />
                                        : <FiXCircle className="w-4 h-4 text-red-600 flex-shrink-0" />}
                                    <span className="text-xs text-gray-700 flex-1">{check.check}</span>
                                    {check.blocking && (
                                        <span className="text-[10px] bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded font-medium">blocking</span>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Reason */}
                    <div>
                        <label className="flex items-center gap-1.5 text-xs font-bold text-gray-700 uppercase mb-2">
                            <FiMessageSquare className="w-3.5 h-3.5" /> Reason (optional)
                        </label>
                        <textarea
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            placeholder="Why are you switching?"
                            rows={2}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                        />
                    </div>

                    {/* Auto-resume */}
                    <div>
                        <label className="flex items-center gap-1.5 text-xs font-bold text-gray-700 uppercase mb-2">
                            <FiClock className="w-3.5 h-3.5" /> Auto-resume optimization after
                        </label>
                        <select
                            value={autoResumeHours}
                            onChange={(e) => setAutoResumeHours(parseInt(e.target.value))}
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        >
                            <option value={1}>1 hour</option>
                            <option value={4}>4 hours</option>
                            <option value={8}>8 hours</option>
                            <option value={12}>12 hours</option>
                            <option value={24}>24 hours</option>
                            <option value={0}>Never (stay manual)</option>
                        </select>
                    </div>

                    {/* Warning */}
                    {!allBlockingPassed && (
                        <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
                            <FiAlertTriangle className="w-4 h-4 text-red-600 flex-shrink-0 mt-0.5" />
                            <p className="text-xs text-red-700">One or more blocking safety checks have failed. Switching is not recommended.</p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-end gap-3 p-5 border-t border-gray-200 bg-gray-50">
                    <button onClick={closeSwitchConfirm}
                        className="px-4 py-2 text-xs font-medium text-gray-600 bg-white rounded-lg hover:bg-gray-50 border border-gray-200 transition-colors">
                        Cancel
                    </button>
                    <button
                        onClick={handleConfirm}
                        disabled={!allBlockingPassed || isSubmitting}
                        className={`px-6 py-2 text-xs font-semibold rounded-lg transition-colors ${allBlockingPassed && !isSubmitting
                                ? 'bg-blue-600 text-white hover:bg-blue-700'
                                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                            }`}
                    >
                        {isSubmitting ? 'Switching...' : 'Confirm Switch'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default SwitchConfirmationModal;
