#!/usr/bin/env python3
"""
Obfuscate Telegram API credentials for distribution.

This script generates a Python file with obfuscated credentials that can be
included in the distributed application. This is NOT encryption - it only
makes casual extraction more difficult.

Usage:
    python scripts/obfuscate_credentials.py --api-id 12345 --api-hash xyz...
    
The output file can be imported to retrieve credentials:
    from adapters.telegram._credentials import get_credentials
    api_id, api_hash = get_credentials()
"""
import argparse
import base64
import secrets
from pathlib import Path


def obfuscate(api_id: int, api_hash: str) -> tuple[bytes, bytes]:
    """
    Obfuscate credentials using XOR with random key.
    
    Args:
        api_id: Telegram API ID
        api_hash: Telegram API Hash
        
    Returns:
        Tuple of (obfuscated_data, key) both base64 encoded
    """
    # Generate random obfuscation key
    key = secrets.token_bytes(32)
    
    # Combine credentials
    data = f"{api_id}:{api_hash}".encode()
    
    # XOR with key (extended if necessary)
    extended_key = (key * (len(data) // len(key) + 1))[:len(data)]
    obfuscated = bytes(a ^ b for a, b in zip(data, extended_key))
    
    return base64.b64encode(obfuscated), base64.b64encode(key)


def generate_embedded_file(obfuscated: bytes, key: bytes, output_path: Path) -> None:
    """
    Generate Python file with obfuscated credentials.
    
    Args:
        obfuscated: Base64-encoded obfuscated data
        key: Base64-encoded obfuscation key
        output_path: Path to write the output file
    """
    content = f'''"""
AUTO-GENERATED - DO NOT EDIT
Obfuscated Telegram API credentials for distribution.

WARNING: This is obfuscation, NOT encryption.
It only makes casual extraction more difficult.
"""
import base64

_O = {obfuscated!r}
_K = {key!r}


def get_credentials() -> tuple[int, str]:
    """
    Retrieve obfuscated credentials.
    
    Returns:
        Tuple of (api_id, api_hash)
    """
    data = base64.b64decode(_O)
    key = base64.b64decode(_K)
    extended_key = (key * (len(data) // len(key) + 1))[:len(data)]
    result = bytes(a ^ b for a, b in zip(data, extended_key)).decode()
    api_id_str, api_hash = result.split(':', 1)
    return int(api_id_str), api_hash
'''
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding='utf-8')
    print(f"✓ Obfuscated credentials written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Obfuscate Telegram API credentials for distribution"
    )
    parser.add_argument(
        '--api-id',
        type=int,
        required=True,
        help="Telegram API ID"
    )
    parser.add_argument(
        '--api-hash',
        required=True,
        help="Telegram API Hash"
    )
    parser.add_argument(
        '--output',
        default='adapters/telegram/_credentials.py',
        help="Output file path (default: adapters/telegram/_credentials.py)"
    )
    
    args = parser.parse_args()
    
    # Obfuscate
    obfuscated, key = obfuscate(args.api_id, args.api_hash)
    
    # Generate file
    output_path = Path(args.output)
    generate_embedded_file(obfuscated, key, output_path)
    
    print(f"✓ API ID: {args.api_id}")
    print(f"✓ API Hash: {args.api_hash[:8]}...{args.api_hash[-4:]}")
    print()
    print("To use in your code:")
    print("    from adapters.telegram._credentials import get_credentials")
    print("    api_id, api_hash = get_credentials()")


if __name__ == '__main__':
    main()
