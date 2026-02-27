import { describe, it, expect } from 'vitest';
import { formatCurrency, formatPercent, formatDecimal } from '../formatters';

describe('formatCurrency', () => {
  it('formats positive value with + prefix', () => {
    expect(formatCurrency(1234)).toContain('+');
    expect(formatCurrency(1234)).toContain('1,234');
  });

  it('formats negative value', () => {
    expect(formatCurrency(-500)).toContain('500');
    expect(formatCurrency(-500)).not.toContain('+');
  });

  it('formats zero as positive', () => {
    expect(formatCurrency(0)).toContain('+');
  });
});

describe('formatPercent', () => {
  it('formats positive percentage', () => {
    expect(formatPercent(12.5)).toBe('+12.5%');
  });

  it('formats negative percentage', () => {
    expect(formatPercent(-5.3)).toBe('-5.3%');
  });

  it('formats zero', () => {
    expect(formatPercent(0)).toBe('+0.0%');
  });

  it('formats 100%', () => {
    expect(formatPercent(100)).toBe('+100.0%');
  });
});

describe('formatDecimal', () => {
  it('formats with default 2 places', () => {
    expect(formatDecimal(1.5555)).toBe('1.56');
  });

  it('formats with custom places', () => {
    expect(formatDecimal(1.5, 1)).toBe('1.5');
  });
});
