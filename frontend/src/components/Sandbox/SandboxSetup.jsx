import React, { useState, useEffect } from 'react';
import { Shield, Key, Server, ArrowRight, Loader2, CheckCircle } from 'lucide-react';

const SandboxSetup = ({ onLaunch, onCancel }) => {
    const [step, setStep] = useState(1); // 1: Select, 2: Generating, 3: Ready
    const [target, setTarget] = useState('');
    const [logs, setLogs] = useState([]);

    const handleGenerate = () => {
        if (!target) return;
        setStep(2);

        // Simulate generation steps
        const steps = [
            "Initializing Isolation Chamber...",
            "Cloning Instance Metadata...",
            "Provisioning Ephemeral Credentials...",
            "Establishing Secure Tunnel...",
            "Sandbox Environment Ready."
        ];

        steps.forEach((log, index) => {
            setTimeout(() => {
                setLogs(prev => [...prev, log]);
                if (index === steps.length - 1) {
                    setStep(3);
                }
            }, (index + 1) * 800);
        });
    };

    return (
        <div className="fixed inset-0 bg-slate-900/90 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-slate-900 border border-slate-700 w-full max-w-lg rounded-xl shadow-2xl overflow-hidden relative">
                {/* Header */}
                <div className="bg-slate-950 p-6 border-b border-slate-800">
                    <div className="flex items-center space-x-3 text-yellow-500 mb-2">
                        <Shield className="w-6 h-6" />
                        <h2 className="text-xl font-bold uppercase tracking-wider">Mission Setup</h2>
                    </div>
                    <p className="text-slate-400 text-sm">Configure your isolated testing environment.</p>
                </div>

                <div className="p-8 space-y-6">
                    {/* Step 1: Target Selection */}
                    {step === 1 && (
                        <div className="space-y-4 animate-in fade-in slide-in-from-right-8">
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-slate-500 uppercase tracking-widest">Select Target Instance</label>
                                <select
                                    className="w-full bg-slate-800 border border-slate-700 text-white p-3 rounded-lg focus:ring-2 focus:ring-yellow-500 outline-none transition-all"
                                    value={target}
                                    onChange={(e) => setTarget(e.target.value)}
                                >
                                    <option value="" disabled>-- Select Safe Candidate --</option>
                                    <option value="i-test-01">i-test-01 (Staging-Web) [SAFE]</option>
                                    <option value="i-test-02">i-test-02 (Dev-Worker) [SAFE]</option>
                                </select>
                            </div>
                            <div className="bg-blue-900/20 border border-blue-800 p-4 rounded-lg flex items-start space-x-3">
                                <Server className="w-5 h-5 text-blue-400 mt-0.5" />
                                <div>
                                    <h4 className="text-sm font-bold text-blue-400">Single Instance Mode</h4>
                                    <p className="text-xs text-blue-300/70 mt-1">Actions will be restricted to the selected target only. Production traffic is unaffected.</p>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Step 2: Generation Logs */}
                    {step === 2 && (
                        <div className="space-y-4 font-mono text-xs animate-in fade-in zoom-in-95">
                            <div className="flex items-center space-x-2 text-yellow-500 mb-4">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                <span className="uppercase font-bold tracking-widest">Generating Environment...</span>
                            </div>
                            <div className="bg-black p-4 rounded-lg h-48 overflow-y-auto border border-slate-800 space-y-2">
                                {logs.map((log, i) => (
                                    <div key={i} className="text-green-500 pb-1 border-b border-green-900/30 last:border-0">
                                        <span className="opacity-50 mr-2">[{new Date().toLocaleTimeString()}]</span>
                                        {log}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Step 3: Credentials & Launch */}
                    {step === 3 && (
                        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4">
                            <div className="bg-green-900/10 border border-green-800 p-4 rounded-lg flex items-center space-x-3">
                                <CheckCircle className="w-6 h-6 text-green-500" />
                                <div>
                                    <h4 className="text-sm font-bold text-green-400">Environment Ready</h4>
                                    <p className="text-xs text-green-300/70">Secure tunnel established.</p>
                                </div>
                            </div>

                            <div className="bg-slate-950 border border-dashed border-slate-700 p-4 rounded-lg space-y-3 relative group">
                                <div className="absolute -top-3 left-4 bg-slate-900 px-2 text-xs font-bold text-slate-500 uppercase">Temp Credentials</div>
                                <div className="flex justify-between items-center text-sm">
                                    <span className="text-slate-500">User:</span>
                                    <span className="font-mono text-white">admin_test_04</span>
                                </div>
                                <div className="flex justify-between items-center text-sm">
                                    <span className="text-slate-500">Pass:</span>
                                    <div className="flex items-center space-x-2">
                                        <span className="font-mono text-yellow-500 tracking-widest">••••••••</span>
                                        <button className="text-xs text-slate-600 hover:text-white uppercase font-bold">Copy</button>
                                    </div>
                                </div>
                                <div className="flex justify-between items-center text-sm">
                                    <span className="text-slate-500">Key:</span>
                                    <span className="font-mono text-slate-400 text-xs">ASIA...X7Y2</span>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer Actions */}
                <div className="bg-slate-950 p-6 border-t border-slate-800 flex justify-between items-center">
                    <button
                        onClick={onCancel}
                        className="text-slate-500 hover:text-white text-sm font-bold uppercase transition-colors"
                    >
                        Abort
                    </button>

                    {step === 1 && (
                        <button
                            onClick={handleGenerate}
                            disabled={!target}
                            className="bg-yellow-500 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-yellow-400 text-black px-6 py-2 rounded-lg text-sm font-bold uppercase tracking-widest flex items-center transition-all hover:scale-105"
                        >
                            Generate Keys
                            <Key className="w-4 h-4 ml-2" />
                        </button>
                    )}
                    {step === 3 && (
                        <button
                            onClick={() => onLaunch(target)}
                            className="bg-green-600 hover:bg-green-500 text-white px-8 py-2 rounded-lg text-sm font-bold uppercase tracking-widest flex items-center transition-all shadow-lg shadow-green-900/50 animate-pulse"
                        >
                            Launch Sandbox
                            <ArrowRight className="w-4 h-4 ml-2" />
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};

export default SandboxSetup;
