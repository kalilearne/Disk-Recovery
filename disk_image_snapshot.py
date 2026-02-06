# -*- coding: utf-8 -*-
"""
磁盘镜像快照模块
用于创建磁盘的逐比特镜像副本，替代VSS快照功能
"""

import os
import platform
import time
import shutil
import tempfile
import threading
from typing import Optional, Dict, Callable
from pathlib import Path

try:
    import win32file
    import win32api
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False
    print("警告: pywin32未安装，某些功能可能受限")

class DiskImageSnapshot:
    """磁盘镜像快照管理类"""
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        """
        初始化磁盘镜像快照管理器
        
        Args:
            progress_callback: 进度回调函数，接收 (current, total, message) 参数
        """
        self.progress_callback = progress_callback
        self.image_path = None
        self.source_disk = None
        self.temp_dir = None
        self.is_creating = False
        self._stop_event = threading.Event()
        
    def _emit_progress(self, current: int, total: int, message: str = ""):
        """发送进度更新"""
        if self.progress_callback:
            self.progress_callback(current, total, message)
    
    def get_disk_size(self, disk_path: str = None) -> int:
        """获取磁盘大小（公共方法）"""
        if disk_path is None:
            disk_path = self.source_disk
        if disk_path is None:
            return 0
        return self._get_disk_size(disk_path)
    
    def _get_disk_size(self, disk_path: str) -> int:
        """获取磁盘大小（私有方法）"""
        try:
            if platform.system() == 'Windows' and WIN32_AVAILABLE:
                # Windows系统使用win32api获取磁盘大小
                # 处理不同格式的驱动器路径
                if self._is_drive_path(disk_path):
                    # 驱动器路径，如 'C:', 'C:\', 'G:\'
                    drive_letter = disk_path[0].upper()
                    drive_root = f"{drive_letter}:\\"
                    
                    print(f"正在检查驱动器 {drive_letter}: 的可访问性...")
                    
                    # 使用多种方法检查驱动器是否存在和可访问
                    drive_accessible = False
                    
                    # 方法1: 检查驱动器根目录
                    try:
                        if os.path.exists(drive_root):
                            drive_accessible = True
                            print(f"✓ 驱动器 {drive_letter}: 根目录可访问")
                    except Exception as e:
                        print(f"检查驱动器根目录失败: {e}")
                    
                    # 方法2: 尝试获取磁盘空间信息
                    disk_size = 0
                    if not drive_accessible:
                        try:
                            free_bytes, total_bytes, _ = win32api.GetDiskFreeSpaceEx(drive_root)
                            if total_bytes > 0:
                                drive_accessible = True
                                disk_size = total_bytes
                                print(f"✓ 驱动器 {drive_letter}: 通过GetDiskFreeSpaceEx检测到，大小: {total_bytes:,} 字节")
                        except Exception as e:
                            print(f"GetDiskFreeSpaceEx检查失败: {e}")
                    
                    # 方法3: 检查逻辑驱动器列表
                    if not drive_accessible:
                        try:
                            drives = win32api.GetLogicalDriveStrings()
                            drive_list = drives.split('\x00')[:-1]
                            if drive_root in drive_list or f"{drive_letter}:" in [d.rstrip('\\') for d in drive_list]:
                                drive_accessible = True
                                print(f"✓ 驱动器 {drive_letter}: 在逻辑驱动器列表中找到")
                        except Exception as e:
                            print(f"检查逻辑驱动器列表失败: {e}")
                    
                    if not drive_accessible:
                        print(f"✗ 驱动器 {drive_letter}: 不存在或无法访问")
                        return 0
                    
                    # 如果已经通过方法2获取到大小，直接返回
                    if disk_size > 0:
                        return disk_size
                    
                    # 尝试获取磁盘大小
                    try:
                        free_bytes, total_bytes, _ = win32api.GetDiskFreeSpaceEx(drive_root)
                        print(f"✓ 驱动器 {drive_letter}: 大小 {total_bytes:,} 字节")
                        return total_bytes
                    except Exception as e:
                        print(f"获取驱动器 {drive_letter}: 大小失败: {e}")
                        # 尝试使用WMI方法
                        wmi_size = self._get_physical_disk_size(drive_letter)
                        if wmi_size > 0:
                            print(f"✓ 通过WMI获取驱动器 {drive_letter}: 大小 {wmi_size:,} 字节")
                            return wmi_size
                        return 0
                else:
                    # 物理磁盘路径
                    handle = win32file.CreateFile(
                        disk_path,
                        win32file.GENERIC_READ,
                        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                        None,
                        win32file.OPEN_EXISTING,
                        0,
                        None
                    )
                    if handle != win32file.INVALID_HANDLE_VALUE:
                        try:
                            size = win32file.GetFileSize(handle)
                            return size
                        finally:
                            win32file.CloseHandle(handle)
            else:
                # Linux/Unix系统
                if os.path.exists(disk_path):
                    stat = os.stat(disk_path)
                    return stat.st_size
                    
        except Exception as e:
            print(f"获取磁盘大小失败: {e}")
            
        return 0
    
    def _is_drive_path(self, path: str) -> bool:
        """判断是否为驱动器路径"""
        if not path or len(path) < 2:
            return False
        
        # 检查是否为驱动器路径格式: X: 或 X:\
        if path[1] == ':' and path[0].isalpha():
            return True
        return False
    
    def _get_physical_disk_size(self, drive_letter: str) -> int:
        """通过物理磁盘路径获取大小"""
        try:
            # 尝试通过WMI或其他方式获取物理磁盘信息
            import subprocess
            result = subprocess.run(
                ['wmic', 'logicaldisk', 'where', f'DeviceID="{drive_letter}:"', 'get', 'Size'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if line.strip().isdigit():
                        return int(line.strip())
        except Exception as e:
            print(f"通过WMI获取磁盘大小失败: {e}")
        
        return 0
    
    def _create_temp_directory(self) -> str:
        """创建临时目录"""
        try:
            self.temp_dir = tempfile.mkdtemp(prefix='disk_image_')
            return self.temp_dir
        except Exception as e:
            print(f"创建临时目录失败: {e}")
            return None
    
    def _cleanup_temp_directory(self):
        """清理临时目录"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
            except Exception as e:
                print(f"清理临时目录失败: {e}")
    
    def create_disk_image(self, source_disk: str, output_path: Optional[str] = None) -> Dict:
        """
        创建磁盘镜像
        
        Args:
            source_disk: 源磁盘路径，如 'C:' 或 '\\\\.\\PhysicalDrive0'
            output_path: 输出镜像文件路径，如果为None则使用临时文件
            
        Returns:
            dict: 创建结果，包含 success, image_path, error 等信息
        """
        result = {
            'success': False,
            'image_path': None,
            'error': None,
            'size': 0,
            'creation_time': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            self.is_creating = True
            self._stop_event.clear()
            self.source_disk = source_disk
            
            # 创建输出路径
            if not output_path:
                temp_dir = self._create_temp_directory()
                if not temp_dir:
                    result['error'] = '无法创建临时目录'
                    return result
                    
                # 生成镜像文件名
                disk_name = source_disk.replace(':', '').replace('\\', '_').replace('.', '_')
                timestamp = int(time.time())
                output_path = os.path.join(temp_dir, f'disk_image_{disk_name}_{timestamp}.img')
            else:
                # 如果指定了输出路径，确保目录存在
                output_dir = os.path.dirname(output_path)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir, exist_ok=True)
                    print(f"创建输出目录: {output_dir}")
            
            self.image_path = output_path
            
            # 获取源磁盘大小
            total_size = self._get_disk_size(source_disk)
            if total_size == 0:
                result['error'] = f'无法获取磁盘 {source_disk} 的大小'
                return result
            
            print(f"开始创建磁盘镜像: {source_disk} -> {output_path}")
            print(f"磁盘大小: {total_size / (1024*1024*1024):.2f} GB")
            
            self._emit_progress(0, total_size, "正在打开源磁盘...")
            
            # 打开源磁盘
            source_handle = None
            actual_disk_path = source_disk
            
            if platform.system() == 'Windows' and WIN32_AVAILABLE:
                # Windows系统
                if self._is_drive_path(source_disk):
                    # 驱动器路径转换为物理路径
                    drive_letter = source_disk[0].upper()
                    actual_disk_path = f'\\\\.\\{drive_letter}:'
                    print(f"将驱动器路径 {source_disk} 转换为物理路径 {actual_disk_path}")
                
                try:
                    source_handle = win32file.CreateFile(
                        actual_disk_path,
                        win32file.GENERIC_READ,
                        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                        None,
                        win32file.OPEN_EXISTING,
                        0,
                        None
                    )
                    
                    if source_handle == win32file.INVALID_HANDLE_VALUE:
                        result['error'] = f'无法打开源磁盘 {actual_disk_path}'
                        return result
                        
                except Exception as e:
                    result['error'] = f'打开磁盘失败: {e}'
                    return result
            else:
                # Linux/Unix系统
                if not os.path.exists(source_disk):
                    result['error'] = f'源磁盘 {source_disk} 不存在'
                    return result
            
            # 创建输出目录
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # 开始复制
            chunk_size = 64 * 1024  # 64KB chunks for better progress monitoring
            copied_size = 0
            
            print(f"开始数据复制，chunk大小: {chunk_size} 字节")
            self._emit_progress(0, total_size, "正在创建磁盘镜像...")
            
            try:
                if platform.system() == 'Windows' and WIN32_AVAILABLE:
                    # Windows系统使用win32file
                    with open(output_path, 'wb') as output_file:
                        read_count = 0
                        while copied_size < total_size and not self._stop_event.is_set():
                            # 计算本次读取大小
                            read_size = min(chunk_size, total_size - copied_size)
                            
                            # 读取数据
                            try:
                                _, data = win32file.ReadFile(source_handle, read_size)
                                read_count += 1
                                
                                if not data:
                                    print(f"读取到空数据，已读取 {read_count} 次，复制了 {copied_size} 字节")
                                    break
                                    
                                # 写入数据
                                output_file.write(data)
                                copied_size += len(data)
                                
                                # 每1000次读取输出一次调试信息
                                if read_count % 1000 == 0:
                                    print(f"已读取 {read_count} 次，复制了 {copied_size:,} 字节，数据块大小: {len(data)} 字节")
                                
                                # 更新进度
                                progress_percent = (copied_size / total_size) * 100
                                self._emit_progress(
                                    copied_size, 
                                    total_size, 
                                    f"已复制: {copied_size / (1024*1024*1024):.2f} GB ({progress_percent:.1f}%)"
                                )
                                
                            except Exception as e:
                                if "到达文件结尾" in str(e) or "EOF" in str(e):
                                    break
                                else:
                                    raise
                else:
                    # Linux/Unix系统
                    with open(source_disk, 'rb') as source_file:
                        with open(output_path, 'wb') as output_file:
                            while copied_size < total_size and not self._stop_event.is_set():
                                data = source_file.read(chunk_size)
                                if not data:
                                    break
                                    
                                output_file.write(data)
                                copied_size += len(data)
                                
                                # 更新进度
                                progress_percent = (copied_size / total_size) * 100
                                self._emit_progress(
                                    copied_size, 
                                    total_size, 
                                    f"已复制: {copied_size / (1024*1024*1024):.2f} GB ({progress_percent:.1f}%)"
                                )
                
            finally:
                # 关闭句柄
                if source_handle and platform.system() == 'Windows' and WIN32_AVAILABLE:
                    win32file.CloseHandle(source_handle)
            
            if self._stop_event.is_set():
                result['error'] = '用户取消了镜像创建'
                # 删除未完成的镜像文件
                if os.path.exists(output_path):
                    os.remove(output_path)
                return result
            
            # 验证镜像文件
            if not os.path.exists(output_path):
                result['error'] = '镜像文件创建失败'
                return result
            
            image_size = os.path.getsize(output_path)
            print(f"磁盘镜像创建完成: {output_path}")
            print(f"原始磁盘大小: {total_size / (1024*1024*1024):.2f} GB ({total_size:,} 字节)")
            print(f"镜像文件大小: {image_size / (1024*1024*1024):.2f} GB ({image_size:,} 字节)")
            print(f"复制完整性: {(image_size / total_size * 100):.2f}%")
            
            # 检查大小是否匹配
            if image_size != total_size:
                print(f"警告: 镜像大小与原始磁盘大小不匹配！")
                print(f"差异: {abs(image_size - total_size):,} 字节")
            
            result['success'] = True
            result['image_path'] = output_path
            result['size'] = image_size
            
            self._emit_progress(total_size, total_size, "磁盘镜像创建完成")
            
        except Exception as e:
            result['error'] = f'创建磁盘镜像时出错: {e}'
            print(f"创建磁盘镜像失败: {e}")
            
        finally:
            self.is_creating = False
            
        return result
    
    def stop_creation(self):
        """停止镜像创建"""
        self._stop_event.set()
    
    def get_image_path(self) -> Optional[str]:
        """获取镜像文件路径"""
        return self.image_path
    
    def cleanup(self, keep_image: bool = False):
        """清理资源
        
        Args:
            keep_image: 是否保留镜像文件，默认为False（删除镜像）
        """
        self.stop_creation()
        
        if not keep_image:
            self._cleanup_temp_directory()
            if self.image_path and self.temp_dir and self.image_path.startswith(self.temp_dir):
                # 如果镜像在临时目录中，删除它
                try:
                    if os.path.exists(self.image_path):
                        os.remove(self.image_path)
                        print(f"已删除临时镜像文件: {self.image_path}")
                except Exception as e:
                    print(f"删除临时镜像文件失败: {e}")
        else:
            print(f"保留镜像文件: {self.image_path}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.cleanup()

def create_disk_image_snapshot(disk_path: str, output_path: Optional[str] = None, 
                              progress_callback: Optional[Callable] = None) -> Optional[Dict]:
    """
    为指定磁盘路径创建镜像快照
    
    Args:
        disk_path: 磁盘路径，如 'C:' 或 '/dev/sda1'
        output_path: 输出镜像文件路径，如果为None则使用临时文件
        progress_callback: 进度回调函数
        
    Returns:
        dict: 镜像创建结果，如果失败返回None
    """
    try:
        print(f"正在为磁盘 {disk_path} 创建镜像快照...")
        
        # 创建镜像快照
        snapshot = DiskImageSnapshot(progress_callback)
        result = snapshot.create_disk_image(disk_path, output_path)
        
        if result['success']:
            print(f"磁盘镜像快照创建成功: {result['image_path']}")
            # 添加快照对象到结果中，以便后续清理
            result['snapshot_object'] = snapshot
            return result
        else:
            print(f"磁盘镜像快照创建失败: {result['error']}")
            snapshot.cleanup()
            return None
            
    except Exception as e:
        print(f"创建磁盘镜像快照时出错: {e}")
        return None

# 测试函数
if __name__ == "__main__":
    def test_progress(current, total, message):
        percent = (current / total) * 100 if total > 0 else 0
        print(f"\r进度: {percent:.1f}% - {message}", end='', flush=True)
    
    print("磁盘镜像快照功能测试")
    
    # 测试创建镜像
    if platform.system() == 'Windows':
        print("测试Windows磁盘镜像创建...")
        result = create_disk_image_snapshot('C:', progress_callback=test_progress)
        if result:
            print(f"\n镜像创建成功: {result['image_path']}")
            # 清理
            if 'snapshot_object' in result:
                result['snapshot_object'].cleanup()
        else:
            print("\n镜像创建失败")
    else:
        print("磁盘镜像快照功能在所有平台上都可用")