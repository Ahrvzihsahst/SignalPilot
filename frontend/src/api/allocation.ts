import apiClient from './client';
import type { AllocationData, AllocationHistoryPoint, AllocationWeights } from '@/types/api';

export async function fetchCurrentAllocation(): Promise<AllocationData> {
  const { data } = await apiClient.get<AllocationData>('/allocation/current');
  return data;
}

export async function fetchAllocationHistory(): Promise<AllocationHistoryPoint[]> {
  const { data } = await apiClient.get<AllocationHistoryPoint[]>('/allocation/history');
  return data;
}

export async function overrideAllocation(weights: AllocationWeights): Promise<AllocationData> {
  const { data } = await apiClient.post<AllocationData>('/allocation/override', weights);
  return data;
}

export async function resetAllocation(): Promise<AllocationData> {
  const { data } = await apiClient.post<AllocationData>('/allocation/reset');
  return data;
}
