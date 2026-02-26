import { useQuery } from '@tanstack/react-query';
import { fetchStrategyComparison, fetchConfirmedStats, fetchStrategyPnlSeries } from '@/api/strategies';

export function useStrategyComparison(period?: string) {
  return useQuery({
    queryKey: ['strategies', 'comparison', period],
    queryFn: () => fetchStrategyComparison(period),
  });
}

export function useConfirmedStats() {
  return useQuery({
    queryKey: ['strategies', 'confirmed'],
    queryFn: fetchConfirmedStats,
  });
}

export function useStrategyPnlSeries(period?: string) {
  return useQuery({
    queryKey: ['strategies', 'pnl-series', period],
    queryFn: () => fetchStrategyPnlSeries(period),
  });
}
