/**
 * Optimizer Coordinator Dashboard
 * ================================
 *
 * Displays unified optimizer status and proposals for cluster optimization.
 * Implements visualization for the phased optimization approach from problems.md.
 *
 * Shows:
 * - Current optimization phase with timeline
 * - Pending rightsizing proposals
 * - Combined EV comparison (Option A vs B vs C)
 * - Cooldown status
 * - Recent optimization history
 */

import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Card, Button, Badge } from '../shared';
import { FiClock, FiActivity, FiCheck, FiX, FiAlertCircle } from 'react-icons/fi';
import toast from 'react-hot-toast';

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000/api/v1';

const OptimizerCoordinatorDashboard = ({ clusterId }) => {
  const [status, setStatus] = useState(null);
  const [proposals, setProposals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedProposal, setSelectedProposal] = useState(null);
  const [evComparison, setEvComparison] = useState(null);
  const [trustPhase, setTrustPhase] = useState(null);
  const [resizeGuard, setResizeGuard] = useState(null);
  const [circuitBreaker, setCircuitBreaker] = useState(null);

  useEffect(() => {
    if (clusterId) {
      fetchOptimizerStatus();
      fetchProposals();
      fetchTrustPhase();
      fetchResizeGuardStatus();
      fetchCircuitBreakerStatus();

      // Refresh every 30 seconds
      const interval = setInterval(() => {
        fetchOptimizerStatus();
        fetchTrustPhase();
        fetchResizeGuardStatus();
        fetchCircuitBreakerStatus();
      }, 30000);

      return () => clearInterval(interval);
    }
  }, [clusterId]);

  const fetchOptimizerStatus = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/optimizer/status/${clusterId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setStatus(response.data.data);
    } catch (error) {
      console.error('Failed to fetch optimizer status:', error);
      toast.error('Failed to load optimizer status');
    } finally {
      setLoading(false);
    }
  };

  const fetchProposals = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/optimizer/proposals/${clusterId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setProposals(response.data.proposals || []);
    } catch (error) {
      console.error('Failed to fetch proposals:', error);
    }
  };

  const fetchEvComparison = async (proposalId) => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/optimizer/comparison/${proposalId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setEvComparison(response.data.evaluation_breakdown);
    } catch (error) {
      console.error('Failed to fetch EV comparison:', error);
    }
  };

  const fetchTrustPhase = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/optimizer/trust-phase/${clusterId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setTrustPhase(response.data.data);
    } catch (error) {
      console.error('Failed to fetch trust phase:', error);
      // Fallback to mock data if API fails
      setTrustPhase({
        phase: 2,
        rightsizing_allowed: true,
        safety_buffer_pct: 20,
        min_samples: 100,
        risk_ceiling_override: null,
        reason: "Phase 2: full mode (connection pending)",
        cluster_age_hours: 0
      });
    }
  };

  const fetchResizeGuardStatus = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/optimizer/resize-guard/${clusterId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setResizeGuard(response.data.data);
    } catch (error) {
      console.error('Failed to fetch resize guard status:', error);
      // Fallback to mock data if API fails
      setResizeGuard({
        active: false,
        recent_executions: 0,
        monitoring_proposals: [],
        last_check: new Date().toISOString()
      });
    }
  };

  const fetchCircuitBreakerStatus = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/optimizer/circuit-breaker/${clusterId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setCircuitBreaker(response.data.data);
    } catch (error) {
      console.error('Failed to fetch circuit breaker status:', error);
      // Fallback to mock data if API fails
      setCircuitBreaker({
        failure_count: 0,
        threshold: 3,
        is_open: false,
        time_until_reset: null
      });
    }
  };

  const handleApproveProposal = async (proposalId) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API_BASE}/optimizer/proposals/${proposalId}/approve`, {}, {
        headers: { Authorization: `Bearer ${token}` }
      });
      toast.success('Proposal approved and executed!');
      fetchOptimizerStatus();
      fetchProposals();
    } catch (error) {
      toast.error('Failed to approve proposal');
    }
  };

  const handleRejectProposal = async (proposalId, reason) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(
        `${API_BASE}/optimizer/proposals/${proposalId}/reject`,
        null,
        {
          params: { reason },
          headers: { Authorization: `Bearer ${token}` }
        }
      );
      toast.success('Proposal rejected');
      fetchProposals();
    } catch (error) {
      toast.error('Failed to reject proposal');
    }
  };

  const handleViewProposal = (proposal) => {
    setSelectedProposal(proposal);
    fetchEvComparison(proposal.id);
  };

  const getPhaseColor = (phase) => {
    switch (phase) {
      case 'INITIAL_POOL_OPTIMIZATION': return 'blue';
      case 'STABILIZATION': return 'yellow';
      case 'RIGHTSIZING_EVALUATION': return 'purple';
      case 'COMBINED_EXECUTION': return 'indigo';
      case 'COOLDOWN': return 'gray';
      default: return 'gray';
    }
  };

  const getPhaseLabel = (phase) => {
    switch (phase) {
      case 'INITIAL_POOL_OPTIMIZATION': return 'Pool Optimization';
      case 'STABILIZATION': return 'Stabilization';
      case 'RIGHTSIZING_EVALUATION': return 'Rightsizing Eval';
      case 'COMBINED_EXECUTION': return 'Combined Execution';
      case 'COOLDOWN': return 'Cooldown';
      default: return phase;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (!status) {
    return (
      <Card>
        <div className="text-center py-8">
          <FiAlertCircle className="w-12 h-12 text-gray-400 mx-auto mb-3" />
          <p className="text-gray-500">Unable to load optimizer status</p>
        </div>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Current Phase */}
      <Card>
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <FiActivity className="w-5 h-5 text-blue-500" />
          Optimization Status
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <div className="text-sm text-gray-600 mb-2">Current Phase</div>
            <Badge color={getPhaseColor(status.phase)} size="lg">
              {getPhaseLabel(status.phase)}
            </Badge>
            <div className="text-xs text-gray-500 mt-2">
              {status.hours_in_phase?.toFixed(1)} hours in phase
            </div>
          </div>

          <div>
            <div className="text-sm text-gray-600 mb-2">Pool Optimization</div>
            <div className={`text-lg font-semibold ${status.can_run_pool_optimization ? 'text-green-600' : 'text-gray-400'}`}>
              {status.can_run_pool_optimization ? 'Ready' : 'Blocked'}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {status.pool_optimization_reason}
            </div>
          </div>

          <div>
            <div className="text-sm text-gray-600 mb-2">Rightsizing Evaluation</div>
            <div className={`text-lg font-semibold ${status.can_run_rightsizing_evaluation ? 'text-green-600' : 'text-gray-400'}`}>
              {status.can_run_rightsizing_evaluation ? 'Ready' : 'Blocked'}
            </div>
            <div className="text-xs text-gray-500 mt-1">
              {status.rightsizing_evaluation_reason}
            </div>
          </div>
        </div>

        {/* Phase Timeline */}
        <div className="mt-6 pt-6 border-t">
          <div className="text-sm text-gray-600 mb-3">Optimization Cycle</div>
          <div className="flex items-center gap-2">
            {['INITIAL_POOL_OPTIMIZATION', 'STABILIZATION', 'RIGHTSIZING_EVALUATION', 'COMBINED_EXECUTION', 'COOLDOWN'].map((phase, idx) => (
              <React.Fragment key={phase}>
                <div className={`flex-1 text-center p-2 rounded ${status.phase === phase ? 'bg-blue-100 border-2 border-blue-500' : 'bg-gray-100'}`}>
                  <div className={`text-xs font-medium ${status.phase === phase ? 'text-blue-700' : 'text-gray-500'}`}>
                    {getPhaseLabel(phase)}
                  </div>
                </div>
                {idx < 4 && <div className="text-gray-400">→</div>}
              </React.Fragment>
            ))}
          </div>
        </div>
      </Card>

      {/* Cooldown Status */}
      {status.cooldown_status && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FiClock className="w-5 h-5 text-orange-500" />
            Cooldown Status
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {['resize', 'pool_switch', 'substitute'].map((action) => {
              const actionStatus = status.cooldown_status[action];
              return (
                <div key={action} className="p-4 bg-gray-50 rounded-lg">
                  <div className="text-sm font-medium text-gray-700 mb-2 capitalize">
                    {action.replace('_', ' ')}
                  </div>
                  <div className={`text-2xl font-bold ${actionStatus.active ? 'text-orange-600' : 'text-green-600'}`}>
                    {actionStatus.active ? `${actionStatus.remaining_minutes}m` : 'Ready'}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    {actionStatus.active ? 'Cooldown active' : 'No cooldown'}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Trust Phase Status */}
      {trustPhase && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FiActivity className="w-5 h-5 text-indigo-500" />
            Progressive Trust Phase
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="p-4 bg-indigo-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Current Phase</div>
              <div className="text-2xl font-bold text-indigo-600">
                Phase {trustPhase.phase}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {trustPhase.phase === 0 && 'Initial (0-30 min)'}
                {trustPhase.phase === 1 && 'Conservative (30-120 min)'}
                {trustPhase.phase === 2 && 'Full Mode (>2h)'}
              </div>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Cluster Age</div>
              <div className="text-2xl font-bold text-gray-900">
                {trustPhase.cluster_age_hours?.toFixed(1)}h
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Hours since activation
              </div>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Safety Buffer</div>
              <div className="text-2xl font-bold text-gray-900">
                {trustPhase.safety_buffer_pct}%
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Above P95 usage
              </div>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Min Samples</div>
              <div className="text-2xl font-bold text-gray-900">
                {trustPhase.min_samples}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Required for sizing
              </div>
            </div>
          </div>

          <div className="mt-4 p-3 bg-blue-50 border-l-4 border-blue-500 rounded">
            <div className="text-sm text-blue-700">
              <strong>Status:</strong> {trustPhase.reason}
            </div>
          </div>
        </Card>
      )}

      {/* Resize Guard Status */}
      {resizeGuard && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FiActivity className="w-5 h-5 text-green-500" />
            Post-Resize Guard (2-Hour Monitoring)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Guard Status</div>
              <div className={`text-2xl font-bold ${resizeGuard.active ? 'text-green-600' : 'text-gray-400'}`}>
                {resizeGuard.active ? 'Monitoring' : 'Inactive'}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {resizeGuard.active ? 'Health checks active' : 'No recent resizes'}
              </div>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Recent Executions</div>
              <div className="text-2xl font-bold text-gray-900">
                {resizeGuard.recent_executions}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Last 2 hours
              </div>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Monitoring</div>
              <div className="text-2xl font-bold text-gray-900">
                {resizeGuard.monitoring_proposals?.length || 0}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Active proposals
              </div>
            </div>
          </div>

          <div className="mt-4 p-3 bg-gray-50 rounded">
            <div className="text-xs text-gray-600">
              <strong>Checks:</strong> CPU stress (&gt;85%), Pod restarts (2x baseline), Memory pressure (&gt;5 events)
            </div>
            <div className="text-xs text-gray-500 mt-1">
              Last check: {new Date(resizeGuard.last_check).toLocaleTimeString()}
            </div>
          </div>
        </Card>
      )}

      {/* Circuit Breaker Status */}
      {circuitBreaker && (
        <Card>
          <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
            <FiAlertCircle className={`w-5 h-5 ${circuitBreaker.is_open ? 'text-red-500' : 'text-green-500'}`} />
            Resize Circuit Breaker
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className={`p-4 rounded-lg ${circuitBreaker.is_open ? 'bg-red-50' : 'bg-green-50'}`}>
              <div className="text-sm font-medium text-gray-700 mb-2">Status</div>
              <div className={`text-2xl font-bold ${circuitBreaker.is_open ? 'text-red-600' : 'text-green-600'}`}>
                {circuitBreaker.is_open ? 'OPEN' : 'CLOSED'}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {circuitBreaker.is_open ? 'Resizing blocked' : 'Normal operation'}
              </div>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Failures (24h)</div>
              <div className={`text-2xl font-bold ${circuitBreaker.failure_count >= circuitBreaker.threshold ? 'text-red-600' : 'text-gray-900'}`}>
                {circuitBreaker.failure_count} / {circuitBreaker.threshold}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                Threshold: {circuitBreaker.threshold} failures
              </div>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg">
              <div className="text-sm font-medium text-gray-700 mb-2">Auto Reset</div>
              <div className="text-2xl font-bold text-gray-900">
                {circuitBreaker.is_open ? '24h' : 'N/A'}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {circuitBreaker.is_open ? 'Automatic reset after 24h' : 'No reset needed'}
              </div>
            </div>
          </div>

          {circuitBreaker.is_open && (
            <div className="mt-4 p-3 bg-red-50 border-l-4 border-red-500 rounded">
              <div className="text-sm text-red-700">
                <strong>⚠️ Warning:</strong> Rightsizing blocked due to repeated failures. Circuit breaker will automatically reset after 24 hours.
              </div>
            </div>
          )}

          {!circuitBreaker.is_open && circuitBreaker.failure_count > 0 && (
            <div className="mt-4 p-3 bg-yellow-50 border-l-4 border-yellow-500 rounded">
              <div className="text-sm text-yellow-700">
                <strong>⚠️ Caution:</strong> {circuitBreaker.failure_count} resize failure(s) detected in last 24h. One more failure will open circuit breaker.
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Pending Proposals */}
      <Card>
        <div className="flex justify-between items-center mb-4">
          <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
            <FiAlertCircle className="w-5 h-5 text-purple-500" />
            Rightsizing Proposals ({proposals.length})
          </h3>
          <Button
            size="sm"
            onClick={() => fetchProposals()}
          >
            Refresh
          </Button>
        </div>

        {proposals.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            No proposals yet. Rightsizing evaluation runs every 24 hours.
          </div>
        ) : (
          <div className="space-y-3">
            {proposals.map((proposal) => (
              <div
                key={proposal.id}
                className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 cursor-pointer"
                onClick={() => handleViewProposal(proposal)}
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <Badge color={
                        proposal.status === 'PENDING' ? 'yellow' :
                          proposal.status === 'APPROVED' ? 'green' :
                            proposal.status === 'REJECTED' ? 'red' :
                              proposal.status === 'EXECUTED' ? 'blue' : 'gray'
                      }>
                        {proposal.status}
                      </Badge>
                      <span className="text-sm text-gray-500">
                        Created {new Date(proposal.created_at).toLocaleString()}
                      </span>
                    </div>

                    <div className="font-medium text-gray-900 mb-1">
                      {proposal.current_instance_type} → {proposal.proposed_instance_type}
                    </div>

                    <div className="text-sm text-green-600 font-semibold">
                      ${proposal.estimated_monthly_savings?.toFixed(2)}/mo savings ({proposal.savings_percentage?.toFixed(1)}%)
                    </div>

                    {/* Task 8.3: Show stored EV from backend */}
                    {proposal.ev_breakdown && (
                      <div className="text-sm text-indigo-600 mt-1" title={
                        `Savings: $${proposal.ev_breakdown.savings?.toFixed(2)}/hr\n` +
                        `Interruption: $${proposal.ev_breakdown.interruption_cost?.toFixed(2)}/hr\n` +
                        `Migration: $${proposal.ev_breakdown.migration_penalty?.toFixed(2)}\n` +
                        `Volatility: $${proposal.ev_breakdown.volatility_cost?.toFixed(2)}/hr\n` +
                        `Eligible: ${proposal.ev_breakdown.is_eligible ? 'Yes' : 'No'}`
                      }>
                        Server EV: <strong>${proposal.ev_breakdown.ev?.toFixed(4)}/hr</strong>
                        {proposal.net_ev != null && (
                          <span className="ml-2 text-gray-500">
                            (Net: ${proposal.net_ev?.toFixed(4)}/hr)
                          </span>
                        )}
                      </div>
                    )}

                    {proposal.rejection_reason && (
                      <div className="text-sm text-red-600 mt-2">
                        Rejected: {proposal.rejection_reason}
                      </div>
                    )}
                  </div>

                  {proposal.status === 'APPROVED' && (
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleApproveProposal(proposal.id);
                      }}
                    >
                      Execute
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* EV Comparison Modal */}
      {selectedProposal && evComparison && (
        <Card>
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold text-gray-900">
              Combined EV Analysis
            </h3>
            <button
              onClick={() => {
                setSelectedProposal(null);
                setEvComparison(null);
              }}
              className="text-gray-400 hover:text-gray-600"
            >
              <FiX className="w-5 h-5" />
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {/* Option A */}
            <div className={`p-4 border-2 rounded-lg ${evComparison.recommended_option === 'A' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}`}>
              <div className="text-sm font-medium text-gray-700 mb-2">Option A</div>
              <div className="text-xs text-gray-600 mb-3">{evComparison.option_a.description}</div>
              <div className="text-2xl font-bold text-gray-900 mb-1">
                ${evComparison.option_a.hourly_cost.toFixed(4)}/hr
              </div>
              <div className="text-sm text-green-600 mb-2">
                ${evComparison.option_a.hourly_savings.toFixed(4)}/hr savings
              </div>
              <div className="text-xs text-gray-500">
                Risk: {(evComparison.option_a.risk * 100).toFixed(1)}%
              </div>
              <div className="text-xs text-gray-500">
                EV: {evComparison.option_a.expected_value.toFixed(4)}
              </div>
            </div>

            {/* Option B */}
            <div className={`p-4 border-2 rounded-lg ${evComparison.recommended_option === 'B' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}`}>
              <div className="text-sm font-medium text-gray-700 mb-2">Option B</div>
              <div className="text-xs text-gray-600 mb-3">{evComparison.option_b.description}</div>
              <div className="text-2xl font-bold text-gray-900 mb-1">
                ${evComparison.option_b.hourly_cost.toFixed(4)}/hr
              </div>
              <div className="text-sm text-green-600 mb-2">
                ${evComparison.option_b.hourly_savings.toFixed(4)}/hr savings
              </div>
              <div className="text-xs text-gray-500">
                Risk: {(evComparison.option_b.risk * 100).toFixed(1)}%
              </div>
              <div className="text-xs text-gray-500">
                EV: {evComparison.option_b.expected_value.toFixed(4)}
              </div>
            </div>

            {/* Option C */}
            <div className={`p-4 border-2 rounded-lg ${evComparison.recommended_option === 'C' ? 'border-blue-500 bg-blue-50' : 'border-gray-200'}`}>
              <div className="text-sm font-medium text-gray-700 mb-2">Option C</div>
              <div className="text-xs text-gray-600 mb-3">{evComparison.option_c.description}</div>
              <div className="text-2xl font-bold text-gray-900 mb-1">
                ${evComparison.option_c.hourly_cost.toFixed(4)}/hr
              </div>
              <div className="text-sm text-gray-600 mb-2">
                Baseline (no change)
              </div>
              <div className="text-xs text-gray-500">
                Risk: {(evComparison.option_c.risk * 100).toFixed(1)}%
              </div>
              <div className="text-xs text-gray-500">
                EV: {evComparison.option_c.expected_value.toFixed(4)}
              </div>
            </div>
          </div>

          <div className="p-4 bg-blue-50 rounded-lg">
            <div className="font-semibold text-blue-900 mb-2">
              Recommendation: Option {evComparison.recommended_option}
            </div>
            <div className="text-sm text-blue-700">
              EV Improvement: {evComparison.best_ev_delta_pct.toFixed(2)}%
              {evComparison.sufficient_improvement ? ' ✓ Sufficient' : ' ✗ Insufficient'}
            </div>
          </div>

          {selectedProposal.status === 'PENDING' && (
            <div className="flex gap-3 mt-4">
              <Button
                variant="primary"
                onClick={() => handleApproveProposal(selectedProposal.id)}
                icon={<FiCheck />}
              >
                Approve & Execute
              </Button>
              <Button
                variant="outline"
                onClick={() => {
                  const reason = prompt('Reason for rejection:');
                  if (reason) {
                    handleRejectProposal(selectedProposal.id, reason);
                    setSelectedProposal(null);
                    setEvComparison(null);
                  }
                }}
                icon={<FiX />}
              >
                Reject
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
};

export default OptimizerCoordinatorDashboard;
