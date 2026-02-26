import { useQuery, useMutation } from '@tanstack/react-query';
import { fetchTrades, exportTradesCsv } from '@/api/trades';
import { downloadBlob } from '@/utils/csv';
import type { TradeFilters } from '@/types/api';
import { format } from 'date-fns';

export function useTrades(filters: TradeFilters) {
  return useQuery({
    queryKey: ['trades', filters],
    queryFn: () => fetchTrades(filters),
  });
}

export function useExportTradesCsv() {
  return useMutation({
    mutationFn: ({ dateFrom, dateTo }: { dateFrom?: string; dateTo?: string }) =>
      exportTradesCsv(dateFrom, dateTo),
    onSuccess: (blob) => {
      const filename = `signalpilot_trades_${format(new Date(), 'yyyy-MM-dd')}.csv`;
      downloadBlob(blob, filename);
    },
  });
}
