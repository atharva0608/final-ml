/**
 * VolatilityMonitor — Self-contained volatility banner (Task 7.5)
 * 
 * Polls GET /api/v1/ascpai/volatility every 10 minutes (matches 2hr Redis TTL).
 * Previously this logic was inline in MainLayout.jsx, causing re-fetches on
 * every route change. Now isolated so a slow/failing endpoint only delays
 * the banner — the rest of the UI renders immediately.
 */
import React, { useState, useEffect } from 'react';
import { ascpaiAPI } from '../../services/api';

const VolatilityMonitor = () => {
    const [volatility, setVolatility] = useState({ regime: 'NORMAL' });

    useEffect(() => {
        let mounted = true;

        const fetchVolatility = async () => {
            try {
                const res = await ascpaiAPI.getVolatilityStatus();
                if (mounted) {
                    setVolatility(res.data || { regime: 'NORMAL' });
                }
            } catch (err) {
                console.error('VolatilityMonitor: fetch failed', err);
                // Fail silent — banner just stays hidden
            }
        };

        fetchVolatility();
        // Poll every 10 minutes (600 000 ms) — NOT on every route change
        const interval = setInterval(fetchVolatility, 600_000);
        return () => {
            mounted = false;
            clearInterval(interval);
        };
    }, []);

    if (volatility.regime === 'NORMAL') return null;

    return (
        <div
            className={`w-full py-1.5 px-4 text-center text-xs font-bold text-white z-50 sticky top-0 ${volatility.regime === 'CRITICAL' ? 'bg-red-600' : 'bg-yellow-600'
                }`}
        >
            ⚠️ VOLATILITY MONITOR: Market regime is currently {volatility.regime}.
            Expected Value risk ceilings are dynamically constrained.
        </div>
    );
};

// React.memo prevents re-renders on parent re-mount (route changes in MainLayout)
export default React.memo(VolatilityMonitor);
