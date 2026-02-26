import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { createElement, type ReactNode } from 'react';
import StrategyComparison from '../StrategyComparison';

vi.mock('@/api/strategies', () => ({
  fetchStrategyComparison: vi.fn().mockResolvedValue({
    period: '30d',
    strategies: [
      { strategy: 'gap_go', win_rate: 57, total_trades: 20, net_pnl: 1500, avg_win: 300, avg_loss: -150, expectancy: 2.5, profit_factor: 1.8, max_consecutive_losses: 3, capital_weight: 35, status: 'live', is_best: false },
      { strategy: 'ORB', win_rate: 63, total_trades: 15, net_pnl: 2100, avg_win: 350, avg_loss: -180, expectancy: 3.2, profit_factor: 2.1, max_consecutive_losses: 2, capital_weight: 25, status: 'live', is_best: false },
      { strategy: 'VWAP Reversal', win_rate: 68, total_trades: 12, net_pnl: 1800, avg_win: 280, avg_loss: -120, expectancy: 3.8, profit_factor: 2.5, max_consecutive_losses: 2, capital_weight: 20, status: 'live', is_best: true },
    ],
  }),
  fetchConfirmedStats: vi.fn().mockResolvedValue({
    total_confirmed_trades: 8, confirmed_win_rate: 75, confirmed_avg_pnl: 420,
    single_strategy_win_rate: 58, single_strategy_avg_pnl: 180,
  }),
  fetchStrategyPnlSeries: vi.fn().mockResolvedValue([]),
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

describe('StrategyComparison Page', () => {
  it('renders page title', async () => {
    render(createElement(StrategyComparison), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Strategy Comparison')).toBeInTheDocument());
  });

  it('renders confirmed stats section', async () => {
    render(createElement(StrategyComparison), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText(/Confirmed Signals/i)).toBeInTheDocument());
  });
});
