/**
 * auth.ts — NextAuth v5 configuration for DeutschMate.
 *
 * Google is the only provider. The Google account's `sub` (subject) field
 * is a stable, globally unique ID for that Google account — used as learner_id.
 *
 * NEXT_AUTH_SECRET and GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are
 * read from environment variables only; never hardcoded.
 */
import NextAuth from 'next-auth';
import Google from 'next-auth/providers/google';

export const { handlers, signIn, signOut, auth } = NextAuth({
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
  ],

  callbacks: {
    /**
     * Persist the Google `sub` (profile.id) into the JWT so it is available
     * in the session without a database round-trip.
     */
    async jwt({ token, account, profile }) {
      if (account && profile) {
        // `profile.sub` is the stable Google user ID
        token.googleId = (profile.sub as string) || (account.providerAccountId as string);
        token.name = profile.name as string;
        token.email = profile.email as string;
        token.picture = (profile as { picture?: string }).picture ?? '';
      }
      if (!token.googleId && token.sub) {
        token.googleId = token.sub;
      }
      return token;
    },

    /**
     * Expose googleId on the client-side session object.
     * Only safe fields — no refresh tokens or secrets reach the client.
     */
    async session({ session, token }) {
      if (session?.user) {
        const id = (token?.googleId as string) || (token?.sub as string);
        if (id) {
          session.user.id = id;
        }
      }
      return session;
    },
  },
});

