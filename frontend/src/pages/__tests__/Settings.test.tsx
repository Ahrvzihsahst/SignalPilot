import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { createElement, type ReactNode } from 'react';
import SettingsPage from '../Settings';

vi.mock('@/api/settings', () => ({
  fetchSettings: vi.fn().mockResolvedValue({
    telegram_chat_id: '12345',
    total_capital: 50000,
    max_positions: 8,
    gap_go_enabled: true,
    orb_enabled: true,
    orb_paper_mode: false,
    vwap_enabled: false,
    vwap_paper_mode: true,
    circuit_breaker_limit: 3,
    confidence_boost_enabled: true,
    adaptive_learning_enabled: true,
    auto_rebalance_enabled: true,
    adaptation_mode: 'aggressive',
  }),
  updateSettings: vi.fn(),
  updateStrategyToggles: vi.fn(),
}));

vi.mock('@/api/trades', () => ({
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

describe('Settings Page', () => {
  it('renders page title', async () => {
    render(createElement(SettingsPage), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Settings')).toBeInTheDocument());
  });

  it('renders Capital & Risk section', async () => {
    render(createElement(SettingsPage), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Capital & Risk')).toBeInTheDocument());
  });

  it('renders Strategies section', async () => {
    render(createElement(SettingsPage), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Strategies')).toBeInTheDocument());
  });

  it('renders Hybrid Scoring section', async () => {
    render(createElement(SettingsPage), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Hybrid Scoring')).toBeInTheDocument());
  });

  it('renders Data section', async () => {
    render(createElement(SettingsPage), { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Data')).toBeInTheDocument());
  });
});
