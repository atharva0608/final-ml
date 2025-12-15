import React, { useState } from 'react';
import { UploadCloud, AlertOctagon, RefreshCw, CheckCircle2 } from 'lucide-react';
import { cn } from '../lib/utils';

const Controls = () => {
    const [isDragging, setIsDragging] = useState(false);
    const [showConfirm, setShowConfirm] = useState(false);

    return (
        <div className="space-y-6 max-w-4xl mx-auto">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 mb-2">System Controls</h1>
                <p className="text-slate-500">Manual overrides and model management</p>
            </div>

            {/* Sandbox Operations */}
            <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-6 shadow-sm flex items-center justify-between relative overflow-hidden group">
                <div className="absolute inset-0 bg-[radial-gradient(#eab308_1px,transparent_1px)] [background-size:16px_16px] opacity-10 pointer-events-none" />
                <div className="relative z-10 flex items-center space-x-4">
                    <div className="p-3 bg-yellow-100 rounded-lg text-yellow-700">
                        <AlertOctagon className="w-6 h-6" />
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-slate-900 flex items-center">
                            Test Flight Mode
                            <span className="ml-2 text-[10px] bg-yellow-200 text-yellow-800 px-2 py-0.5 rounded-full uppercase tracking-wider font-bold">Simulator</span>
                        </h2>
                        <p className="text-sm text-slate-600 max-w-md">Launch a safe, isolated environment to test simulated scenarios without affecting production.</p>
                    </div>
                </div>
                <button
                    onClick={() => window.location.href = '/sandbox'}
                    className="relative z-10 px-6 py-2 bg-yellow-500 hover:bg-yellow-400 text-black font-bold rounded-lg shadow-sm border border-yellow-600 uppercase tracking-wider text-sm transition-all hover:scale-105"
                >
                    Enter Simulator
                </button>
            </div>

            {/* Model Upload Zone */}
            <div className="bg-white border border-slate-200 rounded-xl p-8 shadow-sm">
                <h2 className="text-lg font-bold text-slate-900 mb-1">Model Registry</h2>
                <p className="text-sm text-slate-500 mb-6">Upload new .pkl model artifacts to the decision engine</p>

                <div
                    className={cn(
                        "border-2 border-dashed rounded-xl p-12 flex flex-col items-center justify-center text-center transition-all duration-200 cursor-pointer",
                        isDragging ? "border-blue-500 bg-blue-50/50 scale-[0.99]" : "border-slate-300 hover:border-slate-400 bg-slate-50/50"
                    )}
                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={(e) => { e.preventDefault(); setIsDragging(false); }}
                >
                    <div className="p-4 bg-white rounded-full shadow-sm mb-4">
                        <UploadCloud className="w-8 h-8 text-blue-600" />
                    </div>
                    <h3 className="text-lg font-semibold text-slate-900 mb-1">Upload Model Artifact</h3>
                    <p className="text-slate-500 text-sm mb-4">Drag and drop .pkl files here, or click to browse</p>
                    <button className="px-4 py-2 bg-white border border-slate-300 rounded-lg text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm">
                        Select Files
                    </button>
                </div>
            </div>

            {/* System Actions */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm flex flex-col justify-between">
                    <div>
                        <div className="flex items-center space-x-2 text-emerald-600 mb-4">
                            <RefreshCw className="w-5 h-5" />
                            <span className="font-semibold">Force Rebalance</span>
                        </div>
                        <p className="text-sm text-slate-600 mb-6">Trigger an immediate re-evaluation of the entire fleet. This may cause instance interruptions.</p>
                    </div>
                    <button className="w-full py-2.5 bg-white border border-slate-300 text-slate-700 font-medium rounded-lg hover:bg-slate-50 transition-colors shadow-sm">
                        Trigger Rebalance
                    </button>
                </div>

                <div className="bg-red-50 border border-red-100 rounded-xl p-6 shadow-sm flex flex-col justify-between relative overflow-visible">
                    <div className="absolute top-0 right-0 p-32 bg-red-100 rounded-full blur-3xl opacity-20 -mr-16 -mt-16 pointer-events-none"></div>
                    <div>
                        <div className="flex items-center space-x-2 text-red-700 mb-4">
                            <AlertOctagon className="w-6 h-6" />
                            <span className="font-bold">Emergency Fallback</span>
                        </div>
                        <p className="text-sm text-red-800 mb-6">
                            IMMEDIATELY stop all spot requests and revert to On-Demand. Use only in critical outages.
                        </p>
                    </div>

                    {/* Confirmation State */}
                    {showConfirm ? (
                        <div className="absolute inset-0 bg-white/95 backdrop-blur-sm z-20 flex flex-col items-center justify-center p-6 text-center animate-in fade-in duration-200 rounded-xl">
                            <AlertOctagon className="w-8 h-8 text-red-600 mb-2 animate-bounce" />
                            <h3 className="text-lg font-bold text-slate-900 mb-1">Confirm Emergency?</h3>
                            <p className="text-xs text-slate-500 mb-4">This action can increase costs by up to 60%.</p>
                            <div className="flex space-x-3 w-full">
                                <button
                                    onClick={() => { console.log("GLOBAL FALLBACK"); setShowConfirm(false); }}
                                    className="flex-1 py-2 bg-red-600 text-white font-bold rounded shadow hover:bg-red-700"
                                >
                                    CONFIRM
                                </button>
                                <button
                                    onClick={() => setShowConfirm(false)}
                                    className="flex-1 py-2 bg-slate-100 text-slate-600 font-bold rounded hover:bg-slate-200"
                                >
                                    CANCEL
                                </button>
                            </div>
                        </div>
                    ) : (
                        <button
                            onClick={() => setShowConfirm(true)}
                            className="w-full py-2.5 bg-red-600 text-white font-bold rounded-lg hover:bg-red-700 transition-colors shadow-sm border border-red-700 relative z-10"
                        >
                            ACTIVATE FALLBACK
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Controls;
