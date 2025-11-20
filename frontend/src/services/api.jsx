import APIClient from './apiClient';
import { API_CONFIG } from '../config/api';

const api = new APIClient(API_CONFIG.BASE_URL);

export default api;
