"""
Proxy manager for IP isolation and anti-detection
"""
import random
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from loguru import logger
from config import config

@dataclass
class ProxyInfo:
    """Proxy configuration information"""
    type: str  # socks5, http, mtproto
    hostname: str
    port: int
    username: str = ""
    password: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Pyrogram"""
        proxy_dict = {
            "hostname": self.hostname,
            "port": self.port
        }

        if self.username:
            proxy_dict["username"] = self.username
        if self.password:
            proxy_dict["password"] = self.password

        return proxy_dict

    def to_mtproto_dict(self) -> Dict[str, Any]:
        """Convert to MTProto proxy format"""
        return {
            "scheme": self.type,
            "hostname": self.hostname,
            "port": self.port,
            "secret": getattr(self, 'secret', '')
        }

class ProxyManager:
    def __init__(self):
        self.proxies: List[ProxyInfo] = []
        self.current_index = 0

    def add_proxy(self, proxy: ProxyInfo):
        """Add a proxy to the pool"""
        self.proxies.append(proxy)
        logger.info(f"Added proxy: {proxy.hostname}:{proxy.port}")

    def add_proxy_from_dict(self, proxy_dict: Dict[str, Any]):
        """Add proxy from dictionary configuration"""
        proxy = ProxyInfo(
            type=proxy_dict.get('type', 'socks5'),
            hostname=proxy_dict['hostname'],
            port=proxy_dict['port'],
            username=proxy_dict.get('username', ''),
            password=proxy_dict.get('password', '')
        )
        self.add_proxy(proxy)

    def load_proxies_from_config(self):
        """Load proxies from configuration"""
        if config.proxy.enabled:
            self.add_proxy_from_dict({
                'type': config.proxy.type,
                'hostname': config.proxy.hostname,
                'port': config.proxy.port,
                'username': config.proxy.username,
                'password': config.proxy.password
            })

    def get_next_proxy(self) -> Optional[ProxyInfo]:
        """Get next proxy in round-robin fashion"""
        if not self.proxies:
            return None

        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy

    def get_random_proxy(self) -> Optional[ProxyInfo]:
        """Get random proxy from pool"""
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def get_proxy_for_session(self, session_name: str) -> Optional[ProxyInfo]:
        """Get proxy for specific session (can be customized per session)"""
        # For now, use round-robin. Can be extended to assign specific proxies to sessions
        return self.get_next_proxy()

    def get_proxy_pool_info(self) -> Dict[str, Any]:
        """Get information about proxy pool"""
        return {
            'total_proxies': len(self.proxies),
            'current_index': self.current_index,
            'proxies': [
                {
                    'type': p.type,
                    'hostname': p.hostname,
                    'port': p.port,
                    'has_auth': bool(p.username or p.password)
                }
                for p in self.proxies
            ]
        }

    def clear_proxies(self):
        """Clear all proxies"""
        self.proxies.clear()
        self.current_index = 0
        logger.info("Cleared all proxies")

class ProxyRotator:
    """Advanced proxy rotation with health checking"""

    def __init__(self, proxy_manager: ProxyManager):
        self.proxy_manager = proxy_manager
        self.failed_proxies: List[ProxyInfo] = []
        self.health_check_interval = 300  # 5 minutes

    async def get_healthy_proxy(self) -> Optional[ProxyInfo]:
        """Get a healthy proxy, rotating through available ones"""
        max_attempts = len(self.proxy_manager.proxies)
        attempts = 0

        while attempts < max_attempts:
            proxy = self.proxy_manager.get_next_proxy()
            if not proxy:
                return None

            # Skip recently failed proxies
            if proxy in self.failed_proxies:
                attempts += 1
                continue

            # In a real implementation, you would ping the proxy here
            # For now, assume all proxies are healthy
            return proxy

        return None

    def mark_proxy_failed(self, proxy: ProxyInfo):
        """Mark proxy as failed"""
        if proxy not in self.failed_proxies:
            self.failed_proxies.append(proxy)
            logger.warning(f"Marked proxy as failed: {proxy.hostname}:{proxy.port}")

    def mark_proxy_healthy(self, proxy: ProxyInfo):
        """Mark proxy as healthy again"""
        if proxy in self.failed_proxies:
            self.failed_proxies.remove(proxy)
            logger.info(f"Marked proxy as healthy: {proxy.hostname}:{proxy.port}")

# Global proxy manager instance
proxy_manager = ProxyManager()
proxy_rotator = ProxyRotator(proxy_manager)

def init_proxy_manager():
    """Initialize proxy manager with configuration"""
    proxy_manager.load_proxies_from_config()
    logger.info(f"Proxy manager initialized with {len(proxy_manager.proxies)} proxies")

# Utility functions for proxy testing
async def test_proxy(proxy: ProxyInfo) -> bool:
    """Test if proxy is working"""
    try:
        import aiohttp
        import asyncio

        timeout = aiohttp.ClientTimeout(total=10)
        connector = aiohttp.TCPConnector()

        if proxy.type == 'socks5':
            # For socks5 proxies, we would need aiohttp-socks or similar
            # For now, just return True as a placeholder
            return True
        elif proxy.type == 'http':
            proxy_url = f"http://{proxy.hostname}:{proxy.port}"
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get('https://api.telegram.org', proxy=proxy_url) as response:
                    return response.status == 200

        return True

    except Exception as e:
        logger.error(f"Proxy test failed for {proxy.hostname}:{proxy.port}: {e}")
        return False
