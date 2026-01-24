# Insider Scoring System

This document defines how individual signals are combined into a final
insider score for each wallet.

## Score Range

All scores are normalized to a 0.0 - 1.0 range where:
- 0.0 = Definitely not an insider
- 0.5 = Uncertain / needs more data
- 0.7 = Likely insider (alert threshold)
- 0.9 = Almost certainly insider
- 1.0 = Confirmed insider (manual verification)

## Signal Weights

Each detection signal contributes to the final score with these weights:

| Signal Type | Weight | Rationale |
|-------------|--------|-----------|
| EARLY_BUYER | 0.35 | Strongest signal - requires insider knowledge or sophisticated tooling |
| COORDINATED_BUYING | 0.25 | Multiple actors = organized manipulation |
| BUNDLER | 0.20 | Sophisticated tooling indicates serious actor |
| LARGE_BUY | 0.12 | Capital commitment shows confidence |
| QUICK_FLIP | 0.08 | Behavior pattern, could be coincidental |

**Total: 1.00**

## Score Calculation Formula
For each wallet:
1. Collect all signals
2. Group by signal type
3. Take highest confidence for each type
4. Apply weights:
   weighted_sum = Σ (signal_confidence × signal_weight)
   total_weight = Σ (signal_weight for signals present)
   
   base_score = weighted_sum / total_weight

5. Apply modifiers:
   
   IF signal_count >= 3:
       score = base_score × 1.15  # Multiple red flags
   IF signal_count >= 4:
       score = score × 1.10  # Even more suspicious
   IF wallet_age < 24 hours:
       score = score × 1.10  # New wallet bonus
   IF win_rate > 80%:
       score = score × 1.05  # Too successful
   IF in_sybil_cluster:
       score = score × 1.20  # Part of coordinated group

6. Cap at 1.0:
   final_score = min(1.0, score)

## Example Calculations

### Example 1: Classic Insider
Signals:

EARLY_BUYER: confidence 0.95
COORDINATED_BUYING: confidence 0.85
QUICK_FLIP: confidence 0.70

Calculation:
weighted_sum = (0.95 × 0.35) + (0.85 × 0.25) + (0.70 × 0.08)
= 0.3325 + 0.2125 + 0.056
= 0.601
total_weight = 0.35 + 0.25 + 0.08 = 0.68
base_score = 0.601 / 0.68 = 0.884
Modifiers (3 signals):
score = 0.884 × 1.15 = 1.017 → capped to 1.0
Final Score: 1.0 (CRITICAL)

### Example 2: Suspicious but Uncertain
Signals:

LARGE_BUY: confidence 0.60

Calculation:
weighted_sum = 0.60 × 0.12 = 0.072
total_weight = 0.12
base_score = 0.072 / 0.12 = 0.60
No modifiers apply.
Final Score: 0.60 (MEDIUM - needs more data)

## Risk Level Thresholds

| Score Range | Risk Level | Action |
|-------------|------------|--------|
| 0.90 - 1.00 | CRITICAL | Immediate alert, add to known insiders |
| 0.80 - 0.89 | HIGH | Alert, add to watchlist |
| 0.60 - 0.79 | MEDIUM | Monitor, gather more data |
| 0.40 - 0.59 | LOW | Log but no action |
| 0.00 - 0.39 | MINIMAL | Likely legitimate |

## Confidence Decay

Scores should decay over time if no new signals are detected:
daily_decay = 0.02  # 2% per day
For wallets with no new activity:
score = score × (1 - daily_decay × days_since_last_signal)
Minimum score after decay: 0.3 (if ever flagged)

This ensures old flags don't persist forever but wallets retain
some risk if they were ever suspicious.
