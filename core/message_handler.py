"""
Message handler with flood control and queue management using Telethon
"""
import asyncio
import json
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import time
from loguru import logger
from telethon import TelegramClient, events
from telethon.tl.types import Message
from telethon.errors import FloodWaitError
from config import config
from core.database import db_manager

@dataclass
class MessageTask:
    """Message sending task"""
    session_name: str
    chat_id: int
    text: str
    reply_to_id: Optional[int] = None
    created_at: float = field(default_factory=time.time)
    retry_count: int = 0
    max_retries: int = 3

@dataclass
class FloodControl:
    """Flood control for each session"""
    last_message_time: float = 0
    message_count: int = 0
    flood_wait_until: float = 0

class MessageQueue:
    """Message sending queue with flood control and concurrent processing"""

    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self.flood_controls: Dict[str, FloodControl] = {}
        self.processing = False
        self.workers: List[asyncio.Task] = []
        self.concurrent_mode = True  # 是否启用并发模式
        self.max_concurrent_tasks = 5  # 最大并发任务数
        self.active_tasks: set = set()  # 当前活跃的任务

    async def start(self, num_workers: int = 3):
        """Start message processing workers"""
        self.processing = True
        if self.concurrent_mode:
            # 并发模式：启动多个并发工作者
            for i in range(num_workers):
                worker = asyncio.create_task(self._process_queue_concurrent())
                self.workers.append(worker)
            logger.info(f"Started {num_workers} concurrent message queue workers")
        else:
            # 串行模式：启动单个工作者
            for i in range(num_workers):
                worker = asyncio.create_task(self._process_queue())
                self.workers.append(worker)
            logger.info(f"Started {num_workers} serial message queue workers")

    async def stop(self):
        """Stop message processing"""
        self.processing = False

        # Wait for active tasks to complete
        if self.active_tasks:
            logger.info(f"Waiting for {len(self.active_tasks)} active tasks to complete...")
            await asyncio.gather(*self.active_tasks, return_exceptions=True)
            self.active_tasks.clear()

        # Clear queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Cancel workers
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        logger.info("Message queue stopped")

    async def add_message(self, task: MessageTask):
        """Add message to queue"""
        await self.queue.put(task)
        logger.debug(f"Added message task to queue: {task.session_name} -> {task.chat_id}")

    def get_flood_control(self, session_name: str) -> FloodControl:
        """Get or create flood control for session"""
        if session_name not in self.flood_controls:
            self.flood_controls[session_name] = FloodControl()
        return self.flood_controls[session_name]

    async def _process_queue(self):
        """Process messages from queue (serial mode)"""
        while self.processing:
            try:
                # Get task with timeout
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                await self._send_message(task)
                self.queue.task_done()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing message queue: {e}")

    async def _process_queue_concurrent(self):
        """Process messages from queue (concurrent mode)"""
        semaphore = asyncio.Semaphore(self.max_concurrent_tasks)

        while self.processing:
            try:
                # Get task with timeout
                task = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # Create concurrent task
                async def send_with_semaphore(task):
                    async with semaphore:
                        try:
                            await self._send_message(task)
                        finally:
                            self.queue.task_done()

                # Start concurrent task
                concurrent_task = asyncio.create_task(send_with_semaphore(task))
                self.active_tasks.add(concurrent_task)

                # Clean up completed tasks
                self.active_tasks = {task for task in self.active_tasks if not task.done()}

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing concurrent message queue: {e}")

    async def _send_message(self, task: MessageTask):
        """Send message with flood control"""
        from core.session_manager import session_manager

        try:
            # Get flood control
            flood_control = self.get_flood_control(task.session_name)

            # Check if we're in flood wait
            current_time = time.time()
            if current_time < flood_control.flood_wait_until:
                wait_time = flood_control.flood_wait_until - current_time
                logger.warning(f"Flood wait active for {task.session_name}, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)

            # Apply rate limiting
            time_since_last = current_time - flood_control.last_message_time
            if time_since_last < config.flood_control.message_delay:
                await asyncio.sleep(config.flood_control.message_delay - time_since_last)

            # Get client
            client = session_manager.active_sessions.get(task.session_name)
            if not client or not client.is_connected:
                logger.error(f"Client {task.session_name} not available")
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    await asyncio.sleep(2 ** task.retry_count)  # Exponential backoff
                    await self.queue.put(task)
                return

            # Send message
            try:
                message = await client.send_message(
                    entity=task.chat_id,
                    message=task.text,
                    reply_to=task.reply_to_id
                )

                # Update flood control
                flood_control.last_message_time = time.time()
                flood_control.message_count += 1

                # Save to database
                message_data = {
                    'chat_id': task.chat_id,
                    'message_id': message.id,
                    'sender_id': message.from_user.id if message.from_user else None,
                    'sender_name': message.from_user.first_name if message.from_user else 'Bot',
                    'text': task.text,
                    'type': 'text',
                    'timestamp': message.date,
                    'reply_to_id': task.reply_to_id,
                    'is_outgoing': True
                }
                await db_manager.save_message(task.session_name, message_data)

                logger.info(f"Message sent: {task.session_name} -> {task.chat_id}")

            except FloodWaitError as e:
                # Handle flood wait
                wait_time = e.value * config.flood_control.flood_wait_multiplier
                flood_control.flood_wait_until = time.time() + wait_time
                logger.warning(f"Flood wait for {task.session_name}: {wait_time}s")

                # Retry after wait
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    await asyncio.sleep(wait_time + 1)
                    await self.queue.put(task)
                else:
                    logger.error(f"Max retries exceeded for message: {task.session_name}")

            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    await asyncio.sleep(2 ** task.retry_count)
                    await self.queue.put(task)

        except Exception as e:
            logger.error(f"Error in message sending: {e}")

class MessageListener:
    """Message listener and handler"""

    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = {}
        self.running = False

    def add_listener(self, session_name: str, callback: Callable):
        """Add message listener for session"""
        if session_name not in self.listeners:
            self.listeners[session_name] = []
        self.listeners[session_name].append(callback)
        logger.info(f"Added message listener for {session_name}")

    def remove_listener(self, session_name: str, callback: Callable):
        """Remove message listener"""
        if session_name in self.listeners:
            try:
                self.listeners[session_name].remove(callback)
                logger.info(f"Removed message listener for {session_name}")
            except ValueError:
                pass

    async def start_listening(self, session_name: str):
        """Start listening for messages on a session"""
        from core.session_manager import session_manager

        client = session_manager.active_sessions.get(session_name)
        if not client:
            logger.error(f"Client {session_name} not available for listening")
            return

        @client.on(events.NewMessage)
        async def handle_message(event):
            try:
                message = event.message

                # Save message to database
                message_data = {
                    'chat_id': message.chat_id,
                    'message_id': message.id,
                    'sender_id': message.sender_id,
                    'sender_name': getattr(message.sender, 'first_name', 'Unknown') if message.sender else 'Unknown',
                    'text': message.text or getattr(message, 'caption', '') or '',
                    'type': self._get_message_type(message),
                    'timestamp': message.date,
                    'reply_to_id': getattr(message, 'reply_to_msg_id', None),
                    'is_outgoing': message.from_id == (await client.get_me()).id if message.from_id else False
                }
                await db_manager.save_message(session_name, message_data)

                # Update chat info
                chat = await message.get_chat()
                chat_data = {
                    'chat_id': message.chat_id,
                    'title': getattr(chat, 'title', None),
                    'type': type(chat).__name__.lower(),
                    'username': getattr(chat, 'username', None),
                    'last_message_time': message.date,
                    'unread_count': 0
                }
                await db_manager.save_chat(session_name, chat_data)

                # Check and execute rules (delegate to manager if available)
                if hasattr(self, '_check_and_execute_rules'):
                    await self._check_and_execute_rules(session_name, message, chat)

                # Notify listeners
                if session_name in self.listeners:
                    for callback in self.listeners[session_name]:
                        try:
                            await callback(session_name, message)
                        except Exception as e:
                            logger.error(f"Error in message listener callback: {e}")

            except Exception as e:
                logger.error(f"Error handling message: {e}")

        logger.info(f"Started message listening for {session_name}")

    def _get_message_type(self, message) -> str:
        """Get message type using Telethon"""
        if message.text:
            return 'text'
        elif message.photo:
            return 'photo'
        elif message.video:
            return 'video'
        elif message.document:
            return 'document'
        elif message.audio:
            return 'audio'
        elif message.voice:
            return 'voice'
        elif message.sticker:
            return 'sticker'
        elif message.gif:
            return 'animation'
        else:
            return 'unknown'

    async def _check_and_execute_rules(self, session_name: str, message: Message, chat):
        """检查并执行匹配的规则"""
        try:
            # 获取适用于此群组的规则
            rules = await db_manager.get_message_rules(message.chat_id)

            for rule in rules:
                if not rule.get('is_enabled', True):
                    continue

                if self._rule_matches(rule, message, chat):
                    # 延迟执行
                    delay = rule.get('delay_seconds', 0)
                    if delay > 0:
                        await asyncio.sleep(delay)

                    # 执行规则
                    await self._execute_rule(session_name, rule, message.chat_id)

                    # 如果不是循环规则，执行一次后退出
                    if not rule.get('is_loop', False):
                        break

        except Exception as e:
            logger.error(f"Error checking rules for message {message.id}: {e}")

    def _rule_matches(self, rule: Dict[str, Any], message: Message, chat) -> bool:
        """检查规则是否匹配当前消息"""
        rule_type = rule.get('rule_type', '')

        if rule_type == 'auto_reply':
            # 自动回复：匹配关键词时触发
            trigger_condition = rule.get('trigger_condition', {})
            keywords = trigger_condition.get('keywords', [])

            if not keywords:
                return False

            message_text = (message.text or '').lower()
            return any(keyword.lower() in message_text for keyword in keywords)

        elif rule_type == 'scheduled':
            # 定时发送：由调度器触发，不在这里匹配
            return False

        return False

    async def _execute_rule(self, session_name: str, rule: Dict[str, Any], chat_id: int):
        """执行规则"""
        try:
            reply_message = rule.get('reply_message', '')
            sender_sessions = rule.get('sender_sessions', [])

            if not reply_message or not sender_sessions:
                return

            # 随机选择一个发送者
            import random
            selected_session = random.choice(sender_sessions)

            # 检查发送者是否可用
            from core.telegram_client import telegram_client
            if selected_session not in telegram_client.clients:
                logger.warning(f"Rule sender {selected_session} not available")
                return

            client = telegram_client.clients[selected_session]
            if not client or not client.is_connected():
                logger.warning(f"Rule sender {selected_session} not connected")
                return

            # 发送消息
            await client.send_message(chat_id, reply_message)
            logger.info(f"Rule '{rule['rule_name']}' executed by {selected_session} in chat {chat_id}")

        except Exception as e:
            logger.error(f"Error executing rule '{rule.get('rule_name', 'unknown')}': {e}")

class RuleScheduler:
    """规则调度器，处理定时任务"""

    def __init__(self):
        self.scheduled_tasks = {}
        self.running = False

    async def start(self):
        """启动调度器"""
        self.running = True
        asyncio.create_task(self._schedule_loop())
        logger.info("Rule scheduler started")

    async def stop(self):
        """停止调度器"""
        self.running = False
        # 取消所有定时任务
        for task in self.scheduled_tasks.values():
            if not task.done():
                task.cancel()
        self.scheduled_tasks.clear()
        logger.info("Rule scheduler stopped")

    async def _schedule_loop(self):
        """调度循环，每分钟检查一次"""
        while self.running:
            try:
                await self._check_scheduled_rules()
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"Schedule loop error: {e}")
                await asyncio.sleep(60)

    async def _check_scheduled_rules(self):
        """检查并执行定时规则"""
        try:
            now = datetime.now()
            current_time = now.strftime("%H:%M")
            current_day = now.weekday()  # 0-6, Monday-Sunday
            current_date = now.day

            # 获取所有定时规则
            all_rules = await db_manager.get_message_rules()

            for rule in all_rules:
                if not rule.get('is_enabled', True) or rule.get('rule_type') != 'scheduled':
                    continue

                trigger_condition = rule.get('trigger_condition', {})
                scheduled_times = trigger_condition.get('scheduled_times', [])
                repeat_type = trigger_condition.get('repeat_type', 'once')

                # 检查是否应该执行
                should_execute = False

                if current_time in scheduled_times:
                    if repeat_type == 'once':
                        # 一次性任务，检查是否已经执行过
                        task_key = f"{rule['id']}_{current_time}"
                        if task_key not in self.scheduled_tasks:
                            should_execute = True
                            # 标记为已执行（当天内不会再执行）
                            self.scheduled_tasks[task_key] = asyncio.create_task(asyncio.sleep(86400))  # 24小时后清除
                    elif repeat_type == 'daily':
                        should_execute = True
                    elif repeat_type == 'weekly':
                        # 每周执行，检查是否是指定星期
                        should_execute = True  # 暂时每天都执行，可以扩展为指定星期
                    elif repeat_type == 'monthly':
                        # 每月执行，检查是否是指定日期
                        should_execute = True  # 暂时每天都执行，可以扩展为指定日期

                if should_execute:
                    await self._execute_scheduled_rule(rule)

        except Exception as e:
            logger.error(f"Error checking scheduled rules: {e}")

    async def _execute_scheduled_rule(self, rule: Dict[str, Any]):
        """执行定时规则"""
        try:
            logger.info(f"Executing scheduled rule: {rule['rule_name']}")

            reply_message = rule.get('reply_message', '')
            sender_sessions = rule.get('sender_sessions', [])

            if not reply_message or not sender_sessions:
                logger.warning(f"Rule {rule['rule_name']} missing message or senders")
                return

            # 获取规则关联的群组
            group_id = rule.get('group_id')
            if not group_id:
                logger.warning(f"Rule {rule['rule_name']} has no associated group")
                return

            # 随机选择发送者
            import random
            selected_session = random.choice(sender_sessions)

            # 检查发送者是否可用
            from core.telegram_client import telegram_client
            if selected_session not in telegram_client.clients:
                logger.warning(f"Sender {selected_session} not available for rule {rule['rule_name']}")
                return

            client = telegram_client.clients[selected_session]
            if not client or not client.is_connected():
                logger.warning(f"Sender {selected_session} not connected for rule {rule['rule_name']}")
                return

            # 发送消息
            await client.send_message(group_id, reply_message)

            # 延迟
            delay = rule.get('delay_seconds', 0)
            if delay > 0:
                await asyncio.sleep(delay)

            logger.info(f"Scheduled rule '{rule['rule_name']}' executed successfully")

        except Exception as e:
            logger.error(f"Error executing scheduled rule '{rule['rule_name']}': {e}")

