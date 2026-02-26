import apiClient from './client';
import type { EquityCurveResponse, DailyPnlPoint, WinRatePoint, MonthlySummary } from '@/types/api';
import type { Period } from '@/types/models';

export async function fetchEquityCurve(period: Period): Promise<EquityCurveResponse> {
  const { data } = await apiClient.get<EquityCurveResponse>('/performance/equity-curve', { params: { period } });
  return data;
}

export async function fetchDailyPnl(period: Period): Promise<DailyPnlPoint[]> {
  const { data } = await apiClient.get<DailyPnlPoint[]>('/performance/daily-pnl', { params: { period } });
  return data;
}

export async function fetchWinRate(period: Period): Promise<WinRatePoint[]> {
  const { data } = await apiClient.get<WinRatePoint[]>('/performance/win-rate', { params: { period } });
  return data;
}

export async function fetchMonthlySummary(): Promise<MonthlySummary[]> {
  const { data } = await apiClient.get<MonthlySummary[]>('/performance/monthly');
  return data;
}
