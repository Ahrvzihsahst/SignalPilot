import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { PnlDisplay } from '../PnlDisplay';

describe('PnlDisplay', () => {
  it('uses green class for positive amount', () => {
    const { container } = render(<PnlDisplay amount={100} />);
    expect(container.firstChild).toHaveClass('text-green-600');
  });

  it('uses red class for negative amount', () => {
    const { container } = render(<PnlDisplay amount={-50} />);
    expect(container.firstChild).toHaveClass('text-red-600');
  });

  it('displays percentage when pct provided', () => {
    const { container } = render(<PnlDisplay amount={100} pct={5.2} />);
    expect(container.textContent).toContain('5.2%');
  });
});
