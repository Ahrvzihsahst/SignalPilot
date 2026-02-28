import apiClient from './client';
import type { EquityCurvePoint, DailyPnlPoint, WinRatePoint, MonthlySummary } from '@/types/api';
import type { Period } from '@/types/models';

export async function fetchEquityCurve(period: Period): Promise<EquityCurvePoint[]> {
  const { data } = await apiClient.get<{ data: EquityCurvePoint[] }>('/performance/equity-curve', { params: { period } });
  return data.data;
}

export async function fetchDailyPnl(period: Period): Promise<DailyPnlPoint[]> {
  const { data } = await apiClient.get<{ data: Array<{ date: string; pnl: number }> }>('/performance/daily-pnl', { params: { period } });
  return data.data.map((pt) => ({ date: pt.date, pnl_amount: pt.pnl }));
}

export async function fetchWinRate(period: Period): Promise<WinRatePoint[]> {
  const { data } = await apiClient.get<{ data: Array<{ date: string; win_rate: number; trades_count: number }> }>('/performance/win-rate', { params: { period } });
  return data.data.map((pt) => ({ date: pt.date, win_rate: pt.win_rate, trade_number: pt.trades_count }));
}

export async function fetchMonthlySummary(): Promise<MonthlySummary[]> {
  const { data } = await apiClient.get<{ data: Array<{ month: string; total_pnl: number; trades_count: number; win_rate: number }> }>('/performance/monthly');
  return data.data.map((pt) => ({ month: pt.month, trade_count: pt.trades_count, win_rate: pt.win_rate, net_pnl: pt.total_pnl }));
}
