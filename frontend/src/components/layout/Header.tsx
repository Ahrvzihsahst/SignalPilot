import { format } from 'date-fns';

export function Header() {
  const now = new Date();
  const dateStr = format(now, 'dd MMM yyyy, EEEE');

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white px-6">
      <h2 className="text-lg font-semibold text-gray-900">SignalPilot Dashboard</h2>
      <span className="text-sm text-gray-500">{dateStr}</span>
    </header>
  );
}
