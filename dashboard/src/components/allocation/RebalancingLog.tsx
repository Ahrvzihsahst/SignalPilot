import type { RebalanceLogEntry } from '@/types/api';
import { Card } from '@/components/common/Card';
import { EmptyState } from '@/components/common/EmptyState';
import { RefreshCw } from 'lucide-react';
import { formatShortDate } from '@/utils/formatters';

interface RebalancingLogProps {
  entries: RebalanceLogEntry[];
}

export function RebalancingLog({ entries }: RebalancingLogProps) {
  if (entries.length === 0) {
    return (
      <Card title="Rebalancing Log">
        <EmptyState
          icon={RefreshCw}
          title="No Rebalancing Events"
          message="Allocation changes will appear here after the first rebalance."
        />
      </Card>
    );
  }

  return (
    <Card title="Rebalancing Log">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="pb-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                Date
              </th>
              <th className="pb-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                Description
              </th>
              <th className="pb-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                Changes
              </th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, i) => (
              <tr key={i} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="py-2 pr-4 text-gray-600 whitespace-nowrap">
                  {formatShortDate(entry.date)}
                </td>
                <td className="py-2 pr-4 text-gray-700">{entry.description}</td>
                <td className="py-2 text-gray-500">{entry.changes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
