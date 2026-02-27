import { useSettings } from '@/hooks/useSettings';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ErrorDisplay } from '@/components/common/ErrorDisplay';
import { CapitalRiskForm } from '@/components/settings/CapitalRiskForm';
import { StrategyToggles } from '@/components/settings/StrategyToggles';
import { HybridScoringForm } from '@/components/settings/HybridScoringForm';
import { NotificationPrefs } from '@/components/settings/NotificationPrefs';
import { DataExport } from '@/components/settings/DataExport';

export default function Settings() {
  const { data, isLoading, error, refetch } = useSettings();

  if (isLoading) return <LoadingSpinner message="Loading settings..." />;
  if (error) return <ErrorDisplay error={error} onRetry={refetch} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Settings</h1>

      <CapitalRiskForm settings={data} />
      <StrategyToggles settings={data} />
      <HybridScoringForm settings={data} />
      <NotificationPrefs settings={data} />
      <DataExport />
    </div>
  );
}
