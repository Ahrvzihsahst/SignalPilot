import { Download } from 'lucide-react';
import { useExportTradesCsv } from '@/hooks/useTrades';

interface ExportButtonProps {
  dateFrom?: string;
  dateTo?: string;
}

export function ExportButton({ dateFrom, dateTo }: ExportButtonProps) {
  const { mutate, isPending } = useExportTradesCsv();

  return (
    <button
      onClick={() => mutate({ dateFrom, dateTo })}
      disabled={isPending}
      className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <Download className="h-4 w-4" />
      {isPending ? 'Exporting...' : 'Export CSV'}
    </button>
  );
}
