import apiClient from './client';
import type { StrategyComparisonData, ConfirmedSignalsPerformance, StrategyPnlSeriesPoint } from '@/types/api';

export async function fetchStrategyComparison(period?: string): Promise<StrategyComparisonData> {
  const { data } = await apiClient.get<{
    strategies: Array<{
      strategy: string; total_signals: number; total_trades: number; wins: number; losses: number;
      win_rate: number; total_pnl: number; avg_win: number; avg_loss: number; expectancy: number;
      capital_weight_pct: number;
    }>;
  }>('/strategies/comparison', { params: { period } });
  return {
    strategies: data.strategies.map((s) => ({
      strategy: s.strategy,
      total_signals: s.total_signals,
      total_trades: s.total_trades,
      wins: s.wins,
      losses: s.losses,
      win_rate: s.win_rate,
      total_pnl: s.total_pnl,
      avg_win: s.avg_win,
      avg_loss: s.avg_loss,
      expectancy: s.expectancy,
      capital_weight_pct: s.capital_weight_pct,
    })),
  };
}

export async function fetchConfirmedStats(): Promise<ConfirmedSignalsPerformance> {
  const { data } = await apiClient.get<{
    single_signals: number; single_win_rate: number; single_avg_pnl: number;
    multi_signals: number; multi_win_rate: number; multi_avg_pnl: number;
  }>('/strategies/confirmed');
  return {
    total_confirmed_trades: data.multi_signals,
    confirmed_win_rate: data.multi_win_rate,
    confirmed_avg_pnl: data.multi_avg_pnl,
    single_strategy_win_rate: data.single_win_rate,
    single_strategy_avg_pnl: data.single_avg_pnl,
  };
}

export async function fetchStrategyPnlSeries(period?: string): Promise<StrategyPnlSeriesPoint[]> {
  const { data } = await apiClient.get<{ data: Array<{ date: string; strategy: string; pnl: number }> }>(
    '/strategies/pnl-series',
    { params: { period } }
  );
  const byDate = new Map<string, StrategyPnlSeriesPoint>();
  for (const pt of data.data) {
    if (!byDate.has(pt.date)) {
      byDate.set(pt.date, { date: pt.date, gap_go: 0, orb: 0, vwap: 0 });
    }
    const row = byDate.get(pt.date)!;
    if (pt.strategy === 'gap_go' || pt.strategy === 'Gap & Go') row.gap_go = pt.pnl;
    else if (pt.strategy === 'ORB') row.orb = pt.pnl;
    else if (pt.strategy === 'VWAP Reversal') row.vwap = pt.pnl;
  }
  return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));
}
