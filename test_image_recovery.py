#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试镜像文件恢复功能
"""

import os
import sys
import tempfile
from file_signature_recovery import FileSignatureRecovery

def create_test_image():
    """创建一个包含测试文件的镜像"""
    # 创建临时镜像文件
    with tempfile.NamedTemporaryFile(delete=False, suffix='.img') as temp_file:
        image_path = temp_file.name
        
        # 写入一些测试数据和文件签名
        # JPEG文件签名
        jpeg_header = bytes.fromhex('FFD8FFE0')
        jpeg_data = jpeg_header + b'\x00' * 1000  # 模拟JPEG文件
        
        # PNG文件签名
        png_header = bytes.fromhex('89504E470D0A1A0A')
        png_data = png_header + b'\x00' * 1000  # 模拟PNG文件
        
        # PDF文件签名
        pdf_header = b'%PDF-1.4'
        pdf_data = pdf_header + b'\x00' * 1000  # 模拟PDF文件
        
        # 写入镜像文件
        temp_file.write(b'\x00' * 1024)  # 填充数据
        temp_file.write(jpeg_data)
        temp_file.write(b'\x00' * 1024)  # 填充数据
        temp_file.write(png_data)
        temp_file.write(b'\x00' * 1024)  # 填充数据
        temp_file.write(pdf_data)
        temp_file.write(b'\x00' * 1024)  # 填充数据
        
    return image_path

def test_image_recovery():
    """测试镜像文件恢复"""
    print("=== 测试镜像文件恢复功能 ===")
    
    # 创建测试镜像
    print("创建测试镜像...")
    image_path = create_test_image()
    print(f"测试镜像路径: {image_path}")
    print(f"镜像大小: {os.path.getsize(image_path)} 字节")
    
    # 创建输出目录
    output_dir = tempfile.mkdtemp(prefix='recovery_test_')
    print(f"输出目录: {output_dir}")
    
    try:
        # 测试文件恢复
        print("\n开始文件恢复...")
        selected_types = ['FFD8FF', '89504E470D0A1A0A', '25504446']  # JPEG, PNG, PDF
        
        result = FileSignatureRecovery.recover_files_by_signature(
            disk_path=image_path,
            selected_types=selected_types,
            save_dir=output_dir,
            reverse=False,
            filename_map=None
        )
        
        print(f"\n=== 恢复结果 ===")
        recovered_files = result['files'] if isinstance(result, dict) else result
        print(f"总共恢复文件数: {len(recovered_files)}")
        
        for i, file_info in enumerate(recovered_files, 1):
            print(f"\n文件 {i}:")
            print(f"  名称: {file_info['name']}")
            print(f"  路径: {file_info['path']}")
            print(f"  偏移: 0x{file_info['offset']:x}")
            print(f"  大小: {file_info['size']} 字节")
            print(f"  类型: {file_info['type']}")
            print(f"  簇对齐: {file_info['cluster_aligned']}")
            
            # 验证文件是否存在
            if os.path.exists(file_info['path']):
                actual_size = os.path.getsize(file_info['path'])
                print(f"  实际文件大小: {actual_size} 字节")
            else:
                print(f"  错误: 文件不存在!")
        
        # 检查输出目录结构
        print(f"\n=== 输出目录结构 ===")
        for root, dirs, files in os.walk(output_dir):
            level = root.replace(output_dir, '').count(os.sep)
            indent = ' ' * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                file_path = os.path.join(root, file)
                file_size = os.path.getsize(file_path)
                print(f"{subindent}{file} ({file_size} 字节)")
        
        return len(recovered_files) > 0
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # 清理测试文件
        try:
            os.unlink(image_path)
            print(f"\n已删除测试镜像: {image_path}")
        except:
            pass
        
        # 注意: 不删除输出目录，以便检查结果
        print(f"输出目录保留: {output_dir}")

if __name__ == '__main__':
    success = test_image_recovery()
    if success:
        print("\n✅ 测试成功!")
        sys.exit(0)
    else:
        print("\n❌ 测试失败!")
        sys.exit(1)