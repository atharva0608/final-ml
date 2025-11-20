import React from 'react';
import { AlertCircle } from 'lucide-react';
import Button from './Button';

const ErrorMessage = ({ message, onRetry }) => (
  <div className="bg-red-50 border-2 border-red-200 rounded-lg p-4">
    <div className="flex items-start space-x-3">
      <AlertCircle className="text-red-600 flex-shrink-0" size={20} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-red-800">Error</p>
        <p className="text-sm text-red-600 mt-1 break-words">{message}</p>
      </div>
      {onRetry && (
        <Button variant="danger" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  </div>
);

export default ErrorMessage;
