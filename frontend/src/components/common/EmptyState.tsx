import type { LucideIcon } from 'lucide-react';
import { Inbox } from 'lucide-react';

interface EmptyStateProps {
  icon?: LucideIcon;
  title: string;
  message: string;
}

export function EmptyState({ icon: Icon = Inbox, title, message }: EmptyStateProps) {
  return (
    <div className="flex h-full items-center justify-center py-12">
      <div className="text-center">
        <Icon className="mx-auto h-12 w-12 text-gray-300" />
        <h3 className="mt-3 text-sm font-medium text-gray-900">{title}</h3>
        <p className="mt-1 text-sm text-gray-500">{message}</p>
      </div>
    </div>
  );
}
