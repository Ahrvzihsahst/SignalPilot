import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from 'recharts';
import type { WinRatePoint } from '@/types/api';
import { Card } from '@/components/common/Card';
import { EmptyState } from '@/components/common/EmptyState';
import { TrendingUp } from 'lucide-react';

interface WinRateTrendProps {
  data: WinRatePoint[];
}

export function WinRateTrend({ data }: WinRateTrendProps) {
  if (data.length === 0) {
    return (
      <Card title="Win Rate Trend">
        <EmptyState icon={TrendingUp} title="No Data" message="No win rate data available." />
      </Card>
    );
  }

  const chartData = data.map((pt) => ({
    trade: `#${pt.trade_number}`,
    winRate: parseFloat(pt.win_rate.toFixed(1)),
  }));

  return (
    <Card title="Running Win Rate (%)">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="trade" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
          <Tooltip formatter={(v: number) => [`${v}%`, 'Win Rate']} />
          <ReferenceLine y={50} stroke="#6b7280" strokeDasharray="4 2" label={{ value: '50%', fontSize: 10, fill: '#6b7280' }} />
          <Line
            type="monotone"
            dataKey="winRate"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}
