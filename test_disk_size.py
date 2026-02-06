#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试磁盘大小获取功能
"""

import os
import platform

try:
    import win32api
    import win32file
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

def test_disk_size_detection():
    """测试磁盘大小检测功能"""
    print("=== 磁盘大小检测测试 ===")
    print(f"操作系统: {platform.system()}")
    print(f"Win32 API 可用: {WIN32_AVAILABLE}")
    
    if not WIN32_AVAILABLE:
        print("Win32 API 不可用，无法进行测试")
        return
    
    # 获取所有逻辑驱动器
    try:
        drives = win32api.GetLogicalDriveStrings()
        drive_list = drives.split('\x00')[:-1]
        print(f"\n检测到的驱动器: {drive_list}")
        
        for drive in drive_list:
            print(f"\n--- 测试驱动器 {drive} ---")
            
            # 方法1: GetDiskFreeSpaceEx
            try:
                free_bytes, total_bytes, _ = win32api.GetDiskFreeSpaceEx(drive)
                print(f"✓ GetDiskFreeSpaceEx: {total_bytes:,} 字节 ({total_bytes/(1024**3):.2f} GB)")
            except Exception as e:
                print(f"✗ GetDiskFreeSpaceEx 失败: {e}")
            
            # 方法2: 检查根目录是否存在
            try:
                if os.path.exists(drive):
                    print(f"✓ 根目录可访问: {drive}")
                else:
                    print(f"✗ 根目录不可访问: {drive}")
            except Exception as e:
                print(f"✗ 检查根目录失败: {e}")
            
            # 方法3: 尝试打开物理路径
            drive_letter = drive[0].upper()
            physical_path = f'\\\\.\\{drive_letter}:'
            try:
                handle = win32file.CreateFile(
                    physical_path,
                    win32file.GENERIC_READ,
                    win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                    None,
                    win32file.OPEN_EXISTING,
                    0,
                    None
                )
                if handle != win32file.INVALID_HANDLE_VALUE:
                    print(f"✓ 物理路径可访问: {physical_path}")
                    win32file.CloseHandle(handle)
                else:
                    print(f"✗ 物理路径无效句柄: {physical_path}")
            except Exception as e:
                print(f"✗ 打开物理路径失败: {e}")
    
    except Exception as e:
        print(f"获取驱动器列表失败: {e}")

def test_disk_image_size_logic():
    """测试磁盘镜像大小获取逻辑"""
    print("\n=== 磁盘镜像大小逻辑测试 ===")
    
    try:
        from disk_image_snapshot import DiskImageSnapshot
        
        # 创建实例
        snapshot = DiskImageSnapshot()
        
        # 测试不同格式的路径
        test_paths = [
            "C:",
            "C:\\",
            "D:",
            "D:\\"
        ]
        
        for path in test_paths:
            print(f"\n测试路径: {path}")
            try:
                size = snapshot._get_disk_size(path)
                if size > 0:
                    print(f"✓ 大小: {size:,} 字节 ({size/(1024**3):.2f} GB)")
                else:
                    print(f"✗ 获取大小失败或为0")
            except Exception as e:
                print(f"✗ 异常: {e}")
    
    except Exception as e:
        print(f"导入磁盘镜像模块失败: {e}")

if __name__ == "__main__":
    test_disk_size_detection()
    test_disk_image_size_logic()
    
    print("\n测试完成。")