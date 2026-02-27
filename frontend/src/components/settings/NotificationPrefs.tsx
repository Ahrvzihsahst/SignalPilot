import { useState } from 'react';
import type { UserSettings } from '@/types/api';
import { Card } from '@/components/common/Card';
import { useUpdateSettings } from '@/hooks/useSettings';
import { cn } from '@/utils/cn';

interface NotificationPrefsProps {
  settings: UserSettings;
}

interface ToggleSwitchProps {
  label: string;
  enabled: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}

function ToggleSwitch({ label, enabled, onChange, disabled }: ToggleSwitchProps) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-sm text-gray-700">{label}</span>
      <button
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        onClick={() => onChange(!enabled)}
        className={cn(
          'relative inline-flex h-5 w-10 items-center rounded-full transition-colors focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
          enabled ? 'bg-blue-600' : 'bg-gray-200'
        )}
      >
        <span
          className={cn(
            'inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform',
            enabled ? 'translate-x-5' : 'translate-x-1'
          )}
        />
      </button>
    </div>
  );
}

export function NotificationPrefs({ settings }: NotificationPrefsProps) {
  const [chatId, setChatId] = useState(settings.telegram_chat_id);
  const { mutate, isPending, isSuccess, isError } = useUpdateSettings();

  return (
    <Card title="Notifications">
      <div className="space-y-4">
        <div className="flex flex-col gap-1">
          <label className="text-xs font-medium text-gray-600">Telegram Chat ID</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={chatId}
              onChange={(e) => setChatId(e.target.value)}
              placeholder="e.g. -100123456789"
              className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
            />
            <button
              onClick={() => mutate({ telegram_chat_id: chatId })}
              disabled={isPending || chatId === settings.telegram_chat_id}
              className="rounded-md bg-blue-600 px-3 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              Save
            </button>
          </div>
          {isSuccess && <p className="text-xs text-green-600">Saved.</p>}
          {isError && <p className="text-xs text-red-600">Failed to save.</p>}
        </div>

        <div>
          <p className="mb-2 text-xs font-medium text-gray-600">Notification Types</p>
          <div className="divide-y divide-gray-100">
            <ToggleSwitch label="New signals" enabled={true} onChange={() => {}} disabled={true} />
            <ToggleSwitch label="Exit alerts (SL / Target)" enabled={true} onChange={() => {}} disabled={true} />
            <ToggleSwitch label="Daily summary" enabled={true} onChange={() => {}} disabled={true} />
            <ToggleSwitch label="Circuit breaker events" enabled={true} onChange={() => {}} disabled={true} />
          </div>
          <p className="mt-2 text-xs text-gray-400">
            Notification type preferences are managed via Telegram bot commands.
          </p>
        </div>
      </div>
    </Card>
  );
}
