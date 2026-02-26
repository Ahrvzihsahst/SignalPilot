import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StarRating } from '../StarRating';

describe('StarRating', () => {
  it('renders correct number of filled stars for stars=3', () => {
    const { container } = render(<StarRating stars={3} />);
    const stars = container.querySelectorAll('svg');
    expect(stars).toHaveLength(5);
    const filled = container.querySelectorAll('.fill-yellow-400');
    expect(filled).toHaveLength(3);
  });

  it('renders all filled for stars=5', () => {
    const { container } = render(<StarRating stars={5} />);
    const filled = container.querySelectorAll('.fill-yellow-400');
    expect(filled).toHaveLength(5);
  });

  it('has accessibility aria-label', () => {
    render(<StarRating stars={3} />);
    const el = screen.getByLabelText('3 out of 5 stars');
    expect(el).toBeInTheDocument();
  });
});
