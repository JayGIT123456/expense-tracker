#!/usr/bin/env python3
"""dialer_compliance.py — the gate every outbound call has to pass first.

This is layer 1 of the power dialer: it decides whether a given lead may be
called *right now*, and writes down why. Nothing here places a call. The
dialer asks this module, and only dials on an explicit ALLOW.

The whole file is built to fail closed. Missing consent, a stale DNC scrub, an
unknown time zone and a scrub that was never run all produce the same answer:
BLOCKED. A lead becomes callable by having its paperwork in order, never by
having no paperwork at all.

Usage:
    python dialer_compliance.py init
    python dialer_compliance.py import leads.csv
    python dialer_compliance.py check 3055550182
    python dialer_compliance.py next --limit 25
    python dialer_compliance.py scrub due
    python dialer_compliance.py scrub set 3055550182 --list federal --result clear
    python dialer_compliance.py dnc add 3055550182 --reason "asked to be removed"
    python dialer_compliance.py attempt 3055550182 --outcome no_answer
    python dialer_compliance.py audit --phone 3055550182

Data lives in dialer.db (override with --db). SQLite rather than CSV: the
audit trail has to be append-only and survive a crash mid-write, and that is
exactly what a spreadsheet cannot promise.
"""

import argparse
import csv
import os
import re
import sqlite3
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# SETTINGS — these are the lines to change when you want different behavior.
# Every one of them is a compliance decision. Loosen them deliberately.
# ---------------------------------------------------------------------------

DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dialer.db")

# Federal calling window, enforced in the CALLED PARTY'S local time.
# 8am-9pm is the federal floor; some states are stricter, so if you write
# business in one of those, tighten this rather than tracking it per state.
CALL_WINDOW_START = time(8, 0)
CALL_WINDOW_END = time(21, 0)

# A DNC scrub goes stale. The federal safe harbor expects the registry to have
# been checked within 31 days of the call.
SCRUB_MAX_AGE_DAYS = 31

# Every list named here must have a fresh, clear scrub on file before a number
# is callable. "federal" and "state" are the legal minimum; "litigator" is the
# one that keeps professional plaintiffs out of your queue. Add "rnd" if you
# subscribe to the Reassigned Numbers Database.
REQUIRED_SCRUB_LISTS = ["federal", "state", "litigator"]

# Written consent does not expire on its own, but a lead that opted in two
# years ago and forgot you is both a bad call and a bad look in front of a
# jury. Warn past this age; set to None to disable the warning.
CONSENT_STALE_WARN_DAYS = 90

# Require full prior-express-WRITTEN-consent paperwork (timestamp, IP, source
# URL and the exact disclosure language shown to the lead). The consent rules
# are in the middle of a circuit split, so this defaults to the strictest
# reading. Setting it False accepts bare express consent and is a real
# increase in exposure.
REQUIRE_WRITTEN_CONSENT = True

# Contact frequency. Not strictly federal law, but carriers, lead vendors and
# juries all have opinions, and these caps are what "reasonable" looks like.
MAX_ATTEMPTS_TOTAL = 8
MAX_ATTEMPTS_PER_DAY = 2
MIN_MINUTES_BETWEEN_ATTEMPTS = 240

# No usable address means the time zone is a guess, and a guess is how you
# dial someone at 6am. Leave this True.
BLOCK_WHEN_TIMEZONE_UNKNOWN = True

# Call outcomes that permanently add the number to the internal DNC list.
DNC_OUTCOMES = ["dnc_request", "do_not_call", "hostile"]

VALID_OUTCOMES = [
    "connected", "no_answer", "voicemail", "busy", "bad_number",
    "callback", "not_interested", "sold", "dnc_request", "do_not_call",
    "hostile",
]


# ---------------------------------------------------------------------------
# TIME ZONES — a state can span two of them, so we check every zone it touches
# and only allow the call when the window is open in all of them. Dialing an
# hour late is a nuisance; dialing an hour early is a violation.
# ---------------------------------------------------------------------------

