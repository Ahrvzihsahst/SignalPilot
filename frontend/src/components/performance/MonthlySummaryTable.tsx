import type { MonthlySummary } from '@/types/api';
import { Card } from '@/components/common/Card';
import { PnlDisplay } from '@/components/common/PnlDisplay';
import { EmptyState } from '@/components/common/EmptyState';
import { Calendar } from 'lucide-react';

interface MonthlySummaryTableProps {
  data: MonthlySummary[];
}

export function MonthlySummaryTable({ data }: MonthlySummaryTableProps) {
  if (data.length === 0) {
    return (
      <Card title="Monthly Summary">
        <EmptyState icon={Calendar} title="No Data" message="No monthly data available." />
      </Card>
    );
  }

  return (
    <Card title="Monthly Summary">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="pb-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                Month
              </th>
              <th className="pb-2 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                Trades
              </th>
              <th className="pb-2 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                Win %
              </th>
              <th className="pb-2 text-right text-xs font-semibold uppercase tracking-wide text-gray-500">
                Net P&amp;L
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((row) => (
              <tr key={row.month} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="py-2 text-gray-900">{row.month}</td>
                <td className="py-2 text-right text-gray-600">{row.trade_count}</td>
                <td className="py-2 text-right text-gray-600">{row.win_rate.toFixed(1)}%</td>
                <td className="py-2 text-right">
                  <PnlDisplay amount={row.net_pnl} size="sm" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
