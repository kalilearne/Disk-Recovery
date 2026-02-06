#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAT32磁盘镜像恢复功能测试
"""

import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fat32_recovery import FAT32Recovery

class TestSignalReceiver(QObject):
    """测试信号接收器"""
    
    def __init__(self):
        super().__init__()
        self.progress_values = []
        self.status_messages = []
    
    def on_progress_updated(self, value):
        """进度更新处理"""
        self.progress_values.append(value)
        print(f"进度: {value}%")
    
    def on_status_updated(self, message):
        """状态更新处理"""
        self.status_messages.append(message)
        print(f"状态: {message}")

def test_fat32_disk_image_recovery():
    """测试FAT32磁盘镜像恢复功能"""
    print("FAT32磁盘镜像恢复功能测试")
    print("=" * 50)
    
    try:
        # 创建QApplication（Qt信号需要事件循环）
        app = QApplication(sys.argv)
        
        # 创建FAT32Recovery实例
        recovery = FAT32Recovery()
        print("✓ FAT32Recovery实例创建成功")
        
        # 创建信号接收器
        receiver = TestSignalReceiver()
        recovery.progress_updated.connect(receiver.on_progress_updated)
        recovery.status_updated.connect(receiver.on_status_updated)
        print("✓ 信号连接成功")
        
        # 检查磁盘镜像功能是否可用
        from fat32_recovery import DISK_IMAGE_AVAILABLE
        if DISK_IMAGE_AVAILABLE:
            print("✓ 磁盘镜像快照功能可用")
        else:
            print("⚠ 磁盘镜像快照功能不可用，将使用直接访问方法")
        
        # 检查方法是否存在
        if hasattr(recovery, 'recover_files'):
            print("✓ recover_files方法存在")
        else:
            print("✗ recover_files方法不存在")
            return False
        
        if hasattr(recovery, '_recover_with_disk_image'):
            print("✓ _recover_with_disk_image方法存在")
        else:
            print("✗ _recover_with_disk_image方法不存在")
            return False
        
        if hasattr(recovery, '_recover_direct'):
            print("✓ _recover_direct方法存在")
        else:
            print("✗ _recover_direct方法不存在")
            return False
        
        # 测试方法签名
        import inspect
        sig = inspect.signature(recovery.recover_files)
        params = list(sig.parameters.keys())
        expected_params = ['disk_path', 'output_dir', 'use_disk_image']
        
        if all(param in params for param in expected_params):
            print("✓ recover_files方法签名正确")
        else:
            print(f"✗ recover_files方法签名错误，期望: {expected_params}，实际: {params}")
            return False
        
        # 检查默认参数
        if sig.parameters['use_disk_image'].default is True:
            print("✓ use_disk_image默认参数正确")
        else:
            print("✗ use_disk_image默认参数错误")
            return False
        
        print("\n✓ 所有测试通过，FAT32磁盘镜像恢复功能集成成功")
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    if test_fat32_disk_image_recovery():
        print("\n🎉 FAT32磁盘镜像恢复功能测试通过")
        return 0
    else:
        print("\n❌ FAT32磁盘镜像恢复功能测试失败")
        return 1

if __name__ == '__main__':
    sys.exit(main())