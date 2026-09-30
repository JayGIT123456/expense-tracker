# Cowork exercises

Three small command-line tools. See [Dialer Compliance Gate](#dialer-compliance-gate),
[Call Logger](#call-logger) and [Expense Tracker CLI](#expense-tracker-cli).

---

# Call Logger

Paste a voice-recorded call transcript, get a structured row in `call_log.csv`.
It pulls out the fields logged after every sales touch: who, what company,
contact details, channel, industry, the pain they named, any number they put on
it, which objections came up, whether they can say yes, and the next step —
then scores the call hot / warm / cold.

## Usage

```bash
python call_logger.py sample_transcript.txt
```

Or paste a transcript directly (press Ctrl+Z then Enter on Windows when done):

```bash
python call_logger.py
```

## Example output

```
  Contact          Marcus
  Company          Coastal Bay Realty
  Phone            (305) 555-0182
  Email            marcus.delgado@coastalbayrealty.com
  Channel          Cold call
  Industry         Real estate
  Pain             falling through; manually
  Cost signals     $9,500; 6 leads a month
  Objections       VA didn't work before; Doesn't want a robot
  Decision maker   Yes
  Next step        Booked: Thursday at 2
------------------------------------------------------
  Temperature      HOT  (score 4/4)
  Because          named a specific pain; attached a number to it;
                   is the decision maker; appointment booked
```

Every run appends to `call_log.csv`, which opens directly in Excel or Google
Sheets.

## How the score works

A call earns one point for each qualification signal found:

1. Named a specific pain
2. Attached a number to it (dollars, hours, or leads lost)
3. Is the decision maker
4. Appointment booked

`HOT_THRESHOLD` and `WARM_THRESHOLD` at the top of the file decide what those
scores get labeled.

## Tuning it

The settings and word lists at the top of `call_logger.py` are meant to be
edited — that is where all the behavior lives:

- `HOT_THRESHOLD` / `WARM_THRESHOLD` — how strict the temperature labels are
- `MY_NAMES` / `MY_COMPANY_WORDS` — so the script logs the prospect, not you
- `PAIN_KEYWORDS`, `OBJECTION_PATTERNS`, `INDUSTRY_KEYWORDS` — what it listens for

No API key and no internet needed. Same transcript in, same row out, every time.

## Known limits

It matches keywords, so it finds what it has been told to look for and nothing
else. New phrasing means adding a keyword to a list. It also reads the whole
transcript as one block rather than tracking who is speaking, so a phrase is
credited to the call, not to a specific person.

---

# Expense Tracker CLI

A tiny command-line tool for logging expenses to a CSV file and summarizing
spending by category or month. Built as a Cowork exercise, directed by
Viktoriya and implemented by Claude.

## Usage

```bash
python expense_tracker.py add 12.50 food "Lunch with a friend"
python expense_tracker.py add 45 transport "Gas fill-up" --date 2026-07-01
python expense_tracker.py list
python expense_tracker.py list --month 2026-07
python expense_tracker.py summary
python expense_tracker.py summary --month 2026-07
python expense_tracker.py delete 3
```

By default, data is stored in `expenses.csv` next to the script. Pass
`--file /path/to/file.csv` to use a different location.

## Commands

- `add <amount> <category> [description] [--date YYYY-MM-DD]` — log a new expense (defaults to today's date)
- `list [--month YYYY-MM] [--category NAME]` — list expenses, optionally filtered
- `summary [--month YYYY-MM]` — spending breakdown by category with percentages
- `delete <id>` — remove an expense by its ID


---

# Dialer Compliance Gate

Layer 1 of the power dialer: the thing that decides whether a lead may be
called *right now*, and writes down why. It places no calls. The dialer asks
it, and dials only on an explicit ALLOW.

Every check fails closed. Missing consent, a stale DNC scrub, an unknown time
zone, a scrub that was never run — all produce the same answer: BLOCKED. A
lead becomes callable by having its paperwork in order, never by having no
paperwork at all.

## Usage

```bash
python dialer_compliance.py init
python dialer_compliance.py import sample_leads.csv
python dialer_compliance.py scrub set 3055550182 --list federal --result clear
python dialer_compliance.py check 3055550182
python dialer_compliance.py next --limit 25
python dialer_compliance.py attempt 3055550182 --outcome no_answer
python dialer_compliance.py audit --phone 3055550182
```

## Example output

```
BLOCK  9155550123
  [block]   consent on file is 'express'; prior express WRITTEN consent required
  [block]   written consent is missing capture IP
  [block]   listed on the federal list
  [block]   never scrubbed against the litigator list
  [block]   outside the 08:00-21:00 calling window in America/Chicago 23:07,
            America/Denver 22:07
  [warn]    consent is 268 days old
  [note]    Rosa Nieves — LifeQuoteForm
```

## What it checks

1. **Internal DNC** — permanent, and never removable through the CLI.
2. **Consent** — type, timestamp, source, and for written consent the capture
   IP, source URL and the exact disclosure language shown to the lead.
3. **DNC scrubs** — federal, state and litigator, each needing a `clear`
   result no older than 31 days (the federal safe harbor).
4. **Calling window** — 8am–9pm in the called party's local time.
5. **Frequency** — 8 attempts lifetime, 2 per day, 4 hours apart.

## Time zones are handled conservatively

A state can span two zones, so the window has to be open in **all** of them
before the call is allowed. Texas is the clearest case:

```
Central 07:30 / Mountain 06:30  BLOCK
Central 08:30 / Mountain 07:30  BLOCK   <- El Paso is still closed
Central 09:30 / Mountain 08:30  ALLOW
Central 20:30 / Mountain 19:30  ALLOW
Central 21:30 / Mountain 20:30  BLOCK
```

Dialing an hour late is a nuisance. Dialing an hour early is a violation.

Zone comes from the lead's address. The area code is only a cross-check,
because people keep their mobile number when they move — a disagreement
raises a warning, and a lead with no address at all is blocked outright
(`BLOCK_WHEN_TIMEZONE_UNKNOWN`).

## Wiring up a DNC vendor

`ScrubProvider` is the plug point for DNC.com, Blacklist Alliance or whoever
you use. The shipped default is `NullScrubProvider`, which refuses to answer —
so forgetting to configure a vendor stops the queue instead of silently
approving every call. Until one is wired up, record results by hand with
`scrub set`.

## The audit log is append-only

SQLite triggers reject every UPDATE and DELETE against the `audit` table:

```
UPDATE rejected: audit log is append-only
DELETE rejected: audit log is append-only
```

A compliance log you can quietly edit after the fact is worth nothing in front
of a regulator. This is also why the tool uses SQLite rather than a CSV like
the others here — the trail has to survive a crash mid-write.

## Tuning it

The `SETTINGS` block at the top of `dialer_compliance.py` holds every
compliance decision the tool makes: the calling window, scrub freshness, which
lists are required, whether written consent is mandatory, and the contact
frequency caps. They default to the strictest reading. Loosen them
deliberately.

`REQUIRE_WRITTEN_CONSENT` is the one to leave alone. Consent law is currently
split — the 11th Circuit vacated the FCC's one-to-one rule in January 2025,
and in February 2026 the 5th Circuit held the TCPA requires only prior express
consent, binding just TX/LA/MS. Building to the strictest standard costs
nothing and is the only posture that survives the split.

## Known limits

It records scrub *results*; it does not call a DNC vendor for you until you
wire one into `ScrubProvider`. State-level calling-hour rules that are
stricter than the federal 8am–9pm are not tracked per state — tighten
`CALL_WINDOW_START` / `CALL_WINDOW_END` if you write in those states. The
Reassigned Numbers Database is supported as a scrub list (`rnd`) but is not in
`REQUIRED_SCRUB_LISTS` by default.

**This is a guardrail, not legal advice.** TCPA damages run $500–$1,500 per
call with no cap. Have a telecom attorney review your consent language and
your lead vendors' consent trail before you dial anything.
