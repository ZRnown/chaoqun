#!/usr/bin/env python3
"""
GUI启动脚本 - 专门处理macOS显示问题
"""
import os
import sys
import platform

def setup_macos_display():
    """设置macOS显示环境"""
    if platform.system() == "Darwin":
        # 检查是否已经有DISPLAY设置
        if not os.environ.get('DISPLAY'):
            print("检测到macOS环境，设置DISPLAY=:0")
            os.environ['DISPLAY'] = ':0'

        # 设置其他macOS相关的环境变量
        os.environ.setdefault('QT_QPA_PLATFORM', 'cocoa')
        print(f"macOS显示环境设置完成 - DISPLAY={os.environ.get('DISPLAY')}")

def main():
    """主启动函数"""
    print("🚀 Telegram 群组管理器 GUI启动器")
    print("=" * 50)

    # 设置macOS显示环境
    setup_macos_display()

    # 检查是否在图形环境中
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        screen = app.primaryScreen()
        if screen:
            print(f"✅ 检测到图形环境 - 屏幕大小: {screen.size().width()}x{screen.size().height()}")
        else:
            print("⚠️ 未检测到屏幕，可能无法显示GUI")
            return 1
    except Exception as e:
        print(f"❌ PyQt6初始化失败: {e}")
        return 1

    # 导入并运行主程序
    try:
        print("正在启动主程序...")
        from main import start_application
        start_application()
        return 0
    except SystemExit as e:
        # start_application() 可能会调用 sys.exit()
        return e.code
    except Exception as e:
        print(f"❌ 主程序启动失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
