import { useQuery } from '@tanstack/react-query';
import { fetchAdaptationStatus, fetchAdaptationLog } from '@/api/adaptation';
import { ADAPTATION_POLLING_INTERVAL_MS } from '@/utils/constants';

export function useAdaptationStatus() {
  return useQuery({
    queryKey: ['adaptation', 'status'],
    queryFn: fetchAdaptationStatus,
    refetchInterval: ADAPTATION_POLLING_INTERVAL_MS,
  });
}

export function useAdaptationLog(filters?: {
  strategy?: string;
  event_type?: string;
  date_from?: string;
  date_to?: string;
}) {
  return useQuery({
    queryKey: ['adaptation', 'log', filters],
    queryFn: () => fetchAdaptationLog(filters),
  });
}
