from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
                             QPushButton, QLabel, QFileDialog, QMessageBox,
                             QSpinBox, QListWidget, QListWidgetItem, QDialog,
                             QTabWidget, QMenu, QInputDialog)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QTextCursor, QTextFormat, QAction, QIcon
from datetime import datetime
import asyncio
import re
import random
from core.database import db_manager
from core.telegram_client import telegram_client


class ScriptTab(QWidget):
    """单个剧本执行标签页"""

    execution_finished = pyqtSignal()  # 执行完成信号

    def __init__(self, tab_name, parent=None):
        super().__init__(parent)
        self.tab_name = tab_name
        self.current_file_path = None
        self.sent_messages = {}  # 存储已发送消息的ID {line_number: message_id}
        self.script_execution_paused = False  # 剧本执行暂停状态
        self.script_task = None  # 存储当前的执行任务
        self.group_accounts = [] # 存储当前群组的账号信息（包含实时ID和用户名）
        self.loop_execution = False  # 循环执行标志
        self.loop_task = None  # 循环执行任务
        self.account_execution_order = [] # 账号执行顺序
        self.selected_group = None # 选中的群组
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # 标签页标题和控制
        header_layout = QHBoxLayout()
        self.tab_title = QLabel(f"📄 {self.tab_name}")
        self.tab_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333; padding: 5px 0px;")
        header_layout.addWidget(self.tab_title)

        header_layout.addStretch()

        # 循环执行复选框
        self.loop_checkbox = QPushButton("🔄 循环执行")
        self.loop_checkbox.setCheckable(True)
        self.loop_checkbox.setMaximumWidth(100)
        self.loop_checkbox.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: 1px solid #007AFF;
                color: #007AFF;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 11px;
            }
            QPushButton:checked {
                background-color: #007AFF;
                color: white;
            }
        """)
        self.loop_checkbox.clicked.connect(self.toggle_loop_execution)
        header_layout.addWidget(self.loop_checkbox)

        layout.addLayout(header_layout)

        # 文件操作栏
        file_layout = QHBoxLayout()
        self.file_status_label = QLabel("未加载剧本文件")
        file_layout.addWidget(self.file_status_label)

        file_layout.addStretch()

        load_btn = QPushButton("📂 加载剧本")
        load_btn.clicked.connect(self.load_script)
        file_layout.addWidget(load_btn)

        file_widget = QWidget()
        file_widget.setLayout(file_layout)
        layout.addWidget(file_widget)

        # 主要内容区域
        content_layout = QHBoxLayout()

        # 左侧：剧本内容
        script_layout = QVBoxLayout()
        script_title = QLabel("剧本内容")
        script_title.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        script_layout.addWidget(script_title)

        self.script_view = QTextEdit()
        self.script_view.setReadOnly(True)
        self.script_view.setPlaceholderText("请先加载剧本文件...")
        self.script_view.setMinimumHeight(200)
        script_layout.addWidget(self.script_view)

        script_widget = QWidget()
        script_widget.setLayout(script_layout)
        content_layout.addWidget(script_widget, 3) # 比例 3

        # 右侧：执行日志
        log_layout = QVBoxLayout()
        log_title = QLabel("执行日志")
        log_title.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        log_layout.addWidget(log_title)

        self.execution_log = QTextEdit()
        self.execution_log.setReadOnly(True)
        self.execution_log.setMinimumHeight(200)
        log_layout.addWidget(self.execution_log)

        clear_log_btn = QPushButton("清空日志")
        clear_log_btn.setMaximumWidth(80)
        clear_log_btn.clicked.connect(lambda: self.execution_log.clear())
        log_layout.addWidget(clear_log_btn)

        log_widget = QWidget()
        log_widget.setLayout(log_layout)
        content_layout.addWidget(log_widget, 2) # 比例 2

        layout.addLayout(content_layout, 1)  # 让内容区域占据主要空间

        # 底部控制区域
        control_widget = QWidget()
        control_widget.setMaximumHeight(120)
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 10, 0, 0)

        # 左侧：群组选择
        group_layout = QVBoxLayout()
        group_title = QLabel("群组选择")
        group_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        group_layout.addWidget(group_title)

        self.group_info = QLabel("请先选择一个群组")
        self.group_info.setWordWrap(True)
        self.group_info.setStyleSheet("color: #666; font-size: 11px;")
        group_layout.addWidget(self.group_info)

        select_group_btn = QPushButton("选择群组")
        select_group_btn.setMaximumWidth(80)
        select_group_btn.clicked.connect(self.select_group)
        group_layout.addWidget(select_group_btn)

        control_layout.addLayout(group_layout)

        # 中间：执行选项
        options_layout = QVBoxLayout()
        options_title = QLabel("执行选项")
        options_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        options_layout.addWidget(options_title)

        self.account_order_btn = QPushButton("📋 账号顺序管理")
        self.account_order_btn.clicked.connect(self.manage_account_order)
        self.account_order_btn.setEnabled(False)
        self.account_order_btn.setMaximumWidth(120)
        options_layout.addWidget(self.account_order_btn)

        # 消息间隔设置
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("间隔:"))

        self.min_interval_spinbox = QSpinBox()
        self.min_interval_spinbox.setRange(1, 30)
        self.min_interval_spinbox.setValue(2)
        self.min_interval_spinbox.setSuffix("s")
        self.min_interval_spinbox.setMaximumWidth(60)
        interval_layout.addWidget(self.min_interval_spinbox)

        interval_layout.addWidget(QLabel("~"))

        self.max_interval_spinbox = QSpinBox()
        self.max_interval_spinbox.setRange(1, 60)
        self.max_interval_spinbox.setValue(4)
        self.max_interval_spinbox.setSuffix("s")
        self.max_interval_spinbox.setMaximumWidth(60)
        interval_layout.addWidget(self.max_interval_spinbox)

        options_layout.addLayout(interval_layout)

        control_layout.addLayout(options_layout)

        control_layout.addStretch()

        # 右侧：执行按钮
        buttons_layout = QVBoxLayout()
        buttons_title = QLabel("执行控制")
        buttons_title.setStyleSheet("font-weight: bold; font-size: 12px;")
        buttons_layout.addWidget(buttons_title)

        button_row = QHBoxLayout()
        self.execute_btn = QPushButton("🎭 开始执行")
        self.execute_btn.setProperty("class", "PrimaryBtn")
        self.execute_btn.clicked.connect(self.execute_script)
        self.execute_btn.setMaximumWidth(100)
        button_row.addWidget(self.execute_btn)

        self.pause_btn = QPushButton("⏸️ 暂停")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.pause_btn.setEnabled(False)
        self.pause_btn.setMaximumWidth(80)
        button_row.addWidget(self.pause_btn)

        self.test_image_btn = QPushButton("🖼️ 测试图片")
        self.test_image_btn.clicked.connect(self.test_image_send)
        self.test_image_btn.setMaximumWidth(100)
        button_row.addWidget(self.test_image_btn)

        buttons_layout.addLayout(button_row)

        control_layout.addLayout(buttons_layout)

        layout.addWidget(control_widget)

    def toggle_loop_execution(self):
        """切换循环执行模式"""
        self.loop_execution = self.loop_checkbox.isChecked()
        if self.loop_execution:
            self.add_log_entry("🔄 已启用循环执行模式", "info")
        else:
            self.add_log_entry("🔄 已禁用循环执行模式", "info")
            # 如果有循环任务在运行，停止它
            if self.loop_task and not self.loop_task.done():
                self.loop_task.cancel()

    def load_script(self):
        """加载剧本文件"""
        options = QFileDialog.Option(0)
        import platform
        if platform.system() in ["Darwin", "Linux"]:
            options = QFileDialog.Option.DontUseNativeDialog

        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择剧本文件", "", "文本文件 (*.txt);;所有文件 (*)", options=options
        )

        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                self.script_view.setPlainText(content)
                self.current_file_path = file_path
                self.file_status_label.setText(f"已加载: {file_path.split('/')[-1]}")
                self.add_log_entry(f"剧本文件已加载: {file_path.split('/')[-1]}", "success")

            except Exception as e:
                QMessageBox.critical(self, "错误", f"加载剧本失败: {str(e)}")

    def select_group(self):
        """选择执行群组"""
        dialog = GroupSelectDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_group = dialog.selected_group
            if selected_group:
                self.selected_group = selected_group
                # 安全地更新UI
                try:
                    if hasattr(self, 'group_info') and self.group_info:
                        self.group_info.setText(f"已选择: {selected_group['title']}")
                except (RuntimeError, AttributeError):
                    print(f"UI对象已被删除，无法更新群组信息")
                self.add_log_entry(f"已选择执行群组: {selected_group['title']}", "info")
                # 加载群组账号
                asyncio.create_task(self.display_group_accounts(selected_group))

    async def display_group_accounts(self, group_data):
        """加载账号并预热（获取真实用户名和ID）"""
        try:
            group_id = group_data['chat_id']
            session_names = await db_manager.get_group_sessions(group_id)

            if not session_names:
                # 安全地更新UI
                try:
                    if hasattr(self, 'group_info') and self.group_info:
                        self.group_info.setText(f"⚠️ 群组 {group_data['title']} 中没有添加账号")
                    if hasattr(self, 'account_order_btn') and self.account_order_btn:
                        self.account_order_btn.setEnabled(False)
                except (RuntimeError, AttributeError):
                    print(f"UI对象已被删除，无法更新群组信息")
                return

            self.add_log_entry(f"正在准备 {len(session_names)} 个账号，请稍候...", "info")

            # 1. 启动所有 Session
            success_count = 0
            self.group_accounts = [] # 清空重建

            # 获取数据库中的基本信息
            all_sessions = await db_manager.get_all_sessions()
            session_map_db = {s['session_name']: s for s in all_sessions}

            for session_name in session_names:
                # 启动 Session
                if await telegram_client.start_session(session_name):
                    success_count += 1
                    client = telegram_client.clients.get(session_name)

                    # 获取实时信息 (ID 和 Username) 关键步骤！
                    try:
                        me = await client.get_me()
                        user_info = {
                            'session_name': session_name,
                            'name': session_map_db.get(session_name, {}).get('user_name', session_name),
                            'phone': session_map_db.get(session_name, {}).get('phone_number', '未知'),
                            # 存储真实 Telegram 信息用于 @mention
                            'real_id': me.id,
                            'real_username': me.username,
                            'real_first_name': me.first_name
                        }
                        self.add_log_entry(f"👤 账号信息获取成功: {user_info['name']} - ID:{me.id}, Username:{me.username}", "info")
                    except Exception as e:
                        print(f"Error fetching me for {session_name}: {e}")
                        user_info = {
                            'session_name': session_name,
                            'name': session_name,
                            'phone': '未知',
                            'real_id': None,
                            'real_username': None
                        }
                        self.add_log_entry(f"⚠️ 账号信息获取失败: {session_name}", "warning")

                    self.group_accounts.append(user_info)

            # 初始化默认执行顺序
            self.account_execution_order = [acc['session_name'] for acc in self.group_accounts]

            # 安全地更新UI
            try:
                if hasattr(self, 'account_order_btn') and self.account_order_btn:
                    self.account_order_btn.setEnabled(True)
                    self.account_order_btn.setText(f"📋 账号顺序管理 ({len(self.group_accounts)} 个)")
            except (RuntimeError, AttributeError):
                print(f"UI对象已被删除，无法更新账号顺序按钮")

            self.add_log_entry(f"账号准备完成: {success_count}/{len(session_names)} 可用 (已获取实时信息)", "success")

        except Exception as e:
            self.add_log_entry(f"加载账号出错: {str(e)}", "error")

    async def _get_safe_client(self, session_name):
        """
        获取一个在当前事件循环中安全可用的 Client。
        增强版：检测 Loop 是否匹配，不匹配则重连。
        """
        from core.telegram_client import telegram_client
        import asyncio

        current_loop = asyncio.get_running_loop()
        client = telegram_client.clients.get(session_name)

        if client:
            try:
                # 检查 Loop 是否匹配
                if client.loop != current_loop:
                    print(f"检测到 Loop 不匹配 ({session_name})，正在重新连接...")
                    # 如果 Loop 不匹配，必须丢弃旧连接重新开始
                    # 注意：不能在当前 Loop await 旧 client.disconnect()，因为它属于别的 Loop
                    # 但 Telethon 的 disconnect 比较宽容，通常可以直接丢弃引用
                    # 从管理器移除
                    if session_name in telegram_client.clients:
                        del telegram_client.clients[session_name]
                    # 强制重新启动
                    client = None

                elif client.is_connected() and await client.is_user_authorized():
                    # 状态正常
                    return client
                else:
                    print(f"客户端状态异常，尝试重连: {session_name}")
            except Exception as e:
                print(f"检查客户端出错 ({session_name}): {e}")
                client = None

        if not client:
            print(f"正在初始化/重新启动会话: {session_name}")
            try:
                if await telegram_client.start_session(session_name):
                    client = telegram_client.clients.get(session_name)
                    # 再次确认 Loop
                    if client and client.loop == current_loop:
                        return client
            except Exception as e:
                print(f"启动会话失败 ({session_name}): {e}")

        return None

    def toggle_pause(self):
        """切换暂停/继续状态"""
        self.script_execution_paused = not self.script_execution_paused

        if self.script_execution_paused:
            self.pause_btn.setText("▶️ 继续执行")
            self.add_log_entry("剧本执行已暂停", "warning")
        else:
            self.pause_btn.setText("⏸️ 暂停执行")
            self.add_log_entry("剧本执行已继续", "info")

    def stop_script_execution(self):
        """强制停止剧本（如关闭窗口时）"""
        try:
            if self.script_task and not self.script_task.done():
                self.script_task.cancel()
            if self.loop_task and not self.loop_task.done():
                self.loop_task.cancel()
            self.script_execution_paused = False

            # 安全地更新UI按钮状态
            if hasattr(self, 'execute_btn') and self.execute_btn:
                self.execute_btn.setEnabled(True)
            if hasattr(self, 'pause_btn') and self.pause_btn:
                self.pause_btn.setEnabled(False)

            # 停止时清除高亮
            self.clear_highlight()
        except (RuntimeError, AttributeError) as e:
            # UI对象已被删除，跳过操作
            pass

    def test_image_send(self):
        """测试图片发送功能"""
        if not self.selected_group:
            QMessageBox.warning(self, "警告", "请先选择一个群组")
            return

        # 让用户选择图片文件
        from PyQt6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图片文件", "",
            "图片文件 (*.png *.jpg *.jpeg *.gif *.webp);;所有文件 (*)"
        )

        if not file_path:
            return

        # 让用户输入图片说明
        from PyQt6.QtWidgets import QInputDialog
        caption, ok = QInputDialog.getText(
            self, "图片说明", "输入图片说明（可选）:", text="测试图片发送"
        )

        if not ok:
            return

        # 异步发送图片
        asyncio.create_task(self.send_test_image(file_path, caption))

    async def send_test_image(self, image_path, caption):
        """发送测试图片"""
        try:
            self.add_log_entry(f"🖼️ 开始测试图片发送: {image_path}", "info")

            # 检查文件是否存在
            import os
            if not os.path.exists(image_path):
                self.add_log_entry(f"❌ 图片文件不存在: {image_path}", "error")
                return

            # 获取群组ID
            group_id = self.selected_group['chat_id']

            # 选择一个可用的账号
            if not hasattr(self, 'group_accounts') or not self.group_accounts:
                self.add_log_entry("❌ 没有可用的账号", "error")
                return

            sender_acc = self.group_accounts[0]  # 使用第一个账号
            self.add_log_entry(f"👤 使用账号: {sender_acc['name']}", "info")

            # 获取客户端
            client = telegram_client.clients.get(sender_acc['session_name'])
            if not client or not client.is_connected():
                self.add_log_entry("❌ 客户端未连接", "error")
                return

            # 发送图片
            self.add_log_entry("📤 正在发送图片...", "info")
            sent_msg = await client.send_file(
                entity=group_id,
                file=image_path,
                caption=caption if caption else None
            )

            self.add_log_entry(f"✅ 图片发送成功! 消息ID: {sent_msg.id}", "success")

        except Exception as e:
            self.add_log_entry(f"❌ 图片发送失败: {str(e)}", "error")

    def manage_account_order(self):
        if not hasattr(self, 'group_accounts') or not self.group_accounts:
            QMessageBox.warning(self, "警告", "请先选择包含账号的群组")
            return

        dialog = AccountOrderDialog(self.group_accounts, self.account_execution_order, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.account_execution_order = dialog.get_order()
            self.add_log_entry("账号执行顺序已更新", "info")

    def execute_script(self):
        if not self.script_view.toPlainText().strip():
            QMessageBox.warning(self, "警告", "请加载剧本")
            return

        if not hasattr(self, 'selected_group') or not self.selected_group:
            QMessageBox.warning(self, "警告", "请选择群组")
            return

        lines = [line.strip() for line in self.script_view.toPlainText().split('\n') if line.strip()]

        if not lines:
            return

        # 准备账号映射 {1: account_info, 2: account_info}
        account_map = {}
        # 去重
        unique_order = []
        seen = set()
        for s in self.account_execution_order:
            if s not in seen:
                unique_order.append(s)
                seen.add(s)

        # 建立映射：剧本中的 1号 -> order[0]
        for i, session_name in enumerate(unique_order, 1):
            for acc in self.group_accounts:
                if acc['session_name'] == session_name:
                    account_map[i] = acc
                    self.add_log_entry(f"🔗 账号映射建立: 剧本{i}号 -> {acc.get('name', 'Unknown')} ({session_name})", "info")
                    break

        self.add_log_entry("🚀 开始执行剧本...", "info")
        self.add_log_entry(f"映射关系: {len(account_map)} 个账号已就位", "info")

        self.execute_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.pause_btn.setText("⏸️ 暂停执行")
        self.script_execution_paused = False
        self.sent_messages = {} # 重置消息记录

        if self.loop_execution:
            # 循环执行模式
            self.loop_task = asyncio.create_task(self._run_script_loop_forever(lines, account_map))
            self.loop_task.add_done_callback(self._on_loop_finished)
        else:
            # 单次执行模式
            self.script_task = asyncio.create_task(self._run_script_loop(lines, account_map))
            self.script_task.add_done_callback(self._on_script_finished)

    async def _run_script_loop_forever(self, lines, account_map):
        """循环执行剧本"""
        loop_count = 0
        while self.loop_execution:
            loop_count += 1
            self.add_log_entry(f"🔄 开始第 {loop_count} 轮循环执行", "info")

            try:
                await self._run_script_loop(lines, account_map)
                self.add_log_entry(f"✅ 第 {loop_count} 轮循环执行完成", "success")

                # 循环间隔
                if self.loop_execution:  # 检查是否还在循环模式
                    await asyncio.sleep(5)  # 5秒间隔后开始下一轮

            except asyncio.CancelledError:
                self.add_log_entry("🔄 循环执行被停止", "warning")
                break
            except Exception as e:
                self.add_log_entry(f"💥 循环执行出错: {str(e)}", "error")
                if self.loop_execution:
                    await asyncio.sleep(10)  # 出错后等待10秒再试

    async def _run_script_loop(self, lines, account_map):
        """核心异步执行循环 - 线性执行确保顺序安全"""
        try:
            total_lines = len(lines)
            group_id = self.selected_group['chat_id'] # 使用 ID 发送更稳定

            for index, line in enumerate(lines):
                line_number = index + 1

                # 高亮当前执行行
                self.highlight_current_line(line_number)

                # 1. 检查暂停
                while self.script_execution_paused:
                    await asyncio.sleep(0.5)

                # 2. 解析行内容
                # 格式: "1、R[3] @2：消息内容"
                try:
                    parts = line.split('、', 1)
                    if len(parts) < 2:
                        self.add_log_entry(f"第 {line_number} 行格式错误跳过", "warning")
                        continue

                    role_num = int(parts[0].strip())
                    content_part = parts[1].strip()

                    # 查找执行账号
                    sender_acc = account_map.get(role_num)
                    if not sender_acc:
                        self.add_log_entry(f"❌ 第 {line_number} 行: 找不到 {role_num} 号账号", "error")
                        continue

                    # 解析指令部分 (R[x], @x, [delay])
                    # 格式: "R[3] @2 [5s]：实际消息"
                    msg_content = content_part
                    reply_to_id = None
                    mentions = []
                    delay_extra = 0

                    if '：' in content_part:
                        meta_part, text_body = content_part.split('：', 1)
                        msg_content = text_body
                        self.add_log_entry(f"🔍 第{line_number}行检测到中文冒号，meta_part={meta_part[:50]}, text_body={text_body[:50]}...", "debug")
                    else:
                        msg_content = content_part
                        meta_part = content_part  # 用于后续的 @ 提及解析
                        self.add_log_entry(f"🔍 第{line_number}行未检测到中文冒号", "debug")

                    # 解析回复 (在中文冒号分支外，确保 meta_part 可用)
                    if '：' in content_part:
                        r_match = re.search(r'R\[(\d+)\]', meta_part)
                        if r_match:
                            target_line = int(r_match.group(1))
                            if target_line in self.sent_messages:
                                reply_to_id = self.sent_messages[target_line]
                            else:
                                self.add_log_entry(f"⚠️ 第 {line_number} 行: 引用 R[{target_line}] 不存在 (可能发送失败)", "warning")

                        # 解析提及 (@1, @2)
                        m_matches = re.findall(r'@(\d+)', meta_part)
                        self.add_log_entry(f"🔍 第{line_number}行@符号解析: 找到{m_matches}个@模式", "info")
                        for m_role in m_matches:
                            m_role = int(m_role)
                            if m_role in account_map:
                                mentions.append(account_map[m_role])
                                self.add_log_entry(f"🔍 第{line_number}行@账号映射: {m_role} -> {account_map[m_role].get('name', 'Unknown')}", "info")
                            else:
                                self.add_log_entry(f"⚠️ 第{line_number}行@账号映射失败: {m_role}不在account_map中", "warning")

                        # 解析额外延迟
                        d_match = re.search(r'\[(\d+)s\]', meta_part)
                        if d_match:
                            delay_extra = int(d_match.group(1))
                            self.add_log_entry(f"⏳ 额外等待 {delay_extra} 秒...", "info")
                            await asyncio.sleep(delay_extra)

                    # 3. 构建最终消息（处理 @mention）
                    # 如果有提及，我们需要在消息前加上提及文本
                    prefix_text = ""
                    for m_acc in mentions:
                        name = m_acc.get('real_first_name', m_acc['name'])

                        if m_acc.get('real_username'):
                            # 有用户名时使用@username格式
                            prefix_text += f"@{m_acc['real_username']} "
                        elif m_acc.get('real_id'):
                            # 没有用户名时使用TextMention格式
                            prefix_text += f"[{name}](tg://user?id={m_acc['real_id']}) "
                        else:
                            # 兜底方案：尝试使用名字作为@mention
                            prefix_text += f"@{name} "

                    # 检查是否包含图片（使用原始 content_part，因为 msg_content 可能被修改过）
                    image_path = None
                    image_caption = ""

                    if 'IMG:' in content_part:
                        self.add_log_entry(f"🖼️ 第{line_number}行检测到IMG指令", "info")
                        self.add_log_entry(f"📝 原始content_part: {content_part}", "info")

                        # 方法1：移除 IMG: 前缀，然后分割
                        remaining = content_part[content_part.index('IMG:') + 4:].strip()


                        # 尝试分割路径和说明（支持中英文冒号）
                        path = None
                        caption = ""

                        # 优先尝试中文冒号（你的格式）
                        if '：' in remaining:
                            parts = remaining.split('：', 1)
                            path = parts[0].strip()
                            caption = parts[1].strip() if len(parts) > 1 else ""
                        # 再尝试英文冒号（简单格式，如 path:caption）
                        elif ':' in remaining and remaining.count(':') == 1:
                            parts = remaining.split(':', 1)
                            path = parts[0].strip()
                            caption = parts[1].strip() if len(parts) > 1 else ""
                        else:
                            # 没有冒号，整句都是路径
                            path = remaining.strip()
                            caption = ""


                        if path:
                            image_path = path
                            image_caption = caption
                            self.add_log_entry(f"📂 解析路径: {image_path}", "info")
                            self.add_log_entry(f"📝 解析说明: {image_caption}", "info")

                            # 路径规范化处理（macOS/Windows通用）
                            from pathlib import Path
                            import sys

                            path_obj = Path(image_path)
                            if not path_obj.is_absolute():
                                # 如果是相对路径，转换为相对于项目根目录的绝对路径
                                if hasattr(sys, 'frozen'):
                                    # PyInstaller 打包后的路径
                                    base_dir = Path(sys.executable).parent
                                else:
                                    # 开发环境的路径
                                    base_dir = Path(__file__).parent.parent

                                path_obj = base_dir / image_path
                                self.add_log_entry(f"🔄 路径规范化: {base_dir} + {image_path} = {path_obj}", "info")

                            image_path = str(path_obj.resolve())

                            # 检查文件是否存在
                            if not Path(image_path).exists():
                                self.add_log_entry(f"❌ 第{line_number}行图片文件不存在: {image_path}", "error")
                                image_path = None
                            else:
                                file_size = Path(image_path).stat().st_size
                                self.add_log_entry(f"✅ 第{line_number}行图片文件存在，大小: {file_size} bytes ({file_size/1024:.1f} KB)", "success")
                        else:
                            self.add_log_entry(f"❌ 第{line_number}行图片路径解析失败: {msg_content}", "error")

                    # 调试日志：显示图片解析结果
                    if image_path:
                        self.add_log_entry(f"🖼️ 第{line_number}行检测到图片: {image_path}", "info")
                        self.add_log_entry(f"📝 图片说明: '{image_caption}'", "info")

                    # 构建最终文本（如果有图片，只发送@mention和图片caption）
                    if image_path:
                        final_text = (prefix_text + image_caption).strip()
                    else:
                        final_text = (prefix_text + msg_content).strip()

                    # 添加调试日志
                    if mentions:
                        self.add_log_entry(f"🔍 第{line_number}行@mention解析: 找到{len(mentions)}个提及", "info")
                    else:
                        self.add_log_entry(f"🔍 第{line_number}行@mention解析: 无提及", "info")

                    # 4. 发送消息或图片 (Await 等待结果!)
                    client = telegram_client.clients.get(sender_acc['session_name'])
                    if client and client.is_connected():
                        if image_path:
                             # 路径已经在上面验证过了，直接发送

                            # 发送图片
                            try:
                                self.add_log_entry(f"📤 正在发送图片到群组 {group_id}...", "info")
                                self.add_log_entry(f"📁 图片路径: {image_path}", "info")
                                self.add_log_entry(f"📝 图片说明: '{final_text}'", "info")
                                self.add_log_entry(f"📊 账号: {sender_acc.get('name', 'Unknown')}", "info")

                                sent_msg = await client.send_file(
                                    entity=group_id,
                                    file=image_path,
                                    caption=final_text if final_text else None,
                                    reply_to=reply_to_id
                                )

                                file_name = image_path.split('/')[-1]
                                self.add_log_entry(f"✅ 第{line_number}行图片发送成功! 消息ID: {sent_msg.id}", "success")
                                self.add_log_entry(f"🖼️ 图片文件名: {file_name}", "info")
                            except Exception as img_error:
                                self.add_log_entry(f"❌ 第{line_number}行图片发送失败: {str(img_error)}", "error")
                                import traceback
                                traceback.print_exc()
                                continue
                        else:
                            # 发送纯文本消息
                            sent_msg = await client.send_message(
                                entity=group_id,
                                message=final_text,
                                reply_to=reply_to_id,
                                parse_mode='md' # 启用 Markdown 以支持 text mention
                            )
                            self.add_log_entry(f"✅ 第 {line_number} 行发送成功: {final_text[:20]}...", "success")

                        # 记录成功 ID
                        self.sent_messages[line_number] = sent_msg.id
                    else:
                        self.add_log_entry(f"❌ 第 {line_number} 行失败: 客户端未连接", "error")

                except Exception as e:
                    self.add_log_entry(f"❌ 第 {line_number} 行执行异常: {str(e)}", "error")

                # 5. 随机间隔等待 (最后一行除外)
                if index < total_lines - 1:
                    wait_time = random.uniform(
                        self.min_interval_spinbox.value(),
                        self.max_interval_spinbox.value()
                    )
                    self.add_log_entry(f"💤 等待 {wait_time:.1f} 秒...", "info")
                    await asyncio.sleep(wait_time)

        except asyncio.CancelledError:
            self.add_log_entry("🛑 剧本执行被停止", "warning")
            self.clear_highlight()  # 停止时清除高亮

        except Exception as e:
            self.add_log_entry(f"💥 致命错误: {str(e)}", "error")
            # 出错时保留最后一行高亮，方便排查

    # --- 高亮相关方法 ---
    def highlight_current_line(self, line_number):
        """高亮指定行号（1-based index）"""
        if line_number <= 0:
            return

        # 安全检查：确保UI对象仍然存在
        try:
            if not hasattr(self, 'script_view') or self.script_view is None:
                return

            extra_selections = []

            # 创建高亮选区
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#FFFF00")  # 亮黄色
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)

            # 移动光标到指定行
            cursor = self.script_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.MoveAnchor, line_number - 1)
            selection.cursor = cursor

            # 清除选中状态（只保留背景色），避免干扰
            selection.cursor.clearSelection()

            extra_selections.append(selection)

            # 应用高亮
            self.script_view.setExtraSelections(extra_selections)

            # 自动滚动确保当前行可见
            self.script_view.setTextCursor(cursor)
            self.script_view.ensureCursorVisible()

        except (RuntimeError, AttributeError) as e:
            # UI对象已被删除，跳过高亮
            pass

    def clear_highlight(self):
        """清除所有高亮"""
        self.script_view.setExtraSelections([])

    def _on_script_finished(self, task):
        self.execute_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)

        # 执行完毕后清除高亮
        self.clear_highlight()

        if task.exception():
             pass # 已在 loop 中捕获
        else:
             self.add_log_entry("🏁 剧本全部执行完毕！", "success")

    def _on_loop_finished(self, task):
        self.execute_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.clear_highlight()

        if task.exception():
            pass # 已在 loop 中捕获
        else:
            self.add_log_entry("🔄 循环执行已停止", "info")

    def add_log_entry(self, message, level="info"):
        # 安全检查：确保UI对象仍然存在
        try:
            if not hasattr(self, 'execution_log') or self.execution_log is None:
                # UI对象不存在，只在控制台输出
                timestamp = datetime.now().strftime("%H:%M:%S")
                icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
                icon = icons.get(level, "ℹ️")
                print(f"[{timestamp}] {icon} {message}")
                return

            timestamp = datetime.now().strftime("%H:%M:%S")
            icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
            icon = icons.get(level, "ℹ️")
            color = {"info": "black", "success": "green", "warning": "orange", "error": "red"}.get(level, "black")

            self.execution_log.append(f'<span style="color:{color}">[{timestamp}] {icon} {message}</span>')

            # 自动滚动到底部
            cursor = self.execution_log.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.execution_log.setTextCursor(cursor)

        except (RuntimeError, AttributeError) as e:
            # UI对象已被删除，只在控制台输出
            timestamp = datetime.now().strftime("%H:%M:%S")
            icons = {"info": "ℹ️", "success": "✅", "warning": "⚠️", "error": "❌"}
            icon = icons.get(level, "ℹ️")
            print(f"[{timestamp}] {icon} {message} (UI对象已删除: {e})")


class ScriptPage(QWidget):
    """剧本执行页面 - 多标签页版本"""

    def __init__(self):
        super().__init__()
        self.tab_counter = 1
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 页面标题
        title = QLabel("剧本执行")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333; margin-bottom: 10px;")
        layout.addWidget(title)

        description = QLabel("支持同时给多个群组执行剧本，支持循环执行模式")
        description.setStyleSheet("color: #666; margin-bottom: 20px;")
        layout.addWidget(description)

        # 标签页控制栏
        tab_control_layout = QHBoxLayout()

        self.add_tab_btn = QPushButton("➕ 添加标签页")
        self.add_tab_btn.setProperty("class", "SuccessBtn")
        self.add_tab_btn.clicked.connect(lambda: self.add_new_tab())
        tab_control_layout.addWidget(self.add_tab_btn)

        tab_control_layout.addStretch()

        self.stop_all_btn = QPushButton("🛑 停止所有执行")
        self.stop_all_btn.setProperty("class", "DangerBtn")
        self.stop_all_btn.clicked.connect(self.stop_all_executions)
        tab_control_layout.addWidget(self.stop_all_btn)

        layout.addLayout(tab_control_layout)

        # 标签页容器
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab_widget.customContextMenuRequested.connect(self.show_tab_context_menu)
        layout.addWidget(self.tab_widget)

        # 创建初始标签页
        self.add_new_tab()

    def add_new_tab(self, tab_name=None):
        """添加新标签页"""
        if tab_name is None:
            tab_name = f"剧本{self.tab_counter}"
            self.tab_counter += 1

        # 创建新标签页
        script_tab = ScriptTab(tab_name)
        tab_index = self.tab_widget.addTab(script_tab, tab_name)

        # 设置标签页图标（暂时移除，避免图标问题）
        # self.tab_widget.setTabIcon(tab_index, QIcon())

        # 切换到新标签页
        self.tab_widget.setCurrentIndex(tab_index)

        return script_tab

    def close_tab(self, index):
        """关闭标签页"""
        if self.tab_widget.count() <= 1:
            QMessageBox.warning(self, "警告", "至少需要保留一个标签页")
            return

        tab_widget = self.tab_widget.widget(index)
        if hasattr(tab_widget, 'stop_script_execution'):
            tab_widget.stop_script_execution()

        self.tab_widget.removeTab(index)

    def show_tab_context_menu(self, position):
        """显示标签页右键菜单"""
        if self.tab_widget.tabBar().tabAt(position) == -1:
            return

        menu = QMenu(self)

        rename_action = QAction("重命名标签页", self)
        rename_action.triggered.connect(lambda: self.rename_current_tab())
        menu.addAction(rename_action)

        menu.addSeparator()

        duplicate_action = QAction("复制标签页", self)
        duplicate_action.triggered.connect(lambda: self.duplicate_current_tab())
        menu.addAction(duplicate_action)

        menu.exec(self.tab_widget.mapToGlobal(position))

    def rename_current_tab(self):
        """重命名当前标签页"""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1:
            return

        current_name = self.tab_widget.tabText(current_index)
        new_name, ok = QInputDialog.getText(self, "重命名标签页", "输入新的标签页名称:",
                                          text=current_name)
        if ok and new_name.strip():
            self.tab_widget.setTabText(current_index, new_name.strip())
            current_tab = self.tab_widget.widget(current_index)
            if hasattr(current_tab, 'tab_name'):
                current_tab.tab_name = new_name.strip()
            if hasattr(current_tab, 'tab_title'):
                current_tab.tab_title.setText(f"📄 {new_name.strip()}")

    def duplicate_current_tab(self):
        """复制当前标签页"""
        current_index = self.tab_widget.currentIndex()
        if current_index == -1:
            return

        current_tab = self.tab_widget.widget(current_index)
        current_name = self.tab_widget.tabText(current_index)

        # 创建新标签页
        new_tab_name = f"{current_name}副本"
        new_tab = self.add_new_tab(new_tab_name)

        # 复制设置
        if hasattr(current_tab, 'current_file_path') and current_tab.current_file_path:
            new_tab.current_file_path = current_tab.current_file_path
            new_tab.file_status_label.setText(f"已加载: {current_tab.current_file_path.split('/')[-1]}")
            new_tab.script_view.setPlainText(current_tab.script_view.toPlainText())

        if hasattr(current_tab, 'selected_group') and current_tab.selected_group:
            new_tab.selected_group = current_tab.selected_group
            new_tab.group_info.setText(f"已选择: {current_tab.selected_group['title']}")

        if hasattr(current_tab, 'group_accounts'):
            new_tab.group_accounts = current_tab.group_accounts.copy()

        if hasattr(current_tab, 'account_execution_order'):
            new_tab.account_execution_order = current_tab.account_execution_order.copy()

        # 复制间隔设置
        new_tab.min_interval_spinbox.setValue(current_tab.min_interval_spinbox.value())
        new_tab.max_interval_spinbox.setValue(current_tab.max_interval_spinbox.value())

    def stop_all_executions(self):
        """停止所有标签页的执行"""
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            if hasattr(tab, 'stop_script_execution'):
                tab.stop_script_execution()

        QMessageBox.information(self, "完成", "已停止所有剧本执行")

    def get_current_tab(self):
        """获取当前活跃的标签页"""
        current_index = self.tab_widget.currentIndex()
        if current_index >= 0:
            return self.tab_widget.widget(current_index)
        return None


class AccountOrderDialog(QDialog):
    """账号顺序管理对话框"""
    def __init__(self, accounts, current_order, parent=None):
        super().__init__(parent)
        self.accounts = accounts
        self.current_order = current_order.copy()
        self.account_map = {acc['session_name']: acc for acc in accounts}
        self.setWindowTitle("账号执行顺序管理")
        self.resize(500, 400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        title = QLabel("拖拽调整账号执行顺序（数字1表示剧本中的1号）")
        title.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)

        # 确保所有 session 都在列表中
        seen = set()
        # 先添加已排序的
        for session_name in self.current_order:
            if session_name in self.account_map:
                self._add_item(self.account_map[session_name])
                seen.add(session_name)
        # 添加未排序的新账号
        for acc in self.accounts:
            if acc['session_name'] not in seen:
                self._add_item(acc)
        self.update_item_numbers()

        layout.addWidget(self.list_widget)

        btn_box = QHBoxLayout()
        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(self.reset_order)
        btn_box.addWidget(reset_btn)
        btn_box.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self.accept)
        btn_box.addWidget(ok_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)

    def _add_item(self, account):
        item_text = f"{account['name']} ({account['phone']})"
        item = QListWidgetItem(item_text)
        item.setData(Qt.ItemDataRole.UserRole, account['session_name'])
        self.list_widget.addItem(item)

    def update_item_numbers(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            text = item.text().split('. ', 1)[-1]
            item.setText(f"{i + 1}. {text}")

    def reset_order(self):
        self.list_widget.clear()
        for acc in self.accounts:
            self._add_item(acc)
        self.update_item_numbers()

    def get_order(self):
        return [self.list_widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list_widget.count())]


class GroupSelectDialog(QDialog):
    """群组选择对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_group = None
        self.setWindowTitle("选择执行群组")
        self.resize(400, 300)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        title = QLabel("请选择要执行剧本的群组")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 15px;")
        layout.addWidget(title)
        self.group_list = QListWidget()
        self.group_list.itemDoubleClicked.connect(self.on_group_double_clicked)
        self.load_groups_from_db()
        layout.addWidget(self.group_list)
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        select_btn = QPushButton("选择")
        select_btn.clicked.connect(self.on_select_clicked)
        buttons_layout.addWidget(select_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def load_groups_from_db(self):
        async def _load():
            try:
                groups = await db_manager.get_managed_groups()
                self.populate_groups(groups)
            except Exception:
                self.populate_groups([])

        # 安全地创建任务，避免在应用程序关闭时出现未等待的协程警告
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(_load())
            task.add_done_callback(lambda t: t.exception() if t.exception() else None)
        except RuntimeError:
            # 如果没有运行中的事件循环，直接运行
            import asyncio as asyncio_module
            loop = asyncio_module.new_event_loop()
            asyncio_module.set_event_loop(loop)
            try:
                loop.run_until_complete(_load())
            finally:
                loop.close()

    def populate_groups(self, groups):
        self.group_list.clear()
        if not groups:
            item = QListWidgetItem("未找到已管理的群组")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.group_list.addItem(item)
            return
        for group in groups:
            display_text = f"{group['title']}"
            if group.get('username'):
                display_text += f" (@{group['username']})"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, group)
            self.group_list.addItem(item)

    def on_group_double_clicked(self, item):
        self.selected_group = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def on_select_clicked(self):
        current_item = self.group_list.currentItem()
        if current_item:
            self.selected_group = current_item.data(Qt.ItemDataRole.UserRole)
            self.accept()
        else:
            QMessageBox.warning(self, "警告", "请先选择一个群组")
