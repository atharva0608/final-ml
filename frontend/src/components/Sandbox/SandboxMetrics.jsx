import React from 'react';
import { DollarSign } from 'lucide-react';

const SandboxMetrics = ({ savings }) => {
    return (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6 flex flex-col items-center justify-center text-center relative overflow-hidden">
            {/* Background Glow */}
            <div className="absolute inset-0 bg-emerald-500/5 blur-3xl" />

            <h3 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1 relative z-10">Projected Annual Savings</h3>
            <div className="text-3xl font-bold text-white font-mono flex items-center relative z-10">
                <span className="text-emerald-500 mr-1">$</span>
                {savings.toFixed(2)}
            </div>

            <p className="text-[10px] text-emerald-400 mt-2 font-bold px-2 py-1 bg-emerald-950/50 rounded-full border border-emerald-900/50">
                +420% Efficiency
            </p>
        </div>
    );
};

export default SandboxMetrics;
