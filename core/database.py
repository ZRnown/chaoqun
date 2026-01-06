"""
Database manager for storing sessions, messages, and application data
"""
import asyncio
import aiosqlite
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
from loguru import logger
from config import config

class DatabaseManager:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.database.path
        # Ensure database directory exists
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        self.connection: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        """Initialize database and create tables"""
        try:
            # 添加连接参数以更好地处理并发
            self.connection = await aiosqlite.connect(
                self.db_path,
                timeout=30.0,  # 增加超时时间
                isolation_level=None  # 禁用自动事务
            )

            if config.database.enable_wal:
                await self.connection.execute("PRAGMA journal_mode=WAL")
                await self.connection.execute("PRAGMA synchronous=NORMAL")
                await self.connection.execute("PRAGMA wal_autocheckpoint=1000")  # 自动检查点
                await self.connection.execute("PRAGMA busy_timeout=30000")  # 30秒忙等待超时

            await self._create_tables()
            logger.info(f"Database initialized at {self.db_path}")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def _create_tables(self):
        """Create all necessary tables"""
        # Sessions table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT UNIQUE NOT NULL,
                session_string TEXT,
                session_file_path TEXT,
                phone_number TEXT,
                user_name TEXT,
                is_active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                device_info TEXT,
                proxy_config TEXT
            )
        ''')

        # Add user_name column if it doesn't exist (for migration)
        try:
            await self.connection.execute('ALTER TABLE sessions ADD COLUMN user_name TEXT')
        except:
            pass  # Column might already exist

        # Messages table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT NOT NULL,
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                sender_id INTEGER,
                sender_name TEXT,
                message_text TEXT,
                message_type TEXT DEFAULT 'text',
                timestamp TIMESTAMP,
                reply_to_id INTEGER,
                is_outgoing BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(session_name, chat_id, message_id)
            )
        ''')

        # Chats table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_name TEXT NOT NULL,
                chat_id INTEGER UNIQUE NOT NULL,
                chat_title TEXT,
                chat_type TEXT,
                username TEXT,
                last_message_time TIMESTAMP,
                unread_count INTEGER DEFAULT 0,
                is_pinned BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Group-Session mapping table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS group_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                session_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(group_id, session_name)
            )
        ''')

        # Managed groups table - 用户主动管理的群组
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS managed_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER UNIQUE,
                chat_title TEXT NOT NULL,
                chat_type TEXT NOT NULL,
                username TEXT,
                original_link TEXT,
                join_status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Settings table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Message rules table
        await self.connection.execute('''
            CREATE TABLE IF NOT EXISTS message_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                rule_type TEXT NOT NULL, -- 'welcome', 'auto_reply', 'scheduled'
                trigger_condition TEXT, -- JSON string for trigger conditions
                reply_message TEXT NOT NULL,
                sender_sessions TEXT, -- JSON array of session names
                delay_seconds INTEGER DEFAULT 0,
                is_loop BOOLEAN DEFAULT FALSE,
                loop_interval_seconds INTEGER DEFAULT 60,
                is_enabled BOOLEAN DEFAULT TRUE,
                group_id INTEGER, -- Associated group ID, NULL for global rules
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # 程序启动时重置所有session状态为离线（防止程序异常退出后的状态错误）
        await self.connection.execute('UPDATE sessions SET is_active = 0')
        await self.connection.commit()

        await self.connection.commit()

        # 更新恢复的群组信息，为它们设置更好的标题
        await self.update_recovered_group_info()

    async def save_session(self, session_name: str, session_string: str = None,
                          session_file_path: str = None, phone_number: str = None,
                          user_name: str = None, device_info: Dict = None,
                          proxy_config: Dict = None, is_active: bool = None) -> bool:
        """Save session information"""
        try:
            device_json = json.dumps(device_info) if device_info else None
            proxy_json = json.dumps(proxy_config) if proxy_config else None

            await self.connection.execute('''
                INSERT OR REPLACE INTO sessions
                (session_name, session_string, session_file_path, phone_number, user_name,
                 device_info, proxy_config, is_active, last_used)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session_name, session_string, session_file_path, phone_number, user_name,
                  device_json, proxy_json, is_active, datetime.now()))

            await self.connection.commit()
            logger.info(f"Session {session_name} saved to database")
            return True

        except Exception as e:
            logger.error(f"Failed to save session {session_name}: {e}")
            return False

    async def load_session(self, session_name: str) -> Optional[Dict[str, Any]]:
        """Load session information"""
        try:
            cursor = await self.connection.execute('''
                SELECT * FROM sessions WHERE session_name = ?
            ''', (session_name,))

            row = await cursor.fetchone()
            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            session_data = dict(zip(columns, row))

            # Parse JSON fields
            if session_data.get('device_info'):
                session_data['device_info'] = json.loads(session_data['device_info'])
            if session_data.get('proxy_config'):
                session_data['proxy_config'] = json.loads(session_data['proxy_config'])

            return session_data

        except Exception as e:
            logger.error(f"Failed to load session {session_name}: {e}")
            return None

    async def get_all_sessions(self) -> List[Dict[str, Any]]:
        """Get all sessions"""
        if not self.connection:
            logger.warning("Database connection is None, attempting to reinitialize")
            await self.initialize()
            if not self.connection:
                logger.error("Failed to reinitialize database connection")
                return []

        try:
            cursor = await self.connection.execute('SELECT * FROM sessions ORDER BY last_used DESC')
            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            sessions = []
            for row in rows:
                session_data = dict(zip(columns, row))
                # Parse JSON fields
                if session_data.get('device_info'):
                    try:
                        session_data['device_info'] = json.loads(session_data['device_info'])
                    except:
                        session_data['device_info'] = None
                if session_data.get('proxy_config'):
                    try:
                        session_data['proxy_config'] = json.loads(session_data['proxy_config'])
                    except:
                        session_data['proxy_config'] = None
                sessions.append(session_data)

            return sessions

        except Exception as e:
            logger.error(f"Failed to get all sessions: {e}")
            # Try to reinitialize connection and retry once
            try:
                await self.initialize()
                if self.connection:
                    cursor = await self.connection.execute('SELECT * FROM sessions ORDER BY last_used DESC')
                    rows = await cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description]

                    sessions = []
                    for row in rows:
                        session_data = dict(zip(columns, row))
                        if session_data.get('device_info'):
                            try:
                                session_data['device_info'] = json.loads(session_data['device_info'])
                            except:
                                session_data['device_info'] = None
                        if session_data.get('proxy_config'):
                            try:
                                session_data['proxy_config'] = json.loads(session_data['proxy_config'])
                            except:
                                session_data['proxy_config'] = None
                        sessions.append(session_data)

                    return sessions
            except Exception as e2:
                logger.error(f"Failed to retry getting all sessions: {e2}")

            return []

    async def save_message(self, session_name: str, message_data: Dict[str, Any]) -> bool:
        """Save message to database"""
        try:
            await self.connection.execute('''
                INSERT OR REPLACE INTO messages
                (session_name, chat_id, message_id, sender_id, sender_name,
                 message_text, message_type, timestamp, reply_to_id, is_outgoing)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_name,
                message_data.get('chat_id'),
                message_data.get('message_id'),
                message_data.get('sender_id'),
                message_data.get('sender_name'),
                message_data.get('text'),
                message_data.get('type', 'text'),
                message_data.get('timestamp'),
                message_data.get('reply_to_id'),
                message_data.get('is_outgoing', False)
            ))

            await self.connection.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to save message: {e}")
            return False

    async def get_chat_messages(self, session_name: str, chat_id: int,
                               limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get messages for a specific chat"""
        try:
            cursor = await self.connection.execute('''
                SELECT * FROM messages
                WHERE session_name = ? AND chat_id = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            ''', (session_name, chat_id, limit, offset))

            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            messages = []
            for row in rows:
                message_data = dict(zip(columns, row))
                messages.append(message_data)

            return messages

        except Exception as e:
            logger.error(f"Failed to get chat messages: {e}")
            return []

    async def save_chat(self, session_name: str, chat_data: Dict[str, Any]) -> bool:
        """Save chat information"""
        try:
            # 【修正3】确保 chat_title 和 username 不为 None
            chat_id = chat_data.get('chat_id')
            chat_title = chat_data.get('title') or f"未知对话 {chat_id}"  # 提供一个默认标题
            chat_type = chat_data.get('type')
            username = chat_data.get('username') or None

            await self.connection.execute('''
                INSERT OR REPLACE INTO chats
                (session_name, chat_id, chat_title, chat_type, username,
                 last_message_time, unread_count, is_pinned)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_name,
                chat_id,
                chat_title,  # 使用确保非空的标题
                chat_type,
                username,    # username 允许为 None
                chat_data.get('last_message_time'),
                chat_data.get('unread_count', 0),
                chat_data.get('is_pinned', False)
            ))

            await self.connection.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to save chat: {e}")
            return False

    async def get_chats(self, session_name: str) -> List[Dict[str, Any]]:
        """Get all chats for a session"""
        try:
            cursor = await self.connection.execute('''
                SELECT * FROM chats
                WHERE session_name = ?
                ORDER BY is_pinned DESC, last_message_time DESC
            ''', (session_name,))

            rows = await cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            chats = []
            for row in rows:
                chat_data = dict(zip(columns, row))
                chats.append(chat_data)

            return chats

        except Exception as e:
            logger.error(f"Failed to get chats: {e}")
            return []

    async def set_setting(self, key: str, value: Any) -> bool:
        """Set application setting"""
        try:
            value_str = json.dumps(value) if not isinstance(value, str) else value
            await self.connection.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
            ''', (key, value_str, datetime.now()))

            await self.connection.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            return False

    async def add_group_session(self, group_id: int, session_name: str) -> bool:
        """Add a session to a group"""
        try:
            await self.connection.execute('''
                INSERT OR IGNORE INTO group_sessions (group_id, session_name)
                VALUES (?, ?)
            ''', (group_id, session_name))
            await self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add group session: {e}")
            return False

    async def remove_group_session(self, group_id: int, session_name: str) -> bool:
        """Remove a session from a group"""
        try:
            await self.connection.execute('''
                DELETE FROM group_sessions WHERE group_id = ? AND session_name = ?
            ''', (group_id, session_name))
            await self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to remove group session: {e}")
            return False

    async def get_group_sessions(self, group_id: int) -> List[str]:
        """Get all sessions for a group"""
        try:
            cursor = await self.connection.execute('''
                SELECT session_name FROM group_sessions WHERE group_id = ?
            ''', (group_id,))
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get group sessions: {e}")
            return []

    async def get_session_groups(self, session_name: str) -> List[int]:
        """Get all groups for a session"""
        try:
            cursor = await self.connection.execute('''
                SELECT group_id FROM group_sessions WHERE session_name = ?
            ''', (session_name,))
            rows = await cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Failed to get session groups: {e}")
            return []

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Get application setting"""
        try:
            cursor = await self.connection.execute('''
                SELECT value FROM settings WHERE key = ?
            ''', (key,))

            row = await cursor.fetchone()
            if row:
                try:
                    return json.loads(row[0])
                except json.JSONDecodeError:
                    return row[0]
            return default

        except Exception as e:
            logger.error(f"Failed to get setting {key}: {e}")
            return default

    async def get_all_chats(self):
        """获取用户手动添加的群组信息（去重）- 只返回有账号关联的群组"""
        try:
            # 只获取有账号关联的群组（即用户手动添加的群组），按最后消息时间排序
            cursor = await self.connection.execute('''
                SELECT DISTINCT c.chat_id,
                       c.chat_title,
                       c.chat_type,
                       c.username,
                       c.last_message_time
                FROM chats c
                INNER JOIN group_sessions gs ON c.chat_id = gs.group_id
                WHERE c.chat_type IN ('group', 'channel', 'supergroup')
                GROUP BY c.chat_id, c.chat_title, c.chat_type, c.username
                ORDER BY c.last_message_time DESC
            ''')
            rows = await cursor.fetchall()

            chats = []
            for row in rows:
                chats.append({
                    'chat_id': row[0],
                    'title': row[1],
                    'type': row[2],
                    'username': row[3],
                    'last_message_time': row[4]
                })

            return chats
        except Exception as e:
            logger.error(f"Failed to get all chats: {e}")
            return []

    async def save_message_rule(self, rule_data: Dict[str, Any]) -> int:
        """保存消息规则"""
        try:
            await self.connection.execute('''
                INSERT OR REPLACE INTO message_rules
                (id, rule_name, rule_type, trigger_condition, reply_message,
                 sender_sessions, delay_seconds, is_loop, loop_interval_seconds,
                 is_enabled, group_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                rule_data.get('id'),
                rule_data['rule_name'],
                rule_data['rule_type'],
                json.dumps(rule_data.get('trigger_condition', {})),
                rule_data['reply_message'],
                json.dumps(rule_data.get('sender_sessions', [])),
                rule_data.get('delay_seconds', 0),
                rule_data.get('is_loop', False),
                rule_data.get('loop_interval_seconds', 60),
                rule_data.get('is_enabled', True),
                rule_data.get('group_id')
            ))
            await self.connection.commit()

            if rule_data.get('id'):
                return rule_data['id']
            else:
                # 获取新插入的ID
                cursor = await self.connection.execute('SELECT last_insert_rowid()')
                row = await cursor.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Failed to save message rule: {e}")
            return 0

    async def get_message_rules(self, group_id: int = None) -> List[Dict[str, Any]]:
        """获取消息规则"""
        try:
            if group_id is not None:
                cursor = await self.connection.execute('''
                    SELECT * FROM message_rules
                    WHERE group_id = ? OR group_id IS NULL
                    ORDER BY created_at DESC
                ''', (group_id,))
            else:
                cursor = await self.connection.execute('''
                    SELECT * FROM message_rules
                    ORDER BY created_at DESC
                ''')

            rows = await cursor.fetchall()
            rules = []

            for row in rows:
                rule = {
                    'id': row[0],
                    'rule_name': row[1],
                    'rule_type': row[2],
                    'trigger_condition': json.loads(row[3]) if row[3] else {},
                    'reply_message': row[4],
                    'sender_sessions': json.loads(row[5]) if row[5] else [],
                    'delay_seconds': row[6],
                    'is_loop': bool(row[7]),
                    'loop_interval_seconds': row[8],
                    'is_enabled': bool(row[9]),
                    'group_id': row[10],
                    'created_at': row[11],
                    'updated_at': row[12]
                }
                rules.append(rule)

            return rules
        except Exception as e:
            logger.error(f"Failed to get message rules: {e}")
            return []

    async def delete_message_rule(self, rule_id: int) -> bool:
        """删除消息规则"""
        try:
            await self.connection.execute('DELETE FROM message_rules WHERE id = ?', (rule_id,))
            await self.connection.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete message rule: {e}")
            return False

    # ========== 管理群组相关方法 ==========

    async def add_managed_group(self, chat_id: int = None, chat_title: str = None, chat_type: str = None, username: str = None, original_link: str = None, join_status: str = 'pending') -> bool:
        """添加管理群组"""
        try:
            await self.connection.execute('''
                INSERT OR REPLACE INTO managed_groups
                (chat_id, chat_title, chat_type, username, original_link, join_status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (chat_id, chat_title, chat_type, username, original_link, join_status))
            await self.connection.commit()
            logger.info(f"添加管理群组: {chat_title} ({chat_id or '待获取'})")
            return True
        except Exception as e:
            logger.error(f"Failed to add managed group: {e}")
            return False

    async def remove_managed_group(self, chat_id: int) -> bool:
        """移除管理群组"""
        try:
            await self.connection.execute('''
                DELETE FROM managed_groups WHERE chat_id = ?
            ''', (chat_id,))
            await self.connection.commit()
            logger.info(f"移除管理群组: {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove managed group: {e}")
            return False

    async def get_managed_groups(self) -> List[Dict[str, Any]]:
        """获取所有管理的群组"""
        try:
            cursor = await self.connection.execute('''
                SELECT chat_id, chat_title, chat_type, username, original_link, join_status, created_at, updated_at
                FROM managed_groups
                ORDER BY updated_at DESC
            ''')
            rows = await cursor.fetchall()

            groups = []
            for row in rows:
                groups.append({
                    'chat_id': row[0],
                    'title': row[1],
                    'type': row[2],
                    'username': row[3],
                    'original_link': row[4],
                    'join_status': row[5],
                    'created_at': row[6],
                    'updated_at': row[7]
                })
            return groups
        except Exception as e:
            logger.error(f"Failed to get managed groups: {e}")
            return []

    async def is_managed_group(self, chat_id: int) -> bool:
        """检查群组是否被管理"""
        try:
            cursor = await self.connection.execute('''
                SELECT COUNT(*) FROM managed_groups WHERE chat_id = ?
            ''', (chat_id,))
            count = await cursor.fetchone()
            return count[0] > 0
        except Exception as e:
            logger.error(f"Failed to check managed group: {e}")
            return False

    async def update_managed_group_chat_id(self, original_title: str, chat_id: int, title: str = None, username: str = None) -> bool:
        """更新管理群组的chat_id"""
        try:
            update_data = {'chat_id': chat_id, 'join_status': 'joined'}
            if title:
                update_data['chat_title'] = title
            if username is not None:
                update_data['username'] = username

            set_clause = ', '.join([f"{k} = ?" for k in update_data.keys()])
            values = list(update_data.values()) + [original_title]

            await self.connection.execute(f'''
                UPDATE managed_groups
                SET {set_clause}, updated_at = CURRENT_TIMESTAMP
                WHERE chat_title = ? AND (chat_id IS NULL OR chat_id = 0)
            ''', values)
            await self.connection.commit()
            logger.info(f"更新管理群组chat_id: {original_title} -> {chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update managed group chat_id: {e}")
            return False

    async def update_recovered_group_info(self) -> int:
        """更新从group_sessions恢复的群组信息，为它们设置更好的标题"""
        try:
            # 查找所有标题以"群组 "开头的记录，这些是恢复出来的
            cursor = await self.connection.execute('''
                SELECT chat_id, chat_title FROM managed_groups
                WHERE chat_title LIKE '群组 %' AND chat_id IS NOT NULL
            ''')
            rows = await cursor.fetchall()

            updated_count = 0
            for chat_id, current_title in rows:
                try:
                    # 从chats表中查找这个群组是否有更好的信息
                    cursor = await self.connection.execute('''
                        SELECT chat_title, username FROM chats
                        WHERE chat_id = ?
                        ORDER BY last_message_time DESC
                        LIMIT 1
                    ''', (chat_id,))
                    chat_info = await cursor.fetchone()

                    if chat_info and chat_info[0]:
                        new_title = chat_info[0]
                        new_username = chat_info[1]

                        # 如果找到了更好的标题，更新它
                        if new_title != current_title:
                            await self.connection.execute('''
                                UPDATE managed_groups
                                SET chat_title = ?, username = ?, updated_at = CURRENT_TIMESTAMP
                                WHERE chat_id = ?
                            ''', (new_title, new_username, chat_id))
                            updated_count += 1
                            logger.info(f"更新恢复的群组信息: {current_title} -> {new_title}")

                except Exception as e:
                    logger.warning(f"更新群组 {chat_id} 信息失败: {e}")
                    continue

            if updated_count > 0:
                await self.connection.commit()
                logger.info(f"成功更新了 {updated_count} 个恢复群组的信息")

            return updated_count

        except Exception as e:
            logger.error(f"更新恢复群组信息失败: {e}")
            return 0

    async def execute_with_retry(self, query, parameters=None, max_retries=3):
        """Execute SQL query with retry on database lock"""
        for attempt in range(max_retries):
            try:
                if parameters:
                    cursor = await self.connection.execute(query, parameters)
                else:
                    cursor = await self.connection.execute(query)

                await self.connection.commit()
                return cursor
            except Exception as e:
                error_msg = str(e).lower()
                if "database is locked" in error_msg or "database locked" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 0.5  # 递增等待时间
                        logger.warning(f"Database locked, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                # 如果不是锁定错误或重试次数用完，抛出异常
                raise e

    async def close(self):
        """Close database connection"""
        if self.connection:
            try:
                # 确保所有事务都被提交
                await self.connection.commit()
                await self.connection.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
            finally:
                self.connection = None
                logger.info("Database connection closed")

# Global database instance
db_manager = DatabaseManager()

async def init_database():
    """Initialize global database instance"""
    await db_manager.initialize()

async def close_database():
    """Close global database instance"""
    await db_manager.close()
