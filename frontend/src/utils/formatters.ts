import { format, parseISO } from 'date-fns';

export function formatCurrency(value: number): string {
  const prefix = value >= 0 ? '+' : '';
  return `${prefix}₹${Math.abs(value).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

export function formatPercent(value: number): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
}

export function formatDate(dateStr: string): string {
  try {
    return format(parseISO(dateStr), 'dd MMM yyyy, hh:mm a');
  } catch {
    return dateStr;
  }
}

export function formatShortDate(dateStr: string): string {
  try {
    return format(parseISO(dateStr), 'dd MMM');
  } catch {
    return dateStr;
  }
}

export function formatDecimal(value: number, places: number = 2): string {
  return value.toFixed(places);
}

export function formatStatus(status: string): string {
  const map: Record<string, string> = {
    sent: 'Active',
    taken: 'Taken',
    expired: 'Expired',
    paper: 'Paper',
    position_full: 'Position Full',
  };
  return map[status] || status;
}
