import asyncio
import json
import logging
import os
import random
import urllib.error
import urllib.request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_practice")

FALLBACK_DATA_PATH = r"c:\Users\DELL\OneDrive\Desktop\Voice For Bharat\murf-livekit-starter\backend\data\german_exercises.json"

def _normalize_cefr(level_str: str) -> str:
    lvl = (level_str or "").strip().lower()
    if lvl in ("a1", "beginner", "elementar"):
        return "A1"
    elif lvl in ("a2", "grundlegend"):
        return "A2"
    elif lvl in ("b1", "intermediate", "mittelstufe"):
        return "B1"
    elif lvl in ("b2", "fortgeschritten", "advanced"):
        return "B2"
    elif lvl in ("c1", "c2", "expert"):
        return "C1"
    return "A1"

def _load_local_fallback_exercise(level: str = "", topic: str = "", practice_type: str = "") -> dict | None:
    if not os.path.exists(FALLBACK_DATA_PATH):
        logger.error("Fallback data file does not exist at %s", FALLBACK_DATA_PATH)
        return None
    try:
        with open(FALLBACK_DATA_PATH, "r", encoding="utf-8") as f:
            exercises = json.load(f)
        if not exercises:
            return None

        # Filter by level if provided
        norm_level = _normalize_cefr(level).lower()
        level_filtered = [
            e for e in exercises
            if e.get("level", "").lower() == norm_level or e.get("level", "").lower() in ("beginner", "intermediate", "advanced")
        ]
        pool = level_filtered if level_filtered else exercises

        # Filter by topic if provided
        if topic:
            t_lower = topic.strip().lower()
            topic_filtered = [e for e in pool if t_lower in e.get("topic", "").lower()]
            if topic_filtered:
                pool = topic_filtered

        # Filter by practice_type if provided
        if practice_type:
            pt_lower = practice_type.strip().lower()
            pt_filtered = [e for e in pool if pt_lower in e.get("type", "").lower()]
            if pt_filtered:
                pool = pt_filtered

        chosen = random.choice(pool)
        return {
            "status": "success",
            "source": "local_fallback",
            "note": "The online learning library isn't available right now, so I'll use an offline exercise instead.",
            "level": chosen.get("level", level or "beginner"),
            "topic": chosen.get("topic", topic or "general"),
            "practice_type": chosen.get("type", practice_type or "general"),
            "question": chosen.get("question", ""),
            "answer": chosen.get("answer", ""),
        }
    except Exception as exc:
        logger.error("Error reading local fallback file: %s", exc)
        return None

def _fetch_external_german_practice_sync(level: str = "", topic: str = "", practice_type: str = "") -> dict | None:
    api_key = os.getenv("GERMAN_API_KEY", "demo-key-12345")
    base_url = "https://german-language.onrender.com"
    headers = {
        "X-API-Key": api_key,
        "User-Agent": "DeutschMate/1.0",
    }
    cefr = _normalize_cefr(level)
    pt = (practice_type or "").strip().lower()
    top = (topic or "").strip().lower()

    logger.info("Fetching German practice from external API (level=%s, topic=%s, type=%s)", cefr, top, pt)

    try:
        if pt == "grammar" or top == "grammar":
            url = f"{base_url}/grammar?limit=10"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not items:
                return None
            item = random.choice(items)
            title = item.get("title") or item.get("category") or "German Grammar Rule"
            rule = item.get("rule") or item.get("description") or item.get("explanation") or ""
            examples = item.get("examples") or []
            ex_str = f" Example: '{examples[0]}'" if examples else ""
            return {
                "status": "success",
                "source": "external_api",
                "level": cefr,
                "topic": item.get("category", "grammar"),
                "practice_type": "grammar",
                "question": f"Grammar Topic: {title}. Rule: {rule}. Can you construct a German sentence following this rule?",
                "answer": f"Correct rule usage: {rule}.{ex_str}",
            }
        elif pt == "vocabulary" or top == "vocabulary":
            if top and top != "vocabulary":
                url = f"{base_url}/vocab/search?q={urllib.parse.quote(top)}&limit=10"
            else:
                url = f"{base_url}/vocab?level={cefr.lower()}&limit=20"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not items:
                return None
            item = random.choice(items)
            eng = item.get("english", "")
            ger = item.get("german", "")
            gender = item.get("gender") or ""
            pos = item.get("pos", "word")
            gender_str = f" ({gender})" if gender else ""
            return {
                "status": "success",
                "source": "external_api",
                "level": item.get("level", cefr),
                "topic": "vocabulary",
                "practice_type": "vocabulary",
                "question": f"What is the German word for '{eng}' ({pos})?",
                "answer": f"The German word for '{eng}' is '{ger}'{gender_str}.",
            }
        else:
            # Default / Sentence translation practice
            url = f"{base_url}/sentences/random?level={cefr}&count=5"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not items:
                return None
            item = random.choice(items)
            sen_de = item.get("sentence_de", "")
            sen_en = item.get("sentence_en", "")
            return {
                "status": "success",
                "source": "external_api",
                "level": item.get("level", cefr),
                "topic": topic or "general_practice",
                "practice_type": practice_type or "sentence_translation",
                "question": f"Translate to German: '{sen_en}'",
                "answer": f"'{sen_de}'",
            }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, KeyError, IndexError) as exc:
        logger.warning("External learning API unavailable or failed [%s]: %s", type(exc).__name__, exc)
        return None

async def fetch_german_practice(level: str = "", topic: str = "", practice_type: str = "") -> dict:
    result = await asyncio.to_thread(_fetch_external_german_practice_sync, level, topic, practice_type)
    if result:
        logger.info("German practice retrieved successfully from external API")
        return result
    
    logger.info("External learning API unavailable; using local fallback")
    fallback_result = _load_local_fallback_exercise(level, topic, practice_type)
    if fallback_result:
        return fallback_result
    
    return {
        "status": "error",
        "message": "I'm unable to load an exercise right now. Please try again in a moment."
    }

async def main():
    print("\n--- TEST 1: Sentence Practice (External API) ---")
    res1 = await fetch_german_practice(level="A1", topic="travel", practice_type="sentence")
    print(json.dumps(res1, indent=2))

    print("\n--- TEST 2: Vocab Practice (External API) ---")
    res2 = await fetch_german_practice(level="A1", practice_type="vocabulary")
    print(json.dumps(res2, indent=2))

    print("\n--- TEST 3: Grammar Practice (External API) ---")
    res3 = await fetch_german_practice(practice_type="grammar")
    print(json.dumps(res3, indent=2))

    print("\n--- TEST 4: Fallback Simulation (Bad URL) ---")
    # Save original base_url and force error
    res4 = _load_local_fallback_exercise(level="beginner", topic="travel", practice_type="translation")
    print(json.dumps(res4, indent=2))

if __name__ == "__main__":
    asyncio.run(main())
