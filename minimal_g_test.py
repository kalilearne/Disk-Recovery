#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小化G盘测试
"""

print("开始G盘测试...")

try:
    # 测试1: 基础导入
    print("1. 导入模块...")
    from disk_image_snapshot import DiskImageSnapshot
    print("   ✓ 模块导入成功")
    
    # 测试2: 创建对象
    print("2. 创建对象...")
    snapshot = DiskImageSnapshot()
    print("   ✓ 对象创建成功")
    
    # 测试3: 路径识别
    print("3. 测试路径识别...")
    test_path = "G:"
    is_drive = snapshot._is_drive_path(test_path)
    print(f"   路径 {test_path} 识别为: {'驱动器路径' if is_drive else '非驱动器路径'}")
    
    # 测试4: 获取磁盘大小
    print("4. 获取磁盘大小...")
    try:
        size = snapshot.get_disk_size("G:")
        if size > 0:
            print(f"   ✓ G盘大小: {size:,} 字节")
        else:
            print("   ✗ 无法获取G盘大小")
    except Exception as e:
        print(f"   ✗ 获取大小失败: {e}")
    
    print("\n测试完成")
    
except Exception as e:
    print(f"测试失败: {e}")
    import traceback
    traceback.print_exc()