# Selkirk Invikta Resale — Business Plan

**Cost basis: $70/paddle.** Everything below follows from that number and from
what the Invikta actually sells for right now, not from MSRP.

Run the math yourself with `paddle_business.py` (see [the tool](#the-tool)).

---

## 1. Read this before you price anything

MSRP on Invikta-shape paddles looks great: the VANGUARD Pro Invikta lists at
**$229.99**, AMPED Pro Air at **$200**, LUXX Control Air at **$280**. At $70
cost those look like 3x markups.

They are not, because **almost nobody pays MSRP for a Selkirk.** As of now:

| Paddle | MSRP | Actually selling for |
|---|---|---|
| AMPED Pro Air Invikta | $200 | **$100** (Selkirk's own site) |
| LUXX Control Air Invikta | $280 | **$200** (Selkirk's own site) |
| LABS 007 Invikta | $333 | **$129.99** (closeout) |
| VANGUARD Pro Invikta | $229.99 | **$120–150** across retailers |

Selkirk discounts hard and often, and so do JustPaddles, Pickleball Central,
and Dick's. **Your competition on price is Selkirk itself.**

The consequence: your realistic online ceiling is roughly **$110–150**, not
$230. On an older or closeout Invikta line that Selkirk is dumping at $100,
your $70 cost leaves you almost nothing online after fees. **Which specific
Invikta line you're buying at $70 decides whether the online channel works at
all.** Check what Selkirk.com and JustPaddles charge for *your exact model*
today, before you list a single unit.

Where your $70 does win, reliably: **in person, where there is no price
comparison tab and no platform fee.**

---

## 2. Unit economics by channel

At a $130 sale price, $70 cost, $12 shipping and packaging where it applies:

| Channel | Fees | Your profit | Margin | ROI on $70 |
|---|---|---|---|---|
| **Courts / clubs, cash** | $0 | **$60.00** | 46% | 86% |
| **Facebook Marketplace, local pickup** | $0 | **$60.00** | 46% | 86% |
| Own site (Shopify/Stripe 2.9%+$0.30) | $4.07 | $43.93 | 34% | 63% |
| Facebook Marketplace, shipped | $13.00 | $35.00 | 27% | 50% |
| Mercari (10% + $2 payout) | $15.00 | $33.00 | 25% | 47% |
| OfferUp, shipped (12.9%) | $17.07 | $30.93 | 24% | 44% |
| **eBay (13.6% + $0.40)** | $18.08 | **$29.92** | 23% | 43% |

**The same paddle nets you $60 at a court and $29.92 on eBay.** Platform fees
plus shipping cost you half your profit. That spread is the single most
important fact in this business.

Note eBay's 13.6% applies to the *total* — item, shipping you collect, and
sales tax. Charging shipping separately does not dodge it.

---

## 3. Pricing

Three tiers. Anchor high, discount deliberately.

- **$149 — in person, single paddle.** At courts and clubs, against the $230
  MSRP sticker people have seen, $149 reads as a deal. Nets you **$79**.
- **$129 — online listings and local pickup.** Sits under the retailers'
  typical sale price. Nets $60 local, $30 on eBay.
- **$240 for two ($120 each)** — the highest-leverage move you have. Pickleball
  is doubles. Partners buy together and want matched paddles. Two paddles at
  one meetup doubles your profit per trip with no extra fee drag: **$100 net.**

Never advertise below what your supplier's MAP policy allows (see §7). Also
avoid a race to the bottom on eBay: if you cannot clear $30/unit there, the
listing is not worth the fee and the return risk.

Want a specific target? Ask the tool:

```
python paddle_business.py price --target-profit 45 --channel ebay --ship-paid 12
# -> list at $147.45
```

---

## 4. Where to sell — ranked

**1. Courts, clubs, and leagues (start here).** Zero fees, zero shipping, zero
price-comparison, and instant feedback on what sells. Bring 2–3 paddles and a
demo unit people can hit with. A paddle someone has played three points with
sells itself. Talk to club pros and league organizers about a small commission
for referrals — a league of 60 players is a repeatable pipeline.

**2. Facebook Marketplace + local pickup groups.** Effectively free, and every
metro has active pickleball groups. Post in the groups, not just Marketplace.
This is where your court sales get discovered when you're not at the court.

**3. Tournaments and open-play events.** Highest concentration of buyers per
hour anywhere. A folding table and a banner is the whole setup. Check whether
vendor space costs anything — often it's cheap or free at local events.

**4. eBay — inventory clearance, not primary.** Only 23% margin, and it exposes
you to returns and to buyers comparing against Selkirk's sale price. Its real
value is national reach for slow-moving stock. Use it to liquidate, not to
build.

**5. Own site + Instagram/TikTok — later.** Best fee rate at 2.9%, but a site
with no traffic sells nothing, and paid acquisition will cost you more per sale
than eBay's 13.6%. Build this only once organic demand exists. Free version
today: an Instagram account documenting local play, DMs for orders, Venmo for
payment. Zero fees, and the content is the marketing.

**Skip Mercari and OfferUp** unless you have dead stock — their fees are eBay-
adjacent with a fraction of the buyers.

---

## 5. First 90 days

**Days 1–14 — validate before you scale.**
Buy 5 paddles, not 50. Verify your $70 source: authenticity, warranty status,
whether it's authorized or grey market (§7). Confirm what your exact model
retails for today. Sell all 5 in person. `paddle_business.py pnl` will tell you
your real per-unit profit rather than your hoped-for one.

**Days 15–45 — find the repeatable channel.**
Reorder 10–20 once the first 5 sell. Set up Facebook Marketplace and one local
pickleball group presence. Become a regular at two or three courts. Log every
sale by channel; after ~15 sales `pnl --month` shows which channel actually
pays, and you double down there.

**Days 46–90 — build the flow.**
Reorder to hold 20–30 units. Approach one club or league about a standing
arrangement. Add bundle pricing. Consider eBay for whatever hasn't moved in 30
days. Only now consider a website.

**Do not buy 50 paddles up front.** That is $3,500 in capital bet on an
untested assumption about what your specific model sells for.

---

## 6. Startup capital

| Item | Lean | Comfortable |
|---|---|---|
| Initial inventory | 5 @ $70 = **$350** | 10 @ $70 = **$700** |
| Shipping supplies | $0 (local only) | $60 |
| Business registration / DBA | $50 | $150 |
| Demo paddle (yours, sacrificial) | $70 | $70 |
| Table, banner, cards | $0 | $150 |
| **Total** | **~$470** | **~$1,130** |

Break-even on the comfortable start, at $60/unit local profit:

```
python paddle_business.py breakeven --fixed 1130 --per-unit 60
# -> 19 paddles. About 5 weeks at 4 sales/week.
```

Sell online-only at $30/unit and that same break-even takes **38 paddles.**
Same business, double the work, because of fees.

---

## 7. Risks, and the two that actually matter

**Where is $70 coming from?** This is the question the whole business rests on.

- *Authorized wholesale from Selkirk* — good. But expect a **MAP (Minimum
  Advertised Price) policy** capping how low you may *advertise*. MAP restricts
  advertised price, not the price you sell at, and violating it typically costs
  you your dealer status and your ability to buy at all. Get the policy in
  writing and price above it.
- *Liquidation, closeout, or grey market* — workable but riskier. Verify
  authenticity before you scale. Counterfeit Selkirks exist, and selling one
  gets you an eBay VeRO takedown, account suspension, and chargebacks. Ask
  about warranty: Selkirk's warranty generally runs through authorized dealers,
  and "no warranty" is a real objection at the $130 price point you need.

**Selkirk discounts the model you're holding.** They cut AMPED Pro Air Invikta
from $200 to $100. If that happens to your model, your $70 inventory is
suddenly nearly worthless online. Mitigations: hold small quantities, turn
inventory fast, favor in-person channels where the comparison doesn't happen,
and diversify models rather than going deep on one.

**Smaller ones:** paddle tech cycles roughly annually, so last year's line
loses value; returns and shipping damage on marketplaces; sales tax collection
and a Schedule C at tax time — set aside ~25–30% of profit; competing with
established local pro shops that have club relationships you don't.

---

## 8. Watch these four numbers

1. **Net profit per paddle, by channel** — `pnl` shows it. If a channel is
   under $30, drop it.
2. **Days to sell a unit** — capital sitting in a closet earns nothing. Under
   30 days is healthy.
3. **Capital tied up** — `inventory` shows it. Don't let it exceed what you can
   afford to lose.
4. **Sales per court visit** — your real hourly rate. Two paddles a visit at
   $60 each beats a week of eBay listings.

---

## The tool

`paddle_business.py` does the arithmetic in this plan, with your actual
numbers instead of these estimates.

```bash
python paddle_business.py channels 130 --cost 70      # where to sell, ranked
python paddle_business.py price --target-profit 45 --channel ebay --ship-paid 12
python paddle_business.py buy 10 --cost 70
python paddle_business.py sell 149 --channel court
python paddle_business.py sell 135 --channel ebay --ship-paid 12
python paddle_business.py inventory
python paddle_business.py pnl
python paddle_business.py breakeven --fixed 1130
```

Fee rates live in the `CHANNELS` table at the top of the script — edit them
when a platform changes its cut.

---

## Sources

Pricing and fee figures as of July 2026:

- [Selkirk Invikta paddle collection](https://www.selkirk.com/collections/invikta-paddles)
- [Selkirk VANGUARD Pro Invikta](https://www.selkirk.com/products/vanguard-pro-invikta)
- [JustPaddles Selkirk sale pricing](https://www.justpaddles.com/products/deals~made%20in%20the%20usa,sale/vendor~selkirk/)
- [Pickleball Central — VANGUARD Pro Invikta](https://pickleballcentral.com/selkirk-vanguard-pro-invikta-pickleball-paddle/)
- [eBay seller fees 2026 breakdown](https://www.underpriced.app/blog/ebay-fees-complete-guide-2026)
- [Mercari vs eBay fees 2026](https://closo.co/blogs/shipping-policies/mercari-commission-fees-explained-2025-guide)
- [What a MAP policy is and how it's enforced](https://growbydata.com/minimum-advertised-price/)
