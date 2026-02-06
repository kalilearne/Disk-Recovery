#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
磁盘工具的备用实现，不依赖win32api的特定函数
"""

import os
import sys
import shutil
from pathlib import Path

def get_drives_fallback():
    """获取驱动器列表的备用方法"""
    drives = []
    
    if sys.platform == 'win32':
        # Windows系统，检查A-Z盘符
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            drive_path = f'{letter}:\\'
            if os.path.exists(drive_path):
                try:
                    # 尝试访问驱动器
                    os.listdir(drive_path)
                    drives.append(drive_path)
                except (OSError, PermissionError):
                    # 驱动器存在但无法访问
                    continue
    else:
        # Linux/Mac系统
        drives = ['/']  # 根目录
    
    return drives

def get_disk_info_fallback(drive_path):
    """获取磁盘信息的备用方法"""
    try:
        # 使用shutil获取磁盘使用情况
        total, used, free = shutil.disk_usage(drive_path)
        
        # 尝试获取卷标
        volume_name = '本地磁盘'
        if sys.platform == 'win32':
            # 在Windows上尝试读取卷标文件
            try:
                # 这是一个简化的方法，实际卷标获取更复杂
                volume_name = f'{drive_path[0]}盘'
            except:
                volume_name = '本地磁盘'
        
        return {
            'path': drive_path,
            'name': f'{drive_path} {volume_name}',
            'size': total,
            'free': free,
            'used': used,
            'type': 'fixed',  # 默认为固定磁盘
            'letter': drive_path[0] if len(drive_path) > 0 else ''
        }
    except Exception as e:
        print(f"获取磁盘信息失败 {drive_path}: {e}")
        return None

def test_fallback_methods():
    """测试备用方法"""
    print("测试备用磁盘检测方法...")
    
    drives = get_drives_fallback()
    print(f"找到驱动器: {drives}")
    
    for drive in drives:
        info = get_disk_info_fallback(drive)
        if info:
            print(f"驱动器 {drive}:")
            print(f"  名称: {info['name']}")
            print(f"  总大小: {info['size'] / (1024**3):.2f} GB")
            print(f"  可用空间: {info['free'] / (1024**3):.2f} GB")
            print(f"  类型: {info['type']}")
            print()

if __name__ == "__main__":
    test_fallback_methods()