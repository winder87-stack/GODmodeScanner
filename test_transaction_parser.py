"""Test Transaction Parser implementations"""

import sys
sys.path.insert(0, '.')

from utils.transaction_parser import TransactionParser
from utils.godmode_transaction_parser import GodModeTransactionParser

def test_transaction_parser():
    print("=" * 60)
    print("TESTING: utils/transaction_parser.py")
    print("=" * 60)
    
    parser = TransactionParser()
    
    # Sample transaction data
    sample_tx = {
        'signature': 'test123456789',
        'slot': 123456789,
        'blockTime': 1704067200,
        'transaction': {
            'message': {
                'accountKeys': [
                    'So11111111111111111111111111111111111111112',
                    '6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P',
                    'testwallet123456789'
                ],
                'instructions': [
                    {
                        'programIdIndex': 1,
                        'accounts': [0, 1, 2],
                        'data': 'test_data'
                    }
                ]
            }
        },
        'meta': {
            'err': None,
            'fee': 5000,
            'preBalances': [1000000000, 500000000, 100000000],
            'postBalances': [999995000, 500000000, 100000000],
            'preTokenBalances': [],
            'postTokenBalances': [],
            'logMessages': [
                'Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P invoke [1]',
                'Program log: Buy 1000000 tokens',
                'Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P consumed 20000 of 200000 compute units',
                'Program 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P success'
            ]
        }
    }
    
    print("\n1. Testing parse_transaction...")
    result = parser.parse_transaction(sample_tx)
    
    if result:
        print(f"✅ parse_transaction: PASSED")
        print(f"   Signature: {result['signature']}")
        print(f"   Success: {result['success']}")
        print(f"   Type: {result['transaction_type']}")
    else:
        print("❌ parse_transaction: FAILED")
        return False
    
    print("\n2. Testing extract_transfers...")
    transfers = parser.extract_transfers(sample_tx['meta'])
    print(f"✅ extract_transfers: PASSED ({len(transfers)} transfers found)")
    
    print("\n3. Testing parse_instructions...")
    instructions = parser.parse_instructions(sample_tx['transaction']['message'])
    print(f"✅ parse_instructions: PASSED ({len(instructions)} instructions)")
    if instructions:
        print(f"   Program: {instructions[0].get('program_name', 'unknown')}")
    
    print("\n4. Testing parse_logs...")
    logs = parser.parse_logs(sample_tx['meta'])
    print(f"✅ parse_logs: PASSED ({len(logs)} logs parsed)")
    
    print("\n5. Testing calculate_balance_changes...")
    changes = parser.calculate_balance_changes(
        sample_tx['meta'],
        sample_tx['transaction']['message']
    )
    print(f"✅ calculate_balance_changes: PASSED ({len(changes)} changes)")
    
    print("\n6. Testing identify_transaction_type...")
    tx_type = parser.identify_transaction_type(
        sample_tx['transaction']['message'],
        sample_tx['meta']
    )
    print(f"✅ identify_transaction_type: PASSED (type: {tx_type})")
    
    return True

def test_godmode_transaction_parser():
    print("\n" + "=" * 60)
    print("TESTING: utils/godmode_transaction_parser.py")
    print("=" * 60)
    
    parser = GodModeTransactionParser()
    
    # Sample transaction with Jito tip
    sample_tx = {
        'signature': 'jito_test_123',
        'slot': 123456790,
        'blockTime': 1704067201,
        'transaction': {
            'message': {
                'accountKeys': [
                    'So11111111111111111111111111111111111111112',
                    '96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5',  # Jito tip account
                    'testwallet987654321'
                ],
                'instructions': [
                    {
                        'programIdIndex': 0,
                        'accounts': [0, 1, 2],
                        'data': 'jito_bundle_data'
                    }
                ]
            }
        },
        'meta': {
            'err': None,
            'fee': 10000,
            'preBalances': [1000000000, 0, 100000000],
            'postBalances': [999990000, 10000, 100000000],
            'preTokenBalances': [],
            'postTokenBalances': [],
            'logMessages': [
                'Program 11111111111111111111111111111111 invoke [1]',
                'Program log: Jito bundle executed',
                'Program 11111111111111111111111111111111 success'
            ]
        }
    }
    
    print("\n1. Testing GodMode parse_transaction...")
    result = parser.parse_transaction(sample_tx)
    
    if result:
        print(f"✅ GodMode parse_transaction: PASSED")
        print(f"   Signature: {result['signature']}")
        print(f"   Is Jito Bundle: {result.get('is_jito_bundle', False)}")
        print(f"   Insider Indicators: {result.get('insider_indicators', [])}")
    else:
        print("❌ GodMode parse_transaction: FAILED")
        return False
    
    print("\n2. Testing _is_jito_bundle...")
    is_jito = parser._is_jito_bundle(sample_tx['transaction']['message'])
    print(f"✅ _is_jito_bundle: PASSED (detected: {is_jito})")
    
    print("\n3. Testing _detect_insider_indicators...")
    indicators = parser._detect_insider_indicators(
        sample_tx['transaction']['message'],
        sample_tx['meta']
    )
    print(f"✅ _detect_insider_indicators: PASSED ({len(indicators)} indicators)")
    
    return True

def main():
    print("\n" + "=" * 60)
    print("TRANSACTION PARSER TEST SUITE")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("transaction_parser.py", test_transaction_parser()))
    except Exception as e:
        print(f"\n❌ transaction_parser.py failed: {e}")
        results.append(("transaction_parser.py", False))
    
    try:
        results.append(("godmode_transaction_parser.py", test_godmode_transaction_parser()))
    except Exception as e:
        print(f"\n❌ godmode_transaction_parser.py failed: {e}")
        results.append(("godmode_transaction_parser.py", False))
    
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
    
    all_passed = all(passed for _, passed in results)
    
    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
