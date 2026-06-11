#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BotHost Entry Point для монолитного бота
Используется вместо app.py
"""

import subprocess
import sys
import os

print("\n" + "="*70)
print("🤖 IT MARKET BOT - BOTHOST LAUNCHER")
print("="*70 + "\n")

# Установка зависимостей
print("📦 Установка зависимостей...")
try:
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "--upgrade", "pip"
    ])
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "-q",
        "-r", "requirements-install.txt"
    ])
    print("✅ Зависимости установлены\n")
except subprocess.CalledProcessError as e:
    print(f"❌ Ошибка установки: {e}")
    sys.exit(1)

# Проверка переменных
print("🔐 Проверка переменных окружения...")
if not os.getenv('BOT_TOKEN'):
    print("❌ BOT_TOKEN не установлен")
    sys.exit(1)
print("✅ Переменные в порядке\n")

# Запуск бота
print("🚀 Запуск бота...\n")
os.execvp(sys.executable, [sys.executable, "it_market_bot_monolith.py"])
