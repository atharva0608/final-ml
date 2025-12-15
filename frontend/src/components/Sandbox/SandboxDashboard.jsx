import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import SandboxLayout from './SandboxLayout';
import BlueGreenVisualizer from './BlueGreenVisualizer';
import MatrixTerminal from './MatrixTerminal';
import SimulationControls from './SimulationControls';
import SandboxMetrics from './SandboxMetrics';
import SandboxSetup from './SandboxSetup';
import * as api from '../../services/api';

const SandboxDashboard = () => {
    const navigate = useNavigate();
    const [isSetupOpen, setIsSetupOpen] = useState(true);
    const [sessionActive, setSessionActive] = useState(false);
    const [sessionId, setSessionId] = useState(null);
    const [sessionDetails, setSessionDetails] = useState(null);
    const [systemState, setSystemState] = useState('idle'); // idle, switching, stable
    const [logs, setLogs] = useState([{
        time: new Date().toLocaleTimeString(),
        prefix: 'SYSTEM',
        message: 'Sandbox Initialized. Waiting for Target...',
        color: 'text-slate-500'
    }]);
    const [savings, setSavings] = useState(0);

    const addLog = (prefix, message, color = 'text-green-500') => {
        setLogs(prev => [...prev, { time: new Date().toLocaleTimeString(), prefix, message, color }]);
    };

    const handleLaunch = async (sessionData) => {
        try {
            addLog('SETUP', 'Creating sandbox session...', 'text-yellow-500');

            // Create session via API
            const response = await api.createSandboxSession(sessionData);

            setSessionId(response.session_id);
            setIsSetupOpen(false);
            setSessionActive(true);

            addLog('SANDBOX', `Session Created: ${response.session_id.substring(0, 8)}...`, 'text-green-400');
            addLog('SANDBOX', `Target: ${sessionData.instance_type}@${sessionData.availability_zone}`, 'text-yellow-500');
            addLog('MONITOR', `Monitoring price feed for ${sessionData.aws_region}...`, 'text-blue-400');
            addLog('CREDENTIALS', 'Ephemeral credentials active', 'text-green-500');

            // Start monitoring session
            monitorSession(response.session_id);
        } catch (error) {
            console.error('Failed to create session:', error);
            addLog('ERROR', `Failed to create session: ${error.message}`, 'text-red-500');
        }
    };

    const monitorSession = async (sessionId) => {
        try {
            const details = await api.getSandboxSession(sessionId);
            setSessionDetails(details);

            // Update time remaining periodically
            const interval = setInterval(async () => {
                const updated = await api.getSandboxSession(sessionId);
                setSessionDetails(updated);

                if (updated.time_remaining_minutes <= 0) {
                    addLog('SYSTEM', 'Session expired', 'text-red-500');
                    clearInterval(interval);
                    handleEject();
                }
            }, 60000); // Update every minute

            return () => clearInterval(interval);
        } catch (error) {
            console.error('Failed to monitor session:', error);
        }
    };

    const handleEject = async () => {
        if (!confirm("End Sandbox Session? All simulated instances will be terminated.")) {
            return;
        }

        try {
            if (sessionId) {
                await api.endSandboxSession(sessionId);
                addLog('SYSTEM', 'Session ended, cleanup initiated', 'text-yellow-500');
            }
            setSessionActive(false);
            navigate('/client'); // Return to main dashboard
        } catch (error) {
            console.error('Failed to end session:', error);
            addLog('ERROR', `Failed to end session: ${error.message}`, 'text-red-500');
        }
    };

    const handleTriggerSwap = async () => {
        if (systemState !== 'idle' || !sessionId) return;

        try {
            addLog('OVERRIDE', 'User initiated evaluation...', 'text-pink-500');
            setSystemState('switching');

            // Call evaluation endpoint
            const result = await api.evaluateInstance(sessionId);

            // Sequence of events based on real response
            setTimeout(() => addLog('LOGIC', `Decision: ${result.decision}`, 'text-blue-300'), 500);
            setTimeout(() => addLog('LOGIC', `Reason: ${result.reason}`, 'text-blue-300'), 1000);

            if (result.decision === 'SWITCH') {
                setTimeout(() => addLog('ACTION', 'Provisioning Spot Candidate...', 'text-yellow-400'), 1500);
                setTimeout(() => addLog('NETWORK', 'Draining connections from Original...', 'text-slate-400'), 3500);
                setTimeout(() => {
                    setSystemState('stable');
                    addLog('SUCCESS', 'Traffic Switched to Spot Instance.', 'text-green-400 font-bold');

                    // Update savings
                    if (result.projected_hourly_savings) {
                        setSavings(prev => prev + result.projected_hourly_savings);
                    }
                }, 5000);
            } else {
                setTimeout(() => {
                    setSystemState('idle');
                    addLog('INFO', 'No action taken (instance safe)', 'text-green-400');
                }, 2000);
            }
        } catch (error) {
            console.error('Failed to trigger swap:', error);
            addLog('ERROR', `Evaluation failed: ${error.message}`, 'text-red-500');
            setSystemState('idle');
        }
    };

    const handleReset = () => {
        addLog('OVERRIDE', 'Simulating Price Spike / Interruption...', 'text-red-400');
        setSystemState('idle');
        setSavings(0);
        addLog('ACTION', 'Fallback Triggered. Reverting to On-Demand.', 'text-red-300');
    };

    return (
        <>
            {isSetupOpen && (
                <SandboxSetup
                    onLaunch={handleLaunch}
                    onCancel={() => navigate('/client')}
                />
            )}

            {sessionActive && (
                <SandboxLayout
                    onEject={handleEject}
                    sessionDetails={sessionDetails}
                >
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
