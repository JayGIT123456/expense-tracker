#!/usr/bin/env python3
"""Turn a voice-recorded call transcript into a structured row in call_log.csv.

Paste or point it at a transcript, and it pulls out the company details Jay
logs after every touch: who, where, channel, pain, cost, objections, next
step, and a hot/warm/cold temperature.

Usage:
    python call_logger.py transcript.txt
    python call_logger.py            (then paste, and press Ctrl+Z then Enter)
"""

import argparse
import csv
import os
import re
import sys
from datetime import date

# ---------------------------------------------------------------------------
# SETTINGS — these are the lines to change when you want different behavior.
# ---------------------------------------------------------------------------

LOG_FILE = "call_log.csv"

# A call scores 1 point per signal found (pain, cost, decision maker, booked).
# These two numbers decide what the score gets labeled.
HOT_THRESHOLD = 3       # score >= this  -> HOT
WARM_THRESHOLD = 1      # score >= this  -> WARM, otherwise COLD

# Your own name and company. On a cold call YOU introduce yourself first, so
# without this the script logs you as the prospect. Anything listed here gets
# skipped when looking for the contact and company.
MY_NAMES = ["Jay"]
MY_COMPANY_WORDS = ["Mpower", "Sourcing"]


# ---------------------------------------------------------------------------
# WORD LISTS — what the script looks for in the transcript.
# ---------------------------------------------------------------------------

# Words that usually end a company name, e.g. "Avanti Way Realty".
COMPANY_SUFFIXES = [
    "LLC", "Inc", "Incorporated", "Corp", "Ltd", "Co",
    "Realty", "Group", "Team", "Sourcing", "Solutions", "Agency",
    "Partners", "Media", "Studios", "Properties", "Motors", "Spa",
    "Clinic", "Fitness", "Storage", "Marketing", "Consulting",
    "Services", "Associates", "Enterprises", "Holdings", "Systems",
]

# Phrases that introduce a company name, e.g. "I work at Bright Path Dental".
COMPANY_LEAD_INS = [
    r"work(?:s|ing)? (?:at|for)",
    r"company(?:'s| is)? called",
    r"my company(?:'s| is)?",
    r"we'?re called",
    r"over at",
    r"business (?:is )?called",
    r"the name of (?:the|my) (?:company|business) is",
]

# Phrases that introduce a person's name.
NAME_LEAD_INS = [
    r"is this",
    r"my name(?:'s| is)",
    r"this is",
    r"speaking with",
    r"spoke (?:with|to)",
]

# Which channel the touch came through.
CHANNEL_KEYWORDS = {
    "Cold call": ["cold call", "cold called", "out of the blue"],
    "Follow-up call": ["following up", "follow up call", "we spoke last", "circling back"],
    "Referral": ["referred", "referral", "gave me your name", "mutual friend"],
    "In person": ["met you at", "in person", "gave me your card", "at the event"],
    "Instagram DM": ["instagram", "dm", "direct message"],
    "Email": ["emailed", "sent you an email", "over email"],
    "Zoom": ["zoom", "video call", "hop on a call"],
}

# What industry they're in — used to pick the right case studies later.
INDUSTRY_KEYWORDS = {
    "Real estate": ["realtor", "real estate", "listing", "brokerage", "closing", "buyer", "seller"],
    "Wellness / med spa": ["med spa", "medspa", "salon", "gym", "fitness", "wellness", "clinic"],
    "Professional services": ["insurance", "law firm", "attorney", "accounting", "mortgage"],
    "E-commerce": ["shopify", "ecommerce", "e-commerce", "online store", "orders"],
    "Self storage": ["storage unit", "self storage"],
    "Marketing agency": ["marketing agency", "ad agency", "creative agency"],
}

# Signals of real pain — the problem they actually named.
PAIN_KEYWORDS = [
    "losing leads", "falling through", "slipping through", "slips through",
    "no time", "not enough time", "overwhelmed", "drowning", "swamped",
    "behind on", "backed up", "can't keep up", "cant keep up",
    "manually", "by hand", "forget to follow up", "forgetting to follow up",
    "bottleneck", "headache", "frustrating", "tedious", "waste of time",
    "double booked", "missed appointment", "no show", "no-show",
]

# Signals they can put a number on the pain.
COST_PATTERNS = [
    r"\$\s?[\d,]+(?:\.\d{2})?",                      # $2,500
    r"\d+\s*(?:hours?|hrs?)\s*(?:a|per)\s*(?:day|week|month)",
    r"\d+\s*(?:leads?|deals?|clients?|calls?)\s*(?:a|per)\s*(?:day|week|month)",
]

# Signals they can say yes themselves.
DECISION_MAKER_PHRASES = [
    "i'm the owner", "im the owner", "i own", "i'm the founder", "im the founder",
    "it's my call", "its my call", "i make that decision", "i decide",
    "i run the", "my business", "i'm the boss", "im the boss",
]

