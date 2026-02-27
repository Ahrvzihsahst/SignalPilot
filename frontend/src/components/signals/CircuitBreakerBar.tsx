import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { cn } from '@/utils/cn';

interface CircuitBreakerBarProps {
  slCount: number;
  slLimit: number;
  isActive: boolean;
  isOverridden: boolean;
}

export function CircuitBreakerBar({ slCount, slLimit, isActive, isOverridden }: CircuitBreakerBarProps) {
  return (
    <div
      className={cn(
        'flex items-center justify-between rounded-lg border p-3',
        isActive ? 'border-red-200 bg-red-50 text-red-800' : 'border-green-200 bg-green-50 text-green-800'
      )}
    >
      <div className="flex items-center gap-2">
        {isActive ? <ShieldAlert className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />}
        <span className="text-sm font-medium">
          Circuit Breaker: {slCount}/{slLimit} SL
        </span>
        {isOverridden && <span className="text-xs opacity-75">(overridden)</span>}
      </div>
      <span className="text-xs">{isActive ? 'ACTIVE - Signals paused' : 'Inactive'}</span>
    </div>
  );
}
