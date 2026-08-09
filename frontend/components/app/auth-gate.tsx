'use client';
/**
 * components/app/auth-gate.tsx
 *
 * Shows a Google Sign-In screen when the user is not authenticated.
 * Renders children once the user is signed in.
 *
 * Uses the existing DeutschMate liquid-glass aesthetic — no new styling system.
 */
import { signIn, signOut, useSession } from 'next-auth/react';
import { Loader2 } from 'lucide-react';

interface AuthGateProps {
  children: React.ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const { data: session, status } = useSession();

  // ── Loading ───────────────────────────────────────────────────────────────
  if (status === 'loading') {
    return (
      <div className="bg-black flex h-screen w-full items-center justify-center">
        <Loader2 className="text-white/60 size-8 animate-spin" />
      </div>
    );
  }

  // ── Not signed in — show Google Sign-In gate ──────────────────────────────
  if (status === 'unauthenticated' || !session) {
    return (
      <div className="bg-black text-white relative flex h-screen min-h-screen w-full flex-col items-center justify-center overflow-hidden selection:bg-white selection:text-black">
        {/* Background video — same as main view */}
        <video
          className="absolute inset-0 z-0 h-full w-full object-cover object-bottom opacity-60"
          src="https://designerstephen.github.io/public-assets/videos/observe-hero.mp4"
          muted
          autoPlay
          loop
          playsInline
          preload="auto"
          style={{ playbackRate: 0.5 } as React.CSSProperties}
        />

        {/* Sign-in card */}
        <div
          className="relative z-10 flex flex-col items-center gap-6 rounded-3xl px-10 py-10 text-center"
          style={{
            background: 'rgba(255,255,255,0.06)',
            backdropFilter: 'blur(24px)',
            WebkitBackdropFilter: 'blur(24px)',
            border: '1px solid rgba(255,255,255,0.12)',
            boxShadow: '0 8px 40px rgba(0,0,0,0.5)',
          }}
        >
          {/* Logo */}
          <div className="flex flex-col items-center gap-2">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
              aria-hidden="true"
              className="text-white size-10 shrink-0"
            >
              <path
                d="M4.21 16.5 A9 9 0 0 1 16.5 4.21"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
              <path
                d="M16.5 4.21 A9 9 0 0 1 19.79 16.5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="2.4 2.3"
              />
              <path
                d="M19.79 16.5 A9 9 0 0 1 4.21 16.5"
                stroke="currentColor"
                strokeWidth="2.6"
                strokeLinecap="round"
                strokeDasharray="0.01 4.7"
              />
              <circle cx="12" cy="12" r="2.5" fill="currentColor" />
            </svg>
            <span className="text-white text-2xl font-semibold tracking-tight">DeutschMate</span>
            <span className="text-white/60 text-sm font-normal">Your AI German Tutor</span>
          </div>

          {/* Description */}
          <div className="max-w-xs space-y-1">
            <p className="text-white/85 text-sm leading-relaxed">
              Sign in to remember your German level, track your progress, and continue exactly where you left off.
            </p>
          </div>

          {/* Google Sign-In Button */}
          <button
            id="google-signin-btn"
            onClick={() => signIn('google', { callbackUrl: '/' })}
            className="flex items-center gap-3 rounded-full bg-white px-6 py-3 text-sm font-semibold text-gray-800 shadow-lg transition-all hover:bg-gray-50 hover:shadow-xl active:scale-95 focus:outline-none focus:ring-2 focus:ring-white/50"
          >
            {/* Google G logo */}
            <svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg">
              <g fill="none" fillRule="evenodd">
                <path
                  d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
                  fill="#4285F4"
                />
                <path
                  d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z"
                  fill="#34A853"
                />
                <path
                  d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
                  fill="#FBBC05"
                />
                <path
                  d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
                  fill="#EA4335"
                />
              </g>
            </svg>
            Continue with Google
          </button>

          <p className="text-white/40 text-xs leading-relaxed max-w-xs">
            Your learning data is stored privately and never shared.
            <br />
            You can chat without saving — consent is always asked first.
          </p>
        </div>

        {/* Footer */}
        <p
          className="relative z-10 mt-6 text-white/40 text-xs tracking-wide"
          style={{ textShadow: '0 1px 8px rgba(0,0,0,0.6)' }}
        >
          Built for VoiceForBharat · Powered by Murf Falcon
        </p>
      </div>
    );
  }

  // ── Authenticated — render the main app ───────────────────────────────────
  return <>{children}</>;
}

/**
 * Small floating sign-out button shown in the top-right corner when signed in.
 * Import and place this inside DeutschMateView's navbar if desired.
 */
export function SignOutButton() {
  const { data: session } = useSession();
  if (!session) return null;

  return (
    <button
      id="signout-btn"
      onClick={() => signOut({ callbackUrl: '/' })}
      className="flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium text-white/70 transition-colors hover:text-white hover:bg-white/10 focus:outline-none focus:ring-1 focus:ring-white/30"
      title={`Signed in as ${session.user?.name ?? session.user?.email}`}
    >
      {session.user?.image && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={session.user.image}
          alt={session.user.name ?? 'User'}
          className="size-5 rounded-full object-cover"
        />
      )}
      <span className="hidden sm:inline">{session.user?.name?.split(' ')[0] ?? 'Account'}</span>
      <span className="text-white/40">·</span>
      <span>Sign out</span>
    </button>
  );
}
