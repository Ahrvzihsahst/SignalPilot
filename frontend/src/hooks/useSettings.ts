import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchSettings, updateSettings, updateStrategyToggles } from '@/api/settings';
import type { UserSettings, StrategyToggles } from '@/types/api';

export function useSettings() {
  return useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (updates: Partial<UserSettings>) => updateSettings(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['signals', 'live'] });
    },
  });
}

export function useUpdateStrategyToggles() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (toggles: StrategyToggles) => updateStrategyToggles(toggles),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      queryClient.invalidateQueries({ queryKey: ['signals', 'live'] });
    },
  });
}
