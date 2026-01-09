import React from 'react';
import { motion } from 'framer-motion';
import { FiCheckCircle, FiArrowRight } from 'react-icons/fi';
import { Button } from '../shared';
import Confetti from 'react-canvas-confetti';

const SuccessStep = ({ onConvert }) => {
    const fireConfetti = () => {
        // Simple confetti trigger could go here
    };

    return (
        <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white rounded-2xl shadow-xl p-10 text-center relative overflow-hidden"
        >
            <div className="absolute inset-0 pointer-events-none">
                {/* CSS Background decoration if needed */}
            </div>

            <div className="inline-flex p-4 bg-green-50 rounded-full mb-6 relative z-10">
                <FiCheckCircle className="w-10 h-10 text-green-500" />
            </div>

            <h1 className="text-3xl font-bold text-gray-900 mb-4 relative z-10">
                Connection Successful!
            </h1>
            <p className="text-gray-600 text-lg mb-8 max-w-md mx-auto relative z-10">
                We've started analyzing your clusters. Your cost savings dashboard is being generated right now.
            </p>

            <Button
                variant="primary"
                size="lg"
                className="w-full md:w-auto px-10 py-4 text-lg bg-green-600 hover:bg-green-700 border-transparent relative z-10"
                onClick={onConvert}
                icon={<FiArrowRight />}
            >
                Go to Dashboard
            </Button>
        </motion.div>
    );
};

export default SuccessStep;
