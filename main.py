#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import ctypes
import traceback
from PyQt5.QtWidgets import QApplication, QMessageBox
from disk_recovery_tool import DiskRecoveryTool

def is_admin():
    """检查程序是否以管理员权限运行"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_as_admin():
    """以管理员权限重新启动程序"""
    try:
        # 使用ctypes直接调用ShellExecuteW函数
        script = os.path.abspath(sys.argv[0])
        params = ' '.join([f'"{arg}"' for arg in sys.argv[1:]])
        
        # ShellExecuteW参数: hwnd, operation, file, params, directory, show_cmd
        # 0: SW_HIDE, 1: SW_NORMAL, 5: SW_SHOW
        # 'runas' 操作会触发UAC提权
        ctypes.windll.shell32.ShellExecuteW(
            None,  # hwnd
            "runas",  # operation
            sys.executable if script.endswith('.py') else script,  # file
            f'"{script}" {params}' if script.endswith('.py') else params,  # params
            None,  # directory
            1  # show_cmd: SW_NORMAL
        )
        return True
    except Exception as e:
        QMessageBox.warning(None, "权限错误", f"无法获取管理员权限: {str(e)}\n\n请右键点击程序，选择'以管理员身份运行'。")
        return False

def main():
    try:
        print("程序启动中...")
        
        # 检查是否具有管理员权限，如果没有则请求
        if not is_admin():
            print("正在请求管理员权限...")
            if run_as_admin():
                sys.exit(0)  # 成功启动管理员权限进程，退出当前进程
            else:
                print("警告: 程序未以管理员权限运行，某些功能可能受限。")
        
        print("创建QApplication...")
        app = QApplication(sys.argv)
        
        # 设置全局异常处理器
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            
            error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            print(f"未捕获的异常: {error_msg}")
            
            # 尝试显示错误对话框
            try:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.critical(None, "程序错误", 
                    f"程序遇到未处理的错误:\n\n{exc_value}\n\n程序将继续运行，但可能不稳定。")
            except:
                pass
        
        sys.excepthook = handle_exception
        
        print("创建DiskRecoveryTool窗口...")
        window = DiskRecoveryTool()
        
        print("显示窗口...")
        window.show()
        
        print("启动事件循环...")
        sys.exit(app.exec_())
        
    except ImportError as e:
        print(f"导入错误: {e}")
        print("请确保已安装所有必需的依赖包:")
        print("pip install PyQt5 pywin32")
        input("按回车键退出...")
    except Exception as e:
        print(f"程序启动失败: {e}")
        print(f"错误详情: {traceback.format_exc()}")
        input("按回车键退出...")

if __name__ == "__main__":
    main()