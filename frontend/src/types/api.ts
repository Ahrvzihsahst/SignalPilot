export interface LiveSignal {
  id: number;
  rank: number;
  symbol: string;
  strategy: string;
  entry_price: number;
  stop_loss: number;
  target_1: number;
  target_2: number;
  quantity: number;
  capital_required: number;
  signal_strength: number;
  composite_score: number | null;
  confirmation_level: string;
  confirmed_by: string | null;
  position_size_multiplier: number;
  status: string;
  current_price: number | null;
  pnl_amount: number | null;
  pnl_pct: number | null;
  reason: string;
  setup_type: string | null;
  adaptation_status: string;
  created_at: string;
}

export interface CircuitBreakerStatus {
  sl_count: number;
  sl_limit: number;
  is_active: boolean;
  is_overridden: boolean;
  triggered_at: string | null;
}

export interface LiveSignalsResponse {
  market_status: string;
  current_time: string;
  capital: number;
  positions_used: number;
  positions_max: number;
  today_pnl: number;
  today_pnl_pct: number;
  circuit_breaker: CircuitBreakerStatus;
  active_signals: LiveSignal[];
  expired_signals: LiveSignal[];
}

export interface PaginationInfo {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface TradeRecord {
  id: number;
  date: string;
  symbol: string;
  strategy: string;
  entry_price: number;
  exit_price: number | null;
  stop_loss: number;
  target_1: number;
  target_2: number;
  quantity: number;
  pnl_amount: number | null;
  pnl_pct: number | null;
  exit_reason: string | null;
  confirmation_level: string | null;
  composite_score: number | null;
  taken_at: string | null;
  exited_at: string | null;
}

export interface TradeSummary {
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_win: number;
  avg_loss: number;
  best_trade_pnl: number;
  worst_trade_pnl: number;
}

export interface TradesResponse {
  trades: TradeRecord[];
  pagination: PaginationInfo;
  summary: TradeSummary;
}

export interface TradeFilters {
  date_from?: string;
  date_to?: string;
  strategy?: string;
  result?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export interface SignalHistoryFilters {
  date_from?: string;
  date_to?: string;
  strategy?: string;
  status?: string;
  page?: number;
  page_size?: number;
}

export interface SignalHistoryResponse {
  signals: LiveSignal[];
  pagination: PaginationInfo;
}

export interface EquityCurvePoint {
  date: string;
  cumulative_pnl: number;
  capital: number;
}

export interface EquityCurveResponse {
  period: string;
  data_points: EquityCurvePoint[];
}

export interface DailyPnlPoint {
  date: string;
  pnl_amount: number;
}

export interface WinRatePoint {
  date: string;
  trade_number: number;
  win_rate: number;
}

export interface MonthlySummary {
  month: string;
  trade_count: number;
  win_rate: number;
  net_pnl: number;
}

export interface StrategyMetrics {
  strategy: string;
  win_rate: number;
  total_trades: number;
  net_pnl: number;
  avg_win: number;
  avg_loss: number;
  expectancy: number;
  profit_factor: number;
  max_consecutive_losses: number;
  capital_weight: number;
  status: string;
  is_best: boolean;
}

export interface StrategyComparisonData {
  period: string;
  strategies: StrategyMetrics[];
}

export interface ConfirmedSignalsPerformance {
  total_confirmed_trades: number;
  confirmed_win_rate: number;
  confirmed_avg_pnl: number;
  single_strategy_win_rate: number;
  single_strategy_avg_pnl: number;
}

export interface StrategyPnlSeriesPoint {
  date: string;
  gap_go: number;
  orb: number;
  vwap: number;
}

export interface AllocationItem {
  strategy: string;
  weight_pct: number;
  allocated_amount: number;
}

export interface AllocationData {
  allocations: AllocationItem[];
  reserve_pct: number;
  reserve_amount: number;
  total_capital: number;
  next_rebalance: string | null;
}

export interface AllocationHistoryPoint {
  date: string;
  gap_go: number;
  orb: number;
  vwap: number;
}

export interface RebalanceLogEntry {
  date: string;
  description: string;
  changes: string;
}

export interface AllocationWeights {
  gap_go: number;
  orb: number;
  vwap: number;
}

export interface UserSettings {
  telegram_chat_id: string;
  total_capital: number;
  max_positions: number;
  gap_go_enabled: boolean;
  orb_enabled: boolean;
  orb_paper_mode: boolean;
  vwap_enabled: boolean;
  vwap_paper_mode: boolean;
  circuit_breaker_limit: number;
  confidence_boost_enabled: boolean;
  adaptive_learning_enabled: boolean;
  auto_rebalance_enabled: boolean;
  adaptation_mode: string;
}

export interface StrategyToggles {
  gap_go_enabled?: boolean;
  orb_enabled?: boolean;
  vwap_enabled?: boolean;
}

export interface AdaptationStrategyStatus {
  strategy: string;
  adaptation_status: string;
  consecutive_losses: number;
  daily_wins: number;
  daily_losses: number;
  trailing_5d_win_rate: number | null;
  trailing_10d_win_rate: number | null;
}

export interface AdaptationStatus {
  strategies: AdaptationStrategyStatus[];
}

export interface AdaptationLogEntry {
  id: number;
  date: string;
  strategy: string;
  event_type: string;
  details: string;
  old_weight: number | null;
  new_weight: number | null;
  created_at: string;
}
