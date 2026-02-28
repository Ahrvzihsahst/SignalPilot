import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api',
  timeout: 10_000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 503) {
      console.error('Service unavailable:', error.message);
    }
    return Promise.reject(error);
  }
);

export default apiClient;
