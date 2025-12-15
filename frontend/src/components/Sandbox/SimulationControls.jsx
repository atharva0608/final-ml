import React from 'react';
import { Zap, AlertOctagon, RotateCcw } from 'lucide-react';

const SimulationControls = ({ onTriggerSwap, onSimulateInterruption, onSimulateFailure, disabled }) => {
    return (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">Simulation Overrides</h3>

            <div className="space-y-3">
                <button
                    onClick={onTriggerSwap}
                    disabled={disabled}
                    className="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white text-xs font-bold uppercase py-3 rounded-lg flex items-center justify-center transition-all hover:scale-[1.02] active:scale-[0.98] shadow-lg shadow-blue-900/20"
                >
                    <Zap className="w-4 h-4 mr-2 text-yellow-300" />
                    Force Price Drop
                </button>

                <div className="grid grid-cols-2 gap-3">
                    <button
                        onClick={onSimulateInterruption}
                        disabled={disabled}
                        className="bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-200 text-[10px] font-bold uppercase py-2 rounded-lg flex items-center justify-center border border-slate-600"
                    >
                        <RotateCcw className="w-3 h-3 mr-1" />
                        Simulate Spike
                    </button>
                    <button
                        onClick={onSimulateFailure}
                        disabled={disabled}
                        className="bg-red-900/20 hover:bg-red-900/40 disabled:opacity-50 text-red-400 text-[10px] font-bold uppercase py-2 rounded-lg flex items-center justify-center border border-red-900/50"
                    >
                        <AlertOctagon className="w-3 h-3 mr-1" />
                        Force Fail
                    </button>
                </div>
            </div>
        </div>
    );
};

export default SimulationControls;
