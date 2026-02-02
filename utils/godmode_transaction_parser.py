"""
GodMode Transaction Parser

Enhanced transaction parser for GODMODESCANNER with additional
features for insider detection and pump.fun specific parsing.

Mirrors utils/transaction_parser.py with GodMode-specific enhancements.
"""

import structlog
from typing import Dict, List, Any, Optional
import base58
import re

logger = structlog.get_logger(__name__)

# Program IDs
PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
SOL_MINT = "So11111111111111111111111111111111111111112"

# Jito tip accounts
JITO_TIP_ACCOUNTS = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
]


class GodModeTransactionParser:
    """
    Enhanced transaction parser for GODMODESCANNER
    
    Features:
    - Pump.fun specific instruction parsing
    - Insider pattern detection in transactions
    - Jito bundle identification
    - Enhanced metadata extraction
    """
    
    def __init__(self):
        self.logger = logger.bind(parser="godmode_transaction")
    
    def parse_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a Solana transaction from RPC response (GodMode enhanced)
        
        Args:
            transaction_data: Raw transaction from RPC getTransaction
            
        Returns:
            Parsed transaction with GodMode-specific metadata
        """
        if not transaction_data:
            return None
        
        try:
            # Extract transaction components
            tx = transaction_data.get('transaction', {})
            meta = transaction_data.get('meta', {})
            
            # Parse message
            message = tx.get('message', {})
            
            # Basic parsing
            parsed = {
                'signature': transaction_data.get('signature'),
                'slot': transaction_data.get('slot'),
                'blockTime': transaction_data.get('blockTime'),
                'success': meta.get('err') is None,
                'fee': meta.get('fee', 0),
                
                # Parsed components
                'instructions': self.parse_instructions(message),
                'transfers': self.extract_transfers(meta),
                'logs': self.parse_logs(meta),
                'balance_changes': self.calculate_balance_changes(meta, message),
                'transaction_type': self.identify_transaction_type(message, meta),
                
                # GodMode enhancements
                'is_jito_bundle': self._is_jito_bundle(message),
                'pumpfun_action': self._extract_pumpfun_action(message),
                'insider_indicators': self._detect_insider_indicators(message, meta),
                
                # Raw data
                'raw_message': message,
                'raw_meta': meta
            }
            
            return parsed
            
        except Exception as e:
            logger.error(f"GodMode transaction parse error: {e}", 
                        signature=transaction_data.get('signature'))
            return None
    
    def extract_transfers(self, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract token transfers from transaction metadata
        
        Enhanced version with GodMode-specific tracking
        """
        transfers = []
        
        try:
            # Extract SOL transfers
            pre_balances = meta.get('preBalances', [])
            post_balances = meta.get('postBalances', [])
            accounts = meta.get('loadedAddresses', {}).get('writable', []) + \
                       meta.get('loadedAddresses', {}).get('readonly', [])
            
            for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
                if pre != post:
                    transfers.append({
                        'type': 'SOL',
                        'account_index': i,
                        'account': accounts[i] if i < len(accounts) else None,
                        'pre_balance': pre / 1e9,
                        'post_balance': post / 1e9,
                        'change': (post - pre) / 1e9,
                        'mint': SOL_MINT,
                        'is_significant': abs(post - pre) > 1e9  # > 1 SOL
                    })
            
            # Extract SPL token transfers
            pre_token_balances = meta.get('preTokenBalances', [])
            post_token_balances = meta.get('postTokenBalances', [])
            
            token_changes = {}
            
            for pre in pre_token_balances:
                key = (pre['accountIndex'], pre['mint'])
                token_changes[key] = {
                    'account_index': pre['accountIndex'],
                    'mint': pre['mint'],
                    'owner': pre.get('owner'),
                    'pre_amount': float(pre['uiTokenAmount']['uiAmount'] or 0),
                    'pre_decimals': pre['uiTokenAmount']['decimals']
                }
            
            for post in post_token_balances:
                key = (post['accountIndex'], post['mint'])
                if key in token_changes:
                    token_changes[key]['post_amount'] = float(post['uiTokenAmount']['uiAmount'] or 0)
                    token_changes[key]['change'] = token_changes[key]['post_amount'] - token_changes[key]['pre_amount']
                else:
                    token_changes[key] = {
                        'account_index': post['accountIndex'],
                        'mint': post['mint'],
                        'owner': post.get('owner'),
                        'pre_amount': 0.0,
                        'post_amount': float(post['uiTokenAmount']['uiAmount'] or 0),
                        'change': float(post['uiTokenAmount']['uiAmount'] or 0),
                        'pre_decimals': post['uiTokenAmount']['decimals']
                    }
            
            for change in token_changes.values():
                if change.get('change', 0) != 0:
                    transfers.append({
                        'type': 'SPL',
                        'is_significant': abs(change.get('change', 0)) > 1000,  # > 1000 tokens
                        **change
                    })
            
            return transfers
            
        except Exception as e:
            logger.error(f"GodMode transfer extraction error: {e}")
            return []
    
    def parse_instructions(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse all instructions from transaction message
        
        GodMode enhanced with detailed program analysis
        """
        instructions = []
        
        try:
            raw_instructions = message.get('instructions', [])
            account_keys = message.get('accountKeys', [])
            
            for idx, ix in enumerate(raw_instructions):
                program_id_index = ix.get('programIdIndex')
                program_id = account_keys[program_id_index] if program_id_index < len(account_keys) else None
                
                # Get accounts involved
                accounts = []
                for acc_idx in ix.get('accounts', []):
                    if acc_idx < len(account_keys):
                        accounts.append(account_keys[acc_idx])
                
                # Decode instruction data
                data_raw = ix.get('data', '')
                try:
                    data_bytes = base58.b58decode(data_raw)
                    data_hex = data_bytes.hex()
                except:
                    data_hex = None
                
                parsed_ix = {
                    'index': idx,
                    'program_id': program_id,
                    'accounts': accounts,
                    'data': data_raw,
                    'data_hex': data_hex,
                    'parsed': None,
                    'godmode_tags': []
                }
                
                # Enhanced program identification
                if program_id == PUMP_FUN_PROGRAM:
                    parsed_ix['program_name'] = 'pump.fun'
                    parsed_ix['parsed'] = self._parse_pumpfun_instruction(data_hex, accounts)
                    parsed_ix['godmode_tags'].append('pumpfun')
                    
                    # Detect early buyer
                    if parsed_ix['parsed'].get('type') == 'buy':
                        parsed_ix['godmode_tags'].append('potential_insider')
                
                elif program_id == SYSTEM_PROGRAM:
                    parsed_ix['program_name'] = 'system'
                    parsed_ix['parsed'] = {'type': 'system_call'}
                
                elif program_id == TOKEN_PROGRAM:
                    parsed_ix['program_name'] = 'spl-token'
                    parsed_ix['parsed'] = self._parse_token_instruction(data_hex)
                    parsed_ix['godmode_tags'].append('token_transfer')
                
                instructions.append(parsed_ix)
            
            return instructions
            
        except Exception as e:
            logger.error(f"GodMode instruction parsing error: {e}")
            return []
    
    def _parse_pumpfun_instruction(self, data_hex: str, accounts: List[str]) -> Dict:
        """Parse Pump.fun specific instruction"""
        if not data_hex:
            return {'type': 'unknown'}
        
        discriminators = {
            '66063d1201daebea': 'buy',
            'f0ba0a6e0d88d6c7': 'sell',
            'a0b6e9e7c9b8f5e4': 'create',
        }
        
        discriminator = data_hex[:16] if len(data_hex) >= 16 else None
        ix_type = discriminators.get(discriminator, 'unknown')
        
        return {
            'type': ix_type,
            'discriminator': discriminator,
            'accounts': accounts,
            'is_trading': ix_type in ['buy', 'sell']
        }
    
    def _parse_token_instruction(self, data_hex: str) -> Dict:
        """Parse SPL Token instruction"""
        if not data_hex or len(data_hex) < 2:
            return {'type': 'unknown'}
        
        instruction_types = {
            '03': 'transfer',
            '07': 'mintTo',
            '08': 'burn',
            '09': 'closeAccount',
        }
        
        ix_type = data_hex[:2]
        
        return {
            'type': instruction_types.get(ix_type, 'unknown'),
            'instruction_byte': ix_type
        }
    
    def parse_logs(self, meta: Dict[str, Any]) -> List[str]:
        """
        Parse transaction logs with GodMode enhancements
        """
        logs = []
        
        try:
            raw_logs = meta.get('logMessages', [])
            
            for log in raw_logs:
                parsed_log = {'raw': log}
                
                # Parse compute units
                if 'consumed' in log.lower():
                    match = re.search(r'consumed (\d+) of (\d+) compute units', log)
                    if match:
                        parsed_log['type'] = 'compute'
                        parsed_log['consumed'] = int(match.group(1))
                        parsed_log['limit'] = int(match.group(2))
                        parsed_log['efficiency'] = int(match.group(1)) / int(match.group(2))
                        logs.append(parsed_log)
                        continue
                
                # Parse program invocations
                if 'invoke' in log.lower():
                    parsed_log['type'] = 'invoke'
                    # Extract program ID if present
                    match = re.search(r'invoke \[?([A-Za-z0-9]+)\]?', log)
                    if match:
                        parsed_log['program'] = match.group(1)
                    logs.append(parsed_log)
                    continue
                
                # Parse errors
                if 'error' in log.lower() or 'failed' in log.lower():
                    parsed_log['type'] = 'error'
                    parsed_log['severity'] = 'high'
                    logs.append(parsed_log)
                    continue
                
                # Success indicators
                if 'success' in log.lower():
                    parsed_log['type'] = 'success'
                    logs.append(parsed_log)
                    continue
                
                # Generic log
                parsed_log['type'] = 'log'
                logs.append(parsed_log)
            
            return logs
            
        except Exception as e:
            logger.error(f"GodMode log parsing error: {e}")
            return []
    
    def calculate_balance_changes(self, meta: Dict[str, Any], message: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate balance changes for all accounts
        
        GodMode enhanced with additional metadata
        """
        changes = {}
        
        try:
            pre_balances = meta.get('preBalances', [])
            post_balances = meta.get('postBalances', [])
            account_keys = message.get('accountKeys', [])
            
            for i, (pre, post) in enumerate(zip(pre_balances, post_balances)):
                if i < len(account_keys):
                    account = account_keys[i]
                    change_lamports = post - pre
                    change_sol = change_lamports / 1e9
                    
                    if change_sol != 0:
                        changes[account] = {
                            'change_sol': change_sol,
                            'change_lamports': change_lamports,
                            'is_sender': change_sol < 0,
                            'is_receiver': change_sol > 0,
                            'magnitude': abs(change_sol)
                        }
            
            return changes
            
        except Exception as e:
            logger.error(f"GodMode balance calculation error: {e}")
            return {}
    
    def identify_transaction_type(self, message: Dict[str, Any], meta: Dict[str, Any]) -> str:
        """
        Identify transaction type with GodMode enhancements
        """
        try:
            instructions = message.get('instructions', [])
            account_keys = message.get('accountKeys', [])
            
            # Check for Pump.fun
            for ix in instructions:
                program_idx = ix.get('programIdIndex')
                if program_idx < len(account_keys):
                    program_id = account_keys[program_idx]
                    
                    if program_id == PUMP_FUN_PROGRAM:
                        data = ix.get('data', '')
                        try:
                            data_hex = base58.b58decode(data).hex()[:16]
                            
                            if data_hex == '66063d1201daebea':
                                return 'pump_buy'
                            elif data_hex == 'f0ba0a6e0d88d6c7':
                                return 'pump_sell'
                            elif data_hex == 'a0b6e9e7c9b8f5e4':
                                return 'pump_create'
                        except:
                            pass
                        
                        return 'pump_unknown'
                    
                    elif program_id == TOKEN_PROGRAM:
                        return 'token_transfer'
                    
                    elif program_id == SYSTEM_PROGRAM:
                        return 'sol_transfer'
            
            # Check for Jito bundle
            for account in account_keys:
                if account in JITO_TIP_ACCOUNTS:
                    return 'jito_bundle'
            
            return 'unknown'
            
        except Exception as e:
            logger.error(f"GodMode type identification error: {e}")
            return 'unknown'
    
    def _is_jito_bundle(self, message: Dict[str, Any]) -> bool:
        """Check if transaction is a Jito bundle"""
        account_keys = message.get('accountKeys', [])
        return any(acc in JITO_TIP_ACCOUNTS for acc in account_keys)
    
    def _extract_pumpfun_action(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract Pump.fun action if present"""
        instructions = message.get('instructions', [])
        account_keys = message.get('accountKeys', [])
        
        for ix in instructions:
            program_idx = ix.get('programIdIndex')
            if program_idx < len(account_keys):
                if account_keys[program_idx] == PUMP_FUN_PROGRAM:
                    data = ix.get('data', '')
                    try:
                        data_hex = base58.b58decode(data).hex()[:16]
                        discriminators = {
                            '66063d1201daebea': 'buy',
                            'f0ba0a6e0d88d6c7': 'sell',
                            'a0b6e9e7c9b8f5e4': 'create',
                        }
                        return discriminators.get(data_hex)
                    except:
                        pass
        
        return None
    
    def _detect_insider_indicators(self, message: Dict[str, Any], meta: Dict[str, Any]) -> List[str]:
        """Detect potential insider trading indicators"""
        indicators = []
        
        try:
            # Check for large transfers
            pre_balances = meta.get('preBalances', [])
            post_balances = meta.get('postBalances', [])
            
            for pre, post in zip(pre_balances, post_balances):
                change = abs(post - pre) / 1e9  # SOL
                if change > 100:  # > 100 SOL
                    indicators.append('large_transfer')
                    break
            
            # Check for Pump.fun interactions
            account_keys = message.get('accountKeys', [])
            if PUMP_FUN_PROGRAM in account_keys:
                indicators.append('pumpfun_interaction')
            
            # Check for Jito
            if self._is_jito_bundle(message):
                indicators.append('jito_bundle')
            
            return indicators
            
        except Exception as e:
            logger.error(f"Insider indicator detection error: {e}")
            return []
