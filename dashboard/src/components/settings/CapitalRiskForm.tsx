import { useState } from 'react';
import type { UserSettings } from '@/types/api';
import { Card } from '@/components/common/Card';
import { useUpdateSettings } from '@/hooks/useSettings';

interface CapitalRiskFormProps {
  settings: UserSettings;
}

export function CapitalRiskForm({ settings }: CapitalRiskFormProps) {
  const [capital, setCapital] = useState(settings.total_capital);
  const [maxPositions, setMaxPositions] = useState(settings.max_positions);
  const [cbLimit, setCbLimit] = useState(settings.circuit_breaker_limit);

  const { mutate, isPending, isSuccess, isError } = useUpdateSettings();

  return (
    <Card title="Capital & Risk">
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Total Capital (₹)</label>
            <div className="flex gap-2">
              <input
                type="number"
                min={10000}
                step={10000}
                value={capital}
                onChange={(e) => setCapital(parseFloat(e.target.value) || 0)}
                className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
              />
              <button
                onClick={() => mutate({ total_capital: capital })}
                disabled={isPending}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                Update
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Max Positions</label>
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                max={20}
                value={maxPositions}
                onChange={(e) => setMaxPositions(parseInt(e.target.value) || 1)}
                className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
              />
              <button
                onClick={() => mutate({ max_positions: maxPositions })}
                disabled={isPending}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                Update
              </button>
            </div>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-600">Circuit Breaker (SL count)</label>
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                max={10}
                value={cbLimit}
                onChange={(e) => setCbLimit(parseInt(e.target.value) || 1)}
                className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
              />
              <button
                onClick={() => mutate({ circuit_breaker_limit: cbLimit })}
                disabled={isPending}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                Update
              </button>
            </div>
          </div>
        </div>

        {isSuccess && <p className="text-xs text-green-600">Settings updated successfully.</p>}
        {isError && <p className="text-xs text-red-600">Failed to update settings.</p>}
      </div>
    </Card>
  );
}
