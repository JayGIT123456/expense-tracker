# Cowork exercises

Three small command-line tools. See [Call Logger](#call-logger),
[Expense Tracker CLI](#expense-tracker-cli), and
[Paddle Business CLI](#paddle-business-cli).

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

# Paddle Business CLI

Inventory, pricing, and after-fee profit tracking for a pickleball paddle
resale business — built around Selkirk Invikta paddles bought at $70.

The premise: a $130 sale is not $60 of profit. Marketplace fees and shipping
take 10–14% before you see a dollar, and the same paddle nets $60 at a court
and $29.92 on eBay. Every command works in net terms, after fees.

The strategy that goes with it is in
[PADDLE_BUSINESS_PLAN.md](PADDLE_BUSINESS_PLAN.md) — unit economics, pricing
tiers, channel ranking, a 90-day plan, and the risks worth knowing about.

## Usage

```bash
python paddle_business.py channels 130 --cost 70      # where should I sell this?
python paddle_business.py price --target-profit 45 --channel ebay --ship-paid 12
python paddle_business.py buy 10 --cost 70
python paddle_business.py sell 149 --channel court
python paddle_business.py sell 135 --channel ebay --ship-paid 12
python paddle_business.py inventory
python paddle_business.py pnl --month 2026-07
python paddle_business.py breakeven --fixed 1130
```

## Example output

```
$ python paddle_business.py channels 130 --cost 70

Selling at $130.00, paddle cost $70.00, shipping you cover $12.00

  Channel              Fees    Profit   Margin   Notes
  facebook             0.00     60.00    46.2%   Facebook Marketplace, local pickup
  court                0.00     60.00    46.2%   In person at courts/clubs
  shopify              4.07     43.93    33.8%   Own site, Shopify/Stripe (2.9% + $0.30)
  facebook-ship       13.00     35.00    26.9%   Facebook Marketplace, shipped
  mercari             15.00     33.00    25.4%   Mercari, 10% + $2 payout
  offerup             17.07     30.93    23.8%   OfferUp, shipped
  ebay                18.08     29.92    23.0%   eBay, 13.6% FVF + $0.40 per order

  Best: facebook at $60.00/paddle. Worst: ebay at $29.92.
  Spread of $30.08 on the same paddle.
```

## Commands

- `buy <qty> [--model M] [--cost C] [--ship-paid S] [--date D] [--notes N]` — log an inventory purchase
- `sell <price> --channel CH [--model M] [--qty N] [--cost C] [--ship-collected S] [--ship-paid S]` — log a sale, with the profit broken out
- `price [<price>] [--channel CH] [--target-profit P]` — net profit at a price, or the price that hits a target profit
- `channels [<price>]` — compare profit across every channel at one price
- `inventory` — units on hand and capital tied up, per model
- `pnl [--month YYYY-MM]` — revenue, fees, COGS, profit, and a per-channel breakdown
- `breakeven --fixed F [--per-unit P]` — paddles needed to cover fixed costs
- `log [--month YYYY-MM] [--type buy|sell]` — every ledger entry
- `delete <id>` — remove a ledger entry

Data lives in `paddle_ledger.csv` next to the script (override with `--file`).
Cost defaults to $70/paddle; sales use your weighted-average purchase cost
unless you pass `--cost`.

## Channels and fee rates

`court` and `facebook` (local pickup) are fee-free. `facebook-ship` is 10%,
`mercari` 10% + $2, `offerup` 12.9% + $0.30, `ebay` 13.6% + $0.40, `shopify`
2.9% + $0.30. Percentages apply to the full amount the buyer pays including
shipping, which is how eBay and Mercari actually bill.

Rates are current as of July 2026 and live in the `CHANNELS` table at the top
of the script — edit them when a platform changes its cut.

No API key and no internet needed.

