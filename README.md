# Cowork exercises

Two small command-line tools. See [Call Logger](#call-logger) and
[Expense Tracker CLI](#expense-tracker-cli).

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

