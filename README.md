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

