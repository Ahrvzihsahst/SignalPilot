import { cn } from '@/utils/cn';
import { formatCurrency, formatPercent } from '@/utils/formatters';

interface PnlDisplayProps {
  amount: number;
  pct?: number;
  size?: 'sm' | 'md' | 'lg';
}

const sizeClasses = {
  sm: 'text-sm',
  md: 'text-base',
  lg: 'text-lg font-semibold',
};

export function PnlDisplay({ amount, pct, size = 'md' }: PnlDisplayProps) {
  const colorClass = amount >= 0 ? 'text-green-600' : 'text-red-600';

  return (
    <span className={cn(colorClass, sizeClasses[size])}>
      {formatCurrency(amount)}
      {pct !== undefined && (
        <span className="ml-1 text-xs opacity-75">({formatPercent(pct)})</span>
      )}
    </span>
  );
}
