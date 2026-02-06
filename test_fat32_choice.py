#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试FAT32恢复方式选择功能
"""

import sys
import os
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from disk_recovery_tool import DiskRecoveryTool

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FAT32恢复方式选择测试")
        self.setGeometry(100, 100, 400, 200)
        
        # 创建主窗口部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建布局
        layout = QVBoxLayout(central_widget)
        
        # 创建测试按钮
        test_button = QPushButton("测试FAT32恢复方式选择对话框")
        test_button.clicked.connect(self.test_fat32_dialog)
        layout.addWidget(test_button)
        
        # 创建DiskRecoveryTool实例用于测试
        self.recovery_tool = DiskRecoveryTool()
    
    def test_fat32_dialog(self):
        """测试FAT32恢复方式选择对话框"""
        try:
            result = self.recovery_tool._show_fat32_recovery_method_dialog()
            if result:
                print(f"用户选择的恢复方式: {result}")
                if result == 'image':
                    print("将使用磁盘镜像快照恢复")
                elif result == 'direct':
                    print("将使用传统直接恢复")
            else:
                print("用户取消了选择")
        except Exception as e:
            print(f"测试过程中发生错误: {e}")
            import traceback
            traceback.print_exc()

def main():
    """主函数"""
    app = QApplication(sys.argv)
    
    # 设置应用程序样式
    app.setStyle('Fusion')
    
    # 创建测试窗口
    window = TestWindow()
    window.show()
    
    # 运行应用程序
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()