/**
 * Normalizes a raw node object to a consistent state string.
 * Single source of truth for node state interpretation across all pages.
 * @param {Object} node - Raw node object from API
 * @returns {'ACTIVE'|'DRAINING'|'PROVISIONING'|'BLOCKED'|'UNKNOWN'}
 */
export const normalizeNodeState = (node) => {
  const s         = (node.status         || '').toLowerCase();
  const lifecycle = (node.lifecycle_state || '').toLowerCase();

  if (s === 'draining' || node.draining || node.cordoned)                              return 'DRAINING';
  if (['blocked', 'error', 'failed'].includes(s))                                      return 'BLOCKED';
  if (['provisioning', 'pending', 'notready', 'not_ready'].includes(s)
    || lifecycle === 'provisioning')                                                    return 'PROVISIONING';
  if (node.ready === true || ['ready', 'active', 'running'].includes(s))               return 'ACTIVE';
  return 'UNKNOWN';
};

/**
 * Normalizes a raw action/event object to a consistent execution state.
 * Single source of truth for action state interpretation across all pages.
 * @param {Object} action - Raw action object from API
 * @returns {'COMPLETED'|'RUNNING'|'BLOCKED'|'PENDING'|'UNKNOWN'}
 */
export const normalizeExecutionState = (action) => {
  const s = (action.status || '').toLowerCase();

  if (['completed', 'optimization_complete', 'success'].includes(s)) return 'COMPLETED';
  if (['in_progress', 'active', 'running'].includes(s))               return 'RUNNING';
  if (['blocked', 'failed', 'error', 'stuck'].includes(s))            return 'BLOCKED';
  if (['pending', 'waiting', 'provisioning'].includes(s))             return 'PENDING';
  return 'UNKNOWN';
};
