#!/usr/bin/env python3
"""
paddle_business.py — inventory, pricing, and real profit tracking for a paddle
resale business.

The point of this tool: a $130 sale is not $60 of profit. Marketplace fees and
shipping eat 10-14% before you see a dollar. Every command here works in net
terms, after fees.

Usage:
    python paddle_business.py buy 10 --model invikta --cost 70
    python paddle_business.py price 130 --channel ebay
    python paddle_business.py price --target-profit 45 --channel ebay
    python paddle_business.py sell 135 --channel ebay --ship-paid 12
    python paddle_business.py sell 150 --channel court
    python paddle_business.py inventory
    python paddle_business.py pnl
    python paddle_business.py pnl --month 2026-07
    python paddle_business.py channels
    python paddle_business.py breakeven --fixed 900
    python paddle_business.py delete 4

Data is stored in paddle_ledger.csv in the same directory as this script
(override with --file /path/to/file.csv).
"""

import argparse
import csv
import os
import sys
from datetime import date, datetime
from collections import defaultdict

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "paddle_ledger.csv")
FIELDNAMES = [
    "id", "date", "type", "model", "qty", "channel",
    "unit_cost", "sale_price", "shipping_collected", "shipping_paid",
    "fees", "net", "notes",
]

# What you pay per paddle. Override per purchase with --cost.
DEFAULT_UNIT_COST = 70.00

# Fee structure per sales channel, as of mid-2026. Percentages apply to the
# total the buyer pays you (item + shipping they cover), which is how eBay and
# Mercari actually bill. Edit these when a platform changes its rates.
CHANNELS = {
    "court": {
        "pct": 0.000, "flat": 0.00,
        "label": "In person at courts/clubs (cash, Venmo, Zelle)",
    },
    "facebook": {
        "pct": 0.000, "flat": 0.00,
        "label": "Facebook Marketplace, local pickup",
    },
    "facebook-ship": {
        "pct": 0.100, "flat": 0.00,
        "label": "Facebook Marketplace, shipped through FB checkout",
    },
    "offerup": {
        "pct": 0.129, "flat": 0.30,
        "label": "OfferUp, shipped (local pickup is free)",
    },
    "mercari": {
        "pct": 0.100, "flat": 2.00,
        "label": "Mercari, 10% + $2 direct-deposit payout",
    },
    "ebay": {
        "pct": 0.136, "flat": 0.40,
        "label": "eBay, 13.6% final value fee + $0.40 per order",
    },
    "shopify": {
        "pct": 0.029, "flat": 0.30,
        "label": "Own site, Shopify/Stripe processing (2.9% + $0.30)",
    },
}


def load_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        raw_rows = list(csv.DictReader(f))

    numeric = ["qty", "unit_cost", "sale_price", "shipping_collected",
               "shipping_paid", "fees", "net"]
    rows = []
    for line_num, row in enumerate(raw_rows, start=2):  # header is line 1
        try:
            row["id"] = int(row["id"])
            for key in numeric:
                row[key] = float(row.get(key) or 0)
        except (TypeError, ValueError, KeyError) as exc:
            print(f"Warning: skipping malformed row at line {line_num} in {path} ({exc})",
                  file=sys.stderr)
            continue
        rows.append(row)
    return rows


