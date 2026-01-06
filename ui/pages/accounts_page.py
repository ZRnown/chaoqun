from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
                             QPushButton, QLabel, QMessageBox, QListWidgetItem,
                             QProgressBar, QFrame, QDialog, QTextEdit, QFormLayout,
                             QFileDialog, QLineEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor
from pathlib import Path
import asyncio
import platform
from telethon import TelegramClient
from telethon.sessions import StringSession
from config import config
from core.database import db_manager
from core.telegram_client import telegram_client
from loguru import logger


class AccountsPage(QWidget):
    """账号管理页面"""

    def __init__(self):
        super().__init__()
        self.accounts_data = []  # 存储账号数据
        self.import_worker = None  # 导入工作线程
        self.workers = []  # 存储工作线程引用
        self.setup_ui()
        # 延迟一小段时间加载，确保主循环已就绪
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.load_accounts_from_db)

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # 页面标题
        title = QLabel("账号管理")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #333; margin-bottom: 10px;")
        layout.addWidget(title)

        description = QLabel("管理您的Telegram账号，包括添加、删除和状态监控")
        description.setStyleSheet("color: #666; margin-bottom: 20px;")
        description.setProperty("class", "Subtitle")
        layout.addWidget(description)

        # 统计信息栏
        stats_layout = QHBoxLayout()
        self.stats_total = QLabel("总账号: 0")
        self.stats_online = QLabel("在线: 0")
        self.stats_offline = QLabel("离线: 0")

        stats_layout.addWidget(self.stats_total)
        stats_layout.addWidget(self.stats_online)
        stats_layout.addWidget(self.stats_offline)
        stats_layout.addStretch()

        layout.addLayout(stats_layout)

        # 主要内容区域
        content_layout = QHBoxLayout()

        # 左侧：账号列表
        list_layout = QVBoxLayout()
        list_title = QLabel("账号列表")
        list_layout.addWidget(list_title)

        self.account_list = QListWidget()
        self.account_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.account_list.itemSelectionChanged.connect(self.on_selection_changed)
        list_layout.addWidget(self.account_list)

        list_widget = QWidget()
        list_widget.setLayout(list_layout)
        content_layout.addWidget(list_widget, 2)

        # 右侧：操作面板
        actions_panel = QWidget()
        actions_layout = QVBoxLayout(actions_panel)
        actions_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        actions_title = QLabel("账号操作")
        actions_layout.addWidget(actions_title)

        # 账号操作按钮
        self.btn_add = QPushButton("➕ 添加账号")
        self.btn_add.setMinimumWidth(100)
        self.btn_add.setProperty("class", "SuccessBtn")
        self.btn_add.clicked.connect(self.bulk_add_accounts)  # 现在连接到批量添加功能
        actions_layout.addWidget(self.btn_add)

        actions_layout.addSpacing(20)

        self.btn_start = QPushButton("▶️ 启动账号")
        self.btn_start.setProperty("class", "PrimaryBtn")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start_selected_accounts)
        actions_layout.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹️ 停止账号")
        self.btn_stop.setProperty("class", "DangerBtn")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_selected_accounts)
        actions_layout.addWidget(self.btn_stop)

        actions_layout.addSpacing(20)

        self.btn_delete = QPushButton("🗑️ 删除账号")
        self.btn_delete.setProperty("class", "DangerBtn")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self.delete_selected_accounts)
        actions_layout.addWidget(self.btn_delete)

        actions_layout.addSpacing(20)

        actions_layout.addStretch()

        # 账号详情面板
        details_layout = QVBoxLayout()
        details_title = QLabel("账号详情")
        details_layout.addWidget(details_title)

        self.details_info = QLabel("请选择一个账号查看详情")
        self.details_info.setWordWrap(True)
        details_layout.addWidget(self.details_info)

        details_widget = QWidget()
        details_widget.setLayout(details_layout)
        actions_layout.addWidget(details_widget)

        content_layout.addWidget(actions_panel, 1)

        layout.addLayout(content_layout)

        # 进度条（用于批量操作）
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #e0e0e0;
                border-radius: 3px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #007AFF;
            }
        """)
        layout.addWidget(self.progress_bar)

    def load_accounts_from_db(self):
        """从数据库加载账号列表 (Fixed: 使用 asyncio.create_task)"""
        async def _load():
            try:
                sessions = await db_manager.get_all_sessions()
                self.accounts_data = []

                for session in sessions:
                    user_name = session.get('user_name', '').strip()
                    session_name = session.get('session_name', '').strip()
                    phone_number = session.get('phone_number', '').strip()

                    # 优先使用user_name，如果为空则使用session_name
                    display_name = user_name if user_name else session_name
                    if not display_name:
                        display_name = '未知用户'

                    # 如果phone_number为空，尝试从user_name中提取
                    if not phone_number and '(' in user_name and ')' in user_name:
                        # 从格式如"莫莫 (959690312815)"中提取手机号
                        try:
                            phone_part = user_name.split('(')[-1].split(')')[0]
                            if phone_part.isdigit():
                                phone_number = phone_part
                        except:
                            pass

                    account_data = {
                        'name': display_name,
                        'phone': phone_number if phone_number else '未知',
                        'status': 'online' if session.get('is_active', False) else 'offline',
                        'session_file': session.get('session_file_path', ''),
                        'session_name': session_name
                    }
                    # 确保所有必需的字段都存在
                    if not account_data.get('session_name'):
                        logger.warning(f"跳过无效的session: {session_name}")
                        continue
                    self.accounts_data.append(account_data)

                # UI更新必须在主线程，这里已经是主线程的异步回调，所以安全
                self.load_accounts_ui()

            except Exception as e:
                print(f"Load Error: {e}")
                QMessageBox.critical(self, "错误", f"加载账号数据失败: {str(e)}")

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

    def load_accounts_ui(self):
        """更新UI显示账号列表"""
        try:
            self.account_list.clear()

            for account in self.accounts_data:
                # 再次验证数据完整性
                if not isinstance(account, dict) or 'session_name' not in account:
                    logger.error(f"跳过无效的账号数据: {account}")
                    continue

                item_text = f"{account['name']} ({account['phone']})"
                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, account)

                # 根据状态设置颜色
                if account['status'] == 'online':
                    item.setBackground(QColor("#d4edda"))  # 浅绿色
                    item.setForeground(QColor("#155724"))  # 深绿色
                else:
                    item.setBackground(QColor("#f8f9fa"))  # 浅灰色
                    item.setForeground(QColor("#6c757d"))  # 灰色

                self.account_list.addItem(item)

            self.update_stats()

        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载账号列表失败: {str(e)}")

    def update_stats(self):
        """更新统计信息"""
        total_count = self.account_list.count()
        online_count = 0
        offline_count = 0

        for i in range(total_count):
            item = self.account_list.item(i)
            account = item.data(Qt.ItemDataRole.UserRole)
            if account.get('status') == 'online':
                online_count += 1
            else:
                offline_count += 1

        self.stats_total.setText(f"总账号: {total_count}")
        self.stats_online.setText(f"在线: {online_count}")
        self.stats_offline.setText(f"离线: {offline_count}")

    def on_selection_changed(self):
        """选择改变时更新按钮状态"""
        selected_count = len(self.account_list.selectedItems())

        self.btn_start.setEnabled(selected_count > 0)
        self.btn_stop.setEnabled(selected_count > 0)
        self.btn_delete.setEnabled(selected_count > 0)

        # 更新详情面板
        if selected_count == 1:
            item = self.account_list.selectedItems()[0]
            account = item.data(Qt.ItemDataRole.UserRole)
            status_text = "在线" if account.get('status') == 'online' else "离线"
            details = f"""
