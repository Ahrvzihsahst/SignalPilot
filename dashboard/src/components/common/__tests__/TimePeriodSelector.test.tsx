import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { TimePeriodSelector } from '../TimePeriodSelector';

describe('TimePeriodSelector', () => {
  it('highlights active period with blue', () => {
    render(<TimePeriodSelector selected="1m" onChange={vi.fn()} />);
    const activeButton = screen.getByText('1M');
    expect(activeButton).toHaveClass('bg-blue-600', 'text-white');
  });

  it('calls onChange when clicking inactive period', () => {
    const onChange = vi.fn();
    render(<TimePeriodSelector selected="1m" onChange={onChange} />);
    fireEvent.click(screen.getByText('3M'));
    expect(onChange).toHaveBeenCalledWith('3m');
  });
});