STATE_ZONES = {
    "AL": ["America/Chicago"],
    "AK": ["America/Anchorage", "America/Adak"],
    "AZ": ["America/Phoenix", "America/Denver"],
    "AR": ["America/Chicago"],
    "CA": ["America/Los_Angeles"],
    "CO": ["America/Denver"],
    "CT": ["America/New_York"],
    "DE": ["America/New_York"],
    "DC": ["America/New_York"],
    "FL": ["America/New_York", "America/Chicago"],
    "GA": ["America/New_York"],
    "HI": ["Pacific/Honolulu"],
    "ID": ["America/Boise", "America/Los_Angeles"],
    "IL": ["America/Chicago"],
    "IN": ["America/Indiana/Indianapolis", "America/Chicago"],
    "IA": ["America/Chicago"],
    "KS": ["America/Chicago", "America/Denver"],
    "KY": ["America/New_York", "America/Chicago"],
    "LA": ["America/Chicago"],
    "ME": ["America/New_York"],
    "MD": ["America/New_York"],
    "MA": ["America/New_York"],
    "MI": ["America/Detroit", "America/Menominee"],
    "MN": ["America/Chicago"],
    "MS": ["America/Chicago"],
    "MO": ["America/Chicago"],
    "MT": ["America/Denver"],
    "NE": ["America/Chicago", "America/Denver"],
    "NV": ["America/Los_Angeles", "America/Boise"],
    "NH": ["America/New_York"],
    "NJ": ["America/New_York"],
    "NM": ["America/Denver"],
    "NY": ["America/New_York"],
    "NC": ["America/New_York"],
    "ND": ["America/Chicago", "America/Denver"],
    "OH": ["America/New_York"],
    "OK": ["America/Chicago"],
    "OR": ["America/Los_Angeles", "America/Boise"],
    "PA": ["America/New_York"],
    "RI": ["America/New_York"],
    "SC": ["America/New_York"],
    "SD": ["America/Chicago", "America/Denver"],
    "TN": ["America/New_York", "America/Chicago"],
    "TX": ["America/Chicago", "America/Denver"],
    "UT": ["America/Denver"],
    "VT": ["America/New_York"],
    "VA": ["America/New_York"],
    "WA": ["America/Los_Angeles"],
    "WV": ["America/New_York"],
    "WI": ["America/Chicago"],
    "WY": ["America/Denver"],
    "PR": ["America/Puerto_Rico"],
    "VI": ["America/St_Thomas"],
    "GU": ["Pacific/Guam"],
    "AS": ["Pacific/Pago_Pago"],
    "MP": ["Pacific/Saipan"],
}

