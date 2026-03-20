import { useEffect, useRef, useCallback } from 'react';

/**
 * useAdaptivePolling — Issues #38 + #31
 *
 * Polls `fetchFn` every `fastMs` when `isActive` is true, otherwise every `slowMs`.
 * Cleans up the timer on unmount or when deps change.
 *
 * @param {object} opts
 * @param {() => Promise<any>} opts.fetchFn  - Async function to call on each tick
 * @param {boolean}            opts.isActive - When true, use fast interval (e.g. rebalance in progress)
 * @param {number}             [opts.fastMs=5000]  - Fast poll interval in ms (default 5s)
 * @param {number}             [opts.slowMs=30000] - Slow poll interval in ms (default 30s)
 *
 * Usage:
 *   const hasInProgress = rebalancingActions?.some(a => ['in_progress','waiting_agent'].includes(a.status));
 *   useAdaptivePolling({ fetchFn: fetchMainData, isActive: hasInProgress });
 */
export function useAdaptivePolling({ fetchFn, isActive, fastMs = 5000, slowMs = 30000 }) {
  const timerRef = useRef(null);
  const isActiveRef = useRef(isActive);
  const fetchFnRef = useRef(fetchFn);

  // Keep refs up to date without re-scheduling
  useEffect(() => { isActiveRef.current = isActive; }, [isActive]);
  useEffect(() => { fetchFnRef.current = fetchFn; }, [fetchFn]);

  const scheduleNext = useCallback(() => {
    const delay = isActiveRef.current ? fastMs : slowMs;
    timerRef.current = setTimeout(async () => {
      try {
        await fetchFnRef.current();
      } catch (e) {
        // Swallow errors — fetchFn is responsible for its own error handling
      }
      scheduleNext();
    }, delay);
  }, [fastMs, slowMs]);

  useEffect(() => {
    // Fire immediately on mount / when isActive flips
    fetchFnRef.current().catch(() => {});
    // Clear any existing timer before scheduling
    clearTimeout(timerRef.current);
    scheduleNext();
    return () => clearTimeout(timerRef.current);
  }, [isActive, scheduleNext]);
}
