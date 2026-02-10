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
        className={`border-gray-300 text-gray-700 hover:border-blue-500 hover:text-blue-600 ${className}`}
        title="Requires approval"
        {...props}
      >
        <Lock className="h-4 w-4 mr-2" />
        {children}
      </Button>

      {showModal && (
        <JITRequestModal
          featureId={featureId}
          feature={feature}
          resourceId={resourceId}
          onClose={() => setShowModal(false)}
          onSuccess={handleModalSuccess}
        />
      )}
    </>
  );
};

export default ProtectedButton;
