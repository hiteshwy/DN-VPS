#!/bin/bash

echo "🚀 DarkNodes Bot Setup"

# Ask for Bot Token
read -p "🔑 Enter your Discord Bot Token: " BOT_TOKEN

# Ask for Admin ID
read -p "🛡️ Enter your Admin Discord ID: " ADMIN_ID

# Make sure v2.py exists
if [ ! -f v2.py ]; then
  echo "❌ v2.py not found in current directory!"
  exit 1
fi

# Replace the TOKEN line
sed -i "s|^TOKEN = ''|TOKEN = '$BOT_TOKEN'|" "v2.py"

# Replace the ADMIN_IDS line
sed -i "s|^ADMIN_IDS = \[.*\]|ADMIN_IDS = [$ADMIN_ID]|" "v2.py"

echo "✅ Configuration complete!"
echo "▶️ Starting DarkNodes bot..."
python3 v2.py
