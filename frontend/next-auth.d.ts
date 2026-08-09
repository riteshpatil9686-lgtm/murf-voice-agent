/**
 * next-auth.d.ts — Extend NextAuth session types to include the Google user ID.
 */
import 'next-auth';

declare module 'next-auth' {
  interface Session {
    user: {
      id: string;        // stable Google sub (user_id)
      name?: string | null;
      email?: string | null;
      image?: string | null;
    };
  }
}
