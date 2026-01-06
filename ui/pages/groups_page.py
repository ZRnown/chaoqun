from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QPushButton, QLabel, QMessageBox, QListWidgetItem,
                             QComboBox, QDialog, QLineEdit, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
import asyncio
import re
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest  # 新增引用
from telethon.errors import UserAlreadyParticipantError, InviteHashExpiredError  # 新增引用
from core.database import db_manager
from core.telegram_client import telegram_client


class GroupsPage(QWidget):
    """群组管理页面"""

    def __init__(self):
        super().__init__()
        self.current_group = None
        self.groups_data = {}
        self.setup_ui()
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(200, self.load_groups_from_db)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("群组管理")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333; margin-bottom: 10px;")
        layout.addWidget(title)

        description = QLabel("管理您的Telegram群组，为群组分配账号并监控状态")
        description.setStyleSheet("color: #666; margin-bottom: 20px;")
        layout.addWidget(description)

        # 群组选择区域
        groups_widget = QWidget()
        groups_layout = QHBoxLayout(groups_widget)

        groups_layout.addWidget(QLabel("选择群组:"))

        self.groups_combo = QComboBox()
        self.groups_combo.addItem("请选择群组...")
        self.groups_combo.currentTextChanged.connect(self.on_group_selected_by_combo)
        groups_layout.addWidget(self.groups_combo, 1)

        self.add_group_btn = QPushButton("➕ 新建/添加群组")
        self.add_group_btn.setProperty("class", "SuccessBtn")
        self.add_group_btn.clicked.connect(self.add_group)
        groups_layout.addWidget(self.add_group_btn)

        self.delete_group_btn = QPushButton("🗑️ 删除群组")
        self.delete_group_btn.setEnabled(False)
        self.delete_group_btn.clicked.connect(self.delete_selected_group)
        groups_layout.addWidget(self.delete_group_btn)

        layout.addWidget(groups_widget)

        # 主要内容区域
        content_layout = QHBoxLayout()

        # 左侧：当前群组内的账号列表
        accounts_widget = QWidget()
        accounts_layout = QVBoxLayout(accounts_widget)
        accounts_layout.addWidget(QLabel("已在该群组的账号"))

        self.accounts_list = QListWidget()
        self.accounts_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        accounts_layout.addWidget(self.accounts_list)

        content_layout.addWidget(accounts_widget, 2)

        # 右侧：操作面板
        actions_panel = QWidget()
        actions_layout = QVBoxLayout(actions_panel)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        actions_layout.addWidget(QLabel("账号操作"))

        self.btn_add_account = QPushButton("➕ 添加账号入群")
        self.btn_add_account.setProperty("class", "SuccessBtn")
        self.btn_add_account.setEnabled(False)
        self.btn_add_account.clicked.connect(self.add_account_to_group)
        actions_layout.addWidget(self.btn_add_account)

        self.btn_remove_account = QPushButton("➖ 移除关联")
        self.btn_remove_account.setProperty("class", "DangerBtn")
        self.btn_remove_account.setEnabled(False)
        self.btn_remove_account.clicked.connect(self.remove_account_from_group)
        actions_layout.addWidget(self.btn_remove_account)

        actions_layout.addStretch()

        # 群组信息
        self.group_info = QLabel("请先选择一个群组")
        self.group_info.setWordWrap(True)
        actions_layout.addWidget(self.group_info)

        content_layout.addWidget(actions_panel, 1)
        layout.addLayout(content_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

    def load_groups_from_db(self):
        """加载群组 (使用 asyncio)"""
        async def _load():
            try:
                groups = await db_manager.get_managed_groups()
                self.groups_data = {}
                self.groups_combo.clear()
                self.groups_combo.addItem("请选择群组...")

                for group in groups:
                    # 根据加入状态显示不同的信息
                    status_indicator = ""
                    if group.get('join_status') == 'pending':
                        status_indicator = "[待加入] "
                    elif group.get('join_status') == 'joined':
                        status_indicator = "[已加入] "

                    # 为恢复的群组提供更好的显示名称
                    title = group['title']
                    if title.startswith('群组 ') and group.get('chat_id'):
                        # 如果是恢复的群组，尝试提供更好的名称
                        chat_id = group['chat_id']
                        if group.get('username'):
                            title = f"@{group['username']}"
                        else:
                            # 尝试从chat_id推断类型
                            if str(chat_id).startswith('-100'):
                                title = f"频道 {chat_id}"
                            elif str(chat_id).startswith('-'):
                                title = f"群组 {chat_id}"
                            else:
                                title = f"对话 {chat_id}"

                    link_info = group.get('username') or group.get('original_link') or '无链接'
                    display = f"{status_indicator}{title} ({link_info})"
                    self.groups_data[display] = group
                    self.groups_combo.addItem(display)

            except Exception as e:
                print(f"Error loading groups: {e}")

        # 安全地创建任务，避免在应用程序关闭时出现未等待的协程警告
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_load())
            # 添加任务完成回调来处理可能的异常
            task.add_done_callback(lambda t: t.exception() if t.exception() else None)
        except RuntimeError:
            # 如果没有运行中的事件循环，直接运行（用于初始化时）
            import asyncio as asyncio_module
            loop = asyncio_module.new_event_loop()
            asyncio_module.set_event_loop(loop)
            try:
                loop.run_until_complete(_load())
            finally:
                loop.close()

    def on_group_selected_by_combo(self, text):
        if text not in self.groups_data:
            self.current_group = None
            self.btn_add_account.setEnabled(False)
            self.delete_group_btn.setEnabled(False)
            self.accounts_list.clear()
            self.group_info.setText("请选择群组")
            return

        self.current_group = self.groups_data[text]
        self.btn_add_account.setEnabled(True)
        self.btn_remove_account.setEnabled(True)
        self.delete_group_btn.setEnabled(True)

        info = f"群名: {self.current_group['title']}\n" \
               f"ID: {self.current_group['chat_id']}\n" \
               f"用户名: {self.current_group['username']}"
        self.group_info.setText(info)

        self.load_group_accounts()

    def load_group_accounts(self):
        if not self.current_group:
            return

        async def _load_accts():
            self.accounts_list.clear()
            group_id = self.current_group['chat_id']
            try:
                session_names = await db_manager.get_group_sessions(group_id)
                all_sessions = await db_manager.get_all_sessions()
                session_map = {s['session_name']: s for s in all_sessions}

                for session_name in session_names:
                    session_data = session_map.get(session_name)
                    if session_data:
                        display_name = session_data.get('user_name', session_name)
                        phone = session_data.get('phone_number', '未知')
                        item_text = f"{display_name} ({phone})"
                        item = QListWidgetItem(item_text)
                        item.setData(Qt.ItemDataRole.UserRole, session_data)
                        self.accounts_list.addItem(item)

            except Exception as e:
                print(f"Error loading group accounts: {e}")

        asyncio.create_task(_load_accts())

    def add_group(self):
        """添加新群组"""
        dialog = AddGroupDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            group_data = dialog.get_group_data()
            if group_data:
                for existing_group in self.groups_data.values():
                    if existing_group['chat_id'] == group_data['id']:
                        QMessageBox.warning(self, "警告", f"群组ID {group_data['id']} 已存在")
                        return

                self.save_group_to_db(group_data)

    def save_group_to_db(self, group_data):
        """保存群组到数据库 (Asyncio版)"""
        async def _save():
            try:
                db_data = {
                    'chat_id': group_data.get('id'),
                    'chat_title': group_data['title'],
                    'chat_type': 'group',
                    'username': group_data.get('username'),
                    'original_link': group_data.get('original_link'),
                    'join_status': 'pending' if group_data.get('id') is None else 'joined'
                }
                await db_manager.add_managed_group(**db_data)

                display_text = f"{group_data['title']} ({group_data.get('username') or '无链接'})"
                new_group_struct = {
                    'chat_id': group_data['id'],
                    'title': group_data['title'],
                    'type': 'group',
                    'username': group_data.get('username')
                }

                # UI更新必须在主线程
                from PyQt6.QtCore import QTimer
                def update_ui():
                    self.groups_data[display_text] = new_group_struct
                    self.groups_combo.addItem(display_text)
                    # 暂时断开信号连接，避免触发load_group_accounts
                    self.groups_combo.currentTextChanged.disconnect(self.on_group_selected_by_combo)
                    self.groups_combo.setCurrentText(display_text)
                    self.groups_combo.currentTextChanged.connect(self.on_group_selected_by_combo)

                    QMessageBox.information(self, "成功", f"群组 '{group_data['title']}' 已添加")

                QTimer.singleShot(0, update_ui)

            except Exception as e:
                QMessageBox.warning(self, "警告", f"保存到数据库失败: {e}")

        asyncio.create_task(_save())

    def delete_selected_group(self):
        """删除选中的群组"""
        if not self.current_group:
            return

        group_name = self.current_group['title']
        reply = QMessageBox.question(
            self, "确认删除",
            f"⚠️ 确定要删除群组 '{group_name}' 吗？\n这将删除该群组的管理记录。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.delete_group_async()

    def delete_group_async(self):
        """异步删除群组 (Asyncio版)"""
        async def _delete():
            try:
                await db_manager.remove_managed_group(self.current_group['chat_id'])

                current_text = self.groups_combo.currentText()
                index = self.groups_combo.currentIndex()
                self.groups_combo.removeItem(index)

                if current_text in self.groups_data:
                    del self.groups_data[current_text]

                self.groups_combo.setCurrentIndex(0)
                QMessageBox.information(self, "成功", "群组已删除")

            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除群组失败: {e}")

        asyncio.create_task(_delete())

    def add_account_to_group(self):
        if not self.current_group:
            QMessageBox.warning(self, "警告", "请先选择一个群组")
            return

        dialog = AccountSelectionDialog(self, self.current_group)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_sessions = dialog.get_selected_sessions()
            if selected_sessions:
                self.join_accounts_to_group(selected_sessions)

    def remove_account_from_group(self):
        selected_items = self.accounts_list.selectedItems()
        if not selected_items:
            return

        async def _remove():
            for item in selected_items:
                session = item.data(Qt.ItemDataRole.UserRole)
                await db_manager.remove_group_session(self.current_group['chat_id'], session['session_name'])

            self.load_group_accounts()
            QMessageBox.information(self, "成功", "已移除关联")

        asyncio.create_task(_remove())

    def join_accounts_to_group(self, session_names):
        if not self.current_group or not session_names:
            return

        # 安全地初始化进度条
        try:
            if hasattr(self, 'progress_bar') and self.progress_bar:
                self.progress_bar.setVisible(True)
                self.progress_bar.setMaximum(len(session_names))
                self.progress_bar.setValue(0)
        except (RuntimeError, AttributeError):
            print("进度条初始化失败，可能是UI对象已被删除")
            return

        async def _join_all():
            group_id = self.current_group['chat_id']
            # 获取所有可能的链接形式
            original_link = self.current_group.get('original_link')
            username = self.current_group.get('username')

            success_count = 0

            for i, session_name in enumerate(session_names):
                try:
                    # 1. 检查数据库
                    existing = await db_manager.get_group_sessions(group_id)
                    if session_name in existing:
                        success_count += 1
                        print(f"账号 {session_name} 已在群组中 (DB check)，跳过")
                        continue

                    # 2. 启动会话
                    if not await telegram_client.start_session(session_name):
                        print(f"启动会话失败: {session_name}")
                        continue

                    client = telegram_client.clients.get(session_name)
                    if not client:
                        print(f"获取客户端失败: {session_name}")
                        continue

                    join_success = False

                    # === 增强的加入逻辑 ===
                    try:
                        # 策略 A: 优先使用原始链接 (最准确)
                        if original_link and not join_success:
                            print(f"尝试通过原始链接加入 ({session_name}): {original_link}")
                            try:
                                await client.join_channel(original_link)
                                join_success = True
                                print(f"✅ 通过原始链接加入成功")
                            except Exception as e:
                                print(f"原始链接加入失败: {e}")
                                # 如果是纯字符串且失败了，尝试构造 URL 再次尝试
                                if 't.me' not in original_link and 'http' not in original_link:
                                    constructed_url = f"https://t.me/{original_link.strip().strip('@')}"
                                    print(f"尝试通过构造URL加入: {constructed_url}")
                                    try:
                                        await client.join_channel(constructed_url)
                                        join_success = True
                                        print(f"✅ 通过构造URL加入成功")
                                    except Exception as e2:
                                        print(f"构造URL加入失败: {e2}")

                                # 如果还是失败，且看起来像 Hash，尝试 ImportChatInviteRequest
                                if not join_success:
                                    clean_hash = original_link.split('/')[-1].replace('+', '').strip()
                                    if clean_hash and re.match(r'^[a-zA-Z0-9_-]+$', clean_hash):
                                        print(f"尝试作为邀请Hash加入: {clean_hash}")
                                        try:
                                            await client(ImportChatInviteRequest(clean_hash))
                                            join_success = True
                                            print(f"✅ 通过邀请Hash加入成功")
                                        except Exception as e3:
                                            print(f"邀请Hash加入失败: {e3}")

                        # 策略 B: 使用用户名 (如果跟原始链接不同)
                        if not join_success and username and username != original_link:
                            print(f"尝试通过用户名加入 ({session_name}): {username}")
                            try:
                                await client(JoinChannelRequest(username))
                                join_success = True
                                print(f"✅ 通过用户名加入成功")
                            except Exception as e:
                                print(f"用户名加入失败: {e}")

                        # 策略 C: 通过 ID (仅对已知群组有效)
                        if not join_success and group_id:
                            print(f"尝试通过ID加入 ({session_name}): {group_id}")
                            try:
                                entity = await client.get_entity(group_id)
                                await client(JoinChannelRequest(entity))
                                join_success = True
                                print(f"✅ 通过ID加入成功")
                            except Exception as e:
                                print(f"ID加入失败: {e}")

                    except UserAlreadyParticipantError:
                        print(f"账号已在群组中 (Telegram API): {session_name}")
                        join_success = True
                    except InviteHashExpiredError:
                         print(f"邀请链接已过期 ({session_name})")
                    except Exception as e:
                        # 兜底捕获
                        error_str = str(e).lower()
                        if "already" in error_str:
                            join_success = True
                            print(f"账号已在群组中 (Generic Error): {session_name}")
                        else:
                            print(f"加入尝试全失败 ({session_name}): {e}")

                    if join_success:
                        await db_manager.add_group_session(group_id, session_name)
                        success_count += 1

                        # 更新群组信息
                        if success_count == 1:
                            try:
                                # 尝试获取最新的群组实体信息
                                entity_ref = username or original_link or group_id
                                if entity_ref:
                                    try:
                                        chat = await client.get_entity(entity_ref)
                                        await db_manager.update_managed_group_chat_id(
                                            self.current_group['title'],
                                            chat.id,
                                            getattr(chat, 'title', None),
                                            getattr(chat, 'username', None)
                                        )
                                        print(f"已更新群组信息: {chat.title} ID:{chat.id}")
                                    except:
                                        pass
                            except:
                                pass

                except Exception as e:
                    print(f"处理账号异常 ({session_name}): {e}")

                # 安全地更新进度条，避免对象已被删除的错误
                try:
                    if hasattr(self, 'progress_bar') and self.progress_bar and not self.progress_bar.isHidden():
                        self.progress_bar.setValue(i + 1)
                except (RuntimeError, AttributeError):
                    # 进度条对象已被删除，跳过更新
                    pass

            # 安全地隐藏进度条
            try:
                if hasattr(self, 'progress_bar') and self.progress_bar and not self.progress_bar.isHidden():
                    self.progress_bar.setVisible(False)
            except (RuntimeError, AttributeError):
                # 进度条对象已被删除，跳过隐藏
                pass

            from PyQt6.QtCore import QTimer
            def update_ui():
                try:
                    # 检查对象是否还存在
                    if hasattr(self, 'load_group_accounts'):
                        self.load_group_accounts()
                    if hasattr(self, 'parent') and self.parent():
                        QMessageBox.information(self, "完成", f"操作结束。\n成功: {success_count}\n总数: {len(session_names)}")
                except Exception as e:
                    print(f"UI更新失败: {e}")
                    # 如果UI更新失败，至少在控制台输出结果
                    print(f"操作完成 - 成功: {success_count}/{len(session_names)}")

            QTimer.singleShot(0, update_ui)

        asyncio.create_task(_join_all())


class AddGroupDialog(QDialog):
    """添加群组对话框 (简化版：直接输入链接)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加群组")
        self.resize(500, 400)
        self.fetched_group_data = None
        self.fetch_worker = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        info_label = QLabel("输入群组链接或ID，程序将尝试获取群组信息并加入群组。\n即使无法获取详细信息，也会尝试直接加入：")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        link_layout = QVBoxLayout()
        link_label = QLabel("群组链接/ID:")
        link_layout.addWidget(link_label)

        self.group_link_input = QLineEdit()
        self.group_link_input.setPlaceholderText("例如: https://t.me/groupname 或 @groupname 或 -100123456789 或 邀请链接")
        link_layout.addWidget(self.group_link_input)
        layout.addLayout(link_layout)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        layout.addWidget(self.status_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        self.add_btn = QPushButton("获取信息并添加")
        self.add_btn.setProperty("class", "SuccessBtn")
        self.add_btn.clicked.connect(self.fetch_and_add)
        buttons_layout.addWidget(self.add_btn)

        layout.addLayout(buttons_layout)

    def fetch_and_add(self):
        link = self.group_link_input.text().strip()
        if not link:
            QMessageBox.warning(self, "提示", "请输入群组链接")
            return

        self.add_btn.setEnabled(False)
        self.add_btn.setText("获取中...")
        self.status_label.setText("正在获取群组信息...")
        self.status_label.setStyleSheet("color: #007AFF; font-size: 12px;")

        # 使用工作线程处理异步操作，避免与PyQt事件循环冲突
        self.fetch_worker = GroupFetchWorker(link)
        self.fetch_worker.fetch_completed.connect(self._on_fetch_completed)
        self.fetch_worker.fetch_error.connect(self._on_fetch_error)
        self.fetch_worker.start()

    def _on_fetch_completed(self, group_data):
        """获取完成处理"""
        self.fetched_group_data = group_data
        self.status_label.setText(f"✅ 获取成功: {group_data['title']}")
        self.status_label.setStyleSheet("color: #28a745; font-size: 12px;")
        self.add_btn.setEnabled(True)
        self.add_btn.setText("确认添加")
        self.add_btn.clicked.disconnect()
        self.add_btn.clicked.connect(self.accept)

    def _on_fetch_error(self, error_msg):
        """获取错误处理 - 只有在能获取基本信息时才允许尝试添加"""
        self.status_label.setStyleSheet("color: #ffc107; font-size: 12px;")

        # 构造基本的群组数据用于尝试加入
        link = self.group_link_input.text().strip()
        parsed = self.parse_group_link(link)

        if parsed and (parsed.get('id') or parsed.get('username')):
            basic_group_data = {
                'id': parsed.get('id'),
                'title': parsed.get('username', f"未知群组 ({link[:20]}...)"),
                'username': parsed.get('username'),
                'original_link': link
            }
            self.fetched_group_data = basic_group_data

            self.status_label.setText(f"⚠️ 获取详细信息失败，但仍可尝试加入: {error_msg[:30]}...")
            self.add_btn.setEnabled(True)
            self.add_btn.setText("仍要尝试添加")
            self.add_btn.clicked.disconnect()
            self.add_btn.clicked.connect(self.accept)
        else:
            self.status_label.setText(f"❌ 无法获取有效群组信息: {error_msg[:50]}...")
            self.add_btn.setEnabled(True)
            self.add_btn.setText("获取信息并添加")

    async def _auto_select_account(self):
        from PyQt6.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'page_accounts'):
                accounts = widget.page_accounts.accounts_data
                if accounts:
                    return accounts[0]
        return None

    def parse_group_link(self, link):
        link = link.strip()
        if not link:
            return None

        if link.startswith('http'):
            link = re.sub(r'https?://t\.me/', '', link)
        elif link.startswith('@'):
            link = link[1:]

        if link.startswith('t.me/'):
            link = link[5:]

        link = link.lstrip('/')

        if link.startswith('+'):
            return {'username': link[1:]}

        if link.isdigit() or (link.startswith('-') and link[1:].isdigit()):
            return {'id': int(link)}

        if link and not link.startswith('+'):
            return {'username': link}

        return None

    def get_group_data(self):
        return self.fetched_group_data

    def closeEvent(self, event):
        """关闭对话框时清理工作线程"""
        if self.fetch_worker and self.fetch_worker.isRunning():
            self.fetch_worker.wait(3000)  # 等待最多3秒
        event.accept()


class AccountSelectionDialog(QDialog):
    def __init__(self, parent=None, group_data=None):
        super().__init__(parent)
        self.group_data = group_data
        self.setWindowTitle(f"选择账号加入: {group_data['title']}")
        self.resize(400, 400)
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()

        # 获取当前群组已有的账号
        self.existing_sessions = []
        if hasattr(parent, 'current_group') and parent.current_group:
            import asyncio
            from PyQt6.QtCore import QTimer

            def load_existing_sessions():
                async def _load():
                    try:
                        group_id = parent.current_group['chat_id']
                        existing = await db_manager.get_group_sessions(group_id)
                        self.existing_sessions = existing
                        self.populate_account_list()
                    except Exception as e:
                        print(f"Error loading existing sessions: {e}")
                        self.populate_account_list()

                asyncio.create_task(_load())

            QTimer.singleShot(0, load_existing_sessions)
        else:
            self.populate_account_list()

        layout.addWidget(self.list_widget)

        btn_box = QHBoxLayout()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)
        btn_box.addWidget(ok_btn)
        layout.addLayout(btn_box)

    def populate_account_list(self):
        """填充账号列表"""
        from PyQt6.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'page_accounts'):
                for account in widget.page_accounts.accounts_data:
                    session_name = account['session_name']
                    item = QListWidgetItem(f"{account['name']} ({account['phone']})")
                    item.setData(Qt.ItemDataRole.UserRole, account)

                    # 如果账号已经在群组中，默认勾选且禁用
                    if session_name in self.existing_sessions:
                        item.setCheckState(Qt.CheckState.Checked)
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)  # 禁用该项
                        item.setText(f"✓ {account['name']} ({account['phone']}) [已加入]")
                    else:
                        item.setCheckState(Qt.CheckState.Unchecked)

                    self.list_widget.addItem(item)
                break

    def get_selected_sessions(self):
        """获取新选择的账号（排除已加入的账号）"""
        sessions = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                data = item.data(Qt.ItemDataRole.UserRole)
                session_name = data['session_name']
                # 只返回新选择的账号，已加入的不需要再次处理
                if session_name not in self.existing_sessions:
                    sessions.append(session_name)
        return sessions


class GroupFetchWorker(QThread):
    """群组信息获取工作线程"""
    fetch_completed = pyqtSignal(dict)
    fetch_error = pyqtSignal(str)

    def __init__(self, link):
        super().__init__()
        self.link = link

    def run(self):
        """在工作线程中执行异步操作"""
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                result = loop.run_until_complete(self._fetch_group_info_async())
                self.fetch_completed.emit(result)
            finally:
                loop.close()

        except Exception as e:
            self.fetch_error.emit(str(e))

    async def _fetch_group_info_async(self, link=None):
        """异步获取群组信息"""
        if link is None:
            link = self.link

        parsed = self.parse_group_link(link)
        if not parsed:
            raise ValueError("无法解析群组链接格式")

        selected_account = await self._auto_select_account()
        if not selected_account:
            raise ValueError("没有可用的账号，请先添加账号")

        print(f"DEBUG: selected_account = {selected_account}")  # 调试信息

        # 检查selected_account是否有session_name
        if 'session_name' not in selected_account:
            raise ValueError(f"账号数据不完整，缺少session_name字段: {selected_account}")

        # 直接创建并启动一个新的client，避免与主程序的session冲突
        from core.session_manager import session_manager
        from config import config

        session_name = selected_account['session_name']
        print(f"DEBUG: session_name = {session_name}")  # 调试信息

        # 从数据库获取session数据
        session_data = await db_manager.load_session(session_name)
        if not session_data:
            raise ValueError(f"Session {session_name} not found in database")

        # 创建独立的client
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        if session_data.get('session_string'):
            session = StringSession(session_data['session_string'])
        elif session_data.get('session_file_path'):
            # 使用文件路径创建session
            session = session_data['session_file_path']
        else:
            session = StringSession()

        client = TelegramClient(
            session=session,
            api_id=config.telegram.api_id,
            api_hash=config.telegram.api_hash
        )

        try:
            # 启动client
            await client.start()

            # 验证是否已授权
            if not await client.is_user_authorized():
                raise ValueError("账号未授权，请先在账号管理中登录")

            # 尝试获取群组信息（可选，如果获取失败仍允许加入）
            group_id = None
            title = '未知群组'
            username = None

            try:
                # 获取群组信息
                if parsed.get('username'):
                    try:
                        chat = await client.get_entity(parsed['username'])
                    except:
                        if not parsed['username'].startswith('@'):
                            chat = await client.get_entity(f"@{parsed['username']}")
                        else:
                            raise
                elif parsed.get('id'):
                    chat = await client.get_entity(parsed['id'])
                else:
                    raise ValueError("无效的群组标识")

                group_id = chat.id
                title = getattr(chat, 'title', '未知群组')
                username = getattr(chat, 'username', None)

                print(f"DEBUG: 成功获取群组信息 - ID: {group_id}, 标题: {title}")

            except Exception as e:
                print(f"DEBUG: 获取群组详细信息失败: {e}，将使用基本信息尝试加入")
                # 如果无法获取详细信息，构造基本信息
                group_id = None
                username = None
                title = '未知群组'

                if parsed.get('id'):
                    group_id = parsed['id']
                    title = f"群组 {group_id}"
                elif parsed.get('username'):
                    username = parsed['username'].lstrip('@')
                    title = f"@{username}"
                else:
                    raise ValueError(f"无法解析群组标识且无法获取详细信息: {e}")

            return {
                'id': group_id,
                'title': title,
                'username': username,
                'selected_account': selected_account,
                'original_link': link  # 保存原始链接，用于加入
            }

        finally:
            # 确保client被正确关闭
            await client.disconnect()

    async def _auto_select_account(self):
        """自动选择一个可用的账号"""
        from PyQt6.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if hasattr(widget, 'page_accounts'):
                accounts = widget.page_accounts.accounts_data
                print(f"DEBUG: Found {len(accounts)} accounts")  # 调试信息
                if accounts:
                    print(f"DEBUG: First account = {accounts[0]}")  # 调试信息
                    return accounts[0]
        print("DEBUG: No accounts page found or no accounts")  # 调试信息
        return None

    def parse_group_link(self, link):
        """解析群组链接"""
        link = link.strip()
        if not link:
            return None

        if link.startswith('http'):
            link = re.sub(r'https?://t\.me/', '', link)
        elif link.startswith('@'):
            link = link[1:]

        if link.startswith('t.me/'):
            link = link[5:]

        link = link.lstrip('/')

        if link.startswith('+'):
            return {'username': link[1:]}

        if link.isdigit() or (link.startswith('-') and link[1:].isdigit()):
            return {'id': int(link)}

        if link and not link.startswith('+'):
            return {'username': link}

        return None