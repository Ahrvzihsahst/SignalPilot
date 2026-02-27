import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { createElement, type ReactNode } from 'react';
import PerformanceCharts from '../PerformanceCharts';

vi.mock('@/api/performance', () => ({
  fetchEquityCurve: vi.fn().mockResolvedValue({
    period: '1m',
    data_points: [
      { date: '2025-01-01', cumulative_pnl: 0, capital: 50000 },
      { date: '2025-01-10', cumulative_pnl: 1500, capital: 51500 },
    ],
  }),
  fetchDailyPnl: vi.fn().mockResolvedValue([
    { date: '2025-01-14', pnl_amount: 300 },
    { date: '2025-01-15', pnl_amount: -100 },
  ]),
  fetchWinRate: vi.fn().mockResolvedValue([
    { date: '2025-01-10', trade_number: 10, win_rate: 55 },
    { date: '2025-01-15', trade_number: 20, win_rate: 62 },
  ]),
  fetchMonthlySummary: vi.fn().mockResolvedValue([
    { month: '2025-01', trade_count: 48, win_rate: 60.4, net_pnl: 4280 },
    { month: '2024-12', trade_count: 35, win_rate: 54.2, net_pnl: 2100 },
  ]),
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

describe('PerformanceCharts Page', () => {
  it('renders page title', async () => {
    render(createElement(PerformanceCharts), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Performance')).toBeInTheDocument());
  });

  it('renders equity curve card', async () => {
    render(createElement(PerformanceCharts), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Equity Curve')).toBeInTheDocument());
  });

  it('renders daily P&L card', async () => {
    render(createElement(PerformanceCharts), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Daily P&L')).toBeInTheDocument());
  });

  it('renders monthly summary', async () => {
    render(createElement(PerformanceCharts), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Monthly Summary')).toBeInTheDocument());
  });

  it('renders period selector with 4 options', async () => {
    render(createElement(PerformanceCharts), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('1W')).toBeInTheDocument();
      expect(screen.getByText('1M')).toBeInTheDocument();
      expect(screen.getByText('3M')).toBeInTheDocument();
      expect(screen.getByText('ALL')).toBeInTheDocument();
    });
  });
});