账号名称: {account['name']}
手机号: {account['phone']}
状态: {status_text}
            """.strip()
            self.details_info.setText(details)
        else:
            self.details_info.setText(f"已选择 {selected_count} 个账号")

    def bulk_add_accounts(self):
        """批量添加账号 - 从session文件导入"""
        dialog = BulkAddDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            sessions_to_add = dialog.get_accounts()
            if sessions_to_add:
                # 创建并启动导入工作线程
                self.import_worker = SessionImportWorker(sessions_to_add, self.accounts_data.copy())
                self.import_worker.import_completed.connect(self._on_import_completed)
                self.import_worker.error_occurred.connect(self._on_import_error)
                self.workers.append(self.import_worker)
                self.import_worker.start()


    def start_selected_accounts(self):
        """启动选中的账号"""
        selected_items = self.account_list.selectedItems()
        if not selected_items:
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.btn_start.setEnabled(False)

        session_names = []
        for item in selected_items:
            account = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(account, dict) or 'session_name' not in account:
                continue
            session_names.append(account['session_name'])

        async def _start_async():
            try:
                success_count = 0
                failed_sessions = []
                total = len(session_names)

                for session_name in session_names:
                    try:
                        # 核心修改：直接await telegram_client操作，而不是在线程中
                        if await telegram_client.start_session(session_name):
                            success_count += 1
                        else:
                            failed_sessions.append(f"{session_name} (启动失败)")
                    except Exception as e:
                        error_msg = str(e)
                        if "expired" in error_msg.lower() or "session" in error_msg.lower():
                            failed_sessions.append(f"{session_name} (Session过期)")
                        else:
                            failed_sessions.append(f"{session_name} (错误: {error_msg[:20]})")

                # 处理结果
                self.progress_bar.setVisible(False)
                self.btn_start.setEnabled(True)

                # 更新内存状态
                for account in self.accounts_data:
                    # 简单逻辑：如果没在失败列表里且在本次操作列表中，则设为online
                    if account['session_name'] in session_names:
                        is_failed = any(account['session_name'] in f for f in failed_sessions)
                        if not is_failed:
                            account['status'] = 'online'

                self.load_accounts_ui()

                message = f"启动操作完成，成功: {success_count}/{total}"
                if failed_sessions:
                    message += f"\n\n失败账号:\n" + "\n".join(failed_sessions[:3])
                    if len(failed_sessions) > 3:
                        message += f"\n... 等 {len(failed_sessions)-3} 个"

                QMessageBox.information(self, "完成", message)

            except Exception as e:
                self.progress_bar.setVisible(False)
                self.btn_start.setEnabled(True)
                QMessageBox.critical(self, "错误", f"启动过程发生异常: {str(e)}")

        self._run_async_task(_start_async())

    def stop_selected_accounts(self):
        """停止选中的账号"""
        selected_items = self.account_list.selectedItems()
        if not selected_items:
            return

        # 收集要停止的session名称
        session_names = []
        for item in selected_items:
            account = item.data(Qt.ItemDataRole.UserRole)
            session_names.append(account['session_name'])

        async def _stop_async():
            try:
                for session_name in session_names:
                    try:
                        await telegram_client.stop_session(session_name)
                    except Exception as e:
                        logger.error(f"停止账号 {session_name} 失败: {e}")

                # 更新状态
                for account in self.accounts_data:
                    if account['session_name'] in session_names:
                        account['status'] = 'offline'

                self.btn_stop.setEnabled(True)
                self.load_accounts_ui()
                QMessageBox.information(self, "成功", "已停止选中账号")

            except Exception as e:
                self.btn_stop.setEnabled(True)
                QMessageBox.critical(self, "错误", f"停止过程异常: {str(e)}")

        self._run_async_task(_stop_async())

    def delete_selected_accounts(self):
        """删除选中的账号"""
        selected_items = self.account_list.selectedItems()
        if not selected_items:
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(selected_items)} 个账号吗？\n\n此操作不可撤销！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.btn_delete.setEnabled(False)

            # 收集要删除的账号信息
            accounts_to_delete = []
            for item in selected_items:
                account = item.data(Qt.ItemDataRole.UserRole)
                accounts_to_delete.append(account)

            # 直接在主线程中执行异步操作
            import asyncio

            async def _delete_async():
                try:
                    deleted = []
                    for account in accounts_to_delete:
                        session_name = account['session_name']
                        try:
                            # 停止并删除session
                            await telegram_client.delete_session(session_name)
                            deleted.append(account)
                        except Exception as e:
                            logger.error(f"删除账号 {session_name} 失败: {e}")

                    # 从内存移除
                    for acc in deleted:
                        if acc in self.accounts_data:
                            self.accounts_data.remove(acc)

                    self.btn_delete.setEnabled(True)
                    self.load_accounts_ui()
                    QMessageBox.information(self, "成功", f"已删除 {len(deleted)} 个账号")

                except Exception as e:
                    self.btn_delete.setEnabled(True)
                    QMessageBox.critical(self, "错误", f"删除过程异常: {str(e)}")

            self._run_async_task(_delete_async())



    def cleanup_threads(self):
        """清理所有工作线程（在程序退出前调用）"""
        for worker in self.workers[:]:  # 复制列表以避免修改时的问题
            if worker.isRunning():
                worker.wait(3000)  # 等待最多3秒
            self.workers.remove(worker)

    def _on_import_completed(self, accounts_to_add):
        """导入完成回调"""
        added_count = len(accounts_to_add)
        if added_count > 0:
            # 添加账号到内存列表
            self.accounts_data.extend(accounts_to_add)

            # 保存到数据库并等待完成，然后刷新UI
            asyncio.create_task(self._save_and_refresh(accounts_to_add, added_count))
        else:
            QMessageBox.warning(self, "警告", "没有添加新的账号")
            # 清理导入线程
            if self.import_worker and self.import_worker in self.workers:
                self.workers.remove(self.import_worker)
                self.import_worker = None

    async def _save_and_refresh(self, accounts_to_add, added_count):
        """异步保存到数据库并刷新UI"""
        try:
            # 保存到数据库
            await self._save_accounts_async(accounts_to_add)

            # 重新加载显示
            self.load_accounts_ui()
            QMessageBox.information(self, "成功", f"成功添加了 {added_count} 个账号")

        except Exception as e:
            QMessageBox.warning(self, "警告", f"保存到数据库失败，但账号已添加到内存: {e}")
            # 即使保存失败，也刷新UI显示内存中的账号
            self.load_accounts_ui()
            QMessageBox.information(self, "部分成功", f"账号已添加到内存，但保存到数据库失败: {added_count} 个账号")

        finally:
            # 清理导入线程
            if self.import_worker and self.import_worker in self.workers:
                self.workers.remove(self.import_worker)
                self.import_worker = None

    def _on_start_completed(self, results):
        """启动完成处理"""
        success_count = results['success_count']
        failed_sessions = results['failed_sessions']

        self.progress_bar.setVisible(False)

        # 更新内存中的账号状态
        for account in self.accounts_data:
            if account['session_name'] in [s.split(' ')[0] for s in results.get('failed_sessions', []) if ' ' in s]:
                account['status'] = 'offline'
            else:
                # 假设启动的账号都成功了（这里可以优化，但暂时这样处理）
                account['status'] = 'online' if success_count > 0 else account['status']

        self.load_accounts_ui()  # 刷新UI状态

        message = f"尝试启动完成，成功: {success_count}/{results['total_count']}"
        if failed_sessions:
            message += f"\n\n失败的账号:\n" + "\n".join(f"• {session}" for session in failed_sessions[:3])
            if len(failed_sessions) > 3:
                message += f"\n... 等 {len(failed_sessions) - 3} 个账号"

        QMessageBox.information(self, "完成", message)

        # 清理工作线程
        if self.start_worker and self.start_worker in self.workers:
            self.workers.remove(self.start_worker)
            self.start_worker = None

    def _on_start_error(self, error_msg):
        """启动错误处理"""
        self.progress_bar.setVisible(False)
        QMessageBox.critical(self, "错误", f"启动账号时出现错误: {error_msg}")

        # 清理工作线程
        if self.start_worker and self.start_worker in self.workers:
            self.workers.remove(self.start_worker)
            self.start_worker = None

    def _on_stop_completed(self):
        """停止完成处理"""
        self.load_accounts_ui()
        QMessageBox.information(self, "成功", "已停止选中账号")

        # 清理工作线程
        if self.stop_worker and self.stop_worker in self.workers:
            self.workers.remove(self.stop_worker)
            self.stop_worker = None

    def _on_stop_error(self, error_msg):
        """停止错误处理"""
        QMessageBox.critical(self, "错误", f"停止账号时出现错误: {error_msg}")

        # 清理工作线程
        if self.stop_worker and self.stop_worker in self.workers:
            self.workers.remove(self.stop_worker)
            self.stop_worker = None

    def _on_delete_completed(self, deleted_accounts):
        """删除完成处理"""
        # 从内存数据中移除已删除的账号
        for account in deleted_accounts:
            if account in self.accounts_data:
                self.accounts_data.remove(account)

        self.load_accounts_ui()
        QMessageBox.information(self, "成功", "账号已删除")

        # 清理工作线程
        if self.delete_worker and self.delete_worker in self.workers:
            self.workers.remove(self.delete_worker)
            self.delete_worker = None

    def _on_delete_error(self, error_msg):
        """删除错误处理"""
        QMessageBox.critical(self, "错误", f"删除账号时出现错误: {error_msg}")

        # 清理工作线程
        if self.delete_worker and self.delete_worker in self.workers:
            self.workers.remove(self.delete_worker)
            self.delete_worker = None

    def _run_async_task(self, coro):
        """辅助方法：在主循环中运行协程"""
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(coro)
            # 捕获未处理的异常
            def handle_exception(t):
                if t.exception():
                    logger.error(f"Async task exception: {t.exception()}")
            task.add_done_callback(handle_exception)
        except RuntimeError:
            # 如果没有运行中的循环（极少情况），创建一个新的
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(coro)
            finally:
                loop.close()

    async def _save_accounts_async(self, accounts):
        """异步保存账号到数据库"""
        try:
            for account in accounts:
                session_name = account.get('session_name', account.get('name', 'unknown'))

                # 准备数据库数据
                session_data = {
                    'session_name': session_name,
                    'session_file_path': account.get('session_file', ''),
                    'phone_number': account.get('phone', ''),
                    'user_name': account.get('name', ''),
                    'is_active': account.get('status') == 'online'
                }

                # 保存到数据库
                await db_manager.save_session(**session_data)

            logger.info(f"Successfully saved {len(accounts)} accounts to DB")

        except Exception as e:
            logger.error(f"Save Error: {e}")
            raise e  # 重新抛出异常，让调用者处理

    def _cleanup_worker(self, worker):
        """清理已完成的线程引用"""
        if worker in self.workers:
            self.workers.remove(worker)

    def _on_save_error(self, worker, error_msg):
        """保存错误处理"""
        QMessageBox.warning(self, "警告", f"保存到数据库失败，但账号已添加到内存: {error_msg}")
        self._cleanup_worker(worker)

    def _on_import_error(self, error_msg):
        """导入错误处理"""
        QMessageBox.critical(self, "错误", f"导入过程中出现错误: {error_msg}")


class SessionImportWorker(QThread):
    """Session账号导入工作线程"""
    import_completed = pyqtSignal(list)  # 返回要添加的账号列表
    error_occurred = pyqtSignal(str)  # 错误信息

    def __init__(self, sessions, existing_accounts):
        super().__init__()
        self.sessions = sessions
        self.existing_accounts = existing_accounts  # 现有的账号列表，用于检查重复

    def run(self):
        """在工作线程中执行导入"""
        try:
            accounts_to_add = []

            for session_info in self.sessions:
                try:
                    session_file = session_info['session_file']
                    session_name = session_info['session_name']

                    # 快速验证session文件
                    import os
                    if not os.path.exists(session_file) or os.path.getsize(session_file) == 0:
                        # 文件不存在或为空，仍然添加基本信息
                        account_data = {
                            'name': session_name,
                            'phone': '文件无效',
                            'status': 'offline',
                            'session_file': session_file,
                            'session_name': session_name
                        }
                    else:
                        # 尝试快速验证session文件格式
                        try:
                            from telethon import TelegramClient
                            from telethon.sessions import StringSession
                            import asyncio

                            # 使用和SessionScanWorker相同的方法验证
                            async def validate_session():
                                # 尝试创建客户端实例来验证session文件
                                client = TelegramClient(
                                    session=str(session_file),
                                    api_id=config.telegram.api_id,
                                    api_hash=config.telegram.api_hash
                                )

                                try:
                                    # 尝试连接验证session
                                    await client.connect()

                                    # 检查是否已授权
                                    if await client.is_user_authorized():
                                        try:
                                            me = await client.get_me()
                                            phone = me.phone or '未知'
                                            return {
                                                'name': session_name,
                                                'phone': f'{me.first_name or "未知"} ({phone})',
                                                'status': 'offline',
                                                'session_file': session_file
                                            }
                                        except Exception:
                                            # 即使获取用户信息失败，也认为session有效
                                            return {
                                                'name': session_name,
                                                'phone': '验证通过',
                                                'status': 'offline',
                                                'session_file': session_file
                                            }
                                    else:
                                        return {
                                            'name': session_name,
                                            'phone': '未授权',
                                            'status': 'offline',
                                            'session_file': session_file
                                        }

                                finally:
                                    await client.disconnect()

                            # 创建事件循环验证session
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)

                            try:
                                account_data = loop.run_until_complete(validate_session())
                            finally:
                                loop.close()

                        except Exception as e:
                            # session文件格式错误，仍添加基本信息
                            error_msg = str(e)
                            if "Invalid base64" in error_msg or "Not a valid string" in error_msg:
                                error_msg = "无效的session文件格式"
                            elif "codec" in error_msg.lower():
                                error_msg = "文件编码格式错误"
                            elif "session文件为空" in error_msg:
                                error_msg = "session文件为空"
                            elif "无法读取" in error_msg:
                                error_msg = "无法读取session文件"
                            else:
                                error_msg = f"格式错误: {error_msg[:15]}"

                            account_data = {
                                'name': session_name,
                                'phone': error_msg,
                                'status': 'offline',
                                'session_file': session_file,
                                'session_name': session_name
                            }
                        except Exception as e:
                            # session文件格式错误，仍添加基本信息
                            error_msg = str(e)
                            if "Invalid base64" in error_msg or "Not a valid string" in error_msg:
                                error_msg = "无效的session文件格式"
                            elif "codec" in error_msg.lower():
                                error_msg = "文件编码格式错误"
                            elif "session文件为空" in error_msg:
                                error_msg = "session文件为空"
                            elif "无法读取" in error_msg:
                                error_msg = "无法读取session文件"
                            else:
                                error_msg = f"格式错误: {error_msg[:15]}"

                            account_data = {
                                'name': session_name,
                                'phone': error_msg,
                                'status': 'offline',
                                'session_file': session_file,
                                'session_name': session_name
                            }

                    # 检查是否已存在相同的账号（通过session文件路径）
                    exists = any(
                        acc.get('session_file') == session_file
                        for acc in self.existing_accounts
                    )

                    if not exists:
                        accounts_to_add.append(account_data)

                except Exception as e:
                    # 单个session处理失败，跳过
                    continue

            self.import_completed.emit(accounts_to_add)

        except Exception as e:
            self.error_occurred.emit(str(e))



class SessionScanWorker(QThread):
    """Session文件扫描工作线程"""
    progress_updated = pyqtSignal(int, str)  # 进度, 消息
    scan_completed = pyqtSignal(list)  # 结果
    error_occurred = pyqtSignal(str)  # 错误

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths

    def run(self):
        """在工作线程中执行扫描"""
        try:
            # 创建新的asyncio事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                result = loop.run_until_complete(self._scan_sessions_async())
                self.scan_completed.emit(result)
            finally:
                loop.close()

        except Exception as e:
            self.error_occurred.emit(str(e))

    async def _scan_sessions_async(self):
        """异步扫描session文件"""
        valid_sessions = []

        for i, file_path in enumerate(self.file_paths):
            try:
                session_file = Path(file_path)
                session_name = session_file.stem

                # 发送进度更新
                self.progress_updated.emit(i + 1, f"验证中: {session_name}")

                # 检查文件是否存在且不为空
                if not session_file.exists() or session_file.stat().st_size == 0:
                    self.progress_updated.emit(i + 1, f"错误: {session_name} - 文件不存在或为空")
                    continue

                # 尝试创建客户端实例来验证session文件
                try:
                    client = TelegramClient(
                        session=str(session_file),
                        api_id=config.telegram.api_id,
                        api_hash=config.telegram.api_hash
                    )

                    # 尝试加载session
                    await client.connect()

                    # 检查是否已连接和授权
                    if await client.is_user_authorized():
                        try:
                            me = await client.get_me()
                            user_info = f"{me.first_name or '未知'} ({me.phone or '无手机号'})"
                            status = "有效"
                        except Exception as e:
                            user_info = f"用户信息获取失败: {str(e)[:20]}..."
                            status = "部分有效"
                    else:
                        user_info = "未授权"
                        status = "未授权"

                    await client.disconnect()

                except Exception as e:
                    user_info = f"验证失败: {str(e)[:30]}..."
                    status = "无效"

                # 发送最终结果
                if status in ["有效", "部分有效"]:
                    self.progress_updated.emit(i + 1, f"✓ {session_name} - {user_info}")
                    valid_sessions.append({
                        'session_file': str(session_file),
                        'session_name': session_name
                    })
                else:
                    self.progress_updated.emit(i + 1, f"✗ {session_name} - {user_info}")

            except Exception as e:
                self.progress_updated.emit(i + 1, f"错误: {session_name} - {str(e)[:50]}...")
                continue

        return valid_sessions


class BulkAddDialog(QDialog):
    """添加账号对话框 - 通过session文件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加账号")
        self.resize(600, 500)
        self.found_sessions = []
        self.selected_files = []
        self.scan_worker = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        # 说明标签
        info_label = QLabel("选择Telethon session文件（可多选）。\n程序将验证选中的.session文件并导入有效的账号。")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; margin-bottom: 15px;")
        layout.addWidget(info_label)

        # 文件选择区域
        folder_layout = QHBoxLayout()

        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("选择session文件...")
        self.folder_input.setReadOnly(True)
        folder_layout.addWidget(self.folder_input)

        browse_btn = QPushButton("选择文件...")
        browse_btn.clicked.connect(self.browse_files)
        folder_layout.addWidget(browse_btn)

        layout.addLayout(folder_layout)

        # 扫描结果显示
        self.result_label = QLabel("请先选择文件夹")
        self.result_label.setStyleSheet("margin: 10px 0;")
        layout.addWidget(self.result_label)

        # session文件列表
        self.session_list = QListWidget()
        self.session_list.setMaximumHeight(200)
        layout.addWidget(self.session_list)

        # 进度条
        self.progress_label = QLabel("")
        layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 按钮
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(cancel_btn)

        scan_btn = QPushButton("扫描Session")
        scan_btn.clicked.connect(self.scan_sessions)
        buttons_layout.addWidget(scan_btn)

        import_btn = QPushButton("导入账号")
        import_btn.setProperty("class", "SuccessBtn")
        import_btn.clicked.connect(self.accept)
        import_btn.setEnabled(False)
        self.import_btn = import_btn
        buttons_layout.addWidget(import_btn)

        layout.addLayout(buttons_layout)

    def _on_scan_completed(self, valid_sessions):
        """扫描完成回调"""
        self.found_sessions = valid_sessions

        self.progress_bar.setVisible(False)
        self.progress_label.setText("")

        if valid_sessions:
            self.result_label.setText(f"验证完成，{len(valid_sessions)} 个有效session文件")
            self.import_btn.setEnabled(True)
        else:
            self.result_label.setText("没有找到有效的session文件")
            self.import_btn.setEnabled(False)

    def _on_progress_updated(self, index, message):
        """进度更新处理"""
        self.progress_bar.setValue(index)

        # 更新列表项状态
        if index <= self.session_list.count():
            item = self.session_list.item(index - 1)
            if item:
                item.setText(message)

    def _on_scan_error(self, error_msg):
        """扫描错误处理"""
        self.progress_bar.setVisible(False)
        self.progress_label.setText("")
        QMessageBox.critical(self, "错误", f"验证过程中出现错误: {error_msg}")

    def browse_files(self):
        """选择Session文件"""
        # macOS 特殊处理 - 确保文件对话框正常工作
        if platform.system() == "Darwin":
            # 在macOS上使用特定的对话框选项
            file_dialog = QFileDialog(self)
            file_dialog.setWindowTitle("选择Session文件")
            file_dialog.setNameFilter("Session文件 (*.session);;所有文件 (*)")
            file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)

            if file_dialog.exec():
                file_paths = file_dialog.selectedFiles()
            else:
                file_paths = []
        else:
            # 在其他平台使用标准对话框
            file_paths, _ = QFileDialog.getOpenFileNames(
                self, "选择Session文件", "", "Session文件 (*.session);;所有文件 (*)"
            )
        if file_paths:
            # 显示选择的文件数量
            self.folder_input.setText(f"已选择 {len(file_paths)} 个文件")
            self.selected_files = file_paths
            self.result_label.setText("点击'扫描Session'开始验证")
            self.session_list.clear()

            # 直接显示选择的文件
            for file_path in file_paths:
                file_name = Path(file_path).stem
                item = QListWidgetItem(f"{file_name} - 待验证")
                item.setData(Qt.ItemDataRole.UserRole, {
                    'session_file': file_path,
                    'session_name': file_name
                })
                self.session_list.addItem(item)

    def scan_sessions(self):
        """验证选中的session文件"""
        if not self.selected_files:
            QMessageBox.warning(self, "警告", "请先选择session文件")
            return

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(self.selected_files))
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"正在验证 {len(self.selected_files)} 个session文件...")
        self.found_sessions = []

        # 创建并启动工作线程
        self.scan_worker = SessionScanWorker(self.selected_files)
        self.scan_worker.progress_updated.connect(self._on_progress_updated)
        self.scan_worker.scan_completed.connect(self._on_scan_completed)
        self.scan_worker.error_occurred.connect(self._on_scan_error)

        self.scan_worker.start()


    def get_accounts(self):
        """返回要添加的账号列表"""
        return self.found_sessions


