import apiClient from './client';
import type { TradesResponse, TradeFilters } from '@/types/api';

export async function fetchTrades(filters: TradeFilters): Promise<TradesResponse> {
  const { data } = await apiClient.get<TradesResponse>('/trades', { params: filters });
  return data;
}

export async function exportTradesCsv(dateFrom?: string, dateTo?: string): Promise<Blob> {
  const { data } = await apiClient.get('/trades/export', {
    params: { date_from: dateFrom, date_to: dateTo },
    responseType: 'blob',
  });
  return data;
}
