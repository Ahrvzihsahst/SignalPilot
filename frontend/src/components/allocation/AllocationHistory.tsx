import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { AllocationHistoryPoint } from '@/types/api';
import { formatShortDate } from '@/utils/formatters';
import { Card } from '@/components/common/Card';
import { EmptyState } from '@/components/common/EmptyState';
import { TrendingUp } from 'lucide-react';
import { STRATEGY_COLORS } from '@/utils/constants';

interface AllocationHistoryProps {
  data: AllocationHistoryPoint[];
}

export function AllocationHistory({ data }: AllocationHistoryProps) {
  if (data.length === 0) {
    return (
      <Card title="Allocation History">
        <EmptyState icon={TrendingUp} title="No Data" message="No allocation history available." />
      </Card>
    );
  }

  const chartData = data.map((pt) => ({
    date: formatShortDate(pt.date),
    'Gap & Go': parseFloat((pt.gap_go * 100).toFixed(1)),
    ORB: parseFloat((pt.orb * 100).toFixed(1)),
    'VWAP Reversal': parseFloat((pt.vwap * 100).toFixed(1)),
  }));

  return (
    <Card title="Allocation Weight History (%)">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={(v) => `${v}%`} domain={[0, 100]} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: number) => [`${v}%`]} />
          <Legend />
          <Line
            type="monotone"
            dataKey="Gap & Go"
            stroke={STRATEGY_COLORS['gap_go']}
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="ORB"
            stroke={STRATEGY_COLORS['ORB']}
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="VWAP Reversal"
            stroke={STRATEGY_COLORS['VWAP Reversal']}
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}