# Signals they cannot — someone else has to sign off.
NOT_DECISION_MAKER_PHRASES = [
    "check with my", "run it by", "talk to my partner", "my boss",
    "ask my husband", "ask my wife", "the owner would", "not my decision",
]

# The six objections from the Mpower playbook.
OBJECTION_PATTERNS = {
    # Careful: plain "how much" also matches YOUR discovery question
    # ("how much is that costing you?"), so match their version instead.
    "Too expensive": ["too expensive", "can't afford", "cant afford", "out of budget",
                      "how much does it cost", "how much is it", "what's the price",
                      "whats the price", "pricey", "costs too much"],
    "Already have someone": ["already have someone", "already have a va", "we have a team", "got someone doing"],
    "VA didn't work before": ["tried a va", "didn't work out", "didnt work out", "had a va before", "bad experience"],
    "Doesn't want a robot": ["sounds robotic", "don't want a robot", "dont want a robot", "sound like a bot", "not personal"],
    "Not right now": ["not right now", "maybe later", "in the future", "call me in", "bad timing", "after the holidays"],
    "Send info first": ["send me info", "send me some info", "send some info",
                        "send over some info", "send over details", "send info",
                        "email me something", "email me some", "shoot me some info"],
}

# Signals the appointment got booked.
BOOKED_PATTERNS = [
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)?",
    r"put you down for",
    r"see you (?:on|at)",
    r"calendar invite",
    r"i'?ll send (?:you )?(?:the|a) (?:invite|link)",
]


# ---------------------------------------------------------------------------
# EXTRACTION — one small function per field.
# ---------------------------------------------------------------------------

# Filler words that get swept up on the end of a company name, as in
# "over at Coastal Bay Realty and I noticed...".
TRAILING_FILLER = {
    "and", "but", "so", "i", "we", "he", "she", "they", "which",
    "where", "that", "the", "a", "in", "on", "for", "to", "is", "was",
}


def trim_filler(name):
    """Drop filler words from the end of a company name."""
    words = name.split()
    while words and words[-1].lower().strip(".,") in TRAILING_FILLER:
        words.pop()
    return " ".join(words)


def is_mine(candidate, my_words):
    """True if this name looks like our own rep or our own company."""
    lowered = candidate.lower()
    return any(word.lower() in lowered for word in my_words)


def find_company(text):
    """Return the prospect's company name, or empty string if none found."""
    candidates = []

    # First source: a name that ends in a known suffix, like "Coastal Bay Realty".
    suffixes = "|".join(COMPANY_SUFFIXES)
    pattern = r"\b((?:[A-Z][\w&'.-]*\s+){0,3}(?:" + suffixes + r"))\b"
    for match in re.finditer(pattern, text):
        candidates.append((match.start(), match.group(1)))

    # Second source: a phrase that introduces one, like "I work at Bright Path".
    for lead_in in COMPANY_LEAD_INS:
        for match in re.finditer(lead_in + r"\s+([A-Za-z][\w&'.-]*(?:\s+[A-Za-z][\w&'.-]*){0,3})", text, re.I):
            candidates.append((match.start(), match.group(1)))

    # Earliest mention wins, but never log ourselves as the prospect.
    for _, name in sorted(candidates):
        cleaned = trim_filler(name.strip().rstrip(".,"))
        if cleaned and not is_mine(cleaned, MY_COMPANY_WORDS):
            return cleaned

    return ""


def find_contact(text):
    """Return the prospect's name, or empty string if none found."""
    candidates = []
    for lead_in in NAME_LEAD_INS:
        for match in re.finditer(lead_in + r"\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", text):
            candidates.append((match.start(), match.group(1)))

    for _, name in sorted(candidates):
        cleaned = name.strip()
        if not is_mine(cleaned, MY_NAMES):
            return cleaned

    return ""


def find_phone(text):
    match = re.search(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text)
    return match.group(0).strip() if match else ""


def find_email(text):
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    # rstrip the period so "name@site.com." doesn't end up in the log.
    return match.group(0).strip().rstrip(".") if match else ""


def find_first_keyword_match(text, keyword_map):
    """Given {label: [keywords]}, return the first label whose keyword appears."""
    lowered = text.lower()
    for label, keywords in keyword_map.items():
        for keyword in keywords:
            if keyword in lowered:
                return label
    return ""


def find_pain_points(text):
    """Return every pain keyword that appears, as a list."""
    lowered = text.lower()
    return [kw for kw in PAIN_KEYWORDS if kw in lowered]


def find_cost_signals(text):
    """Return every dollar amount or per-week figure mentioned."""
    found = []
    for pattern in COST_PATTERNS:
        for hit in re.findall(pattern, text, re.I):
            found.append(hit.strip().rstrip(".,"))
    return found


def find_objections(text):
    """Return every playbook objection that came up, as a list."""
    lowered = text.lower()
    hits = []
    for label, keywords in OBJECTION_PATTERNS.items():
        if any(keyword in lowered for keyword in keywords):
            hits.append(label)
    return hits


