#!/usr/bin/env python3
"""dialer_pacer.py — how many lines may we dial at once, right now.

`dialer_compliance.py` answers "may I call this person". This answers "may I
call several people at once and take whoever answers first". They are
different questions with different law behind them.

When you dial several lines and connect to the first answer, every *other*
person who picked up gets dropped. Those are abandoned calls, and they are
metered: no more than 3% of calls answered live by a person, per campaign,
over a rolling 30 days. This module measures that rate from your own call
history and decides the line count for you, rather than letting you pick a
number and hope.

The arithmetic is unforgiving for a solo agent. Abandoned calls are the
answers you could not take, so with one agent every simultaneous second
answer is an abandonment:

    human answer rate    2 lines   3 lines   4 lines
                  5%        2.5%      4.9%      7.3%
                 10%        5.0%      9.7%     14.0%
                 20%       10.0%     18.7%     26.2%

Only the 5% / 2-line cell is under the ceiling. Multi-line dialing is a
feature of agent *pools* — the pool absorbs the extra answers. Add a second
agent and the same 10% answer rate supports 4 lines at 1.6%.

So the governor's honest answer at one agent is usually one line. The speed
you actually want there comes from answering-machine detection and instant
auto-advance, not from parallelism: roughly three quarters of dials never
reach a human, and skipping those is most of the throughput.

Usage:
    python dialer_pacer.py campaign create "FE September"
    python dialer_pacer.py simulate --answer-rate 0.10 --agents 1
    python dialer_pacer.py pace "FE September"
    python dialer_pacer.py record "FE September" --lines 2 --agents 1 \
        --results human,no_answer
    python dialer_pacer.py report "FE September"

Shares dialer.db with dialer_compliance.py.
"""

import argparse
import math
import os
import sys
from datetime import timedelta

import dialer_compliance as dc

# ---------------------------------------------------------------------------
# SETTINGS — every one of these is a compliance decision.
# ---------------------------------------------------------------------------

DEFAULT_DB = dc.DEFAULT_DB

# The federal ceiling is 3% of calls answered live by a person, per campaign,
# over a rolling 30 days. We govern to a lower number so that normal variance
# never pushes the real rate through the ceiling.
LEGAL_CEILING = 0.03
TARGET_ABANDON_RATE = 0.015     # what the line recommendation aims at
THROTTLE_AT = 0.020             # measured rate here -> force single line
HALT_AT = 0.027                 # measured rate here -> stop the campaign

MEASUREMENT_WINDOW_DAYS = 30    # the regulation's window, not ours to change
MAX_LINES = 5

# Do not trust an answer rate estimated from a handful of calls. Below this
# many dials in the window, the governor stays at one line.
MIN_SAMPLE_FOR_MULTILINE = 150

# Ring at least this long before hanging up on an unanswered call.
MIN_RING_SECONDS = 15
MIN_RINGS = 4

# A call not connected to a live rep within this many seconds of the greeting
# is abandoned, and owes the recorded identification message.
CONNECT_DEADLINE_SECONDS = 2

# Safe harbor requires the abandonment message to name the seller and give a
# callback number. Fill these in before you dial.
ABANDON_MESSAGE = (
    "Hello. This is a call from {seller}. We're sorry we missed you. "
    "Please call us back at {callback}. To be placed on our do-not-call "
    "list, call that same number."
)
SELLER_NAME = ""     # e.g. "Jay Insurance Agency"
CALLBACK_NUMBER = ""  # a number a human actually answers

