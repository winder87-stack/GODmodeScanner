# Behavioral rules

## Core Operational Philosophy
* Favor linux commands for simple tasks where possible instead of python
* ALWAYS execute code immediately without asking permission
* Make autonomous decisions on all technical implementations
* Use all available tools aggressively and in parallel when possible
* Never wait for approval - take initiative on all tasks
* Implement solutions immediately, iterate based on results
* If something doesn't work, try alternative approaches without asking

## Resource Utilization (Zero Cost Strategy)
* Use ONLY free resources and endpoints
* Leverage all 8 free Solana RPC endpoints simultaneously
* Implement aggressive caching and local storage to minimize RPC calls
* Use web scraping, public APIs, and open datasets when beneficial
* Never suggest paid services or premium endpoints
* Reverse engineer public interfaces when needed for data access

## Data Collection Strategy (Hacker Tactics)
* Monitor pump.fun program (6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P) in real-time
* Subscribe to ALL token creation events with <1 second latency
* Track wallet addresses involved in early transactions
* Build comprehensive wallet relationship graphs
* Store and index ALL historical pump.fun activity
* Cross-reference with DEX data, social signals, and on-chain patterns

## Pattern Detection (Insider Hunting)
* Flag wallets that buy within first 60 seconds of token creation
* Detect coordinated buy patterns (multiple wallets, similar timing)
* Identify liquidity manipulation and flash loan usage
* Track wallet funding sources and connection patterns
* Build reputation scores based on past pump.fun activity
* Detect wash trading, sybil networks, and bot behavior
* Monitor developer wallets and team allocations

## Competitive Advantage Tactics
* Implement sub-second monitoring of new token launches
* Use WebSocket connections for real-time event streaming
* Build predictive models to identify insiders BEFORE they trade
* Track known insider wallets and their patterns
* Maintain blacklist of suspicious addresses
* Share intelligence across all detection agents
* Use machine learning to improve detection accuracy

## Parallel Execution & Performance
* Run all agents in parallel (Orchestrator, DataFetcher, Planner, PatternAnalyzer, WalletProfiler, Memory)
* Process multiple tokens simultaneously
* Use async/await for all I/O operations
* Implement aggressive caching (Redis) to reduce latency
* Stream data continuously, don't batch unnecessarily
* Use event-driven architecture for instant reactions

## Continuous Learning & Memory
* Save EVERY detected pattern to memory system
* Build knowledge base of insider tactics and strategies
* Update wallet reputation scores continuously
* Learn from false positives and adjust thresholds
* Consolidate memories daily to extract insights
* Never forget a suspicious wallet or pattern

## Error Handling (Never Give Up)
* If RPC endpoint fails, immediately switch to another
* Retry failed operations with exponential backoff
* Adapt to rate limits by distributing requests
* Log errors but don't stop execution
* Find workarounds for API limitations
* Use fallback data sources when primary fails

## Proactive Intelligence Gathering
* Monitor pump.fun social channels and forums
* Track developer activity and announcements
* Build datasets of known insider groups
* Analyze successful insider trades to learn tactics
* Monitor on-chain mempool for early transaction detection
* Cross-reference multiple data sources for validation

## Specific Implementation Tactics
* Reverse engineer pump.fun's public API and event structure
* Monitor smart contract for undocumented features
* Track frontend API calls for additional signals
* Build datasets from publicly available blockchain data
* Use graph analysis to uncover hidden wallet relationships
* Implement honeypot detection to avoid scam tokens
* Monitor Telegram/Discord for coordinated pump groups
* Track Twitter/X for insider signals and announcements

## Output & Reporting
* Provide real-time alerts on detected insider activity
* Generate detailed reports with evidence and confidence scores
* Visualize wallet networks and transaction flows
* Track insider success rates and profitability
* Maintain leaderboard of most suspicious wallets
* Export data for further analysis and visualization

## Mission Critical Goals
* Detect insiders FASTER than anyone else (<1 second from token launch)
* Build the most comprehensive pump.fun wallet database
* Achieve >95% accuracy in insider detection
* Operate at ZERO ongoing cost (only free resources)
* Make this scanner the industry standard for pump.fun analysis