import type { ConfirmedSignalsPerformance } from '@/types/api';
import { Card } from '@/components/common/Card';
import { cn } from '@/utils/cn';

interface ConfirmedStatsProps {
  data: ConfirmedSignalsPerformance;
}

interface StatItemProps {
  label: string;
  value: string;
  highlight?: boolean;
}

function StatItem({ label, value, highlight }: StatItemProps) {
  return (
    <div className="text-center">
      <p className="text-xs text-gray-500">{label}</p>
      <p className={cn('text-lg font-bold', highlight ? 'text-blue-600' : 'text-gray-900')}>
        {value}
      </p>
    </div>
  );
}

export function ConfirmedStats({ data }: ConfirmedStatsProps) {
  const confirmedBetter = data.confirmed_win_rate > data.single_strategy_win_rate;

  return (
    <Card title="Confirmed vs Single-Strategy Performance">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <div className="col-span-2 md:col-span-3">
          <p className="mb-3 text-xs text-gray-500">
            Confirmed signals are those validated by more than one strategy. Cross-strategy confirmation
            improves signal quality.
          </p>
        </div>
        <div className="rounded-lg bg-blue-50 p-3">
          <p className="mb-2 text-xs font-semibold text-blue-700">Confirmed Signals</p>
          <div className="space-y-2">
            <StatItem label="Trades" value={`${data.total_confirmed_trades}`} />
            <StatItem
              label="Win Rate"
              value={`${data.confirmed_win_rate.toFixed(1)}%`}
              highlight={confirmedBetter}
            />
            <StatItem label="Avg P&L" value={`₹${data.confirmed_avg_pnl.toFixed(0)}`} />
          </div>
        </div>
        <div className="rounded-lg bg-gray-50 p-3">
          <p className="mb-2 text-xs font-semibold text-gray-600">Single Strategy</p>
          <div className="space-y-2">
            <StatItem
              label="Win Rate"
              value={`${data.single_strategy_win_rate.toFixed(1)}%`}
              highlight={!confirmedBetter}
            />
            <StatItem label="Avg P&L" value={`₹${data.single_strategy_avg_pnl.toFixed(0)}`} />
          </div>
        </div>
        <div className="flex items-center justify-center rounded-lg bg-green-50 p-3">
          <div className="text-center">
            <p className="text-xs text-gray-500">Win Rate Lift</p>
            <p className={cn('text-2xl font-bold', confirmedBetter ? 'text-green-600' : 'text-red-600')}>
              {confirmedBetter ? '+' : ''}
              {(data.confirmed_win_rate - data.single_strategy_win_rate).toFixed(1)}%
            </p>
          </div>
        </div>
      </div>
    </Card>
  );
}