# Area code -> state, used only as a cross-check and as a last resort when a
# lead has no address. Mobile numbers keep their area code across a move, so
# this is a hint, never proof — see resolve_zones().
_AREA_CODES_BY_STATE = {
    "AL": "205 251 256 334 659 938",
    "AK": "907",
    "AZ": "480 520 602 623 928",
    "AR": "327 479 501 870",
    "CA": "209 213 279 310 323 341 350 369 408 415 424 442 510 530 559 562 619 626 628 650 657 661 669 707 714 747 760 805 818 820 831 840 858 909 916 925 949 951",
    "CO": "303 719 720 970 983",
    "CT": "203 475 860 959",
    "DE": "302",
    "DC": "202",
    "FL": "239 305 321 324 352 386 407 448 561 645 656 689 727 728 754 772 786 813 850 863 904 941 954",
    "GA": "229 404 470 478 678 706 762 770 912 943",
    "HI": "808",
    "ID": "208 986",
    "IL": "217 224 309 312 331 447 464 618 630 708 730 773 779 815 847 861 872",
    "IN": "219 260 317 463 574 765 812 930",
    "IA": "319 515 563 641 712",
    "KS": "316 620 785 913",
    "KY": "270 364 502 606 859",
    "LA": "225 318 337 504 985",
    "ME": "207",
    "MD": "227 240 301 410 443 667",
    "MA": "339 351 413 508 617 774 781 857 978",
    "MI": "231 248 269 313 517 586 616 679 734 810 906 947 989",
    "MN": "218 320 507 612 651 763 924 952",
    "MS": "228 601 662 769",
    "MO": "235 314 417 557 573 636 660 816 975",
    "MT": "406",
    "NE": "308 402 531",
    "NV": "702 725 775",
    "NH": "603",
    "NJ": "201 551 609 640 732 848 856 862 908 973",
    "NM": "505 575",
    "NY": "212 315 329 332 347 363 516 518 585 607 624 631 646 680 716 718 838 845 914 917 929 934",
    "NC": "336 472 704 743 828 910 919 980 984",
    "ND": "701",
    "OH": "216 220 234 283 326 330 380 419 436 440 513 567 614 740 937",
    "OK": "405 539 572 580 918",
    "OR": "458 503 541 971",
    "PA": "215 223 267 272 412 445 484 570 582 610 717 724 814 835 878",
    "RI": "401",
    "SC": "803 821 839 843 854 864",
    "SD": "605",
    "TN": "423 615 629 731 865 901 931",
    "TX": "210 214 254 281 325 346 361 409 430 432 469 512 682 713 726 737 806 817 830 832 903 915 936 940 945 956 972 979",
    "UT": "385 435 801",
    "VT": "802",
    "VA": "276 434 540 571 686 703 757 804 826 948",
    "WA": "206 253 360 425 509 564",
    "WV": "304 681",
    "WI": "262 274 353 414 534 608 715 920",
    "WY": "307",
    "PR": "787 939",
    "VI": "340",
    "GU": "671",
    "AS": "684",
    "MP": "670",
}

AREA_CODE_STATE = {
    code: state
    for state, codes in _AREA_CODES_BY_STATE.items()
    for code in codes.split()
}

