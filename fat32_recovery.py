import os
import struct
import time
from PyQt5.QtCore import QObject, pyqtSignal

# 导入磁盘镜像快照功能
try:
    from disk_image_snapshot import create_disk_image_snapshot
    DISK_IMAGE_AVAILABLE = True
except ImportError:
    DISK_IMAGE_AVAILABLE = False
    print("警告: 磁盘镜像快照功能不可用")

class FAT32Recovery(QObject):
    """FAT32文件系统恢复类"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
    
    def recover_files(self, disk_path, output_dir, use_disk_image=True):
        """恢复FAT32文件系统中的文件
        
        Args:
            disk_path: 磁盘路径
            output_dir: 输出目录
            use_disk_image: 是否使用磁盘镜像恢复（默认True）
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # 如果启用磁盘镜像恢复且功能可用
        if use_disk_image and DISK_IMAGE_AVAILABLE:
            return self._recover_with_disk_image(disk_path, output_dir)
        else:
            return self._recover_direct(disk_path, output_dir)
    
    def _recover_with_disk_image(self, disk_path, output_dir):
        """使用磁盘镜像进行FAT32恢复"""
        print(f"开始为设备 {disk_path} 创建磁盘镜像")
        self.status_updated.emit("正在创建磁盘镜像快照...")
        
        def progress_callback(current, total, message):
            if total > 0:
                percent = (current / total) * 100
                print(f"镜像创建进度: {percent:.1f}% - {message}")
                self.status_updated.emit(f"镜像创建进度: {percent:.1f}% - {message}")
            else:
                print(f"镜像创建状态: {message}")
                self.status_updated.emit(f"{message}")
        
        # 创建磁盘镜像快照，保存到恢复目录
        disk_name = disk_path.replace(':', '').replace('\\', '_').replace('.', '_')
        timestamp = int(time.time())
        image_filename = f'disk_image_{disk_name}_{timestamp}.img'
        image_output_path = os.path.join(output_dir, image_filename)
        
        print(f"调用create_disk_image_snapshot函数，参数: {disk_path}，输出路径: {image_output_path}")
        snapshot_result = create_disk_image_snapshot(disk_path, output_path=image_output_path, progress_callback=progress_callback)
        
        print(f"镜像创建结果: {snapshot_result}")
        
        if not snapshot_result or not snapshot_result['success']:
            error_msg = snapshot_result['error'] if snapshot_result else '未知错误'
            print(f"镜像创建失败: {error_msg}")
            self.status_updated.emit(f"创建磁盘镜像失败: {error_msg}")
            self.status_updated.emit("使用直接访问方法...")
            return self._recover_direct(disk_path, output_dir)
        
        image_path = snapshot_result['image_path']
        print(f"镜像创建成功: {image_path}，大小: {snapshot_result['size']} 字节")
        self.status_updated.emit(f"磁盘镜像创建成功: {image_path}")
        
        try:
            # 使用镜像文件进行恢复
            print(f"开始从镜像文件恢复: {image_path}")
            self.status_updated.emit("正在从磁盘镜像中恢复FAT32文件...")
            result = self._recover_direct(image_path, output_dir)
            print(f"从镜像恢复完成，恢复了 {len(result)} 个文件")
            
            # 在恢复摘要中添加镜像信息
            try:
                summary_path = os.path.join(output_dir, "FAT32恢复摘要.txt")
                with open(summary_path, 'a', encoding='utf-8') as f:
                    f.write(f"\n\n=== 磁盘镜像快照信息 ===\n")
                    f.write(f"原始磁盘路径: {disk_path}\n")
                    f.write(f"镜像文件路径: {image_path}\n")
                    f.write(f"镜像大小: {snapshot_result['size'] / (1024*1024*1024):.2f} GB\n")
                    f.write(f"创建时间: {snapshot_result['creation_time']}\n")
                    f.write(f"- 使用磁盘镜像快照技术进行安全恢复\n")
                    f.write(f"- 避免了对原始磁盘的直接访问\n")
                    f.write(f"- 镜像文件已保存到恢复目录，可用于后续分析\n")
                    f.write(f"- 镜像文件名: {os.path.basename(image_path)}\n")
            except Exception as e:
                self.status_updated.emit(f"添加镜像信息到摘要失败: {e}")
            
            return result
            
        finally:
            # 保留镜像文件，只清理临时资源
            try:
                if 'snapshot_object' in snapshot_result:
                    snapshot_result['snapshot_object'].cleanup(keep_image=True)
                    self.status_updated.emit("磁盘镜像已保存到恢复目录")
            except Exception as e:
                self.status_updated.emit(f"保存磁盘镜像时出错: {e}")
    
    def _recover_direct(self, disk_path, output_dir):
        """直接访问磁盘进行FAT32恢复"""
        try:
            # 检查和处理不同类型的磁盘路径
            device_path = self._prepare_device_path(disk_path)
            if not device_path:
                return []
                
            self.status_updated.emit(f"正在分析FAT32文件系统: {device_path}")
            
            with open(device_path, 'rb') as disk_file:
                # 获取磁盘大小信息
                try:
                    disk_file.seek(0, 2)  # 移动到文件末尾
                    disk_size = disk_file.tell()
                    self.status_updated.emit(f"磁盘大小: {disk_size} 字节 ({disk_size // (1024*1024)} MB)")
                    disk_file.seek(0)  # 回到开头
                except:
                    self.status_updated.emit("无法获取磁盘大小信息")
                
                # 查找FAT32引导扇区
                self.status_updated.emit("正在查找FAT32引导扇区...")
                boot_sector = self._find_fat32_boot_sector(disk_file)
                if not boot_sector:
                    raise Exception("未找到有效的FAT32引导扇区")
                
                self.status_updated.emit(f"找到FAT32引导扇区，偏移: {boot_sector['offset']}")
                
                # 解析FAT32参数
                fat32_info = self._parse_fat32_boot_sector(boot_sector)
                self.status_updated.emit(f"找到FAT32文件系统: {fat32_info['volume_label']}")
                
                # 恢复文件
                recovered_files = self._recover_fat32_files(disk_file, fat32_info, output_dir)
                
                self.status_updated.emit(f"FAT32恢复完成，共恢复 {len(recovered_files)} 个文件")
                return recovered_files
        
        except Exception as e:
            self.status_updated.emit(f"FAT32恢复过程中出错: {str(e)}")
            return []
    
    def _deep_scan_recovery(self, disk_file, fat32_info, failed_entries, output_dir):
        """深度扫描模式：结合目录项信息和文件签名扫描"""
        recovered_files = []
        
        try:
            # 导入文件签名恢复模块
            from file_signature_recovery import FileSignatureRecovery
            
            # 创建深度扫描目录
            deep_scan_dir = os.path.join(output_dir, "DEEP_SCAN")
            os.makedirs(deep_scan_dir, exist_ok=True)
            
            self.status_updated.emit("正在进行基于文件签名的深度扫描...")
            
            # 定义常见文件签名
            signatures = {
                b'\xFF\xD8\xFF': {'ext': '.jpg', 'type': '图片'},
                b'\x89PNG\r\n\x1A\n': {'ext': '.png', 'type': '图片'},
                b'GIF8': {'ext': '.gif', 'type': '图片'},
                b'BM': {'ext': '.bmp', 'type': '图片'},
                b'%PDF': {'ext': '.pdf', 'type': '文档'},
                b'PK\x03\x04': {'ext': '.zip', 'type': '压缩文件'},
                b'\xD0\xCF\x11\xE0': {'ext': '.doc', 'type': '文档'},
                b'ID3': {'ext': '.mp3', 'type': '音频'},
                b'MZ': {'ext': '.exe', 'type': '可执行文件'}
            }
            
            # 计算数据区域范围
            data_start = fat32_info['data_offset']
            cluster_size = fat32_info['cluster_size']
            
            # 为每个失败的文件尝试深度扫描
            for i, entry in enumerate(failed_entries):
                try:
                    self.progress_updated.emit(50 + int((i + 1) * 50 / len(failed_entries)))  # 后50%进度用于深度扫描
                    
                    file_info = entry.get('file_info')
                    original_filename = entry.get('filename')
                    
                    if not file_info or not original_filename:
                        continue
                    
                    self.status_updated.emit(f"深度扫描文件: {original_filename}")
                    
                    # 计算预期的文件位置范围
                    expected_cluster = file_info['start_cluster']
                    expected_size = file_info['file_size']
                    
                    if expected_cluster >= 2:
                        # 计算簇的磁盘位置
                        cluster_offset = data_start + (expected_cluster - 2) * cluster_size
                        
                        # 扩大搜索范围：在预期位置前后搜索
                        search_range = max(cluster_size * 10, expected_size * 2)  # 搜索10个簇或文件大小的2倍
                        search_start = max(data_start, cluster_offset - search_range)
                        search_end = cluster_offset + search_range
                        
                        # 在搜索范围内查找文件签名
                        found_file = self._scan_signature_in_range(
                            disk_file, search_start, search_end, 
                            signatures, original_filename, expected_size, deep_scan_dir
                        )
                        
                        if found_file:
                            recovered_files.append(found_file)
                            self.status_updated.emit(f"深度扫描成功恢复: {original_filename}")
                        else:
                            # 如果在预期位置没找到，尝试全盘扫描该文件类型
                            self.status_updated.emit(f"在预期位置未找到 {original_filename}，尝试全盘扫描...")
                            global_found = self._global_signature_scan(
                                disk_file, fat32_info, signatures, 
                                original_filename, expected_size, deep_scan_dir
                            )
                            if global_found:
                                recovered_files.append(global_found)
                                self.status_updated.emit(f"全盘扫描成功恢复: {original_filename}")
                            else:
                                self.status_updated.emit(f"深度扫描失败: {original_filename}")
                    
                except Exception as e:
                    self.status_updated.emit(f"深度扫描 {original_filename} 时出错: {str(e)}")
                    continue
            
            self.status_updated.emit(f"深度扫描完成，共恢复 {len(recovered_files)} 个文件")
            
        except ImportError:
            self.status_updated.emit("警告: 无法导入文件签名恢复模块，跳过深度扫描")
        except Exception as e:
            self.status_updated.emit(f"深度扫描过程中出错: {str(e)}")
        
        return recovered_files
    
    def _scan_signature_in_range(self, disk_file, start_offset, end_offset, signatures, filename, expected_size, output_dir):
        """在指定范围内扫描文件签名"""
        try:
            chunk_size = 64 * 1024  # 64KB块
            current_pos = start_offset
            
            while current_pos < end_offset:
                # 读取数据块
                disk_file.seek(current_pos)
                read_size = min(chunk_size, end_offset - current_pos)
                data = disk_file.read(read_size)
                
                if len(data) == 0:
                    break
                
                # 在数据块中查找签名
                for sig, info in signatures.items():
                    pos = data.find(sig)
                    if pos != -1:
                        file_offset = current_pos + pos
                        
                        # 尝试恢复文件
                        recovered_file = self._recover_file_by_signature(
                            disk_file, file_offset, info, filename, expected_size, output_dir
                        )
                        
                        if recovered_file:
                            return recovered_file
                
                current_pos += chunk_size
            
        except Exception as e:
            self.status_updated.emit(f"范围扫描出错: {str(e)}")
        
        return None
    
    def _global_signature_scan(self, disk_file, fat32_info, signatures, filename, expected_size, output_dir):
        """全盘扫描指定文件的签名"""
        try:
            # 限制全盘扫描的范围，只扫描数据区域
            data_start = fat32_info['data_offset']
            
            # 获取磁盘大小
            disk_file.seek(0, 2)
            disk_size = disk_file.tell()
            
            # 限制扫描范围，避免扫描时间过长
            scan_size = min(disk_size - data_start, 1024 * 1024 * 1024)  # 最多扫描1GB
            
            return self._scan_signature_in_range(
                disk_file, data_start, data_start + scan_size, 
                signatures, filename, expected_size, output_dir
            )
            
        except Exception as e:
            self.status_updated.emit(f"全盘扫描出错: {str(e)}")
        
        return None
    
    def _recover_file_by_signature(self, disk_file, file_offset, signature_info, filename, expected_size, output_dir):
        """根据文件签名恢复文件"""
        try:
            # 移动到文件位置
            disk_file.seek(file_offset)
            
            # 确定文件大小
            max_read_size = min(expected_size * 2, 10 * 1024 * 1024)  # 最多读取10MB
            file_data = disk_file.read(max_read_size)
            
            if len(file_data) < 100:  # 文件太小，跳过
                return None
            
            # 根据文件类型智能确定文件结束位置
            actual_size = self._estimate_file_size_by_signature(file_data, signature_info)
            if actual_size > 0:
                file_data = file_data[:actual_size]
            
            # 生成输出文件名
            base_name, ext = os.path.splitext(filename)
            if not ext:
                ext = signature_info['ext']
            
            output_filename = f"{base_name}_recovered_at_{file_offset:08X}{ext}"
            output_path = os.path.join(output_dir, output_filename)
            
            # 写入文件
            with open(output_path, 'wb') as f:
                f.write(file_data)
            
            return {
                'filename': output_filename,
                'path': output_path,
                'size': len(file_data),
                'offset': file_offset,
                'type': signature_info['type'],
                'recovery_method': 'signature_scan'
            }
            
        except Exception as e:
            self.status_updated.emit(f"签名恢复文件时出错: {str(e)}")
        
        return None
    
    def _estimate_file_size_by_signature(self, data, signature_info):
        """根据文件签名估算文件大小"""
        try:
            ext = signature_info['ext']
            
            # JPEG文件
            if ext in ['.jpg', '.jpeg']:
                end_marker = b'\xFF\xD9'
                end_pos = data.find(end_marker)
                if end_pos != -1:
                    return end_pos + 2
            
            # PNG文件
            elif ext == '.png':
                iend_marker = b'IEND\xAE\x42\x60\x82'
                end_pos = data.find(iend_marker)
                if end_pos != -1:
                    return end_pos + 8
            
            # GIF文件
            elif ext == '.gif':
                end_marker = b'\x00\x3B'
                end_pos = data.find(end_marker)
                if end_pos != -1:
                    return end_pos + 2
            
            # PDF文件
            elif ext == '.pdf':
                end_marker = b'%%EOF'
                end_pos = data.rfind(end_marker)
                if end_pos != -1:
                    return end_pos + 5
            
            # ZIP文件
            elif ext == '.zip':
                end_marker = b'PK\x05\x06'
                end_pos = data.rfind(end_marker)
                if end_pos != -1 and end_pos + 22 <= len(data):
                    return end_pos + 22
            
            # 默认返回数据长度
            return len(data)
            
        except Exception:
            return len(data)
        
        except PermissionError as e:
            # 权限不足，无法访问设备
            error_msg = f"权限不足，无法访问磁盘设备: {str(e)}"
            self.status_updated.emit(error_msg)
            print(f"错误: {error_msg}")
            return []
        except OSError as e:
            # 系统错误，如设备不存在或无法访问
            error_msg = f"系统错误，无法访问磁盘设备: {str(e)}"
            self.status_updated.emit(error_msg)
            print(f"错误: {error_msg}")
            return []
        except FileNotFoundError as e:
            # 磁盘路径不存在，直接返回空列表
            self.status_updated.emit(f"磁盘路径错误: {str(e)}")
            return []
        except Exception as e:
            self.status_updated.emit(f"FAT32恢复过程中出错: {str(e)}")
            print(f"FAT32恢复异常: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _prepare_device_path(self, disk_path):
        """准备设备路径，支持多种格式的逻辑驱动器路径"""
        # 标准化路径格式
        disk_path = disk_path.strip()
        
        # 检查是否为逻辑驱动器路径的各种格式
        logical_drive_patterns = [
            # F:\ 格式
            (len(disk_path) == 3 and disk_path[1:] == ':\\'),
            # F: 格式
            (len(disk_path) == 2 and disk_path[1] == ':'),
            # F 格式（单个字母）
            (len(disk_path) == 1 and disk_path.isalpha())
        ]
        
        is_logical_drive = any(logical_drive_patterns)
        
        if is_logical_drive:
            # 提取驱动器字母
            drive_letter = disk_path[0].upper()
            
            # 获取系统中的所有分区信息
            try:
                partitions = psutil.disk_partitions()
                available_drives = []
                target_partition = None
                
                for partition in partitions:
                    drive = partition.device[0].upper()
                    available_drives.append(drive)
                    if drive == drive_letter:
                        target_partition = partition
                        break
                
                if not target_partition:
                    error_msg = f"逻辑驱动器 {drive_letter}: 不存在或无法访问"
                    self.status_updated.emit(error_msg)
                    print(f"错误: {error_msg}")
                    self.status_updated.emit(f"可用驱动器: {', '.join(available_drives)}")
                    return None
                
                # 显示分区信息
                self.status_updated.emit(f"找到驱动器 {drive_letter}: - 文件系统: {target_partition.fstype}, 挂载点: {target_partition.mountpoint}")
                
                # 检查是否为FAT32文件系统
                if target_partition.fstype.upper() not in ['FAT32', 'FAT', 'VFAT']:
                    self.status_updated.emit(f"警告: 驱动器 {drive_letter}: 的文件系统为 {target_partition.fstype}，不是FAT32")
                    self.status_updated.emit("继续尝试恢复，但可能无法找到FAT32结构...")
                
            except Exception as e:
                self.status_updated.emit(f"获取分区信息时出错: {str(e)}")
                # 继续尝试访问
            
            # 检查驱动器是否可访问
            try:
                drive_path = f"{drive_letter}:\\"
                if not os.path.exists(drive_path):
                    error_msg = f"逻辑驱动器 {drive_letter}: 无法访问"
                    self.status_updated.emit(error_msg)
                    print(f"错误: {error_msg}")
                    return None
            except Exception as e:
                error_msg = f"检查逻辑驱动器 {drive_letter}: 时出错: {str(e)}"
                self.status_updated.emit(error_msg)
                print(f"错误: {error_msg}")
                return None
            
            # 构造设备路径
            device_path = f"\\\\.\\{drive_letter}:"
            self.status_updated.emit(f"逻辑驱动器 {drive_letter}: 映射到设备路径: {device_path}")
            
            # 检查设备路径是否可访问
            try:
                with open(device_path, 'rb') as test_file:
                    boot_data = test_file.read(512)  # 尝试读取引导扇区
                    if len(boot_data) == 512:
                        self.status_updated.emit(f"设备路径 {device_path} 访问正常，成功读取引导扇区")
                    else:
                        self.status_updated.emit(f"设备路径 {device_path} 访问正常，但引导扇区数据不完整")
                return device_path
            except PermissionError:
                error_msg = f"权限不足，无法访问设备 {device_path}。请以管理员身份运行程序。"
                self.status_updated.emit(error_msg)
                print(f"错误: {error_msg}")
                return None
            except Exception as e:
                error_msg = f"无法访问设备 {device_path}: {str(e)}"
                self.status_updated.emit(error_msg)
                print(f"错误: {error_msg}")
                return None
        
        else:
            # 物理磁盘路径或其他格式
            if not os.path.exists(disk_path):
                error_msg = f"磁盘路径不存在: {disk_path}"
                self.status_updated.emit(error_msg)
                print(f"错误: {error_msg}")
                return None
            
            self.status_updated.emit(f"使用物理磁盘路径: {disk_path}")
            return disk_path
    
    def _find_fat32_boot_sector(self, disk_file):
        """查找FAT32引导扇区"""
        # 首先尝试直接检查扇区0（适用于逻辑驱动器或未分区磁盘）
        self.status_updated.emit("正在检查引导扇区...")
        disk_file.seek(0)
        boot_sector = disk_file.read(512)
        if len(boot_sector) == 512 and self._is_fat32_boot_sector(boot_sector):
            self.status_updated.emit("在扇区0找到FAT32引导扇区")
            return {'data': boot_sector, 'offset': 0}
        
        # 如果扇区0不是FAT32引导扇区，尝试解析MBR分区表
        self.status_updated.emit("扇区0不是FAT32引导扇区，正在检查MBR分区表...")
        disk_file.seek(0)
        mbr = disk_file.read(512)
        
        if len(mbr) < 512:
            self.status_updated.emit("无法读取完整的MBR")
            return None
        
        # 检查MBR签名
        if mbr[510:512] != b'\x55\xaa':
            self.status_updated.emit("MBR签名无效")
            return None
        
        self.status_updated.emit("正在解析MBR分区表...")
        # 解析分区表
        for i in range(4):
            offset = 446 + i * 16
            partition_entry = mbr[offset:offset + 16]
            
            if len(partition_entry) < 16:
                continue
            
            partition_type = partition_entry[4]
            
            # 跳过空分区
            if partition_type == 0:
                continue
            
            # FAT32分区类型: 0x0B (FAT32), 0x0C (FAT32 LBA), 0x1B (Hidden FAT32), 0x1C (Hidden FAT32 LBA)
            # 也检查FAT16类型，因为有些大容量FAT16可能被误识别
            if partition_type in [0x0B, 0x0C, 0x1B, 0x1C, 0x06, 0x0E, 0x16, 0x1E]:
                start_lba = struct.unpack('<L', partition_entry[8:12])[0]
                sectors = struct.unpack('<L', partition_entry[12:16])[0]
                
                self.status_updated.emit(f"检查分区 {i+1}: 类型=0x{partition_type:02X}, 起始LBA={start_lba}, 扇区数={sectors}")
                
                # 读取分区引导扇区
                try:
                    disk_file.seek(start_lba * 512)
                    boot_sector = disk_file.read(512)
                    
                    if len(boot_sector) == 512 and self._is_fat32_boot_sector(boot_sector):
                        self.status_updated.emit(f"在分区 {i+1} 找到FAT32引导扇区")
                        return {'data': boot_sector, 'offset': start_lba * 512}
                except Exception as e:
                    self.status_updated.emit(f"读取分区 {i+1} 引导扇区失败: {str(e)}")
                    continue
        
        self.status_updated.emit("未找到有效的FAT32分区")
        return None
    
    def _is_fat32_boot_sector(self, boot_sector):
        """检查是否为FAT32引导扇区"""
        if len(boot_sector) < 512:
            return False
        
        # 检查引导签名
        if boot_sector[510:512] != b'\x55\xaa':
            return False
        
        try:
            # 检查基本参数
            bytes_per_sector = struct.unpack('<H', boot_sector[11:13])[0]
            sectors_per_cluster = boot_sector[13]
            reserved_sectors = struct.unpack('<H', boot_sector[14:16])[0]
            num_fats = boot_sector[16]
            
            # 基本参数有效性检查
            if not (bytes_per_sector in [512, 1024, 2048, 4096] and 
                    sectors_per_cluster in [1, 2, 4, 8, 16, 32, 64, 128] and
                    reserved_sectors > 0 and num_fats > 0):
                return False
            
            # 检查文件系统类型字符串
            fs_type = boot_sector[82:90].decode('ascii', errors='ignore').strip()
            if 'FAT32' in fs_type:
                self.status_updated.emit(f"通过文件系统标识确认FAT32: {fs_type}")
                return True
            
            # 检查FAT32特有字段
            sectors_per_fat_16 = struct.unpack('<H', boot_sector[22:24])[0]  # FAT16字段
            sectors_per_fat_32 = struct.unpack('<L', boot_sector[36:40])[0]  # FAT32字段
            root_cluster = struct.unpack('<L', boot_sector[44:48])[0]
            
            # FAT32的特征：FAT16字段为0，FAT32字段大于0
            if sectors_per_fat_16 == 0 and sectors_per_fat_32 > 0 and root_cluster >= 2:
                self.status_updated.emit(f"通过FAT32特征确认: sectors_per_fat_32={sectors_per_fat_32}, root_cluster={root_cluster}")
                return True
            
            # 额外检查：计算总簇数来判断是否为FAT32
            total_sectors_16 = struct.unpack('<H', boot_sector[19:21])[0]
            total_sectors_32 = struct.unpack('<L', boot_sector[32:36])[0]
            total_sectors = total_sectors_32 if total_sectors_32 != 0 else total_sectors_16
            
            if total_sectors > 0 and sectors_per_fat_32 > 0:
                # 计算数据区扇区数
                fat_sectors = num_fats * sectors_per_fat_32
                data_sectors = total_sectors - reserved_sectors - fat_sectors
                
                if data_sectors > 0:
                    # 计算簇数
                    cluster_count = data_sectors // sectors_per_cluster
                    
                    # FAT32的簇数应该 >= 65525
                    if cluster_count >= 65525:
                        self.status_updated.emit(f"通过簇数确认FAT32: cluster_count={cluster_count}")
                        return True
            
        except Exception as e:
            self.status_updated.emit(f"FAT32检查过程中出错: {str(e)}")
            return False
        
        return False
    
    def _parse_fat32_boot_sector(self, boot_sector_info):
        """解析FAT32引导扇区"""
        boot_sector = boot_sector_info['data']
        offset = boot_sector_info['offset']
        
        # 解析基本参数
        bytes_per_sector = struct.unpack('<H', boot_sector[11:13])[0]
        sectors_per_cluster = boot_sector[13]
        reserved_sectors = struct.unpack('<H', boot_sector[14:16])[0]
        num_fats = boot_sector[16]
        
        # FAT32特有字段
        sectors_per_fat = struct.unpack('<L', boot_sector[36:40])[0]
        root_cluster = struct.unpack('<L', boot_sector[44:48])[0]
        
        # 总扇区数：FAT32中可能在不同位置
        total_sectors_16 = struct.unpack('<H', boot_sector[19:21])[0]
        total_sectors_32 = struct.unpack('<L', boot_sector[32:36])[0]
        total_sectors = total_sectors_32 if total_sectors_32 != 0 else total_sectors_16
        
        # 卷标解析
        volume_label = boot_sector[71:82].decode('ascii', errors='ignore').strip()
        if not volume_label:
            # 尝试从根目录获取卷标
            volume_label = "FAT32_VOLUME"
        
        info = {
            'partition_offset': offset,
            'bytes_per_sector': bytes_per_sector,
            'sectors_per_cluster': sectors_per_cluster,
            'reserved_sectors': reserved_sectors,
            'num_fats': num_fats,
            'total_sectors': total_sectors,
            'sectors_per_fat': sectors_per_fat,
            'root_cluster': root_cluster,
            'volume_label': volume_label
        }
        
        # 计算关键位置
        info['fat1_offset'] = offset + info['reserved_sectors'] * info['bytes_per_sector']
        info['fat2_offset'] = info['fat1_offset'] + info['sectors_per_fat'] * info['bytes_per_sector']
        info['fat_offset'] = info['fat1_offset']  # 保持向后兼容
        info['data_offset'] = info['fat1_offset'] + info['num_fats'] * info['sectors_per_fat'] * info['bytes_per_sector']
        info['cluster_size'] = info['sectors_per_cluster'] * info['bytes_per_sector']
        
        # 添加详细的DBR信息用于调试
        info['fat_size_bytes'] = info['sectors_per_fat'] * info['bytes_per_sector']
        info['total_clusters'] = (info['total_sectors'] - info['reserved_sectors'] - info['num_fats'] * info['sectors_per_fat']) // info['sectors_per_cluster']
        
        # 验证参数合理性
        if info['bytes_per_sector'] == 0 or info['sectors_per_cluster'] == 0:
            raise Exception(f"无效的扇区参数: bytes_per_sector={info['bytes_per_sector']}, sectors_per_cluster={info['sectors_per_cluster']}")
        
        if info['sectors_per_fat'] == 0:
            raise Exception("无效的FAT表大小: sectors_per_fat=0")
        
        if info['root_cluster'] < 2:
            raise Exception(f"无效的根目录簇号: {info['root_cluster']}")
        
        # 验证计算结果的合理性
        if info['cluster_size'] <= 0 or info['cluster_size'] > 64 * 1024:  # 簇大小应在合理范围内
            raise Exception(f"无效的簇大小: {info['cluster_size']} 字节")
        
        if info['data_offset'] <= info['fat_offset']:
            raise Exception(f"数据区偏移计算错误: data_offset={info['data_offset']}, fat_offset={info['fat_offset']}")
        
        # 输出详细的DBR解析信息
        self.status_updated.emit(f"=== FAT32 DBR解析结果 ===")
        self.status_updated.emit(f"扇区大小: {info['bytes_per_sector']} 字节")
        self.status_updated.emit(f"每簇扇区数: {info['sectors_per_cluster']}")
        self.status_updated.emit(f"簇大小: {info['cluster_size']} 字节")
        self.status_updated.emit(f"保留扇区数: {info['reserved_sectors']}")
        self.status_updated.emit(f"FAT表数量: {info['num_fats']}")
        self.status_updated.emit(f"每个FAT表扇区数: {info['sectors_per_fat']}")
        self.status_updated.emit(f"每个FAT表大小: {info['fat_size_bytes']} 字节")
        self.status_updated.emit(f"根目录起始簇: {info['root_cluster']}")
        self.status_updated.emit(f"总扇区数: {info['total_sectors']}")
        self.status_updated.emit(f"总簇数: {info['total_clusters']}")
        self.status_updated.emit(f"FAT1偏移: {info['fat1_offset']}")
        self.status_updated.emit(f"FAT2偏移: {info['fat2_offset']}")
        self.status_updated.emit(f"数据区偏移: {info['data_offset']}")
        self.status_updated.emit(f"=========================")
        
        return info
    
    def _recover_fat32_files(self, disk_file, fat32_info, output_dir):
        """恢复FAT32文件"""
        recovered_files = []
        
        try:
            # 读取FAT1表（仅用于正常目录遍历）
            self.status_updated.emit("正在读取FAT1表...")
            fat1_table = self._read_fat_table(disk_file, fat32_info, fat_number=1)
            
            # 注意：已删除文件恢复不再依赖FAT表，直接使用FDT信息
            self.status_updated.emit("已删除文件恢复将直接使用FDT信息，无需读取FAT2表")
            
            # 从根目录开始恢复所有文件（包括已删除的）
            self.status_updated.emit("正在恢复根目录中的所有文件（包括已删除文件）...")
            root_files = self._recover_directory(
                disk_file, fat32_info, fat1_table, 
                fat32_info['root_cluster'], output_dir, ""
            )
            recovered_files.extend(root_files)
            
            # 恢复已删除的文件（直接使用FDT信息）
            self.status_updated.emit("正在恢复已删除的文件...")
            deleted_files = self._recover_deleted_files(
                disk_file, fat32_info, output_dir
            )
            recovered_files.extend(deleted_files)
            
            # 额外进行全盘FDT扫描，确保不遗漏任何文件
            self.status_updated.emit("开始全盘FDT扫描，查找遗漏的文件...")
            additional_files = self._scan_all_fdt_entries(disk_file, fat32_info, output_dir)
            recovered_files.extend(additional_files)
            
            self.status_updated.emit(f"全盘FDT扫描完成，额外发现 {len(additional_files)} 个文件")
            
        except Exception as e:
            self.status_updated.emit(f"恢复过程中出错: {str(e)}")
        
        return recovered_files
    
    def _scan_all_fdt_entries(self, disk_file, fat32_info, output_dir):
        """全盘扫描所有FDT条目，确保不遗漏任何文件"""
        recovered_files = []
        fdt_dir = os.path.join(output_dir, "FDT_SCAN")
        os.makedirs(fdt_dir, exist_ok=True)
        
        try:
            self.status_updated.emit("开始全盘FDT扫描...")
            
            # 计算数据区的起始位置和大小
            data_start = fat32_info['data_offset']
            cluster_size = fat32_info['cluster_size']
            total_clusters = fat32_info['total_clusters']
            
            scanned_clusters = 0
            found_files = 0
            
            # 扫描每个数据簇，查找可能的目录项
            for cluster_num in range(2, total_clusters + 2):  # 簇号从2开始
                try:
                    self.progress_updated.emit(int((cluster_num - 2) * 100 / total_clusters))
                    
                    # 计算簇的磁盘偏移
                    cluster_offset = data_start + (cluster_num - 2) * cluster_size
                    
                    # 读取簇数据
                    disk_file.seek(cluster_offset)
                    cluster_data = disk_file.read(cluster_size)
                    
                    if len(cluster_data) < cluster_size:
                        continue
                    
                    # 扫描簇中的目录项
                    cluster_files = self._scan_cluster_for_fdt_entries(
                        cluster_data, cluster_num, disk_file, fat32_info, fdt_dir
                    )
                    
                    if cluster_files:
                        recovered_files.extend(cluster_files)
                        found_files += len(cluster_files)
                        self.status_updated.emit(
                            f"簇 {cluster_num}: 发现 {len(cluster_files)} 个文件条目"
                        )
                    
                    scanned_clusters += 1
                    
                    # 每扫描1000个簇报告一次进度
                    if scanned_clusters % 1000 == 0:
                        self.status_updated.emit(
                            f"已扫描 {scanned_clusters} 个簇，发现 {found_files} 个文件"
                        )
                    
                except Exception as e:
                    # 继续扫描其他簇
                    continue
            
            self.status_updated.emit(
                f"全盘FDT扫描完成: 扫描了 {scanned_clusters} 个簇，发现 {found_files} 个文件"
            )
            
        except Exception as e:
            self.status_updated.emit(f"全盘FDT扫描出错: {str(e)}")
        
        return recovered_files
    
    def _scan_cluster_for_fdt_entries(self, cluster_data, cluster_num, disk_file, fat32_info, output_dir):
        """扫描单个簇中的FDT条目"""
        recovered_files = []
        
        try:
            # 检查簇数据是否可能包含目录项
            if not self._is_likely_directory_cluster(cluster_data):
                return recovered_files
            
            # 扫描32字节的目录项
            for i in range(0, len(cluster_data), 32):
                if i + 32 <= len(cluster_data):
                    dir_entry = cluster_data[i:i+32]
                    
                    # 跳过空项
                    if dir_entry[0] == 0x00:
                        break
                    
                    # 跳过长文件名项
                    if dir_entry[11] & 0x0F == 0x0F:
                        continue
                    
                    # 检查是否为有效的文件/目录项
                    if self._is_valid_directory_entry(dir_entry):
                        is_deleted = (dir_entry[0] == 0xE5)
                        
                        # 解析文件信息
                        file_info = self._parse_directory_entry(dir_entry)
                        
                        if is_deleted:
                            filename = self._restore_deleted_filename(dir_entry)
                            if filename:
                                filename = f"FDT_DELETED_{cluster_num}_{i//32:03d}_{filename}"
                        else:
                            filename = self._parse_filename(dir_entry)
                            if filename:
                                filename = f"FDT_NORMAL_{cluster_num}_{i//32:03d}_{filename}"
                        
                        if filename and file_info and not (file_info['attributes'] & 0x10):  # 只处理文件，不处理目录
                            # 过滤0KB文件
                            if file_info['file_size'] == 0:
                                continue
                            
                            if file_info['file_size'] > 0:  # 有文件大小的文件
                                try:
                                    # 使用强行恢复模式
                                    recovered_file = self._recover_deleted_file_force(
                                        disk_file, fat32_info,
                                        file_info, filename, output_dir, ""
                                    )
                                    
                                    if recovered_file:
                                        recovered_files.append(recovered_file)
                                        
                                except Exception as e:
                                    # 继续处理其他文件
                                    continue
        
        except Exception as e:
            # 继续处理其他簇
            pass
        
        return recovered_files
    
    def _is_likely_directory_cluster(self, cluster_data):
        """判断簇数据是否可能包含目录项"""
        # 简单启发式检查：查找可能的目录项模式
        valid_entries = 0
        
        for i in range(0, min(len(cluster_data), 512), 32):  # 只检查前16个条目
            if i + 32 <= len(cluster_data):
                dir_entry = cluster_data[i:i+32]
                
                # 空项
                if dir_entry[0] == 0x00:
                    break
                
                # 检查是否为可能的目录项
                if (dir_entry[0] != 0xE5 and dir_entry[0] >= 0x20) or dir_entry[0] == 0xE5:
                    # 检查属性字节是否合理
                    attr = dir_entry[11]
                    if attr & 0x0F == 0x0F:  # 长文件名项
                        valid_entries += 1
                    elif attr & 0xC0 == 0:  # 正常属性
                        valid_entries += 1
        
        return valid_entries >= 2  # 至少有2个看起来像目录项的条目
    
    def _is_valid_directory_entry(self, dir_entry):
        """检查是否为有效的目录项"""
        # 检查第一个字节
        first_byte = dir_entry[0]
        if first_byte == 0x00:  # 空项
            return False
        
        # 检查属性字节
        attr = dir_entry[11]
        if attr & 0x0F == 0x0F:  # 长文件名项，跳过
            return False
        
        # 检查保留字节
        if dir_entry[12] != 0:  # 保留字节应该为0
            return False
        
        # 检查文件大小和簇号的合理性
        file_size = struct.unpack('<I', dir_entry[28:32])[0]
        cluster_low = struct.unpack('<H', dir_entry[26:28])[0]
        cluster_high = struct.unpack('<H', dir_entry[20:22])[0]
        start_cluster = (cluster_high << 16) | cluster_low
        
        # 基本合理性检查
        if file_size > 0 and start_cluster == 0:  # 有大小但无簇号（可能是已删除文件）
            return True
        
        if file_size == 0 and (attr & 0x10):  # 目录
            return True
        
        if file_size > 0 and start_cluster >= 2:  # 正常文件
            return True
        
        return False
    
    def _read_fat_table(self, disk_file, fat32_info, fat_number=1):
        """读取指定的FAT表"""
        try:
            # 计算指定FAT表的偏移位置
            fat1_offset = fat32_info['partition_offset'] + fat32_info['reserved_sectors'] * fat32_info['bytes_per_sector']
            fat_size = fat32_info['sectors_per_fat'] * fat32_info['bytes_per_sector']
            
            if fat_number == 1:
                fat_offset = fat1_offset
            elif fat_number == 2:
                fat_offset = fat1_offset + fat_size
            else:
                raise Exception(f"无效的FAT表编号: {fat_number}，只支持1或2")
            
            self.status_updated.emit(f"读取FAT{fat_number}表，偏移: {fat_offset}, 大小: {fat_size} 字节")
            
            disk_file.seek(fat_offset)
            fat_data = disk_file.read(fat_size)
            
            if len(fat_data) < fat_size:
                self.status_updated.emit(f"警告: FAT{fat_number}表数据不完整，期望 {fat_size} 字节，实际读取 {len(fat_data)} 字节")
            
            # 解析FAT表项（每个4字节）
            fat_table = []
            for i in range(0, len(fat_data), 4):
                if i + 4 <= len(fat_data):
                    entry = struct.unpack('<L', fat_data[i:i+4])[0] & 0x0FFFFFFF
                    fat_table.append(entry)
                else:
                    # 不完整的表项，填充为结束标记
                    fat_table.append(0x0FFFFFFF)
            
            # 验证FAT表的基本有效性
            if len(fat_table) < 2:
                raise Exception(f"FAT{fat_number}表太小，无法包含有效数据")
            
            self.status_updated.emit(f"成功读取FAT{fat_number}表，包含 {len(fat_table)} 个表项")
            return fat_table
            
        except Exception as e:
            self.status_updated.emit(f"读取FAT{fat_number}表失败: {str(e)}")
            raise
    
    def _recover_deleted_files(self, disk_file, fat32_info, output_dir):
        """恢复已删除的文件"""
        recovered_files = []
        deleted_dir = os.path.join(output_dir, "DELETED_FILES")
        os.makedirs(deleted_dir, exist_ok=True)
        
        try:
            # 扫描根目录和所有子目录中的已删除文件
            self.status_updated.emit("正在扫描已删除的文件记录...")
            # 需要FAT1表来遍历目录结构
            fat1_table = self._read_fat_table(disk_file, fat32_info, fat_number=1)
            deleted_entries = self._scan_deleted_entries(disk_file, fat32_info, fat32_info['root_cluster'], fat1_table)
            
            self.status_updated.emit(f"发现 {len(deleted_entries)} 个已删除的文件记录")
            
            # 统计直接恢复失败的文件
            failed_recoveries = []
            
            # 恢复每个已删除的文件
            for i, entry in enumerate(deleted_entries):
                try:
                    self.progress_updated.emit(int((i + 1) * 50 / len(deleted_entries)))  # 前50%进度用于直接恢复
                    
                    # 使用已解析的文件信息
                    file_info = entry.get('file_info')
                    original_filename = entry.get('filename')
                    
                    if not file_info or not original_filename:
                        # 如果没有预解析的信息，则重新解析
                        original_filename = self._restore_deleted_filename(entry['dir_entry'])
                        if original_filename:
                            file_info = self._parse_directory_entry(entry['dir_entry'])
                    
                    if file_info and original_filename:
                        # 过滤0KB文件
                        if file_info['file_size'] == 0:
                            self.status_updated.emit(f"跳过0KB已删除文件: {original_filename}")
                            continue
                        
                        # 强行恢复所有已删除文件，不考虑高位簇清零的情况
                        if file_info['file_size'] > 0:
                            # 处理簇号为0或1的情况（shift+delete后可能被清零）
                            if file_info['start_cluster'] < 2:
                                self.status_updated.emit(
                                    f"检测到已删除文件簇号被清零: {original_filename}\n"
                                    f"  - 原始簇号: {file_info['start_cluster']}\n"
                                    f"  - 文件大小: {file_info['file_size']} 字节\n"
                                    f"  - 将尝试通过深度扫描恢复"
                                )
                                failed_recoveries.append(entry)
                            else:
                                self.status_updated.emit(
                                    f"开始强行恢复已删除文件: {original_filename}\n"
                                    f"  - 使用首簇号: {file_info['start_cluster']}\n"
                                    f"  - 文件大小: {file_info['file_size']} 字节\n"
                                    f"  - 强行恢复模式（忽略FAT表状态）"
                                )
                                # 强行使用FDT信息恢复文件（不依赖FAT表）
                                recovered_file = self._recover_deleted_file_force(
                                    disk_file, fat32_info, 
                                    file_info, original_filename, deleted_dir, entry['path']
                                )
                                
                                if recovered_file:
                                    recovered_files.append(recovered_file)
                                    self.status_updated.emit(f"强行恢复已删除文件成功: {original_filename}")
                                else:
                                    self.status_updated.emit(f"强行恢复失败: {original_filename}，将加入深度扫描队列")
                                    failed_recoveries.append(entry)
                        else:
                            self.status_updated.emit(f"跳过空文件: {original_filename} (大小:{file_info['file_size']})")
                            failed_recoveries.append(entry)
                        
                except Exception as e:
                    self.status_updated.emit(f"恢复已删除文件时出错: {str(e)}")
                    failed_recoveries.append(entry)
                    continue
            
            # 启用深度扫描模式恢复失败的文件
            if failed_recoveries:
                self.status_updated.emit(f"\n开始深度扫描模式，尝试恢复 {len(failed_recoveries)} 个失败的文件...")
                deep_scan_files = self._deep_scan_recovery(disk_file, fat32_info, failed_recoveries, deleted_dir)
                recovered_files.extend(deep_scan_files)
            
        except Exception as e:
            self.status_updated.emit(f"扫描已删除文件时出错: {str(e)}")
        
        return recovered_files
    
    def _scan_deleted_entries(self, disk_file, fat32_info, start_cluster, fat1_table, path="", visited_clusters=None):
        """扫描目录中的已删除文件记录项"""
        if visited_clusters is None:
            visited_clusters = set()
            
        deleted_entries = []
        
        if start_cluster < 2 or start_cluster in visited_clusters:
            return deleted_entries
            
        visited_clusters.add(start_cluster)
        
        # 读取目录簇链（使用FAT1表来遍历目录结构）
        cluster = start_cluster
        
        while cluster >= 2 and cluster < 0x0FFFFFF8:
            if cluster in visited_clusters:
                break
            visited_clusters.add(cluster)
            
            # 计算簇的磁盘位置
            cluster_offset = fat32_info['data_offset'] + (cluster - 2) * fat32_info['cluster_size']
            
            try:
                # 读取簇数据
                disk_file.seek(cluster_offset)
                cluster_data = disk_file.read(fat32_info['cluster_size'])
                
                if len(cluster_data) == 0:
                    break
                
                # 解析目录项
                for i in range(0, len(cluster_data), 32):
                    if i + 32 <= len(cluster_data):
                        dir_entry = cluster_data[i:i+32]
                        
                        # 检查是否为已删除的文件记录（第一个字节为0xE5）
                        if dir_entry[0] == 0xE5:
                            # 跳过长文件名项
                            if dir_entry[11] & 0x0F != 0x0F:
                                # 尝试恢复长文件名或使用短文件名
                                restored_filename = self._restore_deleted_filename_with_lfn(cluster_data, i)
                                if not restored_filename:
                                    # 如果长文件名恢复失败，使用传统方法
                                    restored_filename = self._restore_deleted_filename(dir_entry)
                                
                                if restored_filename:
                                    # 解析FDT中的关键字段
                                    file_info = self._parse_directory_entry(dir_entry)
                                    
                                    # 输出详细的FDT解析信息
                                    self.status_updated.emit(
                                        f"发现已删除文件: {restored_filename}\n"
                                        f"  - FDT偏移20-21字节(首簇高位): 0x{struct.unpack('<H', dir_entry[20:22])[0]:04X}\n"
                                        f"  - FDT偏移26-27字节(首簇低位): 0x{struct.unpack('<H', dir_entry[26:28])[0]:04X}\n"
                                        f"  - 组合首簇号: {file_info['start_cluster']}\n"
                                        f"  - FDT偏移28-31字节(文件大小): {file_info['file_size']} 字节\n"
                                        f"  - 文件属性: 0x{file_info['attributes']:02X}"
                                    )
                                    
                                    deleted_entries.append({
                                        'dir_entry': dir_entry,
                                        'path': path,
                                        'cluster_offset': cluster_offset + i,
                                        'file_info': file_info,
                                        'filename': restored_filename
                                    })
                        
                        # 检查是否为子目录（正常的，非删除的）
                        elif dir_entry[0] != 0x00 and dir_entry[11] & 0x0F != 0x0F:
                            if dir_entry[11] & 0x10:  # 目录属性
                                filename = self._parse_filename_with_lfn(cluster_data, i)
                                if filename and filename not in ['.', '..']:
                                    file_info = self._parse_directory_entry(dir_entry)
                                    if file_info['start_cluster'] >= 2:
                                        # 递归扫描子目录
                                        subdir_path = os.path.join(path, filename) if path else filename
                                        subdir_entries = self._scan_deleted_entries(
                                             disk_file, fat32_info, file_info['start_cluster'], 
                                             fat1_table, subdir_path, visited_clusters.copy()
                                         )
                                        deleted_entries.extend(subdir_entries)
                        
                        # 如果遇到空项，停止扫描当前簇
                        elif dir_entry[0] == 0x00:
                            break
                
            except Exception as e:
                self.status_updated.emit(f"读取目录簇 {cluster} 时出错: {str(e)}")
                break
            
            # 使用FAT1表移动到下一个簇
            if cluster < len(fat1_table):
                next_cluster = fat1_table[cluster]
                if next_cluster >= 2 and next_cluster < 0x0FFFFFF8 and next_cluster != cluster:
                    cluster = next_cluster
                else:
                    break
            else:
                break
        
        return deleted_entries
    
    def _restore_deleted_filename(self, dir_entry):
        """恢复已删除文件的文件名"""
        # 创建一个副本来修改
        restored_entry = bytearray(dir_entry)
        
        # 尝试恢复第一个字符
        # 通常第一个字符可能是常见的字母，我们尝试一些可能的值
        possible_first_chars = [ord(c) for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_']
        
        # 简单策略：使用'_'作为默认的第一个字符
        restored_entry[0] = ord('_')
        
        # 解析恢复后的文件名
        filename = self._parse_filename(bytes(restored_entry))
        
        if not filename:
            # 如果解析失败，生成一个默认文件名
            filename = f"DELETED_FILE_{hash(str(dir_entry)) & 0xFFFF:04X}"
        
        return filename
    
    def _restore_deleted_filename_with_lfn(self, cluster_data, entry_offset):
        """恢复已删除文件的长文件名"""
        # 检查当前项是否为已删除的短文件名项
        if entry_offset + 32 > len(cluster_data):
            return None
        
        sfn_entry = cluster_data[entry_offset:entry_offset+32]
        if sfn_entry[0] != 0xE5 or sfn_entry[11] & 0x0F == 0x0F:
            return None
        
        # 创建恢复后的短文件名项用于校验和计算
        restored_sfn = bytearray(sfn_entry)
        restored_sfn[0] = ord('_')  # 临时恢复第一个字符
        sfn_checksum = self._calculate_sfn_checksum(bytes(restored_sfn))
        
        # 向前查找可能的长文件名项
        lfn_entries = []
        current_offset = entry_offset
        
        while current_offset >= 32:
            current_offset -= 32
            if current_offset + 32 <= len(cluster_data):
                prev_entry = cluster_data[current_offset:current_offset+32]
                
                # 检查是否为已删除的长文件名项
                if prev_entry[0] == 0xE5 and prev_entry[11] & 0x0F == 0x0F:
                    # 尝试恢复长文件名项
                    restored_lfn = bytearray(prev_entry)
                    
                    # 尝试不同的序号来恢复第一个字节
                    for seq in range(1, 21):  # 最多支持20个LFN项
                        restored_lfn[0] = seq | 0x40 if len(lfn_entries) == 0 else seq
                        
                        lfn_info = self._parse_long_filename_entry(bytes(restored_lfn))
                        if lfn_info and lfn_info['checksum'] == sfn_checksum:
                            lfn_entries.insert(0, lfn_info)
                            
                            # 如果是最后一个LFN项，停止搜索
                            if lfn_info['is_last']:
                                break
                            break
                    else:
                        # 如果没有找到匹配的序号，停止搜索
                        break
                else:
                    # 遇到非LFN项，停止搜索
                    break
            else:
                break
        
        # 验证并组合长文件名
        if lfn_entries:
            # 检查序号连续性
            valid_lfn = True
            expected_seq = len(lfn_entries)
            for i, lfn in enumerate(lfn_entries):
                if lfn['sequence'] != expected_seq - i:
                    valid_lfn = False
                    break
            
            if valid_lfn:
                long_filename = ''.join([lfn['chars'] for lfn in lfn_entries])
                long_filename = long_filename.rstrip('\x00')
                
                if long_filename:
                    # 过滤非法字符
                    safe_filename = ""
                    for char in long_filename:
                        if char not in '<>:"/\\|?*' and ord(char) >= 32:
                            safe_filename += char
                        else:
                            safe_filename += f"_{ord(char):04X}_"
                    
                    return safe_filename if safe_filename else None
        
        return None
    
    def _recover_deleted_file_force(self, disk_file, fat32_info, file_info, filename, output_dir, path):
        """强行恢复已删除的文件（忽略FAT表状态，适用于shift+delete）"""
        try:
            # 创建输出路径
            if path:
                file_output_dir = os.path.join(output_dir, path)
                os.makedirs(file_output_dir, exist_ok=True)
            else:
                file_output_dir = output_dir
            
            filepath = os.path.join(file_output_dir, f"FORCE_{filename}")
            
            with open(filepath, 'wb') as output_file:
                start_cluster = file_info['start_cluster']
                file_size = file_info['file_size']
                remaining_size = file_size
                
                self.status_updated.emit(
                    f"强行恢复文件: {filename}\n"
                    f"  - 首簇号: {start_cluster}\n"
                    f"  - 文件大小: {file_size} 字节\n"
                    f"  - 强行按连续簇方式读取数据（忽略FAT表）"
                )
                
                current_cluster = start_cluster
                clusters_read = 0
                
                while remaining_size > 0:
                    # 计算当前簇的磁盘偏移
                    cluster_offset = fat32_info['data_offset'] + (current_cluster - 2) * fat32_info['cluster_size']
                    
                    try:
                        # 读取簇数据
                        disk_file.seek(cluster_offset)
                        read_size = min(fat32_info['cluster_size'], remaining_size)
                        cluster_data = disk_file.read(read_size)
                        
                        if len(cluster_data) == 0:
                            self.status_updated.emit(f"警告: 文件 {filename} 簇 {current_cluster} 无法读取数据")
                            break
                        
                        # 写入文件
                        output_file.write(cluster_data)
                        remaining_size -= len(cluster_data)
                        clusters_read += 1
                        
                        self.status_updated.emit(
                            f"  强行读取簇 {current_cluster}: {len(cluster_data)} 字节 "
                            f"(剩余 {remaining_size} 字节)"
                        )
                        
                        # 如果文件已完整恢复，停止读取
                        if remaining_size <= 0:
                            break
                        
                        # 强行移动到下一个连续簇（不检查FAT表）
                        current_cluster += 1
                        
                        # 安全检查：避免读取过多簇
                        if clusters_read > 2000:  # 强行恢复模式允许更多簇
                            self.status_updated.emit(f"警告: 文件 {filename} 已读取过多簇，停止恢复")
                            break
                            
                    except Exception as e:
                        self.status_updated.emit(f"强行读取簇 {current_cluster} 时出错: {str(e)}")
                        # 强行恢复模式：即使出错也尝试下一个簇
                        current_cluster += 1
                        clusters_read += 1
                        if clusters_read > 100:  # 连续错误过多时停止
                            break
                        continue
                
                self.status_updated.emit(
                    f"文件 {filename} 强行恢复完成: 共读取 {clusters_read} 个簇，"
                    f"恢复 {file_size - remaining_size} / {file_size} 字节"
                )
                
                return {
                    'filename': filename,
                    'filepath': filepath,
                    'size': file_size - remaining_size,
                    'clusters': clusters_read,
                    'method': 'force_recovery'
                }
                
        except Exception as e:
            self.status_updated.emit(f"强行恢复文件 {filename} 时出错: {str(e)}")
            return None
    
    def _recover_deleted_file_direct(self, disk_file, fat32_info, file_info, filename, output_dir, path):
        """直接使用FDT信息恢复已删除的文件（不依赖FAT表）"""
        try:
            # 创建输出路径
            if path:
                file_output_dir = os.path.join(output_dir, path)
                os.makedirs(file_output_dir, exist_ok=True)
            else:
                file_output_dir = output_dir
            
            filepath = os.path.join(file_output_dir, f"DIRECT_{filename}")
            
            with open(filepath, 'wb') as output_file:
                start_cluster = file_info['start_cluster']
                file_size = file_info['file_size']
                remaining_size = file_size
                
                self.status_updated.emit(
                    f"直接恢复文件: {filename}\n"
                    f"  - 首簇号: {start_cluster}\n"
                    f"  - 文件大小: {file_size} 字节\n"
                    f"  - 按连续簇方式读取数据"
                )
                
                # 注意：已删除文件的起始簇可能被清零，这里不做严格检查
                if start_cluster < 2:
                    self.status_updated.emit(f"警告: 起始簇号异常 {start_cluster}，但仍尝试恢复")
                    # 对于簇号为0或1的情况，尝试从簇2开始
                    start_cluster = 2
                
                current_cluster = start_cluster
                clusters_read = 0
                
                while remaining_size > 0:
                    # 计算当前簇的磁盘偏移
                    cluster_offset = fat32_info['data_offset'] + (current_cluster - 2) * fat32_info['cluster_size']
                    
                    try:
                        # 读取簇数据
                        disk_file.seek(cluster_offset)
                        read_size = min(fat32_info['cluster_size'], remaining_size)
                        cluster_data = disk_file.read(read_size)
                        
                        if len(cluster_data) == 0:
                            self.status_updated.emit(f"警告: 文件 {filename} 簇 {current_cluster} 无法读取数据")
                            break
                        
                        # 写入文件
                        output_file.write(cluster_data)
                        remaining_size -= len(cluster_data)
                        clusters_read += 1
                        
                        self.status_updated.emit(
                            f"  已读取簇 {current_cluster}: {len(cluster_data)} 字节 "
                            f"(剩余 {remaining_size} 字节)"
                        )
                        
                        # 如果文件已完整恢复，停止读取
                        if remaining_size <= 0:
                            break
                        
                        # 移动到下一个连续簇
                        current_cluster += 1
                        
                        # 安全检查：避免读取过多簇
                        if clusters_read > 1000:  # 限制最多读取1000个簇
                            self.status_updated.emit(f"警告: 文件 {filename} 已读取过多簇，停止恢复")
                            break
                            
                    except Exception as e:
                        self.status_updated.emit(f"读取簇 {current_cluster} 时出错: {str(e)}")
                        break
                
                self.status_updated.emit(
                    f"文件 {filename} 恢复完成: 共读取 {clusters_read} 个簇，"
                    f"恢复 {file_size - remaining_size} / {file_size} 字节"
                )
                
                return {
                    'filename': filename,
                    'filepath': filepath,
                    'size': file_size - remaining_size,
                    'clusters_used': clusters_read
                }
                
        except Exception as e:
            self.status_updated.emit(f"恢复文件 {filename} 失败: {str(e)}")
            return None
    
    def _recover_directory(self, disk_file, fat32_info, fat_table, start_cluster, output_dir, path):
        """恢复目录中的文件"""
        recovered_files = []
        
        if start_cluster < 2 or start_cluster >= len(fat_table):
            return recovered_files
        
        # 创建目录
        dir_path = os.path.join(output_dir, path) if path else output_dir
        os.makedirs(dir_path, exist_ok=True)
        
        # 读取目录簇链
        cluster = start_cluster
        visited_clusters = set()  # 防止循环引用
        
        while cluster >= 2 and cluster < 0x0FFFFFF8 and cluster < len(fat_table):
            # 检查是否已访问过此簇（防止循环）
            if cluster in visited_clusters:
                self.status_updated.emit(f"警告: 目录簇链循环，停止处理簇 {cluster}")
                break
            visited_clusters.add(cluster)
            
            # 计算簇的磁盘位置
            cluster_offset = fat32_info['data_offset'] + (cluster - 2) * fat32_info['cluster_size']
            
            try:
                # 读取簇数据
                disk_file.seek(cluster_offset)
                cluster_data = disk_file.read(fat32_info['cluster_size'])
                
                if len(cluster_data) == 0:
                    self.status_updated.emit(f"警告: 目录簇 {cluster} 无法读取数据")
                    break
                
                if len(cluster_data) < fat32_info['cluster_size']:
                    self.status_updated.emit(f"警告: 目录簇 {cluster} 数据不完整，期望 {fat32_info['cluster_size']} 字节，实际 {len(cluster_data)} 字节")
            except Exception as e:
                self.status_updated.emit(f"读取目录簇 {cluster} 失败: {str(e)}")
                break
            
            # 解析目录项
            for i in range(0, len(cluster_data), 32):
                if i + 32 <= len(cluster_data):
                    dir_entry = cluster_data[i:i+32]
                    
                    # 处理空项
                    if dir_entry[0] == 0x00:  # 空项，停止扫描当前簇
                        break
                    
                    # 处理长文件名项
                    if dir_entry[11] & 0x0F == 0x0F:  # 长文件名项，跳过但不处理
                        continue
                    
                    # 处理已删除项和正常项
                    is_deleted = (dir_entry[0] == 0xE5)
                    
                    if is_deleted:
                        # 尝试恢复已删除文件的文件名
                        filename = self._restore_deleted_filename(dir_entry)
                        if filename:
                            filename = f"DELETED_{filename}"
                    else:
                        # 解析正常文件信息（支持长文件名）
                        filename = self._parse_filename_with_lfn(cluster_data, i)
                    
                    if filename and filename not in ['.', '..']:
                        file_info = self._parse_directory_entry(dir_entry)
                        
                        # 调试信息
                        file_type = "目录" if file_info['attributes'] & 0x10 else "文件"
                        status_prefix = "已删除" if is_deleted else "正常"
                        self.status_updated.emit(f"发现{status_prefix}{file_type}: {filename} (簇:{file_info['start_cluster']}, 大小:{file_info['file_size']})")
                        
                        if file_info['attributes'] & 0x10:  # 目录
                            if file_info['start_cluster'] >= 2:  # 有效簇号
                                subdir_files = self._recover_directory(
                                    disk_file, fat32_info, fat_table,
                                    file_info['start_cluster'],
                                    output_dir, os.path.join(path, filename)
                                )
                                recovered_files.extend(subdir_files)
                            else:
                                self.status_updated.emit(f"目录簇号异常: {filename} (簇:{file_info['start_cluster']})，尝试深度扫描")
                        else:  # 文件
                            # 过滤0KB文件
                            if file_info['file_size'] == 0:
                                self.status_updated.emit(f"跳过0KB文件: {filename}")
                                continue
                            
                            # 强制恢复所有文件，包括已删除和簇号异常的文件
                            try:
                                if is_deleted or file_info['start_cluster'] < 2:
                                    # 使用强行恢复模式
                                    recovered_file = self._recover_deleted_file_force(
                                        disk_file, fat32_info,
                                        file_info, filename, dir_path, ""
                                    )
                                else:
                                    # 使用正常恢复模式
                                    recovered_file = self._recover_file(
                                        disk_file, fat32_info, fat_table,
                                        file_info, filename, dir_path
                                    )
                                
                                if recovered_file:
                                    recovered_files.append(recovered_file)
                                else:
                                    self.status_updated.emit(f"文件恢复失败: {filename}")
                            except Exception as e:
                                self.status_updated.emit(f"恢复文件 {filename} 失败: {str(e)}")
                                # 继续处理其他文件，不中断整个恢复过程
                    elif filename:
                        # 跳过的特殊目录项
                        pass
            
            # 移动到下一个簇
            next_cluster = fat_table[cluster]
            
            # 检查下一个簇的有效性
            if next_cluster == cluster:  # 自引用
                self.status_updated.emit(f"警告: 目录簇 {cluster} 自引用，停止处理")
                break
            
            cluster = next_cluster
        
        return recovered_files
    
    def _parse_filename(self, dir_entry):
        """解析文件名（仅8.3格式）"""
        # 检查是否为有效的目录项
        if dir_entry[0] == 0x00 or dir_entry[0] == 0xE5:
            return None
        
        # 解析8.3格式文件名
        name_bytes = dir_entry[0:8]
        ext_bytes = dir_entry[8:11]
        
        # 处理文件名
        name = ""
        for b in name_bytes:
            if b == 0x20:  # 空格填充
                break
            if b == 0x05:  # 特殊字符0xE5的替代
                name += chr(0xE5)
            elif 32 <= b <= 126:  # 可打印ASCII字符
                # 过滤Windows文件名中的非法字符
                if chr(b) not in '<>:"/\\|?*':
                    name += chr(b)
                else:
                    name += f"_{b:02X}_"
            else:
                name += f"_{b:02X}_"  # 非ASCII字符用十六进制表示
        
        # 处理扩展名
        ext = ""
        for b in ext_bytes:
            if b == 0x20:  # 空格填充
                break
            if 32 <= b <= 126:  # 可打印ASCII字符
                # 过滤Windows文件名中的非法字符
                if chr(b) not in '<>:"/\\|?*':
                    ext += chr(b)
                else:
                    ext += f"_{b:02X}_"
            else:
                ext += f"_{b:02X}_"  # 非ASCII字符用十六进制表示
        
        if not name:
            return None
        
        # 组合文件名
        if ext:
            filename = f"{name}.{ext}"
        else:
            filename = name
        
        # 确保文件名不为空且不是保留名称
        if filename and filename.upper() not in ['CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9']:
            return filename
        else:
            return f"FILE_{hash(str(dir_entry)) & 0xFFFF:04X}"  # 生成备用文件名
    
    def _parse_long_filename_entry(self, dir_entry):
        """解析长文件名目录项"""
        # 检查是否为长文件名项
        if dir_entry[11] & 0x0F != 0x0F:
            return None
        
        # 获取序号和标志
        sequence = dir_entry[0] & 0x3F  # 去掉最高位的结束标志
        is_last = (dir_entry[0] & 0x40) != 0  # 检查是否为最后一个LFN项
        
        # 提取Unicode字符（每个LFN项包含13个Unicode字符）
        chars = []
        
        # 字符1-5 (偏移1-10)
        for i in range(1, 11, 2):
            char_code = struct.unpack('<H', dir_entry[i:i+2])[0]
            if char_code == 0x0000 or char_code == 0xFFFF:
                break
            chars.append(chr(char_code))
        
        # 字符6-11 (偏移14-25)
        for i in range(14, 26, 2):
            char_code = struct.unpack('<H', dir_entry[i:i+2])[0]
            if char_code == 0x0000 or char_code == 0xFFFF:
                break
            chars.append(chr(char_code))
        
        # 字符12-13 (偏移28-31)
        for i in range(28, 32, 2):
            char_code = struct.unpack('<H', dir_entry[i:i+2])[0]
            if char_code == 0x0000 or char_code == 0xFFFF:
                break
            chars.append(chr(char_code))
        
        return {
            'sequence': sequence,
            'is_last': is_last,
            'chars': ''.join(chars),
            'checksum': dir_entry[13]
        }
    
    def _calculate_sfn_checksum(self, dir_entry):
        """计算短文件名的校验和"""
        checksum = 0
        for i in range(11):  # 8.3文件名共11字节
            checksum = ((checksum & 1) << 7) + (checksum >> 1) + dir_entry[i]
            checksum &= 0xFF
        return checksum
    
    def _parse_filename_with_lfn(self, cluster_data, entry_offset):
        """解析文件名（支持长文件名）"""
        # 从当前位置向前查找长文件名项
        lfn_entries = []
        current_offset = entry_offset
        
        # 向前扫描长文件名项
        while current_offset >= 32:
            current_offset -= 32
            if current_offset + 32 <= len(cluster_data):
                prev_entry = cluster_data[current_offset:current_offset+32]
                
                # 检查是否为长文件名项
                if prev_entry[11] & 0x0F == 0x0F:
                    lfn_info = self._parse_long_filename_entry(prev_entry)
                    if lfn_info:
                        lfn_entries.insert(0, lfn_info)  # 插入到开头，保持顺序
                        
                        # 如果是最后一个LFN项，停止搜索
                        if lfn_info['is_last']:
                            break
                else:
                    # 遇到非LFN项，停止搜索
                    break
            else:
                break
        
        # 获取短文件名项
        if entry_offset + 32 <= len(cluster_data):
            sfn_entry = cluster_data[entry_offset:entry_offset+32]
            sfn_checksum = self._calculate_sfn_checksum(sfn_entry)
            
            # 验证长文件名的完整性
            if lfn_entries:
                # 检查校验和
                valid_lfn = True
                for lfn in lfn_entries:
                    if lfn['checksum'] != sfn_checksum:
                        valid_lfn = False
                        break
                
                # 检查序号连续性
                if valid_lfn:
                    expected_seq = len(lfn_entries)
                    for i, lfn in enumerate(lfn_entries):
                        if lfn['sequence'] != expected_seq - i:
                            valid_lfn = False
                            break
                
                # 如果长文件名有效，组合长文件名
                if valid_lfn:
                    long_filename = ''.join([lfn['chars'] for lfn in lfn_entries])
                    # 移除尾部的空字符
                    long_filename = long_filename.rstrip('\x00')
                    
                    if long_filename:
                        # 过滤非法字符
                        safe_filename = ""
                        for char in long_filename:
                            if char not in '<>:"/\\|?*' and ord(char) >= 32:
                                safe_filename += char
                            else:
                                safe_filename += f"_{ord(char):04X}_"
                        
                        return safe_filename if safe_filename else None
            
            # 如果没有有效的长文件名，使用短文件名
            return self._parse_filename(sfn_entry)
        
        return None
    
    def _parse_directory_entry(self, dir_entry):
        """解析目录项"""
        # 解析首簇号（组合高16位和低16位）
        cluster_low = struct.unpack('<H', dir_entry[26:28])[0]  # 偏移26-27：低16位
        cluster_high = struct.unpack('<H', dir_entry[20:22])[0]  # 偏移20-21：高16位
        start_cluster = cluster_low | (cluster_high << 16)
        
        # 解析文件大小（偏移28-31，4字节小端序）
        file_size = struct.unpack('<L', dir_entry[28:32])[0]
        
        # 调试信息：打印FDT解析结果
        print(f"[FAT32调试] FDT解析 - 低位簇号: {cluster_low}, 高位簇号: {cluster_high}, 起始簇: {start_cluster}, 文件大小: {file_size} 字节")
        
        return {
            'attributes': dir_entry[11],
            'start_cluster': start_cluster,
            'file_size': file_size
        }
    
    def _recover_file(self, disk_file, fat32_info, fat_table, file_info, filename, output_dir):
        """恢复单个文件"""
        try:
            filepath = os.path.join(output_dir, filename)
            
            with open(filepath, 'wb') as output_file:
                cluster = file_info['start_cluster']
                remaining_size = file_info['file_size']
                visited_clusters = set()  # 防止循环引用
                
                # 调试信息：打印文件恢复开始信息
                print(f"[FAT32调试] 开始恢复文件: {filename}")
                print(f"[FAT32调试] 起始簇号: {cluster}, 文件大小: {file_info['file_size']} 字节")
                
                # 检查起始簇的有效性
                if cluster < 2 or cluster >= len(fat_table):
                    raise Exception(f"无效的起始簇: {cluster}")
                
                cluster_count = 0  # 簇计数器
                while remaining_size > 0 and cluster >= 2 and cluster < 0x0FFFFFF8 and cluster < len(fat_table):
                    # 检查循环引用
                    if cluster in visited_clusters:
                        self.status_updated.emit(f"警告: 文件 {filename} 簇链存在循环，停止恢复")
                        break
                    visited_clusters.add(cluster)
                    cluster_count += 1
                    
                    # 计算簇位置
                    cluster_offset = fat32_info['data_offset'] + (cluster - 2) * fat32_info['cluster_size']
                    
                    # 调试信息：打印当前簇信息
                    print(f"[FAT32调试] 第{cluster_count}个簇 - 簇号: {cluster}, 偏移: 0x{cluster_offset:08X}, 剩余大小: {remaining_size} 字节")
                    
                    try:
                        # 读取簇数据
                        disk_file.seek(cluster_offset)
                        read_size = min(fat32_info['cluster_size'], remaining_size)
                        cluster_data = disk_file.read(read_size)
                        
                        if len(cluster_data) == 0:
                            self.status_updated.emit(f"警告: 文件 {filename} 簇 {cluster} 无法读取数据")
                            break
                        
                        if len(cluster_data) < read_size:
                            self.status_updated.emit(f"警告: 文件 {filename} 簇 {cluster} 数据不完整，期望 {read_size} 字节，实际 {len(cluster_data)} 字节")
                        
                        # 写入文件
                        output_file.write(cluster_data)
                        remaining_size -= len(cluster_data)
                        
                        # 如果文件已完整恢复，停止读取
                        if remaining_size <= 0:
                            break
                        
                        # 移动到下一个簇
                        next_cluster = fat_table[cluster]
                        
                        # 调试信息：打印簇跳转信息
                        if next_cluster >= 0x0FFFFFF8:
                            print(f"[FAT32调试] 簇跳转 - 当前簇: {cluster} -> 结束标记: 0x{next_cluster:08X} (文件结束)")
                        else:
                            print(f"[FAT32调试] 簇跳转 - 当前簇: {cluster} -> 下一簇: {next_cluster}")
                        
                        # 检查下一个簇的有效性
                        if next_cluster == cluster:  # 自引用
                            self.status_updated.emit(f"警告: 文件 {filename} 簇 {cluster} 自引用，停止恢复")
                            break
                        
                        cluster = next_cluster
                        
                    except Exception as e:
                        self.status_updated.emit(f"读取文件 {filename} 簇 {cluster} 失败: {str(e)}")
                        break
            
            # 调试信息：打印文件恢复完成信息
            recovered_size = file_info['file_size'] - remaining_size
            print(f"[FAT32调试] 文件恢复完成: {filename}")
            print(f"[FAT32调试] 总共读取 {cluster_count} 个簇，恢复 {recovered_size} / {file_info['file_size']} 字节")
            
            self.status_updated.emit(f"恢复文件: {filename}")
            return filepath
        
        except Exception as e:
            self.status_updated.emit(f"恢复文件 {filename} 失败: {str(e)}")
            return None