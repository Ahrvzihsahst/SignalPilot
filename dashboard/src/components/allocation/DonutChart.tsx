import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { AllocationData } from '@/types/api';
import { Card } from '@/components/common/Card';
import { STRATEGY_COLORS } from '@/utils/constants';

interface DonutChartProps {
  data: AllocationData;
}

const SEGMENT_COLORS: Record<string, string> = {
  ...STRATEGY_COLORS,
  Reserve: STRATEGY_COLORS['reserve'],
};

export function DonutChart({ data }: DonutChartProps) {
  const segments = [
    ...data.allocations.map((a) => ({
      name: a.strategy,
      value: a.weight_pct,
      amount: a.allocated_amount,
    })),
    {
      name: 'Reserve',
      value: data.reserve_pct,
      amount: data.reserve_amount,
    },
  ];

  return (
    <Card title="Current Capital Allocation">
      <ResponsiveContainer width="100%" height={260}>
        <PieChart>
          <Pie
            data={segments}
            cx="50%"
            cy="50%"
            innerRadius={65}
            outerRadius={100}
            paddingAngle={3}
            dataKey="value"
          >
            {segments.map((entry, index) => (
              <Cell
                key={index}
                fill={SEGMENT_COLORS[entry.name] ?? '#9ca3af'}
              />
            ))}
          </Pie>
          <Tooltip
            formatter={(value: number, name: string, props) => [
              `${value.toFixed(1)}% — ₹${props.payload.amount.toLocaleString('en-IN')}`,
              name,
            ]}
          />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
      <p className="mt-1 text-center text-xs text-gray-500">
        Total Capital: ₹{data.total_capital.toLocaleString('en-IN')}
        {data.next_rebalance && ` | Next rebalance: ${data.next_rebalance}`}
      </p>
    </Card>
  );
}
