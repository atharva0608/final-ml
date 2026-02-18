/**
 * Hibernation API Service
 */
import api from './api';

const BASE = '/api/v1/hibernation';

export const hibernationApi = {
  // List schedules
  listSchedules: (params = {}) => 
    api.get(`${BASE}/schedules`, { params }),
  
  // Get schedule by ID
  getSchedule: (id) => 
    api.get(`${BASE}/schedules/${id}`),
  
  // Create schedule
  createSchedule: (data) => 
    api.post(`${BASE}/schedules`, data),
  
  // Update schedule
  updateSchedule: (id, data) => 
    api.put(`${BASE}/schedules/${id}`, data),
  
  // Delete schedule
  deleteSchedule: (id) => 
    api.delete(`${BASE}/schedules/${id}`),
  
  // Toggle active status
  toggleSchedule: (id, isActive) => 
    api.post(`${BASE}/schedules/${id}/toggle?is_active=${isActive}`),
  
  // Compare strategies
  compareStrategies: () => 
    api.get(`${BASE}/strategies/compare`),
  
  // Estimate savings
  estimateSavings: (id) => 
    api.get(`${BASE}/schedules/${id}/savings`)
};

// Schedule matrix helpers
export const generateScheduleMatrix = (preset = 'weekends') => {
  const matrix = new Array(168).fill('0');
  
  if (preset === 'weekends') {
    for (let day = 5; day <= 6; day++) {
      for (let hour = 0; hour < 24; hour++) {
        matrix[day * 24 + hour] = '1';
      }
    }
  } else if (preset === 'nights') {
    for (let day = 0; day <= 4; day++) {
      for (let hour = 0; hour < 8; hour++) {
        matrix[day * 24 + hour] = '1';
      }
      for (let hour = 18; hour < 24; hour++) {
        matrix[day * 24 + hour] = '1';
      }
    }
  } else if (preset === 'business_hours') {
    matrix.fill('1');
    for (let day = 0; day <= 4; day++) {
      for (let hour = 9; hour < 17; hour++) {
        matrix[day * 24 + hour] = '0';
      }
    }
  }
  
  return matrix.join('');
};

export const formatTimeUntil = (targetTime) => {
  if (!targetTime) return 'N/A';
  const now = new Date();
  const target = new Date(targetTime);
  const diff = target - now;
  
  if (diff < 0) return 'Now';
  
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
  
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};