LEAD_IMPORT_FIELDS = [
    "phone", "first_name", "last_name", "state", "zip", "source",
    "consent_type", "consent_timestamp", "consent_ip", "consent_url",
    "consent_text",
]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id                INTEGER PRIMARY KEY,
    phone             TEXT NOT NULL UNIQUE,
    first_name        TEXT,
    last_name         TEXT,
    state             TEXT,
    zip               TEXT,
    source            TEXT,
    consent_type      TEXT,
    consent_timestamp TEXT,
    consent_ip        TEXT,
    consent_url       TEXT,
    consent_text      TEXT,
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrubs (
    id         INTEGER PRIMARY KEY,
    phone      TEXT NOT NULL,
    list_name  TEXT NOT NULL,
    result     TEXT NOT NULL,          -- clear | listed
    provider   TEXT,
    checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scrubs_phone ON scrubs (phone, list_name, checked_at);

CREATE TABLE IF NOT EXISTS internal_dnc (
    phone    TEXT PRIMARY KEY,
    reason   TEXT,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    id           INTEGER PRIMARY KEY,
    phone        TEXT NOT NULL,
    outcome      TEXT NOT NULL,
    note         TEXT,
    attempted_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_attempts_phone ON attempts (phone, attempted_at);

-- Append-only. The triggers below are the point: a compliance log you can
-- quietly edit after the fact is worth nothing in front of a regulator.
CREATE TABLE IF NOT EXISTS audit (
    id       INTEGER PRIMARY KEY,
    at       TEXT NOT NULL,
    phone    TEXT,
    decision TEXT NOT NULL,
    reasons  TEXT,
    detail   TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_phone ON audit (phone, at);

CREATE TRIGGER IF NOT EXISTS audit_no_update
BEFORE UPDATE ON audit
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;

CREATE TRIGGER IF NOT EXISTS audit_no_delete
BEFORE DELETE ON audit
BEGIN SELECT RAISE(ABORT, 'audit log is append-only'); END;
"""


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path):
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def now_utc():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_dt(value):
    """Parse a stored or imported timestamp, assuming UTC when none is given."""
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y", "%m/%d/%Y %H:%M"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def normalize_phone(raw):
    """Return a 10-digit NANP number, or None if it cannot be one."""
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    # NANP: area code and exchange both start 2-9.
    if digits[0] in "01" or digits[3] in "01":
        return None
    return digits


def audit(conn, phone, decision, reasons=None, detail=None):
    conn.execute(
        "INSERT INTO audit (at, phone, decision, reasons, detail) VALUES (?,?,?,?,?)",
        (iso(now_utc()), phone, decision, "; ".join(reasons or []), detail),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

class Decision:
    """The answer to 'may I dial this number right now', plus the reasoning."""

    def __init__(self, phone):
        self.phone = phone
        self.blocks = []
        self.warnings = []
        self.notes = []

    @property
    def allowed(self):
        return not self.blocks

    def block(self, reason):
        self.blocks.append(reason)

    def warn(self, reason):
        self.warnings.append(reason)

    def note(self, text):
        self.notes.append(text)

    def __str__(self):
        head = "ALLOW" if self.allowed else "BLOCK"
        lines = [f"{head}  {self.phone}"]
        for b in self.blocks:
            lines.append(f"  [block]   {b}")
        for w in self.warnings:
            lines.append(f"  [warn]    {w}")
        for n in self.notes:
            lines.append(f"  [note]    {n}")
        return "\n".join(lines)


def resolve_zones(lead):
    """Time zones the lead might be in, and how confident we are.

    Returns (zones, source). The address wins when it disagrees with the area
    code, because people keep their mobile number when they move. A conflict
    is worth surfacing but is not by itself a reason to block.
    """
    state = (lead["state"] or "").strip().upper()
    area_state = AREA_CODE_STATE.get(lead["phone"][:3]) if lead["phone"] else None

    if state in STATE_ZONES:
        source = "address"
        if area_state and area_state != state:
            source = f"address (area code says {area_state})"
        return STATE_ZONES[state], source

    if area_state:
        return STATE_ZONES[area_state], f"area code only ({area_state})"

    return [], "unknown"


def check_calling_window(decision, lead, at):
    zones, source = resolve_zones(lead)

    if not zones:
        msg = "no state on file and area code is unrecognized, so local time is unknown"
        if BLOCK_WHEN_TIMEZONE_UNKNOWN:
            decision.block(msg)
        else:
            decision.warn(msg)
        return

    if source.startswith("area code only"):
        decision.warn(f"time zone derived from {source}; get the address on file")
    elif "area code says" in source:
        decision.warn(f"time zone from {source}")

    closed = []
    for name in zones:
        local = at.astimezone(ZoneInfo(name))
        if not (CALL_WINDOW_START <= local.time() <= CALL_WINDOW_END):
            closed.append(f"{name} {local.strftime('%H:%M')}")

    if closed:
        window = f"{CALL_WINDOW_START:%H:%M}-{CALL_WINDOW_END:%H:%M}"
        decision.block(
            f"outside the {window} calling window in " + ", ".join(closed)
        )
    else:
        shown = ", ".join(
            f"{n.split('/')[-1]} {at.astimezone(ZoneInfo(n)):%H:%M}" for n in zones
        )
        decision.note(f"local time {shown} (via {source})")


def check_consent(decision, lead, at):
    ctype = (lead["consent_type"] or "").strip().lower()
    stamp = parse_dt(lead["consent_timestamp"])

    if not ctype:
        decision.block("no consent record on file")
        return
    if ctype not in ("written", "express"):
        decision.block(f"unrecognized consent type {ctype!r}")
        return
    if REQUIRE_WRITTEN_CONSENT and ctype != "written":
        decision.block(
            f"consent on file is {ctype!r}; prior express WRITTEN consent required"
        )
    if not stamp:
        decision.block("consent has no usable timestamp")
    if not (lead["source"] or "").strip():
        decision.block("consent has no source recorded")

    if REQUIRE_WRITTEN_CONSENT:
        for field, label in (
            ("consent_ip", "capture IP"),
            ("consent_url", "source URL"),
            ("consent_text", "the exact disclosure language shown"),
        ):
            if not (lead[field] or "").strip():
                decision.block(f"written consent is missing {label}")

    if stamp and CONSENT_STALE_WARN_DAYS:
        age = (at - stamp).days
        if age > CONSENT_STALE_WARN_DAYS:
            decision.warn(f"consent is {age} days old")


def check_internal_dnc(decision, conn, phone):
    row = conn.execute(
        "SELECT reason, added_at FROM internal_dnc WHERE phone = ?", (phone,)
    ).fetchone()
    if row:
        decision.block(
            f"on your internal DNC since {row['added_at'][:10]}"
            + (f" ({row['reason']})" if row["reason"] else "")
        )


def check_scrubs(decision, conn, phone, at):
    cutoff = at - timedelta(days=SCRUB_MAX_AGE_DAYS)
    for list_name in REQUIRED_SCRUB_LISTS:
        row = conn.execute(
            """SELECT result, checked_at FROM scrubs
               WHERE phone = ? AND list_name = ?
               ORDER BY checked_at DESC LIMIT 1""",
            (phone, list_name),
        ).fetchone()

        if row is None:
            decision.block(f"never scrubbed against the {list_name} list")
            continue
        if row["result"] != "clear":
            decision.block(f"listed on the {list_name} list")
            continue
        checked = parse_dt(row["checked_at"])
        if checked is None or checked < cutoff:
            age = (at - checked).days if checked else "?"
            decision.block(
                f"{list_name} scrub is {age} days old "
                f"(must be within {SCRUB_MAX_AGE_DAYS})"
            )


def check_frequency(decision, conn, phone, at):
    rows = conn.execute(
        "SELECT outcome, attempted_at FROM attempts WHERE phone = ? ORDER BY attempted_at DESC",
        (phone,),
    ).fetchall()
    if not rows:
        return

    stamps = [parse_dt(r["attempted_at"]) for r in rows]
    stamps = [s for s in stamps if s]

    if len(stamps) >= MAX_ATTEMPTS_TOTAL:
        decision.block(f"already attempted {len(stamps)} times (cap {MAX_ATTEMPTS_TOTAL})")

    today = [s for s in stamps if (at - s) < timedelta(days=1)]
    if len(today) >= MAX_ATTEMPTS_PER_DAY:
        decision.block(
            f"{len(today)} attempts in the last 24h (cap {MAX_ATTEMPTS_PER_DAY})"
        )

    if stamps:
        gap = (at - stamps[0]).total_seconds() / 60
        if gap < MIN_MINUTES_BETWEEN_ATTEMPTS:
            wait = int(MIN_MINUTES_BETWEEN_ATTEMPTS - gap)
            decision.block(f"last attempt was {int(gap)} min ago; wait {wait} more min")

    if any(r["outcome"] == "bad_number" for r in rows):
        decision.warn("a previous attempt marked this a bad number")


def evaluate(conn, phone, at=None, log=True):
    """Run every check. The lead is callable only if all of them pass."""
    at = at or now_utc()
    decision = Decision(phone)

    lead = conn.execute("SELECT * FROM leads WHERE phone = ?", (phone,)).fetchone()
    if lead is None:
        decision.block("no lead record — a number with no provenance is never callable")
        if log:
            audit(conn, phone, "BLOCK", decision.blocks)
        return decision

    if lead["first_name"] or lead["last_name"]:
        decision.note(
            f"{(lead['first_name'] or '').strip()} {(lead['last_name'] or '').strip()}".strip()
            + (f" — {lead['source']}" if lead["source"] else "")
        )

    check_internal_dnc(decision, conn, phone)
    check_consent(decision, lead, at)
    check_scrubs(decision, conn, phone, at)
    check_calling_window(decision, lead, at)
    check_frequency(decision, conn, phone, at)

    if log:
        audit(
            conn, phone,
            "ALLOW" if decision.allowed else "BLOCK",
            decision.blocks or decision.warnings,
        )
    return decision


# ---------------------------------------------------------------------------
# Scrub providers
#
# Plug your DNC vendor in here (DNC.com, Blacklist Alliance, whoever). The
# contract is one method that answers "clear" or "listed" for one number and
# one list. The default provider deliberately refuses to answer, so that
# forgetting to wire up a real one blocks the queue instead of silently
# approving every call.
# ---------------------------------------------------------------------------

class ScrubProvider:
    name = "base"

    def check(self, phone, list_name):
        raise NotImplementedError


class NullScrubProvider(ScrubProvider):
    """No vendor configured. Answers nothing, so the gate stays shut."""

    name = "none"

    def check(self, phone, list_name):
        raise RuntimeError(
            "no scrub provider configured — wire one up in ScrubProvider, or "
            "record results manually with `scrub set`"
        )


def record_scrub(conn, phone, list_name, result, provider="manual", at=None):
    if result not in ("clear", "listed"):
        raise ValueError("result must be 'clear' or 'listed'")
    conn.execute(
        "INSERT INTO scrubs (phone, list_name, result, provider, checked_at) VALUES (?,?,?,?,?)",
        (phone, list_name, result, provider, iso(at or now_utc())),
    )
    if result == "listed":
        add_internal_dnc(conn, phone, f"listed on {list_name}")
    conn.commit()
    audit(conn, phone, "SCRUB", [f"{list_name}={result}"], provider)


def add_internal_dnc(conn, phone, reason=None):
    conn.execute(
        "INSERT OR IGNORE INTO internal_dnc (phone, reason, added_at) VALUES (?,?,?)",
        (phone, reason, iso(now_utc())),
    )
    conn.commit()
    audit(conn, phone, "DNC_ADD", [reason or "manual"])


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args):
    init_db(args.db)
    print(f"Initialized {args.db}")
    print(f"Required scrub lists: {', '.join(REQUIRED_SCRUB_LISTS)}")
    print(f"Calling window: {CALL_WINDOW_START:%H:%M}-{CALL_WINDOW_END:%H:%M} local")
    print(f"Written consent required: {REQUIRE_WRITTEN_CONSENT}")


def cmd_import(args):
    conn = init_db(args.db)
    with open(args.csvfile, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        print("No rows found.", file=sys.stderr)
        return 1

    missing = [c for c in ("phone",) if c not in rows[0]]
    if missing:
        print(f"CSV must have a 'phone' column. Found: {list(rows[0])}", file=sys.stderr)
        return 1

    added = skipped = 0
    for line_num, row in enumerate(rows, start=2):
        phone = normalize_phone(row.get("phone"))
        if not phone:
            print(f"  line {line_num}: unusable phone {row.get('phone')!r}", file=sys.stderr)
            skipped += 1
            continue

        values = {k: (row.get(k) or "").strip() for k in LEAD_IMPORT_FIELDS}
        values["phone"] = phone
        values["state"] = values["state"].upper()[:2]

        if args.dry_run:
            print(f"  would import {phone} ({values['state'] or '??'})")
            added += 1
            continue

        try:
            conn.execute(
                f"""INSERT INTO leads ({', '.join(LEAD_IMPORT_FIELDS)}, created_at)
                    VALUES ({', '.join('?' * len(LEAD_IMPORT_FIELDS))}, ?)""",
                [values[k] for k in LEAD_IMPORT_FIELDS] + [iso(now_utc())],
            )
            added += 1
            audit(conn, phone, "IMPORT", [values["source"] or "no source"], args.csvfile)
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    verb = "Would import" if args.dry_run else "Imported"
    print(f"{verb} {added} leads, skipped {skipped}.")
    if not args.dry_run and added:
        print(f"None are callable until scrubbed against: {', '.join(REQUIRED_SCRUB_LISTS)}")
    return 0


def cmd_check(args):
    conn = init_db(args.db)
    phone = normalize_phone(args.phone)
    if not phone:
        print(f"{args.phone!r} is not a valid US number.", file=sys.stderr)
        return 1
    print(evaluate(conn, phone))
    return 0


def cmd_next(args):
    conn = init_db(args.db)
    at = now_utc()
    rows = conn.execute("SELECT phone FROM leads ORDER BY id").fetchall()

    callable_leads = []
    for row in rows:
        decision = evaluate(conn, row["phone"], at=at, log=False)
        if decision.allowed:
            callable_leads.append(decision)
        if len(callable_leads) >= args.limit:
            break

    if not callable_leads:
        print(f"Nothing callable right now (checked {len(rows)} leads).")
        print("Run `scrub due` to see what is waiting on a scrub.")
        return 0

    print(f"{len(callable_leads)} callable now:\n")
    for d in callable_leads:
        note = d.notes[0] if d.notes else ""
        print(f"  {d.phone}  {note}")
        for w in d.warnings:
            print(f"             ! {w}")
    return 0


def cmd_scrub_due(args):
    conn = init_db(args.db)
    at = now_utc()
    cutoff = at - timedelta(days=SCRUB_MAX_AGE_DAYS)

    due = []
    for row in conn.execute("SELECT phone FROM leads ORDER BY id"):
        phone = row["phone"]
        needs = []
        for list_name in REQUIRED_SCRUB_LISTS:
            scrub = conn.execute(
                """SELECT result, checked_at FROM scrubs
                   WHERE phone = ? AND list_name = ?
                   ORDER BY checked_at DESC LIMIT 1""",
                (phone, list_name),
            ).fetchone()
            if scrub is None:
                needs.append(f"{list_name} (never)")
            elif scrub["result"] == "clear":
                checked = parse_dt(scrub["checked_at"])
                if checked is None or checked < cutoff:
                    needs.append(f"{list_name} (stale)")
        if needs:
            due.append((phone, needs))

    if not due:
        print("Every lead has a fresh scrub on all required lists.")
        return 0

    print(f"{len(due)} leads need scrubbing:\n")
    for phone, needs in due[: args.limit]:
        print(f"  {phone}  {', '.join(needs)}")
    if len(due) > args.limit:
        print(f"  ... and {len(due) - args.limit} more")
    return 0


def cmd_scrub_set(args):
    conn = init_db(args.db)
    phone = normalize_phone(args.phone)
    if not phone:
        print(f"{args.phone!r} is not a valid US number.", file=sys.stderr)
        return 1
    record_scrub(conn, phone, args.list, args.result, args.provider)
    print(f"Recorded {args.list}={args.result} for {phone}.")
    if args.result == "listed":
        print("Also added to your internal DNC.")
    return 0


def cmd_dnc_add(args):
    conn = init_db(args.db)
    phone = normalize_phone(args.phone)
    if not phone:
        print(f"{args.phone!r} is not a valid US number.", file=sys.stderr)
        return 1
    add_internal_dnc(conn, phone, args.reason)
    print(f"{phone} added to internal DNC. This is permanent by design.")
    return 0


def cmd_dnc_list(args):
    conn = init_db(args.db)
    rows = conn.execute("SELECT * FROM internal_dnc ORDER BY added_at DESC").fetchall()
    if not rows:
        print("Internal DNC is empty.")
        return 0
    print(f"{len(rows)} numbers on your internal DNC:\n")
    for r in rows:
        print(f"  {r['phone']}  {r['added_at'][:10]}  {r['reason'] or ''}")
    return 0


def cmd_attempt(args):
    conn = init_db(args.db)
    phone = normalize_phone(args.phone)
    if not phone:
        print(f"{args.phone!r} is not a valid US number.", file=sys.stderr)
        return 1

    conn.execute(
        "INSERT INTO attempts (phone, outcome, note, attempted_at) VALUES (?,?,?,?)",
        (phone, args.outcome, args.note, iso(now_utc())),
    )
    conn.commit()
    audit(conn, phone, "ATTEMPT", [args.outcome], args.note)
    print(f"Logged {args.outcome} for {phone}.")

    if args.outcome in DNC_OUTCOMES:
        add_internal_dnc(conn, phone, f"outcome: {args.outcome}")
        print("Added to internal DNC — this number will never come back up.")
    return 0


def cmd_audit(args):
    conn = init_db(args.db)
    if args.phone:
        phone = normalize_phone(args.phone)
        rows = conn.execute(
            "SELECT * FROM audit WHERE phone = ? ORDER BY at DESC LIMIT ?",
            (phone, args.limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit ORDER BY at DESC LIMIT ?", (args.limit,)
        ).fetchall()

    if not rows:
        print("No audit entries.")
        return 0
    for r in rows:
        line = f"  {r['at'][:19]}  {r['decision']:<8} {r['phone'] or '':<12} {r['reasons'] or ''}"
        print(line.rstrip())
    return 0


def cmd_stats(args):
    conn = init_db(args.db)
    at = now_utc()
    total = conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
    dnc = conn.execute("SELECT COUNT(*) c FROM internal_dnc").fetchone()["c"]
    attempts = conn.execute("SELECT COUNT(*) c FROM attempts").fetchone()["c"]

    allowed = 0
    block_reasons = {}
    for row in conn.execute("SELECT phone FROM leads"):
        d = evaluate(conn, row["phone"], at=at, log=False)
        if d.allowed:
            allowed += 1
        else:
            key = d.blocks[0].split("(")[0].strip()
            block_reasons[key] = block_reasons.get(key, 0) + 1

    print(f"  Leads              {total}")
    print(f"  Callable right now {allowed}")
    print(f"  Internal DNC       {dnc}")
    print(f"  Attempts logged    {attempts}")
    if block_reasons:
        print("\n  Top blockers:")
        for reason, count in sorted(block_reasons.items(), key=lambda kv: -kv[1])[:6]:
            print(f"    {count:>4}  {reason}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(
        description="Compliance gate for outbound dialing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--db", default=DEFAULT_DB, help="SQLite file (default: dialer.db)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the database").set_defaults(func=cmd_init)

    sp = sub.add_parser("import", help="import leads from CSV")
    sp.add_argument("csvfile")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("check", help="may I call this number right now?")
    sp.add_argument("phone")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("next", help="leads that are callable right now")
    sp.add_argument("--limit", type=int, default=25)
    sp.set_defaults(func=cmd_next)

    sp = sub.add_parser("scrub", help="DNC scrub records")
    scrub_sub = sp.add_subparsers(dest="scrub_command", required=True)
    due = scrub_sub.add_parser("due", help="leads needing a scrub")
    due.add_argument("--limit", type=int, default=50)
    due.set_defaults(func=cmd_scrub_due)
    setp = scrub_sub.add_parser("set", help="record a scrub result")
    setp.add_argument("phone")
    setp.add_argument("--list", required=True, help="federal | state | litigator | rnd")
    setp.add_argument("--result", required=True, choices=["clear", "listed"])
    setp.add_argument("--provider", default="manual")
    setp.set_defaults(func=cmd_scrub_set)

    sp = sub.add_parser("dnc", help="internal do-not-call list")
    dnc_sub = sp.add_subparsers(dest="dnc_command", required=True)
    addp = dnc_sub.add_parser("add")
    addp.add_argument("phone")
    addp.add_argument("--reason")
    addp.set_defaults(func=cmd_dnc_add)
    dnc_sub.add_parser("list").set_defaults(func=cmd_dnc_list)

    sp = sub.add_parser("attempt", help="log a call attempt")
    sp.add_argument("phone")
    sp.add_argument("--outcome", required=True, choices=VALID_OUTCOMES)
    sp.add_argument("--note")
    sp.set_defaults(func=cmd_attempt)

    sp = sub.add_parser("audit", help="read the audit log")
    sp.add_argument("--phone")
    sp.add_argument("--limit", type=int, default=40)
    sp.set_defaults(func=cmd_audit)

    sub.add_parser("stats", help="queue health").set_defaults(func=cmd_stats)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
