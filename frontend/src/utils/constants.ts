export const STRATEGY_NAMES = ['gap_go', 'ORB', 'VWAP Reversal'] as const;

export const STRATEGY_DISPLAY_NAMES: Record<string, string> = {
  gap_go: 'Gap & Go',
  ORB: 'ORB',
  'VWAP Reversal': 'VWAP Reversal',
};

export const STRATEGY_COLORS: Record<string, string> = {
  gap_go: '#3b82f6',
  ORB: '#8b5cf6',
  'VWAP Reversal': '#06b6d4',
  reserve: '#9ca3af',
};

export const POLLING_INTERVAL_MS = 30_000;
export const ADAPTATION_POLLING_INTERVAL_MS = 60_000;
