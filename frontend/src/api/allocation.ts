import apiClient from './client';
import type { AllocationData, AllocationHistoryPoint, AllocationWeights } from '@/types/api';

export async function fetchCurrentAllocation(): Promise<AllocationData> {
  const { data } = await apiClient.get<{
    total_capital: number;
    allocations: Array<{ strategy: string; weight_pct: number; capital_allocated: number }>;
  }>('/allocation/current');
  const totalWeight = data.allocations.reduce((sum, a) => sum + a.weight_pct, 0);
  const reservePct = Math.max(0, Math.round((100 - totalWeight) * 100) / 100);
  return {
    total_capital: data.total_capital,
    allocations: data.allocations.map((a) => ({
      strategy: a.strategy,
      weight_pct: a.weight_pct,
      allocated_amount: a.capital_allocated,
    })),
    reserve_pct: reservePct,
    reserve_amount: Math.round((data.total_capital * reservePct / 100) * 100) / 100,
    next_rebalance: null,
  };
}

export async function fetchAllocationHistory(): Promise<AllocationHistoryPoint[]> {
  const { data } = await apiClient.get<{
    data: Array<{ date: string; strategy: string; weight_pct: number }>;
  }>('/allocation/history');
  const byDate = new Map<string, AllocationHistoryPoint>();
  for (const pt of data.data) {
    if (!byDate.has(pt.date)) {
      byDate.set(pt.date, { date: pt.date, gap_go: 0, orb: 0, vwap: 0 });
    }
    const row = byDate.get(pt.date)!;
    if (pt.strategy === 'gap_go' || pt.strategy === 'Gap & Go') row.gap_go = pt.weight_pct / 100;
    else if (pt.strategy === 'ORB') row.orb = pt.weight_pct / 100;
    else if (pt.strategy === 'VWAP Reversal') row.vwap = pt.weight_pct / 100;
  }
  return Array.from(byDate.values()).sort((a, b) => a.date.localeCompare(b.date));
}

export async function overrideAllocation(weights: AllocationWeights): Promise<AllocationData> {
  const stratMap: Record<string, string> = { gap_go: 'gap_go', orb: 'ORB', vwap: 'VWAP Reversal' };
  for (const [key, value] of Object.entries(weights)) {
    const strategy = stratMap[key];
    if (strategy) {
      await apiClient.post('/allocation/override', { strategy, weight_pct: value });
    }
  }
  return fetchCurrentAllocation();
}

export async function resetAllocation(): Promise<AllocationData> {
  await apiClient.post('/allocation/reset');
  return fetchCurrentAllocation();
}
