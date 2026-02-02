# GODMODESCANNER Core Knowledge

## Mission
Detect pump.fun insider wallets on Solana with zero tolerance.

## Detection Rules

### Rule 1: Early Buyer
Wallets buying within 3 seconds of token creation are flagged.
- 0-1 seconds: 0.99 confidence
- 1-2 seconds: 0.95 confidence
- 2-3 seconds: 0.90 confidence

### Rule 2: Coordinated Buying
3+ wallets buying in same block indicates coordination.
- Base confidence: 0.75
- Add 0.05 per additional wallet (cap at 0.98)

### Rule 3: Bundler
10+ transactions per minute indicates Jito bundle usage.
- Base confidence: 0.70
- Add 0.02 per additional tx (cap at 0.95)

### Rule 4: Large Buy
Purchases over 5 SOL indicate significant capital.
- Base confidence: 0.50
- Add 0.03 per SOL above 5
- Add 0.15 bonus if within first 60 seconds

### Rule 5: Quick Flip
Selling within 5 minutes of buying indicates planned exit.
- Base confidence: 0.60
- Add 0.08 per minute under 5
- Add 0.15 if profit > 50%

## Scoring System

Weights:
- EARLY_BUYER: 0.35
- COORDINATED_BUYING: 0.25
- BUNDLER: 0.20
- LARGE_BUY: 0.12
- QUICK_FLIP: 0.08

Calculation:
1. Sum (confidence × weight) for each signal
2. Divide by sum of weights for signals present
3. Apply modifiers: x1.15 for 3+ signals, x1.10 for 4+, x1.10 for new wallet, x1.20 for Sybil cluster
4. Cap at 1.0

## Alert Thresholds

- CRITICAL (>=0.90): Immediate alert, add to database
- HIGH (0.80-0.89): Alert, watchlist
- MEDIUM (0.60-0.79): Log for review
- LOW (0.40-0.59): Log only

## Insider Patterns

Pattern 1 - Dev Insider: Creator funds 3-10 new wallets before launch, all buy within 0-3 seconds. Confidence: 0.95

Pattern 2 - Telegram Alpha: 5-20 wallets buy within 10 seconds, history of coordinated buys. Confidence: 0.85

Pattern 3 - Sniper Bot: Buys at T+0-1 seconds, uses Jito bundles. Confidence: 0.90

Pattern 4 - Wash Trader: Circular transactions between wallets, amounts match. Confidence: 0.80

Pattern 5 - Delayed Insider: Buys at T+5-30 seconds, >70% win rate. Confidence: 0.70

Pattern 6 - Sybil Army: 20-100+ wallets with common funding, identical timing. Confidence: 0.92

## Key Constants

- pump.fun Program: 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P
- Early buy window: 3 seconds
- Coordination threshold: 3 wallets
- Bundler threshold: 10 tx/min
- Large buy: 5 SOL
- Quick flip: 5 minutes
