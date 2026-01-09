import React, { useEffect } from 'react';
import { motion } from 'framer-motion';

const VerifyStep = ({ onNext }) => {
    // Logic usually handled in ConnectStep, this is just a visual intermediary if needed
    // or if we want a dedicated generic "Verifying" screen
    useEffect(() => {
        // Auto-advance if we end up here
        const timer = setTimeout(onNext, 1000);
        return () => clearTimeout(timer);
    }, [onNext]);

    return (
        <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="bg-white rounded-2xl shadow-xl p-10 text-center"
        >
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600 mx-auto mb-6"></div>
            <h2 className="text-xl font-bold text-gray-900">Verifying Access...</h2>
            <p className="text-gray-500 mt-2">Connecting securely via AWS STS</p>
        </motion.div>
    );
};

export default VerifyStep;
