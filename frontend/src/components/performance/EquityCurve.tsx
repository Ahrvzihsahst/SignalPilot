import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { EquityCurvePoint } from '@/types/api';
import { formatShortDate } from '@/utils/formatters';
import { Card } from '@/components/common/Card';
import { EmptyState } from '@/components/common/EmptyState';
import { TrendingUp } from 'lucide-react';

interface EquityCurveProps {
  data: EquityCurvePoint[];
}

function formatYAxis(value: number): string {
  if (Math.abs(value) >= 1000) return `₹${(value / 1000).toFixed(0)}k`;
  return `₹${value}`;
}

export function EquityCurve({ data }: EquityCurveProps) {
  if (data.length === 0) {
    return (
      <Card title="Equity Curve">
        <EmptyState icon={TrendingUp} title="No Data" message="No equity curve data available." />
      </Card>
    );
  }

  const chartData = data.map((pt) => ({
    date: formatShortDate(pt.date),
    pnl: pt.cumulative_pnl,
  }));

  const color = (data[data.length - 1]?.cumulative_pnl ?? 0) >= 0 ? '#16a34a' : '#dc2626';

  return (
    <Card title="Equity Curve (Cumulative P&L)">
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={formatYAxis} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value: number) => [`₹${value.toLocaleString('en-IN')}`, 'Cumulative P&L']}
          />
          <Line
            type="monotone"
            dataKey="pnl"
            stroke={color}
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}
