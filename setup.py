#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BotHost setup script - runs once during deployment
"""

import subprocess
import sys

print("\n" + "="*50)
print("🔧 BotHost Setup Script")
print("="*50 + "\n")

print("📦 Installing Python dependencies...")
subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "pip"])
subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

print("\n✅ Setup completed successfully!")
print("\nYou can now start the bot with: python3 app.py")
print("\n" + "="*50 + "\n")
