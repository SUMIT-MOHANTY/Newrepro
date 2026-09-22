"""
RSA utility for the BournAI metrics public endpoint.

Decrypts an incoming base64-encoded RSA ciphertext (salt_key)
using the RSA-2048 public key.

The external service encrypts the salt value with its RSA-2048 private key,
and we recover (decrypt) it here using the public key via raw RSA:
    plaintext = ciphertext^e mod n

We then strip PKCS1v15 padding to confirm the decryption was valid.
The RSA keypair itself IS the authentication mechanism.
"""

import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# RSA-2048 public key provided by BournAI for salt_key verification
BOURNAI_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAxgMczcTmX+917cqJ6mTp
OTWGKpW0b93pb8Mdc2tNx9o55i/5rX+wD+rbQKGr1gYZ/EUfNx+MaCaWJkbeIdGa
tJBp8rJG+ymbYyGIccVacFxWIipgnWw25M0UyQEmmadqDQtQiitHirXezzcnJiH1
svO+2+UuHuk47FMpmb+lZY5njF02nmM/95BKxebQMNZfBirbfw3xplNWOpFwJ3kT
njFiaAcKTBwEQS6LwphDlpsR6dhDIA/qFd0VxvnImqtyeN4MhsHXZgEkx8cKo0gi
60ITCPRQiVCepEhzqLjoar1jsSwiWJb6vgBJWVfsB8Tu5wuVYj5votxrMpM0Rxrn
GwIDAQAB
-----END PUBLIC KEY-----"""


def _rsa_raw_operation(cipher_int: int, n: int, e: int) -> int:
    """Perform raw RSA: plaintext = ciphertext^e mod n"""
    return pow(cipher_int, e, n)


def _strip_pkcs1v15_padding(plain_bytes: bytes) -> Optional[bytes]:
    """
    Strip PKCS1v15 padding from a raw RSA decryption result.
    
    PKCS1v15 block format (Type 1 - signature):
        0x00 0x01 0xFF 0xFF ... 0xFF 0x00 <message>
    
    PKCS1v15 block format (Type 2 - encryption):
        0x00 0x02 <random non-zero bytes> 0x00 <message>
    
    After lstrip(b'\\x00'), the first byte is the block type (0x01 or 0x02).
    Returns the message bytes, or None if padding is invalid.
    """
    stripped = plain_bytes.lstrip(b'\x00')
    
    if len(stripped) < 3:
        return None
    
    block_type = stripped[0]
    
    if block_type == 0x01:
        # Type 1: signature padding - 01 FF FF ... FF 00 <message>
        idx = 1
        while idx < len(stripped) and stripped[idx] == 0xFF:
            idx += 1
        if idx >= len(stripped) or stripped[idx] != 0x00:
            return None
        return stripped[idx + 1:]
    
    elif block_type == 0x02:
        # Type 2: encryption padding - 02 <random non-zero> 00 <message>
        idx = 1
        while idx < len(stripped) and stripped[idx] != 0x00:
            idx += 1
        if idx >= len(stripped):
            return None
        return stripped[idx + 1:]
    
    return None


def _load_key_components_cryptography(pem: str):
    """Load RSA key components (n, e) using the cryptography library."""
    from cryptography.hazmat.primitives import serialization
    
    public_key = serialization.load_pem_public_key(pem.encode())
    numbers = public_key.public_numbers()
    return numbers.n, numbers.e


def _load_key_components_pure_python(pem: str):
    """
    Parse a PEM-encoded RSA public key and return (n, e) as integers.
    Pure Python implementation using minimal ASN.1 DER parsing.
    """
    import re
    import struct
    
    # Strip PEM headers/footers and whitespace, decode base64
    b64_data = re.sub(
        r"-----BEGIN [A-Z ]+-----|-----END [A-Z ]+-----|\s+",
        "",
        pem,
    )
    der_bytes = base64.b64decode(b64_data)
    
    # RSA SubjectPublicKeyInfo DER structure:
    # SEQUENCE {                          -- outer
    #   SEQUENCE {                        -- algorithm identifier
    #     OID rsaEncryption (1.2.840.113549.1.1.1)
    #     NULL
    #   }
    #   BIT STRING {                      -- subjectPublicKey
    #     SEQUENCE {                      -- RSAPublicKey
    #       INTEGER (modulus n)
    #       INTEGER (exponent e)
    #     }
    #   }
    # }
    
    # Simple DER length decoder
    def read_length(data, pos):
        if pos >= len(data):
            return 0, pos
        byte = data[pos]
        if byte < 0x80:
            return byte, pos + 1
        num_bytes = byte & 0x7F
        if num_bytes == 0 or num_bytes > 4:
            raise ValueError(f"Unsupported DER length encoding at offset {pos}")
        val = 0
        for i in range(num_bytes):
            val = (val << 8) | data[pos + 1 + i]
        return val, pos + 1 + num_bytes
    
    # Parse outer SEQUENCE
    pos = 0
    if der_bytes[pos] != 0x30:
        raise ValueError("Expected SEQUENCE tag (0x30)")
    
    outer_len, pos = read_length(der_bytes, pos + 1)
    
    # Skip algorithm identifier SEQUENCE (should be 0x30 ...)
    if pos < len(der_bytes) and der_bytes[pos] == 0x30:
        algo_len, _ = read_length(der_bytes, pos + 1)
        pos = pos + 2 + algo_len  # Skip algorithm SEQUENCE
    
    # Expect BIT STRING tag
    if pos >= len(der_bytes) or der_bytes[pos] != 0x03:
        raise ValueError(f"Expected BIT STRING tag (0x03) at offset {pos}")
    
    bit_str_len, pos = read_length(der_bytes, pos + 1)
    
    # Skip unused bits byte
    if pos >= len(der_bytes):
        raise ValueError("Truncated BIT STRING")
    unused_bits = der_bytes[pos]
    pos += 1
    
    # Now at inner RSAPublicKey SEQUENCE
    if pos >= len(der_bytes) or der_bytes[pos] != 0x30:
        raise ValueError(f"Expected RSAPublicKey SEQUENCE (0x30) at offset {pos}")
    
    inner_len, pos = read_length(der_bytes, pos + 1)
    inner_end = pos + inner_len
    
    # Read modulus INTEGER
    if pos >= inner_end or der_bytes[pos] != 0x02:
        raise ValueError("Expected INTEGER tag (0x02) for modulus")
    n_len, pos = read_length(der_bytes, pos + 1)
    n_bytes = der_bytes[pos:pos + n_len]
    n = int.from_bytes(n_bytes, byteorder='big')
    pos += n_len
    
    # Read exponent INTEGER
    if pos >= inner_end or der_bytes[pos] != 0x02:
        raise ValueError("Expected INTEGER tag (0x02) for exponent")
    e_len, pos = read_length(der_bytes, pos + 1)
    e_bytes = der_bytes[pos:pos + e_len]
    e = int.from_bytes(e_bytes, byteorder='big')
    
    return n, e


def decrypt_and_verify(
    encrypted_salt_b64: str,
    expected_salt: Optional[str] = None,
    public_key_pem: Optional[str] = None,
) -> bool:
    """
    Decrypt the base64-encoded RSA ciphertext using the RSA-2048 public key,
    then compare the decrypted plaintext with the expected salt value.

    The external service encrypts the known salt value with their private key.
    We decrypt it here with the public key and confirm it matches.

    Args:
        encrypted_salt_b64: Base64-encoded RSA ciphertext
        expected_salt: Expected plaintext salt value to match against
        public_key_pem: PEM-encoded RSA public key (defaults to BOURNAI_PUBLIC_KEY)

    Returns:
        True if decryption succeeds AND decrypted text matches expected_salt
    """
    if public_key_pem is None:
        public_key_pem = BOURNAI_PUBLIC_KEY

    try:
        # Try using the cryptography library first (most reliable PEM parsing)
        n, e = _load_key_components_cryptography(public_key_pem)
    except ImportError:
        # Fall back to pure Python DER parsing
        logger.info("cryptography library not available, using pure Python RSA")
        try:
            n, e = _load_key_components_pure_python(public_key_pem)
        except Exception as e2:
            logger.error(f"Failed to parse RSA public key: {e2}")
            return False
    except Exception as e:
        logger.warning(f"cryptography parsing failed, falling back to pure Python: {e}")
        try:
            n, e = _load_key_components_pure_python(public_key_pem)
        except Exception as e2:
            logger.error(f"Pure Python key parsing also failed: {e2}")
            return False

    # Decode the base64 ciphertext
    try:
        ciphertext = base64.b64decode(encrypted_salt_b64)
    except Exception as e:
        logger.error(f"Failed to base64-decode salt_key: {e}")
        return False

    # Convert to integer and perform raw RSA operation
    cipher_int = int.from_bytes(ciphertext, byteorder='big')
    plain_int = _rsa_raw_operation(cipher_int, n, e)

    # Convert result to bytes (pad to RSA modulus length)
    byte_length = (n.bit_length() + 7) // 8
    plain_bytes = plain_int.to_bytes(byte_length, byteorder='big')

    # Strip PKCS1v15 padding
    message_bytes = _strip_pkcs1v15_padding(plain_bytes)
    if message_bytes is None:
        logger.warning("PKCS1v15 padding not found — authentication rejected")
        return False

    # Decode the extracted message
    try:
        message_str = message_bytes.decode('utf-8', errors='replace')
    except Exception as e:
        logger.error(f"Failed to decode decrypted message: {e}")
        return False

    # Compare with expected salt
    if expected_salt is not None and message_str != expected_salt:
        logger.warning("Decrypted salt does not match expected value — authentication rejected")
        return False

    # Decryption + comparison succeeded
    return True
