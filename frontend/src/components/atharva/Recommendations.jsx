import React from 'react';
import { motion } from 'framer-motion';
import { FiZap, FiCheckCircle, FiArrowRight } from 'react-icons/fi';

const Recommendations = ({ recommendations }) => {
    return (
        <div className="flex flex-col h-full gap-4">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold flex items-center gap-2 text-gray-900">
                    <FiZap className="text-yellow-500" /> AI Insights
                </h2>
                <span className="text-xs text-blue-600 cursor-pointer hover:underline font-medium">View All</span>
            </div>

            <div className="flex-1 space-y-3 overflow-y-auto custom-scrollbar pr-1">
                {recommendations?.length === 0 && (
                    <div className="text-center py-8 text-gray-400">
                        <FiCheckCircle className="mx-auto text-3xl mb-2 opacity-50" />
                        <p>No active recommendations</p>
                        <p className="text-xs">System is optimized</p>
                    </div>
                )}

                {recommendations?.map((rec, index) => (
                    <motion.div
                        key={rec.id}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: index * 0.1 }}
                        className={`p-4 rounded-lg border-l-4 shadow-sm group relative overflow-hidden bg-white ${rec.risk_level === 'high' ? 'border-red-500 hover:bg-red-50' :
                                rec.risk_level === 'medium' ? 'border-yellow-500 hover:bg-yellow-50' :
                                    'border-blue-500 hover:bg-blue-50'
                            } transition-all duration-300 border-t border-r border-b border-gray-200`}
                    >
                        <div className="flex justify-between items-start mb-2 relative z-10">
                            <h4 className="font-bold text-sm text-gray-900 transition-colors">{rec.title}</h4>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase tracking-wide border ${rec.risk_level === 'high' ? 'bg-red-100 text-red-700 border-red-200' :
                                    rec.risk_level === 'medium' ? 'bg-yellow-100 text-yellow-700 border-yellow-200' :
                                        'bg-blue-100 text-blue-700 border-blue-200'
                                }`}>
                                {rec.risk_level} Impact
                            </span>
                        </div>

                        <p className="text-xs text-gray-600 mb-3 line-clamp-2 leading-relaxed transition-colors">{rec.description}</p>

                        <div className="flex justify-between items-center relative z-10">
                            <div className="flex flex-col">
                                <span className="text-[10px] uppercase font-bold text-gray-400 mb-1">Target</span>
                                <span className="text-xs font-mono text-gray-700 font-medium bg-gray-100 px-1 rounded">{rec.applies_to}</span>
                            </div>

                            <div className="text-right">
                                <span className="text-[10px] uppercase font-bold text-gray-400 mb-1 block">Benefit</span>
                                <span className="text-green-600 font-bold text-sm">{rec.impact}</span>
                            </div>
                        </div>

                        {/* Action Bar */}
                        <div className="mt-4 flex gap-2 justify-end opacity-0 group-hover:opacity-100 transition-opacity duration-300 transform translate-y-2 group-hover:translate-y-0">
                            <button className="text-xs bg-white hover:bg-gray-50 text-gray-600 hover:text-gray-900 px-3 py-1.5 rounded transition-colors border border-gray-300 shadow-sm">Dismiss</button>
                            <button className="text-xs bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded transition-colors flex items-center gap-1 shadow-sm">
                                Apply Fix <FiArrowRight />
                            </button>
                        </div>
                    </motion.div>
                ))}
            </div>
        </div>
    );
};

export default Recommendations;
