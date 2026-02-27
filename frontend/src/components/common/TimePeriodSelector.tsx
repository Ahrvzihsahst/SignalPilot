import { cn } from '@/utils/cn';
import type { Period } from '@/types/models';

interface TimePeriodSelectorProps {
  selected: Period;
  onChange: (period: Period) => void;
}

const PERIODS: { value: Period; label: string }[] = [
  { value: '1w', label: '1W' },
  { value: '1m', label: '1M' },
  { value: '3m', label: '3M' },
  { value: 'all', label: 'ALL' },
];

export function TimePeriodSelector({ selected, onChange }: TimePeriodSelectorProps) {
  return (
    <div className="inline-flex rounded-lg border border-gray-200">
      {PERIODS.map(({ value, label }) => (
        <button
          key={value}
          onClick={() => onChange(value)}
          className={cn(
            'px-3 py-1.5 text-sm transition-colors first:rounded-l-lg last:rounded-r-lg',
            value === selected
              ? 'bg-blue-600 text-white'
              : 'text-gray-600 hover:bg-gray-50'
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
