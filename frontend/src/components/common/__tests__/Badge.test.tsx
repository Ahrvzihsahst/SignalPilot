import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import { Badge } from '../Badge';

describe('Badge', () => {
  it('renders confirmed variant with amber classes', () => {
    const { container } = render(<Badge variant="confirmed">Test</Badge>);
    expect(container.firstChild).toHaveClass('bg-amber-100', 'text-amber-800');
  });

  it('renders success variant with green classes', () => {
    const { container } = render(<Badge variant="success">Test</Badge>);
    expect(container.firstChild).toHaveClass('bg-green-100', 'text-green-800');
  });

  it('renders danger variant with red classes', () => {
    const { container } = render(<Badge variant="danger">Test</Badge>);
    expect(container.firstChild).toHaveClass('bg-red-100', 'text-red-800');
  });
});
