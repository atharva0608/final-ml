import React from 'react';
import { FiActivity } from 'react-icons/fi';
import { motion } from 'framer-motion';

const InstanceRankings = ({ rankings }) => {
    return (
        <div className="bg-white rounded-xl border border-gray-200 p-5 h-full overflow-hidden flex flex-col shadow-sm">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-gray-900">
                <FiActivity className="text-blue-600" /> Instance Pool Rankings
            </h2>

            <div className="flex-1 overflow-y-auto space-y-4 pr-1 custom-scrollbar">
                {/* Safe Pools Section */}
                <div className="bg-gray-50 p-3 rounded-lg border border-gray-200">
                    <div className="flex justify-between items-center mb-2">
                        <h3 className="text-sm font-medium text-gray-600">Safest Pools</h3>
                        <span className="text-[10px] bg-green-100 text-green-700 px-1.5 py-0.5 rounded border border-green-200">Low Risk</span>
                    </div>
                    <ul className="space-y-2">
                        {rankings?.top_safe_pools.map((pool, index) => (
                            <motion.li
                                key={pool.id}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: index * 0.05 }}
                                className="group flex justify-between items-center text-sm p-2 hover:bg-white hover:shadow-sm rounded cursor-pointer transition-all border border-transparent hover:border-gray-200"
                            >
                                <div className="flex flex-col">
                                    <span className="font-mono text-gray-700 font-medium group-hover:text-blue-600 transition-colors">{pool.name}</span>
                                    <span className="text-[10px] text-gray-500">{pool.availability_zone} • {pool.instance_type}</span>
                                </div>
                                <div className="text-right">
                                    <span className="block text-green-600 font-bold">{pool.interrupt_risk}% Risk</span>
                                    <span className="text-[10px] text-gray-500">${pool.price}/hr</span>
                                </div>
                            </motion.li>
                        ))}
                    </ul>
                </div>

                {/* Cheap Pools Section */}
                <div className="bg-gray-50 p-3 rounded-lg border border-gray-200">
                    <div className="flex justify-between items-center mb-2">
                        <h3 className="text-sm font-medium text-gray-600">Cheapest Pools</h3>
                        <span className="text-[10px] bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded border border-yellow-200">Best Value</span>
                    </div>
                    <ul className="space-y-2">
                        {rankings?.top_cheap_pools.map((pool, index) => (
                            <motion.li
                                key={pool.id}
                                initial={{ opacity: 0, x: -10 }}
                                animate={{ opacity: 1, x: 0 }}
                                transition={{ delay: 0.2 + (index * 0.05) }}
                                className="group flex justify-between items-center text-sm p-2 hover:bg-white hover:shadow-sm rounded cursor-pointer transition-all border border-transparent hover:border-gray-200"
                            >
                                <div className="flex flex-col">
                                    <span className="font-mono text-gray-700 font-medium group-hover:text-blue-600 transition-colors">{pool.name}</span>
                                    <span className="text-[10px] text-gray-500">{pool.availability_zone} • {pool.instance_type}</span>
                                </div>
                                <div className="text-right">
                                    <span className="block text-yellow-600 font-bold">${pool.price}/hr</span>
                                    <span className="text-[10px] text-gray-500">{pool.interrupt_risk}% Risk</span>
                                </div>
                            </motion.li>
                        ))}
                    </ul>
                </div>
            </div>
        </div>
    );
};

export default InstanceRankings;
