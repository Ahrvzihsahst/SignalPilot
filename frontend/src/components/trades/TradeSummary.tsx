import type { TradeSummary as TradeSummaryType } from '@/types/api';
import { PnlDisplay } from '@/components/common/PnlDisplay';

interface TradeSummaryProps {
  summary: TradeSummaryType;
}

export function TradeSummary({ summary }: TradeSummaryProps) {
  return (
    <div className="grid grid-cols-2 gap-3 rounded-lg border border-gray-200 bg-white p-4 md:grid-cols-4 lg:grid-cols-6">
      <div className="text-center">
        <p className="text-xs text-gray-500">Total Trades</p>
        <p className="text-lg font-bold text-gray-900">{summary.total_trades}</p>
      </div>
      <div className="text-center">
        <p className="text-xs text-gray-500">Wins</p>
        <p className="text-lg font-bold text-green-600">{summary.wins}</p>
      </div>
      <div className="text-center">
        <p className="text-xs text-gray-500">Losses</p>
        <p className="text-lg font-bold text-red-600">{summary.losses}</p>
      </div>
      <div className="text-center">
        <p className="text-xs text-gray-500">Win Rate</p>
        <p className="text-lg font-bold text-gray-900">{summary.win_rate.toFixed(1)}%</p>
      </div>
      <div className="text-center">
        <p className="text-xs text-gray-500">Net P&amp;L</p>
        <PnlDisplay amount={summary.total_pnl} size="lg" />
      </div>
      <div className="text-center">
        <p className="text-xs text-gray-500">Best / Worst</p>
        <div className="flex justify-center gap-1 text-sm">
          <span className="text-green-600">+₹{(summary.best_trade_pnl ?? 0).toLocaleString('en-IN')}</span>
          <span className="text-gray-400">/</span>
          <span className="text-red-600">-₹{Math.abs(summary.worst_trade_pnl ?? 0).toLocaleString('en-IN')}</span>
        </div>
      </div>
    </div>
  );
}
