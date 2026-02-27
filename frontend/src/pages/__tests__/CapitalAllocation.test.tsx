import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { createElement, type ReactNode } from 'react';
import CapitalAllocation from '../CapitalAllocation';

vi.mock('@/api/allocation', () => ({
  fetchCurrentAllocation: vi.fn().mockResolvedValue({
    allocations: [
      { strategy: 'gap_go', weight_pct: 35, allocated_amount: 17500 },
      { strategy: 'ORB', weight_pct: 25, allocated_amount: 12500 },
      { strategy: 'VWAP Reversal', weight_pct: 20, allocated_amount: 10000 },
    ],
    reserve_pct: 20, reserve_amount: 10000, total_capital: 50000, next_rebalance: '2025-01-19',
  }),
  fetchAllocationHistory: vi.fn().mockResolvedValue([]),
  overrideAllocation: vi.fn(),
  resetAllocation: vi.fn(),
}));

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      QueryClientProvider,
      { client: queryClient },
      createElement(MemoryRouter, null, children)
    );
  };
}

describe('CapitalAllocation Page', () => {
  it('renders page title', async () => {
    render(createElement(CapitalAllocation), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Capital Allocation')).toBeInTheDocument());
  });

  it('renders manual override section', async () => {
    render(createElement(CapitalAllocation), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Manual Override')).toBeInTheDocument());
  });
});