def is_decision_maker(text):
    """Return 'Yes', 'No', or 'Unclear'."""
    lowered = text.lower()
    if any(phrase in lowered for phrase in NOT_DECISION_MAKER_PHRASES):
        return "No"
    if any(phrase in lowered for phrase in DECISION_MAKER_PHRASES):
        return "Yes"
    return "Unclear"


def find_next_step(text):
    """Return the booked time if there is one, else the best guess at a next step."""
    for pattern in BOOKED_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            return "Booked: " + match.group(0).strip()

    objections = find_objections(text)
    if "Send info first" in objections:
        return "Send info, then lock calendar"
    if "Not right now" in objections:
        return "Re-touch later — ask what needs to change"
    return "No next step captured"


def score_call(pain_points, cost_signals, decision_maker, next_step):
    """Add up the qualification signals. Returns (score, list of reasons)."""
    score = 0
    reasons = []

    if pain_points:
        score += 1
        reasons.append("named a specific pain")
    if cost_signals:
        score += 1
        reasons.append("attached a number to it")
    if decision_maker == "Yes":
        score += 1
        reasons.append("is the decision maker")
    if next_step.startswith("Booked"):
        score += 1
        reasons.append("appointment booked")

    return score, reasons


def temperature_for(score):
    """Turn a score into HOT / WARM / COLD using the thresholds up top."""
    if score >= HOT_THRESHOLD:
        return "HOT"
    if score >= WARM_THRESHOLD:
        return "WARM"
    return "COLD"


# ---------------------------------------------------------------------------
# PUTTING IT TOGETHER
# ---------------------------------------------------------------------------

def parse_transcript(text, source="pasted"):
    """Run every extractor over the transcript and return one finished record."""
    # Transcripts arrive wrapped across lines, which splits names like
    # "Coastal Bay\nRealty". Collapse all whitespace to single spaces first.
    text = re.sub(r"\s+", " ", text)

    pain_points = find_pain_points(text)
    cost_signals = find_cost_signals(text)
    decision_maker = is_decision_maker(text)
    next_step = find_next_step(text)
    score, reasons = score_call(pain_points, cost_signals, decision_maker, next_step)

    return {
        "date": date.today().isoformat(),
        "contact": find_contact(text),
        "company": find_company(text),
        "phone": find_phone(text),
        "email": find_email(text),
        "channel": find_first_keyword_match(text, CHANNEL_KEYWORDS),
        "industry": find_first_keyword_match(text, INDUSTRY_KEYWORDS),
        "pain_points": "; ".join(pain_points),
        "cost_signals": "; ".join(cost_signals),
        "objections": "; ".join(find_objections(text)),
        "decision_maker": decision_maker,
        "next_step": next_step,
        "score": score,
        "temperature": temperature_for(score),
        "why": "; ".join(reasons),
        "source": source,
    }


def append_to_log(record, log_path):
    """Add the record as a new row, writing the header if the file is new."""
    is_new_file = not os.path.exists(log_path)
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(record.keys()))
        if is_new_file:
            writer.writeheader()
        writer.writerow(record)


def print_record(record):
    """Show the parsed record in the terminal so you can eyeball it."""
    print()
    print("=" * 58)
    print("  CALL LOGGED")
    print("=" * 58)
    labels = {
        "contact": "Contact", "company": "Company", "phone": "Phone",
        "email": "Email", "channel": "Channel", "industry": "Industry",
        "pain_points": "Pain", "cost_signals": "Cost signals",
        "objections": "Objections", "decision_maker": "Decision maker",
        "next_step": "Next step",
    }
    for key, label in labels.items():
        print(f"  {label:<16} {record[key] or '—'}")
    print("-" * 58)
    print(f"  {'Temperature':<16} {record['temperature']}  (score {record['score']}/4)")
    print(f"  {'Because':<16} {record['why'] or 'no qualification signals found'}")
    print("=" * 58)
    print()


def main():
    parser = argparse.ArgumentParser(description="Log a call transcript to a CSV.")
    parser.add_argument("transcript", nargs="?", help="path to a transcript file (omit to paste instead)")
    parser.add_argument("--file", default=LOG_FILE, help=f"where to save the log (default: {LOG_FILE})")
    args = parser.parse_args()

    if args.transcript:
        with open(args.transcript, encoding="utf-8") as f:
            text = f.read()
        source = os.path.basename(args.transcript)
    else:
        print("Paste the transcript, then press Ctrl+Z and Enter (Windows) or Ctrl+D (Mac):")
        text = sys.stdin.read()
        source = "pasted"

    if not text.strip():
        print("Nothing to log — the transcript was empty.")
        return

    record = parse_transcript(text, source)
    append_to_log(record, args.file)
    print_record(record)
    print(f"Saved to {args.file}")


if __name__ == "__main__":
    main()
