import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { createElement, type ReactNode, Suspense } from 'react';
import LiveSignals from '../LiveSignals';

const mockData = {
  market_status: 'open',
  current_time: '2025-01-15T10:30:00+05:30',
  capital: 50000,
  positions_used: 3,
  positions_max: 8,
  today_pnl: 450,
  today_pnl_pct: 0.9,
  circuit_breaker: { sl_count: 1, sl_limit: 3, is_active: false, is_overridden: false, triggered_at: null },
  active_signals: [
    {
      id: 1, rank: 1, symbol: 'RELIANCE', strategy: 'gap_go',
      entry_price: 2500, stop_loss: 2450, target_1: 2550, target_2: 2600,
      quantity: 10, capital_required: 25000, signal_strength: 4,
      composite_score: 85.0, confirmation_level: 'double',
      confirmed_by: 'Gap & Go,ORB', position_size_multiplier: 1.5,
      status: 'sent', current_price: 2520, pnl_amount: 200, pnl_pct: 0.8,
      reason: 'Gap up 3.5% with volume', setup_type: null, adaptation_status: 'normal',
      created_at: '2025-01-15T09:30:00+05:30',
    },
    {
      id: 2, rank: 2, symbol: 'TCS', strategy: 'ORB',
      entry_price: 3800, stop_loss: 3750, target_1: 3850, target_2: 3900,
      quantity: 5, capital_required: 19000, signal_strength: 3,
      composite_score: 72.0, confirmation_level: 'single',
      confirmed_by: null, position_size_multiplier: 1.0,
      status: 'taken', current_price: 3820, pnl_amount: 100, pnl_pct: 0.5,
      reason: 'ORB breakout above 30m range', setup_type: null, adaptation_status: 'normal',
      created_at: '2025-01-15T09:50:00+05:30',
    },
  ],
  expired_signals: [
    {
      id: 3, rank: 3, symbol: 'INFY', strategy: 'VWAP Reversal',
      entry_price: 1600, stop_loss: 1580, target_1: 1620, target_2: 1640,
      quantity: 15, capital_required: 24000, signal_strength: 2,
      composite_score: 55.0, confirmation_level: 'single',
      confirmed_by: null, position_size_multiplier: 1.0,
      status: 'expired', current_price: null, pnl_amount: null, pnl_pct: null,
      reason: 'VWAP bounce', setup_type: null, adaptation_status: 'normal',
      created_at: '2025-01-15T10:15:00+05:30',
    },
  ],
};

vi.mock('@/api/signals', () => ({
  fetchLiveSignals: vi.fn().mockResolvedValue(mockData),
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

describe('LiveSignals Page', () => {
  it('renders market status', async () => {
    render(createElement(LiveSignals), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText(/Market Open/i)).toBeInTheDocument());
  });

  it('renders capital display', async () => {
    render(createElement(LiveSignals), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText(/50,000/)).toBeInTheDocument());
  });

  it('renders positions count', async () => {
    render(createElement(LiveSignals), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Positions: 3/8')).toBeInTheDocument());
  });

  it('renders 2 active signal cards', async () => {
    render(createElement(LiveSignals), { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('RELIANCE')).toBeInTheDocument();
      expect(screen.getByText('TCS')).toBeInTheDocument();
    });
  });

  it('shows CONFIRMED badge for double confirmation', async () => {
    render(createElement(LiveSignals), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('CONFIRMED')).toBeInTheDocument());
  });

  it('renders expired signals section', async () => {
    render(createElement(LiveSignals), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('INFY')).toBeInTheDocument());
  });

  it('renders circuit breaker status', async () => {
    render(createElement(LiveSignals), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText(/1\/3 SL/)).toBeInTheDocument());
  });

  it('expands signal details on click', async () => {
    render(createElement(LiveSignals), { wrapper: createWrapper() });
    await waitFor(() => screen.getByText('RELIANCE'));
    const detailsButton = screen.getAllByText('Details')[0];
    fireEvent.click(detailsButton);
    await waitFor(() => expect(screen.getByText(/Gap up 3.5%/)).toBeInTheDocument());
  });
});
