"""
outbound_call.py — Day 6: Daily German Practice Call trigger for DeutschMate.

Usage:
    uv run python src/outbound_call.py \\
        --sip-uri "sip:justtcocoo@sip.linphone.org" \\
        --learner-id "109912924948936435507"

How it works:
    This script does NOT dial the number directly. It uses the LiveKit
    Dispatch API to create a new room and tell the DeutschMate agent worker
    (already running via `python src/agent.py dev`) to connect to that room.

    The agent's outbound_practice_session() entrypoint then uses
    ctx.api.sip.create_sip_participant() to dial the Linphone SIP address.
    When the learner answers, the agent speaks first with the transparent
    introduction, then begins the German practice session.

Architecture (official LiveKit outbound approach):
    [This script]
        → LiveKit Dispatch API (create new room + dispatch agent)
        → DeutschMate agent worker picks up the dispatch job
        → agent.py: outbound_practice_session() runs
            → ctx.api.sip.create_sip_participant(sip_call_to=sip_uri)
            → Linphone receives incoming ring
            → Learner answers
            → Agent speaks first: transparent introduction
            → German practice session begins

Requirements:
    - The DeutschMate agent must already be running:
        uv run python src/agent.py dev
    - SIP_OUTBOUND_TRUNK_ID must be set in .env.local
    - A LiveKit SIP Outbound Trunk must be configured in LiveKit Cloud
    - Linphone must be registered at the target SIP URI


"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import json
import uuid

from dotenv import load_dotenv

# Load environment — same order as agent.py
load_dotenv(".env.local")
load_dotenv(".env")
load_dotenv()

logger = logging.getLogger("deutschmate.outbound")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _check_env() -> dict[str, str]:
    """Validate required environment variables before attempting any API call."""
    required = {
        "LIVEKIT_URL": os.getenv("LIVEKIT_URL", "").strip(),
        "LIVEKIT_API_KEY": os.getenv("LIVEKIT_API_KEY", "").strip(),
        "LIVEKIT_API_SECRET": os.getenv("LIVEKIT_API_SECRET", "").strip(),
        "SIP_OUTBOUND_TRUNK_ID": os.getenv("SIP_OUTBOUND_TRUNK_ID", "").strip(),
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        print("\n❌  Missing required environment variables:")
        for m in missing:
            print(f"    {m}")
        print(
            "\nSet these in backend/.env.local before triggering an outbound call.\n"
            "See backend/.env.example for documentation.\n"
        )
        sys.exit(1)
    return required


async def dispatch_outbound_call(sip_uri: str, learner_id: str) -> None:
    """
    Dispatch the DeutschMate outbound-practice agent job via LiveKit API.

    The metadata JSON attached to this dispatch is read by the agent's
    outbound_practice_session() entrypoint via ctx.job.metadata.
    The learner_id stored here is the authenticated Google 'sub' ID,
    ensuring Day 4 PostgreSQL memory is correctly loaded.

    Args:
        sip_uri:    Full SIP address to dial, e.g. "sip:user@sip.linphone.org"
        learner_id: Authenticated Google account 'sub' ID (stable learner identity).
    """
    from livekit import api  # import here so env is loaded first

    env = _check_env()

    # Build the metadata payload that the agent reads via ctx.job.metadata.
    # The agent's _get_learner_id() reads 'learner_id' from this JSON dict
    # (highest-priority branch in the existing implementation).
    metadata = json.dumps({
        "sip_uri": sip_uri,
        "learner_id": learner_id,
        "call_type": "daily_german_practice",
    })

    lk_url = env["LIVEKIT_URL"]

    print(f"\n📞  DeutschMate Daily German Practice Call")
    print(f"    SIP target : {sip_uri}")
    print(f"    Learner ID : {learner_id}")
    print(f"    LiveKit    : {lk_url}")
    print(f"    Trunk ID   : {env['SIP_OUTBOUND_TRUNK_ID']}")
    print(f"\n🚀  Dispatching agent job…\n")

    lk_api = api.LiveKitAPI(
        url=lk_url,
        api_key=env["LIVEKIT_API_KEY"],
        api_secret=env["LIVEKIT_API_SECRET"],
    )

    try:
        # Generate a unique room name for this outbound call session
        room_name = f"deutschmate_outbound_{uuid.uuid4().hex[:8]}"

        # Dispatch to the single registered agent worker ("my-agent" / AGENT_NAME)
        agent_name = os.getenv("AGENT_NAME", "my-agent")
        dispatch = await lk_api.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=agent_name,
                room=room_name,
                metadata=metadata,
            )
        )
        logger.info(
            "Agent dispatched successfully | dispatch_id=%s | room=%s",
            dispatch.id,
            dispatch.room,
        )
        print(f"✅  Agent dispatched.")
        print(f"    Dispatch ID : {dispatch.id}")
        print(f"    Room        : {dispatch.room}")
        print(f"\n📱  Linphone should ring at {sip_uri} within a few seconds.")
        print(f"    Answer the call to start your German practice session.\n")

    except Exception as exc:
        # Report the error clearly without exposing any secrets.
        error_type = type(exc).__name__
        # Redact any accidental credential leakage from error messages
        msg = str(exc).replace(env["LIVEKIT_API_KEY"], "***").replace(
            env["LIVEKIT_API_SECRET"], "***"
        )
        print(f"\n❌  Failed to dispatch outbound call.")
        print(f"    Error type : {error_type}")
        print(f"    Details    : {msg}")
        print(f"\nTroubleshooting:")
        print(f"  1. Verify the DeutschMate agent is running:  uv run python src/agent.py dev")
        print(f"  2. Verify LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET in .env.local")
        print(f"  3. Verify SIP_OUTBOUND_TRUNK_ID is correct (LiveKit Cloud → SIP → Outbound Trunks)")
        print(f"  4. Verify the SIP URI format: sip:username@sip.linphone.org")
        logger.error("Dispatch failed [%s]: %s", error_type, msg)
        sys.exit(1)

    finally:
        await lk_api.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="outbound_call.py",
        description=(
            "DeutschMate Day 6 — Trigger a Daily German Practice outbound call "
            "to a Linphone SIP address."
        ),
    )
    parser.add_argument(
        "--sip-uri",
        required=True,
        help=(
            'Full SIP URI of the Linphone target, e.g. "sip:testuser@sip.linphone.org". '
            "The learner must have Linphone open and registered at this address."
        ),
    )
    parser.add_argument(
        "--learner-id",
        required=True,
        help=(
            "The learner's authenticated Google 'sub' ID (stable identity from Day 4). "
            "This is used to load PostgreSQL memory for the call. "
            "Do NOT use a name, phone number, or room name here."
        ),
    )
    args = parser.parse_args()

    sip_uri = args.sip_uri.strip()
    learner_id = args.learner_id.strip()

    # Validate SIP URI format (basic check — must begin with "sip:")
    if not sip_uri.startswith("sip:"):
        print(f"\n❌  Invalid SIP URI: '{sip_uri}'")
        print("    SIP URIs must begin with 'sip:', e.g.: sip:testuser@sip.linphone.org\n")
        sys.exit(1)

    if not learner_id:
        print("\n❌  --learner-id cannot be empty.")
        print("    Pass the authenticated Google 'sub' ID from your DeutschMate session.\n")
        sys.exit(1)

    asyncio.run(dispatch_outbound_call(sip_uri, learner_id))


if __name__ == "__main__":
    main()
