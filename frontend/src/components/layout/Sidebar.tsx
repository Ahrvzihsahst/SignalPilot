import { NavLink } from 'react-router-dom';
import { Activity, BookOpen, TrendingUp, BarChart3, PieChart, Settings } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { LucideIcon } from 'lucide-react';

interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { path: '/', label: 'Live Signals', icon: Activity },
  { path: '/trades', label: 'Trade Journal', icon: BookOpen },
  { path: '/performance', label: 'Performance', icon: TrendingUp },
  { path: '/strategies', label: 'Strategies', icon: BarChart3 },
  { path: '/allocation', label: 'Allocation', icon: PieChart },
  { path: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  return (
    <aside className="flex w-64 flex-col border-r border-gray-200 bg-white">
      <div className="flex h-16 items-center px-6">
        <h1 className="text-xl font-bold text-gray-900">SignalPilot</h1>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors',
                isActive
                  ? 'bg-blue-50 font-medium text-blue-700'
                  : 'text-gray-600 hover:bg-gray-100'
              )
            }
          >
            <item.icon className="h-5 w-5" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
