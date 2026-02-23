import os
import base64
import json
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SALT_LENGTH = 32
IV_LENGTH = 16
KEY_LENGTH = 32
ITERATIONS = 100000
SENSITIVE_KEYS = ['client_secret', 'api_key', 'password', 'token', 'secret']


def _derive_key(salt: bytes) -> bytes:
    secret = os.environ.get('SESSION_SECRET', 'fallback-secret-key')
    return hashlib.pbkdf2_hmac('sha256', secret.encode(), salt, ITERATIONS, dklen=KEY_LENGTH)


def decrypt_value(ciphertext: str) -> str:
    combined = base64.b64decode(ciphertext)
    salt = combined[:SALT_LENGTH]
    iv = combined[SALT_LENGTH:SALT_LENGTH + IV_LENGTH]
    tag_and_encrypted = combined[SALT_LENGTH + IV_LENGTH:]
    tag = tag_and_encrypted[:16]
    encrypted = tag_and_encrypted[16:]

    key = _derive_key(salt)
    aesgcm = AESGCM(key)
    ciphertext_with_tag = encrypted + tag
    plaintext = aesgcm.decrypt(iv, ciphertext_with_tag, None)
    return plaintext.decode('utf-8')


def decrypt_config(config: dict) -> dict:
    if not config:
        return config
    decrypted = {}
    for key, value in config.items():
        if isinstance(value, dict) and value.get('__encrypted') is True:
            try:
                decrypted[key] = decrypt_value(value['value'])
            except Exception:
                decrypted[key] = ''
        else:
            decrypted[key] = value
    return decrypted


def is_sensitive_key(key: str) -> bool:
    key_lower = key.lower()
    return any(sk in key_lower for sk in SENSITIVE_KEYS)
