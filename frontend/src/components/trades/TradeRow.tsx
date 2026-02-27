import { useState } from 'react';
import type { TradeRecord } from '@/types/api';
import { PnlDisplay } from '@/components/common/PnlDisplay';
import { Badge } from '@/components/common/Badge';
import { formatDate, formatShortDate } from '@/utils/formatters';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { cn } from '@/utils/cn';

interface TradeRowProps {
  trade: TradeRecord;
}

function getResultVariant(trade: TradeRecord): 'success' | 'danger' | 'default' {
  if (trade.pnl_amount === null) return 'default';
  return trade.pnl_amount >= 0 ? 'success' : 'danger';
}

function getResultLabel(trade: TradeRecord): string {
  if (trade.pnl_amount === null) return 'OPEN';
  return trade.pnl_amount >= 0 ? 'WIN' : 'LOSS';
}

export function TradeRow({ trade }: TradeRowProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <tr
        className={cn(
          'cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors',
          expanded && 'bg-blue-50'
        )}
        onClick={() => setExpanded((v) => !v)}
      >
        <td className="px-4 py-3 text-sm text-gray-600">{formatShortDate(trade.date)}</td>
        <td className="px-4 py-3 text-sm font-semibold text-gray-900">{trade.symbol}</td>
        <td className="px-4 py-3 text-sm text-gray-600">{trade.strategy}</td>
        <td className="px-4 py-3 text-sm">
          {trade.pnl_amount !== null ? (
            <PnlDisplay amount={trade.pnl_amount} pct={trade.pnl_pct ?? undefined} size="sm" />
          ) : (
            <span className="text-gray-400">—</span>
          )}
        </td>
        <td className="px-4 py-3">
          <Badge variant={getResultVariant(trade)}>{getResultLabel(trade)}</Badge>
        </td>
        <td className="px-4 py-3 text-right">
          <button className="text-gray-400 hover:text-gray-600">
            {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr className="border-b border-gray-100 bg-gray-50">
          <td colSpan={6} className="px-4 py-4">
            <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm md:grid-cols-4">
              <div>
                <span className="text-gray-500">Entry Price</span>
                <p className="font-medium">₹{trade.entry_price.toFixed(2)}</p>
              </div>
              {trade.exit_price !== null && (
                <div>
                  <span className="text-gray-500">Exit Price</span>
                  <p className="font-medium">₹{trade.exit_price.toFixed(2)}</p>
                </div>
              )}
              <div>
                <span className="text-gray-500">Stop Loss</span>
                <p className="font-medium text-red-600">₹{trade.stop_loss.toFixed(2)}</p>
              </div>
              <div>
                <span className="text-gray-500">Target 1</span>
                <p className="font-medium">₹{trade.target_1.toFixed(2)}</p>
              </div>
              <div>
                <span className="text-gray-500">Target 2</span>
                <p className="font-medium text-green-600">₹{trade.target_2.toFixed(2)}</p>
              </div>
              <div>
                <span className="text-gray-500">Quantity</span>
                <p className="font-medium">{trade.quantity}</p>
              </div>
              {trade.exit_reason && (
                <div>
                  <span className="text-gray-500">Exit Reason</span>
                  <p className="font-medium">{trade.exit_reason}</p>
                </div>
              )}
              {trade.composite_score !== null && (
                <div>
                  <span className="text-gray-500">Score</span>
                  <p className="font-medium">{trade.composite_score.toFixed(1)}</p>
                </div>
              )}
              {trade.confirmation_level && (
                <div>
                  <span className="text-gray-500">Confirmation</span>
                  <p className="font-medium capitalize">{trade.confirmation_level}</p>
                </div>
              )}
              {trade.taken_at && (
                <div>
                  <span className="text-gray-500">Taken At</span>
                  <p className="font-medium">{formatDate(trade.taken_at)}</p>
                </div>
              )}
              {trade.exited_at && (
                <div>
                  <span className="text-gray-500">Exited At</span>
                  <p className="font-medium">{formatDate(trade.exited_at)}</p>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