def save_rows(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def next_id(rows):
    if not rows:
        return 1
    return max(r["id"] for r in rows) + 1


def validate_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{value}', expected YYYY-MM-DD")
    return value


def validate_channel(value):
    key = value.strip().lower()
    if key not in CHANNELS:
        options = ", ".join(sorted(CHANNELS))
        raise argparse.ArgumentTypeError(f"Unknown channel '{value}'. Choose from: {options}")
    return key


def fees_for(channel, gross):
    """Platform fees on a sale where the buyer paid `gross` in total."""
    spec = CHANNELS[channel]
    if gross <= 0:
        return 0.0
    return round(gross * spec["pct"] + spec["flat"], 2)


def avg_cost(rows, model):
    """Weighted average purchase cost for a model, or the default if never bought."""
    units = spend = 0.0
    for r in rows:
        if r["type"] == "buy" and (not model or r["model"] == model):
            units += r["qty"]
            spend += r["qty"] * r["unit_cost"]
    if units <= 0:
        return DEFAULT_UNIT_COST
    return spend / units


def units_on_hand(rows):
    """Net units per model: bought minus sold."""
    counts = defaultdict(float)
    for r in rows:
        if r["type"] == "buy":
            counts[r["model"]] += r["qty"]
        elif r["type"] == "sell":
            counts[r["model"]] -= r["qty"]
    return counts


def filter_month(rows, month):
    if not month:
        return rows
    return [r for r in rows if r["date"].startswith(month)]


def cmd_buy(args):
    rows = load_rows(args.file)
    unit_cost = args.cost if args.cost is not None else DEFAULT_UNIT_COST
    entry = {
        "id": next_id(rows),
        "date": args.date or date.today().isoformat(),
        "type": "buy",
        "model": args.model.strip().lower(),
        "qty": args.qty,
        "channel": "",
        "unit_cost": round(unit_cost, 2),
        "sale_price": 0,
        "shipping_collected": 0,
        "shipping_paid": round(args.ship_paid, 2),
        "fees": 0,
        "net": round(-(args.qty * unit_cost + args.ship_paid), 2),
        "notes": args.notes or "",
    }
    rows.append(entry)
    save_rows(args.file, rows)
    outlay = -entry["net"]
    print(f"Bought #{entry['id']}: {entry['qty']:g} x {entry['model']} @ "
          f"${entry['unit_cost']:.2f} = ${outlay:.2f} out the door")
    on_hand = units_on_hand(rows)
    print(f"On hand: {on_hand[entry['model']]:g} x {entry['model']}")


def cmd_sell(args):
    rows = load_rows(args.file)
    model = args.model.strip().lower()
    unit_cost = args.cost if args.cost is not None else avg_cost(rows, model)

    gross = args.price * args.qty + args.ship_collected
    fees = fees_for(args.channel, gross)
    cogs = unit_cost * args.qty
    net = gross - fees - cogs - args.ship_paid

    entry = {
        "id": next_id(rows),
        "date": args.date or date.today().isoformat(),
        "type": "sell",
        "model": model,
        "qty": args.qty,
        "channel": args.channel,
        "unit_cost": round(unit_cost, 2),
        "sale_price": round(args.price, 2),
        "shipping_collected": round(args.ship_collected, 2),
        "shipping_paid": round(args.ship_paid, 2),
        "fees": round(fees, 2),
        "net": round(net, 2),
        "notes": args.notes or "",
    }
    rows.append(entry)
    save_rows(args.file, rows)

    margin = (net / gross * 100) if gross else 0
    print(f"Sold #{entry['id']}: {args.qty:g} x {model} @ ${args.price:.2f} "
          f"on {CHANNELS[args.channel]['label']}")
    print(f"  Buyer paid      ${gross:>8.2f}")
    print(f"  Platform fees  -${fees:>8.2f}")
    print(f"  Your cost      -${cogs:>8.2f}")
    if args.ship_paid:
        print(f"  Shipping paid  -${args.ship_paid:>8.2f}")
    print(f"  {'PROFIT':<14} ${net:>8.2f}  ({margin:.1f}% of gross)")

    remaining = units_on_hand(rows)[model]
    print(f"On hand: {remaining:g} x {model}")
    if remaining < 0:
        print("  Note: that is fewer than zero — log the purchase with `buy`.",
              file=sys.stderr)


def cmd_price(args):
    """Show the net on a given list price, or solve for the price that hits a target."""
    rows = load_rows(args.file)
    unit_cost = args.cost if args.cost is not None else avg_cost(rows, args.model.strip().lower())
    spec = CHANNELS[args.channel]

    if args.target_profit is not None:
        # net = P*(1-pct) - flat - cost - ship_paid  ->  solve for P
        price = (args.target_profit + unit_cost + args.ship_paid + spec["flat"]) / (1 - spec["pct"])
        print(f"To clear ${args.target_profit:.2f} per paddle on "
              f"{spec['label']}, list at ${price:.2f}")
        print(f"  (cost ${unit_cost:.2f}, shipping you cover ${args.ship_paid:.2f}, "
              f"fees {spec['pct'] * 100:.1f}% + ${spec['flat']:.2f})")
        args_price = price
    else:
        args_price = args.price

    gross = args_price + args.ship_collected
    fees = fees_for(args.channel, gross)
    net = gross - fees - unit_cost - args.ship_paid
    markup = (net / unit_cost * 100) if unit_cost else 0
    margin = (net / gross * 100) if gross else 0

    print()
    print(f"At ${args_price:.2f} on {spec['label']}:")
    print(f"  Buyer pays      ${gross:>8.2f}")
    print(f"  Platform fees  -${fees:>8.2f}")
    print(f"  Paddle cost    -${unit_cost:>8.2f}")
    print(f"  Shipping       -${args.ship_paid:>8.2f}")
    print(f"  {'PROFIT':<14} ${net:>8.2f}")
    print(f"  Margin {margin:.1f}% of gross, {markup:.0f}% return on the ${unit_cost:.0f} you put in")


def cmd_channels(args):
    """Compare every channel at one list price. Answers 'where should I sell this?'"""
    rows = load_rows(args.file)
    unit_cost = args.cost if args.cost is not None else avg_cost(rows, args.model.strip().lower())

    print(f"Selling at ${args.price:.2f}, paddle cost ${unit_cost:.2f}, "
          f"shipping you cover ${args.ship_paid:.2f}\n")
    print(f"  {'Channel':<16}{'Fees':>9}{'Profit':>10}{'Margin':>9}   Notes")

    results = []
    for key, spec in CHANNELS.items():
        gross = args.price + args.ship_collected
        fees = fees_for(key, gross)
        # Local channels have no shipping to pay.
        ship = 0.0 if spec["pct"] == 0 and spec["flat"] == 0 else args.ship_paid
        net = gross - fees - unit_cost - ship
        results.append((net, key, fees, gross, spec))

    for net, key, fees, gross, spec in sorted(results, reverse=True):
        margin = (net / gross * 100) if gross else 0
        print(f"  {key:<16}{fees:>9.2f}{net:>10.2f}{margin:>8.1f}%   {spec['label']}")

    best = max(results)
    worst = min(results)
    print(f"\n  Best: {best[1]} at ${best[0]:.2f}/paddle. "
          f"Worst: {worst[1]} at ${worst[0]:.2f}. "
          f"Spread of ${best[0] - worst[0]:.2f} on the same paddle.")


def cmd_inventory(args):
    rows = load_rows(args.file)
    on_hand = units_on_hand(rows)
    if not on_hand:
        print("No inventory logged yet. Start with: paddle_business.py buy 10 --cost 70")
        return

    print(f"  {'Model':<20}{'On hand':>9}{'Avg cost':>10}{'Capital tied up':>17}")
    total_units = total_capital = 0.0
    for model, units in sorted(on_hand.items()):
        cost = avg_cost(rows, model)
        capital = units * cost
        total_units += units
        total_capital += capital
        print(f"  {model:<20}{units:>9.0f}{cost:>10.2f}{capital:>17.2f}")
    print(f"\n  {'TOTAL':<20}{total_units:>9.0f}{'':>10}{total_capital:>17.2f}")


def cmd_pnl(args):
    rows = filter_month(load_rows(args.file), args.month)
    sales = [r for r in rows if r["type"] == "sell"]
    buys = [r for r in rows if r["type"] == "buy"]

    label = f" for {args.month}" if args.month else ""
    if not sales and not buys:
        print(f"Nothing logged{label}.")
        return

    revenue = sum(r["sale_price"] * r["qty"] + r["shipping_collected"] for r in sales)
    fees = sum(r["fees"] for r in sales)
    cogs = sum(r["unit_cost"] * r["qty"] for r in sales)
    shipping = sum(r["shipping_paid"] for r in sales)
    profit = sum(r["net"] for r in sales)
    units_sold = sum(r["qty"] for r in sales)
    spent = sum(r["qty"] * r["unit_cost"] + r["shipping_paid"] for r in buys)

    print(f"P&L{label}")
    print(f"  Revenue          ${revenue:>9.2f}")
    print(f"  Platform fees   -${fees:>9.2f}")
    print(f"  Cost of paddles -${cogs:>9.2f}")
    print(f"  Shipping        -${shipping:>9.2f}")
    print(f"  {'PROFIT':<16} ${profit:>9.2f}")
    if units_sold:
        print(f"\n  {units_sold:g} paddles sold, ${profit / units_sold:.2f} profit each")
        if revenue:
            print(f"  Fees ate {fees / revenue * 100:.1f}% of revenue")

    if sales:
        by_channel = defaultdict(lambda: {"units": 0.0, "profit": 0.0, "revenue": 0.0})
        for r in sales:
            bucket = by_channel[r["channel"]]
            bucket["units"] += r["qty"]
            bucket["profit"] += r["net"]
            bucket["revenue"] += r["sale_price"] * r["qty"] + r["shipping_collected"]

        print("\n  By channel:")
        print(f"    {'Channel':<16}{'Units':>7}{'Profit':>10}{'Per unit':>10}{'Margin':>9}")
        for channel, b in sorted(by_channel.items(), key=lambda kv: -kv[1]["profit"]):
            per_unit = b["profit"] / b["units"] if b["units"] else 0
            margin = b["profit"] / b["revenue"] * 100 if b["revenue"] else 0
            print(f"    {channel:<16}{b['units']:>7.0f}{b['profit']:>10.2f}"
                  f"{per_unit:>10.2f}{margin:>8.1f}%")

    print(f"\n  Cash out on inventory{label}: ${spent:.2f}")
    on_hand = sum(units_on_hand(load_rows(args.file)).values())
    if on_hand > 0:
        print(f"  Still holding {on_hand:g} paddles "
              f"(${on_hand * avg_cost(load_rows(args.file), None):.2f} of capital)")


def cmd_breakeven(args):
    rows = load_rows(args.file)
    sales = [r for r in rows if r["type"] == "sell"]

    if args.per_unit is not None:
        per_unit = args.per_unit
        source = "the figure you passed"
    elif sales:
        units = sum(r["qty"] for r in sales)
        per_unit = sum(r["net"] for r in sales) / units
        source = f"your actual average across {units:g} sales"
    else:
        cost = avg_cost(rows, None)
        gross = 130.00
        per_unit = gross - fees_for("ebay", gross) - cost - 12.00
        source = f"an estimate: ${gross:.0f} on eBay, ${cost:.0f} cost, $12 shipping"

    if per_unit <= 0:
        print(f"Profit per paddle is ${per_unit:.2f} — you cannot break even losing money "
              f"on each sale. Raise the price or cut the channel.")
        return

    units = args.fixed / per_unit
    print(f"Profit per paddle: ${per_unit:.2f} ({source})")
    print(f"Fixed costs to cover: ${args.fixed:.2f}")
    print(f"\n  Break even at {units:.1f} paddles sold "
          f"(round up: {int(units) + 1}).")
    print(f"  At 4 sales/week that is {units / 4:.1f} weeks.")
    print(f"  At 10 sales/week that is {units / 10:.1f} weeks.")


def cmd_log(args):
    rows = filter_month(load_rows(args.file), args.month)
    if args.type:
        rows = [r for r in rows if r["type"] == args.type]
    rows.sort(key=lambda r: r["date"])
    if not rows:
        print("Nothing logged.")
        return

    print(f"{'ID':<4}{'Date':<12}{'Type':<6}{'Model':<14}{'Channel':<15}"
          f"{'Qty':>4}{'Price':>9}{'Fees':>8}{'Net':>10}")
    for r in rows:
        print(f"{r['id']:<4}{r['date']:<12}{r['type']:<6}{r['model']:<14}"
              f"{r['channel']:<15}{r['qty']:>4.0f}{r['sale_price']:>9.2f}"
              f"{r['fees']:>8.2f}{r['net']:>10.2f}")
    print(f"\nNet across {len(rows)} entries: ${sum(r['net'] for r in rows):.2f}")


def cmd_delete(args):
    rows = load_rows(args.file)
    remaining = [r for r in rows if r["id"] != args.id]
    if len(remaining) == len(rows):
        print(f"No entry found with id {args.id}")
        sys.exit(1)
    save_rows(args.file, remaining)
    print(f"Deleted entry #{args.id}")


def build_parser():
    parser = argparse.ArgumentParser(
        description="Inventory, pricing, and after-fee profit for a paddle resale business.")
    parser.add_argument("--file", default=DEFAULT_FILE,
                        help="Path to the CSV ledger (default: paddle_ledger.csv next to this script)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_buy = sub.add_parser("buy", help="Log an inventory purchase")
    p_buy.add_argument("qty", type=float, help="How many paddles")
    p_buy.add_argument("--model", default="invikta", help="Paddle model (default: invikta)")
    p_buy.add_argument("--cost", type=float, help=f"Cost per paddle (default: {DEFAULT_UNIT_COST})")
    p_buy.add_argument("--ship-paid", type=float, default=0.0, help="Inbound shipping you paid")
    p_buy.add_argument("--date", type=validate_date, help="Date in YYYY-MM-DD (default: today)")
    p_buy.add_argument("--notes", default="", help="Supplier, order number, anything")
    p_buy.set_defaults(func=cmd_buy)

    p_sell = sub.add_parser("sell", help="Log a sale and see the real profit")
    p_sell.add_argument("price", type=float, help="What the buyer paid for the paddle")
    p_sell.add_argument("--channel", type=validate_channel, required=True,
                        help="Where you sold it (see the `channels` command)")
    p_sell.add_argument("--model", default="invikta", help="Paddle model (default: invikta)")
    p_sell.add_argument("--qty", type=float, default=1, help="Paddles in this sale (default: 1)")
    p_sell.add_argument("--cost", type=float,
                        help="Override cost per paddle (default: your average purchase cost)")
    p_sell.add_argument("--ship-collected", type=float, default=0.0,
                        help="Shipping the buyer paid on top")
    p_sell.add_argument("--ship-paid", type=float, default=0.0,
                        help="Shipping and packaging you paid")
    p_sell.add_argument("--date", type=validate_date, help="Date in YYYY-MM-DD (default: today)")
    p_sell.add_argument("--notes", default="", help="Buyer, listing, anything")
    p_sell.set_defaults(func=cmd_sell)

    p_price = sub.add_parser("price", help="Net profit at a list price, or the price for a target profit")
    p_price.add_argument("price", type=float, nargs="?", default=130.0,
                         help="List price to evaluate (default: 130)")
    p_price.add_argument("--channel", type=validate_channel, default="ebay",
                         help="Channel to price for (default: ebay)")
    p_price.add_argument("--target-profit", type=float,
                         help="Solve for the list price that clears this much per paddle")
    p_price.add_argument("--model", default="invikta", help="Paddle model (default: invikta)")
    p_price.add_argument("--cost", type=float, help="Override cost per paddle")
    p_price.add_argument("--ship-collected", type=float, default=0.0,
                         help="Shipping the buyer pays on top")
    p_price.add_argument("--ship-paid", type=float, default=0.0,
                         help="Shipping and packaging you pay")
    p_price.set_defaults(func=cmd_price)

    p_ch = sub.add_parser("channels", help="Compare profit across every channel at one price")
    p_ch.add_argument("price", type=float, nargs="?", default=130.0,
                      help="List price to compare (default: 130)")
    p_ch.add_argument("--model", default="invikta", help="Paddle model (default: invikta)")
    p_ch.add_argument("--cost", type=float, help="Override cost per paddle")
    p_ch.add_argument("--ship-collected", type=float, default=0.0,
                      help="Shipping the buyer pays on top")
    p_ch.add_argument("--ship-paid", type=float, default=12.0,
                      help="Shipping and packaging you pay on shipped orders (default: 12)")
    p_ch.set_defaults(func=cmd_channels)

    p_inv = sub.add_parser("inventory", help="Units on hand and capital tied up")
    p_inv.set_defaults(func=cmd_inventory)

    p_pnl = sub.add_parser("pnl", help="Profit and loss, broken down by channel")
    p_pnl.add_argument("--month", help="Filter by month, e.g. 2026-07")
    p_pnl.set_defaults(func=cmd_pnl)

    p_be = sub.add_parser("breakeven", help="How many paddles to cover your fixed costs")
    p_be.add_argument("--fixed", type=float, required=True,
                      help="Fixed costs to cover, e.g. your initial inventory buy")
    p_be.add_argument("--per-unit", type=float,
                      help="Profit per paddle (default: your actual average, or an estimate)")
    p_be.set_defaults(func=cmd_breakeven)

    p_log = sub.add_parser("log", help="List every ledger entry")
    p_log.add_argument("--month", help="Filter by month, e.g. 2026-07")
    p_log.add_argument("--type", choices=["buy", "sell"], help="Filter by entry type")
    p_log.set_defaults(func=cmd_log)

    p_del = sub.add_parser("delete", help="Delete a ledger entry by id")
    p_del.add_argument("id", type=int)
    p_del.set_defaults(func=cmd_delete)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
