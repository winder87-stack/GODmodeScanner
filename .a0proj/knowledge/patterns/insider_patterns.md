# Insider Pattern Library

This document catalogs known insider behavior patterns. Use these patterns
to identify similar behavior in new tokens.

---

## Pattern 001: The Classic Dev Insider

**Description:**
Token creator has multiple wallets ready to buy at launch.

**Identification:**
- Creator wallet funds 3-10 new wallets shortly before launch
- Funded wallets buy within 0-3 seconds of creation
- Funded wallets often have similar buy amounts
- All wallets sell within 1-24 hours

**Visual Pattern:**
Creator Wallet ──┬──> Wallet A ──> Buy at T+1s ──> Sell at T+2h
├──> Wallet B ──> Buy at T+1s ──> Sell at T+2h
├──> Wallet C ──> Buy at T+2s ──> Sell at T+2h
└──> Wallet D ──> Buy at T+2s ──> Sell at T+2h

**Detection Confidence:** 0.95 when funding pattern + early buy confirmed

---

## Pattern 002: Telegram Alpha Group

**Description:**
Coordinated group receives advance notice of launches.

**Identification:**
- 5-20 wallets buy within the same 10-second window
- Wallets have no common funding source
- Wallets have history of similar coordinated buys
- Buy amounts vary (not uniform like bot)

**Visual Pattern:**
                          ┌──> Wallet A (3 SOL)
                          ├──> Wallet B (1.5 SOL)
Token Launch ── Telegram Alert ├──> Wallet C (2 SOL)
├──> Wallet D (5 SOL)
└──> Wallet E (0.5 SOL)

**Detection Confidence:** 0.85 when 5+ wallets in same block

---

## Pattern 003: The Sniper Bot Network

**Description:**
Sophisticated bot network that detects and buys new tokens instantly.

**Identification:**
- Buys at T+0-1 seconds (faster than humanly possible)
- Uses Jito bundles for MEV protection
- Often has high transaction volume
- May use multiple wallets with shared funding

**Visual Pattern:**
New Token Created
↓
Bot Detects (50ms)
↓
Jito Bundle Submitted
↓
Buy Executed at T+200ms

**Detection Confidence:** 0.90 for sub-second buys

---

## Pattern 004: The Wash Trader

**Description:**
Single entity creating fake volume to attract buyers.

**Identification:**
- Circular transactions between related wallets
- Buy and sell amounts match closely
- No net position change
- Activity generates volume charts that attract retail

**Visual Pattern:**
Wallet A ──buy──> Token ──sell──> Wallet B
↑                                 │
└─────────── SOL Transfer ────────┘

**Detection Confidence:** 0.80 when circular flow detected

---

## Pattern 005: The Delayed Insider

**Description:**
Insider who waits slightly to avoid obvious detection.

**Identification:**
- Buys at T+5-30 seconds (just after obvious insider window)
- Has history of successful early entries
- Often sells at peak
- Win rate > 80%

**Visual Pattern:**
T+0s: Token created
T+1s: Obvious bots buy (flagged immediately)
T+10s: Delayed insider buys (tries to look organic)
T+30s: Retail starts buying
T+5min: Delayed insider sells at peak

**Detection Confidence:** 0.70 (harder to detect, needs historical analysis)

---

## Pattern 006: The Sybil Army

**Description:**
Large number of wallets controlled by single entity.

**Identification:**
- 20-100+ wallets with similar behavior signatures
- Common funding source (often through mixers)
- Identical or near-identical timing on actions
- May be used across multiple token launches

**Visual Pattern:**
Funding Source (Exchange/Mixer)
│
├──> Wallet 001 ──┐
├──> Wallet 002 ──│
├──> Wallet 003 ──├──> All buy Token X at T+2s
├──> ...          │
└──> Wallet 100 ──┘

**Detection Confidence:** 0.92 when cluster detected

---

## Anti-Patterns (False Positives to Avoid)

### Anti-Pattern A: The Unlucky Bot
- Buys early but loses money consistently
- No insider edge, just fast infrastructure
- Should not be flagged as insider

### Anti-Pattern B: The Whale Retail
- Large buy but late timing (T+5min+)
- Just a wealthy degen, not an insider
- Lower confidence score

### Anti-Pattern C: The Exchange Hot Wallet
- High volume, fast transactions
- But it's a known exchange wallet
- Exclude from analysis entirely
