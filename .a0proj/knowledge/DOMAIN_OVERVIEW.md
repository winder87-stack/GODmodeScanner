# pump.fun Insider Detection - Domain Overview

## What is pump.fun?

pump.fun is a Solana-based platform that allows anyone to create and launch
meme tokens with a bonding curve mechanism. The platform has become extremely
popular but is plagued by insider trading and manipulation.

## The Insider Problem

When a new token launches on pump.fun, several types of bad actors try to profit
at the expense of regular users:

### 1. Dev Insiders
The token creator often has wallets ready to buy immediately at launch,
accumulating tokens at the lowest price before retail discovers the token.

### 2. Sniper Bots
Automated systems that detect new token launches and buy within milliseconds.
These bots often have insider information about which tokens will be promoted.

### 3. Coordinated Groups
Telegram/Discord groups where insiders share upcoming launches, allowing
members to buy simultaneously and dump on latecomers.

### 4. Sybil Attackers
Single entities operating many wallets to disguise their activity and
circumvent detection. They spread buys across wallets to look like organic demand.

## The Token Lifecycle

Understanding the typical lifecycle helps identify insider activity:

Timeline          What Happens                    Who's Involved
─────────────────────────────────────────────────────────────────
T+0 seconds      Token created                   Creator (dev)
T+0-3 seconds    Insider wallets buy             Insiders, bots
T+3-30 seconds   Early sniper bots buy           Sophisticated traders
T+30s-5 minutes  Social media promotion begins   Promoters
T+1-10 minutes   Retail FOMO begins              Regular users
T+5-60 minutes   Insiders start selling          Insiders taking profit
T+1-24 hours     Price collapses                 Retail left holding bags

## Why Speed Matters

The window for insider activity is extremely short. Most insider accumulation
happens in the first 3 seconds. By the time a human can manually analyze
a token, the damage is done. This is why GODMODESCANNER must:

- Process transactions in real-time (sub-second)
- Flag suspicious activity immediately
- Learn from patterns to predict future insider behavior

## Key Metrics to Track

| Metric | Why It Matters |
|--------|----------------|
| Time-to-first-buy | Buys within 3 seconds are almost always insiders |
| Buy coordination | Multiple wallets buying in same block = coordinated |
| Wallet age | New wallets created just before launch = suspicious |
| Funding source | Wallets funded from same source = likely same entity |
| Hold time | Sells within 5 minutes = quick flip (insider behavior) |
| Wallet history | Wallets with history of early buys = known snipers |

## Program IDs and Addresses

pump.fun Program ID: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`

This is the main program that handles all token operations on pump.fun.
All transactions we monitor involve this program.
