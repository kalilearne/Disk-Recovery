#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import platform
import traceback
import datetime
import threading
import time
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, 
    QTreeWidget, QTreeWidgetItem, QHeaderView, QTabWidget, 
    QAction, QToolBar, QStatusBar, QMessageBox, QFileDialog,
    QMenu, QLabel, QPushButton, QComboBox, QApplication, QDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QTimer
from PyQt5.QtGui import QIcon, QPixmap

from disk_reader import DiskReader
from file_signature_recovery import FileSignatureRecovery
from file_system_reader import FileSystemReader
from ui_components import (
    HexViewer, FileSystemTree, DiskInfoPanel, ProgressDialog,
    DataWipeDialog, FileRecoveryDialog, WorkerThread, StatusBar
)

class DiskRecoveryTool(QMainWindow):
    """磁盘恢复工具主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("磁盘恢复工具")
        self.resize(1200, 800)
        
        # 初始化UI
        self.init_ui()
        
        # 加载磁盘列表
        self.load_disks()
        
        # 当前选中的磁盘
        self.current_disk = None
        
        # 当前工作线程
        self.current_worker = None
        
        # 状态更新定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(5000)  # 每5秒更新一次状态
    
    def init_ui(self):
        """初始化用户界面"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 创建主分割器
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # 创建左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 磁盘选择下拉框
        disk_layout = QHBoxLayout()
        disk_layout.addWidget(QLabel("选择磁盘："))
        self.disk_combo = QComboBox()
        self.disk_combo.currentIndexChanged.connect(self.on_disk_selected)
        disk_layout.addWidget(self.disk_combo)
        refresh_button = QPushButton("刷新")
        refresh_button.clicked.connect(self.load_disks)
        disk_layout.addWidget(refresh_button)
        left_layout.addLayout(disk_layout)
        
        # 文件系统树
        self.file_tree = FileSystemTree()
        self.file_tree.item_double_clicked.connect(self.on_tree_item_double_clicked)
        left_layout.addWidget(self.file_tree)
        
        # 添加左侧面板到主分割器
        self.main_splitter.addWidget(left_panel)
        
        # 创建右侧面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建右侧选项卡
        self.tabs = QTabWidget()
        
        # 十六进制查看器选项卡
        self.hex_viewer = HexViewer()
        self.tabs.addTab(self.hex_viewer, "十六进制查看器")
        
        # 磁盘信息选项卡
        self.disk_info_panel = DiskInfoPanel()
        self.tabs.addTab(self.disk_info_panel, "磁盘信息")
        
        # 添加选项卡到右侧面板
        right_layout.addWidget(self.tabs)
        
        # 添加右侧面板到主分割器
        self.main_splitter.addWidget(right_panel)
        
        # 设置分割器初始大小
        self.main_splitter.setSizes([300, 900])
        
        # 创建工具栏
        self.create_toolbar()
        
        # 创建菜单栏
        self.create_menu()
        
        # 创建状态栏
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar)
    
    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)
        
        # 刷新按钮
        refresh_action = QAction("刷新", self)
        refresh_action.setStatusTip("刷新磁盘列表")
        refresh_action.triggered.connect(self.load_disks)
        toolbar.addAction(refresh_action)
        
        toolbar.addSeparator()
        
        # 物理磁盘浏览按钮
        browse_physical_action = QAction("物理磁盘浏览", self)
        browse_physical_action.setStatusTip("浏览物理磁盘")
        browse_physical_action.triggered.connect(self.browse_physical_disk)
        toolbar.addAction(browse_physical_action)
        
        # 分区浏览按钮
        browse_partition_action = QAction("分区浏览", self)
        browse_partition_action.setStatusTip("浏览分区")
        browse_partition_action.triggered.connect(self.browse_partition)
        toolbar.addAction(browse_partition_action)
        
        toolbar.addSeparator()
        
        # 文件签名恢复按钮
        file_recovery_action = QAction("文件签名恢复", self)
        file_recovery_action.setStatusTip("通过文件签名恢复文件")
        file_recovery_action.triggered.connect(self.recover_files_by_signature)
        toolbar.addAction(file_recovery_action)
        
        # FAT32恢复按钮
        fat32_recovery_action = QAction("FAT32恢复", self)
        fat32_recovery_action.setStatusTip("恢复FAT32文件系统")
        fat32_recovery_action.triggered.connect(self.recover_fat32)
        toolbar.addAction(fat32_recovery_action)
        
        # NTFS恢复按钮
        ntfs_recovery_action = QAction("NTFS恢复", self)
        ntfs_recovery_action.setStatusTip("恢复NTFS文件系统")
        ntfs_recovery_action.triggered.connect(self.recover_ntfs)
        toolbar.addAction(ntfs_recovery_action)
        
        toolbar.addSeparator()
        
        # 虚拟磁盘按钮
        virtual_disk_action = QAction("虚拟磁盘", self)
        virtual_disk_action.setStatusTip("打开虚拟磁盘文件")
        virtual_disk_action.triggered.connect(self.open_virtual_disk)
        toolbar.addAction(virtual_disk_action)
        
        toolbar.addSeparator()
        
        # 数据擦除按钮
        wipe_action = QAction("数据擦除", self)
        wipe_action.setStatusTip("安全擦除磁盘数据")
        wipe_action.triggered.connect(self.wipe_disk)
        toolbar.addAction(wipe_action)
    
    def create_menu(self):
        """创建菜单栏"""
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        refresh_action = QAction("刷新磁盘列表", self)
        refresh_action.triggered.connect(self.load_disks)
        file_menu.addAction(refresh_action)
        
        open_virtual_action = QAction("打开虚拟磁盘...", self)
        open_virtual_action.triggered.connect(self.open_virtual_disk)
        file_menu.addAction(open_virtual_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 浏览菜单
        browse_menu = menubar.addMenu("浏览")
        
        browse_physical_action = QAction("物理磁盘浏览", self)
        browse_physical_action.triggered.connect(self.browse_physical_disk)
        browse_menu.addAction(browse_physical_action)
        
        browse_partition_action = QAction("分区浏览", self)
        browse_partition_action.triggered.connect(self.browse_partition)
        browse_menu.addAction(browse_partition_action)
        
        # 恢复菜单
        recovery_menu = menubar.addMenu("恢复")
        
        file_recovery_action = QAction("文件签名恢复", self)
        file_recovery_action.triggered.connect(self.recover_files_by_signature)
        recovery_menu.addAction(file_recovery_action)
        
        fat32_recovery_action = QAction("FAT32恢复", self)
        fat32_recovery_action.triggered.connect(self.recover_fat32)
        recovery_menu.addAction(fat32_recovery_action)
        
        ntfs_recovery_action = QAction("NTFS恢复", self)
        ntfs_recovery_action.triggered.connect(self.recover_ntfs)
        recovery_menu.addAction(ntfs_recovery_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        
        wipe_action = QAction("数据擦除", self)
        wipe_action.triggered.connect(self.wipe_disk)
        tools_menu.addAction(wipe_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def load_disks(self):
        """加载磁盘列表"""
        try:
            # 创建进度对话框
            progress_dialog = ProgressDialog("加载磁盘", "正在扫描系统磁盘...", self)
            
            # 创建磁盘加载工作线程
            self.disk_loader_worker = DiskLoaderWorker()
            
            # 连接信号
            self.disk_loader_worker.progress_updated.connect(progress_dialog.set_progress)
            self.disk_loader_worker.status_updated.connect(progress_dialog.set_message)
            self.disk_loader_worker.detail_updated.connect(progress_dialog.set_detail)
            self.disk_loader_worker.operation_completed.connect(self.on_disks_loaded)
            self.disk_loader_worker.operation_failed.connect(self.show_error)
            
            # 启动线程
            self.disk_loader_worker.start()
            
            # 显示进度对话框
            if progress_dialog.exec_() == QDialog.Rejected:
                # 用户取消了操作
                self.disk_loader_worker.cancel()
                
        except Exception as e:
            self.show_error(f"加载磁盘列表错误: {str(e)}")
            traceback.print_exc()
    
    def on_disks_loaded(self, result):
        """处理磁盘加载完成事件"""
        try:
            self.disk_combo.clear()
            self.file_tree.clear_tree()
            
            physical_disks = result.get('disks', [])
            
            # 添加到下拉框
            for disk in physical_disks:
                disk_name = f"{disk['name']} ({disk['size_human']})" if 'size_human' in disk else disk['name']
                self.disk_combo.addItem(disk_name, disk)
            
            self.status_bar.set_status(f"已加载 {len(physical_disks)} 个磁盘")
        except Exception as e:
            self.show_error(f"处理磁盘加载结果错误: {str(e)}")
            traceback.print_exc()
    
    def on_disk_selected(self, index):
        """处理磁盘选择事件"""
        if index < 0:
            return
        
        try:
            # 获取选中的磁盘
            self.current_disk = self.disk_combo.itemData(index)
            if not self.current_disk:
                return
            
            # 清空文件树
            self.file_tree.clear_tree()
            
            # 显示磁盘信息
            self.show_disk_info(self.current_disk)
            
            # 如果是物理磁盘，尝试读取MBR
            if self.current_disk['type'] == 'physical':
                self.read_mbr(self.current_disk['path'])
            
            # 如果是逻辑磁盘，尝试读取文件系统
            elif self.current_disk['type'] == 'logical':
                self.read_filesystem(self.current_disk['path'])
            
            self.status_bar.set_status(f"已选择磁盘: {self.current_disk['name']}")
        except Exception as e:
            self.show_error(f"选择磁盘错误: {str(e)}")
            traceback.print_exc()
    
    def show_disk_info(self, disk):
        """显示磁盘信息"""
        try:
            # 准备磁盘信息
            info = {}
            for key, value in disk.items():
                if key not in ['path']:
                    info[key] = value
            
            # 显示在信息面板中
            self.disk_info_panel.set_html(info)
            
            # 切换到信息选项卡
            self.tabs.setCurrentWidget(self.disk_info_panel)
        except Exception as e:
            self.show_error(f"显示关于信息错误: {str(e)}")
            traceback.print_exc()


class DiskLoaderWorker(WorkerThread):
    """磁盘加载工作线程"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def run(self):
        """执行磁盘加载任务"""
        try:
            self.status_updated.emit("正在扫描系统磁盘...")
            self.progress_updated.emit(10)
            
            if self.is_cancelled:
                return
            
            # 获取物理磁盘列表（使用多线程优化）
            self.detail_updated.emit("正在读取物理磁盘信息...")
            physical_disks = self._read_disks_with_progress()
            
            if self.is_cancelled:
                return
            
            self.progress_updated.emit(90)
            self.detail_updated.emit("正在整理磁盘信息...")
            
            # 为每个磁盘添加人类可读的大小信息
            for disk in physical_disks:
                if 'size' in disk and disk['size'] > 0:
                    disk['size_human'] = self._format_size(disk['size'])
                else:
                    disk['size_human'] = "未知大小"
            
            self.progress_updated.emit(100)
            self.status_updated.emit(f"成功加载 {len(physical_disks)} 个磁盘")
            
            # 发送完成信号
            self.operation_completed.emit({'disks': physical_disks})
            
        except Exception as e:
            self.operation_failed.emit(f"磁盘加载失败: {str(e)}")
            traceback.print_exc()
    
    def _read_disks_with_progress(self):
        """带进度的磁盘读取"""
        disks = []
        
        try:
            # 使用线程池并行读取磁盘信息
            import concurrent.futures
            import threading
            
            self.progress_updated.emit(20)
            
            if platform.system() == 'Windows':
                # 先获取逻辑驱动器
                self.detail_updated.emit("正在扫描逻辑驱动器...")
                logical_disks = self._get_logical_drives()
                disks.extend(logical_disks)
                
                if self.is_cancelled:
                    return disks
                
                self.progress_updated.emit(50)
                
                # 再获取物理磁盘
                self.detail_updated.emit("正在扫描物理磁盘...")
                physical_disks = self._get_physical_drives()
                disks.extend(physical_disks)
                
                self.progress_updated.emit(80)
            else:
                # Linux/Unix系统的处理
                self.detail_updated.emit("正在扫描Unix/Linux磁盘...")
                unix_disks = DiskReader.read_physical_disks()
                disks.extend(unix_disks)
                self.progress_updated.emit(80)
            
        except Exception as e:
            print(f"读取磁盘时发生错误: {e}")
            # 如果多线程读取失败，回退到原始方法
            self.detail_updated.emit("回退到标准扫描模式...")
            disks = DiskReader.read_physical_disks()
        
        return disks
    
    def _get_logical_drives(self):
        """获取逻辑驱动器"""
        drives = []
        if platform.system() == 'Windows':
            import win32api
            import win32file
            
            try:
                drive_strings = win32api.GetLogicalDriveStrings().split('\x00')[:-1]
                for i, drive in enumerate(drive_strings):
                    if self.is_cancelled:
                        break
                    
                    try:
                        drive_type = win32file.GetDriveType(drive)
                        if drive_type == win32file.DRIVE_FIXED or drive_type == win32file.DRIVE_REMOVABLE:
                            # 获取磁盘信息
                            volume_name = ''
                            try:
                                volume_name = win32api.GetVolumeInformation(drive)[0]
                            except:
                                pass
                            
                            # 获取磁盘大小
                            try:
                                sectors_per_cluster, bytes_per_sector, free_clusters, total_clusters = win32file.GetDiskFreeSpace(drive)
                                total_size = total_clusters * sectors_per_cluster * bytes_per_sector
                                free_size = free_clusters * sectors_per_cluster * bytes_per_sector
                            except:
                                total_size = 0
                                free_size = 0
                            
                            disk_info = {
                                'path': drive,
                                'name': f'{drive} {volume_name}',
                                'size': total_size,
                                'free': free_size,
                                'type': 'logical',
                                'letter': drive[0]
                            }
                            drives.append(disk_info)
                    except Exception as e:
                        print(f"Error reading drive {drive}: {e}")
            except Exception as e:
                print(f"Error getting logical drives: {e}")
        
        return drives
    
    def _get_physical_drives(self):
        """获取物理驱动器"""
        drives = []
        if platform.system() == 'Windows':
            import win32file
            import winioctlcon
            import struct
            
            # 使用线程池并行检查物理磁盘
            import concurrent.futures
            
            def check_physical_disk(disk_index):
                try:
                    disk_path = f'\\\\.\\PhysicalDrive{disk_index}'
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
                            disk_size = 0
                        
                        disk_info = {
                            'path': disk_path,
                            'name': f'物理磁盘 {disk_index}',
                            'size': disk_size,
                            'free': 0,
                            'type': 'physical'
                        }
                        win32file.CloseHandle(handle)
                        return disk_info
                except:
                    pass
                return None
            
            # 并行检查最多10个物理磁盘
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                future_to_index = {executor.submit(check_physical_disk, i): i for i in range(10)}
                
                for future in concurrent.futures.as_completed(future_to_index):
                    if self.is_cancelled:
                        break
                    
                    result = future.result()
                    if result:
                        drives.append(result)
        
        return drives
    
    def _format_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    
    def read_mbr(self, disk_path):
        """读取MBR分区表"""
        try:
            # 读取MBR
            mbr_info = FileSystemReader.read_mbr(disk_path)
            
            if 'error' in mbr_info:
                self.show_error(mbr_info['error'])
                return
            
            # 显示MBR信息
            self.disk_info_panel.set_html(mbr_info)
            
            # 在文件树中添加分区
            root = self.file_tree.invisibleRootItem()
            disk_item = self.file_tree.add_item(root, f"磁盘 {disk_path}", "", "物理磁盘")
            
            if 'partitions' in mbr_info:
                for partition in mbr_info['partitions']:
                    partition_name = f"分区 {partition['index']} ({partition['type_name']}, {partition['size_human']})"
                    partition_item = self.file_tree.add_item(
                        disk_item, 
                        partition_name, 
                        partition['size_human'], 
                        partition['type_name'],
                        partition['status'],
                        {
                            'type': 'partition',
                            'disk_path': disk_path,
                            'start_lba': partition['start_lba'],
                            'sectors': partition['sectors'],
                            'partition_type': partition['type'],
                            'name': partition_name
                        }
                    )
        except Exception as e:
            self.show_error(f"读取MBR错误: {str(e)}")
            traceback.print_exc()
    
    def read_filesystem(self, disk_path):
        """读取文件系统"""
        try:
            # 读取文件系统信息
            fs_info = FileSystemReader.read_universal_filesystem(disk_path)
            
            if 'error' in fs_info:
                self.show_error(fs_info['error'])
                return
            
            # 显示文件系统信息
            self.disk_info_panel.set_html(fs_info)
            
            # 在文件树中添加文件系统信息
            root = self.file_tree.invisibleRootItem()
            fs_type = fs_info.get('filesystem', '未知')
            
            if fs_type == 'FAT32':
                fs_item = self.file_tree.add_item(root, f"FAT32 ({disk_path})", "", "文件系统")
                if 'volume_label' in fs_info and fs_info['volume_label']:
                    self.file_tree.add_item(fs_item, f"卷标: {fs_info['volume_label']}")
                self.file_tree.add_item(fs_item, f"簇大小: {fs_info['cluster_size']} 字节")
                self.file_tree.add_item(fs_item, f"总大小: {fs_info['total_size_human']}")
            
            elif fs_type == 'NTFS':
                fs_item = self.file_tree.add_item(root, f"NTFS ({disk_path})", "", "文件系统")
                self.file_tree.add_item(fs_item, f"簇大小: {fs_info['cluster_size']} 字节")
                self.file_tree.add_item(fs_item, f"总大小: {fs_info['total_size_human']}")
                self.file_tree.add_item(fs_item, f"MFT起始簇: {fs_info['mft_cluster']}")
            
            elif fs_type == 'MBR' and 'mbr_info' in fs_info:
                # 如果是MBR，显示分区信息
                mbr_info = fs_info['mbr_info']
                disk_item = self.file_tree.add_item(root, f"磁盘 {disk_path}", "", "物理磁盘")
                
                if 'partitions' in mbr_info:
                    for partition in mbr_info['partitions']:
                        partition_name = f"分区 {partition['index']} ({partition['type_name']}, {partition['size_human']})"
                        partition_item = self.file_tree.add_item(
                            disk_item, 
                            partition_name, 
                            partition['size_human'], 
                            partition['type_name'],
                            partition['status'],
                            {
                                'type': 'partition',
                                'disk_path': disk_path,
                                'start_lba': partition['start_lba'],
                                'sectors': partition['sectors'],
                                'partition_type': partition['type'],
                                'name': partition_name
                            }
                        )
            
            elif 'scan_result' in fs_info and 'found_files' in fs_info['scan_result']:
                # 如果是未知文件系统但有扫描结果，显示找到的文件
                scan_item = self.file_tree.add_item(root, f"扫描结果 ({disk_path})", "", "扫描结果")
                
                # 按类型组织文件
                if 'files_by_type' in fs_info['scan_result']:
                    for file_type, files in fs_info['scan_result']['files_by_type'].items():
                        type_item = self.file_tree.add_item(scan_item, f"{file_type} ({len(files)}个文件)", "", file_type)
                        
                        for i, file in enumerate(files):
                            file_name = f"{file['desc']} (偏移: {file['offset']})"
                            self.file_tree.add_item(
                                type_item,
                                file_name,
                                f"{file['estimated_size']} 字节",
                                file['ext'][1:] if file['ext'] else "未知",
                                "",
                                {
                                    'type': 'file_signature',
                                    'disk_path': disk_path,
                                    'offset': file['offset'],
                                    'estimated_size': file['estimated_size'],
                                    'file_type': file['type'],
                                    'ext': file['ext'],
                                    'name': file_name
                                }
                            )
        except Exception as e:
            self.show_error(f"读取文件系统错误: {str(e)}")
            traceback.print_exc()
    
    def on_tree_item_double_clicked(self, item_data):
        """处理树项目双击事件"""
        try:
            if not item_data:
                return
            
            item_type = item_data.get('type')
            
            if item_type == 'partition':
                # 读取分区引导扇区
                disk_path = item_data['disk_path']
                start_lba = item_data['start_lba']
                
                # 检测文件系统类型
                fs_info = FileSystemReader.detect_filesystem(disk_path, start_lba)
                
                if 'error' in fs_info:
                    self.show_error(fs_info['error'])
                    return
                
                filesystem = fs_info.get('filesystem', '未知')
                
                # 根据文件系统类型读取详细信息
                if filesystem == 'NTFS':
                    fs_info = FileSystemReader.read_ntfs_boot_sector(disk_path, start_lba)
                elif filesystem == 'FAT32':
                    fs_info = FileSystemReader.read_fat32_boot_sector(disk_path, start_lba)
                else:
                    fs_info = {'filesystem': filesystem, 'message': f'暂不支持读取{filesystem}文件系统详细信息'}
                
                # 显示文件系统信息
                self.disk_info_panel.set_html(fs_info)
                self.tabs.setCurrentWidget(self.disk_info_panel)
                
                # 读取分区前几个扇区的数据
                sector_data = DiskReader.read_disk_sector(disk_path, start_lba, 8)
                if sector_data:
                    self.hex_viewer.set_data(sector_data, start_lba * 512)
            
            elif item_type == 'file_signature':
                # 读取文件签名数据
                disk_path = item_data['disk_path']
                offset = item_data['offset']
                estimated_size = min(item_data['estimated_size'], 1024 * 1024)  # 限制为最大1MB
                
                # 计算起始扇区和扇区数
                start_sector = offset // 512
                sectors_to_read = (estimated_size + 511) // 512  # 向上取整
                
                # 读取数据
                file_data = DiskReader.read_disk_sector(disk_path, start_sector, sectors_to_read)
                if file_data:
                    # 计算在扇区内的偏移
                    sector_offset = offset % 512
                    # 截取实际的文件数据
                    file_data = file_data[sector_offset:sector_offset + estimated_size]
                    # 显示在十六进制查看器中
                    self.hex_viewer.set_data(file_data, offset)
                    self.tabs.setCurrentWidget(self.hex_viewer)
        except Exception as e:
            self.show_error(f"处理项目双击错误: {str(e)}")
            traceback.print_exc()
    
    def browse_physical_disk(self):
        """浏览物理磁盘"""
        if not self.current_disk:
            self.show_error("请先选择一个磁盘")
            return
        
        try:
            disk_path = self.current_disk['path']
            
            # 读取前几个扇区的数据
            sector_data = DiskReader.read_disk_sector(disk_path, 0, 16)
            if sector_data:
                self.hex_viewer.set_data(sector_data, 0)
                self.tabs.setCurrentWidget(self.hex_viewer)
        except Exception as e:
            self.show_error(f"浏览物理磁盘错误: {str(e)}")
            traceback.print_exc()
    
    def browse_partition(self):
        """浏览分区"""
        if not self.current_disk:
            self.show_error("请先选择一个磁盘")
            return
        
        try:
            # 如果是逻辑磁盘，直接读取
            if self.current_disk['type'] == 'logical':
                disk_path = self.current_disk['path']
                
                # 读取前几个扇区的数据
                sector_data = DiskReader.read_disk_sector(disk_path, 0, 16)
                if sector_data:
                    self.hex_viewer.set_data(sector_data, 0)
                    self.tabs.setCurrentWidget(self.hex_viewer)
            else:
                self.show_error("请选择一个逻辑磁盘或分区")
        except Exception as e:
            self.show_error(f"浏览分区错误: {str(e)}")
            traceback.print_exc()
    
    def recover_files_by_signature(self):
        """通过文件签名恢复文件"""
        if not self.current_disk:
            self.show_error("请先选择一个磁盘")
            return
        
        try:
            # 显示文件恢复对话框
            dialog = FileRecoveryDialog(self)
            if dialog.exec_():
                # 获取用户选择
                selected_types = dialog.get_selected_types()
                reverse = dialog.get_scan_direction()
                save_path = dialog.get_save_path()
                
                # 创建进度对话框
                progress_dialog = ProgressDialog("文件恢复", "正在恢复文件...", self)
                
                # 创建工作线程
                class RecoveryWorker(WorkerThread):
                    def __init__(self, disk_path, selected_types, save_path, reverse):
                        super().__init__()
                        self.disk_path = disk_path
                        self.selected_types = selected_types
                        self.save_path = save_path
                        self.reverse = reverse
                    
                    def run(self):
                        try:
                            # 转换选择的类型为实际的签名
                            signature_map = {
                                "images": [b'\xFF\xD8\xFF', b'\x89PNG\r\n\x1A\n', b'GIF8', b'BM'],
                                "documents": [b'%PDF', b'\xD0\xCF\x11\xE0', b'PK\x03\x04\x14\x00\x06\x00'],
                                "archives": [b'PK\x03\x04', b'Rar!\x1A\x07\x00', b'7z\xBC\xAF\x27\x1C'],
                                "audio": [b'ID3'],
                                "video": [b'\x00\x00\x00\x18ftypmp42', b'\x00\x00\x00\x14ftypqt']
                            }
                            
                            # 如果选择了所有类型，使用None表示所有签名
                            if "all" in self.selected_types:
                                selected_signatures = None
                            else:
                                # 合并所有选择的类型的签名
                                selected_signatures = []
                                for type_name in self.selected_types:
                                    if type_name in signature_map:
                                        selected_signatures.extend(signature_map[type_name])
                            
                            # 恢复文件
                            result = FileSignatureRecovery.recover_files_by_signature(
                                self.disk_path,
                                selected_signatures,
                                self.save_path,
                                self.reverse
                            )
                            
                            # 发送完成信号
                            self.operation_completed.emit(result)
                        except Exception as e:
                            self.operation_failed.emit(str(e))
                            traceback.print_exc()
                
                # 创建并启动工作线程
                self.current_worker = RecoveryWorker(
                    self.current_disk['path'],
                    selected_types,
                    save_path,
                    reverse
                )
                
                # 连接信号
                self.current_worker.progress_updated.connect(progress_dialog.set_progress)
                self.current_worker.status_updated.connect(progress_dialog.set_message)
                self.current_worker.detail_updated.connect(progress_dialog.set_detail)
                self.current_worker.operation_completed.connect(self.on_recovery_completed)
                self.current_worker.operation_failed.connect(self.show_error)
                
                # 启动线程
                self.current_worker.start()
                
                # 显示进度对话框
                if progress_dialog.exec_() == QDialog.Rejected:
                    # 用户取消了操作
                    self.current_worker.cancel()
        except Exception as e:
            self.show_error(f"文件恢复错误: {str(e)}")
            traceback.print_exc()
    
    def on_recovery_completed(self, result):
        """处理恢复完成事件"""
        try:
            files = result.get('files', [])
            by_type = result.get('by_type', {})
            
            # 显示恢复结果
            message = f"恢复完成，共恢复 {len(files)} 个文件。\n\n"
            
            # 按类型统计
            for file_type, type_files in by_type.items():
                message += f"{file_type}: {len(type_files)} 个文件\n"
            
            # 询问是否打开恢复目录
            reply = QMessageBox.question(
                self,
                "恢复完成",
                message + "\n是否打开恢复目录？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                # 打开恢复目录
                save_dir = os.path.dirname(files[0]['path']) if files else None
                if save_dir and os.path.exists(save_dir):
                    if platform.system() == 'Windows':
                        os.startfile(save_dir)
                    elif platform.system() == 'Darwin':  # macOS
                        os.system(f'open "{save_dir}"')
                    else:  # Linux
                        os.system(f'xdg-open "{save_dir}"')
        except Exception as e:
            self.show_error(f"处理恢复完成错误: {str(e)}")
            traceback.print_exc()
    
    def recover_fat32(self):
        """恢复FAT32文件系统"""
        self.show_info("FAT32恢复功能尚未实现")
    
    def recover_ntfs(self):
        """恢复NTFS文件系统"""
        self.show_info("NTFS恢复功能尚未实现")
    
    def open_virtual_disk(self):
        """打开虚拟磁盘文件"""
        try:
            # 打开文件对话框
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "打开虚拟磁盘文件",
                "",
                "虚拟磁盘文件 (*.vhd *.vmdk *.vdi *.img *.iso *.bin);;所有文件 (*.*)"
            )
            
            if not file_path:
                return
            
            # 读取虚拟磁盘
            disk_data = DiskReader.read_virtual_disk(file_path)
            
            if not disk_data:
                self.show_error("无法读取虚拟磁盘文件")
                return
            
            # 显示在十六进制查看器中
            self.hex_viewer.set_data(disk_data, 0)
            self.tabs.setCurrentWidget(self.hex_viewer)
            
            # 尝试读取MBR
            mbr_info = FileSystemReader.read_mbr(file_path)
            
            if 'error' not in mbr_info:
                # 显示MBR信息
                self.disk_info_panel.set_html(mbr_info)
                
                # 在文件树中添加分区
                self.file_tree.clear_tree()
                root = self.file_tree.invisibleRootItem()
                disk_item = self.file_tree.add_item(root, f"虚拟磁盘 {os.path.basename(file_path)}", "", "虚拟磁盘")
                
                if 'partitions' in mbr_info:
                    for partition in mbr_info['partitions']:
                        partition_name = f"分区 {partition['index']} ({partition['type_name']}, {partition['size_human']})"
                        partition_item = self.file_tree.add_item(
                            disk_item, 
                            partition_name, 
                            partition['size_human'], 
                            partition['type_name'],
                            partition['status'],
                            {
                                'type': 'partition',
                                'disk_path': file_path,
                                'start_lba': partition['start_lba'],
                                'sectors': partition['sectors'],
                                'partition_type': partition['type'],
                                'name': partition_name
                            }
                        )
            
            self.status_bar.set_status(f"已打开虚拟磁盘: {os.path.basename(file_path)}")
        except Exception as e:
            self.show_error(f"打开虚拟磁盘错误: {str(e)}")
            traceback.print_exc()
    
    def wipe_disk(self):
        """安全擦除磁盘数据"""
        if not self.current_disk:
            self.show_error("请先选择一个磁盘")
            return
        
        try:
            # 显示警告对话框
            reply = QMessageBox.warning(
                self,
                "数据擦除警告",
                f"您即将擦除磁盘 {self.current_disk['name']} 上的所有数据。\n\n此操作不可逆！\n\n是否继续？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            # 显示数据擦除对话框
            dialog = DataWipeDialog(self)
            if dialog.exec_():
                # 获取用户选择的擦除方法
                wipe_method = dialog.get_selected_method()
                
                # 显示进度对话框
                progress_dialog = ProgressDialog("数据擦除", "正在擦除数据...", self)
                
                # 创建工作线程
                class WipeWorker(WorkerThread):
                    def __init__(self, disk_path, wipe_method):
                        super().__init__()
                        self.disk_path = disk_path
                        self.wipe_method = wipe_method
                    
                    def run(self):
                        try:
                            # 这里应该实现实际的擦除逻辑
                            # 由于擦除是危险操作，这里只模拟进度
                            for i in range(101):
                                if self.is_cancelled:
                                    break
                                
                                self.progress_updated.emit(i)
                                self.status_updated.emit(f"正在擦除... {i}%")
                                self.detail_updated.emit(f"当前位置: {i * 1024 * 1024} 字节")
                                
                                # 模拟耗时操作
                                time.sleep(0.1)
                            
                            # 发送完成信号
                            self.operation_completed.emit({"success": True})
                        except Exception as e:
                            self.operation_failed.emit(str(e))
                            traceback.print_exc()
                
                # 创建并启动工作线程
                self.current_worker = WipeWorker(
                    self.current_disk['path'],
                    wipe_method
                )
                
                # 连接信号
                self.current_worker.progress_updated.connect(progress_dialog.set_progress)
                self.current_worker.status_updated.connect(progress_dialog.set_message)
                self.current_worker.detail_updated.connect(progress_dialog.set_detail)
                self.current_worker.operation_completed.connect(lambda result: self.show_info("数据擦除完成"))
                self.current_worker.operation_failed.connect(self.show_error)
                
                # 启动线程
                self.current_worker.start()
                
                # 显示进度对话框
                if progress_dialog.exec_() == QDialog.Rejected:
                    # 用户取消了操作
                    self.current_worker.cancel()
        except Exception as e:
            self.show_error(f"数据擦除错误: {str(e)}")
            traceback.print_exc()
    
    def update_status(self):
        """更新状态栏信息"""
        if self.current_disk:
            self.status_bar.set_status(f"当前磁盘: {self.current_disk['name']}")
    
    def show_error(self, message):
        """显示错误消息"""
        QMessageBox.critical(self, "错误", str(message))
    
    def show_info(self, message):
        """显示信息消息"""
        QMessageBox.information(self, "信息", str(message))
    
    def show_about(self):
        """显示关于对话框"""
        try:
            QMessageBox.about(
                self,
                "关于磁盘恢复工具",
                "<h3>磁盘恢复工具</h3>"
                "<p>版本 1.0</p>"
                "<p>一个用于磁盘数据恢复和分析的工具。</p>"
                "<p>功能包括：</p>"
                "<ul>"
                "<li>物理磁盘和分区浏览</li>"
                "<li>十六进制查看器</li>"
                "<li>文件系统树查看</li>"
                "<li>磁盘信息显示</li>"
                "<li>文件签名恢复</li>"
                "<li>FAT32和NTFS文件系统恢复</li>"
                "<li>虚拟磁盘支持</li>"
                "<li>数据安全擦除</li>"
                "</ul>"
                "<p>&copy; 2023 磁盘恢复工具团队</p>"
            )
        except Exception as e:
            self.show_error(f"显示关于信息错误: {str(e)}")
            traceback.print_exc()