import React, { useState } from 'react';
import { FiX, FiCheckCircle, FiTrendingUp, FiAlertTriangle, FiArrowRight, FiDollarSign } from 'react-icons/fi';
import Button from '../../shared/Button';

const RIWizard = ({
    isOpen,
    onClose,
    selectedResources = []
}) => {
    const [step, setStep] = useState(1);
    const [analyzing, setAnalyzing] = useState(false);

    if (!isOpen) return null;

    // Wizard Steps
    // 1. Analysis (Why are they wasted?)
    // 2. Recommendations
    // 3. Execution Plan

    const totalWaste = selectedResources.reduce((acc, r) => acc + (r.cost_per_month || 0), 0);

    const handleNext = () => {
        if (step === 1) {
            setAnalyzing(true);
            setTimeout(() => {
                setAnalyzing(false);
                setStep(2);
            }, 1000);
        } else if (step < 3) {
            setStep(step + 1);
        } else {
            onClose(); // In real app, trigger execute
        }
    };

    return (
        <div className="fixed inset-0 bg-gray-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl h-[600px] flex flex-col">
                {/* Header */}
                <div className="px-8 py-6 border-b border-gray-100 flex justify-between items-center">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900">RI Optimization Wizard</h2>
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
                            <div className="bg-blue-50 p-4 rounded-xl border border-blue-100 flex gap-4">
                                <div className="bg-blue-200 p-2 rounded-lg h-fit">
                                    <FiTrendingUp className="text-blue-700 w-6 h-6" />
                                </div>
                                <div className="flex-1">
                                    <h3 className="font-semibold text-blue-900">Analysis Summary</h3>
                                    <p className="text-sm text-blue-700 mt-1">
                                        You selected {selectedResources.length} RIs that are underutilized.
                                        Total wasted spend is estimated at <span className="font-bold">${totalWaste.toFixed(2)}/mo</span>.
                                    </p>
                                </div>
                            </div>

                            <h3 className="text-lg font-semibold top-6">Selected Resources</h3>
                            <div className="border rounded-xl overflow-hidden">
                                <table className="min-w-full divide-y divide-gray-200">
                                    <thead className="bg-gray-50 text-xs text-gray-500 uppercase">
                                        <tr>
                                            <th className="px-4 py-3 text-left">RI ID</th>
                                            <th className="px-4 py-3 text-left">Utilization</th>
                                            <th className="px-4 py-3 text-left">Waste / Mo</th>
                                        </tr>
                                    </thead>
                                    <tbody className="bg-white divide-y divide-gray-200">
                                        {selectedResources.map(r => (
                                            <tr key={r.id}>
                                                <td className="px-4 py-3 font-mono text-sm">{r.id}</td>
                                                <td className="px-4 py-3">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-24 bg-gray-200 rounded-full h-2">
                                                            <div className="bg-red-500 h-2 rounded-full" style={{ width: '10%' }}></div>
                                                        </div>
                                                        <span className="text-xs font-bold text-red-600">Low</span>
                                                    </div>
                                                </td>
                                                <td className="px-4 py-3 text-sm font-medium">${r.cost_per_month.toFixed(2)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="space-y-6 animate-fadeIn">
                            <h3 className="text-lg font-semibold">Recommendations</h3>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="border border-green-200 bg-green-50 p-5 rounded-xl cursor-pointer hover:shadow-md transition-shadow ring-2 ring-green-500">
                                    <div className="flex justify-between items-start mb-2">
                                        <h4 className="font-bold text-green-900">List on Marketplace</h4>
                                        <FiCheckCircle className="text-green-600 w-5 h-5" />
                                    </div>
                                    <p className="text-sm text-green-800 mb-4">
                                        Recover cost by selling unused Standard RIs. Estimated recovery: ${(totalWaste * 0.8).toFixed(2)}.
                                    </p>
                                    <div className="text-xs font-mono bg-white/50 p-2 rounded text-green-800">
                                        Potential Net: +${(totalWaste * 0.8).toFixed(2)}
                                    </div>
                                </div>

                                <div className="border border-gray-200 p-5 rounded-xl cursor-pointer hover:shadow-md transition-shadow opacity-60">
                                    <h4 className="font-bold text-gray-900">Convert / Modify</h4>
                                    <p className="text-sm text-gray-600 mb-4">
                                        Convert to different instance family. (Not available for Standard RIs).
                                    </p>
                                </div>
                            </div>
                        </div>
                    )}

                    {step === 3 && (
                        <div className="space-y-6 animate-fadeIn text-center py-8">
                            <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mx-auto mb-6">
                                <FiArrowRight className="w-10 h-10 text-blue-600" />
                            </div>
                            <h3 className="text-2xl font-bold text-gray-900">Ready to Execute</h3>
                            <p className="text-gray-600 max-w-md mx-auto">
                                This will create {selectedResources.length} marketplace listings. Updates may take up to 15 minutes to reflect in AWS Console.
                            </p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-8 py-6 border-t border-gray-100 flex justify-end gap-3 bg-gray-50 rounded-b-2xl">
                    <Button variant="ghost" onClick={onClose} disabled={analyzing}>Cancel</Button>
                    <Button variant="primary" onClick={handleNext} disabled={analyzing}>
                        {analyzing ? 'Analyzing...' : step === 3 ? 'Execute Plan' : 'Next Step'}
                    </Button>
                </div>
            </div>
        </div>
    );
};

export default RIWizard;
