/**
 * JITRequestModal Component
 *
 * Modal for requesting Just-In-Time feature access
 */
import React, { useState } from 'react';
import { X, Clock, Shield, AlertTriangle } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import Button from '../shared/Button';
import RiskBadge from '../shared/RiskBadge';
import { approvalsAPI } from '../../services/api';

const JITRequestModal = ({ featureId, feature, resourceId = null, onClose, onSuccess }) => {
  const [reason, setReason] = useState('');
  const [duration, setDuration] = useState(feature?.default_duration_hours || 1);
  const [reasonCategory, setReasonCategory] = useState('MAINTENANCE');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!reason.trim()) {
      setError('Please provide a reason for access');
      return;
    }

    try {
      setSubmitting(true);
      setError('');

      await approvalsAPI.createJITRequest({
        feature_id: featureId,
        reason_category: reasonCategory,
        reason_text: reason,
        duration_hours: duration,
        resource_id: resourceId,
        jit_scope: 'TEAM'
      });

      if (onSuccess) {
        onSuccess();
      }

      // Show success message
      alert('Access request submitted successfully! Awaiting approval from Team Lead.');
      onClose();
    } catch (err) {
      console.error('Failed to submit request:', err);
      setError(err.response?.data?.detail || 'Failed to submit request. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!feature) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50 p-4">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.95 }}
          transition={{ duration: 0.2 }}
          className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        >
          {/* Header */}
          <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <Shield className="h-6 w-6 text-blue-600" />
              <div>
                <h2 className="text-xl font-semibold text-gray-900">Request Access</h2>
                <p className="text-sm text-gray-500">{feature.name}</p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 transition-colors"
            >
              <X className="h-6 w-6" />
            </button>
          </div>

          {/* Body */}
          <div className="p-6 space-y-6">
            {/* Risk Level Alert */}
            <div className={`border-l-4 p-4 rounded-r-lg ${
              feature.risk_level === 'CRITICAL' ? 'bg-red-50 border-red-500' :
              feature.risk_level === 'HIGH' ? 'bg-orange-50 border-orange-500' :
              feature.risk_level === 'MEDIUM' ? 'bg-yellow-50 border-yellow-500' :
              'bg-green-50 border-green-500'
            }`}>
              <div className="flex items-start space-x-3">
                <AlertTriangle className={`h-5 w-5 mt-0.5 ${
                  feature.risk_level === 'CRITICAL' ? 'text-red-600' :
                  feature.risk_level === 'HIGH' ? 'text-orange-600' :
                  feature.risk_level === 'MEDIUM' ? 'text-yellow-600' :
                  'text-green-600'
                }`} />
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <RiskBadge level={feature.risk_level} />
                  </div>
                  <p className="text-sm text-gray-700">
                    <strong>Requires approval from:</strong> {feature.min_approver_role === 'ORG_ADMIN' ? 'Organization Admin' : 'Team Lead'}
                  </p>
                </div>
              </div>
            </div>

            {/* Description */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">What this allows</h3>
              <p className="text-sm text-gray-600">{feature.description}</p>
            </div>

            {/* Duration Slider */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                <Clock className="inline h-4 w-4 mr-1" />
                Access Duration (hours)
              </label>
              <div className="space-y-2">
                <input
                  type="range"
                  min="1"
                  max={feature.max_duration_hours}
                  value={duration}
                  onChange={(e) => setDuration(parseInt(e.target.value))}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-blue-600"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>Default: {feature.default_duration_hours}h</span>
                  <span className="font-semibold text-blue-600">{duration}h</span>
                  <span>Maximum: {feature.max_duration_hours}h</span>
                </div>
              </div>
            </div>

            {/* Reason Category */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Reason Category
              </label>
              <select
                value={reasonCategory}
                onChange={(e) => setReasonCategory(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="MAINTENANCE">Maintenance</option>
                <option value="INCIDENT">Incident Response</option>
                <option value="DEPLOYMENT">Deployment</option>
                <option value="DEBUGGING">Debugging</option>
                <option value="AUDIT">Audit/Compliance</option>
                <option value="OTHER">Other</option>
              </select>
            </div>

            {/* Reason Text */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Reason for Access <span className="text-red-500">*</span>
              </label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Explain why you need this access... (e.g., Need to cleanup orphaned EBS volumes costing $200/month)"
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              />
              <p className="mt-1 text-xs text-gray-500">
                Be specific. Your Team Lead will review this request.
              </p>
            </div>

            {/* Error Message */}
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-sm text-red-800">{error}</p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="sticky bottom-0 bg-gray-50 px-6 py-4 flex justify-end space-x-3 border-t border-gray-200">
            <Button
              variant="ghost"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={submitting}
              disabled={submitting || !reason.trim()}
            >
              Submit Request
            </Button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};

export default JITRequestModal;
