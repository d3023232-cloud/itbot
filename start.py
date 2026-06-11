#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BotHost Entry Point - Install dependencies before starting bot
"""

import subprocess
import sys
import os

print("🚀 BotHost Entry Point Initializer")
print("==================================\n")

# Install requirements
print("📦 Installing dependencies...")
subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
print("✅ Dependencies installed\n")

# Import and run app
print("🤖 Starting IT Market Bot...\n")
os.execvp(sys.executable, [sys.executable, "app.py"])
