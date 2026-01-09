import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { onboardingAPI } from '../services/api';
import WelcomeStep from '../components/onboarding/WelcomeStep';
import ConnectStep from '../components/onboarding/ConnectStep';
import VerifyStep from '../components/onboarding/VerifyStep';
import SuccessStep from '../components/onboarding/SuccessStep';
import { FiX } from 'react-icons/fi';

const Onboarding = () => {
    const navigate = useNavigate();
    const [step, setStep] = useState('WELCOME');
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        // Check current state from backend
        const fetchState = async () => {
            try {
                const response = await onboardingAPI.getState();
                const { current_step, is_completed } = response.data;

                if (is_completed) {
                    navigate('/dashboard');
                } else {
                    // Start from backend state or default to WELCOME
                    setStep(current_step);
                }
            } catch (error) {
                console.error("Failed to fetch onboarding state", error);
            } finally {
                setLoading(false);
            }
        };
        fetchState();
    }, [navigate]);

    const handleSkip = async () => {
        try {
            await onboardingAPI.skip();
            navigate('/dashboard');
        } catch (error) {
            console.error("Skip failed", error);
        }
    };

    const nextStep = (next) => setStep(next);

    if (loading) return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
        </div>
    );

    return (
        <div className="min-h-screen bg-gray-50 font-sans text-gray-900 flex flex-col">
            {/* Minimal Header */}
            <div className="w-full h-16 bg-white border-b border-gray-200 flex items-center justify-between px-8">
                <div className="flex items-center gap-2">
                    <div className="w-8 h-8 bg-blue-600 rounded-lg flex items-center justify-center text-white font-bold">S</div>
                    <span className="font-bold text-xl tracking-tight">SpotOptimizer</span>
                </div>
                <button
                    onClick={handleSkip}
                    className="text-gray-500 hover:text-gray-700 text-sm font-medium flex items-center gap-1"
                >
                    Skip for now <FiX />
                </button>
            </div>

            {/* Main Content Area */}
            <div className="flex-1 flex items-center justify-center p-6">
                <div className="w-full max-w-2xl">
                    <AnimatePresence mode="wait">
                        {step === 'WELCOME' && (
                            <WelcomeStep key="welcome" onNext={() => nextStep('CONNECT_AWS')} />
                        )}
                        {step === 'CONNECT_AWS' && (
                            <ConnectStep key="connect" onNext={() => nextStep('VERIFYING')} />
                        )}
                        {step === 'VERIFYING' && ( // Usually triggered automatically by ConnectStep, but kept for state logic
                            <VerifyStep key="verifying" onNext={() => nextStep('COMPLETED')} />
                        )}
                        {step === 'COMPLETED' && (
                            <SuccessStep key="success" onConvert={() => navigate('/dashboard')} />
                        )}
                    </AnimatePresence>
                </div>
            </div>

            {/* Progress Footer */}
            <div className="h-2 bg-gray-100 w-full fixed bottom-0 left-0">
                <motion.div
                    className="h-full bg-blue-600"
                    initial={{ width: "0%" }}
                    animate={{
                        width: step === 'WELCOME' ? '25%' :
                            step === 'CONNECT_AWS' ? '50%' :
                                step === 'VERIFYING' ? '75%' : '100%'
                    }}
                    transition={{ duration: 0.5 }}
                />
            </div>
        </div>
    );
};

export default Onboarding;
