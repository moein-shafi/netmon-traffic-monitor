# Fix bcrypt Compatibility Issue

The error is due to bcrypt version incompatibility with passlib. Here's how to fix it:

## Solution: Update bcrypt

Run these commands on your server:

```bash
cd /opt/netmon
source env/bin/activate

# Uninstall old bcrypt
pip uninstall -y bcrypt

# Install compatible version
pip install 'bcrypt>=4.0.0'

# Or install latest
pip install --upgrade bcrypt passlib[bcrypt]
```

## Alternative: Use a simpler hashing method

If bcrypt continues to cause issues, we can switch to a different hashing method temporarily.

## After fixing, create admin user:

```bash
cd /opt/netmon
source env/bin/activate
export PYTHONPATH=/opt/netmon

python3 << 'EOF'
from app.auth import load_users, save_users, get_password_hash
from datetime import datetime, timezone
from app.config import CONFIG_DIR
from app.auth import USERS_FILE
import json
import os

# Ensure config directory exists
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Load existing users or create new dict
try:
    users = load_users()
    print(f"Loaded {len(users)} existing users")
except Exception as e:
    print(f"Error loading users: {e}")
    users = {}
    print("Creating new users file")

# Create or update admin user
users["admin"] = {
    "username": "admin",
    "hashed_password": get_password_hash("admin"),
    "role": "admin",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "active": True,
}

# Save users
with USERS_FILE.open("w") as f:
    json.dump(users, f, indent=2)

# Set permissions
os.chmod(USERS_FILE, 0o600)

print("✅ Admin user created successfully!")
print(f"   Username: admin")
print(f"   Password: admin")
print(f"   Users file: {USERS_FILE}")
EOF
```

