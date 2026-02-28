import { cn } from '@/utils/cn';
import type { ReactNode } from 'react';

interface BadgeProps {
  variant?: 'confirmed' | 'success' | 'danger' | 'default';
  children: ReactNode;
}

const variantClasses = {
  confirmed: 'bg-amber-100 text-amber-800',
  success: 'bg-green-100 text-green-800',
  danger: 'bg-red-100 text-red-800',
  default: 'bg-gray-100 text-gray-800',
};

export function Badge({ variant = 'default', children }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        variantClasses[variant]
      )}
    >
      {children}
    </span>
  );
}
