import { PnlDisplay } from '@/components/common/PnlDisplay';

interface MarketStatusBarProps {
  marketStatus: string;
  currentTime: string;
  capital: number;
  positionsUsed: number;
  positionsMax: number;
  todayPnl: number;
  todayPnlPct: number;
}

export function MarketStatusBar({
  marketStatus,
  capital,
  positionsUsed,
  positionsMax,
  todayPnl,
  todayPnlPct,
}: MarketStatusBarProps) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${marketStatus === 'open' ? 'bg-green-500' : 'bg-gray-400'}`} />
        <span className="text-sm font-medium text-gray-700">
          Market {marketStatus === 'open' ? 'Open' : 'Closed'}
        </span>
      </div>
      <span className="text-sm text-gray-600">Capital: ₹{capital.toLocaleString('en-IN')}</span>
      <span className="text-sm text-gray-600">Positions: {positionsUsed}/{positionsMax}</span>
      <div className="flex items-center gap-1 text-sm">
        <span className="text-gray-600">Today&apos;s P&amp;L:</span>
        <PnlDisplay amount={todayPnl} pct={todayPnlPct} size="sm" />
      </div>
    </div>
  );
}
