"""
Telegram client wrapper with integrated session and message management using Telethon
"""
import asyncio
from typing import Dict, List, Optional, Any, Callable
from loguru import logger
from telethon import TelegramClient
from telethon.tl.types import User, Chat
from config import config
from core.session_manager import session_manager
from core.message_handler import message_manager
from core.database import db_manager

class TelegramClientManager:
    """Unified Telegram client manager using Telethon"""

    def __init__(self):
        self.clients: Dict[str, TelegramClient] = {}
        self.message_callbacks: Dict[str, List[Callable]] = {}

    async def initialize(self):
        """Initialize the client manager"""
        logger.info("Initializing Telegram client manager")

        # Load existing sessions from database
        sessions = await db_manager.get_all_sessions()
        for session_data in sessions:
            session_name = session_data['session_name']
            try:
                client = await session_manager.load_session(session_name)
                if client:
                    self.clients[session_name] = client
                    logger.info(f"Loaded existing session: {session_name}")
            except Exception as e:
                logger.error(f"Failed to load session {session_name}: {e}")

    async def create_session(self, session_name: str = None,
                           session_string: str = None,
                           phone_number: str = None,
                           proxy_config: Dict = None) -> Optional[str]:
        """Create new session"""
        try:
            if session_string:
                # Create from string session
                session_name = await session_manager.create_session_from_string(
                    session_string, session_name, phone_number, proxy_config
                )
            else:
                # Create new session
                client = await session_manager.create_new_session(
                    phone_number, session_name, proxy_config
                )
                if client:
                    session_name = session_name or client.name
                    self.clients[session_name] = client

            if session_name:
                logger.info(f"Session created: {session_name}")
            return session_name

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            return None

    async def import_session_file(self, file_path: str, session_name: str = None) -> Optional[str]:
        """Import session from file"""
        try:
            session_name = await session_manager.import_session_file(file_path, session_name)
            if session_name:
                client = await session_manager.load_session(session_name)
                if client:
                    self.clients[session_name] = client
                    logger.info(f"Session imported: {session_name}")
            return session_name

        except Exception as e:
            logger.error(f"Failed to import session file: {e}")
            return None

    async def start_session(self, session_name: str) -> bool:
        """启动会话并自动同步该账号的群组列表"""
        try:
            success = await session_manager.start_session(session_name)
            if success:
                client = session_manager.active_sessions.get(session_name)
                if client:
                    self.clients[session_name] = client
                    # 启动消息监听
                    await message_manager.start_listening(session_name)

                    # 【新增】自动同步该账号的群组到数据库
                    logger.info(f"正在同步会话 {session_name} 的群组列表...")
                    await self.sync_dialogs(session_name)

                    logger.info(f"Session started and listening: {session_name}")
            return success

        except Exception as e:
            logger.error(f"Failed to start session {session_name}: {e}")
            return False

    async def sync_dialogs(self, session_name: str):
        """【核心逻辑】拉取账号的所有群组并保存"""
        client = self.clients.get(session_name)
        if not client:
            return

        try:
            dialogs = await client.get_dialogs(limit=config.telegram.dialogs_limit)  # 使用配置限制

            for d in dialogs:
                chat = d.entity
                chat_id = chat.id
                username = getattr(chat, 'username', None)

                # 【修正1】更健壮地获取聊天标题
                chat_title = None
                chat_type = None

                if d.is_group or d.is_channel:
                    chat_title = getattr(chat, 'title', None)
                    chat_type = 'channel' if d.is_channel else 'group'
                elif d.is_user:
                    # 对于用户，使用他们的名字作为标题，并标记为 'user' 类型
                    chat_title = getattr(chat, 'first_name', None)
                    if getattr(chat, 'last_name', None):
                        chat_title += f" {chat.last_name}"
                    chat_type = 'user'

                # 【修正2】确保 chat_title 不为 None，提供一个默认值
                if not chat_title:
                    if username:
                        chat_title = f"@{username}"
                    else:
                        chat_title = f"未知对话 {chat_id}"

                # 我们主要关注群组和频道，所以只保存这些类型
                if chat_type in ['group', 'channel']:
                    chat_data = {
                        'chat_id': chat_id,
                        'title': chat_title,  # 使用处理后的标题
                        'type': chat_type,
                        'username': username,
                        'last_message_time': d.message.date if d.message else None  # 确保获取最后消息时间
                    }
                    await db_manager.save_chat(session_name, chat_data)

                    # 自动建立 账号<->群组 的关联
                    await db_manager.add_group_session(chat_id, session_name)

            logger.info(f"会话 {session_name} 群组同步完成")
        except Exception as e:
            logger.error(f"同步群组失败: {e}")

    async def stop_session(self, session_name: str) -> bool:
        """Stop a session"""
        try:
            success = await session_manager.stop_session(session_name)
            if success and session_name in self.clients:
                del self.clients[session_name]
                logger.info(f"Session stopped: {session_name}")
            return success

        except Exception as e:
            logger.error(f"Failed to stop session {session_name}: {e}")
            return False

    async def delete_session(self, session_name: str) -> bool:
        """Delete a session"""
        try:
            # Stop first
            await self.stop_session(session_name)

            # Delete from manager
            success = await session_manager.delete_session(session_name)

            if success and session_name in self.clients:
                del self.clients[session_name]

            return success

        except Exception as e:
            logger.error(f"Failed to delete session {session_name}: {e}")
            return False

    async def get_user_info(self, session_name: str) -> Optional[Dict[str, Any]]:
        """Get user information for session"""
        try:
            client = self.clients.get(session_name)
            if not client or not client.is_connected:
                return None

            me = await client.get_me()
            return {
                'id': me.id,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'username': me.username,
                'phone_number': me.phone_number,
                'is_bot': me.is_bot
            }

        except Exception as e:
            logger.error(f"Failed to get user info for {session_name}: {e}")
            return None

    async def get_chats(self, session_name: str, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get chats for session"""
        try:
            if force_refresh:
                # Clear cached chats and refresh - but don't do this here to avoid event loop issues
                # Instead, just get from database
                pass

            return await db_manager.get_chats(session_name)

        except Exception as e:
            logger.error(f"Failed to get chats for {session_name}: {e}")
            return []

    async def send_message(self, session_name: str, chat_id: int, text: str,
                          reply_to_id: Optional[int] = None) -> bool:
        """Send message"""
        try:
            return await message_manager.send_message(session_name, chat_id, text, reply_to_id)

        except Exception as e:
            logger.error(f"Failed to send message from {session_name}: {e}")
            return False

    async def send_photo(self, session_name: str, chat_id: int, photo_path: str,
                        caption: str = None) -> bool:
        """Send photo using Telethon"""
        try:
            client = self.clients.get(session_name)
            if not client or not client.is_connected():
                logger.error(f"Client {session_name} not available")
                return False

            message = await client.send_file(entity=chat_id, file=photo_path, caption=caption)

            # Save to database
            message_data = {
                'chat_id': chat_id,
                'message_id': message.id,
                'sender_id': message.sender_id,
                'sender_name': 'Bot',
                'text': caption or '',
                'type': 'photo',
                'timestamp': message.date,
                'is_outgoing': True
            }
            await db_manager.save_message(session_name, message_data)

            logger.info(f"Photo sent: {session_name} -> {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send photo from {session_name}: {e}")
            return False

    async def send_document(self, session_name: str, chat_id: int, document_path: str,
                           caption: str = None) -> bool:
        """Send document/file using Telethon"""
        try:
            client = self.clients.get(session_name)
            if not client or not client.is_connected():
                logger.error(f"Client {session_name} not available")
                return False

            message = await client.send_file(entity=chat_id, file=document_path, caption=caption, force_document=True)

            # Save to database
            message_data = {
                'chat_id': chat_id,
                'message_id': message.id,
                'sender_id': message.sender_id,
                'sender_name': 'Bot',
                'text': caption or '',
                'type': 'document',
                'timestamp': message.date,
                'is_outgoing': True
            }
            await db_manager.save_message(session_name, message_data)

            logger.info(f"Document sent: {session_name} -> {chat_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send document from {session_name}: {e}")
            return False

    async def broadcast_message(self, session_names: List[str], chat_id: int,
                               text: str, reply_to_id: Optional[int] = None) -> int:
        """Broadcast message to multiple sessions"""
        try:
            return await message_manager.broadcast_message(session_names, chat_id, text, reply_to_id)

        except Exception as e:
            logger.error(f"Failed to broadcast message: {e}")
            return 0

    async def get_chat_history(self, session_name: str, chat_id: int,
                              limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get chat message history"""
        try:
            return await message_manager.get_chat_history(session_name, chat_id, limit, offset)

        except Exception as e:
            logger.error(f"Failed to get chat history for {session_name}: {e}")
            return []

    def add_message_listener(self, session_name: str, callback: Callable):
        """Add message listener"""
        message_manager.add_message_listener(session_name, callback)

    async def export_session_string(self, session_name: str) -> Optional[str]:
        """Export session as string"""
        try:
            return await session_manager.export_session_string(session_name)

        except Exception as e:
            logger.error(f"Failed to export session string for {session_name}: {e}")
            return None

    def get_active_sessions(self) -> List[str]:
        """Get active session names"""
        return list(self.clients.keys())

    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all sessions info"""
        return await session_manager.get_all_sessions()

    def get_session_info(self, session_name: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        return session_manager.get_session_info(session_name)

    async def refresh_session_status(self):
        """Refresh status of all sessions"""
        try:
            sessions = await self.get_all_sessions()
            for session_data in sessions:
                session_name = session_data['session_name']
                is_active = session_data.get('is_active', False)

                client = self.clients.get(session_name)
                if client and client.is_connected:
                    if not is_active:
                        # Update database
                        await db_manager.connection.execute('''
                            UPDATE sessions SET is_active = 1 WHERE session_name = ?
                        ''', (session_name,))
                        await db_manager.connection.commit()
                elif is_active:
                    # Update database
                    await db_manager.connection.execute('''
                        UPDATE sessions SET is_active = 0 WHERE session_name = ?
                    ''', (session_name,))
                    await db_manager.connection.commit()

        except Exception as e:
            logger.error(f"Failed to refresh session status: {e}")

# Global client manager instance
telegram_client = TelegramClientManager()

async def init_telegram_client():
    """Initialize Telegram client manager"""
    await telegram_client.initialize()
    logger.info("Telegram client manager initialized")

async def cleanup_telegram_client():
    """Cleanup Telegram client manager"""
    active_sessions = telegram_client.get_active_sessions()
    for session_name in active_sessions:
        await telegram_client.stop_session(session_name)
    logger.info("Telegram client manager cleaned up")
