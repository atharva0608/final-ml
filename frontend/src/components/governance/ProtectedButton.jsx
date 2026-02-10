/**
 * ProtectedButton Component
 *
 * Button that enforces JIT permission checks.
 * Automatically shows lock icon and opens request modal if permission denied.
 */
import React, { useState } from 'react';
import { Lock, Clock, CheckCircle } from 'lucide-react';
import Button from '../shared/Button';
import JITRequestModal from './JITRequestModal';
import { usePermission } from '../../hooks/usePermission';

const ProtectedButton = ({
  featureId,
  resourceId = null,
  onClick,
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false,
  ...props
}) => {
  const { hasPermission, loading, feature, ticket, expiresAt } = usePermission(featureId, resourceId);
  const [showModal, setShowModal] = useState(false);

  const handleClick = (e) => {
    if (!hasPermission) {
      e.preventDefault();
      setShowModal(true);
      return;
    }

    if (onClick) {
      onClick(e);
    }
  };

  const handleModalSuccess = () => {
    setShowModal(false);
    // Optionally reload permissions or show notification
  };

  // Loading state
  if (loading) {
    return (
      <Button
        variant={variant}
        size={size}
        disabled={true}
        className={className}
        {...props}
      >
        Loading...
      </Button>
    );
  }

  // Has active permission
  if (hasPermission && ticket) {
    return (
      <>
        <Button
          variant={variant}
          size={size}
          onClick={handleClick}
          disabled={disabled}
          className={className}
          {...props}
        >
          <CheckCircle className="h-4 w-4 mr-2 text-green-500" />
          {children}
        </Button>
      </>
    );
  }

  // Has permission (no approval needed)
  if (hasPermission && !ticket) {
    return (
      <Button
        variant={variant}
        size={size}
        onClick={handleClick}
        disabled={disabled}
        className={className}
        {...props}
      >
        {children}
      </Button>
    );
  }

  // Requires approval - Locked
  return (
    <>
      <Button
        variant="outline"
        size={size}
        onClick={handleClick}
        disabled={disabled}
        className={`border-gray-300 text-gray-700 hover:border-indigo-500 hover:text-indigo-600 ${className}`}
        title="Requires approval - Click to request access"
        {...props}
      >
        <Lock className="h-4 w-4 mr-2" />
        {children}
      </Button>

      {showModal && (
        <>
          {/* Blur Overlay */}
          <div className="fixed inset-0 bg-black/60 backdrop-blur-md flex items-center justify-center z-[70] p-4">
            <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-8 relative animate-fadeIn">
              {/* Lock Icon */}
              <div className="flex justify-center mb-6">
                <div className="bg-red-100 rounded-full p-6">
                  <Lock className="w-12 h-12 text-red-600" />
                </div>
              </div>

              {/* Title */}
              <h2 className="text-2xl font-bold text-gray-900 text-center mb-3">
                Permission Required
              </h2>

              {/* Description */}
              <p className="text-gray-600 text-center mb-6">
                You don't have access to perform this action.
                {feature && (
                  <span className="block mt-2 text-sm text-gray-500">
                    {feature.description}
                  </span>
                )}
              </p>

              {/* Feature Details */}
              {feature && (
                <div className="bg-indigo-50 rounded-lg p-4 mb-6 border border-indigo-100">
                  <div className="flex items-start space-x-3">
                    <CheckCircle className="w-5 h-5 text-indigo-600 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="font-semibold text-indigo-900 text-sm">{feature.name}</p>
                      <div className="flex items-center space-x-4 mt-2 text-xs text-indigo-600">
                        <span className="flex items-center">
                          <Clock className="w-3 h-3 mr-1" />
                          Max {feature.max_duration_hours}h
                        </span>
                        {feature.risk_level && (
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            feature.risk_level === 'CRITICAL' ? 'bg-red-100 text-red-700' :
                            feature.risk_level === 'HIGH' ? 'bg-orange-100 text-orange-700' :
                            feature.risk_level === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                            'bg-green-100 text-green-700'
                          }`}>
                            {feature.risk_level} Risk
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex space-x-3">
                <button
                  onClick={() => setShowModal(false)}
                  className="flex-1 px-6 py-3 border-2 border-gray-300 rounded-lg font-semibold text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setShowModal(false);
                    // Open the actual JIT request modal
                    window.dispatchEvent(new CustomEvent('governance:required', {
                      detail: {
                        action: featureId,
                        resource_id: resourceId
                      }
                    }));
                  }}
                  className="flex-1 px-6 py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-semibold transition-colors shadow-lg flex items-center justify-center space-x-2"
                >
                  <Lock className="w-4 h-4" />
                  <span>Request Access</span>
                </button>
              </div>

              {/* Help Text */}
              <p className="text-xs text-gray-500 text-center mt-4">
                Your request will be reviewed by your Team Lead or Organization Admin.
              </p>
            </div>
          </div>
        </>
      )}
    </>
  );
};

export default ProtectedButton;
