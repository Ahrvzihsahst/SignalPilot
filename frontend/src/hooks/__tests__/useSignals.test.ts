import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement, type ReactNode } from 'react';
import { useLiveSignals } from '../useSignals';

vi.mock('@/api/signals', () => ({
  fetchLiveSignals: vi.fn().mockResolvedValue({
    market_status: 'open',
    current_time: '2025-01-15T10:00:00',
    capital: 50000,
    positions_used: 3,
    positions_max: 8,
    today_pnl: 450,
    today_pnl_pct: 0.9,
    circuit_breaker: { sl_count: 0, sl_limit: 3, is_active: false, is_overridden: false },
    active_signals: [],
    expired_signals: [],
  }),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe('useLiveSignals', () => {
  it('returns data after successful fetch', async () => {
    const { result } = renderHook(() => useLiveSignals(), { wrapper: createWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.market_status).toBe('open');
    expect(result.current.data?.capital).toBe(50000);
  });
});
