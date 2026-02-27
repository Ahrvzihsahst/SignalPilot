import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { createElement, type ReactNode } from 'react';
import TradeJournal from '../TradeJournal';

const mockTradesResponse = {
  trades: [
    {
      id: 1, date: '2025-01-15', symbol: 'RELIANCE', strategy: 'gap_go',
      entry_price: 2500, exit_price: 2550, stop_loss: 2450, target_1: 2550, target_2: 2600,
      quantity: 10, pnl_amount: 500, pnl_pct: 2.0,
      exit_reason: 't1_hit', confirmation_level: 'single', composite_score: 72.0,
      taken_at: '2025-01-15T09:45:00', exited_at: '2025-01-15T11:30:00',
    },
    {
      id: 2, date: '2025-01-15', symbol: 'TCS', strategy: 'ORB',
      entry_price: 3800, exit_price: 3750, stop_loss: 3750, target_1: 3850, target_2: 3900,
      quantity: 5, pnl_amount: -250, pnl_pct: -1.3,
      exit_reason: 'sl_hit', confirmation_level: null, composite_score: null,
      taken_at: '2025-01-15T10:00:00', exited_at: '2025-01-15T10:45:00',
    },
  ],
  pagination: { page: 1, page_size: 20, total_items: 48, total_pages: 3 },
  summary: {
    total_trades: 48, wins: 29, losses: 19, win_rate: 60.4,
    total_pnl: 4280, avg_win: 320, avg_loss: -180, best_trade_pnl: 1200, worst_trade_pnl: -650,
  },
};

vi.mock('@/api/trades', () => ({
  fetchTrades: vi.fn().mockResolvedValue(mockTradesResponse),
  exportTradesCsv: vi.fn().mockResolvedValue(new Blob()),
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

describe('TradeJournal Page', () => {
  it('renders filter controls', async () => {
    render(createElement(TradeJournal), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('Trade Journal')).toBeInTheDocument();
    });
  });

  it('renders trade rows', async () => {
    render(createElement(TradeJournal), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('RELIANCE')).toBeInTheDocument();
      expect(screen.getByText('TCS')).toBeInTheDocument();
    });
  });

  it('renders summary stats', async () => {
    render(createElement(TradeJournal), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText(/48/)).toBeInTheDocument();
      expect(screen.getByText(/60.4%/)).toBeInTheDocument();
    });
  });

  it('renders pagination', async () => {
    render(createElement(TradeJournal), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByLabelText('Next page')).toBeInTheDocument();
    });
  });
});
