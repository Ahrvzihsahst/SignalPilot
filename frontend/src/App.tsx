import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { AppLayout } from '@/components/layout/AppLayout';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { lazy, Suspense } from 'react';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';

const LiveSignals = lazy(() => import('@/pages/LiveSignals'));
const TradeJournal = lazy(() => import('@/pages/TradeJournal'));
const PerformanceCharts = lazy(() => import('@/pages/PerformanceCharts'));
const StrategyComparison = lazy(() => import('@/pages/StrategyComparison'));
const CapitalAllocation = lazy(() => import('@/pages/CapitalAllocation'));
const Settings = lazy(() => import('@/pages/Settings'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 2,
      refetchOnWindowFocus: true,
    },
  },
});

function LazyWrapper({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingSpinner />}>{children}</Suspense>;
}

const router = createBrowserRouter([
  {
    element: <AppLayout />,
    errorElement: <ErrorBoundary><div /></ErrorBoundary>,
    children: [
      { index: true, element: <LazyWrapper><LiveSignals /></LazyWrapper> },
      { path: 'trades', element: <LazyWrapper><TradeJournal /></LazyWrapper> },
      { path: 'performance', element: <LazyWrapper><PerformanceCharts /></LazyWrapper> },
      { path: 'strategies', element: <LazyWrapper><StrategyComparison /></LazyWrapper> },
      { path: 'allocation', element: <LazyWrapper><CapitalAllocation /></LazyWrapper> },
      { path: 'settings', element: <LazyWrapper><Settings /></LazyWrapper> },
    ],
  },
]);

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
