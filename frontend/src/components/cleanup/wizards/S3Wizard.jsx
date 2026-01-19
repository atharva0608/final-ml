import React, { useState } from 'react';
import { FiX, FiCheckCircle, FiArchive, FiBarChart2, FiArrowRight, FiDatabase } from 'react-icons/fi';
import Button from '../../shared/Button';

const S3Wizard = ({
    isOpen,
    onClose,
    selectedResources = []
}) => {
    const [step, setStep] = useState(1);
    const [analyzing, setAnalyzing] = useState(false);

    if (!isOpen) return null;

    const totalSavings = selectedResources.reduce((acc, r) => acc + (r.cost_per_month || 0), 0);

    const handleNext = () => {
        if (step === 2) { // Simulate analysis on step 2
            setAnalyzing(true);
            setTimeout(() => {
                setAnalyzing(false);
                setStep(3);
            }, 1000);
        } else if (step < 4) {
            setStep(step + 1);
        } else {
            onClose();
        }
    };

    return (
        <div className="fixed inset-0 bg-gray-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[700px] flex flex-col">
                {/* Header */}
                <div className="px-8 py-6 border-b border-gray-100 flex justify-between items-center">
                    <div>
                        <h2 className="text-xl font-bold text-gray-900">S3 Lifecycle Optimization</h2>
                        <p className="text-sm text-gray-500">Step {step} of 4</p>
                    </div>
                    <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
                        <FiX className="w-6 h-6" />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8">
                    {step === 1 && (
                        <div className="space-y-6 animate-fadeIn">
                            <div className="text-center py-8">
                                <h3 className="text-lg font-semibold">Select Buckets to Optimize</h3>
                                <p className="text-gray-500">Showing {selectedResources.length} buckets without active lifecycle policies</p>
                            </div>
                            {/* Bucket Grid */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {selectedResources.map(r => (
                                    <div key={r.id} className="p-4 border border-blue-500 bg-blue-50 rounded-xl flex items-center gap-4 cursor-pointer hover:border-blue-300">
                                        <div className="p-3 bg-white rounded-lg border border-gray-100 shadow-sm">
                                            <FiDatabase className="w-6 h-6 text-gray-400" />
                                        </div>
                                        <div className="flex-1">
                                            <h4 className="font-medium text-gray-900 truncate" title={r.id}>{r.id}</h4>
                                            <p className="text-xs text-gray-500">
                                                {(r.metadata?.SizeBytes ? (r.metadata.SizeBytes / (1024 ** 3)).toFixed(2) : '0')} GB • Standard
                                            </p>
                                        </div>
                                        <div className="text-right">
                                            <span className="block font-bold text-green-600">-${r.cost_per_month?.toFixed(2) || '0.00'}/mo</span>
                                            <span className="text-xs text-gray-400">Potential Savings</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {step === 2 && (
                        <div className="flex flex-col items-center justify-center h-full text-center animate-fadeIn">
                            {!analyzing ? (
                                <>
                                    <div className="w-20 h-20 bg-blue-100 rounded-full flex items-center justify-center mb-6">
                                        <FiBarChart2 className="w-10 h-10 text-blue-600" />
                                    </div>
                                    <h3 className="text-xl font-bold text-gray-900">Analyze Access Patterns</h3>
                                    <p className="text-gray-600 max-w-md mt-2 mb-8">
                                        We'll analyze object access frequency to recommend the optimal storage class tiering for each bucket.
                                    </p>
                                    <div className="bg-gray-50 p-6 rounded-xl border border-gray-200 w-full max-w-md text-left">
                                        <h4 className="font-medium text-gray-900 mb-2">Analysis Scope</h4>
                                        <ul className="space-y-2 text-sm text-gray-600">
                                            <li className="flex items-center"><FiCheckCircle className="mr-2 text-green-500" /> {selectedResources.length} Buckets Selected</li>
                                            <li className="flex items-center"><FiCheckCircle className="mr-2 text-green-500" /> Check last 90 days access</li>
                                            <li className="flex items-center"><FiCheckCircle className="mr-2 text-green-500" /> Evaluate transition costs</li>
                                        </ul>
                                    </div>
                                </>
                            ) : (
                                <div className="space-y-4">
                                    <div className="w-16 h-16 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
                                    <h3 className="font-medium text-gray-900">Analyzing Access Patterns...</h3>
                                    <p className="text-sm text-gray-500">Scanning metadata...</p>
                                </div>
                            )}
                        </div>
                    )}

                    {step === 3 && (
                        <div className="space-y-6 animate-fadeIn">
                            <h3 className="text-lg font-semibold">Configure Lifecycle Policy</h3>

                            {/* Visual Timeline Builder Placeholder */}
                            <div className="bg-gray-50 rounded-xl p-8 border border-gray-200 relative">
                                <div className="h-1 bg-gray-300 w-full absolute top-12 left-0 right-0 z-0"></div>
                                <div className="flex justify-between relative z-10">
                                    {/* Stage 1 */}
                                    <div className="flex flex-col items-center">
                                        <div className="w-4 h-4 rounded-full bg-blue-600 mb-2"></div>
                                        <span className="font-bold text-gray-900">Standard</span>
                                        <span className="text-xs text-gray-500">Day 0</span>
                                    </div>
                                    {/* Stage 2 */}
                                    <div className="flex flex-col items-center">
                                        <div className="w-8 h-8 rounded-full bg-white border-2 border-blue-600 flex items-center justify-center mb-2 shadow-sm cursor-grab">
                                            <span className="text-xs font-bold text-blue-600">30</span>
                                        </div>
                                        <span className="font-bold text-gray-900">Infrequent Access</span>
                                        <span className="text-xs text-green-600">Save 40%</span>
                                    </div>
                                    {/* Stage 3 */}
                                    <div className="flex flex-col items-center">
                                        <div className="w-8 h-8 rounded-full bg-white border-2 border-blue-600 flex items-center justify-center mb-2 shadow-sm cursor-grab">
                                            <span className="text-xs font-bold text-blue-600">90</span>
                                        </div>
                                        <span className="font-bold text-gray-900">Glacier</span>
                                        <span className="text-xs text-green-600">Save 80%</span>
                                    </div>
                                    {/* Stage 4 */}
                                    <div className="flex flex-col items-center opacity-50">
                                        <div className="w-4 h-4 rounded-full bg-gray-400 mb-2"></div>
                                        <span className="font-bold text-gray-500">Expire</span>
                                        <span className="text-xs text-gray-400">Never</span>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 flex justify-between items-center">
                                <div>
                                    <p className="font-medium text-blue-900">Projected Annual Savings</p>
                                    <p className="text-xs text-blue-700">Based on moving items to cooler tiers</p>
                                </div>
                                <div className="text-2xl font-bold text-blue-700">${(totalSavings * 12).toFixed(2)}</div>
                            </div>
                        </div>
                    )}

                    {step === 4 && (
                        <div className="space-y-6 animate-fadeIn text-center py-8">
                            <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
                                <FiArchive className="w-10 h-10 text-green-600" />
                            </div>
                            <h3 className="text-2xl font-bold text-gray-900">Ready to Apply Policies</h3>
                            <p className="text-gray-600 max-w-md mx-auto mb-6">
                                3 lifecycle policies will be applied to 3 buckets. Changes typically take 24-48 hours to begin transitioning objects.
                            </p>
                            <div className="bg-amber-50 rounded-lg p-4 border border-amber-200 text-left max-w-md mx-auto">
                                <h4 className="flex items-center text-amber-800 font-medium mb-1">
                                    <FiAlertTriangle className="mr-2" /> Note on retrieval costs
                                </h4>
                                <p className="text-xs text-amber-700">
                                    Ensure these objects are rarely accessed. Retrieving from Glacier incurs a cost and delay.
                                </p>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-8 py-6 border-t border-gray-100 flex justify-end gap-3 bg-gray-50 rounded-b-2xl">
                    <Button variant="ghost" onClick={onClose} disabled={analyzing}>Cancel</Button>
                    <Button variant="primary" onClick={handleNext} disabled={analyzing}>
                        {analyzing ? 'Analyzing...' : step === 4 ? 'Apply Policies' : 'Next Step'}
                    </Button>
                </div>
            </div>
        </div>
    );
};

export default S3Wizard;
