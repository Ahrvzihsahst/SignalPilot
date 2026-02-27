import { useState } from 'react';
import { Card } from '@/components/common/Card';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { useExportTradesCsv } from '@/hooks/useTrades';
import { Download, RefreshCw, Trash2 } from 'lucide-react';
import apiClient from '@/api/client';
import { useQueryClient } from '@tanstack/react-query';

export function DataExport() {
  const queryClient = useQueryClient();
  const { mutate: exportCsv, isPending: isExporting } = useExportTradesCsv();

  const [confirmState, setConfirmState] = useState<{
    open: boolean;
    title: string;
    message: string;
    onConfirm: () => void;
    variant: 'danger' | 'default';
  }>({
    open: false,
    title: '',
    message: '',
    onConfirm: () => {},
    variant: 'default',
  });

  const closeConfirm = () => setConfirmState((s) => ({ ...s, open: false }));

  const handleResetPaper = () => {
    setConfirmState({
      open: true,
      title: 'Reset Paper Trades',
      message:
        'This will delete all paper mode trade records. Live trades will not be affected. This action cannot be undone.',
      variant: 'danger',
      onConfirm: async () => {
        await apiClient.post('/trades/reset-paper');
        queryClient.invalidateQueries({ queryKey: ['trades'] });
        closeConfirm();
      },
    });
  };

  const handleResetAll = () => {
    setConfirmState({
      open: true,
      title: 'Reset All Trade Data',
      message:
        'This will permanently delete ALL trade and signal records. This action cannot be undone. Are you absolutely sure?',
      variant: 'danger',
      onConfirm: async () => {
        await apiClient.post('/trades/reset-all');
        queryClient.invalidateQueries();
        closeConfirm();
      },
    });
  };

  return (
    <>
      <Card title="Data Export & Reset">
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            Export your trade history as CSV or reset data for a fresh start.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => exportCsv({})}
              disabled={isExporting}
              className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              <Download className="h-4 w-4" />
              {isExporting ? 'Exporting...' : 'Export CSV'}
            </button>
            <button
              onClick={handleResetPaper}
              className="flex items-center gap-2 rounded-md border border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-700 hover:bg-amber-100"
            >
              <RefreshCw className="h-4 w-4" />
              Reset Paper Trades
            </button>
            <button
              onClick={handleResetAll}
              className="flex items-center gap-2 rounded-md border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-700 hover:bg-red-100"
            >
              <Trash2 className="h-4 w-4" />
              Reset All Data
            </button>
          </div>
        </div>
      </Card>

      <ConfirmDialog
        isOpen={confirmState.open}
        title={confirmState.title}
        message={confirmState.message}
        confirmLabel="Yes, proceed"
        cancelLabel="Cancel"
        variant={confirmState.variant}
        onConfirm={confirmState.onConfirm}
        onCancel={closeConfirm}
      />
    </>
  );
}
