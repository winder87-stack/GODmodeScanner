# GODMODESCANNER Knowledge Base Index

This is the master index of all knowledge available to GODMODESCANNER.
When starting up or when uncertain, consult this index to find relevant information.

## Quick Reference

| Topic | File | Description |
|-------|------|-------------|
| Detection Rules | rules/detection_rules.md | Core detection algorithms and thresholds |
| Scoring System | rules/scoring_weights.md | How insider scores are calculated |
| Alert Levels | rules/alert_thresholds.md | When and how to alert |
| Insider Patterns | patterns/insider_patterns.md | Known insider behavior patterns |
| Sybil Attacks | patterns/sybil_patterns.md | Sybil cluster detection methods |
| Known Insiders | wallets/known_insiders.json | Database of flagged wallets |
| pump.fun Protocol | technical/pump_fun_protocol.md | How pump.fun works |
| Solana Basics | technical/solana_transactions.md | Transaction parsing reference |

## Mission Statement

GODMODESCANNER exists to protect retail traders from insider manipulation on pump.fun.
Our goal is to detect and flag insider wallets with high confidence before they can
dump on unsuspecting buyers.

## Core Principles

1. **Speed over perfection** - Flag suspicious activity quickly, refine later
2. **Evidence-based** - Every flag must have documented evidence
3. **Learn continuously** - Store all patterns in memory for future detection
4. **Zero false negatives** - Better to over-flag than miss an insider

## How to Use This Knowledge Base

When analyzing a new token launch:
1. First check wallets/known_insiders.json for known bad actors
2. Apply rules from rules/detection_rules.md
3. Match against patterns in patterns/insider_patterns.md
4. Calculate scores using rules/scoring_weights.md
5. Alert based on rules/alert_thresholds.md

When encountering an unknown situation:
1. Consult technical/ for protocol understanding
2. Check examples/ for similar past cases
3. If truly novel, document and add to knowledge base
