# pump.fun Protocol Technical Reference

## Overview

pump.fun is a token launchpad on Solana that uses a bonding curve mechanism.
Anyone can create a token by paying a small fee, and the token immediately
becomes tradeable.

## Program ID
6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P

This is the main program that handles all token operations.

## Key Concepts

### Bonding Curve

pump.fun uses a constant product bonding curve (similar to Uniswap).
As more tokens are bought, the price increases. As tokens are sold,
the price decreases.
Price formula (simplified):
price = k / (total_supply - tokens_bought)
Where:

k = curve constant (set at token creation)
total_supply = initial token supply
tokens_bought = cumulative tokens purchased


### Migration

When a token reaches a certain market cap threshold on pump.fun,
it "graduates" and migrates to Raydium (full DEX). This is when
many insiders take profit.

Migration threshold: ~$69,000 market cap (can vary)

## Transaction Types

### 1. Create Token
Instruction: "create"
Creates new token with:

Token mint address (generated)
Initial supply
Bonding curve parameters
Creator receives no initial tokens


### 2. Buy
Instruction: "buy"
User sends SOL, receives tokens at current bonding curve price.
Emits: BuyEvent with amount, price, buyer

### 3. Sell
Instruction: "sell"
User sends tokens, receives SOL at current bonding curve price.
Emits: SellEvent with amount, price, seller

## Log Parsing

pump.fun transactions emit logs that can be parsed:
Example buy log:
"Program log: Instruction: Buy"
"Program log: buyer: <wallet_address>"
"Program log: amount: <sol_amount>"
"Program log: token_amount: <tokens_received>"

## Important Addresses

| Purpose | Address |
|---------|---------|
| Program ID | 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P |
| Fee Vault | (varies per deploy) |
| Migration Target | Raydium AMM |

## Rate Limits

Free RPC endpoints have rate limits:

| Endpoint | Limit |
|----------|-------|
| Solana Mainnet | ~100 req/s |
| Ankr | ~30 req/s |
| Public RPC | varies |

Rotate between endpoints to avoid hitting limits.
