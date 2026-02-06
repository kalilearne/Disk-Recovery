import os
import struct
from PyQt5.QtCore import QObject, pyqtSignal

class NTFSRecovery(QObject):
    """NTFS文件系统恢复类"""
    
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
    
    def recover_files(self, disk_path, output_dir, use_disk_image=True):
        """恢复NTFS文件系统中的文件"""
        os.makedirs(output_dir, exist_ok=True)
        
        try:
            # 检查磁盘路径是否存在
            # 对于逻辑驱动器路径（如 F:\），需要特殊处理
            if len(disk_path) == 3 and disk_path[1:] == ':\\':
                # 逻辑驱动器路径，检查驱动器是否存在
                if not os.path.exists(disk_path):
                    error_msg = f"逻辑驱动器不存在或无法访问: {disk_path}"
                    self.status_updated.emit(error_msg)
                    print(f"错误: {error_msg}")
                    return []
                # 对于逻辑驱动器，需要使用设备路径
                device_path = f"\\\\.\\{disk_path[0]}:"
            elif not os.path.exists(disk_path):
                error_msg = f"磁盘路径不存在: {disk_path}"
                self.status_updated.emit(error_msg)
                print(f"错误: {error_msg}")
                return []
            else:
                device_path = disk_path
                
            self.status_updated.emit("正在分析NTFS文件系统...")
            
            with open(device_path, 'rb') as disk_file:
                # 查找NTFS引导扇区
                boot_sector = self._find_ntfs_boot_sector(disk_file)
                if not boot_sector:
                    raise Exception("未找到有效的NTFS引导扇区")
                
                # 解析NTFS参数
                ntfs_info = self._parse_ntfs_boot_sector(boot_sector)
                self.status_updated.emit(f"找到NTFS文件系统: {ntfs_info['volume_label']}")
                
                # 恢复文件
                recovered_files = self._recover_ntfs_files(disk_file, ntfs_info, output_dir)
                
                self.status_updated.emit(f"NTFS恢复完成，共恢复 {len(recovered_files)} 个文件")
                return recovered_files
        
        except FileNotFoundError as e:
            # 磁盘路径不存在，直接返回空列表
            self.status_updated.emit(f"磁盘路径错误: {str(e)}")
            print(f"NTFS恢复路径错误: {e}")
            return []
        except PermissionError as e:
            # 权限不足，可能需要管理员权限
            error_msg = f"访问磁盘需要管理员权限: {str(e)}"
            self.status_updated.emit(error_msg)
            print(f"NTFS恢复权限错误: {error_msg}")
            return []
        except OSError as e:
            # 系统错误，如设备不可访问
            error_msg = f"磁盘访问错误: {str(e)}"
            self.status_updated.emit(error_msg)
            print(f"NTFS恢复系统错误: {error_msg}")
            return []
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.status_updated.emit(f"NTFS恢复失败: {str(e)}")
            print(f"NTFS恢复详细错误: {error_details}")
            # 不再重新抛出异常，而是返回空列表
            return []
    
    def _find_ntfs_boot_sector(self, disk_file):
        """查找NTFS引导扇区"""
        # 检查MBR
        disk_file.seek(0)
        mbr = disk_file.read(512)
        
        if len(mbr) < 512:
            return None
        
        # 检查MBR签名
        if mbr[510:512] != b'\x55\xaa':
            return None
        
        # 解析分区表
        for i in range(4):
            offset = 446 + i * 16
            partition_entry = mbr[offset:offset + 16]
            
            if len(partition_entry) < 16:
                continue
            
            partition_type = partition_entry[4]
            
            # NTFS分区类型: 0x07
            if partition_type == 0x07:
                start_lba = struct.unpack('<L', partition_entry[8:12])[0]
                
                # 读取分区引导扇区
                disk_file.seek(start_lba * 512)
                boot_sector = disk_file.read(512)
                
                if len(boot_sector) == 512 and self._is_ntfs_boot_sector(boot_sector):
                    return {'data': boot_sector, 'offset': start_lba * 512}
        
        # 如果没有找到分区，尝试直接检查扇区0
        disk_file.seek(0)
        boot_sector = disk_file.read(512)
        if len(boot_sector) == 512 and self._is_ntfs_boot_sector(boot_sector):
            return {'data': boot_sector, 'offset': 0}
        
        return None
    
    def _is_ntfs_boot_sector(self, boot_sector):
        """检查是否为NTFS引导扇区"""
        if len(boot_sector) < 512:
            return False
        
        # 检查引导签名
        if boot_sector[510:512] != b'\x55\xaa':
            return False
        
        # 检查NTFS文件系统标识
        fs_type = boot_sector[3:11]
        if fs_type == b'NTFS    ':
            return True
        
        return False
    
    def _parse_ntfs_boot_sector(self, boot_sector_info):
        """解析NTFS引导扇区"""
        boot_sector = boot_sector_info['data']
        offset = boot_sector_info['offset']
        
        info = {
            'partition_offset': offset,
            'bytes_per_sector': struct.unpack('<H', boot_sector[11:13])[0],
            'sectors_per_cluster': boot_sector[13],
            'total_sectors': struct.unpack('<Q', boot_sector[40:48])[0],
            'mft_cluster': struct.unpack('<Q', boot_sector[48:56])[0],
            'mft_mirror_cluster': struct.unpack('<Q', boot_sector[56:64])[0],
            'volume_label': 'NTFS Volume'
        }
        
        # 计算关键参数
        info['cluster_size'] = info['sectors_per_cluster'] * info['bytes_per_sector']
        info['mft_offset'] = offset + info['mft_cluster'] * info['cluster_size']
        
        return info
    
    def _recover_ntfs_files(self, disk_file, ntfs_info, output_dir):
        """恢复NTFS文件"""
        recovered_files = []
        
        try:
            # 读取MFT
            self.status_updated.emit("正在读取MFT...")
            mft_records = self._read_mft_records(disk_file, ntfs_info)
            
            # 恢复文件
            self.status_updated.emit("正在恢复文件...")
            
            # 定义可恢复的文件类型（扩展列表以支持更多大文件类型）
            recoverable_extensions = {
                # 文档类型
                'txt', 'doc', 'docx', 'pdf', 'xls', 'xlsx', 'ppt', 'pptx', 'rtf', 'odt', 'ods', 'odp',
                # 图片类型
                'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'ico', 'webp', 'svg', 'psd', 'ai', 'eps',
                # 音频类型
                'mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'opus',
                # 视频类型（通常是大文件）
                'mp4', 'avi', 'mkv', 'mov', 'wmv', 'flv', 'webm', 'm4v', 'mpg', 'mpeg', '3gp', 'f4v',
                # 压缩文件（可能很大）
                'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'iso', 'dmg',
                # 可执行文件
                'exe', 'dll', 'sys', 'bat', 'cmd', 'msi', 'app',
                # 网页和脚本
                'html', 'htm', 'css', 'js', 'xml', 'json', 'php', 'asp', 'jsp',
                # 编程语言
                'c', 'cpp', 'h', 'py', 'java', 'cs', 'go', 'rs', 'swift', 'kt',
                # 数据库文件（可能很大）
                'db', 'sqlite', 'mdb', 'accdb', 'sql',
                # 虚拟机和镜像文件（通常很大）
                'vmdk', 'vdi', 'vhd', 'qcow2', 'img',
                # CAD和设计文件（通常较大）
                'dwg', 'dxf', 'step', 'iges', 'stl',
                # 其他常见大文件类型
                'bin', 'dat', 'log', 'backup', 'bak'
            }
            
            for record_num, mft_record in enumerate(mft_records):
                if record_num % 100 == 0:
                    # 文件恢复占50%进度（从50%开始）
                    progress = 50 + min(50, (record_num * 50) // len(mft_records))
                    self.progress_updated.emit(progress)
                
                try:
                    file_info = self._parse_mft_record(mft_record)
                    if (file_info and file_info['filename'] and 
                        not file_info['is_directory'] and 
                        file_info['file_size'] > 0):
                        
                        # 文件类型过滤（扩展逻辑以支持更多文件）
                        should_recover = False
                        
                        # 如果有扩展名且在可恢复列表中
                        if (file_info['file_extension'] and 
                            file_info['file_extension'] in recoverable_extensions):
                            should_recover = True
                        
                        # 如果没有扩展名但文件大小超过1MB，也尝试恢复（可能是大文件）
                        elif not file_info['file_extension'] and file_info['file_size'] > 1024 * 1024:
                            should_recover = True
                        
                        # 如果文件大小超过10MB，无论扩展名如何都尝试恢复
                        elif file_info['file_size'] > 10 * 1024 * 1024:
                            should_recover = True
                        
                        if should_recover:
                            
                            # 添加文件大小信息到状态显示
                            file_size_mb = file_info['file_size'] / (1024 * 1024)
                            data_runs_count = len(file_info.get('data_runs', []))
                            self.status_updated.emit(
                                f"正在恢复: {file_info['filename']} ({file_size_mb:.1f}MB, {data_runs_count}个数据运行)"
                            )
                            
                            recovered_file = self._recover_ntfs_file(
                                disk_file, ntfs_info, file_info, output_dir
                            )
                            if recovered_file:
                                recovered_files.append(recovered_file)
                                
                                # 显示恢复状态
                                status = "已删除" if file_info['is_deleted'] else "正常"
                                completion = recovered_file.get('completion_rate', 0)
                                self.status_updated.emit(
                                    f"恢复完成: {file_info['filename']} ({status}, 完整度: {completion:.1f}%)"
                                )
                            else:
                                self.status_updated.emit(
                                    f"恢复失败: {file_info['filename']} ({file_size_mb:.1f}MB)"
                                )
                except Exception as e:
                    # 记录但不中断恢复过程
                    continue
            
        except Exception as e:
            self.status_updated.emit(f"恢复过程中出错: {str(e)}")
        
        return recovered_files
    
    def _read_mft_records(self, disk_file, ntfs_info):
        """读取MFT记录"""
        mft_records = []
        
        # 从MFT开始位置读取
        disk_file.seek(ntfs_info['mft_offset'])
        
        # 计算MFT大小，尝试读取更多记录
        # 对于大磁盘，需要读取更多MFT记录以发现所有文件
        max_records = min(100000, ntfs_info['total_sectors'] // 2)  # 增加到100000个记录
        
        # 对于超过1TB的磁盘，进一步增加记录数
        if ntfs_info['total_sectors'] * ntfs_info['bytes_per_sector'] > 1024 * 1024 * 1024 * 1024:  # 1TB
            max_records = min(500000, ntfs_info['total_sectors'] // 2)
        
        consecutive_failures = 0
        for i in range(max_records):
            try:
                # 如果连续失败太多次，尝试跳过一些扇区
                if consecutive_failures > 100:
                    disk_file.seek(disk_file.tell() + 1024 * 10)  # 跳过10个记录
                    consecutive_failures = 0
                    continue
                
                record_data = disk_file.read(1024)
                if len(record_data) < 1024:
                    break
                
                # 检查MFT记录签名（包括已删除的记录）
                if record_data[0:4] in [b'FILE', b'BAAD']:  # BAAD表示损坏或删除的记录
                    mft_records.append(record_data)
                    consecutive_failures = 0  # 重置失败计数
                else:
                    consecutive_failures += 1
                    
                # 更新进度
                if i % 1000 == 0:
                    progress = min(50, (i * 50) // max_records)  # MFT读取占50%进度
                    self.progress_updated.emit(progress)
                    self.status_updated.emit(f"已读取MFT记录: {len(mft_records)}/{i+1}")
                    
            except Exception as e:
                # 跳过读取失败的记录
                consecutive_failures += 1
                continue
        
        return mft_records
    
    def _parse_mft_record(self, mft_record):
        """解析MFT记录"""
        if len(mft_record) < 1024:
            return None
            
        # 检查记录签名
        signature = mft_record[0:4]
        if signature not in [b'FILE', b'BAAD']:
            return None
        
        # 检查记录状态
        flags = struct.unpack('<H', mft_record[22:24])[0]
        is_in_use = bool(flags & 0x01)
        is_directory = bool(flags & 0x02)
        
        # 对于删除的文件，我们仍然尝试恢复
        # if not is_in_use:  # 注释掉这个检查，允许恢复删除的文件
        #     return None
        
        # 获取属性偏移
        attr_offset = struct.unpack('<H', mft_record[20:22])[0]
        
        file_info = {
            'filename': None,
            'file_size': 0,
            'is_directory': is_directory,
            'is_deleted': not is_in_use,
            'data_runs': [],
            'file_extension': None,
            'creation_time': None,
            'modification_time': None
        }
        
        # 解析属性
        offset = attr_offset
        while offset < len(mft_record) - 4:
            attr_type = struct.unpack('<L', mft_record[offset:offset+4])[0]
            
            if attr_type == 0xFFFFFFFF:  # 属性结束
                break
            
            attr_length = struct.unpack('<L', mft_record[offset+4:offset+8])[0]
            if attr_length == 0 or offset + attr_length > len(mft_record):
                break
            
            attr_data = mft_record[offset:offset+attr_length]
            
            if attr_type == 0x10:  # STANDARD_INFORMATION
                try:
                    # 解析标准信息属性
                    std_info = self._parse_standard_information(attr_data)
                    if std_info:
                        file_info['creation_time'] = std_info.get('creation_time')
                        file_info['modification_time'] = std_info.get('modification_time')
                        # 更新目录标志
                        if 'file_attributes' in std_info:
                            file_info['is_directory'] = bool(std_info['file_attributes'] & 0x10)
                except:
                    pass
            elif attr_type == 0x30:  # FILE_NAME
                filename = self._parse_filename_attribute(attr_data)
                if filename and not filename.startswith('$'):
                    file_info['filename'] = filename
                    # 提取文件扩展名
                    if '.' in filename:
                        file_info['file_extension'] = filename.split('.')[-1].lower()
            elif attr_type == 0x80:  # DATA
                # 检查是否为主数据流（无名称）还是备用数据流（有名称）
                attr_name = self._get_attribute_name(attr_data)
                
                # 只处理主数据流（无名称的DATA属性），跳过备用数据流
                if not attr_name:  # 主数据流
                    data_info = self._parse_data_attribute(attr_data)
                    if data_info:
                        file_info['file_size'] = data_info['file_size']
                        file_info['data_runs'] = data_info['data_runs']
                        # 如果是常驻属性，保存常驻数据
                        if 'resident_data' in data_info:
                            file_info['resident_data'] = data_info['resident_data']
                        # 调试信息：确认处理了主数据流
                        if data_info['file_size'] > 1024 * 1024:  # 大于1MB的文件
                            print(f"处理主数据流: 文件大小={data_info['file_size']}, 数据运行数量={len(data_info['data_runs'])}")
                else:
                    # 备用数据流，跳过处理
                    # 这些通常是Zone.Identifier等元数据
                    print(f"跳过备用数据流: {attr_name}")
            
            offset += attr_length
        
        return file_info if file_info['filename'] else None
    
    def _parse_standard_information(self, attr_data):
        """解析标准信息属性"""
        try:
            if len(attr_data) < 24:
                return None
            
            # 获取属性内容偏移
            content_offset = struct.unpack('<H', attr_data[20:22])[0]
            if content_offset >= len(attr_data) or len(attr_data) < content_offset + 48:
                return None
            
            content = attr_data[content_offset:]
            
            # 解析时间戳（Windows FILETIME格式）
            creation_time = struct.unpack('<Q', content[0:8])[0]
            modification_time = struct.unpack('<Q', content[8:16])[0]
            file_attributes = struct.unpack('<L', content[32:36])[0]
            
            return {
                'creation_time': creation_time,
                'modification_time': modification_time,
                'file_attributes': file_attributes
            }
        except:
            return None
    
    def _parse_filename_attribute(self, attr_data):
        """解析文件名属性"""
        if len(attr_data) < 24:
            return None
        
        # 获取属性内容偏移
        content_offset = struct.unpack('<H', attr_data[20:22])[0]
        if content_offset >= len(attr_data):
            return None
        
        content = attr_data[content_offset:]
        if len(content) < 66:
            return None
        
        # 获取文件名长度和文件名
        filename_length = content[64]
        if len(content) < 66 + filename_length * 2:
            return None
        
        filename_data = content[66:66 + filename_length * 2]
        try:
            filename = filename_data.decode('utf-16le')
            return filename
        except:
            return None
    
    def _get_attribute_name(self, attr_data):
        """获取属性名称，用于区分主数据流和备用数据流"""
        if len(attr_data) < 24:
            return None
        
        # 获取属性名称长度和偏移
        name_length = attr_data[9]  # 属性名称长度（以UTF-16字符为单位）
        name_offset = struct.unpack('<H', attr_data[10:12])[0]  # 属性名称偏移
        
        # 如果没有名称，返回None（主数据流）
        if name_length == 0 or name_offset == 0:
            return None
        
        # 检查偏移是否有效
        if name_offset >= len(attr_data) or name_offset + name_length * 2 > len(attr_data):
            return None
        
        try:
            # 读取属性名称（UTF-16LE编码）
            name_data = attr_data[name_offset:name_offset + name_length * 2]
            attr_name = name_data.decode('utf-16le')
            return attr_name
        except:
            return None
    
    def _parse_data_attribute(self, attr_data):
        """解析数据属性"""
        if len(attr_data) < 16:
            return None
        
        # 检查是否为非常驻属性
        non_resident = attr_data[8]
        if non_resident == 0:  # 常驻属性
            if len(attr_data) < 24:
                return None
            
            content_length = struct.unpack('<L', attr_data[16:20])[0]
            content_offset = struct.unpack('<H', attr_data[20:22])[0]
            
            # 提取常驻属性的实际数据内容
            if content_offset + content_length <= len(attr_data):
                resident_data = attr_data[content_offset:content_offset + content_length]
                return {
                    'file_size': content_length, 
                    'data_runs': [],
                    'resident_data': resident_data  # 添加常驻数据
                }
            else:
                return {'file_size': content_length, 'data_runs': []}
        
        # 非常驻属性
        if len(attr_data) < 64:
            return None
        
        file_size = struct.unpack('<Q', attr_data[48:56])[0]
        
        # 正确读取数据运行偏移量（从属性头偏移0x20处）
        runlist_offset = struct.unpack('<H', attr_data[32:34])[0]
        
        # 调试信息：输出关键参数
        if file_size > 3 * 1024 * 1024:  # 对于大于3MB的文件输出调试信息
            print(f"解析非常驻属性: 文件大小={file_size}, runlist_offset={runlist_offset}, attr_data长度={len(attr_data)}")
        
        # 验证runlist_offset的有效性
        if runlist_offset >= len(attr_data) or runlist_offset == 0:
            # 如果偏移无效，尝试从标准位置开始查找
            # 对于非常驻属性，数据运行通常从偏移64开始
            for test_offset in [64, 72, 80]:  # 尝试几个可能的位置
                if test_offset < len(attr_data) and attr_data[test_offset] != 0:
                    runlist_offset = test_offset
                    if file_size > 3 * 1024 * 1024:
                        print(f"使用备用runlist_offset: {runlist_offset}")
                    break
            else:
                if file_size > 3 * 1024 * 1024:
                    print(f"无法找到有效的runlist_offset")
                return {'file_size': file_size, 'data_runs': []}
            
        if runlist_offset >= len(attr_data):
            return {'file_size': file_size, 'data_runs': []}
        
        # 解析数据运行列表
        runlist_data = attr_data[runlist_offset:]
        if file_size > 3 * 1024 * 1024:
            print(f"开始解析数据运行，runlist数据长度: {len(runlist_data)}")
            if len(runlist_data) > 0:
                print(f"runlist前8字节: {runlist_data[:min(8, len(runlist_data))].hex()}")
        
        data_runs = self._parse_data_runs(runlist_data)
        
        # 对于大文件，验证数据运行的合理性
        if file_size > 3 * 1024 * 1024:
            print(f"解析完成，数据运行数量: {len(data_runs)}")
            if len(data_runs) > 0:
                print(f"第一个数据运行: cluster={data_runs[0]['cluster']}, length={data_runs[0]['length']}")
            elif file_size > 10 * 1024 * 1024:
                print(f"警告：大文件但没有数据运行，可能解析失败")
        
        return {'file_size': file_size, 'data_runs': data_runs}
    
    def _parse_data_runs(self, runlist_data):
        """解析数据运行列表"""
        data_runs = []
        offset = 0
        current_cluster = 0
        debug_large_file = len(runlist_data) > 0 and runlist_data[0] != 0  # 简单判断是否需要调试
        
        try:
            while offset < len(runlist_data):
                if runlist_data[offset] == 0:
                    if debug_large_file:
                        print(f"数据运行解析结束，偏移: {offset}")
                    break
                
                # 获取长度和偏移的字节数
                length_bytes = runlist_data[offset] & 0x0F
                offset_bytes = (runlist_data[offset] & 0xF0) >> 4
                
                if debug_large_file:
                    print(f"偏移{offset}: 头字节=0x{runlist_data[offset]:02x}, length_bytes={length_bytes}, offset_bytes={offset_bytes}")
                
                if length_bytes == 0 or offset + 1 + length_bytes + offset_bytes > len(runlist_data):
                    break
                
                # 读取长度
                length_data = runlist_data[offset + 1:offset + 1 + length_bytes]
                length = 0
                for i, byte in enumerate(length_data):
                    length |= byte << (i * 8)
                
                if debug_large_file:
                    print(f"  长度数据: {length_data.hex()}, 解析长度: {length}")
                
                # 读取偏移
                if offset_bytes > 0:
                    offset_data = runlist_data[offset + 1 + length_bytes:offset + 1 + length_bytes + offset_bytes]
                    cluster_offset = 0
                    for i, byte in enumerate(offset_data):
                        cluster_offset |= byte << (i * 8)
                    
                    # 处理负偏移
                    if cluster_offset & (1 << (offset_bytes * 8 - 1)):
                        cluster_offset -= 1 << (offset_bytes * 8)
                    
                    old_cluster = current_cluster
                    current_cluster += cluster_offset
                    
                    if debug_large_file:
                        print(f"  偏移数据: {offset_data.hex()}, cluster_offset: {cluster_offset}, 当前簇: {old_cluster} -> {current_cluster}")
                    
                    # 验证数据运行的有效性
                    if current_cluster >= 0 and length > 0:
                        data_runs.append({'cluster': current_cluster, 'length': length})
                        if debug_large_file:
                            print(f"  添加数据运行: cluster={current_cluster}, length={length}")
                    elif debug_large_file:
                        print(f"  跳过无效数据运行: cluster={current_cluster}, length={length}")
                else:
                    # 处理稀疏数据运行（offset_bytes=0）
                    # 稀疏数据运行表示文件中的空洞，簇号保持不变
                    if length > 0:
                        # 对于稀疏数据运行，我们需要记录空洞的位置
                        # 但在NTFS恢复中，我们可以跳过空洞部分
                        if debug_large_file:
                            print(f"  处理稀疏数据运行: length={length}, 当前簇保持: {current_cluster}")
                        # 注意：稀疏数据运行不改变current_cluster，但我们需要记录这个空洞
                        # 为了简化恢复过程，我们可以创建一个特殊的数据运行标记
                        data_runs.append({'cluster': -1, 'length': length, 'sparse': True})
                        if debug_large_file:
                            print(f"  添加稀疏数据运行: length={length}")
                    else:
                        if debug_large_file:
                            print(f"  跳过无效数据运行: length={length}, offset_bytes={offset_bytes}")
                
                offset += 1 + length_bytes + offset_bytes
                
        except Exception as e:
            # 如果解析失败，返回已解析的部分
            pass
        
        return data_runs
    
    def _recover_ntfs_file(self, disk_file, ntfs_info, file_info, output_dir):
        """恢复NTFS文件"""
        try:
            filename = file_info['filename']
            
            # 清理文件名中的非法字符，保留更多有效字符
            import re
            filename = re.sub(r'[<>:"/\|?*]', '_', filename)
            filename = filename.strip()
            
            if not filename:
                # 如果文件名为空，生成一个基于扩展名的名称
                ext = file_info.get('file_extension', 'unknown')
                filename = f"recovered_file_{hash(str(file_info)) & 0xFFFF}.{ext}"
            
            # 处理重复文件名
            base_name, ext = os.path.splitext(filename)
            counter = 1
            filepath = os.path.join(output_dir, filename)
            
            while os.path.exists(filepath):
                new_filename = f"{base_name}_{counter}{ext}"
                filepath = os.path.join(output_dir, new_filename)
                counter += 1
            
            # 创建子目录（按文件类型分类）
            if file_info.get('file_extension'):
                type_dir = os.path.join(output_dir, file_info['file_extension'].upper())
                os.makedirs(type_dir, exist_ok=True)
                filepath = os.path.join(type_dir, os.path.basename(filepath))
            
            with open(filepath, 'wb') as output_file:
                remaining_size = file_info['file_size']
                bytes_written = 0
                
                # 如果没有数据运行信息，尝试从常驻属性恢复
                if not file_info['data_runs']:
                    # 检查是否有常驻数据
                    if 'resident_data' in file_info and file_info['resident_data']:
                        # 写入常驻属性数据
                        output_file.write(file_info['resident_data'])
                        bytes_written = len(file_info['resident_data'])
                        self.status_updated.emit(f"恢复常驻属性文件: {filename}")
                    else:
                        # 小文件可能存储在MFT记录中但数据提取失败
                        self.status_updated.emit(f"无法恢复常驻属性文件: {filename}")
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return None
                
                # 检查是否所有数据运行都是稀疏的
                non_sparse_runs = [run for run in file_info['data_runs'] if not run.get('sparse', False) and run['cluster'] != -1]
                if not non_sparse_runs and file_info['data_runs']:
                    # 如果只有稀疏数据运行，这可能是一个空文件或损坏的文件
                    self.status_updated.emit(f"文件只包含稀疏数据运行，可能已损坏: {filename}")
                    # 仍然尝试恢复，但标记为可能损坏
                    pass
                
                for data_run in file_info['data_runs']:
                    if remaining_size <= 0:
                        break
                    
                    try:
                        # 检查是否为稀疏数据运行
                        if data_run.get('sparse', False) or data_run['cluster'] == -1:
                            # 稀疏数据运行：写入零字节
                            sparse_size = min(data_run['length'] * ntfs_info['cluster_size'], remaining_size)
                            if sparse_size > 0:
                                output_file.write(b'\x00' * sparse_size)
                                remaining_size -= sparse_size
                                bytes_written += sparse_size
                                self.status_updated.emit(f"处理稀疏数据运行: {sparse_size} 字节 (簇: {data_run['cluster']}, 长度: {data_run['length']})")
                            continue
                        
                        # 计算簇位置
                        cluster_offset = (ntfs_info['partition_offset'] + 
                                        data_run['cluster'] * ntfs_info['cluster_size'])
                        
                        # 对于大文件，使用批量读取优化
                        if data_run['length'] > 1024:  # 超过1024个簇时使用批量读取
                            # 批量读取整个数据运行
                            try:
                                disk_file.seek(cluster_offset)
                                total_read_size = min(data_run['length'] * ntfs_info['cluster_size'], remaining_size)
                                run_data = disk_file.read(total_read_size)
                                
                                if len(run_data) > 0:
                                    write_size = min(len(run_data), remaining_size)
                                    output_file.write(run_data[:write_size])
                                    remaining_size -= write_size
                                    bytes_written += write_size
                                else:
                                    # 如果批量读取失败，回退到逐簇读取
                                    remaining_size -= min(total_read_size, remaining_size)
                            except Exception as e:
                                # 批量读取失败，回退到逐簇读取
                                for i in range(data_run['length']):
                                    if remaining_size <= 0:
                                        break
                                    try:
                                        disk_file.seek(cluster_offset + i * ntfs_info['cluster_size'])
                                        read_size = min(ntfs_info['cluster_size'], remaining_size)
                                        cluster_data = disk_file.read(read_size)
                                        
                                        if len(cluster_data) > 0:
                                            write_size = min(len(cluster_data), remaining_size)
                                            output_file.write(cluster_data[:write_size])
                                            remaining_size -= write_size
                                            bytes_written += write_size
                                        else:
                                            remaining_size -= min(ntfs_info['cluster_size'], remaining_size)
                                    except Exception as e:
                                        remaining_size -= min(ntfs_info['cluster_size'], remaining_size)
                                        continue
                        else:
                            # 小文件使用原有的逐簇读取方式
                            for i in range(data_run['length']):
                                if remaining_size <= 0:
                                    break
                                
                                try:
                                    disk_file.seek(cluster_offset + i * ntfs_info['cluster_size'])
                                    read_size = min(ntfs_info['cluster_size'], remaining_size)
                                    cluster_data = disk_file.read(read_size)
                                    
                                    if len(cluster_data) > 0:
                                        # 只写入实际需要的字节数
                                        write_size = min(len(cluster_data), remaining_size)
                                        output_file.write(cluster_data[:write_size])
                                        remaining_size -= write_size
                                        bytes_written += write_size
                                    else:
                                        # 如果读取失败，跳过这个簇
                                        remaining_size -= min(ntfs_info['cluster_size'], remaining_size)
                                        
                                except Exception as e:
                                    # 跳过损坏的簇，继续恢复其他部分
                                    remaining_size -= min(ntfs_info['cluster_size'], remaining_size)
                                    continue
                                
                    except Exception as e:
                        # 跳过损坏的数据运行
                        continue
            
            # 检查文件完整性
            if bytes_written > 0:
                completion_rate = (bytes_written / file_info['file_size']) * 100 if file_info['file_size'] > 0 else 100
                status_msg = f"恢复文件: {filename} (完整度: {completion_rate:.1f}%)"
                
                if file_info['is_deleted']:
                    status_msg += " [已删除文件]"
                    
                self.status_updated.emit(status_msg)
                return {
                    'filepath': filepath,
                    'original_name': file_info['filename'],
                    'size': bytes_written,
                    'completion_rate': completion_rate,
                    'is_deleted': file_info['is_deleted'],
                    'file_type': file_info.get('file_extension', 'unknown')
                }
            else:
                # 删除空文件
                if os.path.exists(filepath):
                    os.remove(filepath)
                return None
        
        except Exception as e:
            self.status_updated.emit(f"恢复文件 {file_info['filename']} 失败: {str(e)}")
            # 清理失败的文件
            if 'filepath' in locals() and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except:
                    pass
            return None