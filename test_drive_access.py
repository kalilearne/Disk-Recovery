#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试驱动器访问和磁盘镜像功能
"""

import os
import sys
import tempfile
from pathlib import Path

def test_drive_detection():
    """测试驱动器检测"""
    print("=== 测试驱动器检测 ===")
    try:
        # 获取所有可用驱动器
        drives = []
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append(letter)
                print(f"✓ 发现驱动器: {letter}:")
        
        if drives:
            print(f"✓ 总共发现 {len(drives)} 个驱动器: {', '.join([d+':' for d in drives])}")
            return drives
        else:
            print("✗ 未发现任何驱动器")
            return []
            
    except Exception as e:
        print(f"✗ 驱动器检测失败: {e}")
        return []

def test_disk_image_with_drive(drive_letter):
    """测试特定驱动器的磁盘镜像功能"""
    print(f"\n=== 测试驱动器 {drive_letter}: 的磁盘镜像功能 ===")
    try:
        from disk_image_snapshot import DiskImageSnapshot
        
        # 测试不同的路径格式
        test_paths = [
            f"{drive_letter}:",
            f"{drive_letter}:\\",
            f"{drive_letter.lower()}:",
            f"{drive_letter.lower()}:\\"
        ]
        
        for path in test_paths:
            print(f"\n测试路径格式: {path}")
            
            # 创建磁盘镜像快照对象
            snapshot = DiskImageSnapshot()
            
            # 测试获取磁盘大小
            disk_size = snapshot.get_disk_size(path)
            if disk_size > 0:
                print(f"✓ 磁盘大小获取成功: {disk_size:,} 字节 ({disk_size/(1024**3):.2f} GB)")
            else:
                print(f"✗ 磁盘大小获取失败")
            
            # 测试路径识别
            is_drive = snapshot._is_drive_path(path)
            print(f"✓ 路径识别: {'驱动器路径' if is_drive else '非驱动器路径'}")
            
        return True
        
    except ImportError as e:
        print(f"✗ 磁盘镜像模块导入失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 磁盘镜像测试失败: {e}")
        return False

def test_specific_drive_g():
    """专门测试G盘"""
    print("\n=== 专门测试G盘 ===")
    
    # 检查G盘是否存在
    g_drive_paths = ["G:\\", "G:"]
    g_exists = False
    
    for path in g_drive_paths:
        if os.path.exists(path):
            g_exists = True
            print(f"✓ G盘存在: {path}")
            break
    
    if not g_exists:
        print("✗ G盘不存在，跳过G盘测试")
        return False
    
    # 测试G盘的磁盘镜像功能
    return test_disk_image_with_drive('G')

def test_wmic_command():
    """测试WMIC命令"""
    print("\n=== 测试WMIC命令 ===")
    try:
        import subprocess
        
        # 测试获取所有逻辑磁盘
        result = subprocess.run(
            ['wmic', 'logicaldisk', 'get', 'DeviceID,Size'],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            print("✓ WMIC命令执行成功")
            print("逻辑磁盘信息:")
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line.strip() and 'DeviceID' not in line:
                    print(f"  {line.strip()}")
            return True
        else:
            print(f"✗ WMIC命令执行失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"✗ WMIC命令测试失败: {e}")
        return False

def test_win32_availability():
    """测试Win32模块可用性"""
    print("\n=== 测试Win32模块可用性 ===")
    try:
        import win32file
        import win32api
        print("✓ Win32模块导入成功")
        
        # 测试基本API
        try:
            drives = win32api.GetLogicalDriveStrings()
            print(f"✓ 获取逻辑驱动器成功: {drives.split('\x00')[:-1]}")
        except Exception as e:
            print(f"✗ 获取逻辑驱动器失败: {e}")
        
        return True
        
    except ImportError as e:
        print(f"✗ Win32模块导入失败: {e}")
        return False

def main():
    """主测试函数"""
    print("驱动器访问和磁盘镜像功能测试")
    print("=" * 60)
    
    tests = [
        test_win32_availability,
        test_wmic_command,
        test_drive_detection,
        test_specific_drive_g,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    # 如果发现了驱动器，测试第一个可用驱动器
    drives = test_drive_detection()
    if drives:
        first_drive = drives[0]
        print(f"\n=== 测试第一个可用驱动器 {first_drive}: ===")
        if test_disk_image_with_drive(first_drive):
            passed += 1
        total += 1
    
    print("\n" + "=" * 60)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("✓ 所有测试通过，驱动器访问功能正常")
        return True
    else:
        print("✗ 部分测试失败，请检查相关功能")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)