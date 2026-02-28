import React, { useState, useEffect } from 'react';
import { atharvaAiAPI } from '../../services/api';

const BlacklistMonitorCard = () => {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const fetchStatus = async () => {
            try {
                const res = await atharvaAiAPI.getBlacklistStatus();
                setStatus(res.data);
            } catch (err) {
                console.error("Failed to fetch blacklist status", err);
            } finally {
                setLoading(false);
            }
        };
        fetchStatus();
    }, []);

    if (loading) return null;

    // Example response structure: { active_count: 12, suspended: true, reason: "high_saturation" }
    const isSuspended = status?.suspended;

    if (!isSuspended) return null; // Only show if suspended or significantly saturated

    return (
        <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg shadow-sm mb-6 flex items-start gap-3">
            <div className="flex-shrink-0 mt-0.5">
                <svg className="h-5 w-5 text-red-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
            </div>
            <div>
                <h3 className="text-sm font-bold text-red-800">Predictive Blacklisting Suspended</h3>
                <p className="text-sm text-red-700 mt-1">
                    The predictive blacklist monitor has detected high saturation ({status?.active_count || 'many'} active blacklists).
                    To prevent capacity starvation, AI-driven predictive blacklisting has been temporarily suspended.
                    <i> Only exact ITNs (Termination Notices) will trigger blacklists.</i>
                </p>
            </div>
        </div>
    );
};

export default BlacklistMonitorCard;
