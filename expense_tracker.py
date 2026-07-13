#!/usr/bin/env python3
"""
expense_tracker.py — a tiny CLI for logging expenses to a CSV file and
summarizing spending by category or by month.

Usage:
    python expense_tracker.py add 12.50 food "Lunch with a friend"
    python expense_tracker.py add 45 transport "Gas fill-up" --date 2026-07-01
    python expense_tracker.py list
    python expense_tracker.py list --month 2026-07
    python expense_tracker.py summary
    python expense_tracker.py summary --month 2026-07
    python expense_tracker.py delete 3

Data is stored in expenses.csv in the same directory as this script
(override with --file /path/to/file.csv).
"""

import argparse
import csv
import os
import sys
from datetime import date, datetime
from collections import defaultdict

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "expenses.csv")
FIELDNAMES = ["id", "date", "amount", "category", "description"]


def load_expenses(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw_rows = list(reader)

    expenses = []
    for line_num, row in enumerate(raw_rows, start=2):  # header is line 1
        try:
            row["id"] = int(row["id"])
            row["amount"] = float(row["amount"])
        except (TypeError, ValueError, KeyError) as exc:
            print(f"Warning: skipping malformed row at line {line_num} in {path} ({exc})", file=sys.stderr)
            continue
        expenses.append(row)
    return expenses


def save_expenses(path, expenses):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in expenses:
            writer.writerow(row)


def next_id(expenses):
    if not expenses:
        return 1
    return max(e["id"] for e in expenses) + 1


def validate_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}', expected YYYY-MM-DD")
    return value


def cmd_add(args):
    expenses = load_expenses(args.file)
    entry = {
        "id": next_id(expenses),
        "date": args.date or date.today().isoformat(),
        "amount": round(args.amount, 2),
        "category": args.category.strip().lower(),
        "description": args.description or "",
    }
    expenses.append(entry)
    save_expenses(args.file, expenses)
    print(f"Added #{entry['id']}: ${entry['amount']:.2f} on {entry['date']} [{entry['category']}] {entry['description']}")


def cmd_list(args):
    expenses = load_expenses(args.file)
    if args.month:
        expenses = [e for e in expenses if e["date"].startswith(args.month)]
    if args.category:
        expenses = [e for e in expenses if e["category"] == args.category.lower()]
    expenses.sort(key=lambda e: e["date"])
    if not expenses:
        print("No expenses found.")
        return
    print(f"{'ID':<4}{'Date':<12}{'Amount':>10}  {'Category':<14}Description")
    for e in expenses:
        print(f"{e['id']:<4}{e['date']:<12}{e['amount']:>10.2f}  {e['category']:<14}{e['description']}")
    total = sum(e["amount"] for e in expenses)
    print(f"\nTotal: ${total:.2f} ({len(expenses)} entries)")


def cmd_summary(args):
    expenses = load_expenses(args.file)
    if args.month:
        expenses = [e for e in expenses if e["date"].startswith(args.month)]
    if not expenses:
        print("No expenses found.")
        return

    by_category = defaultdict(float)
    for e in expenses:
        by_category[e["category"]] += e["amount"]

    grand_total = sum(by_category.values())
    label = f" for {args.month}" if args.month else ""
    print(f"Spending summary{label}:")
    for category, total in sorted(by_category.items(), key=lambda kv: -kv[1]):
        pct = (total / grand_total * 100) if grand_total else 0
        print(f"  {category:<14}${total:>8.2f}  ({pct:4.1f}%)")
    print(f"\n  {'TOTAL':<14}${grand_total:>8.2f}")


def cmd_delete(args):
    expenses = load_expenses(args.file)
    remaining = [e for e in expenses if e["id"] != args.id]
    if len(remaining) == len(expenses):
        print(f"No expense found with id {args.id}")
        sys.exit(1)
    save_expenses(args.file, remaining)
    print(f"Deleted expense #{args.id}")


def build_parser():
    parser = argparse.ArgumentParser(description="Track expenses in a CSV file.")
    parser.add_argument("--file", default=DEFAULT_FILE, help="Path to the CSV file (default: expenses.csv next to this script)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add an expense")
    p_add.add_argument("amount", type=float, help="Amount spent")
    p_add.add_argument("category", help="Category, e.g. food, transport, rent")
    p_add.add_argument("description", nargs="?", default="", help="Optional description")
    p_add.add_argument("--date", type=validate_date, help="Date in YYYY-MM-DD (default: today)")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="List expenses")
    p_list.add_argument("--month", help="Filter by month, e.g. 2026-07")
    p_list.add_argument("--category", help="Filter by category")
    p_list.set_defaults(func=cmd_list)

    p_summary = sub.add_parser("summary", help="Summarize spending by category")
    p_summary.add_argument("--month", help="Filter by month, e.g. 2026-07")
    p_summary.set_defaults(func=cmd_summary)

    p_delete = sub.add_parser("delete", help="Delete an expense by id")
    p_delete.add_argument("id", type=int)
    p_delete.set_defaults(func=cmd_delete)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()


