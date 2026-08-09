'use client';
/**
 * components/app/auth-provider.tsx
 *
 * Wraps the app in NextAuth's client-side SessionProvider.
 * Must be a client component because SessionProvider uses React context.
 */
import { SessionProvider } from 'next-auth/react';

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  return <SessionProvider>{children}</SessionProvider>;
}
