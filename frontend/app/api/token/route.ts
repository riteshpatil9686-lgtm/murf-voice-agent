/**
 * app/api/token/route.ts
 *
 * Issues LiveKit participant tokens.
 *
 * Security changes vs. the original:
 * - Requires a valid NextAuth session (Google Sign-In).
 * - Embeds the authenticated Google user ID into LiveKit room metadata
 *   as `learner_id` so the backend agent can read it securely.
 * - The client cannot forge a different learner_id because:
 *   (a) the session is validated server-side before the token is minted, and
 *   (b) the room metadata is signed inside the LiveKit JWT — the client has
 *       no way to alter it after issuance.
 * - Room name is a fresh random value per conversation (session ≠ identity).
 */
import { NextResponse } from 'next/server';
import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { RoomConfiguration } from '@livekit/protocol';
import { auth } from '@/auth';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

const API_KEY = process.env.LIVEKIT_API_KEY;
const API_SECRET = process.env.LIVEKIT_API_SECRET;
const LIVEKIT_URL = process.env.LIVEKIT_URL;
const AGENT_NAME = process.env.AGENT_NAME;

export const revalidate = 0;

export async function POST(req: Request) {
  try {
    // ── 1. Require an authenticated Google session ──────────────────────────
    const session = await auth();
    if (!session?.user?.id) {
      return new NextResponse('Unauthorized — please sign in with Google first.', {
        status: 401,
      });
    }

    // Stable Google user ID — this is the learner_id used in PostgreSQL
    const learnerId: string = session.user.id;
    const learnerName: string = session.user.name ?? 'Learner';

    console.log(`[DIAGNOSTIC] Google session user ID: ${learnerId}`);
    console.log(`[DIAGNOSTIC] learner_id embedded in LiveKit token: ${learnerId}`);

    // ── 2. Validate required env vars ────────────────────────────────────────
    if (!LIVEKIT_URL) throw new Error('LIVEKIT_URL is not defined');
    if (!API_KEY) throw new Error('LIVEKIT_API_KEY is not defined');
    if (!API_SECRET) throw new Error('LIVEKIT_API_SECRET is not defined');

    // ── 3. Parse room_config & inject learner_id into agent job metadata ──────
    const body = await req.json().catch(() => ({}));
    let roomConfig: RoomConfiguration | undefined;

    const agentMetadata = JSON.stringify({ learner_id: learnerId });
    const targetAgentName = AGENT_NAME ?? 'my-agent';

    const rawConfig = body?.room_config
      ? (typeof body.room_config === 'string' ? JSON.parse(body.room_config) : body.room_config)
      : {};

    if (!rawConfig.agents || !Array.isArray(rawConfig.agents) || rawConfig.agents.length === 0) {
      rawConfig.agents = [{ agentName: targetAgentName, metadata: agentMetadata }];
    } else {
      rawConfig.agents[0].metadata = agentMetadata;
    }

    roomConfig = RoomConfiguration.fromJson(rawConfig, { ignoreUnknownFields: true });

    // ── 4. Generate a fresh room name per conversation ────────────────────────
    const roomName = `deutschmate_room_${Math.floor(Math.random() * 100_000)}`;

    // ── 5. Embed the authenticated learner_id in metadata (signed JWT) ─────────
    const roomMetadata = JSON.stringify({ learner_id: learnerId });

    // ── 6. Mint the participant token ─────────────────────────────────────────
    const participantIdentity = `google_${learnerId}`;
    const participantToken = await createParticipantToken(
      { identity: participantIdentity, name: learnerName, metadata: roomMetadata },
      roomName,
      roomMetadata,
      roomConfig
    );

    // ── 7. Return connection details ───────────────────────────────────────────
    const data: ConnectionDetails = {
      serverUrl: LIVEKIT_URL,
      roomName,
      participantName: learnerName,
      participantToken,
    };

    return NextResponse.json(data, {
      headers: { 'Cache-Control': 'no-store' },
    });
  } catch (error) {
    console.error('[/api/token]', error);
    if (error instanceof Error) {
      return new NextResponse(error.message, { status: 500 });
    }
    return new NextResponse('Internal server error', { status: 500 });
  }
}

function createParticipantToken(
  userInfo: AccessTokenOptions,
  roomName: string,
  roomMetadata: string,
  roomConfig?: RoomConfiguration
): Promise<string> {
  const at = new AccessToken(API_KEY, API_SECRET, {
    ...userInfo,
    ttl: '15m',
  });

  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
    // Embed learner_id as room metadata so the agent can trust it
    roomRecord: false,
  };
  at.addGrant(grant);

  // Pass the metadata so the agent receives it via ctx.room.metadata
  at.metadata = roomMetadata;

  if (roomConfig) {
    at.roomConfig = roomConfig;
  }

  return at.toJwt();
}
