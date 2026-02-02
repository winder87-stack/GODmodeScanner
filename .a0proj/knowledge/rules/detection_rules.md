# GODMODESCANNER Detection Rules

This document defines the core detection algorithms used to identify insider activity.
These rules are the foundation of the detection system.

## Rule 1: Early Buyer Detection

**Purpose:** Identify wallets that buy within seconds of token launch.

**Logic:**
IF wallet buys within 3 seconds of token creation THEN
IF buy occurs within 1 second:
confidence = 0.99 (almost certainly insider or bot)
ELSE IF buy occurs within 2 seconds:
confidence = 0.95 (very likely insider)
ELSE IF buy occurs within 3 seconds:
confidence = 0.90 (likely insider)
FLAG as EARLY_BUYER

**Evidence Required:**
- Token creation transaction signature and timestamp
- Buy transaction signature and timestamp
- Time difference calculation

**Why This Works:**
No human can react to a new token in under 3 seconds. This requires either:
- Advance knowledge of the launch (insider)
- Automated detection and buying (sophisticated bot with insider info)
- Being the creator themselves

---

## Rule 2: Coordinated Buying Detection

**Purpose:** Identify groups of wallets acting together.

**Logic:**
FOR each block containing token transactions:
unique_buyers = wallets that bought in this block
IF unique_buyers.count >= 3 THEN
    base_confidence = 0.75
    bonus = (unique_buyers.count - 3) * 0.05
    confidence = min(0.98, base_confidence + bonus)
    
    FLAG all wallets as COORDINATED_BUYING

**Evidence Required:**
- Block/slot number
- List of all buying wallets in that block
- Transaction signatures for each

**Why This Works:**
Legitimate organic buying is random - it's astronomically unlikely for 3+
unrelated people to buy in the exact same block by chance. When this happens,
it indicates:
- Shared signal (Telegram/Discord group coordination)
- Same entity with multiple wallets
- Bot network acting in unison

---

## Rule 3: Bundler Detection

**Purpose:** Identify wallets using transaction bundles (MEV protection).

**Logic:**
FOR each wallet:
FOR each 60-second window:
tx_count = transactions in this window
    IF tx_count >= 10 THEN
        base_confidence = 0.70
        bonus = (tx_count - 10) * 0.02
        confidence = min(0.95, base_confidence + bonus)
        
        FLAG as BUNDLER

**Evidence Required:**
- List of transaction signatures
- Timestamps for each
- Time window analysis

**Why This Works:**
Normal users don't send 10+ transactions per minute. This pattern indicates:
- Jito bundle usage (MEV protection = sophisticated actor)
- High-frequency trading bot
- Coordinated multi-wallet operation

---

## Rule 4: Large Buy Detection

**Purpose:** Flag wallets making significant purchases early in token life.

**Logic:**
IF wallet buys > 5 SOL worth of tokens THEN
IF buy occurs within first 60 seconds of token launch:
base_confidence = 0.60
size_bonus = min(0.25, (sol_amount - 5) * 0.03)
timing_bonus = 0.15
confidence = base_confidence + size_bonus + timing_bonus
ELSE:
base_confidence = 0.50
size_bonus = min(0.30, (sol_amount - 5) * 0.03)
confidence = base_confidence + size_bonus
FLAG as LARGE_BUY

**Evidence Required:**
- SOL amount of purchase
- Time since token launch
- Transaction signature

**Why This Works:**
Large early purchases indicate:
- Confidence in the token's success (insider knowledge)
- Intent to manipulate price
- Accumulation phase before promotion

---

## Rule 5: Quick Flip Detection

**Purpose:** Identify wallets that sell shortly after buying.

**Logic:**
FOR each wallet with both buy and sell transactions:
hold_time = sell_timestamp - buy_timestamp
IF hold_time <= 5 minutes THEN
    base_confidence = 0.60
    time_bonus = max(0, (5 - hold_time_minutes) * 0.08)
    
    IF profit_percentage > 50%:
        profit_bonus = 0.15
    ELSE:
        profit_bonus = 0
    
    confidence = base_confidence + time_bonus + profit_bonus
    
    FLAG as QUICK_FLIP

**Evidence Required:**
- Buy transaction with timestamp
- Sell transaction with timestamp
- Profit/loss calculation if possible

**Why This Works:**
Quick flips indicate:
- Pre-planned exit strategy
- Knowledge that price would spike temporarily
- Pump and dump participation

---

## Rule Priority Order

When multiple rules trigger, prioritize in this order:

1. **EARLY_BUYER** (highest priority - strongest signal)
2. **COORDINATED_BUYING** (requires multiple actors)
3. **BUNDLER** (sophisticated tooling)
4. **LARGE_BUY** (significant capital)
5. **QUICK_FLIP** (behavior pattern)

---

## Edge Cases and Exceptions

### Legitimate Early Buyers
Some legitimate users use sniper bots without insider knowledge. Consider:
- Wallet has long history of similar behavior
- Wallet loses money frequently (no insider edge)
- Wallet only catches 1 in 100 tokens early

### Market Makers
Some wallets are legitimate market makers. They may:
- Have large transaction volumes
- Quick buy/sell cycles
- But should have balanced activity over time

### Exchange Wallets
Known exchange wallets should be excluded from analysis.
See: wallets/exchange_wallets.json
