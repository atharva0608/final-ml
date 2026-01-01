/**
 * Utility Functions for Formatting
 */
import { format, formatDistanceToNow } from 'date-fns';

/**
 * Format currency
 */
export const formatCurrency = (amount, currency = 'USD') => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
};

/**
 * Format number with commas
 */
export const formatNumber = (number) => {
  return new Intl.NumberFormat('en-US').format(number);
};

/**
 * Format percentage
 */
export const formatPercentage = (value, decimals = 1) => {
  return `${value.toFixed(decimals)}%`;
};

/**
 * Format date
 */
export const formatDate = (date) => {
  if (!date) return 'N/A';
  return format(new Date(date), 'MMM dd, yyyy');
};

/**
 * Format datetime
 */
export const formatDateTime = (date) => {
  if (!date) return 'N/A';
  return format(new Date(date), 'MMM dd, yyyy HH:mm');
};

/**
 * Format relative time (e.g., "2 hours ago")
 */
export const formatRelativeTime = (date) => {
  if (!date) return 'N/A';
  return formatDistanceToNow(new Date(date), { addSuffix: true });
};

/**
 * Format file size
 */
export const formatFileSize = (bytes) => {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
};

/**
 * Truncate text with ellipsis
 */
export const truncate = (str, length = 50) => {
  if (!str) return '';
  return str.length > length ? str.substring(0, length) + '...' : str;
};

/**
 * Capitalize first letter
 */
export const capitalize = (str) => {
  if (!str) return '';
  return str.charAt(0).toUpperCase() + str.slice(1).toLowerCase();
};

/**
 * Format instance state badge color
 */
export const getStatusColor = (status) => {
  const colors = {
    running: 'green',
    active: 'green',
    pending: 'yellow',
    stopping: 'orange',
    stopped: 'red',
    terminated: 'gray',
    error: 'red',
    completed: 'green',
    draft: 'blue',
    cancelled: 'gray',
  };
  return colors[status?.toLowerCase()] || 'gray';
};

/**
 * Get lifecycle badge color
 */
export const getLifecycleColor = (lifecycle) => {
  return lifecycle === 'spot' ? 'purple' : 'blue';
};

/**
 * Format cluster type
 */
export const formatClusterType = (type) => {
  const types = {
    EKS: 'Amazon EKS',
    SELF_MANAGED: 'Self-Managed',
  };
  return types[type] || type;
};
