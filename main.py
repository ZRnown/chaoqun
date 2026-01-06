import sys
import asyncio
import platform
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from qasync import QEventLoop
from loguru import logger

# Import your refactored main window
from ui.main_window import MainWindow

# Import core modules
from core.database import init_database
from core.telegram_client import init_telegram_client

# Global Exception Hook to prevent crashes without logging
def exception_hook(exctype, value, traceback):
    logger.error(f"Uncaught exception: {value}", exc_info=(exctype, value, traceback))
    sys.__excepthook__(exctype, value, traceback)

sys.excepthook = exception_hook

# 添加全局异常处理器
import traceback
def global_exception_handler(exc_type, exc_value, exc_traceback):
    """全局异常处理器"""
    logger.error("未捕获的异常:")
    logger.error(f"异常类型: {exc_type}")
    logger.error(f"异常信息: {exc_value}")
    logger.error("详细堆栈:")
    for line in traceback.format_exception(exc_type, exc_value, exc_traceback):
        logger.error(line.strip())
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# 设置全局异常处理器
sys.excepthook = global_exception_handler

def start_application():
    """可导入的应用程序启动函数"""
    print("程序启动...")
    print("正在导入模块...")

    try:
        print("导入完成，开始初始化...")
        # 1. 创建 QApplication（必须在创建任何 QWidget 之前）
        global app
        app = QApplication(sys.argv)
        logger.info("QApplication创建成功")

        # 检查图形环境
        try:
            screen = app.primaryScreen()
            if screen:
                logger.info(f"主屏幕信息: {screen.size().width()}x{screen.size().height()}")
            else:
                logger.warning("未检测到主屏幕，可能在无图形环境中运行")
        except Exception as e:
            logger.warning(f"屏幕检测失败: {e}")

        # 检查环境变量
        import os
        display = os.environ.get('DISPLAY')
        logger.info(f"DISPLAY环境变量: {display}")

        if not display and platform.system() == "Darwin":
            logger.warning("macOS环境下未设置DISPLAY，可能导致GUI无法显示")
            # 尝试设置默认DISPLAY
            os.environ['DISPLAY'] = ':0'
            logger.info("已设置DISPLAY=:0")

        # macOS 特殊处理
        if platform.system() == "Darwin":
            app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, False)
            app.setAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta, False)
            # 重要：不要在最后一个窗口关闭时自动退出，让我们手动控制
            app.setQuitOnLastWindowClosed(False)
            logger.info("macOS特殊属性设置完成")

        # 2. 创建 qasync 事件循环
        try:
            logger.info("正在创建qasync事件循环...")
            loop = QEventLoop(app)
            logger.info("QEventLoop创建成功")

            asyncio.set_event_loop(loop)
            logger.info("事件循环设置完成")
        except Exception as e:
            logger.error(f"创建事件循环失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            raise

        async def async_main():
            try:
                logger.info("开始初始化后端服务...")

                # 初始化数据库
                logger.info("正在初始化数据库...")
                await init_database()
                logger.info("数据库初始化完成")

                # 初始化Telegram客户端
                logger.info("正在初始化Telegram客户端...")
                await init_telegram_client()
                logger.info("Telegram客户端初始化完成")

                logger.info("后端服务初始化完成")

                logger.info("创建主窗口...")
                try:
                    # 创建和显示主窗口（暂时禁用页面自动加载以避免异步问题）
                    logger.info("正在实例化MainWindow...")
                    window = MainWindow()
                    logger.info("MainWindow实例创建成功")

                    window.show()
                    logger.info("主窗口show()调用完成")

                    window.raise_()  # 确保窗口在前面
                    window.activateWindow()  # 激活窗口
                    logger.info("主窗口激活完成")

                    # 在 macOS 上额外确保窗口可见
                    if platform.system() == "Darwin":
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(100, lambda: window.raise_())

                    # 强制刷新和重绘
                    app.processEvents()
                    window.repaint()

                    logger.info(f"主窗口已创建和显示，大小: {window.size().width()}x{window.size().height()}")
                    logger.info(f"窗口位置: x={window.x()}, y={window.y()}")
                    logger.info(f"窗口是否可见: {window.isVisible()}")
                    logger.info(f"窗口是否最小化: {window.isMinimized()}")

                    # 尝试强制窗口到前台
                    from PyQt6.QtCore import QTimer
                    def force_show():
                        try:
                            window.show()
                            window.raise_()
                            window.activateWindow()
                            window.showNormal()  # 确保不是最小化状态
                            app.processEvents()
                            logger.info(f"强制显示后 - 可见: {window.isVisible()}, 最小化: {window.isMinimized()}")
                        except Exception as e:
                            logger.error(f"强制显示失败: {e}")

                    QTimer.singleShot(500, force_show)
                    QTimer.singleShot(1000, force_show)
                    QTimer.singleShot(2000, force_show)

                    logger.info("应用程序启动完成 - 窗口现在应该可见了")

                    return window

                except Exception as e:
                    logger.error(f"主窗口创建失败: {e}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    raise

            except Exception as e:
                logger.error(f"异步初始化失败: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
                raise

        # 4. 运行应用程序
        logger.info("准备启动事件循环")
        with loop:
            try:
                # 先运行异步初始化
                logger.info("开始异步初始化...")
                try:
                    logger.info("创建async_main任务...")
                    init_task = loop.create_task(async_main())
                    logger.info("任务创建成功，开始运行...")
                    window = loop.run_until_complete(init_task)
                    logger.info(f"异步初始化完成，窗口: {window}")
                except Exception as e:
                    logger.error(f"异步初始化失败: {e}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    raise

                # 重写窗口的关闭事件处理
                original_close_event = window.closeEvent

                def custom_close_event(event):
                    logger.info("主窗口关闭，准备退出应用程序...")
                    # 先调用原始的关闭事件处理
                    original_close_event(event)
                    # 如果事件被接受，停止事件循环
                    if event.isAccepted():
                        loop.stop()

                window.closeEvent = custom_close_event

                # 设置退出处理
                def handle_quit():
                    logger.info("收到退出信号，正在关闭应用程序...")
                    loop.stop()

                app.aboutToQuit.connect(handle_quit)
                logger.info("退出处理设置完成")

                # 运行事件循环，等待用户交互或退出信号
                logger.info("进入主事件循环，等待用户交互...")
                try:
                    loop.run_forever()
                except KeyboardInterrupt:
                    logger.info("收到键盘中断信号")
                finally:
                    logger.info("退出事件循环")

            except Exception as e:
                logger.error(f"事件循环错误: {e}")
                import traceback
                logger.error(f"详细错误: {traceback.format_exc()}")
            finally:
                # 取消所有待处理的异步任务
                logger.info("正在清理异步任务...")
                try:
                    # 取消所有待处理的任务
                    pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
                    if pending_tasks:
                        logger.info(f"取消 {len(pending_tasks)} 个待处理的异步任务")
                        for task in pending_tasks:
                            task.cancel()

                        # 等待所有任务完成或被取消
                        try:
                            loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                        except Exception as e:
                            logger.warning(f"取消任务时出错: {e}")

                except Exception as e:
                    logger.warning(f"清理任务时出错: {e}")

                # 执行最终清理
                logger.info("正在执行最终资源清理...")
                try:
                    # 创建新的清理事件循环，避免与正在关闭的循环冲突
                    cleanup_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(cleanup_loop)

                    async def async_cleanup():
                        try:
                            # 停止所有 Telegram 会话
                            from core.telegram_client import cleanup_telegram_client
                            await cleanup_telegram_client()

                            # 关闭数据库连接
                            from core.database import close_database
                            await close_database()

                            logger.info("资源清理完成")
                        except Exception as e:
                            logger.warning(f"清理过程中出错: {e}")

                    cleanup_loop.run_until_complete(async_cleanup())
                    cleanup_loop.close()

                except Exception as e:
                    logger.warning(f"最终清理出错: {e}")

    except Exception as e:
        logger.error(f"程序启动失败: {e}")
        import traceback
        logger.error(f"详细错误: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    print("程序启动...")
    print("正在导入模块...")

    try:
        print("导入完成，开始初始化...")
        # 1. 创建 QApplication（必须在创建任何 QWidget 之前）
        app = QApplication(sys.argv)
        logger.info("QApplication创建成功")

        # 检查图形环境
        try:
            screen = app.primaryScreen()
            if screen:
                logger.info(f"主屏幕信息: {screen.size().width()}x{screen.size().height()}")
            else:
                logger.warning("未检测到主屏幕，可能在无图形环境中运行")
        except Exception as e:
            logger.warning(f"屏幕检测失败: {e}")

        # 检查环境变量
        import os
        display = os.environ.get('DISPLAY')
        logger.info(f"DISPLAY环境变量: {display}")

        if not display and platform.system() == "Darwin":
            logger.warning("macOS环境下未设置DISPLAY，可能导致GUI无法显示")
            # 尝试设置默认DISPLAY
            os.environ['DISPLAY'] = ':0'
            logger.info("已设置DISPLAY=:0")

        # macOS 特殊处理
        if platform.system() == "Darwin":
            app.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeMenuBar, False)
            app.setAttribute(Qt.ApplicationAttribute.AA_MacDontSwapCtrlAndMeta, False)
            # 重要：不要在最后一个窗口关闭时自动退出，让我们手动控制
            app.setQuitOnLastWindowClosed(False)
            logger.info("macOS特殊属性设置完成")

        # 2. 创建 qasync 事件循环
        try:
            logger.info("正在创建qasync事件循环...")
            loop = QEventLoop(app)
            logger.info("QEventLoop创建成功")

            asyncio.set_event_loop(loop)
            logger.info("事件循环设置完成")
        except Exception as e:
            logger.error(f"创建事件循环失败: {e}")
            import traceback
            logger.error(f"详细错误: {traceback.format_exc()}")
            raise

        async def async_main():
            try:
                logger.info("开始初始化后端服务...")

                # 初始化数据库
                logger.info("正在初始化数据库...")
                await init_database()
                logger.info("数据库初始化完成")

                # 初始化Telegram客户端
                logger.info("正在初始化Telegram客户端...")
                await init_telegram_client()
                logger.info("Telegram客户端初始化完成")

                logger.info("后端服务初始化完成")

                logger.info("创建主窗口...")
                try:
                    # 创建和显示主窗口（暂时禁用页面自动加载以避免异步问题）
                    logger.info("正在实例化MainWindow...")
                    window = MainWindow()
                    logger.info("MainWindow实例创建成功")

                    window.show()
                    logger.info("主窗口show()调用完成")

                    window.raise_()  # 确保窗口在前面
                    window.activateWindow()  # 激活窗口
                    logger.info("主窗口激活完成")

                    # 在 macOS 上额外确保窗口可见
                    if platform.system() == "Darwin":
                        from PyQt6.QtCore import QTimer
                        QTimer.singleShot(100, lambda: window.raise_())
                        logger.info("macOS额外窗口处理已设置")

                    # 强制刷新和重绘
                    app.processEvents()
                    window.repaint()

                    logger.info(f"主窗口已创建和显示，大小: {window.size().width()}x{window.size().height()}")
                    logger.info(f"窗口位置: x={window.x()}, y={window.y()}")
                    logger.info(f"窗口是否可见: {window.isVisible()}")
                    logger.info(f"窗口是否最小化: {window.isMinimized()}")
                    logger.info(f"窗口几何信息: {window.geometry()}")

                    # 尝试强制窗口到前台
                    from PyQt6.QtCore import QTimer
                    def force_show():
                        try:
                            window.show()
                            window.raise_()
                            window.activateWindow()
                            window.showNormal()  # 确保不是最小化状态
                            app.processEvents()
                            logger.info(f"强制显示后 - 可见: {window.isVisible()}, 最小化: {window.isMinimized()}")
                        except Exception as e:
                            logger.error(f"强制显示失败: {e}")

                    QTimer.singleShot(500, force_show)
                    QTimer.singleShot(1000, force_show)
                    QTimer.singleShot(2000, force_show)

                    logger.info("应用程序启动完成 - 窗口现在应该可见了")

                except Exception as e:
                    logger.error(f"主窗口创建失败: {e}")
                    import traceback
                    logger.error(f"详细错误: {traceback.format_exc()}")
                    raise

                # 重写窗口的关闭事件处理
                original_close_event = window.closeEvent

                def custom_close_event(event):
                    logger.info("主窗口关闭，准备退出应用程序...")
                    # 先调用原始的关闭事件处理
                    original_close_event(event)
                    # 如果事件被接受，停止事件循环
                    if event.isAccepted():
                        loop.stop()

                window.closeEvent = custom_close_event

            except Exception as e:
                logger.error(f"初始化失败: {e}")
                import traceback
                logger.error(f"详细错误信息: {traceback.format_exc()}")
                app.quit()

        # 清理将在事件循环结束后进行，而不是在 aboutToQuit 信号中
        # 这样可以避免 "Cannot run the event loop while another loop is running" 错误

                # 4. 运行应用程序
                logger.info("准备启动事件循环")
                with loop:
                    try:
                        # 暂时跳过异步初始化，先测试窗口显示
                        logger.info("跳过异步初始化，直接创建窗口...")

                        logger.info("创建主窗口...")
                        try:
                            # 创建和显示主窗口
                            logger.info("正在实例化MainWindow...")
                            window = MainWindow()
                            logger.info("MainWindow实例创建成功")

                            window.show()
                            logger.info("主窗口show()调用完成")

                            window.raise_()  # 确保窗口在前面
                            window.activateWindow()  # 激活窗口
                            logger.info("主窗口激活完成")

                            logger.info(f"主窗口已创建和显示，大小: {window.size().width()}x{window.size().height()}")
                            logger.info("主窗口创建成功，准备运行事件循环")

                        except Exception as e:
                            logger.error(f"主窗口创建失败: {e}")
                            import traceback
                            logger.error(f"详细错误: {traceback.format_exc()}")
                            raise

                        # 设置退出处理
                        def handle_quit():
                            logger.info("收到退出信号，正在关闭应用程序...")
                            loop.stop()

                        app.aboutToQuit.connect(handle_quit)
                        logger.info("退出处理设置完成")

                        # 运行事件循环，等待用户交互或退出信号
                        logger.info("进入主事件循环，等待用户交互...")
                        try:
                            loop.run_forever()
                        except KeyboardInterrupt:
                            logger.info("收到键盘中断信号")
                        finally:
                            logger.info("退出事件循环")

                    except Exception as e:
                        logger.error(f"事件循环错误: {e}")
                        import traceback
                        logger.error(f"详细错误: {traceback.format_exc()}")
            finally:
                # 取消所有待处理的异步任务
                logger.info("正在清理异步任务...")
                try:
                    # 取消所有待处理的任务
                    pending_tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
                    if pending_tasks:
                        logger.info(f"取消 {len(pending_tasks)} 个待处理的异步任务")
                        for task in pending_tasks:
                            task.cancel()

                        # 等待所有任务完成或被取消
                        try:
                            loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
                        except Exception as e:
                            logger.warning(f"取消任务时出错: {e}")

                except Exception as e:
                    logger.warning(f"清理任务时出错: {e}")

                # 执行最终清理
                logger.info("正在执行最终资源清理...")
                try:
                    # 创建新的清理事件循环，避免与正在关闭的循环冲突
                    cleanup_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(cleanup_loop)

                    async def async_cleanup():
                        try:
                            # 停止所有 Telegram 会话
                            from core.telegram_client import cleanup_telegram_client
                            await cleanup_telegram_client()

                            # 关闭数据库连接
                            from core.database import close_database
                            await close_database()

                            logger.info("应用程序清理完成")
                        except Exception as e:
                            logger.error(f"异步清理过程中出错: {e}")

                    cleanup_loop.run_until_complete(async_cleanup())
                    cleanup_loop.close()

                except Exception as e:
                    logger.error(f"清理过程中出错: {e}")
                    # 即使清理出错，也要尝试关闭数据库
                    try:
                        import aiosqlite
                        async def emergency_db_close():
                            try:
                                from core.database import db_manager
                                if db_manager.connection:
                                    await db_manager.connection.close()
                            except:
                                pass
                        # 在新循环中紧急关闭数据库
                        emergency_loop = asyncio.new_event_loop()
                        emergency_loop.run_until_complete(emergency_db_close())
                        emergency_loop.close()
                    except:
                        pass

    except KeyboardInterrupt:
        logger.info("用户中断应用程序")
    except Exception as e:
        logger.error(f"Main Loop Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_application()
