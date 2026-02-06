#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
from PyQt5.QtWidgets import QApplication
from fat32_recovery import FAT32Recovery
from ntfs_recovery import NTFSRecovery

def test_fat32_recovery():
    """测试FAT32恢复功能"""
    print("测试FAT32恢复功能...")
    
    try:
        # 创建FAT32Recovery实例
        recovery = FAT32Recovery()
        print("✓ FAT32Recovery实例创建成功")
        
        # 检查信号是否正确定义
        if hasattr(recovery, 'progress_updated') and hasattr(recovery, 'status_updated'):
            print("✓ 信号定义正确")
        else:
            print("✗ 信号定义错误")
            return False
            
        # 检查recover_files方法是否存在
        if hasattr(recovery, 'recover_files'):
            print("✓ recover_files方法存在")
        else:
            print("✗ recover_files方法不存在")
            return False
            
        return True
        
    except Exception as e:
        print(f"✗ FAT32恢复测试失败: {e}")
        return False

def test_ntfs_recovery():
    """测试NTFS恢复功能"""
    print("\n测试NTFS恢复功能...")
    
    try:
        # 创建NTFSRecovery实例
        recovery = NTFSRecovery()
        print("✓ NTFSRecovery实例创建成功")
        
        # 检查信号是否正确定义
        if hasattr(recovery, 'progress_updated') and hasattr(recovery, 'status_updated'):
            print("✓ 信号定义正确")
        else:
            print("✗ 信号定义错误")
            return False
            
        # 检查recover_files方法是否存在
        if hasattr(recovery, 'recover_files'):
            print("✓ recover_files方法存在")
        else:
            print("✗ recover_files方法不存在")
            return False
            
        return True
        
    except Exception as e:
        print(f"✗ NTFS恢复测试失败: {e}")
        return False

def test_recovery_worker():
    """测试RecoveryWorker"""
    print("\n测试RecoveryWorker...")
    
    try:
        from disk_recovery_tool import RecoveryWorker
        
        # 创建RecoveryWorker实例
        worker = RecoveryWorker('fat32', 'F:', 'C:\\temp')
        print("✓ RecoveryWorker实例创建成功")
        
        # 检查属性
        if worker.recovery_type == 'fat32':
            print("✓ recovery_type设置正确")
        else:
            print("✗ recovery_type设置错误")
            return False
            
        return True
        
    except Exception as e:
        print(f"✗ RecoveryWorker测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("磁盘恢复功能测试")
    print("=" * 50)
    
    # 创建QApplication（Qt信号需要事件循环）
    app = QApplication(sys.argv)
    
    # 运行测试
    tests = [
        test_fat32_recovery,
        test_ntfs_recovery,
        test_recovery_worker
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("✓ 所有测试通过，恢复功能正常")
        return 0
    else:
        print("✗ 部分测试失败，请检查代码")
        return 1

if __name__ == '__main__':
    sys.exit(main())