import type { TradeFilterState } from '@/types/models';

interface TradeFiltersProps {
  filters: TradeFilterState;
  onChange: (filters: TradeFilterState) => void;
}

const STRATEGIES = ['', 'gap_go', 'ORB', 'VWAP Reversal'];
const RESULTS = ['', 'win', 'loss', 'open'];

export function TradeFilters({ filters, onChange }: TradeFiltersProps) {
  const update = (key: keyof TradeFilterState, value: string | number) => {
    onChange({ ...filters, [key]: value, page: 1 });
  };

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">From</label>
        <input
          type="date"
          value={filters.dateFrom}
          onChange={(e) => update('dateFrom', e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">To</label>
        <input
          type="date"
          value={filters.dateTo}
          onChange={(e) => update('dateTo', e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">Strategy</label>
        <select
          value={filters.strategy}
          onChange={(e) => update('strategy', e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
        >
          {STRATEGIES.map((s) => (
            <option key={s} value={s}>{s || 'All Strategies'}</option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">Result</label>
        <select
          value={filters.result}
          onChange={(e) => update('result', e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
        >
          {RESULTS.map((r) => (
            <option key={r} value={r}>{r || 'All Results'}</option>
          ))}
        </select>
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-600">Search</label>
        <input
          type="text"
          placeholder="Symbol..."
          value={filters.search}
          onChange={(e) => update('search', e.target.value)}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
        />
      </div>
      <button
        onClick={() =>
          onChange({
            dateFrom: '',
            dateTo: '',
            strategy: '',
            result: '',
            search: '',
            page: 1,
            pageSize: 20,
          })
        }
        className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50"
      >
        Clear
      </button>
    </div>
  );
}
