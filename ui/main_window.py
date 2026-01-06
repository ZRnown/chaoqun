# ui/main_window.py

import sys
import platform
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QStackedWidget, QLabel, QPushButton, QButtonGroup)
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QCloseEvent

from ui.styles import get_stylesheet

# Import your pages
from ui.pages.accounts_page import AccountsPage
from ui.pages.groups_page import GroupsPage
from ui.pages.script_page import ScriptPage

class MainWindow(QMainWindow):
    """现代化主窗口 - 左侧边栏 + 内容区域"""

    def __init__(self):
        super().__init__()
        print("MainWindow: 开始初始化")

        self.setWindowTitle("Telegram 群组管理器 v2.0")
        self.resize(1200, 800)
        print("MainWindow: 基本属性设置完成")

        # macOS 特殊处理
        if platform.system() == "Darwin":  # macOS
            # 简化macOS窗口设置，避免样式问题
            self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)
            print("MainWindow: macOS特殊处理完成")

        # 应用现代化的样式表
        try:
            self.setStyleSheet(get_stylesheet())
            print("MainWindow: 样式表应用完成")
        except Exception as e:
            print(f"MainWindow: 样式表应用失败: {e}")
            # 不应用样式表，继续运行

        # 主布局容器
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QHBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        print("MainWindow: 主布局容器创建完成")

        # 1. 初始化侧边栏
        try:
            self.init_sidebar()
            print("MainWindow: 侧边栏初始化完成")
        except Exception as e:
            print(f"MainWindow: 侧边栏初始化失败: {e}")
            raise

        # 2. 初始化内容区域
        try:
            self.init_content_area()
            print("MainWindow: 内容区域初始化完成")
        except Exception as e:
            print(f"MainWindow: 内容区域初始化失败: {e}")
            raise

        # 3. 连接侧边栏到内容
        try:
            self.setup_connections()
            print("MainWindow: 连接设置完成")
        except Exception as e:
            print(f"MainWindow: 连接设置失败: {e}")
            raise

        # 默认显示第一个页面
        try:
            self.nav_group.button(0).setChecked(True)
            self.stack.setCurrentIndex(0)
            print("MainWindow: 默认页面设置完成")
        except Exception as e:
            print(f"MainWindow: 默认页面设置失败: {e}")
            raise

        # macOS 额外处理 - 在窗口初始化完成后再次确保属性正确
        if platform.system() == "Darwin":
            # 使用定时器延迟设置，确保窗口完全初始化后再设置属性
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self._ensure_macos_window_attributes)
            print("MainWindow: macOS额外处理设置完成")

        print("MainWindow: 初始化完成")

    def init_sidebar(self):
        """创建左侧导航栏"""
        self.sidebar = QWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(260)

        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(0, 25, 0, 25)
        layout.setSpacing(5)

        # 应用标题
        title = QLabel("TG 群管助手")
        title.setObjectName("AppTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        layout.addSpacing(20)

        # 导航按钮组
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        # 创建导航按钮
        self.btn_accounts = self.create_nav_btn("👥 账号管理", 0)
        self.btn_groups = self.create_nav_btn("💬 群组管理", 1)
        self.btn_scripts = self.create_nav_btn("🎭 剧本执行", 2)

        layout.addWidget(self.btn_accounts)
        layout.addWidget(self.btn_groups)
        layout.addWidget(self.btn_scripts)

        layout.addStretch()

        # 底部版本信息
        version = QLabel("v2.0.1")
        version.setStyleSheet("color: #7f8c8d; font-size: 10px; padding-left: 20px;")
        layout.addWidget(version)

        self.main_layout.addWidget(self.sidebar)

    def create_nav_btn(self, text, id):
        """创建导航按钮"""
        btn = QPushButton(text)
        btn.setProperty("class", "SidebarBtn")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.nav_group.addButton(btn, id)
        return btn

    def init_content_area(self):
        """初始化右侧内容区域"""
        self.content_container = QWidget()
        layout = QVBoxLayout(self.content_container)
        layout.setContentsMargins(25, 25, 25, 25)

        self.stack = QStackedWidget()

        # 实例化页面
        self.page_accounts = AccountsPage()
        self.page_groups = GroupsPage()
        self.page_scripts = ScriptPage()

        self.stack.addWidget(self.page_accounts)
        self.stack.addWidget(self.page_groups)
        self.stack.addWidget(self.page_scripts)

        layout.addWidget(self.stack)
        self.main_layout.addWidget(self.content_container)

    def setup_connections(self):
        """连接侧边栏到内容切换"""
        self.nav_group.idClicked.connect(self.stack.setCurrentIndex)

    def closeEvent(self, event: QCloseEvent):
        """程序关闭事件处理"""
        # 清理资源
        try:
            # 首先停止脚本执行
            if hasattr(self, 'page_scripts'):
                self.page_scripts.stop_script_execution()

            # 停止账号页面的工作线程
            if hasattr(self, 'page_accounts'):
                self.page_accounts.cleanup_threads()

            # 简单地标记应用程序即将退出，让main.py处理异步清理
            import sys
            sys.exit(0)

        except Exception as e:
            print(f"清理资源时出错: {e}")
            # 即使清理出错也要退出
            import sys
            sys.exit(1)

    def _macos_window_fix(self):
        """macOS窗口控制按钮修复"""
        if platform.system() == "Darwin":
            try:
                # 临时隐藏再显示来强制macOS重新绘制窗口控制按钮
                self.hide()
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(10, self.show)
            except Exception as e:
                print(f"macOS窗口修复失败: {e}")

    def _ensure_macos_window_attributes(self):
        """确保macOS上的窗口属性正确设置"""
        if platform.system() == "Darwin":
            # 重新设置窗口标志，确保控制按钮可用
            current_flags = self.windowFlags()
            new_flags = (Qt.WindowType.Window |
                        Qt.WindowType.WindowMinimizeButtonHint |
                        Qt.WindowType.WindowMaximizeButtonHint |
                        Qt.WindowType.WindowCloseButtonHint)

            if current_flags != new_flags:
                self.setWindowFlags(new_flags)
                self.show()  # 重新显示窗口以应用新标志

            # 重新激活窗口
            self.activateWindow()
            self.raise_()
            self.setFocus()

            # 再次设置模态属性
            self.setWindowModality(Qt.WindowModality.NonModal)

            # 强制刷新窗口
            self.repaint()

            # 对于macOS，尝试通过最小化/恢复来强制重绘窗口控制按钮
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(200, self._macos_window_fix)
