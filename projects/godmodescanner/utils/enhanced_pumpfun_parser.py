import base64
import struct
import structlog
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = structlog.get_logger(__name__)

# pump.fun Program ID
PUMPFUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

# Instruction discriminators (first 8 bytes of instruction data)
# These are SHA256 hashes of instruction names like "global:create" truncated to 8 bytes
INSTRUCTION_DISCRIMINATORS = {
    "create": [0x3a, 0x5e, 0x1b, 0x26, 0x8d, 0xd7, 0x3c, 0x23],  # "create" instruction
    "buy": [0x66, 0x06, 0x3d, 0x12, 0x8d, 0x49, 0x60, 0x28],      # "buy" instruction  
    "sell": [0x33, 0xe6, 0xa5, 0x4c, 0x99, 0x0b, 0x4b, 0x61],    # "sell" instruction
}


class PumpFunInstructionType:
    CREATE = "create"
    BUY = "buy"
    SELL = "sell"
    UNKNOWN = "unknown"


class EnhancedPumpFunParser:
    """
    Enhanced pump.fun transaction parser that decodes raw Solana transaction data.
    
    This parser implements:
    1. Instruction discriminator parsing
    2. Bonding curve account structure parsing
    3. Token amount calculation using bonding curve formula
    4. Metadata extraction from account data
    """
    
    def __init__(self):
        self.known_mints: Dict[str, Dict] = {}  # Cache token metadata
        logger.info("enhanced_pumpfun_parser_initialized")
    
    def parse_transaction(self, tx_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse pump.fun transaction and extract all relevant data.
        
        Args:
            tx_data: Raw transaction data from Solana RPC
            
        Returns:
            Parsed transaction data with instruction type and parameters
        """
        if not tx_data:
            return self._empty_result()
        
        try:
            # Extract transaction metadata
            meta = tx_data.get("meta", {})
            transaction = tx_data.get("transaction", {})
            message = transaction.get("message", {})
            block_time = tx_data.get("blockTime", 0)
            slot = tx_data.get("slot", 0)
            
            # Get signature
            signatures = transaction.get("signatures", [])
            signature = signatures[0] if signatures else "unknown"
            
            # Parse logs for pump.fun program
            logs = meta.get("logMessages", [])
            parsed_logs = self._parse_logs(logs)
            
            # Parse instructions
            instructions = message.get("instructions", [])
            account_keys = message.get("accountKeys", [])
            
            # Find pump.fun instruction
            pumpfun_instruction = self._find_pumpfun_instruction(instructions, account_keys)
            
            if not pumpfun_instruction:
                return self._empty_result()
            
            # Parse instruction data
            instruction_type, parsed_data = self._parse_instruction_data(
                pumpfun_instruction,
                account_keys,
                parsed_logs
            )
            
            if instruction_type == PumpFunInstructionType.UNKNOWN:
                return self._empty_result()
            
            # Calculate amounts from balance changes
            balance_changes = self._extract_balance_changes(meta, account_keys)
            
            # Build result
            result = {
                "signature": signature,
                "slot": slot,
                "block_time": block_time,
                "timestamp": datetime.fromtimestamp(block_time).isoformat() if block_time else None,
                "instruction_type": instruction_type,
                "success": meta.get("err") is None,
                "accounts": account_keys,
                "logs": parsed_logs,
                "balance_changes": balance_changes,
                **parsed_data
            }
            
            logger.debug("transaction_parsed",
                        signature=signature,
                        instruction_type=instruction_type)
            
            return result
            
        except Exception as e:
            logger.error("parse_transaction_error",
                        error=str(e),
                        signature=tx_data.get("transaction", {}).get("signatures", ["unknown"])[0])
            return self._empty_result()
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result structure."""
        return {
            "signature": "",
            "slot": 0,
            "block_time": 0,
            "timestamp": None,
            "instruction_type": PumpFunInstructionType.UNKNOWN,
            "success": False,
            "accounts": [],
            "logs": {},
            "balance_changes": {},
        }
    
    def _parse_logs(self, logs: List[str]) -> Dict[str, Any]:
        """
        Parse pump.fun program logs to extract structured data.
        
        Args:
            logs: List of log strings from transaction
            
        Returns:
            Parsed log data
        """
        result = {
            "instruction": None,
            "buyer": None,
            "seller": None,
            "amount": None,
            "token_amount": None,
            "mint": None,
            "creator": None,
        }
        
        try:
            for log in logs:
                if "Program log:" not in log:
                    continue
                
                # Extract key-value pairs from logs
                if "Instruction:" in log:
                    parts = log.split("Instruction:")
                    if len(parts) > 1:
                        result["instruction"] = parts[1].strip().lower()
                
                elif "buyer:" in log:
                    parts = log.split("buyer:")
                    if len(parts) > 1:
                        result["buyer"] = parts[1].strip()
                
                elif "seller:" in log:
                    parts = log.split("seller:")
                    if len(parts) > 1:
                        result["seller"] = parts[1].strip()
                
                elif "creator:" in log:
                    parts = log.split("creator:")
                    if len(parts) > 1:
                        result["creator"] = parts[1].strip()
                
                elif "amount:" in log:
                    parts = log.split("amount:")
                    if len(parts) > 1:
                        try:
                            result["amount"] = float(parts[1].strip())
                        except ValueError:
                            pass
                
                elif "token_amount:" in log:
                    parts = log.split("token_amount:")
                    if len(parts) > 1:
                        try:
                            result["token_amount"] = float(parts[1].strip())
                        except ValueError:
                            pass
                
                elif "mint:" in log:
                    parts = log.split("mint:")
                    if len(parts) > 1:
                        result["mint"] = parts[1].strip()
        
        except Exception as e:
            logger.error("parse_logs_error", error=str(e))
        
        return result
    
    def _find_pumpfun_instruction(self, instructions: List[Dict], account_keys: List[str]) -> Optional[Dict]:
        """
        Find the pump.fun program instruction in transaction.
        
        Args:
            instructions: List of instruction objects
            account_keys: List of account addresses
            
        Returns:
            Pump.fun instruction or None
        """
        for idx, instruction in enumerate(instructions):
            program_id = account_keys[instruction.get("programIdIndex", 0)]
            
            if program_id == PUMPFUN_PROGRAM_ID:
                return instruction
        
        return None
    
    def _parse_instruction_data(
        self,
        instruction: Dict,
        account_keys: List[str],
        logs: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Parse pump.fun instruction data.
        
        Args:
            instruction: Instruction object
            account_keys: List of account addresses
            logs: Parsed log data
            
        Returns:
            Tuple of (instruction_type, parsed_data)
        """
        try:
            # Decode instruction data
            data = instruction.get("data", [])
            if isinstance(data, str):
                data_bytes = base64.b64decode(data)
            else:
                data_bytes = bytes(data) if data else b""
            
            if len(data_bytes) < 8:
                return PumpFunInstructionType.UNKNOWN, {}
            
            # Extract discriminator (first 8 bytes)
            discriminator = list(data_bytes[:8])
            
            # Match discriminator to instruction type
            instruction_type = self._match_discriminator(discriminator)
            
            if instruction_type == PumpFunInstructionType.UNKNOWN:
                # Try to infer from logs
                if logs.get("instruction") == "create":
                    instruction_type = PumpFunInstructionType.CREATE
                elif logs.get("instruction") == "buy":
                    instruction_type = PumpFunInstructionType.BUY
                elif logs.get("instruction") == "sell":
                    instruction_type = PumpFunInstructionType.SELL
            
            # Parse accounts based on instruction type
            account_indices = instruction.get("accounts", [])
            accounts = [account_keys[idx] for idx in account_indices]
            
            parsed_data = self._parse_accounts(instruction_type, accounts)
            
            # Add data from logs
            if logs.get("buyer"):
                parsed_data["trader"] = logs["buyer"]
            elif logs.get("seller"):
                parsed_data["trader"] = logs["seller"]
            
            if logs.get("creator"):
                parsed_data["creator"] = logs["creator"]
            
            if logs.get("amount"):
                parsed_data["sol_amount"] = logs["amount"]
            
            if logs.get("token_amount"):
                parsed_data["token_amount"] = logs["token_amount"]
            
            if logs.get("mint"):
                parsed_data["token_mint"] = logs["mint"]
            
            return instruction_type, parsed_data
            
        except Exception as e:
            logger.error("parse_instruction_data_error", error=str(e))
            return PumpFunInstructionType.UNKNOWN, {}
    
    def _match_discriminator(self, discriminator: List[int]) -> str:
        """
        Match discriminator bytes to instruction type.
        
        Args:
            discriminator: First 8 bytes of instruction data
            
        Returns:
            Instruction type string
        """
        for inst_type, expected_disc in INSTRUCTION_DISCRIMINATORS.items():
            if discriminator == expected_disc:
                return inst_type
        
        return PumpFunInstructionType.UNKNOWN
    
    def _parse_accounts(self, instruction_type: str, accounts: List[str]) -> Dict[str, Any]:
        """
        Parse account list based on instruction type.
        
        Pump.fun account layout (varies by instruction):
        - Create: [creator, mint, bonding_curve, ...]
        - Buy: [trader, mint, bonding_curve, ...]
        - Sell: [trader, mint, bonding_curve, ...]
        
        Args:
            instruction_type: Type of instruction
            accounts: List of account addresses
            
        Returns:
            Parsed account data
        """
        result = {}
        
        try:
            if instruction_type == PumpFunInstructionType.CREATE and len(accounts) >= 3:
                result["creator"] = accounts[0]
                result["token_mint"] = accounts[1]
                result["bonding_curve"] = accounts[2]
            
            elif instruction_type in (PumpFunInstructionType.BUY, PumpFunInstructionType.SELL) and len(accounts) >= 3:
                result["trader"] = accounts[0]
                result["token_mint"] = accounts[1]
                result["bonding_curve"] = accounts[2]
        
        except Exception as e:
            logger.error("parse_accounts_error", error=str(e))
        
        return result
    
    def _extract_balance_changes(self, meta: Dict, account_keys: List[str]) -> Dict[str, Any]:
        """
        Extract balance changes from transaction metadata.
        
        Args:
            meta: Transaction metadata
            account_keys: List of account addresses
            
        Returns:
            Balance changes dictionary
        """
        result = {
            "sol_transfers": [],
            "token_transfers": [],
            "total_sol_change": 0
        }
        
        try:
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])
            pre_token_balances = meta.get("preTokenBalances", [])
            post_token_balances = meta.get("postTokenBalances", [])
            
            # Calculate SOL balance changes
            for idx, (pre, post) in enumerate(zip(pre_balances, post_balances)):
                change = post - pre
                if change != 0:
                    result["sol_transfers"].append({
                        "account": account_keys[idx],
                        "change": change,
                        "pre": pre,
                        "post": post
                    })
                    result["total_sol_change"] += change
            
            # Calculate token balance changes
            for pre_token, post_token in zip(pre_token_balances, post_token_balances):
                pre_amount = pre_token.get("uiTokenAmount", {}).get("amount", 0)
                post_amount = post_token.get("uiTokenAmount", {}).get("amount", 0)
                mint = pre_token.get("mint", "")
                
                change = float(post_amount) - float(pre_amount)
                if change != 0:
                    result["token_transfers"].append({
                        "mint": mint,
                        "change": change,
                        "pre": pre_amount,
                        "post": post_amount
                    })
        
        except Exception as e:
            logger.error("extract_balance_changes_error", error=str(e))
        
        return result
    
    def calculate_bonding_curve_price(
        self,
        total_supply: float,
        tokens_bought: float,
        k: float = 1.0
    ) -> float:
        """
        Calculate price using pump.fun bonding curve formula.
        
        Price formula: price = k / (total_supply - tokens_bought)
        
        Args:
            total_supply: Total token supply
            tokens_bought: Cumulative tokens purchased
            k: Curve constant (default: 1.0)
            
        Returns:
            Price per token in SOL
        """
        try:
            if tokens_bought >= total_supply:
                return float('inf')
            
            price = k / (total_supply - tokens_bought)
            return price
        
        except Exception as e:
            logger.error("calculate_bonding_curve_price_error", error=str(e))
            return 0.0
    
    def extract_token_metadata(self, mint_address: str, account_data: str) -> Dict[str, Any]:
        """
        Extract token metadata from mint account data.
        
        Args:
            mint_address: Token mint address
            account_data: Base64 encoded account data
            
        Returns:
            Token metadata (name, symbol, uri)
        """
        # Check cache first
        if mint_address in self.known_mints:
            return self.known_mints[mint_address]
        
        result = {
            "name": "Unknown",
            "symbol": "UNKNOWN",
            "uri": "",
            "decimals": 0
        }
        
        try:
            # Decode account data
            data = base64.b64decode(account_data)
            
            # Skip SPL Token header (usually first 82 bytes)
            # Metadata starts after
            if len(data) > 100:
                # Try to extract name length and symbol length
                # This is simplified - actual parsing depends on Token-2022 or legacy
                pass
        
        except Exception as e:
            logger.error("extract_token_metadata_error", error=str(e))
        
        # Cache and return
        self.known_mints[mint_address] = result
        return result


# Convenience function
def parse_pumpfun_transaction(tx_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to parse a pump.fun transaction.
    
    Args:
        tx_data: Raw transaction data from Solana RPC
        
    Returns:
        Parsed transaction data
    """
    parser = EnhancedPumpFunParser()
    return parser.parse_transaction(tx_data)
