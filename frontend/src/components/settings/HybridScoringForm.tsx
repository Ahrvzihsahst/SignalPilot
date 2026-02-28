import type { UserSettings } from '@/types/api';
import { Card } from '@/components/common/Card';
import { useUpdateSettings } from '@/hooks/useSettings';
import { cn } from '@/utils/cn';

interface HybridScoringFormProps {
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
    <div className="flex items-center justify-between py-3">
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

const ADAPTATION_MODES = [
  { value: 'conservative', label: 'Conservative' },
  { value: 'moderate', label: 'Moderate' },
  { value: 'aggressive', label: 'Aggressive' },
];

export function HybridScoringForm({ settings }: HybridScoringFormProps) {
  const { mutate, isPending } = useUpdateSettings();

  return (
    <Card title="Hybrid Scoring & Adaptation">
      <div className="divide-y divide-gray-100">
        <ToggleSwitch
          label="Confidence Boost"
          description="Increase position size for multi-strategy confirmed signals"
          enabled={settings.confidence_boost_enabled}
          onChange={(v) => mutate({ confidence_boost_enabled: v })}
          disabled={isPending}
        />
        <ToggleSwitch
          label="Adaptive Learning"
          description="Dynamically adjust strategy weights based on recent performance"
          enabled={settings.adaptive_learning_enabled}
          onChange={(v) => mutate({ adaptive_learning_enabled: v })}
          disabled={isPending}
        />
        <ToggleSwitch
          label="Auto-Rebalance"
          description="Automatically rebalance capital weights weekly"
          enabled={settings.auto_rebalance_enabled}
          onChange={(v) => mutate({ auto_rebalance_enabled: v })}
          disabled={isPending}
        />
        <div className="flex items-center justify-between py-3">
          <div>
            <p className="text-sm font-medium text-gray-900">Adaptation Mode</p>
            <p className="text-xs text-gray-500">
              Controls how aggressively weights shift with performance changes
            </p>
          </div>
          <select
            value={settings.adaptation_mode}
            onChange={(e) => mutate({ adaptation_mode: e.target.value })}
            disabled={isPending || !settings.adaptive_learning_enabled}
            className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-blue-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          >
            {ADAPTATION_MODES.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </div>
      </div>
    </Card>
  );
}
