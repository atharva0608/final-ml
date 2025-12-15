import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import SandboxLayout from './SandboxLayout';
import BlueGreenVisualizer from './BlueGreenVisualizer';
import MatrixTerminal from './MatrixTerminal';
import SimulationControls from './SimulationControls';
import SandboxMetrics from './SandboxMetrics';
import SandboxSetup from './SandboxSetup';

const SandboxDashboard = () => {
    const navigate = useNavigate();
    const [isSetupOpen, setIsSetupOpen] = useState(true);
    const [sessionActive, setSessionActive] = useState(false);
    const [systemState, setSystemState] = useState('idle'); // idle, switching, stable
    const [logs, setLogs] = useState([{ time: new Date().toLocaleTimeString(), prefix: 'SYSTEM', message: 'Sandbox Initialized. Waiting for Target...', color: 'text-slate-500' }]);
    const [savings, setSavings] = useState(0);

    const addLog = (prefix, message, color = 'text-green-500') => {
        setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), prefix, message, color }]);
    };

    const handleLaunch = (target) => {
        setIsSetupOpen(false);
        setSessionActive(true);
        addLog('SANDBOX', `Target Acquired: ${target}`, 'text-yellow-500');
        addLog('MONITOR', 'Monitoring Price Feed for us-east-1...', 'text-blue-400');
    };

    const handleEject = () => {
        if (confirm("End Sandbox Session? All simulated instances will be terminated.")) {
            setSessionActive(false);
            navigate('/client'); // Return to main dashboard
        }
    };

    const handleTriggerSwap = () => {
        if (systemState !== 'idle') return;

        addLog('OVERRIDE', 'User initiated FORCE_PRICE_DROP', 'text-pink-500');
        setSystemState('switching');

        // Sequence of events
        setTimeout(() => addLog('LOGIC', 'Detected Spot Price $0.024 < $0.096 (75% Delta)', 'text-blue-300'), 500);
        setTimeout(() => addLog('ACTION', 'Provisioning Spot Candidate i-spot-01...', 'text-yellow-400'), 1500);
        setTimeout(() => addLog('NETWORK', 'Draining connections from Original...', 'text-slate-400'), 3500);
        setTimeout(() => {
            setSystemState('stable');
            addLog('SUCCESS', 'Traffic Switched to Spot Instance.', 'text-green-400 font-bold');
            setSavings(350.40);
        }, 5000);
    };

    const handleReset = () => {
        addLog('OVERRIDE', 'Simulating Price Spike / Interruption...', 'text-red-400');
        setSystemState('idle');
        setSavings(0);
        addLog('ACTION', 'Fallback Triggered. Reverting to On-Demand.', 'text-red-300');
    };

    // If setup is open, show strictly setup or redirect

    return (
        <>
            {isSetupOpen && (
                <SandboxSetup
                    onLaunch={handleLaunch}
                    onCancel={() => navigate('/client')}
                />
            )}

            {sessionActive && (
                <SandboxLayout onEject={handleEject}>
                    <div className="grid grid-cols-12 gap-6 h-full">
                        {/* LEFT COLUMN: Visualizer (8 cols) */}
                        <div className="col-span-12 lg:col-span-8 h-full min-h-[500px]">
                            <BlueGreenVisualizer state={systemState} />
                        </div>

                        {/* RIGHT COLUMN: Controls & Logs (4 cols) */}
                        <div className="col-span-12 lg:col-span-4 flex flex-col space-y-6">

                            {/* Metrics */}
                            <SandboxMetrics savings={savings} />

                            {/* Controls */}
                            <SimulationControls
                                onTriggerSwap={handleTriggerSwap}
                                onSimulateInterruption={handleReset}
                                onSimulateFailure={() => addLog('ERROR', 'Simulated Health Check Failure!', 'text-red-600')}
                                disabled={systemState === 'switching'}
                            />

                            {/* Terminal */}
                            <div className="flex-1 min-h-0">
                                <MatrixTerminal logs={logs} />
                            </div>
                        </div>
                    </div>
                </SandboxLayout>
            )}
        </>
    );
};

export default SandboxDashboard;
