#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的FAT32磁盘镜像恢复功能测试
"""

import sys
import os
import inspect

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_fat32_imports():
    """测试FAT32恢复模块导入"""
    print("测试FAT32恢复模块导入...")
    
    try:
        # 测试磁盘镜像快照功能导入
        try:
            from disk_image_snapshot import create_disk_image_snapshot
            print("✓ 磁盘镜像快照功能导入成功")
            disk_image_available = True
        except ImportError as e:
            print(f"⚠ 磁盘镜像快照功能导入失败: {e}")
            disk_image_available = False
        
        # 测试FAT32恢复模块导入
        from fat32_recovery import FAT32Recovery, DISK_IMAGE_AVAILABLE
        print("✓ FAT32Recovery模块导入成功")
        
        # 检查DISK_IMAGE_AVAILABLE标志
        if DISK_IMAGE_AVAILABLE == disk_image_available:
            print(f"✓ DISK_IMAGE_AVAILABLE标志正确: {DISK_IMAGE_AVAILABLE}")
        else:
            print(f"✗ DISK_IMAGE_AVAILABLE标志错误: 期望{disk_image_available}，实际{DISK_IMAGE_AVAILABLE}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 导入测试失败: {e}")
        return False

def test_fat32_methods():
    """测试FAT32恢复方法"""
    print("\n测试FAT32恢复方法...")
    
    try:
        from fat32_recovery import FAT32Recovery
        
        # 检查类是否存在
        print("✓ FAT32Recovery类存在")
        
        # 检查方法是否存在
        methods_to_check = [
            'recover_files',
            '_recover_with_disk_image', 
            '_recover_direct',
            '_prepare_device_path',
            '_find_fat32_boot_sector',
            '_parse_fat32_boot_sector',
            '_recover_fat32_files'
        ]
        
        for method_name in methods_to_check:
            if hasattr(FAT32Recovery, method_name):
                print(f"✓ {method_name}方法存在")
            else:
                print(f"✗ {method_name}方法不存在")
                return False
        
        # 检查recover_files方法签名
        sig = inspect.signature(FAT32Recovery.recover_files)
        params = list(sig.parameters.keys())
        expected_params = ['self', 'disk_path', 'output_dir', 'use_disk_image']
        
        if params == expected_params:
            print("✓ recover_files方法签名正确")
        else:
            print(f"✗ recover_files方法签名错误，期望: {expected_params}，实际: {params}")
            return False
        
        # 检查默认参数
        if sig.parameters['use_disk_image'].default is True:
            print("✓ use_disk_image默认参数正确")
        else:
            print(f"✗ use_disk_image默认参数错误: {sig.parameters['use_disk_image'].default}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 方法测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_integration():
    """测试集成"""
    print("\n测试集成...")
    
    try:
        # 测试disk_recovery_tool中的导入
        from disk_recovery_tool import RecoveryWorker
        print("✓ RecoveryWorker导入成功")
        
        # 检查RecoveryWorker是否能正确处理FAT32恢复
        worker = RecoveryWorker('fat32', 'test_disk', 'test_output')
        print("✓ RecoveryWorker实例创建成功")
        
        if worker.recovery_type == 'fat32':
            print("✓ recovery_type设置正确")
        else:
            print(f"✗ recovery_type设置错误: {worker.recovery_type}")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 集成测试失败: {e}")
        return False

def main():
    """主函数"""
    print("FAT32磁盘镜像恢复功能测试")
    print("=" * 50)
    
    tests = [
        test_fat32_imports,
        test_fat32_methods,
        test_integration
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            break  # 如果有测试失败，停止后续测试
    
    print("\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过，FAT32磁盘镜像恢复功能集成成功")
        return 0
    else:
        print("❌ 部分测试失败，请检查代码")
        return 1

if __name__ == '__main__':
    sys.exit(main())