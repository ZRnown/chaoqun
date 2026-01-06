#!/usr/bin/env python3
"""
Quick start script for Telegram Desktop Client
"""
import os
import sys
from pathlib import Path

def check_env_file():
    """Check if .env file exists and has required configuration"""
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found!")
        print("Please create a .env file with your Telegram API credentials:")
        print("TELEGRAM_API_ID=your_api_id")
        print("TELEGRAM_API_HASH=your_api_hash")
        print("\nGet these from: https://my.telegram.org/")
        return False

    # Read env file
    with open(env_file, 'r') as f:
        content = f.read()

    if 'your_api_id_here' in content or 'your_api_hash_here' in content:
        print("❌ Please configure your .env file with actual API credentials!")
        print("Current .env file contains placeholder values.")
        return False

    print("✅ .env file configured")
    return True

def check_dependencies():
    """Check if required dependencies are installed"""
    # Map package names to their import names
    required_modules = {
        'PyQt6': 'PyQt6',
        'telethon': 'telethon',
        'qasync': 'qasync',
        'aiosqlite': 'aiosqlite',
        'faker': 'faker',
        'loguru': 'loguru',
        'pydantic': 'pydantic',
        'python-dotenv': 'dotenv'
    }

    missing = []
    for package, module in required_modules.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)

    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("Run: pip install -r requirements.txt")
        return False

    print("✅ All dependencies installed")
    return True

def main():
    """Main startup function"""
    print("🚀 Starting Telegram Desktop Client v2.0")
    print("=" * 50)

    # Check environment
    if not check_env_file():
        return 1

    if not check_dependencies():
        return 1

    print("\n🎯 Starting application...")
    print("Note: First run may take longer to download required files")
    print("Close the application with Ctrl+C if needed\n")

    # Import and run main application
    try:
        # 直接运行 main.py 模块（它会在 if __name__ == "__main__" 块中启动）
        import subprocess
        import sys
        result = subprocess.run([sys.executable, "main.py"], cwd=".")
        return result.returncode
    except KeyboardInterrupt:
        print("\n👋 Application interrupted by user")
        return 0
    except Exception as e:
        print(f"❌ Failed to start application: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
