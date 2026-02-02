"""
Transaction Parser for Solana Blockchain

Parses Solana transactions to extract:
- Token transfers (SOL and SPL)
- Instructions and program calls
- Balance changes
- Transaction types
- Logs and metadata
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


class TransactionParser:
    """Parse Solana transactions from RPC responses"""
    
    def __init__(self):
        self.logger = logger.bind(parser="transaction")
    
    def parse_transaction(self, transaction_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse a Solana transaction from RPC response
        
        Args:
            transaction_data: Raw transaction from RPC getTransaction
            
        Returns:
            Parsed transaction with metadata
        """
        if not transaction_data:
            return None
        
        try:
            # Extract transaction components
            tx = transaction_data.get('transaction', {})
            meta = transaction_data.get('meta', {})
            
            # Parse message
            message = tx.get('message', {})
            
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
                
                # Raw data
                'raw_message': message,
                'raw_meta': meta
            }
            
            return parsed
            
        except Exception as e:
            logger.error(f"Transaction parse error: {e}", signature=transaction_data.get('signature'))
            return None
    
    def extract_transfers(self, meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract token transfers from transaction metadata
        
        Parses both:
        - SOL transfers (preBalances/postBalances)
        - SPL token transfers (preTokenBalances/postTokenBalances)
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
                        'mint': SOL_MINT
                    })
            
            # Extract SPL token transfers
            pre_token_balances = meta.get('preTokenBalances', [])
            post_token_balances = meta.get('postTokenBalances', [])
            
            # Match pre/post by account index
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
                        **change
                    })
            
            return transfers
            
        except Exception as e:
            logger.error(f"Transfer extraction error: {e}")
            return []
    
    def parse_instructions(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse all instructions from transaction message
        
        Returns:
            List of parsed instructions with program, accounts, data
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
                
                # Decode instruction data (base58)
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
                    'parsed': None
                }
                
                # Try to identify instruction type
                if program_id == PUMP_FUN_PROGRAM:
                    parsed_ix['program_name'] = 'pump.fun'
                    parsed_ix['parsed'] = self._parse_pumpfun_instruction(data_hex, accounts)
                
                elif program_id == SYSTEM_PROGRAM:
                    parsed_ix['program_name'] = 'system'
                    parsed_ix['parsed'] = {'type': 'system_call'}
                
                elif program_id == TOKEN_PROGRAM:
                    parsed_ix['program_name'] = 'spl-token'
                    parsed_ix['parsed'] = self._parse_token_instruction(data_hex)
                
                instructions.append(parsed_ix)
            
            return instructions
            
        except Exception as e:
            logger.error(f"Instruction parsing error: {e}")
            return []
    
    def _parse_pumpfun_instruction(self, data_hex: str, accounts: List[str]) -> Dict:
        """Parse Pump.fun specific instruction"""
        if not data_hex:
            return {'type': 'unknown'}
        
        # Pump.fun instruction discriminators (first 8 bytes)
        discriminators = {
            '66063d1201daebea': 'buy',
            'f0ba0a6e0d88d6c7': 'sell',
            'a0b6e9e7c9b8f5e4': 'create',
        }
        
        discriminator = data_hex[:16] if len(data_hex) >= 16 else None
        
        return {
            'type': discriminators.get(discriminator, 'unknown'),
            'discriminator': discriminator,
            'accounts': accounts
        }
    
    def _parse_token_instruction(self, data_hex: str) -> Dict:
        """Parse SPL Token instruction"""
        if not data_hex or len(data_hex) < 2:
            return {'type': 'unknown'}
        
        # SPL Token instruction types (first byte)
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
        Parse transaction logs
        
        Extracts:
        - Program invocations
        - CPI (Cross-Program Invocation) calls
        - Compute units consumed
        - Errors
        """
        logs = []
        
        try:
            raw_logs = meta.get('logMessages', [])
            
            for log in raw_logs:
                # Parse compute units
                if 'consumed' in log.lower():
                    match = re.search(r'consumed (\d+) of (\d+) compute units', log)
                    if match:
                        logs.append({
                            'type': 'compute',
                            'consumed': int(match.group(1)),
                            'limit': int(match.group(2)),
                            'raw': log
                        })
                        continue
                
                # Parse program invocations
                if 'invoke' in log.lower():
                    logs.append({
                        'type': 'invoke',
                        'raw': log
                    })
                    continue
                
                # Parse errors
                if 'error' in log.lower() or 'failed' in log.lower():
                    logs.append({
                        'type': 'error',
                        'raw': log
                    })
                    continue
                
                # Generic log
                logs.append({
                    'type': 'log',
                    'raw': log
                })
            
            return logs
            
        except Exception as e:
            logger.error(f"Log parsing error: {e}")
            return []
    
    def calculate_balance_changes(self, meta: Dict[str, Any], message: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate balance changes for all accounts
        
        Returns:
            Dict mapping account address to balance change (negative = sent, positive = received)
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
                        changes[account] = change_sol
            
            return changes
            
        except Exception as e:
            logger.error(f"Balance calculation error: {e}")
            return {}
    
    def identify_transaction_type(self, message: Dict[str, Any], meta: Dict[str, Any]) -> str:
        """
        Identify transaction type based on instructions
        
        Types:
        - pump_buy: Pump.fun token purchase
        - pump_sell: Pump.fun token sale
        - pump_create: Pump.fun token creation
        - token_transfer: SPL token transfer
        - sol_transfer: SOL transfer
        - jito_bundle: Jito MEV bundle
        - unknown: Unrecognized
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
                        # Pump.fun transaction
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
            logger.error(f"Type identification error: {e}")
            return 'unknown'
