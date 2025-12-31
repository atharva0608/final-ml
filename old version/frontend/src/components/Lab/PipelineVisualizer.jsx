import React from 'react';
import { ArrowRight, Database, Filter, BoxSelect, Scale, BrainCircuit, Zap } from 'lucide-react';
import { cn } from '../../lib/utils';
import { motion } from 'framer-motion';

const PipelineBlock = ({ icon: Icon, label, status, isBeta }) => {
    // Status: 'active', 'bypassed', 'processing'

    const isBypassed = status === 'bypassed';
    const isActive = status === 'active';
    const isProcessing = status === 'processing';

    return (
        <div className="flex flex-col items-center relative group">
            <div className={cn(
                "w-16 h-16 rounded-xl flex items-center justify-center border-2 transition-all duration-500 relative z-10",
                isActive ? "bg-white border-emerald-500 text-emerald-600 shadow-lg shadow-emerald-100" : "",
                isBypassed ? "bg-slate-50 border-slate-200 text-slate-400" : "",
                isProcessing ? "bg-purple-50 border-purple-500 text-purple-600 shadow-lg shadow-purple-100" : ""
            )}>
                {/* Bypassed Cross Line */}
                {isBypassed && (
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                        <div className="w-full h-0.5 bg-slate-300 rotate-45 transform scale-75" />
                    </div>
                )}

                {/* Pulse Effect for Processing */}
                {isProcessing && (
                    <span className="absolute inline-flex h-full w-full rounded-xl bg-purple-400 opacity-20 animate-ping"></span>
                )}

                <Icon className={cn("w-7 h-7", isBypassed && "opacity-50")} />
            </div>

            <span className={cn(
                "mt-3 text-xs font-bold uppercase tracking-wide transition-colors",
                isActive ? "text-emerald-600" : "",
                isBypassed ? "text-slate-400 line-through decoration-slate-300" : "",
                isProcessing ? "text-purple-600" : "text-slate-500"
            )}>
                {label}
            </span>

            {/* Tooltip for Beta */}
            {isProcessing && isBeta && (
                <div className="absolute -top-10 bg-purple-600 text-white text-[10px] px-2 py-1 rounded font-bold shadow-lg animate-bounce">
                    Using v2.1-Beta
                </div>
            )}
        </div>
    );
};

const Connector = ({ active }) => (
    <div className="flex-1 h-0.5 mx-2 relative">
        <div className="absolute inset-0 bg-slate-800" />
        {active && (
            <motion.div
                className="absolute inset-0 bg-emerald-500"
                initial={{ width: 0 }}
                animate={{ width: "100%" }}
                transition={{ duration: 1.5, repeat: Infinity }}
            />
        )}
    </div>
);

const PipelineVisualizer = ({ activeModel }) => {
    const isBeta = activeModel.includes('Beta');

    return (
        <div className="bg-white border border-slate-200 rounded-xl p-8 shadow-sm">
            <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wider mb-8 flex items-center">
                <BrainCircuit className="w-4 h-4 mr-2 text-purple-600" />
                Active Inference Pipeline Topology
            </h3>

            <div className="flex items-center justify-between relative">
                {/* Connection Line */}
                <div className="absolute top-8 left-0 w-full h-0.5 bg-slate-100 -z-0"></div>

                <PipelineBlock icon={Database} label="Ingestion" status="active" />

                <ArrowRight className="text-slate-300 w-5 h-5 relative z-10" />

                <PipelineBlock icon={Filter} label="Pre-Process" status="active" />

                <ArrowRight className="text-slate-300 w-5 h-5 relative z-10" />

                {/* 3. Bin Packing (Skipped in Single Mode) */}
                <PipelineBlock icon={BoxSelect} label="Bin Packing" status="bypassed" />

                <ArrowRight className="text-slate-300 w-5 h-5 relative z-10" />

                {/* 4. Right Sizing (Skipped in Single Mode) */}
                <PipelineBlock icon={Scale} label="Right Sizing" status="bypassed" />

                <ArrowRight className="text-slate-300 w-5 h-5 relative z-10" />

                {/* 5. ML Inference */}
                <PipelineBlock
                    icon={BrainCircuit}
                    label="ML Inference"
                    status={isBeta ? "processing" : "active"}
                    isBeta={isBeta}
                />

                <ArrowRight className="text-slate-300 w-5 h-5 relative z-10" />

                {/* 6. Switch Execution */}
                <PipelineBlock icon={Zap} label="Switch Exec" status="active" />
            </div>

            {/* Logic Explanation Footer */}
            <div className="mt-8 bg-slate-50 border border-slate-200 rounded-lg p-4 text-xs text-slate-500 flex items-start space-x-3">
                <div className="p-1 bg-blue-50 text-blue-600 rounded">
                    <BrainCircuit className="w-4 h-4" />
                </div>
                <div>
                    <span className="font-bold text-slate-900 block mb-1">Pipeline Logic:</span>
                    {isBeta
                        ? "Currently running EXPERIMENTAL single-instance logic. Bin-packing and Right-sizing algorithms are strictly bypassed to isolate model variables."
                        : "Running STANDARD production pipeline. Note: Single-instance targets automatically bypass aggregation steps."
                    }
                </div>
            </div>
        </div>
    );
};

export default PipelineVisualizer;
