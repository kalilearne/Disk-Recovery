#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试磁盘镜像创建功能的调试脚本
"""

import os
import sys

def test_disk_image_creation():
    """测试磁盘镜像创建功能"""
    print("=== 磁盘镜像创建测试 ===")
    
    try:
        # 导入磁盘镜像模块
        from disk_image_snapshot import DiskImageSnapshot, create_disk_image_snapshot
        print("✓ 成功导入磁盘镜像模块")
        
        # 测试可用的驱动器
        import win32api
        drives = win32api.GetLogicalDriveStrings()
        drive_list = drives.split('\x00')[:-1]
        print(f"可用驱动器: {drive_list}")
        
        # 选择一个小的驱动器进行测试（通常选择U盘或小分区）
        test_drive = None
        for drive in drive_list:
            try:
                free_bytes, total_bytes, _ = win32api.GetDiskFreeSpaceEx(drive)
                size_gb = total_bytes / (1024*1024*1024)
                print(f"驱动器 {drive}: {size_gb:.2f} GB")
                
                # 选择小于8GB的驱动器进行测试
                if size_gb < 8.0 and test_drive is None:
                    test_drive = drive.rstrip('\\')
                    print(f"选择测试驱动器: {test_drive}")
                    
            except Exception as e:
                print(f"检查驱动器 {drive} 失败: {e}")
        
        if not test_drive:
            print("未找到合适的小容量驱动器进行测试")
            print("请插入一个U盘或选择一个小分区进行测试")
            return False
        
        # 创建进度回调函数
        def progress_callback(current, total, message):
            if total > 0:
                percent = (current / total) * 100
                print(f"进度: {percent:.1f}% - {message}")
            else:
                print(f"状态: {message}")
        
        print(f"\n开始为驱动器 {test_drive} 创建镜像...")
        
        # 创建磁盘镜像
        with DiskImageSnapshot(progress_callback) as snapshot:
            result = snapshot.create_disk_image(test_drive)
            
            print(f"\n镜像创建结果:")
            print(f"成功: {result['success']}")
            if result['success']:
                print(f"镜像路径: {result['image_path']}")
                print(f"镜像大小: {result['size']:,} 字节")
                print(f"创建时间: {result['creation_time']}")
                
                # 验证镜像文件
                if os.path.exists(result['image_path']):
                    actual_size = os.path.getsize(result['image_path'])
                    print(f"实际文件大小: {actual_size:,} 字节")
                    print(f"大小匹配: {actual_size == result['size']}")
                else:
                    print("错误: 镜像文件不存在！")
            else:
                print(f"错误: {result['error']}")
                
        return result['success']
        
    except Exception as e:
        print(f"测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_fat32_recovery_with_image():
    """测试FAT32镜像恢复功能"""
    print("\n=== FAT32镜像恢复测试 ===")
    
    try:
        from fat32_recovery import FAT32Recovery
        
        # 创建测试接收器
        class TestReceiver:
            def __init__(self):
                self.progress = 0
                self.status = ""
            
            def on_progress(self, value):
                self.progress = value
                print(f"进度: {value}%")
            
            def on_status(self, message):
                self.status = message
                print(f"状态: {message}")
        
        receiver = TestReceiver()
        
        # 创建FAT32恢复实例
        recovery = FAT32Recovery()
        recovery.progress_updated.connect(receiver.on_progress)
        recovery.status_updated.connect(receiver.on_status)
        
        print("✓ 成功创建FAT32Recovery实例")
        print(f"✓ 磁盘镜像功能可用: {hasattr(recovery, '_recover_with_disk_image')}")
        
        return True
        
    except Exception as e:
        print(f"FAT32恢复测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("磁盘镜像功能调试测试")
    print("=" * 50)
    
    # 测试磁盘镜像创建
    image_test = test_disk_image_creation()
    
    # 测试FAT32恢复
    fat32_test = test_fat32_recovery_with_image()
    
    print("\n=== 测试结果 ===")
    print(f"磁盘镜像创建: {'✓ 通过' if image_test else '✗ 失败'}")
    print(f"FAT32镜像恢复: {'✓ 通过' if fat32_test else '✗ 失败'}")
    
    if image_test and fat32_test:
        print("\n所有测试通过！磁盘镜像功能正常。")
    else:
        print("\n部分测试失败，请检查错误信息。")