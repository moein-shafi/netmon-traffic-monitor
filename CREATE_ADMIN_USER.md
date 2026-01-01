# Create Admin User - Troubleshooting

If you're getting "Invalid credentials", the users file might not exist or the default admin wasn't created.

## Option 1: Check if users file exists

```bash
# Check if users file exists
ls -la /var/netmon/config/users.json

# If it doesn't exist, we need to create it
```

## Option 2: Create admin user via Python script

Run this on your server:

```bash
cd /opt/netmon
source env/bin/activate
export PYTHONPATH=/opt/netmon

python3 << 'EOF'
from app.auth import load_users, save_users, get_password_hash
from datetime import datetime, timezone
import json

# Load or create users
users = load_users()

# Create or update admin user
users["admin"] = {
    "username": "admin",
    "hashed_password": get_password_hash("admin"),
    "role": "admin",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "active": True,
}

# Save users
from app.auth import USERS_FILE, CONFIG_DIR
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
with USERS_FILE.open("w") as f:
    json.dump(users, f, indent=2)

print("Admin user created!")
print(f"Username: admin")
print(f"Password: admin")
print(f"Users file: {USERS_FILE}")
EOF
```

## Option 3: Create users file manually

```bash
# Create the config directory
sudo mkdir -p /var/netmon/config

# Create users.json with admin user
sudo tee /var/netmon/config/users.json > /dev/null << 'EOF'
{
  "admin": {
    "username": "admin",
    "hashed_password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyY5Y5Y5Y5Y5Y",
    "role": "admin",
    "created_at": "2026-01-01T00:00:00+00:00",
    "active": true
  }
}
EOF

# Set permissions
sudo chmod 600 /var/netmon/config/users.json
```

**Note:** The hash above is just a placeholder. Use Option 2 to generate the correct hash.

## Option 4: Test authentication directly

```bash
cd /opt/netmon
source env/bin/activate
export PYTHONPATH=/opt/netmon

python3 << 'EOF'
from app.auth import authenticate_user, load_users

# Check what users exist
users = load_users()
print("Users:", list(users.keys()))

# Test authentication
result = authenticate_user("admin", "admin")
if result:
    print("Authentication successful!")
    print("User:", result)
else:
    print("Authentication failed!")
    print("Available users:", users)
EOF
```

## Option 5: Reset password via API (if you have another way in)

If you can access the API directly, you might be able to create a user via the API endpoint (though this might require authentication).

## Most Likely Solution

Run Option 2 - it will create the users file with the correct password hash.

