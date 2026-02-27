import { useQuery } from '@tanstack/react-query';
import { fetchEquityCurve, fetchDailyPnl, fetchWinRate, fetchMonthlySummary } from '@/api/performance';
import type { Period } from '@/types/models';

export function useEquityCurve(period: Period) {
  return useQuery({
    queryKey: ['performance', 'equity-curve', period],
    queryFn: () => fetchEquityCurve(period),
  });
}

export function useDailyPnl(period: Period) {
  return useQuery({
    queryKey: ['performance', 'daily-pnl', period],
    queryFn: () => fetchDailyPnl(period),
  });
}

export function useWinRate(period: Period) {
  return useQuery({
    queryKey: ['performance', 'win-rate', period],
    queryFn: () => fetchWinRate(period),
  });
}

export function useMonthlySummary() {
  return useQuery({
    queryKey: ['performance', 'monthly'],
    queryFn: fetchMonthlySummary,
  });
}
