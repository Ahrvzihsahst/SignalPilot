import { useState } from 'react';
import { useLiveSignals } from '@/hooks/useSignals';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorDisplay } from '@/components/common/ErrorDisplay';
import { EmptyState } from '@/components/common/EmptyState';
import { MarketStatusBar } from '@/components/signals/MarketStatusBar';
import { CircuitBreakerBar } from '@/components/signals/CircuitBreakerBar';
import { SignalCard } from '@/components/signals/SignalCard';
import { Activity } from 'lucide-react';

export default function LiveSignals() {
  const { data, isLoading, error, refetch } = useLiveSignals();
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (isLoading) return <LoadingSpinner message="Loading signals..." />;
  if (error) return <ErrorDisplay error={error} onRetry={refetch} />;
  if (!data) return null;

  const hasSignals = data.active_signals.length > 0 || data.expired_signals.length > 0;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Live Signals</h1>
      <MarketStatusBar
        marketStatus={data.market_status}
        currentTime={data.current_time}
        capital={data.capital}
        positionsUsed={data.positions_used}
        positionsMax={data.positions_max}
        todayPnl={data.today_pnl}
        todayPnlPct={data.today_pnl_pct}
      />
      <CircuitBreakerBar
        slCount={data.circuit_breaker.sl_count}
        slLimit={data.circuit_breaker.sl_limit}
        isActive={data.circuit_breaker.is_active}
        isOverridden={data.circuit_breaker.is_overridden}
      />

      {!hasSignals ? (
        <EmptyState icon={Activity} title="No Signals" message="No signals generated yet today." />
      ) : (
        <>
          {data.active_signals.length > 0 && (
            <div>
              <h2 className="mb-2 text-sm font-semibold text-gray-700">
                Active Signals ({data.active_signals.length})
              </h2>
              <div className="space-y-3">
                {data.active_signals.map((signal, i) => (
                  <SignalCard
                    key={signal.id}
                    signal={signal}
                    rank={i + 1}
                    isExpanded={expandedIds.has(signal.id)}
                    onToggleExpand={() => toggleExpand(signal.id)}
                  />
                ))}
              </div>
            </div>
          )}
          {data.expired_signals.length > 0 && (
            <div className="opacity-60">
              <h2 className="mb-2 text-sm font-semibold text-gray-500">
                Expired / Reference Signals
              </h2>
              <div className="space-y-3">
                {data.expired_signals.map((signal, i) => (
                  <SignalCard
                    key={signal.id}
                    signal={signal}
                    rank={data.active_signals.length + i + 1}
                    isExpanded={expandedIds.has(signal.id)}
                    onToggleExpand={() => toggleExpand(signal.id)}
                  />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
