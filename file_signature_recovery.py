#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import platform
import datetime
import struct
import time
import traceback
from disk_reader import DiskReader
from disk_image_snapshot import DiskImageSnapshot, create_disk_image_snapshot

class FileSignatureRecovery:
    """文件签名恢复类，提供基于文件签名的数据恢复功能"""
    
    # 详细的文件签名定义（用于高级恢复）
    DETAILED_SIGNATURES = {
        # 图片文件
        b'\xFF\xD8\xFF': {'ext': '.jpg', 'type': '图片', 'desc': 'JPEG图像', 'size': 2 * 1024 * 1024},  # 2MB
        b'\x89PNG\r\n\x1A\n': {'ext': '.png', 'type': '图片', 'desc': 'PNG图像', 'size': 1 * 1024 * 1024},  # 1MB
        b'GIF8': {'ext': '.gif', 'type': '图片', 'desc': 'GIF图像', 'size': 512 * 1024},  # 512KB
        b'BM': {'ext': '.bmp', 'type': '图片', 'desc': 'BMP图像', 'size': 5 * 1024 * 1024},  # 5MB
        
        # 文档文件
        b'%PDF': {'ext': '.pdf', 'type': '文档', 'desc': 'PDF文档', 'size': 10 * 1024 * 1024},  # 10MB
        b'\xFF\xFE': {'ext': '.txt', 'type': '文档', 'desc': 'Unicode UTF-16LE Text', 'size': 64 * 1024},  # 64KB
        b'\xEF\xBB\xBF': {'ext': '.txt', 'type': '文档', 'desc': 'Unicode UTF-8 Text', 'size': 64 * 1024},  # 64KB
        b'\xD0\xCF\x11\xE0': {'ext': '.doc', 'type': '文档', 'desc': 'Microsoft Office文档', 'size': 5 * 1024 * 1024},  # 5MB
        b'PK\x03\x04\x14\x00\x06\x00': {'ext': '.docx', 'type': '文档', 'desc': 'Microsoft Word 2007+文档', 'size': 3 * 1024 * 1024},  # 3MB
        
        # 压缩文件
        b'PK\x03\x04': {'ext': '.zip', 'type': '压缩文件', 'desc': 'ZIP压缩文件', 'size': 50 * 1024 * 1024},  # 50MB
        b'Rar!\x1A\x07\x00': {'ext': '.rar', 'type': '压缩文件', 'desc': 'RAR压缩文件', 'size': 50 * 1024 * 1024},  # 50MB
        b'7z\xBC\xAF\'\x1C': {'ext': '.7z', 'type': '压缩文件', 'desc': '7-Zip压缩文件', 'size': 50 * 1024 * 1024},  # 50MB
        
        # 音视频文件
        b'ID3': {'ext': '.mp3', 'type': '音频', 'desc': 'MP3音频文件', 'size': 10 * 1024 * 1024},  # 10MB
        b'\x00\x00\x00\x18ftypmp42': {'ext': '.mp4', 'type': '视频', 'desc': 'MP4视频文件', 'size': 100 * 1024 * 1024},  # 100MB
        b'\x00\x00\x00\x14ftypqt': {'ext': '.mov', 'type': '视频', 'desc': 'QuickTime视频文件', 'size': 100 * 1024 * 1024},  # 100MB
        
        # 可执行文件
        b'MZ': {'ext': '.exe', 'type': '可执行文件', 'desc': 'Windows可执行文件', 'size': 20 * 1024 * 1024},  # 20MB
        b'\x7FELF': {'ext': '', 'type': '可执行文件', 'desc': 'Linux可执行文件', 'size': 20 * 1024 * 1024},  # 20MB
    }
    
    # 兼容性别名
    FILE_SIGNATURES = DETAILED_SIGNATURES
    
    @staticmethod
    def get_cluster_info(disk_path):
        """获取磁盘的簇信息"""
        try:
            # 检查是否为镜像文件
            if os.path.isfile(disk_path):
                print(f"检测到镜像文件，正在分析: {disk_path}")
                try:
                    with open(disk_path, 'rb') as f:
                        # 读取引导扇区
                        boot_sector = f.read(512)
                        
                        if len(boot_sector) >= 512:
                            # 尝试解析FAT32
                            if boot_sector[0x52:0x5A] == b'FAT32   ':
                                bytes_per_sector = struct.unpack('<H', boot_sector[0x0B:0x0D])[0]
                                sectors_per_cluster = boot_sector[0x0D]
                                cluster_size = bytes_per_sector * sectors_per_cluster
                                print(f"镜像文件系统: FAT32, 簇大小: {cluster_size}, 扇区大小: {bytes_per_sector}")
                                return {'type': 'FAT32', 'cluster_size': cluster_size, 'sector_size': bytes_per_sector}
                            
                            # 尝试解析NTFS
                            elif boot_sector[3:7] == b'NTFS':
                                bytes_per_sector = struct.unpack('<H', boot_sector[0x0B:0x0D])[0]
                                sectors_per_cluster = boot_sector[0x0D]
                                cluster_size = bytes_per_sector * sectors_per_cluster
                                print(f"镜像文件系统: NTFS, 簇大小: {cluster_size}, 扇区大小: {bytes_per_sector}")
                                return {'type': 'NTFS', 'cluster_size': cluster_size, 'sector_size': bytes_per_sector}
                            
                            # 尝试查找MBR分区表中的活动分区
                            elif boot_sector[510:512] == b'\x55\xAA':  # MBR签名
                                print("检测到MBR，查找活动分区...")
                                # 分区表从偏移0x1BE开始
                                for i in range(4):
                                    partition_offset = 0x1BE + i * 16
                                    if partition_offset + 16 <= len(boot_sector):
                                        partition_entry = boot_sector[partition_offset:partition_offset + 16]
                                        # 检查分区是否活动（第一个字节为0x80）
                                        if partition_entry[0] == 0x80:
                                            # 获取分区起始扇区
                                            start_sector = struct.unpack('<L', partition_entry[8:12])[0]
                                            print(f"找到活动分区，起始扇区: {start_sector}")
                                            
                                            # 读取分区的引导扇区
                                            f.seek(start_sector * 512)
                                            partition_boot = f.read(512)
                                            
                                            if len(partition_boot) >= 512:
                                                # 再次尝试解析文件系统
                                                if partition_boot[0x52:0x5A] == b'FAT32   ':
                                                    bytes_per_sector = struct.unpack('<H', partition_boot[0x0B:0x0D])[0]
                                                    sectors_per_cluster = partition_boot[0x0D]
                                                    cluster_size = bytes_per_sector * sectors_per_cluster
                                                    print(f"分区文件系统: FAT32, 簇大小: {cluster_size}, 扇区大小: {bytes_per_sector}")
                                                    return {'type': 'FAT32', 'cluster_size': cluster_size, 'sector_size': bytes_per_sector}
                                                elif partition_boot[3:7] == b'NTFS':
                                                    bytes_per_sector = struct.unpack('<H', partition_boot[0x0B:0x0D])[0]
                                                    sectors_per_cluster = partition_boot[0x0D]
                                                    cluster_size = bytes_per_sector * sectors_per_cluster
                                                    print(f"分区文件系统: NTFS, 簇大小: {cluster_size}, 扇区大小: {bytes_per_sector}")
                                                    return {'type': 'NTFS', 'cluster_size': cluster_size, 'sector_size': bytes_per_sector}
                            
                            print("无法识别镜像文件系统类型，使用默认值")
                        else:
                            print("镜像文件引导扇区读取不完整")
                            
                except Exception as e:
                    print(f"分析镜像文件错误: {e}")
                    traceback.print_exc()
            
            # 处理物理磁盘或分区
            elif platform.system() == 'Windows':
                import win32file
                try:
                    # 确保路径格式正确
                    if disk_path.endswith('\\'):
                        disk_path = f"\\\\.\\{disk_path[0]}:"
                    elif not disk_path.startswith('\\\\.\\'): 
                        # 如果不是原始设备路径，尝试转换
                        if len(disk_path) == 2 and disk_path[1] == ':':
                            disk_path = f"\\\\.\\{disk_path[0]}:"
                    
                    print(f"Opening disk: {disk_path}")
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
                        # 读取引导扇区
                        win32file.SetFilePointer(handle, 0, win32file.FILE_BEGIN)
                        result, boot_sector = win32file.ReadFile(handle, 512)
                        win32file.CloseHandle(handle)
                        
                        if len(boot_sector) >= 512:
                            # 尝试解析FAT32
                            if boot_sector[0x52:0x5A] == b'FAT32   ':
                                bytes_per_sector = struct.unpack('<H', boot_sector[0x0B:0x0D])[0]
                                sectors_per_cluster = boot_sector[0x0D]
                                cluster_size = bytes_per_sector * sectors_per_cluster
                                return {'type': 'FAT32', 'cluster_size': cluster_size, 'sector_size': bytes_per_sector}
                            
                            # 尝试解析NTFS
                            elif boot_sector[3:7] == b'NTFS':
                                bytes_per_sector = struct.unpack('<H', boot_sector[0x0B:0x0D])[0]
                                sectors_per_cluster = boot_sector[0x0D]
                                cluster_size = bytes_per_sector * sectors_per_cluster
                                return {'type': 'NTFS', 'cluster_size': cluster_size, 'sector_size': bytes_per_sector}
                except Exception as e:
                    print(f"获取簇信息错误 - 磁盘路径: {disk_path}, 错误: {e}")
                    traceback.print_exc()
            
            # 默认值
            print("使用默认簇信息")
            return {'type': 'Unknown', 'cluster_size': 4096, 'sector_size': 512}
        except Exception as e:
            print(f"获取簇信息失败 - 磁盘路径: {disk_path}, 错误类型: {type(e).__name__}, 错误: {e}")
            traceback.print_exc()
            return {'type': 'Unknown', 'cluster_size': 4096, 'sector_size': 512}
    
    @staticmethod
    def estimate_file_size(data, signature_info, file_offset):
        """根据文件类型和内容估算文件大小"""
        try:
            file_type = signature_info['type']
            ext = signature_info['ext']
            
            # JPEG文件大小估算
            if ext in ['.jpg', '.jpeg']:
                # 查找JPEG结束标记 FF D9
                end_marker = b'\xFF\xD9'
                end_pos = data.find(end_marker)
                if end_pos != -1:
                    return end_pos + 2
            
            # PNG文件大小估算
            elif ext == '.png':
                # PNG文件有固定的结构，查找IEND块
                iend_marker = b'IEND\xAE\x42\x60\x82'
                end_pos = data.find(iend_marker)
                if end_pos != -1:
                    return end_pos + 8
            
            # GIF文件大小估算
            elif ext == '.gif':
                # 查找GIF结束标记
                end_marker = b'\x00\x3B'
                end_pos = data.find(end_marker)
                if end_pos != -1:
                    return end_pos + 2
            
            # PDF文件大小估算
            elif ext == '.pdf':
                # 查找PDF结束标记
                end_marker = b'%%EOF'
                end_pos = data.rfind(end_marker)  # 使用rfind查找最后一个
                if end_pos != -1:
                    return end_pos + 5
            
            # ZIP文件大小估算
            elif ext == '.zip':
                # 查找ZIP中央目录结束记录
                end_marker = b'PK\x05\x06'
                end_pos = data.rfind(end_marker)
                if end_pos != -1 and end_pos + 22 <= len(data):
                    return end_pos + 22
            
            # 默认大小限制
            default_size = min(len(data), 10 * 1024 * 1024)  # 最大10MB
            return max(1024, default_size)  # 确保至少1KB
            
        except Exception as e:
            print(f"估算文件大小错误: {e}")
            default_size = min(len(data) if data else 1024 * 1024, 5 * 1024 * 1024)  # 默认最大5MB
            return max(1024, default_size)  # 确保至少1KB
    
    @staticmethod
    def is_cluster_aligned(offset, cluster_size):
        """检查偏移量是否对齐到簇边界"""
        return offset % cluster_size == 0
    
    @staticmethod
    def recover_files_by_signature_with_snapshot(disk_path, selected_types=None, save_dir=None, reverse=False, filename_map=None):
        """
        使用磁盘镜像快照进行文件签名恢复（推荐方法）
        
        Args:
            disk_path: 磁盘路径
            selected_types: 选定的文件类型
            save_dir: 保存目录
            reverse: 是否逆序扫描
            filename_map: 文件名映射
            
        Returns:
            dict: 恢复结果
        """
        print("=== 使用磁盘镜像快照进行文件签名恢复 ===")
        
        try:
            # 检查是否为挂载的分区
            is_mounted_partition = (
                len(disk_path) >= 2 and 
                disk_path[1] == ':' and 
                (len(disk_path) == 2 or disk_path.endswith('\\'))
            )
            
            if not is_mounted_partition:
                print(f"磁盘路径 {disk_path} 不是挂载的分区，使用常规方法")
                return FileSignatureRecovery.recover_files_by_signature(
                    disk_path, selected_types, save_dir, reverse, filename_map
                )
            
            print(f"检测到挂载分区: {disk_path}")
            print("正在创建磁盘镜像快照以安全访问磁盘数据...")
            
            # 生成唯一的镜像文件名
            disk_name = disk_path.replace(':', '').replace('\\', '_').replace('.', '_')
            timestamp = int(time.time())
            image_filename = f'disk_image_{disk_name}_{timestamp}.img'
            image_path = os.path.join(save_dir, image_filename) if save_dir else None
            
            print(f"镜像将保存到: {image_path}" if image_path else "使用临时镜像文件")
            
            # 定义进度回调函数
            def progress_callback(current, total, message):
                if total > 0:
                    percent = (current / total) * 100
                    print(f"\r镜像创建进度: {percent:.1f}% - {message}", end='', flush=True)
                else:
                    print(f"\r{message}", end='', flush=True)
            
            # 创建磁盘镜像快照
            snapshot_result = create_disk_image_snapshot(disk_path, progress_callback=progress_callback, output_path=image_path)
            print()  # 换行
            
            if not snapshot_result or not snapshot_result['success']:
                error_msg = snapshot_result['error'] if snapshot_result else '未知错误'
                print(f"创建磁盘镜像失败: {error_msg}")
                print("使用常规方法...")
                return FileSignatureRecovery.recover_files_by_signature(
                    disk_path, selected_types, save_dir, reverse, filename_map
                )
            
            image_path = snapshot_result['image_path']
            print(f"磁盘镜像创建成功: {image_path}")
            
            try:
                # 使用镜像文件进行恢复
                print("正在从磁盘镜像中恢复文件...")
                result = FileSignatureRecovery.recover_files_by_signature(
                    image_path, selected_types, save_dir, reverse, filename_map
                )
                
                # 在恢复摘要中添加镜像信息
                if save_dir:
                    summary_path = os.path.join(save_dir, "恢复摘要.txt")
                    try:
                        with open(summary_path, 'a', encoding='utf-8') as f:
                            f.write(f"\n\n=== 磁盘镜像快照信息 ===\n")
                            f.write(f"原始磁盘路径: {disk_path}\n")
                            f.write(f"镜像文件路径: {snapshot_result['image_path']}\n")
                            f.write(f"镜像大小: {snapshot_result['size'] / (1024*1024*1024):.2f} GB\n")
                            f.write(f"创建时间: {snapshot_result['creation_time']}\n")
                            f.write(f"- 使用磁盘镜像快照技术进行安全恢复\n")
                            f.write(f"- 避免了对原始磁盘的直接访问\n")
                            f.write(f"- 镜像文件已保存到恢复目录，可用于后续分析\n")
                            f.write(f"- 镜像文件名: {os.path.basename(snapshot_result['image_path'])}\n")
                    except Exception as e:
                        print(f"添加镜像信息到摘要失败: {e}")
                
                return result
                
            finally:
                # 保留镜像文件，只清理临时资源
                try:
                    if 'snapshot_object' in snapshot_result:
                        snapshot_result['snapshot_object'].cleanup(keep_image=True)
                        print("磁盘镜像已保存到恢复目录")
                except Exception as e:
                    print(f"保存磁盘镜像时出错: {e}")
                    
        except Exception as e:
            print(f"磁盘镜像快照恢复失败: {e}")
            traceback.print_exc()
            print("使用常规方法...")
            return FileSignatureRecovery.recover_files_by_signature(
                disk_path, selected_types, save_dir, reverse, filename_map
            )
    

    
    @staticmethod
    def recover_files_by_signature(disk_path, selected_types=None, save_dir=None, reverse=False, filename_map=None):
        """根据文件签名恢复文件"""
        if not save_dir:
            save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recovered_files")
        
        os.makedirs(save_dir, exist_ok=True)
        
        # 获取磁盘簇信息
        cluster_info = FileSignatureRecovery.get_cluster_info(disk_path)
        cluster_size = cluster_info['cluster_size']
        sector_size = cluster_info['sector_size']
        print(f"磁盘信息: 文件系统={cluster_info['type']}, 簇大小={cluster_size}字节, 扇区大小={sector_size}字节")
        
        # 如果没有指定文件类型，则恢复所有类型
        if not selected_types:
            selected_types = list(FileSignatureRecovery.DETAILED_SIGNATURES.keys())
        
        # 过滤签名列表，只保留选定类型的签名
        filtered_signatures = {}
        for sig, info in FileSignatureRecovery.DETAILED_SIGNATURES.items():
            # 将字节签名转换为十六进制字符串进行比较
            sig_hex = sig.hex().upper()
            if not selected_types or sig in selected_types or sig_hex in selected_types:
                filtered_signatures[sig] = info
        
        # 创建类型目录
        type_dirs = {}
        for sig, info in filtered_signatures.items():
            file_type = info['type']
            if file_type not in type_dirs:
                type_dir = os.path.join(save_dir, file_type)
                os.makedirs(type_dir, exist_ok=True)
                type_dirs[file_type] = type_dir
        
        # 恢复文件
        recovered_files = []
        total_files_found = 0
        cluster_aligned_files = 0
        
        try:
            # 打开磁盘
            if platform.system() == 'Windows':
                import win32file
                import winioctlcon
                
                # 检查是否为镜像文件
                is_image_file = os.path.isfile(disk_path)
                
                if is_image_file:
                    # 处理镜像文件
                    print(f"检测到镜像文件: {disk_path}")
                    disk_size = os.path.getsize(disk_path)
                    
                    # 设置扫描参数
                    # 对于小文件，使用更小的chunk_size
                    if disk_size < 10 * 1024 * 1024:  # 小于10MB
                        chunk_size = min(64 * 1024, disk_size)  # 64KB或文件大小
                        step = 4 * 1024  # 4KB步长
                    else:
                        chunk_size = 1024 * 1024  # 1MB
                        step = chunk_size
                    
                    # 设置扫描范围
                    start_pos = 0
                    end_pos = disk_size
                    
                    # 如果是逆序扫描，从末尾开始
                    if reverse:
                        current_pos = end_pos - chunk_size
                        step = -step  # 使step为负值
                    else:
                        current_pos = start_pos
                    
                    # 使用普通文件读取方式处理镜像文件
                    with open(disk_path, 'rb') as disk_file:
                        # 扫描镜像文件
                        while (not reverse and current_pos < end_pos) or (reverse and current_pos >= start_pos):
                            # 移动到当前位置
                            disk_file.seek(current_pos)
                            
                            # 读取数据块
                            try:
                                read_size = min(chunk_size, end_pos - current_pos) if not reverse else min(chunk_size, current_pos + 1)
                                data = disk_file.read(read_size)
                                if not data:
                                    break
                            except Exception as e:
                                print(f"读取数据块错误: {e}")
                                # 如果读取失败，跳过此块
                                current_pos = current_pos + step if not reverse else current_pos + step
                                continue
                            
                            # 搜索文件签名
                            for signature, info in filtered_signatures.items():
                                # signature已经是bytes对象，直接使用
                                sig_bytes = signature
                                offset = data.find(sig_bytes)
                                
                                while offset != -1:
                                    file_offset = current_pos + offset
                                    
                                    # 检查簇对齐
                                    cluster_offset = file_offset % cluster_size
                                    is_cluster_aligned = cluster_offset == 0
                                    
                                    if is_cluster_aligned:
                                        cluster_aligned_files += 1
                                    
                                    # 估算文件大小
                                    estimated_size = FileSignatureRecovery.estimate_file_size(data, info, file_offset)
                                    if estimated_size <= 0:
                                        estimated_size = info.get('size', 1024 * 1024)  # 默认1MB
                                    
                                    # 确保估算大小在合理范围内
                                    estimated_size = max(1024, min(estimated_size, 100 * 1024 * 1024))  # 1KB到100MB
                                    
                                    # 构造文件名
                                    file_type = info['type']
                                    extension = info['ext'].lstrip('.')  # 移除开头的点号
                                    
                                    if filename_map and signature in filename_map:
                                        filename = f"{filename_map[signature]}.{extension}"
                                    else:
                                        filename = f"recovered_{total_files_found:06d}_{file_offset:016x}.{extension}"
                                    
                                    # 保存文件
                                    type_dir = type_dirs[file_type]
                                    file_path = os.path.join(type_dir, filename)
                                    
                                    try:
                                        # 验证估算大小
                                        if estimated_size <= 0:
                                            print(f"\n跳过文件: 估算大小无效 ({estimated_size})")
                                            continue
                                        
                                        # 限制最大读取大小，避免内存问题
                                        max_read_size = min(estimated_size, 50 * 1024 * 1024)  # 最大50MB
                                        
                                        # 移动到文件开始位置
                                        disk_file.seek(file_offset)
                                        file_data = disk_file.read(max_read_size)
                                        
                                        # 验证读取的数据
                                        if not file_data:
                                            print(f"\n跳过文件: 无法读取数据 (偏移: 0x{file_offset:x})")
                                            continue
                                        
                                        # 确保目录存在
                                        os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                        
                                        # 保存文件
                                        with open(file_path, 'wb') as f:
                                            f.write(file_data)
                                        
                                        # 验证文件是否成功保存
                                        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                                            print(f"\n文件保存验证失败: {file_path}")
                                            continue
                                        
                                        recovered_files.append({
                                            'name': filename,
                                            'path': file_path,
                                            'offset': file_offset,
                                            'size': len(file_data),
                                            'estimated_size': estimated_size,
                                            'type': file_type,
                                            'description': info['desc'],
                                            'cluster_aligned': is_cluster_aligned,
                                            'cluster_offset': cluster_offset
                                        })
                                        
                                        total_files_found += 1
                                        print(f"\r恢复文件: {total_files_found} - {filename} (偏移: 0x{file_offset:x})", end='', flush=True)
                                        
                                    except Exception as e:
                                        print(f"\n保存文件失败: {e}")
                                        print(f"文件路径: {file_path}")
                                        print(f"文件偏移: 0x{file_offset:x}")
                                        print(f"估算大小: {estimated_size}")
                                        import traceback
                                        traceback.print_exc()
                                    
                                    # 查找下一个匹配
                                    offset = data.find(sig_bytes, offset + 1)
                            
                            # 移动到下一个位置
                            if not reverse:
                                current_pos = current_pos + step
                            else:
                                current_pos = current_pos - step
                            
                            # 显示进度
                            if end_pos > 0:
                                if not reverse:
                                    progress = min((current_pos / end_pos) * 100, 100.0)
                                else:
                                    progress = min(((end_pos - current_pos) / end_pos) * 100, 100.0)
                                print(f"\r扫描进度: {progress:.1f}% - 已找到 {total_files_found} 个文件", end='', flush=True)
                else:
                    # 处理物理磁盘设备
                    print(f"检测到磁盘设备: {disk_path}")
                    
                    # 确保路径格式正确
                    if disk_path.endswith('\\'):
                        disk_path = f"\\\\.\\{disk_path[0]}:"
                    
                    try:
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
                            # 获取磁盘大小
                            try:
                                disk_size = win32file.DeviceIoControl(
                                    handle,
                                    winioctlcon.IOCTL_DISK_GET_LENGTH_INFO,
                                    None,
                                    8
                                )
                                disk_size = struct.unpack('Q', disk_size)[0]
                            except:
                                # 如果无法获取磁盘大小，使用默认值
                                disk_size = 100 * 1024 * 1024 * 1024  # 100GB
                            
                            # 设置扫描参数
                            chunk_size = 1024 * 1024  # 1MB
                            step = chunk_size
                            
                            # 设置扫描范围
                            start_pos = 0
                            end_pos = disk_size
                            
                            # 如果是逆序扫描，从末尾开始
                            if reverse:
                                current_pos = end_pos - chunk_size
                                step = -chunk_size
                            else:
                                current_pos = start_pos
                            
                            # 扫描物理磁盘
                            while (not reverse and current_pos < end_pos) or (reverse and current_pos >= start_pos):
                                # 移动到当前位置
                                win32file.SetFilePointer(handle, current_pos, win32file.FILE_BEGIN)
                                
                                # 读取数据块
                                try:
                                    read_size = min(chunk_size, end_pos - current_pos) if not reverse else min(chunk_size, current_pos + 1)
                                    _, data = win32file.ReadFile(handle, read_size)
                                    if not data:
                                        break
                                except Exception as e:
                                    print(f"读取数据块错误: {e}")
                                    # 如果读取失败，跳过此块
                                    current_pos = current_pos + step if not reverse else current_pos + step
                                    continue
                                
                                # 搜索文件签名
                                for signature, info in filtered_signatures.items():
                                    # signature已经是bytes对象，直接使用
                                    sig_bytes = signature
                                    offset = data.find(sig_bytes)
                                    
                                    while offset != -1:
                                        file_offset = current_pos + offset
                                        
                                        # 检查簇对齐
                                        cluster_offset = file_offset % cluster_size
                                        is_cluster_aligned = cluster_offset == 0
                                        
                                        if is_cluster_aligned:
                                            cluster_aligned_files += 1
                                        
                                        # 估算文件大小
                                        estimated_size = FileSignatureRecovery.estimate_file_size(data, info, file_offset)
                                        if estimated_size <= 0:
                                            estimated_size = info.get('size', 1024 * 1024)  # 默认1MB
                                        
                                        # 确保估算大小在合理范围内
                                        estimated_size = max(1024, min(estimated_size, 100 * 1024 * 1024))  # 1KB到100MB
                                        
                                        # 构造文件名
                                        file_type = info['type']
                                        extension = info['ext'].lstrip('.')  # 移除开头的点号
                                        
                                        if filename_map and signature in filename_map:
                                            filename = f"{filename_map[signature]}.{extension}"
                                        else:
                                            filename = f"recovered_{total_files_found:06d}_{file_offset:016x}.{extension}"
                                        
                                        # 保存文件
                                        type_dir = type_dirs[file_type]
                                        file_path = os.path.join(type_dir, filename)
                                        
                                        try:
                                            # 验证估算大小
                                            if estimated_size <= 0:
                                                print(f"\n跳过文件: 估算大小无效 ({estimated_size})")
                                                continue
                                            
                                            # 限制最大读取大小，避免内存问题
                                            max_read_size = min(estimated_size, 50 * 1024 * 1024)  # 最大50MB
                                            
                                            # 移动到文件开始位置
                                            win32file.SetFilePointer(handle, file_offset, win32file.FILE_BEGIN)
                                            _, file_data = win32file.ReadFile(handle, max_read_size)
                                            
                                            # 验证读取的数据
                                            if not file_data:
                                                print(f"\n跳过文件: 无法读取数据 (偏移: 0x{file_offset:x})")
                                                continue
                                            
                                            # 确保目录存在
                                            os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                            
                                            # 保存文件
                                            with open(file_path, 'wb') as f:
                                                f.write(file_data)
                                            
                                            # 验证文件是否成功保存
                                            if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                                                print(f"\n文件保存验证失败: {file_path}")
                                                continue
                                            
                                            recovered_files.append({
                                                'name': filename,
                                                'path': file_path,
                                                'offset': file_offset,
                                                'size': len(file_data),
                                                'estimated_size': estimated_size,
                                                'type': file_type,
                                                'description': info['desc'],
                                                'cluster_aligned': is_cluster_aligned,
                                                'cluster_offset': cluster_offset
                                            })
                                            
                                            total_files_found += 1
                                            print(f"\r恢复文件: {total_files_found} - {filename} (偏移: 0x{file_offset:x})", end='', flush=True)
                                            
                                        except Exception as e:
                                            print(f"\n保存文件失败: {e}")
                                            print(f"文件路径: {file_path}")
                                            print(f"文件偏移: 0x{file_offset:x}")
                                            print(f"估算大小: {estimated_size}")
                                            import traceback
                                            traceback.print_exc()
                                        
                                        # 查找下一个匹配
                                        offset = data.find(sig_bytes, offset + 1)
                                
                                # 移动到下一个位置
                                current_pos = current_pos + step if not reverse else current_pos + step
                                
                                # 显示进度
                                if end_pos > 0:
                                    progress = (current_pos / end_pos) * 100 if not reverse else ((end_pos - current_pos) / end_pos) * 100
                                    print(f"\r扫描进度: {progress:.1f}% - 已找到 {total_files_found} 个文件", end='', flush=True)
                            
                            # 关闭句柄
                            win32file.CloseHandle(handle)
                        
                        else:
                            result['error'] = f'无法打开源磁盘 {disk_path}'
                            return result
                    except Exception as e:
                        print(f"打开磁盘错误: {e}")
                        traceback.print_exc()
            else:
                # Linux系统下的实现
                try:
                    # 获取磁盘大小
                    disk_size = os.path.getsize(disk_path) if os.path.isfile(disk_path) else 0
                    if disk_size == 0:
                        # 如果是设备文件，尝试使用其他方法获取大小
                        try:
                            with open(disk_path, 'rb') as f:
                                f.seek(0, 2)  # 移动到文件末尾
                                disk_size = f.tell()
                        except:
                            disk_size = 100 * 1024 * 1024 * 1024  # 默认100GB
                    
                    # 设置扫描参数
                    chunk_size = 1024 * 1024  # 1MB
                    step = chunk_size
                    
                    # 设置扫描范围
                    start_pos = 0
                    end_pos = disk_size
                    
                    # 如果是逆序扫描，从末尾开始
                    if reverse:
                        current_pos = end_pos - chunk_size
                        step = -chunk_size
                    else:
                        current_pos = start_pos
                    
                    # 打开磁盘
                    with open(disk_path, 'rb') as disk_file:
                        # 扫描磁盘
                        while (not reverse and current_pos < end_pos) or (reverse and current_pos >= start_pos):
                            # 移动到当前位置
                            disk_file.seek(current_pos)
                            
                            # 读取数据块
                            try:
                                data = disk_file.read(min(chunk_size, end_pos - current_pos) if not reverse else min(chunk_size, current_pos + 1))
                            except Exception as e:
                                print(f"读取数据块错误: {e}")
                                # 如果读取失败，跳过此块
                                current_pos = current_pos + step if not reverse else current_pos + step
                                continue
                            
                            # 在数据块中查找文件签名
                            for sig, info in filtered_signatures.items():
                                sig_len = len(sig)
                                offset = 0
                                while True:
                                    # 查找签名
                                    pos = data.find(sig, offset)
                                    if pos == -1:
                                        break
                                    
                                    # 计算文件在磁盘中的实际偏移量
                                    file_offset = current_pos + pos
                                    total_files_found += 1
                                    
                                    # 检查是否对齐到簇边界
                                    is_aligned = FileSignatureRecovery.is_cluster_aligned(file_offset, cluster_size)
                                    if is_aligned:
                                        cluster_aligned_files += 1
                                    
                                    # 获取用于文件大小估算的数据
                                    analysis_size = min(10 * 1024 * 1024, len(data) - pos)
                                    analysis_data = data[pos:pos + analysis_size]
                                    
                                    # 智能估算文件大小
                                    estimated_size = FileSignatureRecovery.estimate_file_size(
                                        analysis_data, info, file_offset
                                    )
                                    
                                    # 限制文件大小
                                    max_file_size = min(estimated_size, 10 * 1024 * 1024)
                                    file_data = data[pos:pos + max_file_size]
                                    
                                    # 跳过过小的文件
                                    if len(file_data) < 100:
                                        offset = pos + sig_len
                                        continue
                                    
                                    # 创建文件名
                                    align_suffix = "_aligned" if is_aligned else "_unaligned"
                                    
                                    # 使用filename_map如果提供
                                    base_name_from_map = None
                                    if filename_map and sig in filename_map:
                                        raw_name = filename_map[sig]
                                        base_name_from_map = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in raw_name).strip()
                                        if not base_name_from_map:
                                            base_name_from_map = f"Type_{sig.hex()[:8]}"
                                    
                                    if base_name_from_map:
                                        file_name_base = base_name_from_map
                                    else:
                                        file_name_base = info['type']
                                    
                                    file_name = f"{file_name_base}_{len(recovered_files) + 1}{align_suffix}{info['ext']}"
                                    file_path = os.path.join(type_dirs[info['type']], file_name)
                                    
                                    # 写入文件
                                    try:
                                        with open(file_path, 'wb') as output_file:
                                            output_file.write(file_data)
                                    except Exception as e:
                                        print(f"写入恢复文件错误: {e}")
                                        offset = pos + sig_len
                                        continue
                                    
                                    # 记录恢复的文件信息
                                    recovered_files.append({
                                        'name': file_name,
                                        'path': file_path,
                                        'offset': file_offset,
                                        'size': len(file_data),
                                        'estimated_size': estimated_size,
                                        'type': info['type'],
                                        'desc': info['desc'],
                                        'cluster_aligned': is_aligned,
                                        'cluster_offset': file_offset % cluster_size
                                    })
                                    
                                    print(f"发现文件: {file_name} (偏移: {file_offset}, 大小: {len(file_data)}, 簇对齐: {is_aligned})")
                                    
                                    # 移动偏移量，继续查找
                                    offset = pos + sig_len
                            
                            # 移动到下一个数据块
                            current_pos = current_pos + step if not reverse else current_pos + step
                except Exception as e:
                    print(f"Error recovering files: {e}")
                    traceback.print_exc()
        except Exception as e:
            print(f"Error recovering files: {e}")
            traceback.print_exc()
        
        # 创建恢复摘要文件
        summary_path = os.path.join(save_dir, "恢复摘要.txt")
        try:
            # 检查磁盘空间
            import shutil
            free_space = shutil.disk_usage(save_dir).free
            if free_space < 1024 * 1024:  # 少于1MB空间时警告
                print(f"警告: 目标目录剩余空间不足: {free_space / 1024 / 1024:.2f} MB")
            
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(f"文件签名恢复摘要\n")
                f.write(f"==============\n\n")
                f.write(f"恢复时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"恢复文件总数: {len(recovered_files)}\n")
                if total_files_found > 0:
                    f.write(f"簇对齐文件: {cluster_aligned_files}\n")
                    f.write(f"非簇对齐文件: {total_files_found - cluster_aligned_files}\n")
                    f.write(f"簇对齐率: {(cluster_aligned_files / total_files_found * 100):.2f}%\n\n")
                
                # 按类型统计
                type_counts = {}
                for file in recovered_files:
                    file_type = file['type']
                    if file_type not in type_counts:
                        type_counts[file_type] = 0
                    type_counts[file_type] += 1
                
                f.write(f"文件类型统计:\n")
                for file_type, count in type_counts.items():
                    f.write(f"- {file_type}: {count} 个文件\n")
                
                f.write(f"\n文件列表:\n")
                for i, file in enumerate(recovered_files):
                    f.write(f"{i+1}. {file['name']} (大小: {file['size']} 字节, 偏移: {file['offset']}, 描述: {file['description']}, 簇对齐: {'是' if file['cluster_aligned'] else '否'})\n")
        except OSError as e:
            if e.errno == 28:  # No space left on device
                print(f"错误: 磁盘空间不足，无法创建恢复摘要文件: {e}")
                # 尝试清理一些空间或提示用户
                raise Exception(f"磁盘空间不足，无法完成文件恢复操作。请清理磁盘空间后重试。")
            else:
                print(f"创建恢复摘要文件时发生错误: {e}")
                raise
        except Exception as e:
            print(f"创建恢复摘要文件时发生未知错误: {e}")
            raise
        
        # 按类型统计恢复的文件
        recovered_by_type = {}
        for file in recovered_files:
            file_type = file['type']
            if file_type not in recovered_by_type:
                recovered_by_type[file_type] = []
            recovered_by_type[file_type].append(file)
        
        return {
            'files': recovered_files,
            'by_type': recovered_by_type
        }