import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchCircuitBreakerStatus, overrideCircuitBreaker } from '@/api/circuitBreaker';
import { POLLING_INTERVAL_MS } from '@/utils/constants';

export function useCircuitBreakerStatus() {
  return useQuery({
    queryKey: ['circuit-breaker'],
    queryFn: fetchCircuitBreakerStatus,
    refetchInterval: POLLING_INTERVAL_MS,
  });
}

export function useOverrideCircuitBreaker() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: overrideCircuitBreaker,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['circuit-breaker'] });
      queryClient.invalidateQueries({ queryKey: ['signals', 'live'] });
    },
  });
}
