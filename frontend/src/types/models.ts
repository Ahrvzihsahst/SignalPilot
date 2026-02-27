export interface TradeFilterState {
  dateFrom: string;
  dateTo: string;
  strategy: string;
  result: string;
  search: string;
  page: number;
  pageSize: number;
}

export type Period = '1w' | '1m' | '3m' | 'all';
