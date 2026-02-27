import { useState } from 'react';
import type { Period } from '@/types/models';
import { useEquityCurve, useDailyPnl, useWinRate, useMonthlySummary } from '@/hooks/usePerformance';
import { TimePeriodSelector } from '@/components/common/TimePeriodSelector';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EquityCurve } from '@/components/performance/EquityCurve';
import { DailyPnlChart } from '@/components/performance/DailyPnlChart';
import { WinRateTrend } from '@/components/performance/WinRateTrend';
import { MonthlySummaryTable } from '@/components/performance/MonthlySummaryTable';

export default function PerformanceCharts() {
  const [period, setPeriod] = useState<Period>('1m');

  const equity = useEquityCurve(period);
  const daily = useDailyPnl(period);
  const winRate = useWinRate(period);
  const monthly = useMonthlySummary();

  const isLoading = equity.isLoading || daily.isLoading || winRate.isLoading || monthly.isLoading;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Performance Charts</h1>
        <TimePeriodSelector selected={period} onChange={setPeriod} />
      </div>

      {isLoading ? (
        <LoadingSpinner message="Loading charts..." />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <EquityCurve data={equity.data?.data_points ?? []} />
          <DailyPnlChart data={daily.data ?? []} />
          <WinRateTrend data={winRate.data ?? []} />
          <MonthlySummaryTable data={monthly.data ?? []} />
        </div>
      )}
    </div>
  );
}
