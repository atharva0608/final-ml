/**
 * RiskBadge Component
 *
 * Displays risk level with appropriate color and icon
 */
import React from 'react';
import { CheckCircle, AlertTriangle, AlertOctagon } from 'lucide-react';

const RiskBadge = ({ level }) => {
  const variants = {
    LOW: {
      className: 'bg-green-100 text-green-800 border border-green-300',
      icon: CheckCircle,
      label: 'LOW RISK'
    },
    MEDIUM: {
      className: 'bg-yellow-100 text-yellow-800 border border-yellow-300',
      icon: AlertTriangle,
      label: 'MEDIUM RISK'
    },
    HIGH: {
      className: 'bg-orange-100 text-orange-800 border border-orange-300',
      icon: AlertTriangle,
      label: 'HIGH RISK'
    },
    CRITICAL: {
      className: 'bg-red-100 text-red-800 border border-red-300',
      icon: AlertOctagon,
      label: 'CRITICAL RISK'
    }
  };

  const config = variants[level] || variants.MEDIUM;
  const Icon = config.icon;

  return (
    <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${config.className}`}>
      <Icon className="h-3.5 w-3.5 mr-1.5" />
      {config.label}
    </span>
  );
};

export default RiskBadge;
