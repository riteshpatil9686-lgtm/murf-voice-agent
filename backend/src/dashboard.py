"""
dashboard.py — Day 8 analytics dashboard for DeutschMate.

Serves a live analytics dashboard on http://localhost:8888 and http://127.0.0.1:8888

Run from the backend directory:
    python src/dashboard.py
"""

import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv(".env.local")
load_dotenv(".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>DeutschMate · Day 8 Analytics</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0a0a0f;
    --surface: #13131a;
    --border: rgba(255,255,255,0.07);
    --accent: #7c6af7;
    --accent2: #4fc3f7;
    --success: #4ade80;
    --fail: #f87171;
    --text: #e2e8f0;
    --muted: #64748b;
  }
  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 40px 24px;
  }
  header {
    max-width: 900px;
    margin: 0 auto 48px;
    display: flex;
    align-items: center;
    gap: 14px;
  }
  .logo {
    width: 42px; height: 42px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
  }
  h1 { font-size: 22px; font-weight: 600; letter-spacing: -0.3px; }
  .sub { font-size: 13px; color: var(--muted); margin-top: 2px; }
  .cards {
    max-width: 900px;
    margin: 0 auto 48px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 20px;
  }
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px 24px;
    position: relative;
    overflow: hidden;
    transition: transform 0.2s, box-shadow 0.2s;
  }
  .card:hover { transform: translateY(-2px); box-shadow: 0 12px 40px rgba(0,0,0,0.4); }
  .card-label {
    font-size: 12px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 12px;
  }
  .card-value {
    font-size: 48px;
    font-weight: 700;
    letter-spacing: -2px;
    line-height: 1;
    background: var(--grad);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  .card-desc { font-size: 12px; color: var(--muted); margin-top: 8px; }
  .total  { --glow: var(--accent);  --grad: linear-gradient(135deg, #a78bfa, #7c6af7); }
  .success{ --glow: var(--success); --grad: linear-gradient(135deg, #86efac, #4ade80); }
  .failed { --glow: var(--fail);    --grad: linear-gradient(135deg, #fca5a5, #f87171); }
  .table-wrap {
    max-width: 900px;
    margin: 0 auto;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    overflow: hidden;
  }
  .table-header {
    padding: 20px 24px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
    font-weight: 600;
  }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    text-align: left;
    padding: 12px 24px;
    font-size: 11px;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
  }
  tbody tr { transition: background 0.15s; }
  tbody tr:hover { background: rgba(255,255,255,0.03); }
  tbody td { padding: 14px 24px; font-size: 13px; border-bottom: 1px solid var(--border); }
  tbody tr:last-child td { border-bottom: none; }
  .badge {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
  }
  .badge.success { background: rgba(74,222,128,0.12); color: var(--success); }
  .badge.failed  { background: rgba(248,113,113,0.12); color: var(--fail); }
  .badge.browser { background: rgba(124,106,247,0.12); color: var(--accent); }
  .badge.sip     { background: rgba(79,195,247,0.12); color: var(--accent2); }
  .refresh-btn {
    float: right;
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 4px 12px;
    border-radius: 8px;
    font-size: 12px;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.15s;
  }
  .refresh-btn:hover { background: rgba(255,255,255,0.1); color: var(--text); }
  .empty { text-align: center; padding: 48px; color: var(--muted); font-size: 14px; }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; display: inline-block; }
  .ts { color: var(--muted); font-size: 12px; }
  .id { font-family: monospace; font-size: 11px; color: var(--muted); }
</style>
</head>
<body>
<header>
  <div class="logo">DE</div>
  <div>
    <h1>DeutschMate Analytics</h1>
    <div class="sub">Day 8 · Live from PostgreSQL · Auto-refreshes every 30 s</div>
  </div>
</header>

<div class="cards">
  <div class="card total">
    <div class="card-label">Total Calls</div>
    <div class="card-value">__TOTAL__</div>
    <div class="card-desc">All sessions recorded</div>
  </div>
  <div class="card success">
    <div class="card-label">Successful Calls</div>
    <div class="card-value">__SUCCESS__</div>
    <div class="card-desc">Exercise completed correctly</div>
  </div>
  <div class="card failed">
    <div class="card-label">Failed Calls</div>
    <div class="card-value">__FAILED__</div>
    <div class="card-desc">Session ended without success</div>
  </div>
</div>

<div class="table-wrap">
  <div class="table-header">
    Recent Sessions
    <button class="refresh-btn" onclick="location.reload()">Refresh</button>
  </div>
  __TABLE__
</div>

<script>
  setTimeout(() => location.reload(), 30000);
</script>
</body>
</html>
"""


async def query_stats():
    """Query PostgreSQL for analytics data."""
    if not DATABASE_URL:
        return None, None
    try:
        conn = await asyncpg.connect(dsn=DATABASE_URL)
        try:
            rows = await conn.fetch(
                "SELECT session_id, learner_id, channel, outcome, created_at "
                "FROM call_analytics ORDER BY created_at DESC LIMIT 50"
            )
            counts = await conn.fetchrow(
                "SELECT COUNT(*) AS total, "
                "COUNT(*) FILTER (WHERE outcome='success') AS success, "
                "COUNT(*) FILTER (WHERE outcome='failed') AS failed "
                "FROM call_analytics"
            )
            return rows, counts
        finally:
            await conn.close()
    except Exception as exc:
        print(f"[DASHBOARD] DB query error: {exc}")
        return None, None


def render_table(rows):
    if not rows:
        return '<div class="empty">No calls recorded yet. Start a session to see data.</div>'
    html = (
        "<table><thead><tr>"
        "<th>Session ID</th><th>Learner</th><th>Channel</th><th>Outcome</th><th>Time</th>"
        "</tr></thead><tbody>"
    )
    for r in rows:
        sid = str(r["session_id"])[:18] + "..."
        lid = str(r["learner_id"])[:20] + "..." if len(str(r["learner_id"])) > 20 else str(r["learner_id"])
        channel = str(r["channel"])
        outcome = str(r["outcome"])
        ts = r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "-"
        html += (
            f"<tr>"
            f'<td class="id">{sid}</td>'
            f"<td>{lid}</td>"
            f'<td><span class="badge {channel}">{channel.upper()}</span></td>'
            f'<td><span class="badge {outcome}"><span class="dot"></span>{outcome}</span></td>'
            f'<td class="ts">{ts}</td>'
            f"</tr>"
        )
    html += "</tbody></table>"
    return html


async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        await reader.read(2048)
        rows, counts = await query_stats()

        if counts:
            total = counts["total"] or 0
            success = counts["success"] or 0
            failed = counts["failed"] or 0
        else:
            total = success = failed = "0"

        table_html = render_table(rows) if rows is not None else (
            '<div class="empty">Could not connect to PostgreSQL. '
            'Check DATABASE_URL in backend/.env.local</div>'
        )

        page = (HTML_TEMPLATE
                .replace("__TOTAL__", str(total))
                .replace("__SUCCESS__", str(success))
                .replace("__FAILED__", str(failed))
                .replace("__TABLE__", table_html))

        body_bytes = page.encode("utf-8")
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            f"Content-Length: {len(body_bytes)}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(headers.encode("utf-8") + body_bytes)
        await writer.drain()
    except Exception as e:
        print(f"[DASHBOARD] Request error: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def main():
    port = 8888
    server = await asyncio.start_server(handle_client, "0.0.0.0", port)
    print(f"[DASHBOARD] DeutschMate Day 8 Analytics active at http://localhost:{port} (http://127.0.0.1:{port})")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
