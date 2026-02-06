#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from data_wipe import DataWipe

def test_data_wipe():
    """测试DataWipe功能"""
    print("开始测试DataWipe功能...")
    
    # 创建测试文件
    test_file = 'test_wipe_sample.txt'
    test_content = 'This is test data for wiping. ' * 100  # 创建较大的测试内容
    
    try:
        # 写入测试数据
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        print(f"创建测试文件: {test_file}")
        print(f"文件大小: {os.path.getsize(test_file)} 字节")
        
        # 读取原始内容验证
        with open(test_file, 'r', encoding='utf-8') as f:
            original_content = f.read()
        print(f"原始内容前50字符: {original_content[:50]}...")
        
        # 创建DataWipe实例
        wiper = DataWipe()
        print("DataWipe实例创建成功")
        
        # 连接信号以查看状态更新
        def on_status_update(status):
            print(f"状态: {status}")
        
        def on_progress_update(progress):
            print(f"进度: {progress}%")
        
        wiper.status_updated.connect(on_status_update)
        wiper.progress_updated.connect(on_progress_update)
        
        # 执行文件擦除
        print("开始擦除文件...")
        result = wiper.wipe_file(test_file, method='zeros', passes=1)
        
        if result:
            print("文件擦除成功")
        else:
            print("文件擦除失败")
        
        # 检查文件是否被删除
        if os.path.exists(test_file):
            print("警告: 文件仍然存在，擦除可能未完成")
        else:
            print("确认: 文件已被删除")
            
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理测试文件
        if os.path.exists(test_file):
            try:
                os.remove(test_file)
                print("清理测试文件完成")
            except:
                print("清理测试文件失败")

def test_disk_wipe_simulation():
    """测试磁盘擦除功能（使用虚拟文件模拟）"""
    print("\n开始测试磁盘擦除功能（模拟）...")
    
    # 创建虚拟磁盘文件
    virtual_disk = 'virtual_disk_test.img'
    disk_size = 1024 * 1024  # 1MB
    
    try:
        # 创建虚拟磁盘文件
        with open(virtual_disk, 'wb') as f:
            # 写入一些测试数据
            test_pattern = b'TESTDATA' * (disk_size // 8)
            f.write(test_pattern[:disk_size])
        
        print(f"创建虚拟磁盘: {virtual_disk}")
        print(f"磁盘大小: {os.path.getsize(virtual_disk)} 字节")
        
        # 读取原始数据验证
        with open(virtual_disk, 'rb') as f:
            original_data = f.read(100)
        print(f"原始数据前100字节: {original_data}")
        
        # 创建DataWipe实例
        wiper = DataWipe()
        
        # 连接信号
        def on_status_update(status):
            print(f"状态: {status}")
        
        def on_progress_update(progress):
            print(f"进度: {progress}%")
        
        wiper.status_updated.connect(on_status_update)
        wiper.progress_updated.connect(on_progress_update)
        
        # 执行磁盘擦除
        print("开始擦除虚拟磁盘...")
        result = wiper.wipe_disk(virtual_disk, method='zeros', passes=1)
        
        if result:
            print("磁盘擦除成功")
            
            # 验证擦除结果
            with open(virtual_disk, 'rb') as f:
                wiped_data = f.read(100)
            print(f"擦除后数据前100字节: {wiped_data}")
            
            # 检查是否全为0
            if all(b == 0 for b in wiped_data):
                print("验证成功: 数据已被擦除为全0")
            else:
                print("警告: 数据未被完全擦除")
        else:
            print("磁盘擦除失败")
            
    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理虚拟磁盘文件
        if os.path.exists(virtual_disk):
            try:
                os.remove(virtual_disk)
                print("清理虚拟磁盘文件完成")
            except:
                print("清理虚拟磁盘文件失败")

if __name__ == '__main__':
    print("DataWipe功能测试")
    print("=" * 50)
    
    # 测试文件擦除
    test_data_wipe()
    
    # 测试磁盘擦除
    test_disk_wipe_simulation()
    
    print("\n测试完成")