# Call results we record. Only "human" counts toward the abandonment
# denominator — a voicemail pickup is not a person, which is exactly why
# answering machine detection buys you headroom.
RESULTS = ["human", "machine", "no_answer", "busy", "failed"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaigns (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    halted     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bursts (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
    lines       INTEGER NOT NULL,
    agents      INTEGER NOT NULL,
    started_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS burst_calls (
    id            INTEGER PRIMARY KEY,
    burst_id      INTEGER NOT NULL REFERENCES bursts(id),
    phone         TEXT,
    result        TEXT NOT NULL,
    connected     INTEGER NOT NULL DEFAULT 0,
    abandoned     INTEGER NOT NULL DEFAULT 0,
    ring_seconds  REAL,
    abandon_msg   INTEGER NOT NULL DEFAULT 0,
    at            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_burst_calls ON burst_calls (burst_id, at);
"""


def open_db(path):
    conn = dc.init_db(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------

def expected_abandon_rate(p, lines, agents):
    """Predicted TSR abandonment rate for one burst.

    Answers are Binomial(lines, p). Agents absorb up to `agents` of them; the
    rest are abandoned. The TSR denominator is calls answered live by a
    person, which is every answer, taken or not.
    """
    # An unmeasured answer rate is not a zero one. Callers must not guess.
    if p is None:
        raise ValueError("answer rate is unknown; cannot model abandonment")
    if lines <= 0 or p <= 0:
        return 0.0
    expected_answers = lines * p
    abandoned = sum(
        (k - agents) * math.comb(lines, k) * p**k * (1 - p) ** (lines - k)
        for k in range(agents + 1, lines + 1)
    )
    return abandoned / expected_answers


def recommend_lines(p, agents, target=TARGET_ABANDON_RATE, max_lines=MAX_LINES):
    """Most lines we can dial and still expect to stay under `target`."""
    best = 1
    for lines in range(1, max_lines + 1):
        if expected_abandon_rate(p, lines, agents) <= target:
            best = lines
    return best


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------

def get_campaign(conn, name, create=False):
    row = conn.execute("SELECT * FROM campaigns WHERE name = ?", (name,)).fetchone()
    if row is None and create:
        conn.execute(
            "INSERT INTO campaigns (name, created_at) VALUES (?,?)",
            (name, dc.iso(dc.now_utc())),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM campaigns WHERE name = ?", (name,)).fetchone()
    return row


def window_stats(conn, campaign_id, at=None):
    """Counts over the rolling regulatory window."""
    at = at or dc.now_utc()
    since = dc.iso(at - timedelta(days=MEASUREMENT_WINDOW_DAYS))
    row = conn.execute(
        """SELECT
             COUNT(*)                                   AS dials,
             SUM(CASE WHEN result='human' THEN 1 ELSE 0 END)   AS humans,
             SUM(CASE WHEN result='machine' THEN 1 ELSE 0 END) AS machines,
             SUM(abandoned)                             AS abandoned,
             SUM(CASE WHEN abandoned=1 AND abandon_msg=0 THEN 1 ELSE 0 END)
                                                        AS silent_drops
           FROM burst_calls bc
           JOIN bursts b ON b.id = bc.burst_id
           WHERE b.campaign_id = ? AND bc.at >= ?""",
        (campaign_id, since),
    ).fetchone()

    dials = row["dials"] or 0
    humans = row["humans"] or 0
    return {
        "dials": dials,
        "humans": humans,
        "machines": row["machines"] or 0,
        "abandoned": row["abandoned"] or 0,
        "silent_drops": row["silent_drops"] or 0,
        "human_answer_rate": (humans / dials) if dials else None,
        "abandon_rate": ((row["abandoned"] or 0) / humans) if humans else None,
    }


def governor(conn, campaign, agents=1, at=None):
    """Decide the line count and say why. Returns a dict."""
    stats = window_stats(conn, campaign["id"], at)
    state, reasons = "NORMAL", []

    if campaign["halted"]:
        return {"state": "HALTED", "lines": 0, "stats": stats,
                "reasons": ["campaign is halted; clear it with `resume` once you "
                            "have fixed what caused the abandonment"]}

    measured = stats["abandon_rate"]
    if measured is not None:
        if measured >= HALT_AT:
            conn.execute("UPDATE campaigns SET halted=1 WHERE id=?", (campaign["id"],))
            conn.commit()
            dc.audit(conn, None, "PACE_HALT",
                     [f"abandon rate {measured:.2%} >= {HALT_AT:.1%}"], campaign["name"])
            return {"state": "HALTED", "lines": 0, "stats": stats,
                    "reasons": [f"measured abandonment {measured:.2%} reached the "
                                f"halt threshold {HALT_AT:.1%} (ceiling {LEGAL_CEILING:.0%})"]}
        if measured >= THROTTLE_AT:
            state = "THROTTLED"
            reasons.append(
                f"measured abandonment {measured:.2%} is at or above the throttle "
                f"threshold {THROTTLE_AT:.1%} — single line until it decays"
            )
            return {"state": state, "lines": 1, "stats": stats, "reasons": reasons}

    if stats["silent_drops"]:
        return {"state": "THROTTLED", "lines": 1, "stats": stats,
                "reasons": [f"{stats['silent_drops']} abandoned calls went out without "
                            "the required identification message — fix that before "
                            "dialing multi-line"]}

    if not SELLER_NAME or not CALLBACK_NUMBER:
        return {"state": "THROTTLED", "lines": 1, "stats": stats,
                "reasons": ["SELLER_NAME / CALLBACK_NUMBER are unset, so an abandoned "
                            "call could not play a compliant message — single line"]}

    p = stats["human_answer_rate"]
    if p is None:
        return {"state": "MEASURING", "lines": 1, "stats": stats,
                "reasons": ["no dials in the window yet, so there is no answer rate "
                            "to reason from — start at one line"]}
    if stats["dials"] < MIN_SAMPLE_FOR_MULTILINE:
        return {"state": "MEASURING", "lines": 1, "stats": stats,
                "reasons": [f"only {stats['dials']} dials in the window; need "
                            f"{MIN_SAMPLE_FOR_MULTILINE} before trusting an answer rate"]}

    lines = recommend_lines(p, agents)
    predicted = expected_abandon_rate(p, lines, agents)
    reasons.append(
        f"human answer rate {p:.1%} over {stats['dials']} dials with {agents} agent(s) "
        f"supports {lines} line(s) at a predicted {predicted:.2%}"
    )
    if lines == 1:
        reasons.append(
            "no multi-line headroom at this answer rate — the throughput is in "
            "answering-machine detection and auto-advance, not parallelism"
        )
    return {"state": state, "lines": lines, "stats": stats, "reasons": reasons}


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_burst(conn, campaign, lines, agents, results, phones=None,
                 ring_seconds=None, abandon_msg=True):
    """Record one dial burst and work out which calls were abandoned.

    `results` is one entry per line dialed. The first human answer connects to
    an agent; further humans beyond the available agents are abandoned.
    """
    for r in results:
        if r not in RESULTS:
            raise ValueError(f"unknown result {r!r}; expected one of {RESULTS}")
    if ring_seconds is not None and ring_seconds < MIN_RING_SECONDS:
        raise ValueError(
            f"ring_seconds {ring_seconds} is under the {MIN_RING_SECONDS}s "
            f"/ {MIN_RINGS}-ring minimum for an unanswered call"
        )

    at = dc.now_utc()
    cur = conn.execute(
        "INSERT INTO bursts (campaign_id, lines, agents, started_at) VALUES (?,?,?,?)",
        (campaign["id"], lines, agents, dc.iso(at)),
    )
    burst_id = cur.lastrowid

    seats = agents
    abandoned_count = 0
    for i, result in enumerate(results):
        phone = phones[i] if phones and i < len(phones) else None
        connected = abandoned = 0
        if result == "human":
            if seats > 0:
                seats -= 1
                connected = 1
            else:
                abandoned = 1
                abandoned_count += 1
        conn.execute(
            """INSERT INTO burst_calls
               (burst_id, phone, result, connected, abandoned, ring_seconds, abandon_msg, at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (burst_id, phone, result, connected, abandoned, ring_seconds,
             1 if (abandoned and abandon_msg) else 0, dc.iso(at)),
        )
    conn.commit()

    if abandoned_count:
        dc.audit(conn, None, "ABANDON",
                 [f"{abandoned_count} abandoned in burst {burst_id}"], campaign["name"])
    return burst_id, abandoned_count


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_campaign_create(args):
    conn = open_db(args.db)
    if get_campaign(conn, args.name):
        print(f"Campaign {args.name!r} already exists.", file=sys.stderr)
        return 1
    get_campaign(conn, args.name, create=True)
    print(f"Created campaign {args.name!r}.")
    print(f"Governing to {TARGET_ABANDON_RATE:.1%} against a {LEGAL_CEILING:.0%} ceiling.")
    if not SELLER_NAME or not CALLBACK_NUMBER:
        print("\n  Set SELLER_NAME and CALLBACK_NUMBER before dialing — without them")
        print("  an abandoned call cannot play a compliant message, and the")
        print("  governor will hold you at one line.")
    return 0


def cmd_campaign_list(args):
    conn = open_db(args.db)
    rows = conn.execute("SELECT * FROM campaigns ORDER BY created_at").fetchall()
    if not rows:
        print("No campaigns.")
        return 0
    for r in rows:
        s = window_stats(conn, r["id"])
        rate = f"{s['abandon_rate']:.2%}" if s["abandon_rate"] is not None else "n/a"
        flag = "  [HALTED]" if r["halted"] else ""
        print(f"  {r['name']:<28} dials {s['dials']:>6}  abandon {rate:>7}{flag}")
    return 0


def cmd_pace(args):
    conn = open_db(args.db)
    campaign = get_campaign(conn, args.name)
    if not campaign:
        print(f"No campaign {args.name!r}.", file=sys.stderr)
        return 1

    g = governor(conn, campaign, agents=args.agents)
    s = g["stats"]

    print(f"  Campaign          {campaign['name']}")
    print(f"  Window            {MEASUREMENT_WINDOW_DAYS} days")
    print(f"  Dials             {s['dials']}")
    print(f"  Human answers     {s['humans']}"
          + (f"  ({s['human_answer_rate']:.1%})" if s["human_answer_rate"] is not None else ""))
    print(f"  Machine answers   {s['machines']}")
    print(f"  Abandoned         {s['abandoned']}"
          + (f"  ({s['abandon_rate']:.2%} of live answers)" if s["abandon_rate"] is not None else ""))
    if s["silent_drops"]:
        print(f"  Silent drops      {s['silent_drops']}   <- no identification message")
    print()
    print(f"  State             {g['state']}")
    print(f"  Dial              {g['lines']} line(s) with {args.agents} agent(s)")
    for r in g["reasons"]:
        print(f"                    {r}")
    return 0


def cmd_record(args):
    conn = open_db(args.db)
    campaign = get_campaign(conn, args.name, create=True)
    results = [r.strip() for r in args.results.split(",") if r.strip()]
    if len(results) != args.lines:
        print(f"Gave {args.lines} lines but {len(results)} results.", file=sys.stderr)
        return 1
    try:
        burst_id, abandoned = record_burst(
            conn, campaign, args.lines, args.agents, results,
            ring_seconds=args.ring_seconds, abandon_msg=not args.no_message,
        )
    except ValueError as exc:
        print(f"Rejected: {exc}", file=sys.stderr)
        return 1

    print(f"Recorded burst {burst_id}: {args.lines} lines, {results.count('human')} human, "
          f"{abandoned} abandoned.")
    g = governor(conn, campaign, agents=args.agents)
    if g["state"] != "NORMAL":
        print(f"\n  {g['state']} — {g['reasons'][0]}")
    return 0


def cmd_simulate(args):
    p, agents = args.answer_rate, args.agents
    print(f"  Human answer rate {p:.1%},  {agents} agent(s)\n")
    print(f"  {'lines':>6}  {'predicted abandon':>18}  verdict")
    print("  " + "-" * 48)
    for lines in range(1, args.max_lines + 1):
        r = expected_abandon_rate(p, lines, agents)
        if r > LEGAL_CEILING:
            verdict = "ILLEGAL (over 3%)"
        elif r > TARGET_ABANDON_RATE:
            verdict = "legal but no margin"
        else:
            verdict = "ok"
        print(f"  {lines:>6}  {r:>17.2%}  {verdict}")
    best = recommend_lines(p, agents, max_lines=args.max_lines)
    print(f"\n  Recommended: {best} line(s) "
          f"(predicted {expected_abandon_rate(p, best, agents):.2%})")
    if best == 1 and agents == 1:
        print("  Add a second agent and re-run — the pool is what makes multi-line work.")
    return 0


def cmd_resume(args):
    conn = open_db(args.db)
    campaign = get_campaign(conn, args.name)
    if not campaign:
        print(f"No campaign {args.name!r}.", file=sys.stderr)
        return 1
    stats = window_stats(conn, campaign["id"])
    measured = stats["abandon_rate"]

    conn.execute("UPDATE campaigns SET halted=0 WHERE id=?", (campaign["id"],))
    conn.commit()
    dc.audit(conn, None, "PACE_RESUME", [args.reason or "manual"], campaign["name"])
    print(f"Resumed {args.name!r}. It restarts at one line and must re-earn more.")

    # Be honest about the rolling window: clearing the flag does not clear the
    # history the rate is computed from.
    if measured is not None and measured >= HALT_AT:
        oldest = conn.execute(
            """SELECT MIN(bc.at) AS t FROM burst_calls bc
               JOIN bursts b ON b.id = bc.burst_id WHERE b.campaign_id = ?""",
            (campaign["id"],),
        ).fetchone()["t"]
        print(
            f"\n  Heads up: the measured rate is still {measured:.2%}, over the "
            f"{HALT_AT:.1%} halt threshold,\n  so the next `pace` call will halt it "
            f"again. The rate is computed over a rolling\n  {MEASUREMENT_WINDOW_DAYS} days, "
            f"and clearing the halt does not clear that history."
        )
        if oldest:
            clears = dc.parse_dt(oldest) + timedelta(days=MEASUREMENT_WINDOW_DAYS)
            print(f"  The oldest call in the window ages out {dc.iso(clears)[:10]}.")
        print("  Dial single-line under a new campaign name if you need to keep working.")
    return 0


def cmd_report(args):
    """The records the safe harbor expects you to be able to produce."""
    conn = open_db(args.db)
    campaign = get_campaign(conn, args.name)
    if not campaign:
        print(f"No campaign {args.name!r}.", file=sys.stderr)
        return 1
    s = window_stats(conn, campaign["id"])
    print(f"  Abandonment record — {campaign['name']}")
    print(f"  Rolling {MEASUREMENT_WINDOW_DAYS}-day window ending {dc.iso(dc.now_utc())[:10]}\n")
    print(f"    Calls placed                     {s['dials']}")
    print(f"    Answered live by a person        {s['humans']}")
    print(f"    Answered by machine              {s['machines']}")
    print(f"    Abandoned                        {s['abandoned']}")
    rate = f"{s['abandon_rate']:.3%}" if s["abandon_rate"] is not None else "n/a"
    print(f"    Abandonment rate                 {rate}  (ceiling {LEGAL_CEILING:.0%})")
    print(f"    Abandoned without a message      {s['silent_drops']}")
    print(f"\n    Minimum ring enforced            {MIN_RING_SECONDS}s / {MIN_RINGS} rings")
    print(f"    Connect deadline                 {CONNECT_DEADLINE_SECONDS}s")
    print(f"    Identification message           "
          f"{'SET' if SELLER_NAME and CALLBACK_NUMBER else 'NOT SET'}")
    if s["abandon_rate"] is not None and s["abandon_rate"] > LEGAL_CEILING:
        print("\n    OVER THE CEILING for this window.")
    return 0


def build_parser():
    p = argparse.ArgumentParser(description="Pacing governor for multi-line dialing.")
    p.add_argument("--db", default=DEFAULT_DB)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("campaign")
    csub = sp.add_subparsers(dest="campaign_command", required=True)
    c = csub.add_parser("create"); c.add_argument("name"); c.set_defaults(func=cmd_campaign_create)
    csub.add_parser("list").set_defaults(func=cmd_campaign_list)

    sp = sub.add_parser("pace", help="how many lines may I dial right now")
    sp.add_argument("name"); sp.add_argument("--agents", type=int, default=1)
    sp.set_defaults(func=cmd_pace)

    sp = sub.add_parser("record", help="record a dial burst")
    sp.add_argument("name")
    sp.add_argument("--lines", type=int, required=True)
    sp.add_argument("--agents", type=int, default=1)
    sp.add_argument("--results", required=True, help="comma list, one per line: " + "|".join(RESULTS))
    sp.add_argument("--ring-seconds", type=float)
    sp.add_argument("--no-message", action="store_true",
                    help="record that no identification message was played (a violation)")
    sp.set_defaults(func=cmd_record)

    sp = sub.add_parser("simulate", help="model the abandonment rate before dialing")
    sp.add_argument("--answer-rate", type=float, required=True)
    sp.add_argument("--agents", type=int, default=1)
    sp.add_argument("--max-lines", type=int, default=MAX_LINES)
    sp.set_defaults(func=cmd_simulate)

    sp = sub.add_parser("resume", help="clear a halt")
    sp.add_argument("name"); sp.add_argument("--reason")
    sp.set_defaults(func=cmd_resume)

    sp = sub.add_parser("report", help="safe-harbor abandonment record")
    sp.add_argument("name"); sp.set_defaults(func=cmd_report)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
