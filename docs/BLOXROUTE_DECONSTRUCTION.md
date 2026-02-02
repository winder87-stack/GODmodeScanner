# bloXroute Logic Deconstruction

## Overview

This document deconstructs the bloXroute Pump.fun streams to understand what we're losing and what needs to be replicated using native Solana RPC connections.

**Current State:** Using bloXroute WebSocket streams (wss://pump-ny.solana.dex.blxrbdn.com/ws)

**Target State:** Native Solana RPC-based monitoring with on-chain transaction parsing

---

## Part 1: What bloXroute Provides (Pre-Parsed Data)

### Stream 1: GetPumpFunNewTokensStream

**Purpose:** Detect when a new bonding curve account is created for Pump.fun

**Pre-Parsed Data Fields:**

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `txnHash` | string | Transaction signature | On-chain transaction |
| `mint` | string | New token mint address | Account data |
| `name` | string | Token name | Metadata / Account data |
| `symbol` | string | Token symbol | Metadata / Account data |
| `uri` | string | Token metadata URI | Metadata / Account data |
| `creator` | string | Creator wallet address | Instruction account |
| `bondingCurve` | string | Bonding curve PDA | Account data |
| `timestamp` | string | Unix timestamp | Block time |
| `slot` | int | Solana slot number | Block info |

**Event Detection Logic:**
```
1. Monitor for transactions to Pump.fun Program ID
2. Filter for "create" instruction
3. Extract bonding curve PDA from instruction accounts
4. Parse token mint from created account
5. Extract creator from signer
```

---

### Stream 2: GetPumpFunSwapsStream

**Purpose:** Detect transactions that interact with Pump.fun program and result in token swaps

**Pre-Parsed Data Fields:**

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `txnHash` | string | Transaction signature | On-chain transaction |
| `mintAddress` | string | Token mint address | Instruction account |
| `userAddress` | string | Wallet performing swap | Instruction account |
| `userTokenAccountAddress` | string | User's token account | Instruction account |
| `bondingCurveAddress` | string | Bonding curve PDA | Instruction account |
| `tokenVaultAddress` | string | Token vault PDA | Instruction account |
| `solAmount` | int | SOL amount (lamports) | Instruction data / log |
| `tokenAmount` | int | Token amount | Instruction data / log |
| `isBuy` | boolean | True if buy, false if sell | Instruction discriminator |
| `virtualSolReserves` | int | Virtual SOL reserves | Bonding curve account |
| `virtualTokenReserves` | int | Virtual token reserves | Bonding curve account |
| `creator` | string | Token creator | Bonding curve account |
| `timestamp` | string | Unix timestamp | Block time |
| `slot` | int | Solana slot number | Block info |

**Event Detection Logic:**
```
1. Monitor for transactions to Pump.fun Program ID
2. Filter for "buy" or "sell" instruction
3. Extract bonding curve PDA from instruction accounts
4. Parse user wallet from signer / instruction accounts
5. Extract SOL and token amounts from instruction data
6. Read bonding curve account for reserves
7. Determine buy/sell from instruction discriminator (0-7 bytes)
```

---

### Stream 3: GetPumpFunAMMSwapsStream

**Purpose:** Subset of swap data focusing on AMM mechanics (can be derived from swap transactions)

**Pre-Parsed Data Fields:**

Same as SWAPS stream plus:

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `ammMint` | string | AMM pool mint (derived) | Token mint address |
| `ammUserAccount` | string | User AMM account | Instruction account |
| `liquidityProviderFee` | int | LP fee amount | Calculated from reserves |
| `protocolFee` | int | Protocol fee amount | Calculated from amount |

**Note:** This is a derived stream. All data can be calculated from SWAPS data.

**AMM Calculations:**
```
lp_fee = solAmount * 0.01  # 1% LP fee
protocol_fee = solAmount * 0.006  # 0.6% protocol fee
net_amount = solAmount - lp_fee - protocol_fee
```

---

## Part 2: What We Need to Build

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Solana RPC Endpoints                            │
│              (Rotate: Ankr, Helius, QuickNode, etc.)                │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│              Transaction Filter (Program ID Monitor)                 │
│  - Subscribe to account changes (Program ID: 6EF8rrecthR5...)        │
│  - Filter transactions by program interaction                      │
│  - Batch transaction fetching with getConfirmedBlock               │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                Instruction Parser (Instruction 0-7 bytes)            │
│  - Parse instruction discriminator                                 │
│  - Map to operation: create (0x...), buy (0x...), sell (0x...)    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Account Data Parser (borsh)                        │
│  - Parse bonding curve accounts                                    │
│  - Extract: reserves, creator, mint, virtual reserves              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                Event Emitter (to Redis Streams)                    │
│  - NEW_TOKENS: godmode:new_tokens                                 │
│  - SWAPS: godmode:new_transactions                                 │
│  - AMM_SWAPS: godmode:new_transactions (calculated)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 3: Parsing Logic

### 3.1 Program ID Detection

**Pump.fun Program ID:** `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`

**Detection Strategy:**
```python
# Option 1: Account subscription (preferred)
from solana.rpc.websocket_api import SolanaWsClient

ws = SolanaWsClient("wss://api.mainnet-beta.solana.com")
await ws.account_subscribe(
    pubkey="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
    encoding="jsonParsed",
    commitment="confirmed"
)

# Option 2: Logs subscription
await ws.logs_subscribe(
    mentions=["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"]
)
```

---

### 3.2 Instruction Discriminator Parsing

Pump.fun uses instruction discriminators (first 8 bytes of SHA256 hash):

| Instruction | Discriminator (hex) | Discriminator (base64) |
|-------------|---------------------|------------------------|
| **create** | `6a618b2b...` | `amGysr...` |
| **buy** | `099e392e...` | `CZ45Lu...` |
| **sell** | `4b465b7e...` | `S0Zbf...` |

**Parsing Code:**
```python
import base64

INSTRUCTION_DISCRIMINATORS = {
    "create": "6a618b2b",
    "buy": "099e392e",
    "sell": "4b465b7e",
}

def parse_instruction(instruction_data: bytes) -> str:
    discriminator = instruction_data[:8].hex()
    for op, disc in INSTRUCTION_DISCRIMINATORS.items():
        if discriminator.startswith(disc[:8]):
            return op
    return "unknown"
```

---

### 3.3 Create Token Parsing

**Instruction Data Structure:**
```
[discriminator: 8 bytes]
[name_length: 4 bytes]
[name: name_length bytes]
[symbol_length: 4 bytes]
[symbol: symbol_length bytes]
[uri_length: 4 bytes]
[uri: uri_length bytes]
```

**Parsing Code:**
```python
import struct

def parse_create_instruction(data: bytes) -> dict:
    offset = 8  # Skip discriminator
    
    # Parse name
    name_len = struct.unpack("<I", data[offset:offset+4])[0]
    offset += 4
    name = data[offset:offset+name_len].decode("utf-8")
    offset += name_len
    
    # Parse symbol
    symbol_len = struct.unpack("<I", data[offset:offset+4])[0]
    offset += 4
    symbol = data[offset:offset+symbol_len].decode("utf-8")
    offset += symbol_len
    
    # Parse URI
    uri_len = struct.unpack("<I", data[offset:offset+4])[0]
    offset += 4
    uri = data[offset:offset+uri_len].decode("utf-8")
    
    return {
        "name": name,
        "symbol": symbol,
        "uri": uri,
    }
```

**Account List for Create:**

| Index | Purpose | Needed For |
|-------|---------|------------|
| 0 | Creator | `creator` field |
| 1 | Mint | `mint` field |
| 2 | Bonding Curve | `bondingCurve` field |
| 3 | Associated Bonding Curve | (ignore) |

---

### 3.4 Buy/Sell Instruction Parsing

**Instruction Data Structure:**
```
[discriminator: 8 bytes]
[amount: 8 bytes]  // SOL amount in lamports
[min_out: 8 bytes]   // Minimum tokens out (slippage protection)
```

**Parsing Code:**
```python
def parse_swap_instruction(data: bytes) -> dict:
    offset = 8  # Skip discriminator
    
    # Parse amount (SOL in lamports)
    amount = struct.unpack("<Q", data[offset:offset+8])[0]
    offset += 8
    
    # Parse minimum output
    min_out = struct.unpack("<Q", data[offset:offset+8])[0]
    
    return {
        "solAmount": amount,
        "minOut": min_out,
    }
```

**Account List for Buy:**

| Index | Purpose | Needed For |
|-------|---------|------------|
| 0 | Global Config | (ignore) |
| 1 | User | `userAddress` field |
| 2 | Bonding Curve | `bondingCurveAddress` field |
| 3 | Associated Bonding Curve | (ignore) |
| 4 | User Token Account | `userTokenAccountAddress` field |
| 5 | Token Vault | `tokenVaultAddress` field |
| 6 | System Program | (ignore) |
| 7 | Token Program | (ignore) |
| 8 | Events Authority | (ignore) |

**Account List for Sell:**

| Index | Purpose | Needed For |
|-------|---------|------------|
| 0 | Global Config | (ignore) |
| 1 | User | `userAddress` field |
| 2 | Bonding Curve | `bondingCurveAddress` field |
| 3 | Associated Bonding Curve | (ignore) |
| 4 | User Token Account | `userTokenAccountAddress` field |
| 5 | Token Vault | `tokenVaultAddress` field |
| 6 | System Program | (ignore) |
| 7 | Token Program | (ignore) |
| 8 | Events Authority | (ignore) |

---

### 3.5 Bonding Curve Account Parsing

**Account Data Structure (borsh):**
```
[discriminator: 8 bytes]
[virtual_token_reserves: 8 bytes]
[virtual_sol_reserves: 8 bytes]
[real_token_reserves: 8 bytes]
[completed: 1 byte]
[creator: 32 bytes]
```

**Parsing Code:**
```python
def parse_bonding_curve_account(data: bytes) -> dict:
    offset = 8  # Skip discriminator
    
    # Parse reserves
    virtual_token_reserves = struct.unpack("<Q", data[offset:offset+8])[0]
    offset += 8
    
    virtual_sol_reserves = struct.unpack("<Q", data[offset:offset+8])[0]
    offset += 8
    
    real_token_reserves = struct.unpack("<Q", data[offset:offset+8])[0]
    offset += 8
    
    # Parse completed flag
    completed = data[offset] == 1
    offset += 1
    
    # Parse creator (32 bytes, but it's optional in account)
    # Note: Creator might not be stored in account data
    
    return {
        "virtualTokenReserves": virtual_token_reserves,
        "virtualSolReserves": virtual_sol_reserves,
        "realTokenReserves": real_token_reserves,
        "completed": completed,
    }
```

---

### 3.6 Token Amount Calculation (Buy)

**Bonding Curve Formula:**
```
tokens_out = (sqrt((virtualSolReserves + solAmount) * virtualTokenReserves * 4) - virtualSolReserves * 2) / 2
```

**Implementation:**
```python
import math

def calculate_tokens_out(
    sol_amount: int,
    virtual_sol_reserves: int,
    virtual_token_reserves: int
) -> int:
    """Calculate tokens received from bonding curve purchase"""
    
    # Apply fees (1% LP fee + 0.6% protocol fee)
    fee = sol_amount * 0.016
    sol_amount_net = sol_amount - int(fee)
    
    # Bonding curve calculation
    product = (virtual_sol_reserves + sol_amount_net) * virtual_token_reserves * 4
    sqrt_product = int(math.isqrt(product))
    tokens_out = (sqrt_product - virtual_sol_reserves * 2) // 2
    
    return tokens_out
```

---

### 3.7 SOL Amount Calculation (Sell)

**Bonding Curve Formula (reverse):**
```
sol_out = ((virtualTokenReserves - tokenAmount) * virtualSolReserves / virtualTokenReserves) - fee
```

**Implementation:**
```python

def calculate_sol_out(
    token_amount: int,
    virtual_sol_reserves: int,
    virtual_token_reserves: int
) -> int:
    """Calculate SOL received from selling tokens"""
    
    # Bonding curve calculation
    sol_out = (
        (virtual_token_reserves - token_amount) * 
        virtual_sol_reserves // 
        virtual_token_reserves
    )
    
    # Apply fees
    fee = sol_out * 0.016
    sol_out_net = sol_out - int(fee)
    
    return sol_out_net
```

---

## Part 4: Data Field Mapping

### GetPumpFunNewTokensStream Mapping

| bloXroute Field | Source | RPC Method | Parser |
|-----------------|--------|------------|--------|
| `txnHash` | Transaction signature | `getConfirmedBlock` | N/A |
| `mint` | Instruction account[1] | `getConfirmedBlock` | Parse account list |
| `name` | Instruction data | `getConfirmedBlock` | Parse instruction data |
| `symbol` | Instruction data | `getConfirmedBlock` | Parse instruction data |
| `uri` | Instruction data | `getConfirmedBlock` | Parse instruction data |
| `creator` | Instruction account[0] | `getConfirmedBlock` | Parse account list |
| `bondingCurve` | Instruction account[2] | `getConfirmedBlock` | Parse account list |
| `timestamp` | Block timestamp | `getConfirmedBlock` | N/A |
| `slot` | Block slot | `getConfirmedBlock` | N/A |

### GetPumpFunSwapsStream Mapping

| bloXroute Field | Source | RPC Method | Parser |
|-----------------|--------|------------|--------|
| `txnHash` | Transaction signature | `getConfirmedBlock` | N/A |
| `mintAddress` | Bonding curve account | `getAccountInfo` | Parse bonding curve |
| `userAddress` | Instruction account[1] | `getConfirmedBlock` | Parse account list |
| `userTokenAccountAddress` | Instruction account[4] | `getConfirmedBlock` | Parse account list |
| `bondingCurveAddress` | Instruction account[2] | `getConfirmedBlock` | Parse account list |
| `tokenVaultAddress` | Instruction account[5] | `getConfirmedBlock` | Parse account list |
| `solAmount` | Instruction data | `getConfirmedBlock` | Parse instruction data |
| `tokenAmount` | Calculated | Custom | Calculate from curve |
| `isBuy` | Instruction discriminator | `getConfirmedBlock` | Parse discriminator |
| `virtualSolReserves` | Bonding curve account | `getAccountInfo` | Parse bonding curve |
| `virtualTokenReserves` | Bonding curve account | `getAccountInfo` | Parse bonding curve |
| `creator` | Bonding curve account | `getAccountInfo` | Parse bonding curve |
| `timestamp` | Block timestamp | `getConfirmedBlock` | N/A |
| `slot` | Block slot | `getConfirmedBlock` | N/A |

---

## Part 5: Rate Limiting Strategy

### RPC Endpoint Rotation

```python
RPC_ENDPOINTS = [
    "https://api.mainnet-beta.solana.com",  # 100 req/s
    "https://solana-api.projectserum.com",  # 100 req/s
    "https://rpc.ankr.com/solana",  # 30 req/s
    "https://solana-mainnet.g.alchemy.com/v2/YOUR_KEY",  # Custom
]

class RPCRotator:
    def __init__(self):
        self.endpoints = RPC_ENDPOINTS.copy()
        self.current_index = 0
        self.rate_limits = {url: 0 for url in RPC_ENDPOINTS}
    
    def get_next_endpoint(self) -> str:
        # Select endpoint with lowest current usage
        best = min(self.rate_limits.items(), key=lambda x: x[1])
        return best[0]
```

### Batching Strategy

```python
# Batch fetch multiple transactions in one RPC call
async def fetch_transactions_batch(
    signatures: List[str],
    batch_size: int = 100
) -> List[Transaction]:
    """Fetch transactions in batches"""
    
    results = []
    for i in range(0, len(signatures), batch_size):
        batch = signatures[i:i+batch_size]
        
        # Use getMultipleAccounts for efficiency
        accounts = await rpc_client.get_multiple_accounts(
            batch,
            encoding="base64"
        )
        
        results.extend(accounts.value)
    
    return results
```

---

## Part 6: Implementation Priority

### Phase 1: Core Monitoring (Critical)

1. **Program ID Subscription**
   - Implement WebSocket subscription to Pump.fun program ID
   - Filter transactions by program interaction
   - Deduplicate transaction signatures

2. **Instruction Discriminator Parser**
   - Parse first 8 bytes of instruction data
   - Map to create/buy/sell operations

3. **Basic Transaction Fetcher**
   - Fetch confirmed blocks with `getConfirmedBlock`
   - Extract transaction details
   - Parse account lists

### Phase 2: Data Extraction (High Priority)

4. **Create Token Parser**
   - Parse instruction data for name/symbol/uri
   - Extract mint, creator, bonding curve from accounts

5. **Swap Instruction Parser**
   - Parse SOL amount from instruction data
   - Extract user, bonding curve, token vault from accounts
   - Determine buy/sell from discriminator

6. **Bonding Curve Account Parser**
   - Parse virtual reserves from account data
   - Extract creator if present
   - Calculate token amounts using bonding curve formula

### Phase 3: Optimization (Medium Priority)

7. **Account Caching**
   - Cache bonding curve account data
   - Avoid redundant `getAccountInfo` calls
   - Implement TTL-based cache invalidation

8. **Batch Processing**
   - Batch transaction fetching
   - Batch account data fetching
   - Implement parallel processing

9. **Rate Limiting**
   - Implement endpoint rotation
   - Track request counts per endpoint
   - Implement exponential backoff on 429 errors

---

## Part 7: Performance Considerations

### Expected Latency

| Operation | bloXroute | Native RPC | Delta |
|-----------|-----------|------------|-------|
| **New Token Detection** | <50ms | 100-300ms | +50-250ms |
| **Swap Detection** | <50ms | 100-300ms | +50-250ms |
| **Account Data Fetch** | Included | 50-150ms | +50-150ms |

**Total End-to-End Latency:**
- bloXroute: ~50ms
- Native RPC: ~200-450ms

### Throughput

| Metric | bloXroute | Native RPC |
|--------|-----------|------------|
| **Messages/sec** | 1000+ | 500-800 |
| **RPC Calls/sec** | N/A | 100-300 |
| **CPU Usage** | Low | Medium (parsing) |

---

## Part 8: Cost Analysis

### bloXroute

| Cost | Amount |
|------|--------|
| **Monthly** | Free tier available |
| **Rate Limit** | High (unlimited?) |
| **Data** | Pre-parsed, minimal processing |

### Native RPC

| Cost | Amount |
|------|--------|
| **Free Endpoints** | 100-300 req/s (limited) |
| **Paid Endpoints** | $10-50/month for higher limits |
| **Data Processing** | Additional CPU for parsing |

**Recommendation:** Use free RPC endpoints with aggressive rotation and caching for zero-cost operation.

---

## Part 9: Risk Mitigation

### Potential Issues

| Issue | Impact | Mitigation |
|-------|--------|------------|
| **RPC Rate Limits** | Data gaps | Multi-endpoint rotation + caching |
| **Missing Transactions** | Incomplete data | Account subscription as fallback |
| **Parsing Errors** | Wrong data | Comprehensive error handling |
| **Schema Changes** | Breaks parsing | Flexible parser + fallback |

### Fallback Strategy

1. **Primary:** WebSocket subscription to Pump.fun program ID
2. **Fallback 1:** Logs subscription (less precise but reliable)
3. **Fallback 2:** Periodic polling of recent blocks
4. **Fallback 4:** Revert to bloXroute if available

---

## Summary

### What We're Losing

✅ **Pre-parsed data** - Must implement custom parsers  
✅ **Low latency** - Will add 50-250ms latency  
✅ **High throughput** - May reduce to 500-800 msg/s  
✅ **Zero processing** - Need CPU for parsing  

### What We're Gaining

✅ **Independence** - No reliance on third-party streams  
✅ **Control** - Full control over data pipeline  
✅ **Cost** - Can use free RPC endpoints  
✅ **Flexibility** - Can extend with custom logic  

### Implementation Complexity

| Component | Complexity | Time Estimate |
|-----------|-------------|---------------|
| **Program ID Monitor** | Medium | 2-3 hours |
| **Instruction Parser** | Low | 1-2 hours |
| **Account Parser** | Medium | 2-3 hours |
| **Bonding Curve Logic** | Medium | 2-3 hours |
| **Caching & Optimization** | High | 3-4 hours |
| **Testing & Debugging** | High | 4-6 hours |
| **Total** | - | 14-21 hours |

---

**Next Steps:** Proceed to Step 2 - Implementing the Pump.fun Parser
