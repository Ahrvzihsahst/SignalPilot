import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Sidebar } from '../Sidebar';

describe('Sidebar', () => {
  it('renders all 6 navigation links', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );
    expect(screen.getByText('Live Signals')).toBeInTheDocument();
    expect(screen.getByText('Trade Journal')).toBeInTheDocument();
    expect(screen.getByText('Performance')).toBeInTheDocument();
    expect(screen.getByText('Strategies')).toBeInTheDocument();
    expect(screen.getByText('Allocation')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
  });

  it('renders SignalPilot brand name', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>
    );
    expect(screen.getByText('SignalPilot')).toBeInTheDocument();
  });

  it('highlights active link', () => {
    render(
      <MemoryRouter initialEntries={['/trades']}>
        <Sidebar />
      </MemoryRouter>
    );
    const tradeLink = screen.getByText('Trade Journal').closest('a');
    expect(tradeLink).toHaveClass('bg-blue-50');
  });
});
