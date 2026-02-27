import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ResponsiveContainer,
} from 'recharts';
import type { DailyPnlPoint } from '@/types/api';
import { formatShortDate } from '@/utils/formatters';
import { Card } from '@/components/common/Card';
import { EmptyState } from '@/components/common/EmptyState';
import { BarChart2 } from 'lucide-react';

interface DailyPnlChartProps {
  data: DailyPnlPoint[];
}

function formatYAxis(value: number): string {
  if (Math.abs(value) >= 1000) return `₹${(value / 1000).toFixed(0)}k`;
  return `₹${value}`;
}

export function DailyPnlChart({ data }: DailyPnlChartProps) {
  if (data.length === 0) {
    return (
      <Card title="Daily P&L">
        <EmptyState icon={BarChart2} title="No Data" message="No daily P&L data available." />
      </Card>
    );
  }

  const chartData = data.map((pt) => ({
    date: formatShortDate(pt.date),
    pnl: pt.pnl_amount,
  }));

  return (
    <Card title="Daily P&L">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={formatYAxis} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value: number) => [`₹${value.toLocaleString('en-IN')}`, 'P&L']}
          />
          <Bar dataKey="pnl" radius={[3, 3, 0, 0]}>
            {chartData.map((entry, index) => (
              <Cell key={index} fill={entry.pnl >= 0 ? '#16a34a' : '#dc2626'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
