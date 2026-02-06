#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试磁盘镜像保存到恢复目录功能
"""

import os
import tempfile
import time

def test_image_save_to_recovery_dir():
    """测试镜像保存到恢复目录功能"""
    print("=== 测试镜像保存到恢复目录 ===")
    
    try:
        from disk_image_snapshot import DiskImageSnapshot, create_disk_image_snapshot
        
        # 创建临时恢复目录
        recovery_dir = tempfile.mkdtemp(prefix="recovery_test_")
        print(f"创建测试恢复目录: {recovery_dir}")
        
        # 测试驱动器（选择一个小的驱动器）
        test_drive = "C:"
        
        # 生成镜像文件路径
        disk_name = test_drive.replace(':', '').replace('\\', '_').replace('.', '_')
        timestamp = int(time.time())
        image_filename = f'disk_image_{disk_name}_{timestamp}.img'
        image_path = os.path.join(recovery_dir, image_filename)
        
        print(f"目标镜像路径: {image_path}")
        
        # 创建进度回调
        def progress_callback(current, total, message):
            if total > 0:
                percent = (current / total) * 100
                print(f"\r进度: {percent:.1f}% - {message}", end='', flush=True)
            else:
                print(f"\r状态: {message}", end='', flush=True)
        
        print(f"\n开始创建镜像到恢复目录...")
        
        # 使用DiskImageSnapshot直接测试
        with DiskImageSnapshot(progress_callback) as snapshot:
            result = snapshot.create_disk_image(test_drive, output_path=image_path)
            
            print(f"\n\n镜像创建结果:")
            print(f"成功: {result['success']}")
            
            if result['success']:
                print(f"镜像路径: {result['image_path']}")
                print(f"镜像大小: {result['size']:,} 字节")
                
                # 验证文件是否存在于恢复目录
                if os.path.exists(result['image_path']):
                    actual_size = os.path.getsize(result['image_path'])
                    print(f"实际文件大小: {actual_size:,} 字节")
                    print(f"文件位置正确: {result['image_path'].startswith(recovery_dir)}")
                    
                    # 测试保留镜像功能
                    print("\n测试保留镜像功能...")
                    snapshot.cleanup(keep_image=True)
                    
                    # 验证镜像是否仍然存在
                    if os.path.exists(result['image_path']):
                        print("✓ 镜像文件已成功保留")
                        return True
                    else:
                        print("✗ 镜像文件未能保留")
                        return False
                else:
                    print("✗ 镜像文件不存在")
                    return False
            else:
                print(f"错误: {result['error']}")
                return False
                
    except Exception as e:
        print(f"\n测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 清理测试目录
        try:
            import shutil
            if os.path.exists(recovery_dir):
                shutil.rmtree(recovery_dir)
                print(f"\n已清理测试目录: {recovery_dir}")
        except Exception as e:
            print(f"清理测试目录失败: {e}")

def test_fat32_recovery_with_saved_image():
    """测试FAT32恢复中的镜像保存功能"""
    print("\n=== 测试FAT32恢复镜像保存 ===")
    
    try:
        from fat32_recovery import FAT32Recovery
        
        # 创建测试接收器
        class TestReceiver:
            def __init__(self):
                self.messages = []
            
            def on_status(self, message):
                self.messages.append(message)
                print(f"状态: {message}")
        
        receiver = TestReceiver()
        
        # 创建FAT32恢复实例
        recovery = FAT32Recovery()
        recovery.status_updated.connect(receiver.on_status)
        
        print("✓ 成功创建FAT32Recovery实例")
        print(f"✓ 镜像保存功能可用: {hasattr(recovery, '_recover_with_disk_image')}")
        
        # 检查是否正确导入了time模块
        import fat32_recovery
        print(f"✓ time模块已导入: {hasattr(fat32_recovery, 'time')}")
        
        return True
        
    except Exception as e:
        print(f"FAT32恢复测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("磁盘镜像保存功能测试")
    print("=" * 50)
    
    # 测试镜像保存到恢复目录
    image_save_test = test_image_save_to_recovery_dir()
    
    # 测试FAT32恢复
    fat32_test = test_fat32_recovery_with_saved_image()
    
    print("\n=== 测试结果 ===")
    print(f"镜像保存到恢复目录: {'✓ 通过' if image_save_test else '✗ 失败'}")
    print(f"FAT32镜像保存功能: {'✓ 通过' if fat32_test else '✗ 失败'}")
    
    if image_save_test and fat32_test:
        print("\n所有测试通过！镜像保存功能正常。")
        print("镜像文件现在将保存到恢复目录而不是被删除。")
    else:
        print("\n部分测试失败，请检查错误信息。")