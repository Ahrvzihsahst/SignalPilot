import { useQuery } from '@tanstack/react-query';
import { fetchLiveSignals, fetchSignalHistory } from '@/api/signals';
import type { SignalHistoryFilters } from '@/types/api';
import { POLLING_INTERVAL_MS } from '@/utils/constants';

export function useLiveSignals() {
  return useQuery({
    queryKey: ['signals', 'live'],
    queryFn: fetchLiveSignals,
    refetchInterval: POLLING_INTERVAL_MS,
  });
}

export function useSignalHistory(filters: SignalHistoryFilters) {
  return useQuery({
    queryKey: ['signals', 'history', filters],
    queryFn: () => fetchSignalHistory(filters),
  });
}
