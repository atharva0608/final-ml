/**
 * PermissionGate Component
 *
 * Wraps sections/pages that require permissions.
 * Shows full-screen blur overlay with permission request modal when access is denied.
 */
import React, { useState, useEffect, memo } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePermission } from '../../hooks/usePermission';
import { FiLock, FiShield, FiClock, FiX, FiAlertTriangle } from 'react-icons/fi';
import TicketRequestModal from '../approvals/TicketRequestModal';

const PermissionGate = ({
  featureId,
  resourceId = null,
  children,
  sectionName = "this section",
  sectionDescription = "Access to this feature requires approval"
}) => {
  const navigate = useNavigate();
  const { hasPermission, loading, feature, pending, ticket, refresh } = usePermission(featureId, resourceId);
  const [showModal, setShowModal] = useState(false);
  const [hasAttemptedAccess, setHasAttemptedAccess] = useState(false);

  const handleModalClose = () => {
    setShowModal(false);
    // Refresh permission state after submitting request
    if (refresh) {
      refresh();
    }
  };

  // Check permission on mount
  useEffect(() => {
    if (!loading && !hasPermission) {
      setHasAttemptedAccess(true);
    }
  }, [loading, hasPermission]);

  // Always render children to prevent re-mounting, just show/hide overlay
  return (
    <div className="relative min-h-screen">
      {/* Main content - always rendered, never re-mounted */}
      <div
        className={`transition-all duration-300 ${
          !hasPermission && !loading ? 'filter blur-sm pointer-events-none select-none opacity-50' : ''
        }`}
      >
        {children}
      </div>

      {/* Loading overlay - smooth fade in/out */}
      {loading && (
        <div className="fixed inset-0 bg-white/80 backdrop-blur-sm flex items-center justify-center z-50 animate-fadeIn">
          <div className="text-center">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
            <p className="text-gray-600">Checking permissions...</p>
          </div>
        </div>
      )}

      {/* Permission overlay - smooth fade in/out */}
      {!loading && !hasPermission && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-50 p-4 animate-fadeIn">
        <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-8 relative animate-fadeIn">
          {/* Icon */}
          <div className="flex justify-center mb-6">
            <div className={`rounded-full p-6 ${pending ? 'bg-yellow-100' : 'bg-red-100'}`}>
              {pending ? (
                <FiClock className="w-12 h-12 text-yellow-600" />
              ) : (
                <FiLock className="w-12 h-12 text-red-600" />
              )}
            </div>
          </div>

          {/* Title */}
          <h2 className="text-2xl font-bold text-gray-900 text-center mb-3">
            {pending ? 'Request Pending Approval' : 'Permission Required'}
          </h2>

          {/* Description */}
          <p className="text-gray-600 text-center mb-6">
            {pending ? (
              <>
                Your request for access to <strong>{sectionName}</strong> is awaiting approval.
                <span className="block mt-2 text-sm text-gray-500">
                  You'll be notified once a Team Lead or Admin approves your request.
                </span>
              </>
            ) : (
              <>
                You don't have access to <strong>{sectionName}</strong>.
                {sectionDescription && (
                  <span className="block mt-2 text-sm text-gray-500">
                    {sectionDescription}
                  </span>
                )}
              </>
            )}
          </p>

          {/* Feature Details */}
          {feature && (
            <div className="bg-indigo-50 rounded-lg p-4 mb-6 border border-indigo-100">
              <div className="flex items-start space-x-3">
                <FiShield className="w-5 h-5 text-indigo-600 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="font-semibold text-indigo-900 text-sm">{feature.name}</p>
                  <p className="text-xs text-indigo-700 mt-1">{feature.description}</p>
                  <div className="flex items-center space-x-4 mt-2 text-xs text-indigo-600">
                    <span className="flex items-center">
                      <FiClock className="w-3 h-3 mr-1" />
                      Max {feature.max_duration_hours}h
                    </span>
                    <span className="flex items-center">
                      <FiAlertTriangle className="w-3 h-3 mr-1" />
                      {feature.risk_level} Risk
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Action Buttons */}
          <div className="flex space-x-3">
            <button
              onClick={() => window.history.back()}
              className="flex-1 px-6 py-3 border-2 border-gray-300 rounded-lg font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Go Back
            </button>
            {pending ? (
              <button
                onClick={() => navigate('/approvals')}
                className="flex-1 px-6 py-3 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg font-semibold transition-colors shadow-lg flex items-center justify-center space-x-2"
              >
                <FiClock className="w-4 h-4" />
                <span>View Status</span>
              </button>
            ) : (
              <button
                onClick={() => setShowModal(true)}
                className="flex-1 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold transition-colors shadow-lg flex items-center justify-center space-x-2"
              >
                <FiShield className="w-4 h-4" />
                <span>Request Access</span>
              </button>
            )}
          </div>

          {/* Help Text */}
          <p className="text-xs text-gray-500 text-center mt-4">
            {pending
              ? 'Check the Approvals page to track your request status.'
              : 'Your request will be sent to your Team Lead or Organization Admin for approval.'
            }
          </p>
        </div>
      </div>
      )}

      {/* Request Modal */}
      {showModal && (
        <TicketRequestModal
          isOpen={showModal}
          onClose={handleModalClose}
          initialData={{
            action: featureId,
            resource_id: resourceId || sectionName
          }}
        />
      )}
    </div>
  );
};

// Memoize to prevent unnecessary re-renders
export default memo(PermissionGate);
