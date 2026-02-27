import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { StrategyPnlSeriesPoint } from '@/types/api';
import { formatShortDate } from '@/utils/formatters';
import { Card } from '@/components/common/Card';
import { EmptyState } from '@/components/common/EmptyState';
import { TrendingUp } from 'lucide-react';
import { STRATEGY_COLORS } from '@/utils/constants';

interface PnlStackedChartProps {
  data: StrategyPnlSeriesPoint[];
}

function formatYAxis(value: number): string {
  if (Math.abs(value) >= 1000) return `₹${(value / 1000).toFixed(0)}k`;
  return `₹${value}`;
}

export function PnlStackedChart({ data }: PnlStackedChartProps) {
  if (data.length === 0) {
    return (
      <Card title="P&L by Strategy">
        <EmptyState icon={TrendingUp} title="No Data" message="No P&L series data available." />
      </Card>
    );
  }

  const chartData = data.map((pt) => ({
    date: formatShortDate(pt.date),
    'Gap & Go': pt.gap_go,
    ORB: pt.orb,
    'VWAP Reversal': pt.vwap,
  }));

  return (
    <Card title="Cumulative P&L by Strategy">
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis tickFormatter={formatYAxis} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value: number, name: string) => [
              `₹${value.toLocaleString('en-IN')}`,
              name,
            ]}
          />
          <Legend />
          <Area
            type="monotone"
            dataKey="Gap & Go"
            stackId="1"
            stroke={STRATEGY_COLORS['gap_go']}
            fill={STRATEGY_COLORS['gap_go']}
            fillOpacity={0.6}
          />
          <Area
            type="monotone"
            dataKey="ORB"
            stackId="1"
            stroke={STRATEGY_COLORS['ORB']}
            fill={STRATEGY_COLORS['ORB']}
            fillOpacity={0.6}
          />
          <Area
            type="monotone"
            dataKey="VWAP Reversal"
            stackId="1"
            stroke={STRATEGY_COLORS['VWAP Reversal']}
            fill={STRATEGY_COLORS['VWAP Reversal']}
            fillOpacity={0.6}
          />
        </AreaChart>
      </ResponsiveContainer>
    </Card>
  );
}
