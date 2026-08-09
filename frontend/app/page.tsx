import { headers } from 'next/headers';
import { App } from '@/components/app/app';
import { AuthGate } from '@/components/app/auth-gate';
import { getAppConfig } from '@/lib/utils';

export default async function Page() {
  const hdrs = await headers();
  const appConfig = await getAppConfig(hdrs);

  return (
    <AuthGate>
      <App appConfig={appConfig} />
    </AuthGate>
  );
}
