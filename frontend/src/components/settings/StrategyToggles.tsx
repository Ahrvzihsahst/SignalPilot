import type { UserSettings } from '@/types/api';
import { Card } from '@/components/common/Card';
import { useUpdateSettings } from '@/hooks/useSettings';
import { cn } from '@/utils/cn';

interface StrategyTogglesProps {
  settings: UserSettings;
}

interface ToggleSwitchProps {
  label: string;
  description: string;
  enabled: boolean;
  onChange: (value: boolean) => void;
  disabled?: boolean;
}

function ToggleSwitch({ label, description, enabled, onChange, disabled }: ToggleSwitchProps) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-gray-100 last:border-0">
      <div>
        <p className="text-sm font-medium text-gray-900">{label}</p>
        <p className="text-xs text-gray-500">{description}</p>
      </div>
      <button
        role="switch"
        aria-checked={enabled}
        disabled={disabled}
        onClick={() => onChange(!enabled)}
        className={cn(
          'relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none disabled:cursor-not-allowed disabled:opacity-50',
          enabled ? 'bg-blue-600' : 'bg-gray-200'
        )}
      >
        <span
          className={cn(
            'inline-block h-4 w-4 transform rounded-full bg-white transition-transform',
            enabled ? 'translate-x-6' : 'translate-x-1'
          )}
        />
      </button>
    </div>
  );
}

export function StrategyToggles({ settings }: StrategyTogglesProps) {
  const { mutate, isPending } = useUpdateSettings();

  return (
    <Card title="Strategy Enable / Disable">
      <div className="divide-y divide-gray-100">
        <ToggleSwitch
          label="Gap & Go"
          description="Opening gap momentum strategy (9:15–9:45)"
          enabled={settings.gap_go_enabled}
          onChange={(v) => mutate({ gap_go_enabled: v })}
          disabled={isPending}
        />
        <ToggleSwitch
          label="ORB (Opening Range Breakout)"
          description="Breakout from 30-min opening range (9:45–11:00)"
          enabled={settings.orb_enabled}
          onChange={(v) => mutate({ orb_enabled: v })}
          disabled={isPending}
        />
        <ToggleSwitch
          label="VWAP Reversal"
          description="Mean-reversion from VWAP deviation (10:00–14:30)"
          enabled={settings.vwap_enabled}
          onChange={(v) => mutate({ vwap_enabled: v })}
          disabled={isPending}
        />
      </div>
    </Card>
  );
}
