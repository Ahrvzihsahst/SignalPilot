import { useCurrentAllocation, useAllocationHistory } from '@/hooks/useAllocation';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorDisplay } from '@/components/common/ErrorDisplay';
import { DonutChart } from '@/components/allocation/DonutChart';
import { AllocationHistory } from '@/components/allocation/AllocationHistory';
import { RebalancingLog } from '@/components/allocation/RebalancingLog';
import { ManualOverride } from '@/components/allocation/ManualOverride';
import type { AllocationWeights } from '@/types/api';

export default function CapitalAllocation() {
  const allocation = useCurrentAllocation();
  const history = useAllocationHistory();

  const isLoading = allocation.isLoading || history.isLoading;
  const error = allocation.error || history.error;

  if (isLoading) return <LoadingSpinner message="Loading allocation data..." />;
  if (error) return <ErrorDisplay error={error} onRetry={() => { allocation.refetch(); history.refetch(); }} />;
  if (!allocation.data) return null;

  const currentWeights: AllocationWeights = allocation.data.allocations.reduce(
    (acc, a) => {
      const keyMap: Record<string, keyof AllocationWeights> = {
        gap_go: 'gap_go',
        ORB: 'orb',
        'VWAP Reversal': 'vwap',
      };
      const key = keyMap[a.strategy];
      if (key) acc[key] = a.weight_pct;
      return acc;
    },
    { gap_go: 0, orb: 0, vwap: 0 } as AllocationWeights
  );

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Capital Allocation</h1>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DonutChart data={allocation.data} />
        <AllocationHistory data={history.data ?? []} />
      </div>

      <ManualOverride currentWeights={currentWeights} />

      <RebalancingLog entries={[]} />
    </div>
  );
}
