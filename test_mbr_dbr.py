#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试MBR和DBR读取功能
"""

import sys
import os
from disk_utils import DiskManager
from ui_components import FileSystemTree

def test_mbr_dbr_reading():
    """测试MBR和DBR读取功能"""
    print("=== 测试MBR和DBR读取功能 ===")
    
    # 创建磁盘管理器
    disk_manager = DiskManager()
    
    # 获取可用磁盘
    print("\n1. 获取可用磁盘...")
    try:
        disks = disk_manager.get_physical_disks()
        print(f"找到 {len(disks)} 个磁盘:")
        for i, disk in enumerate(disks):
            print(f"  {i+1}. {disk.get('name', 'Unknown')} - {disk.get('path', 'Unknown')}")
    except Exception as e:
        print(f"获取磁盘列表失败: {e}")
        return
    
    if not disks:
        print("没有找到可用磁盘")
        return
    
    # 选择第一个磁盘进行测试
    test_disk = disks[0]
    disk_path = test_disk['path']
    print(f"\n2. 测试磁盘: {disk_path}")
    
    # 测试获取磁盘信息
    print("\n3. 获取磁盘信息...")
    try:
        disk_info = disk_manager.get_disk_info(disk_path)
        print(f"磁盘类型: {disk_info.get('type', 'Unknown')}")
        print(f"磁盘大小: {disk_info.get('size_human', 'Unknown')}")
        
        if 'mbr_signature' in disk_info:
            print(f"MBR签名: {disk_info['mbr_signature']}")
        
        if 'partitions' in disk_info:
            print(f"分区数量: {len(disk_info['partitions'])}")
            for i, partition in enumerate(disk_info['partitions']):
                print(f"  分区 {i+1}:")
                print(f"    类型: {partition.get('type_name', 'Unknown')}")
                print(f"    状态: {partition.get('status', 'Unknown')}")
                print(f"    起始扇区: {partition.get('start_sector', 'Unknown')}")
                print(f"    大小: {partition.get('size_human', 'Unknown')}")
        else:
            print("没有找到分区信息")
    except Exception as e:
        print(f"获取磁盘信息失败: {e}")
        return
    
    # 测试读取MBR（仅对物理磁盘）
    print("\n4. 测试读取MBR...")
    if disk_info.get('is_logical_drive', False):
        print("跳过MBR读取: 逻辑驱动器没有MBR")
    else:
        try:
            mbr_data = disk_manager.read_sectors(disk_path, 0, 1)
            if mbr_data:
                print(f"MBR数据长度: {len(mbr_data)} 字节")
                print(f"MBR签名: {mbr_data[510:512].hex() if len(mbr_data) >= 512 else 'N/A'}")
                print(f"前16字节: {mbr_data[:16].hex() if len(mbr_data) >= 16 else 'N/A'}")
            else:
                print("读取MBR失败: 返回空数据")
        except Exception as e:
            print(f"读取MBR失败: {e}")
    
    # 测试读取DBR（如果有分区）
    if 'partitions' in disk_info and disk_info['partitions']:
        print("\n5. 测试读取DBR...")
        for i, partition in enumerate(disk_info['partitions']):
            try:
                start_sector = partition.get('start_sector', 0)
                print(f"  分区 {i+1} DBR (起始扇区: {start_sector}):")
                
                dbr_data = disk_manager.read_sectors(disk_path, start_sector, 1)
                if dbr_data:
                    print(f"    DBR数据长度: {len(dbr_data)} 字节")
                    print(f"    前16字节: {dbr_data[:16].hex() if len(dbr_data) >= 16 else 'N/A'}")
                    
                    # 检查文件系统签名
                    if len(dbr_data) >= 512:
                        if dbr_data[510:512] == b'\x55\xAA':
                            print(f"    引导签名: 有效 (0x55AA)")
                        else:
                            print(f"    引导签名: 无效或缺失")
                        
                        # 检查文件系统类型
                        if b'FAT32' in dbr_data[:90]:
                            print(f"    文件系统: FAT32")
                        elif b'NTFS' in dbr_data[:90]:
                            print(f"    文件系统: NTFS")
                        else:
                            print(f"    文件系统: 未知")
                else:
                    print(f"    读取DBR失败: 返回空数据")
            except Exception as e:
                print(f"    读取分区 {i+1} DBR失败: {e}")
    
    print("\n=== 测试完成 ===")

if __name__ == '__main__':
    test_mbr_dbr_reading()