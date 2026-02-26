import { useState } from 'react';
import { useStrategyComparison, useConfirmedStats, useStrategyPnlSeries } from '@/hooks/useStrategies';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorDisplay } from '@/components/common/ErrorDisplay';
import { TimePeriodSelector } from '@/components/common/TimePeriodSelector';
import { ComparisonTable } from '@/components/strategies/ComparisonTable';
import { PnlStackedChart } from '@/components/strategies/PnlStackedChart';
import { ConfirmedStats } from '@/components/strategies/ConfirmedStats';
import type { Period } from '@/types/models';

export default function StrategyComparison() {
  const [period, setPeriod] = useState<Period>('1m');

  const comparison = useStrategyComparison(period);
  const confirmedStats = useConfirmedStats();
  const pnlSeries = useStrategyPnlSeries(period);

  const isLoading = comparison.isLoading || confirmedStats.isLoading || pnlSeries.isLoading;
  const error = comparison.error || confirmedStats.error || pnlSeries.error;

  if (isLoading) return <LoadingSpinner message="Loading strategy data..." />;
  if (error) return <ErrorDisplay error={error} onRetry={() => { comparison.refetch(); confirmedStats.refetch(); pnlSeries.refetch(); }} />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Strategy Comparison</h1>
        <TimePeriodSelector selected={period} onChange={setPeriod} />
      </div>

      <div className="space-y-4">
        <ComparisonTable strategies={comparison.data?.strategies ?? []} />
        <PnlStackedChart data={pnlSeries.data ?? []} />
        {confirmedStats.data && <ConfirmedStats data={confirmedStats.data} />}
      </div>
    </div>
  );
}
