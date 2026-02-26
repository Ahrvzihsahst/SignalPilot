import apiClient from './client';
import type { LiveSignalsResponse, SignalHistoryFilters, SignalHistoryResponse } from '@/types/api';

export async function fetchLiveSignals(): Promise<LiveSignalsResponse> {
  const { data } = await apiClient.get<LiveSignalsResponse>('/signals/live');
  return data;
}

export async function fetchSignalHistory(filters: SignalHistoryFilters): Promise<SignalHistoryResponse> {
  const { data } = await apiClient.get<SignalHistoryResponse>('/signals/history', { params: filters });
  return data;
}
