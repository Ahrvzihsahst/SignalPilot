import { useState } from 'react';
import { useTrades } from '@/hooks/useTrades';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorDisplay } from '@/components/common/ErrorDisplay';
import { Pagination } from '@/components/common/Pagination';
import { TradeFilters } from '@/components/trades/TradeFilters';
import { TradeTable } from '@/components/trades/TradeTable';
import { TradeSummary } from '@/components/trades/TradeSummary';
import { ExportButton } from '@/components/trades/ExportButton';
import type { TradeFilterState } from '@/types/models';

const DEFAULT_FILTERS: TradeFilterState = {
  dateFrom: '',
  dateTo: '',
  strategy: '',
  result: '',
  search: '',
  page: 1,
  pageSize: 20,
};

export default function TradeJournal() {
  const [filters, setFilters] = useState<TradeFilterState>(DEFAULT_FILTERS);

  const { data, isLoading, error, refetch } = useTrades({
    date_from: filters.dateFrom || undefined,
    date_to: filters.dateTo || undefined,
    strategy: filters.strategy || undefined,
    result: filters.result || undefined,
    search: filters.search || undefined,
    page: filters.page,
    page_size: filters.pageSize,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Trade Journal</h1>
        <ExportButton dateFrom={filters.dateFrom || undefined} dateTo={filters.dateTo || undefined} />
      </div>

      <TradeFilters filters={filters} onChange={setFilters} />

      {isLoading ? (
        <LoadingSpinner message="Loading trades..." />
      ) : error ? (
        <ErrorDisplay error={error} onRetry={refetch} />
      ) : data ? (
        <>
          <TradeTable trades={data.trades} />
          <div className="flex items-center justify-between">
            <TradeSummary summary={data.summary} />
          </div>
          <div className="flex justify-center">
            <Pagination
              page={data.pagination.page}
              totalPages={data.pagination.total_pages}
              onPageChange={(p) => setFilters((f) => ({ ...f, page: p }))}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