class MessageManager:
    """Main message management class"""

    def __init__(self):
        self.queue = MessageQueue()
        self.listener = MessageListener()
        self.scheduler = RuleScheduler()

    def set_concurrent_mode(self, enabled: bool, max_concurrent: int = 5):
        """Set concurrent sending mode"""
        self.queue.concurrent_mode = enabled
        self.queue.max_concurrent_tasks = max_concurrent
        logger.info(f"Concurrent mode {'enabled' if enabled else 'disabled'}, max concurrent: {max_concurrent}")

    async def start(self):
        """Start message manager"""
        await self.queue.start()
        await self.scheduler.start()
        logger.info("Message manager started")

    async def stop(self):
        """Stop message manager"""
        await self.queue.stop()
        await self.scheduler.stop()
        logger.info("Message manager stopped")

    async def send_message(self, session_name: str, chat_id: int, text: str,
                          reply_to_id: Optional[int] = None) -> bool:
        """Send message through queue"""
        task = MessageTask(
            session_name=session_name,
            chat_id=chat_id,
            text=text,
            reply_to_id=reply_to_id
        )
        await self.queue.add_message(task)
        return True

    async def broadcast_message(self, session_names: List[str], chat_id: int,
                               text: str, reply_to_id: Optional[int] = None) -> int:
        """Send message to multiple sessions"""
        sent_count = 0
        for session_name in session_names:
            try:
                await self.send_message(session_name, chat_id, text, reply_to_id)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast message to {session_name}: {e}")
        return sent_count

    def add_message_listener(self, session_name: str, callback: Callable):
        """Add message listener"""
        self.listener.add_listener(session_name, callback)

    async def start_listening(self, session_name: str):
        """Start listening for messages"""
        await self.listener.start_listening(session_name)

    async def get_chat_history(self, session_name: str, chat_id: int,
                              limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get chat message history"""
        return await db_manager.get_chat_messages(session_name, chat_id, limit, offset)

    async def get_chats(self, session_name: str) -> List[Dict[str, Any]]:
        """Get chats for session"""
        # First try to get from database
        chats = await db_manager.get_chats(session_name)

        # If no chats in database, try to fetch from Telegram
        if not chats:
            from core.session_manager import session_manager
            client = session_manager.active_sessions.get(session_name)
            if client and client.is_connected:
                try:
                    dialogs = await client.get_dialogs()
                    for dialog in dialogs:
                        # Get the chat entity
                        chat = dialog.entity

                        # Determine chat type and properties
                        chat_type = type(chat).__name__.lower()
                        title = getattr(chat, 'title', None) or getattr(chat, 'first_name', None) or 'Unknown'
                        username = getattr(chat, 'username', None)

                        chat_data = {
                            'chat_id': chat.id,
                            'title': title,
                            'type': chat_type,
                            'username': username,
                            'last_message_time': dialog.message.date if dialog.message else None,
                            'unread_count': dialog.unread_count,
                            'is_pinned': dialog.pinned
                        }
                        await db_manager.save_chat(session_name, chat_data)
                        chats.append(chat_data)
                except Exception as e:
                    logger.error(f"Failed to fetch chats for {session_name}: {e}")

        return chats

# Global message manager instance
message_manager = MessageManager()

async def init_message_manager():
    """Initialize message manager"""
    await message_manager.start()

async def cleanup_message_manager():
    """Cleanup message manager"""
    await message_manager.stop()
