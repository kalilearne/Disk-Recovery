#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试G盘访问功能
"""

import os
import sys

def test_g_drive_basic():
    """基础G盘测试"""
    print("=== 基础G盘访问测试 ===")
    
    # 测试不同路径格式
    test_paths = ["G:", "G:\\", "g:", "g:\\"]
    
    for path in test_paths:
        print(f"\n测试路径: {path}")
        try:
            exists = os.path.exists(path)
            print(f"  os.path.exists(): {exists}")
            
            if exists:
                try:
                    files = os.listdir(path)
                    print(f"  文件数量: {len(files)}")
                except Exception as e:
                    print(f"  列出文件失败: {e}")
        except Exception as e:
            print(f"  检查失败: {e}")

def test_win32_g_drive():
    """Win32 API测试G盘"""
    print("\n=== Win32 API G盘测试 ===")
    
    try:
        import win32api
        import win32file
        
        # 获取所有逻辑驱动器
        drives = win32api.GetLogicalDriveStrings()
        drive_list = drives.split('\x00')[:-1]
        print(f"所有逻辑驱动器: {drive_list}")
        
        # 检查G盘是否在列表中
        g_found = False
        for drive in drive_list:
            if drive.upper().startswith('G:'):
                g_found = True
                print(f"✓ 找到G盘: {drive}")
                
                # 尝试获取磁盘空间
                try:
                    free_bytes, total_bytes, _ = win32api.GetDiskFreeSpaceEx(drive)
                    print(f"  总大小: {total_bytes:,} 字节 ({total_bytes/(1024**3):.2f} GB)")
                    print(f"  可用空间: {free_bytes:,} 字节 ({free_bytes/(1024**3):.2f} GB)")
                except Exception as e:
                    print(f"  获取磁盘空间失败: {e}")
                break
        
        if not g_found:
            print("✗ G盘未在逻辑驱动器列表中找到")
            
    except ImportError:
        print("✗ Win32 API不可用")
    except Exception as e:
        print(f"✗ Win32 API测试失败: {e}")

def test_disk_image_g_drive():
    """测试磁盘镜像模块对G盘的处理"""
    print("\n=== 磁盘镜像模块G盘测试 ===")
    
    try:
        from disk_image_snapshot import DiskImageSnapshot
        
        snapshot = DiskImageSnapshot()
        
        # 测试路径识别
        test_paths = ["G:", "G:\\", "g:", "g:\\"]
        
        for path in test_paths:
            print(f"\n测试路径: {path}")
            
            # 测试路径识别
            is_drive = snapshot._is_drive_path(path)
            print(f"  路径识别: {'驱动器路径' if is_drive else '非驱动器路径'}")
            
            # 测试获取磁盘大小
            try:
                size = snapshot.get_disk_size(path)
                if size > 0:
                    print(f"  ✓ 磁盘大小: {size:,} 字节 ({size/(1024**3):.2f} GB)")
                else:
                    print(f"  ✗ 无法获取磁盘大小")
            except Exception as e:
                print(f"  ✗ 获取磁盘大小异常: {e}")
                
    except ImportError as e:
        print(f"✗ 磁盘镜像模块导入失败: {e}")
    except Exception as e:
        print(f"✗ 磁盘镜像模块测试失败: {e}")

def main():
    """主函数"""
    print("G盘访问功能快速测试")
    print("=" * 50)
    
    test_g_drive_basic()
    test_win32_g_drive()
    test_disk_image_g_drive()
    
    print("\n" + "=" * 50)
    print("测试完成")

if __name__ == "__main__":
    main()