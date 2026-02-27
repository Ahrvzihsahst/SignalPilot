import apiClient from './client';
import type { CircuitBreakerStatus } from '@/types/api';

export async function fetchCircuitBreakerStatus(): Promise<CircuitBreakerStatus> {
  const { data } = await apiClient.get<CircuitBreakerStatus>('/circuit-breaker');
  return data;
}

export async function overrideCircuitBreaker(): Promise<CircuitBreakerStatus> {
  const { data } = await apiClient.post<CircuitBreakerStatus>('/circuit-breaker/override');
  return data;
}
