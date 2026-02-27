import type { LiveSignal } from '@/types/api';
import { formatCurrency, formatDate } from '@/utils/formatters';

interface SignalDetailsProps {
  signal: LiveSignal;
}

export function SignalDetails({ signal }: SignalDetailsProps) {
  return (
    <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 rounded-md bg-gray-50 p-4 text-sm md:grid-cols-4">
      <div>
        <span className="text-gray-500">Strategy</span>
        <p className="font-medium">{signal.strategy}{signal.setup_type ? ` (${signal.setup_type})` : ''}</p>
      </div>
      <div>
        <span className="text-gray-500">Entry</span>
        <p className="font-medium">₹{signal.entry_price.toFixed(2)}</p>
      </div>
      <div>
        <span className="text-gray-500">Stop Loss</span>
        <p className="font-medium text-red-600">₹{signal.stop_loss.toFixed(2)}</p>
      </div>
      <div>
        <span className="text-gray-500">Target 1</span>
        <p className="font-medium">₹{signal.target_1.toFixed(2)}</p>
      </div>
      <div>
        <span className="text-gray-500">Target 2</span>
        <p className="font-medium text-green-600">₹{signal.target_2.toFixed(2)}</p>
      </div>
      <div>
        <span className="text-gray-500">Quantity</span>
        <p className="font-medium">{signal.quantity}</p>
      </div>
      <div>
        <span className="text-gray-500">Capital Required</span>
        <p className="font-medium">{formatCurrency(signal.capital_required)}</p>
      </div>
      {signal.position_size_multiplier > 1 && (
        <div>
          <span className="text-gray-500">Allocation</span>
          <p className="font-medium text-amber-700">{signal.position_size_multiplier}x</p>
        </div>
      )}
      <div className="col-span-2 md:col-span-4">
        <span className="text-gray-500">Reason</span>
        <p className="font-medium">{signal.reason}</p>
      </div>
      <div>
        <span className="text-gray-500">Created</span>
        <p className="font-medium">{formatDate(signal.created_at)}</p>
      </div>
    </div>
  );
}
