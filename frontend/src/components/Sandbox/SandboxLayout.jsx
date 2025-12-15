import React from 'react';
import { AlertTriangle, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const SandboxLayout = ({ children, onEject }) => {
    return (
        <div className="min-h-screen bg-slate-900 flex flex-col relative overflow-hidden font-mono">
            {/* Disclaimer Overlay (Subtle Construction Pattern) */}
            <div className="absolute inset-0 pointer-events-none opacity-5"
                style={{ backgroundImage: 'repeating-linear-gradient(45deg, #000 0, #000 10px, #eab308 10px, #eab308 20px)' }}
            />

            {/* Top Hazard Banner */}
            <div className="bg-yellow-500 text-black px-4 py-2 flex items-center justify-between shadow-lg relative z-50">
                <div className="flex items-center space-x-3 font-bold uppercase tracking-widest text-sm">
                    <AlertTriangle className="w-5 h-5" />
                    <span>Sandbox Session Active</span>
                    <span className="hidden md:inline text-[10px] bg-black text-yellow-500 px-2 py-0.5 rounded opacity-80">
                        Simulation Mode
                    </span>
                </div>

                <div className="flex items-center space-x-4">
                    <div className="text-xs font-bold font-mono">
                        T-Minus: 01:59:42
                    </div>
                    <button
                        onClick={onEject}
                        className="bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded text-xs font-bold uppercase tracking-wider flex items-center transition-colors shadow-sm"
                    >
                        <LogOut className="w-3 h-3 mr-2" />
                        Eject
                    </button>
                </div>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 relative z-10 p-6 overflow-auto">
                {children}
            </div>

            {/* Footer Status */}
            <div className="bg-slate-950 border-t border-slate-800 p-2 text-[10px] text-slate-500 flex justify-between px-6 z-50">
                <span>Environment: ISOLATED_TEST_NET_V1</span>
                <span>Security Level: EPHEMERAL</span>
            </div>
        </div>
    );
};

export default SandboxLayout;
