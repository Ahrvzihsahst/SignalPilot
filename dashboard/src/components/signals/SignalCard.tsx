import type { LiveSignal } from '@/types/api';
import { Card } from '@/components/common/Card';
import { StarRating } from '@/components/common/StarRating';
import { PnlDisplay } from '@/components/common/PnlDisplay';
import { Badge } from '@/components/common/Badge';
import { SignalDetails } from './SignalDetails';
import { cn } from '@/utils/cn';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface SignalCardProps {
  signal: LiveSignal;
  rank: number;
  isExpanded: boolean;
  onToggleExpand: () => void;
}

export function SignalCard({ signal, rank, isExpanded, onToggleExpand }: SignalCardProps) {
  const pnl = signal.pnl_amount ?? 0;
  return (
    <Card className={cn('border-l-4', pnl >= 0 ? 'border-l-green-500' : 'border-l-red-500')}>
      <div className="flex items-center gap-3">
        <span className="text-sm font-bold text-gray-400">#{rank}</span>
        {signal.confirmation_level === 'double' && <Badge variant="confirmed">CONFIRMED</Badge>}
        {signal.confirmation_level === 'triple' && <Badge variant="confirmed">TRIPLE</Badge>}
        <span className="font-semibold text-gray-900">{signal.symbol}</span>
        <StarRating stars={signal.signal_strength} />
        {signal.composite_score !== null && (
          <span className="text-xs text-gray-500">Score: {signal.composite_score.toFixed(1)}</span>
        )}
        <div className="ml-auto flex items-center gap-3">
          {signal.pnl_amount !== null && (
            <PnlDisplay amount={signal.pnl_amount} pct={signal.pnl_pct ?? undefined} size="sm" />
          )}
          <Badge variant={signal.status === 'taken' ? 'success' : 'default'}>
            {signal.status.toUpperCase()}
          </Badge>
          <button
            onClick={onToggleExpand}
            className="text-xs text-blue-600 hover:underline flex items-center gap-1"
          >
            {isExpanded ? (
              <><ChevronUp className="h-3 w-3" /> Collapse</>
            ) : (
              <><ChevronDown className="h-3 w-3" /> Details</>
            )}
          </button>
        </div>
      </div>
      {isExpanded && <SignalDetails signal={signal} />}
    </Card>
  );
}
