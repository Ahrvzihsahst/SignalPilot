import apiClient from './client';
import type { StrategyComparisonData, ConfirmedSignalsPerformance, StrategyPnlSeriesPoint } from '@/types/api';

export async function fetchStrategyComparison(period?: string): Promise<StrategyComparisonData> {
  const { data } = await apiClient.get<StrategyComparisonData>('/strategies/comparison', { params: { period } });
  return data;
}

export async function fetchConfirmedStats(): Promise<ConfirmedSignalsPerformance> {
  const { data } = await apiClient.get<ConfirmedSignalsPerformance>('/strategies/confirmed');
  return data;
}

export async function fetchStrategyPnlSeries(period?: string): Promise<StrategyPnlSeriesPoint[]> {
  const { data } = await apiClient.get<StrategyPnlSeriesPoint[]>('/strategies/pnl-series', { params: { period } });
  return data;
}
