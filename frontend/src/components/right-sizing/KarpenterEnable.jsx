import React, { useState } from 'react';
import { FiZap, FiCpu, FiDollarSign, FiRefreshCw, FiCheck, FiAlertCircle, FiArrowRight } from 'react-icons/fi';
import { Card, Button } from '../shared';
import KarpenterSetup from './KarpenterSetup';

/**
 * KarpenterEnable — Landing page that leads into the Setup Wizard.
 *
 * Props:
 *   onComplete – () => void  (called after successful enablement)
 *   onCancel   – () => void  (called when user cancels)
 */
const KarpenterEnable = ({ onComplete, onCancel }) => {
    const [showWizard, setShowWizard] = useState(false);

    if (showWizard) {
        return (
            <KarpenterSetup
                onComplete={onComplete}
                onCancel={() => setShowWizard(false)}
            />
        );
    }

    return (
        <div className="space-y-6 max-w-5xl mx-auto pb-10">
            {/* Hero Card */}
            <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-2xl p-8 text-white shadow-xl relative overflow-hidden">
                <div className="absolute top-0 right-0 p-12 opacity-10">
                    <FiZap className="w-64 h-64 transform rotate-12" />
                </div>

                <div className="relative z-10 max-w-2xl">
                    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/20 text-blue-50 text-xs font-medium mb-4 backdrop-blur-sm border border-white/20">
                        <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse"></span>
                        New: Safe Mode Available
                    </div>
                    <h2 className="text-3xl font-bold mb-4 tracking-tight">
                        Automate Right-Sizing with Karpenter
                    </h2>
                    <p className="text-blue-100 text-lg mb-8 leading-relaxed">
                        Eliminate waste by letting Karpenter automatically provision the perfect instance types for your pods.
                        Handles spot interruptions, consolidation, and scaling in real-time.
                    </p>
                    <div className="flex gap-4">
                        <button
                            onClick={() => setShowWizard(true)}
                            className="px-6 py-3 bg-white text-blue-600 rounded-lg font-bold hover:bg-blue-50 transition-colors shadow-lg flex items-center gap-2"
                        >
                            Start Setup Wizard <FiArrowRight className="w-4 h-4" />
                        </button>
                        <button
                            onClick={onCancel}
                            className="px-6 py-3 bg-blue-700/50 text-white border border-white/20 rounded-lg font-medium hover:bg-blue-700 transition-colors backdrop-blur-sm"
                        >
                            Maybe Later
                        </button>
                    </div>
                </div>
            </div>

            {/* Value Props */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <Card className="!p-6 border-t-4 border-t-green-500 hover:shadow-md transition-shadow">
                    <div className="w-12 h-12 bg-green-50 rounded-xl flex items-center justify-center mb-4">
                        <FiDollarSign className="w-6 h-6 text-green-600" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-2">50% Lower Costs</h3>
                    <p className="text-sm text-gray-500 mb-4">Aggressively uses Spot instances and cheaper generations (Graviton) without safe-guards.</p>
                    <ul className="space-y-2 text-sm text-gray-600">
                        <li className="flex gap-2"><FiCheck className="text-green-500 mt-0.5" /> <span>Spot interruption handling</span></li>
                        <li className="flex gap-2"><FiCheck className="text-green-500 mt-0.5" /> <span>Heterogeneous instances</span></li>
                    </ul>
                </Card>

                <Card className="!p-6 border-t-4 border-t-blue-500 hover:shadow-md transition-shadow">
                    <div className="w-12 h-12 bg-blue-50 rounded-xl flex items-center justify-center mb-4">
                        <FiCpu className="w-6 h-6 text-blue-600" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-2">High Performance</h3>
                    <p className="text-sm text-gray-500 mb-4">Ensures pods always have resources. Removes pending pods in milliseconds, not minutes.</p>
                    <ul className="space-y-2 text-sm text-gray-600">
                        <li className="flex gap-2"><FiCheck className="text-green-500 mt-0.5" /> <span>JIT Provisioning</span></li>
                        <li className="flex gap-2"><FiCheck className="text-green-500 mt-0.5" /> <span>Respects all constraints</span></li>
                    </ul>
                </Card>

                <Card className="!p-6 border-t-4 border-t-purple-500 hover:shadow-md transition-shadow">
                    <div className="w-12 h-12 bg-purple-50 rounded-xl flex items-center justify-center mb-4">
                        <FiRefreshCw className="w-6 h-6 text-purple-600" />
                    </div>
                    <h3 className="text-lg font-semibold text-gray-900 mb-2">Zero Maintenance</h3>
                    <p className="text-sm text-gray-500 mb-4">Set it and forget it. Nodes scale up and down, and rotate automatically to stay fresh.</p>
                    <ul className="space-y-2 text-sm text-gray-600">
                        <li className="flex gap-2"><FiCheck className="text-green-500 mt-0.5" /> <span>Auto-consolidation</span></li>
                        <li className="flex gap-2"><FiCheck className="text-green-500 mt-0.5" /> <span>AMI Upgrades</span></li>
                    </ul>
                </Card>
            </div>

            {/* How It Works Strip */}
            <div className="border border-gray-200 rounded-xl bg-gray-50 p-6">
                <h4 className="font-semibold text-gray-900 mb-4 text-center">How Deployment Works</h4>
                <div className="flex flex-col md:flex-row items-center justify-between gap-4 text-sm relative">
                    {/* Connecting line (desktop only) */}
                    <div className="hidden md:block absolute top-1/2 left-0 w-full h-0.5 bg-gray-200 -z-10 transform -translate-y-1/2"></div>

                    {[
                        { step: 1, title: 'Select Clusters', desc: 'Choose target' },
                        { step: 2, title: 'Set Strategy', desc: 'Balanced or Aggressive' },
                        { step: 3, title: 'Validation', desc: 'Dry-run check' },
                        { step: 4, title: 'Active', desc: 'Continuous optim.' }
                    ].map((s, i) => (
                        <div key={i} className="flex flex-col items-center bg-gray-50 px-4 z-10">
                            <div className="w-8 h-8 rounded-full bg-white border-2 border-blue-500 text-blue-600 font-bold flex items-center justify-center mb-2 shadow-sm">
                                {s.step}
                            </div>
                            <span className="font-medium text-gray-900">{s.title}</span>
                            <span className="text-gray-500 text-xs">{s.desc}</span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
};

export default KarpenterEnable;
