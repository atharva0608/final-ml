import React, { useState } from 'react';
import { FiX, FiDatabase, FiAlertTriangle, FiClock, FiActivity, FiShield } from 'react-icons/fi';
import Button from '../../shared/Button';

const RDSWizard = ({
    isOpen,
    onClose,
    selectedResources = []
}) => {
    const [step, setStep] = useState(1);

    const totalSavings = selectedResources.reduce((acc, r) => acc + (r.cost_per_month || 0), 0);

    if (!isOpen) return null;

    const handleNext = () => {
        if (step < 3) {
            setStep(step + 1);
        } else {
            onClose();
        }
    };

    return (
        <div className="fixed inset-0 bg-gray-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl h-[600px] flex flex-col">
                {/* Header */}
                <div className="px-8 py-6 border-b border-gray-100 flex justify-between items-center">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900">Multi-AZ Optimization</h2>
                        <p className="text-sm text-gray-500">Step {step} of 3</p>
                    </div>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                        <FiX className="w-6 h-6" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8">
                    {step === 1 && (
                        <div className="space-y-6 animate-fadeIn">
                            <div className="bg-gradient-to-r from-purple-50 to-blue-50 p-6 rounded-xl border border-blue-100">
                                <h3 className="font-semibold text-gray-900 mb-2">Why remove Multi-AZ?</h3>
                                <p className="text-sm text-gray-600">
                                    Development and Staging environments rarely need the 99.95% availability SLA of Multi-AZ.
                                    Disabling it cuts your RDS costs by exactly 50% for those instances.
                                </p>
                            </div>

                            <h4 className="font-semibold text-gray-900 mt-6 mb-4">Candidates for Optimization</h4>
                            <div className="space-y-3">
                                {selectedResources.map(r => (
                                    <div key={r.id} className="flex items-center p-4 border rounded-xl hover:border-blue-300 cursor-pointer border-blue-500 bg-blue-50">
                                        <div className="mr-4 p-3 bg-white rounded-lg shadow-sm">
                                            <FiDatabase className="w-6 h-6 text-purple-600" />
                                        </div>
                                        <div className="flex-1">
                                            <div className="flex items-center gap-2">
                                                <h5 className="font-bold text-gray-900">{r.name}</h5>
                                                <span className="px-2 py-0.5 bg-gray-200 text-gray-700 text-xs rounded font-medium">{r.metadata?.Environment || 'Dev/Test'}</span>
                                            </div>
                                            <p className="text-sm text-gray-500 mt-0.5">{r.metadata?.Class || 'db.m5.large'} • {r.metadata?.Engine || 'PostgreSQL'}</p>
                                        </div>
                                        <div className="text-right">
                                            <div className="text-green-600 font-bold">${r.cost_per_month?.toFixed(2)}/mo</div>
                                            <div className="text-xs text-gray-400">Savings</div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-6 animate-fadeIn">
                            <h3 className="text-lg font-semibold">Impact Assessment</h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="p-4 border border-red-200 bg-red-50 rounded-xl">
                                    <div className="flex items-center gap-2 mb-2">
                                        <FiActivity className="text-red-600" />
                                        <h4 className="font-bold text-red-900">Downtime Required</h4>
                                    </div>
                                    <p className="text-sm text-red-800">
                                        Modifying Multi-AZ status requires a database reboot.
                                        Estimated downtime: <span className="font-bold">3-5 minutes</span>.
                                    </p>
                                </div>
                                <div className="p-4 border border-green-200 bg-green-50 rounded-xl">
                                    <div className="flex items-center gap-2 mb-2">
                                        <FiShield className="text-green-600" />
                                        <h4 className="font-bold text-green-900">Data Safety</h4>
                                    </div>
                                    <p className="text-sm text-green-800">
                                        No data will be lost. Automated backups remain enabled (Single-AZ).
                                    </p>
                                </div>
                            </div>

                            <h4 className="font-semibold mt-4 mb-2">Schedule Change</h4>
                            <div className="bg-gray-50 p-4 rounded-xl border border-gray-200 space-y-3">
                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input type="radio" name="schedule" className="text-blue-600" />
                                    <div>
                                        <span className="block font-medium text-gray-900">Immediate</span>
                                        <span className="text-xs text-gray-500">Apply now (Reboot immediately)</span>
                                    </div>
                                </label>
                                <label className="flex items-center gap-3 cursor-pointer">
                                    <input type="radio" name="schedule" className="text-blue-600" defaultChecked />
                                    <div>
                                        <span className="block font-medium text-gray-900">Maintenance Window</span>
                                        <span className="text-xs text-gray-500">Next window: Sunday 03:00 UTC</span>
                                    </div>
                                </label>
                            </div>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="text-center py-10 space-y-6 animate-fadeIn">
                            <div className="inline-block p-4 bg-purple-100 rounded-full">
                                <FiClock className="w-12 h-12 text-purple-600" />
                            </div>
                            <div>
                                <h3 className="text-2xl font-bold text-gray-900 mb-2">Confirm Scheduled Change</h3>
                                <p className="text-gray-600 max-w-lg mx-auto">
                                    You are scheduling the removal of Multi-AZ for <strong>{selectedResources.length} instances</strong>.
                                    Changes will apply during the next maintenance window.
                                </p>
                            </div>
                            <div className="flex justify-center gap-8 py-4">
                                <div className="text-center">
                                    <div className="text-3xl font-bold text-green-600">${totalSavings.toFixed(0)}</div>
                                    <div className="text-xs text-gray-500 uppercase tracking-wide">Monthly Savings</div>
                                </div>
                                <div className="text-center">
                                    <div className="text-3xl font-bold text-gray-900">{selectedResources.length}</div>
                                    <div className="text-xs text-gray-500 uppercase tracking-wide">Databases</div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-8 py-6 border-t border-gray-100 flex justify-end gap-3 bg-gray-50 rounded-b-2xl">
                    <Button variant="ghost" onClick={onClose}>Cancel</Button>
                    <Button variant="primary" onClick={handleNext}>
                        {step === 3 ? 'Schedule Changes' : 'Next Step'}
                    </Button>
                </div>
            </div>
        </div>
    );
};

export default RDSWizard;
