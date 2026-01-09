import React from 'react';
import { motion } from 'framer-motion';
import { FiArrowRight, FiShield, FiTrendingDown, FiClock } from 'react-icons/fi';
import { Button } from '../shared';

const WelcomeStep = ({ onNext }) => {
    return (
        <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className="bg-white rounded-2xl shadow-xl p-10 text-center"
        >
            <div className="inline-flex p-4 bg-blue-50 rounded-full mb-6">
                <FiTrendingDown className="w-8 h-8 text-blue-600" />
            </div>

            <h1 className="text-3xl font-bold text-gray-900 mb-4">
                Let's find your savings
            </h1>
            <p className="text-gray-600 text-lg mb-8 max-w-md mx-auto">
                Connect your AWS account in read-only mode to see how much you can save. No agents or code changes required.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10 text-left">
                <div className="p-4 bg-gray-50 rounded-lg">
                    <FiShield className="w-6 h-6 text-green-600 mb-2" />
                    <h3 className="font-semibold text-gray-900">Secure</h3>
                    <p className="text-sm text-gray-500">Read-only access via AWS STS. No long-term keys.</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg">
                    <FiClock className="w-6 h-6 text-purple-600 mb-2" />
                    <h3 className="font-semibold text-gray-900">Fast</h3>
                    <p className="text-sm text-gray-500">Get results in less than 5 minutes.</p>
                </div>
                <div className="p-4 bg-gray-50 rounded-lg">
                    <FiTrendingDown className="w-6 h-6 text-blue-600 mb-2" />
                    <h3 className="font-semibold text-gray-900">Impactful</h3>
                    <p className="text-sm text-gray-500">Average savings of 40-60% on compute.</p>
                </div>
            </div>

            <Button
                variant="primary"
                size="lg"
                className="w-full md:w-auto px-12 py-4 text-lg"
                onClick={onNext}
                icon={<FiArrowRight />}
            >
                Start Connection
            </Button>
        </motion.div>
    );
};

export default WelcomeStep;
