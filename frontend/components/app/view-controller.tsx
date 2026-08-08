'use client';

import type { AppConfig } from '@/app-config';
import { DeutschMateView } from '@/components/app/deutschmate-view';

interface ViewControllerProps {
  appConfig: AppConfig;
}

export function ViewController({ appConfig: _appConfig }: ViewControllerProps) {
  return <DeutschMateView />;
}

