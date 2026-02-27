import apiClient from './client';
import type { AdaptationStatus, AdaptationLogEntry } from '@/types/api';

export async function fetchAdaptationStatus(): Promise<AdaptationStatus> {
  const { data } = await apiClient.get<AdaptationStatus>('/adaptation/status');
  return data;
}

export async function fetchAdaptationLog(filters?: {
  strategy?: string;
  event_type?: string;
  date_from?: string;
  date_to?: string;
}): Promise<AdaptationLogEntry[]> {
  const { data } = await apiClient.get<AdaptationLogEntry[]>('/adaptation/log', { params: filters });
  return data;
}
