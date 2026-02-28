import { useState } from 'react';
import type { AllocationWeights } from '@/types/api';
import { Card } from '@/components/common/Card';
import { useOverrideAllocation, useResetAllocation } from '@/hooks/useAllocation';

interface ManualOverrideProps {
  currentWeights: AllocationWeights;
}

export function ManualOverride({ currentWeights }: ManualOverrideProps) {
  const [weights, setWeights] = useState<AllocationWeights>({
    gap_go: currentWeights.gap_go,
    orb: currentWeights.orb,
    vwap: currentWeights.vwap,
  });

  const overrideMutation = useOverrideAllocation();
  const resetMutation = useResetAllocation();

  const total = weights.gap_go + weights.orb + weights.vwap;
  const isValid = total <= 80 && weights.gap_go >= 0 && weights.orb >= 0 && weights.vwap >= 0;

  const handleUpdate = (key: keyof AllocationWeights, value: string) => {
    const num = parseFloat(value) || 0;
    setWeights((prev) => ({ ...prev, [key]: num }));
  };

  const handleApply = () => {
    if (isValid) overrideMutation.mutate(weights);
  };

  const handleReset = () => {
    resetMutation.mutate(undefined, {
      onSuccess: () => {
        setWeights({ gap_go: currentWeights.gap_go, orb: currentWeights.orb, vwap: currentWeights.vwap });
      },
    });
  };

  return (
    <Card title="Manual Allocation Override">
      <p className="mb-4 text-xs text-gray-500">
        Set custom weights for each strategy. Total must not exceed 80%. Remaining capital is held
        as reserve.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {(
          [
            { key: 'gap_go', label: 'Gap & Go (%)' },
            { key: 'orb', label: 'ORB (%)' },
            { key: 'vwap', label: 'VWAP Reversal (%)' },
          ] as { key: keyof AllocationWeights; label: string }[]
        ).map(({ key, label }) => (
          <div key={key} className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">{label}</label>
            <input
              type="number"
              min={0}
              max={80}
              step={5}
              value={weights[key]}
              onChange={(e) => handleUpdate(key, e.target.value)}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
        ))}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <p className={`text-sm ${total > 80 ? 'text-red-600 font-medium' : 'text-gray-600'}`}>
          Total: {total.toFixed(1)}% {total > 80 && '— exceeds 80% limit'}
        </p>
        <div className="flex gap-2">
          <button
            onClick={handleReset}
            disabled={resetMutation.isPending}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
          >
            {resetMutation.isPending ? 'Resetting...' : 'Reset to Auto'}
          </button>
          <button
            onClick={handleApply}
            disabled={!isValid || overrideMutation.isPending}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {overrideMutation.isPending ? 'Applying...' : 'Apply'}
          </button>
        </div>
      </div>

      {overrideMutation.isSuccess && (
        <p className="mt-2 text-xs text-green-600">Allocation updated successfully.</p>
      )}
      {(overrideMutation.isError || resetMutation.isError) && (
        <p className="mt-2 text-xs text-red-600">An error occurred. Please try again.</p>
      )}
    </Card>
  );
}
