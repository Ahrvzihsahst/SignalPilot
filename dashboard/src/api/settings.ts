import apiClient from './client';
import type { UserSettings, StrategyToggles } from '@/types/api';

export async function fetchSettings(): Promise<UserSettings> {
  const { data } = await apiClient.get<UserSettings>('/settings');
  return data;
}

export async function updateSettings(updates: Partial<UserSettings>): Promise<UserSettings> {
  const { data } = await apiClient.put<UserSettings>('/settings', updates);
  return data;
}

export async function updateStrategyToggles(toggles: StrategyToggles): Promise<void> {
  await apiClient.put('/settings/strategies', toggles);
}
