import { cn } from '@/utils/cn';
import type { ReactNode } from 'react';

interface CardProps {
  title?: string;
  className?: string;
  children: ReactNode;
}

export function Card({ title, className, children }: CardProps) {
  return (
    <div className={cn('rounded-lg border border-gray-200 bg-white p-4 shadow-sm', className)}>
      {title && <h3 className="mb-3 text-sm font-semibold text-gray-900">{title}</h3>}
      {children}
    </div>
  );
}
