"""
Configuration management for Telegram Desktop Client
"""
import os
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class TelegramConfig(BaseModel):
    """Telegram API configuration"""
    api_id: int = Field(default_factory=lambda: int(os.getenv('TELEGRAM_API_ID', '0')))
    api_hash: str = Field(default_factory=lambda: os.getenv('TELEGRAM_API_HASH', ''))
    dialogs_limit: int = 100  # 【新增配置】同步对话的限制数量

class DatabaseConfig(BaseModel):
    """Database configuration"""
    path: str = "data/telegram_client.db"
    enable_wal: bool = True

class ProxyConfig(BaseModel):
    """Proxy configuration for IP isolation"""
    enabled: bool = False
    type: str = "socks5"  # socks5, http, mtproto
    hostname: str = "127.0.0.1"
    port: int = 1080
    username: str = ""
    password: str = ""

class FloodControlConfig(BaseModel):
    """Flood control configuration"""
    max_concurrent_messages: int = 5
    message_delay: float = 1.0  # seconds between messages
    flood_wait_multiplier: float = 1.5  # multiply wait time by this factor

class DeviceConfig(BaseModel):
    """Device simulation configuration"""
    randomize_device: bool = True
    device_models: List[str] = [
        "Samsung Galaxy S23", "iPhone 14 Pro", "Google Pixel 7",
        "OnePlus 11", "Xiaomi 13", "Huawei P50", "Sony Xperia 1 IV"
    ]
    system_versions: List[str] = [
        "Android 13", "iOS 16.5", "Android 12", "iOS 15.7"
    ]
    app_versions: List[str] = [
        "10.5.0", "10.4.2", "10.3.1", "10.2.0"
    ]

class AppConfig(BaseModel):
    """Main application configuration"""
    telegram: TelegramConfig
    database: DatabaseConfig
    proxy: ProxyConfig
    flood_control: FloodControlConfig
    device: DeviceConfig

    window_width: int = 1200
    window_height: int = 800
    max_sessions: int = 10
    log_level: str = "INFO"

# Global config instance
config = AppConfig(
    telegram=TelegramConfig(),
    database=DatabaseConfig(),
    proxy=ProxyConfig(),
    flood_control=FloodControlConfig(),
    device=DeviceConfig()
)

def load_config_from_env() -> AppConfig:
    """Load configuration from environment variables"""
    return AppConfig(
        telegram=TelegramConfig(
            api_id=int(os.getenv('TELEGRAM_API_ID', '0')),
            api_hash=os.getenv('TELEGRAM_API_HASH', '')
        )
    )

def validate_config() -> bool:
    """Validate configuration"""
    if not config.telegram.api_id or config.telegram.api_id == 0:
        print("Error: TELEGRAM_API_ID not set. Please set it in .env file or environment.")
        return False
    if not config.telegram.api_hash:
        print("Error: TELEGRAM_API_HASH not set. Please set it in .env file or environment.")
        return False
    return True
