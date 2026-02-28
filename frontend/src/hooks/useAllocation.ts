import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchCurrentAllocation, fetchAllocationHistory, overrideAllocation, resetAllocation } from '@/api/allocation';
import type { AllocationWeights } from '@/types/api';

export function useCurrentAllocation() {
  return useQuery({
    queryKey: ['allocation', 'current'],
    queryFn: fetchCurrentAllocation,
  });
}

export function useAllocationHistory() {
  return useQuery({
    queryKey: ['allocation', 'history'],
    queryFn: fetchAllocationHistory,
  });
}

export function useOverrideAllocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (weights: AllocationWeights) => overrideAllocation(weights),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['allocation'] });
    },
  });
}

export function useResetAllocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: resetAllocation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['allocation'] });
    },
  });
}
