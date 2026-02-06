#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from disk_utils import DiskUtils

def test_logical_drive_fix():
    """测试逻辑驱动器路径修复"""
    print("测试逻辑驱动器路径修复...")
    
    disk_utils = DiskUtils()
    
    # 测试C盘读取
    try:
        print("\n测试读取C盘扇区...")
        data = disk_utils.read_sectors("C:\\", 0, 1)
        if data:
            print(f"成功读取C盘扇区，数据长度: {len(data)} 字节")
            print(f"前16字节: {data[:16].hex()}")
        else:
            print("读取失败：返回空数据")
    except Exception as e:
        print(f"读取C盘失败: {e}")
    
    # 测试获取C盘信息
    try:
        print("\n测试获取C盘信息...")
        info = disk_utils.get_disk_info("C:\\")
        if info:
            print("成功获取C盘信息:")
            print(f"  分区数量: {len(info.get('partitions', []))}")
            for i, partition in enumerate(info.get('partitions', [])):
                print(f"  分区{i+1}: {partition.get('status', 'Unknown')} - {partition.get('type_name', 'Unknown')}")
        else:
            print("获取C盘信息失败")
    except Exception as e:
        print(f"获取C盘信息失败: {e}")

if __name__ == "__main__":
    test_logical_drive_fix()
    input("\n按回车键退出...")