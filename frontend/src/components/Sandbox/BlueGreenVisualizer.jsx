import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Cloud, ArrowRight, Server, Play, ShieldAlert, CheckCircle2 } from 'lucide-react';
import { cn } from '../../lib/utils';

const BlueGreenVisualizer = ({ state }) => {
    // state: 'idle' | 'switching' | 'stable' | 'reverting'

    return (
        <div className="h-full bg-slate-800/50 rounded-xl border border-slate-700 p-8 flex flex-col relative overflow-hidden">
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-8 flex items-center">
                <Server className="w-4 h-4 mr-2" />
                Live Topology Visualizer
            </h3>

            <div className="flex-1 flex items-center justify-center space-x-12 relative z-10">

                {/* INTERNET SOURCE */}
                <div className="text-center space-y-2 z-20">
                    <div className="w-16 h-16 bg-slate-700 rounded-full flex items-center justify-center border-4 border-slate-600 shadow-xl">
                        <Cloud className="w-8 h-8 text-blue-400" />
                    </div>
                    <div className="text-[10px] font-bold text-slate-500 uppercase">Traffic Source</div>
                </div>

                {/* CONNECTION LINES CONTAINER */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    {/* Line to Blue */}
                    <svg className="absolute w-full h-full" style={{ zIndex: 0 }}>
                        {/* Path to Blue (Top) */}
                        <motion.path
                            d="M 120 150 C 200 150, 250 100, 350 100"
                            fill="transparent"
                            strokeWidth="4"
                            stroke={state === 'stable' ? '#475569' : '#3b82f6'} // Gray if switched, Blue otherwise
                            strokeDasharray={state === 'stable' ? "5 5" : "0"}
                            initial={false}
                            animate={{ stroke: state === 'stable' ? '#475569' : '#3b82f6' }}
                        />
                        {/* Path to Green (Bottom) */}
                        <motion.path
                            d="M 120 150 C 200 150, 250 200, 350 200"
                            fill="transparent"
                            strokeWidth="4"
                            stroke={state === 'idle' ? 'transparent' : '#10b981'}
                            strokeDasharray={state === 'switching' ? "5 5" : "0"}
                            initial={false}
                            animate={{
                                stroke: state === 'idle' ? 'transparent' : '#10b981',
                                strokeDasharray: state === 'switching' ? "5 5" : "0"
                            }}
                        />
                        {/* Traffic Dots Animation could go here */}
                    </svg>
                </div>

                {/* TARGETS COLUMN */}
                <div className="space-y-16 pl-32 relative z-10">

                    {/* BLUE BOX (Original) */}
                    <motion.div
                        animate={{
                            scale: state === 'stable' ? 0.9 : 1,
                            opacity: state === 'stable' ? 0.5 : 1,
                            filter: state === 'stable' ? 'grayscale(100%)' : 'grayscale(0%)'
                        }}
                        className="w-64 bg-slate-900 border-l-4 border-blue-500 rounded-lg p-4 shadow-lg relative"
                    >
                        <div className="absolute top-2 right-2">
                            {state === 'stable' ? (
                                <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded uppercase font-bold">Stopped</span>
                            ) : (
                                <span className="text-[10px] bg-blue-500/20 text-blue-400 px-2 py-0.5 rounded uppercase font-bold animate-pulse">Running</span>
                            )}
                        </div>
                        <h4 className="text-blue-400 font-bold text-sm">Original (On-Demand)</h4>
                        <p className="text-slate-500 text-xs font-mono mt-1">i-0a1b2c3d (m5.large)</p>
                        <div className="mt-4 flex items-center text-xs text-slate-400">
                            <span className="font-bold mr-2">$0.096/hr</span>
                        </div>
                    </motion.div>

                    {/* GREEN BOX (Spot Candidate) */}
                    <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{
                            opacity: state === 'idle' ? 0 : 1,
                            x: state === 'idle' ? 20 : 0
                        }}
                        className="w-64 bg-slate-900 border-l-4 border-emerald-500 rounded-lg p-4 shadow-lg relative"
                    >
                        <div className="absolute top-2 right-2">
                            {state === 'switching' && (
                                <span className="text-[10px] bg-emerald-500/20 text-emerald-400 px-2 py-0.5 rounded uppercase font-bold flex items-center">
                                    <ArrowRight className="w-3 h-3 mr-1 animate-spin" /> Booting
                                </span>
                            )}
                            {state === 'stable' && (
                                <span className="text-[10px] bg-emerald-500 text-black px-2 py-0.5 rounded uppercase font-bold">Active</span>
                            )}
                        </div>
                        <h4 className="text-emerald-400 font-bold text-sm">Candidate (Spot)</h4>
                        <p className="text-slate-500 text-xs font-mono mt-1">i-spot-new (m5.large)</p>
                        <div className="mt-4 flex items-center justify-between text-xs text-slate-400">
                            <span className="font-bold text-emerald-400">$0.024/hr (-75%)</span>
                        </div>
                    </motion.div>
                </div>
            </div>
        </div>
    );
};

export default BlueGreenVisualizer;
