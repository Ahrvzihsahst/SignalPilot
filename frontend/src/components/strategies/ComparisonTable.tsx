import type { StrategyMetrics } from '@/types/api';
import { Card } from '@/components/common/Card';
import { PnlDisplay } from '@/components/common/PnlDisplay';
import { cn } from '@/utils/cn';
import { EmptyState } from '@/components/common/EmptyState';
import { BarChart2 } from 'lucide-react';

interface ComparisonTableProps {
  strategies: StrategyMetrics[];
}

export function ComparisonTable({ strategies }: ComparisonTableProps) {
  if (strategies.length === 0) {
    return (
      <Card title="Strategy Metrics">
        <EmptyState icon={BarChart2} title="No Data" message="No strategy data available." />
      </Card>
    );
  }

  return (
    <Card title="Strategy Metrics Comparison">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="pb-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                Metric
              </th>
              {strategies.map((s) => (
                <th
                  key={s.strategy}
                  className="pb-2 text-right text-xs font-semibold uppercase tracking-wide text-gray-500"
                >
                  {s.strategy}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            <MetricRow label="Win Rate" strategies={strategies} getValue={(s) => `${s.win_rate.toFixed(1)}%`} highlight="max" getNum={(s) => s.win_rate} />
            <MetricRow label="Total Trades" strategies={strategies} getValue={(s) => `${s.total_trades}`} getNum={(s) => s.total_trades} />
            <MetricRow label="Net P&L" strategies={strategies} getValue={(s) => null} pnlGetter={(s) => s.total_pnl} getNum={(s) => s.total_pnl} highlight="max" />
            <MetricRow label="Avg Win" strategies={strategies} getValue={(s) => `₹${s.avg_win.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`} getNum={(s) => s.avg_win} highlight="max" />
            <MetricRow label="Avg Loss" strategies={strategies} getValue={(s) => `₹${Math.abs(s.avg_loss).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`} getNum={(s) => s.avg_loss} highlight="min" />
            <MetricRow label="Expectancy" strategies={strategies} getValue={(s) => `₹${s.expectancy.toFixed(0)}`} getNum={(s) => s.expectancy} highlight="max" />
            <MetricRow label="Capital Weight" strategies={strategies} getValue={(s) => `${s.capital_weight_pct.toFixed(0)}%`} getNum={(s) => s.capital_weight_pct} />
          </tbody>
        </table>
      </div>
    </Card>
  );
}

interface MetricRowProps {
  label: string;
  strategies: StrategyMetrics[];
  getValue: (s: StrategyMetrics) => string | null;
  pnlGetter?: (s: StrategyMetrics) => number;
  getNum: (s: StrategyMetrics) => number;
  highlight?: 'max' | 'min';
}

function MetricRow({ label, strategies, getValue, pnlGetter, getNum, highlight }: MetricRowProps) {
  const nums = strategies.map(getNum);
  const best = highlight === 'max' ? Math.max(...nums) : highlight === 'min' ? Math.min(...nums) : null;

  return (
    <tr>
      <td className="py-2.5 pr-4 text-gray-500">{label}</td>
      {strategies.map((s) => {
        const num = getNum(s);
        const isBest = best !== null && num === best;
        return (
          <td
            key={s.strategy}
            className={cn('py-2.5 text-right', isBest ? 'font-semibold text-blue-600' : 'text-gray-700')}
          >
            {pnlGetter ? (
              <PnlDisplay amount={pnlGetter(s)} size="sm" />
            ) : (
              getValue(s)
            )}
          </td>
        );
      })}
    </tr>
  );
}
