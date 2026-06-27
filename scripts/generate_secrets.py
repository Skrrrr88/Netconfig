import secrets
from cryptography.fernet import Fernet

print("=" * 50)
print("  NetConfig - Secret Key Generator")
print("=" * 50)
print()
print("Copy these values into your .env file:")
print()
print(f"SECRET_KEY={secrets.token_hex(32)}")
print(f"FERNET_KEY={Fernet.generate_key().decode()}")
print()
print("=" * 50)
