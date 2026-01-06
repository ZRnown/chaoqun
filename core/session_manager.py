"""
Session manager for handling Telegram sessions (string and file-based) using Telethon
"""
import os
import asyncio
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from faker import Faker
from loguru import logger
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import config
from core.database import db_manager
from core.proxy_manager import proxy_manager, ProxyInfo

class SessionManager:
    def __init__(self):
        self.active_sessions: Dict[str, TelegramClient] = {}
        self.fake = Faker()
        self.session_dir = Path("data/sessions")
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def generate_device_info(self) -> Dict[str, str]:
        """Generate random device information for anti-detection"""
        if not config.device.randomize_device:
            return {
                'device_model': 'Telegram Desktop',
                'system_version': 'Windows 10',
                'app_version': '4.0.0'
            }

        return {
            'device_model': self.fake.random_element(config.device.device_models),
            'system_version': self.fake.random_element(config.device.system_versions),
            'app_version': self.fake.random_element(config.device.app_versions)
        }

    def generate_session_name(self, prefix: str = "session") -> str:
        """Generate a unique session name"""
        import uuid
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    async def create_session_from_string(self, session_string: str,
                                       session_name: str = None,
                                       phone_number: str = None,
                                       proxy_config: Dict = None) -> Optional[str]:
        """Create session from string session using Telethon"""
        try:
            # Basic validation of session string
            if not session_string or not isinstance(session_string, str):
                raise ValueError("字符串会话为空或无效")

            # Remove any whitespace
            session_string = session_string.strip()

            # Check minimum length
            if len(session_string) < 100:
                raise ValueError("字符串会话长度太短，可能不完整")

            if not session_name:
                session_name = self.generate_session_name()

            device_info = self.generate_device_info()

            # Create Telethon client with string session
            session = StringSession(session_string)
            client = TelegramClient(
                session=session,
                api_id=config.telegram.api_id,
                api_hash=config.telegram.api_hash
            )

            # Add proxy if specified
            if proxy_config:
                proxy = ProxyInfo(**proxy_config)
                # Telethon proxy format is different
                client.set_proxy(proxy.to_dict())

            # Test connection
            await client.start()
            me = await client.get_me()

            # Convert back to string for storage
            session_string = client.session.save()

            # Get user display name
            user_name = me.first_name
            if me.last_name:
                user_name += f" {me.last_name}"
            if me.username:
                user_name += f" (@{me.username})"

            # Save to database
            await db_manager.save_session(
                session_name=session_name,
                session_string=session_string,
                phone_number=phone_number or me.phone,
                user_name=user_name,
                device_info=device_info,
                proxy_config=proxy_config
            )

            await client.disconnect()
            logger.info(f"Session {session_name} created and saved from string")
            return session_name

        except ValueError as e:
            logger.error(f"Session string validation error: {e}")
            raise e
        except Exception as e:
            logger.error(f"Failed to create session from string: {e}")
            if "auth" in str(e).lower() or "authorization" in str(e).lower():
                raise ValueError("字符串会话已过期或无效。请重新登录获取新的会话。")
            else:
                raise ValueError(f"字符串会话验证失败: {str(e)}")

    async def import_session_file(self, file_path: str,
                                session_name: str = None) -> Optional[str]:
        """Import session from .session file"""
        try:
            file_path = Path(file_path)
            if not file_path.exists():
                raise FileNotFoundError(f"Session file not found: {file_path}")

            if not session_name:
                session_name = file_path.stem

            # Copy file to sessions directory
            dest_path = self.session_dir / f"{session_name}.session"
            import shutil
            shutil.copy2(file_path, dest_path)

            device_info = self.generate_device_info()

            # Create client to verify session
            client = TelegramClient(
                name=session_name,
                api_id=config.telegram.api_id,
                api_hash=config.telegram.api_hash,
                device_model=device_info['device_model'],
                system_version=device_info['system_version'],
                app_version=device_info['app_version'],
                workdir=str(self.session_dir)
            )

            await client.start()
            me = await client.get_me()
            phone_number = me.phone

            # Get user display name
            user_name = me.first_name
            if me.last_name:
                user_name += f" {me.last_name}"
            if me.username:
                user_name += f" (@{me.username})"

            # Save to database
            await db_manager.save_session(
                session_name=session_name,
                session_file_path=str(dest_path),
                phone_number=phone_number,
                user_name=user_name,
                device_info=device_info
            )

            await client.disconnect()
            logger.info(f"Session {session_name} imported from file: {file_path}")
            return session_name

        except Exception as e:
            logger.error(f"Failed to import session file: {e}")
            return None

    async def create_new_session(self, phone_number: str = None,
                               session_name: str = None,
                               proxy_config: Dict = None) -> Optional[TelegramClient]:
        """Create new session with phone login"""
        try:
            if not session_name:
                session_name = self.generate_session_name()

            device_info = self.generate_device_info()

            client = TelegramClient(
                session=StringSession(),
                api_id=config.telegram.api_id,
                api_hash=config.telegram.api_hash
            )

            # Add proxy if specified or get from proxy manager
            if proxy_config:
                proxy = ProxyInfo(**proxy_config)
                client.proxy = proxy.to_dict()
            elif proxy_manager.proxies:
                proxy = proxy_manager.get_proxy_for_session(session_name)
                if proxy:
                    client.proxy = proxy.to_dict()

            # Save initial session info
            await db_manager.save_session(
                session_name=session_name,
                phone_number=phone_number,
                device_info=device_info,
                proxy_config=proxy_config
            )

            self.active_sessions[session_name] = client
            logger.info(f"New session {session_name} created")
            return client

        except Exception as e:
            logger.error(f"Failed to create new session: {e}")
            return None

    async def load_session(self, session_name: str) -> Optional[TelegramClient]:
        """Load existing session using Telethon"""
        try:
            # Check if already active
            if session_name in self.active_sessions:
                return self.active_sessions[session_name]

            # Load from database
            session_data = await db_manager.load_session(session_name)
            if not session_data:
                logger.error(f"Session {session_name} not found in database")
                return None

            # Create Telethon client
            if session_data.get('session_string'):
                session = StringSession(session_data['session_string'])
            elif session_data.get('session_file_path'):
                # Use file-based session
                session = session_data['session_file_path']
            else:
                # Create new session if no string or file available
                session = StringSession()

            client = TelegramClient(
                session=session,
                api_id=config.telegram.api_id,
                api_hash=config.telegram.api_hash
            )

            # Add proxy if configured
            proxy_config = session_data.get('proxy_config')
            if proxy_config:
                proxy = ProxyInfo(**proxy_config)
                client.set_proxy(proxy.to_dict())
            elif proxy_manager.proxies:
                proxy = proxy_manager.get_proxy_for_session(session_name)
                if proxy:
                    client.set_proxy(proxy.to_dict())

            self.active_sessions[session_name] = client
            logger.info(f"Session {session_name} loaded")
            return client

        except Exception as e:
            logger.error(f"Failed to load session {session_name}: {e}")
            return None

    async def start_session(self, session_name: str) -> bool:
        """Start a session"""
        try:
            client = await self.load_session(session_name)
            if not client:
                return False

            await client.start()

            # Update last used time and active status
            try:
                await db_manager.execute_with_retry('''
                    UPDATE sessions SET last_used = ?, is_active = 1
                    WHERE session_name = ?
                ''', (asyncio.get_event_loop().time(), session_name))
                logger.debug(f"Database updated for session {session_name}")
            except Exception as e:
                logger.warning(f"Failed to update database for session {session_name}: {e}")
                # 即使数据库更新失败，session 也已经启动了
                return True

            logger.info(f"Session {session_name} started")
            return True

        except Exception as e:
            logger.error(f"Failed to start session {session_name}: {e}")
            return False

    async def stop_session(self, session_name: str) -> bool:
        """Stop a session"""
        try:
            if session_name in self.active_sessions:
                client = self.active_sessions[session_name]

                # 安全地断开连接，避免事件循环已关闭的错误
                try:
                    if not client.is_connected():
                        logger.debug(f"Client {session_name} already disconnected")
                    else:
                        await client.disconnect()
                except Exception as e:
                    if "closed" in str(e).lower() or "loop" in str(e).lower():
                        logger.debug(f"Client {session_name} disconnect skipped (event loop closed)")
                    else:
                        logger.warning(f"Error disconnecting client {session_name}: {e}")

                # 更新数据库状态，使用重试机制
                try:
                    await db_manager.execute_with_retry('''
                        UPDATE sessions SET is_active = 0 WHERE session_name = ?
                    ''', (session_name,))
                    logger.debug(f"Database updated for session {session_name}")
                except Exception as e:
                    if "closed" in str(e).lower() or "loop" in str(e).lower():
                        logger.debug(f"Database update skipped for {session_name} (event loop closed)")
                    else:
                        logger.warning(f"Error updating database for session {session_name}: {e}")

                # 清理会话引用
                del self.active_sessions[session_name]
                logger.info(f"Session {session_name} stopped")
                return True

            return False

        except Exception as e:
            logger.error(f"Failed to stop session {session_name}: {e}")
            return False

    async def delete_session(self, session_name: str) -> bool:
        """Delete a session completely"""
        try:
            # Stop if active
            await self.stop_session(session_name)

            # Remove from database
            await db_manager.connection.execute('''
                DELETE FROM sessions WHERE session_name = ?
            ''', (session_name,))
            await db_manager.connection.commit()

            # Remove session files
            session_file = self.session_dir / f"{session_name}.session"
            if session_file.exists():
                session_file.unlink()

            logger.info(f"Session {session_name} deleted")
            return True

        except Exception as e:
            logger.error(f"Failed to delete session {session_name}: {e}")
            return False

    async def get_active_sessions(self) -> List[str]:
        """Get list of active session names"""
        return list(self.active_sessions.keys())

    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all sessions info"""
        return await db_manager.get_all_sessions()

    async def export_session_string(self, session_name: str) -> Optional[str]:
        """Export session as string using Telethon"""
        try:
            client = self.active_sessions.get(session_name)
            if not client:
                client = await self.load_session(session_name)
                if not client:
                    return None
                await client.start()

            # Telethon session string
            session_string = client.session.save()

            # Save to database
            await db_manager.connection.execute('''
                UPDATE sessions SET session_string = ? WHERE session_name = ?
            ''', (session_string, session_name))
            await db_manager.connection.commit()

            if session_name not in self.active_sessions:
                await client.disconnect()

            logger.info(f"Session {session_name} exported as string")
            return session_string

        except Exception as e:
            logger.error(f"Failed to export session string for {session_name}: {e}")
            return None

    def get_session_info(self, session_name: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        # This is a synchronous version for UI calls
        # In real implementation, this should be async
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(db_manager.load_session(session_name))
            loop.close()
            return result
        except Exception as e:
            logger.error(f"Failed to get session info for {session_name}: {e}")
            return None

# Global session manager instance
session_manager = SessionManager()

async def init_session_manager():
    """Initialize session manager"""
    logger.info("Session manager initialized")

async def cleanup_sessions():
    """Cleanup all active sessions"""
    active_sessions = list(session_manager.active_sessions.keys())
    for session_name in active_sessions:
        await session_manager.stop_session(session_name)
    logger.info("All sessions cleaned up")
