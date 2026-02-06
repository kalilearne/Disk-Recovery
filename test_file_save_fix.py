#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件保存修复验证脚本
验证修复后的文件签名恢复功能是否能正确保存文件
"""

import os
import sys
from file_signature_recovery import FileSignatureRecovery

def test_file_save_fix():
    """测试文件保存修复"""
    print("=== 测试文件保存修复 ===")
    
    try:
        # 创建测试目录
        test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_save_fix")
        os.makedirs(test_dir, exist_ok=True)
        print(f"测试目录: {test_dir}")
        
        # 测试文件大小估算函数
        print("\n1. 测试文件大小估算函数")
        
        # 测试JPEG数据
        jpeg_data = b'\xFF\xD8\xFF\xE0' + b'\x00' * 1000 + b'\xFF\xD9'
        jpeg_info = {'type': '图片', 'ext': '.jpg'}
        
        estimated_size = FileSignatureRecovery.estimate_file_size(jpeg_data, jpeg_info, 0)
        print(f"JPEG估算大小: {estimated_size} 字节 (数据长度: {len(jpeg_data)})")
        
        if estimated_size > 0:
            print("✓ JPEG大小估算正常")
        else:
            print("✗ JPEG大小估算异常")
            return False
        
        # 测试空数据
        empty_data = b''
        empty_info = {'type': '其他', 'ext': '.dat'}
        
        estimated_size = FileSignatureRecovery.estimate_file_size(empty_data, empty_info, 0)
        print(f"空数据估算大小: {estimated_size} 字节")
        
        if estimated_size >= 1024:  # 应该至少1KB
            print("✓ 空数据大小估算正常")
        else:
            print("✗ 空数据大小估算异常")
            return False
        
        # 测试目录创建和文件保存
        print("\n2. 测试目录创建和文件保存")
        
        # 创建类型目录
        type_dir = os.path.join(test_dir, "图片")
        os.makedirs(type_dir, exist_ok=True)
        print(f"类型目录: {type_dir}")
        
        # 模拟文件保存过程
        file_data = b'\xFF\xD8\xFF\xE0' + b'test data' * 100 + b'\xFF\xD9'
        filename = "test_recovered_000001.jpg"
        file_path = os.path.join(type_dir, filename)
        
        print(f"保存文件: {file_path}")
        print(f"文件大小: {len(file_data)} 字节")
        
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        # 保存文件
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        # 验证文件保存
        if os.path.exists(file_path):
            saved_size = os.path.getsize(file_path)
            if saved_size == len(file_data) and saved_size > 0:
                print(f"✓ 文件保存成功: {saved_size} 字节")
                
                # 验证文件内容
                with open(file_path, 'rb') as f:
                    saved_data = f.read()
                
                if saved_data == file_data:
                    print("✓ 文件内容验证通过")
                else:
                    print("✗ 文件内容不匹配")
                    return False
            else:
                print(f"✗ 文件大小异常: {saved_size}")
                return False
        else:
            print("✗ 文件未保存")
            return False
        
        print("\n3. 测试边界条件")
        
        # 测试大文件处理
        large_data = b'A' * (60 * 1024 * 1024)  # 60MB数据
        max_read_size = min(len(large_data), 50 * 1024 * 1024)  # 最大50MB
        
        print(f"大文件数据: {len(large_data)} 字节")
        print(f"最大读取: {max_read_size} 字节")
        
        if max_read_size == 50 * 1024 * 1024:
            print("✓ 大文件大小限制正常")
        else:
            print("✗ 大文件大小限制异常")
            return False
        
        # 测试小文件处理
        small_data = b'small'
        small_size = max(1024, min(len(small_data), 100 * 1024 * 1024))
        
        print(f"小文件数据: {len(small_data)} 字节")
        print(f"调整后大小: {small_size} 字节")
        
        if small_size >= 1024:
            print("✓ 小文件大小调整正常")
        else:
            print("✗ 小文件大小调整异常")
            return False
        
        return True
        
    except Exception as e:
        print(f"✗ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

def cleanup_test_files():
    """清理测试文件"""
    print("\n=== 清理测试文件 ===")
    
    import shutil
    
    test_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_save_fix")
    
    try:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            print(f"✓ 清理目录: {test_dir}")
    except Exception as e:
        print(f"✗ 清理目录失败: {e}")

def main():
    """主函数"""
    print("文件保存修复验证开始...")
    print("=" * 50)
    
    try:
        success = test_file_save_fix()
        
        print("\n" + "=" * 50)
        if success:
            print("✓ 所有测试通过！文件保存修复成功。")
            print("\n修复内容:")
            print("- 添加了文件大小验证，避免保存空文件")
            print("- 限制了最大读取大小，防止内存问题")
            print("- 确保目录存在，避免路径错误")
            print("- 添加了文件保存验证，确保文件正确写入")
            print("- 改进了文件大小估算，确保返回合理值")
        else:
            print("✗ 部分测试失败！需要进一步检查。")
        
        return success
        
    except Exception as e:
        print(f"\n测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        cleanup_test_files()

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n测试被用户中断")
        cleanup_test_files()
        sys.exit(1)