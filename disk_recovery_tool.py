import os
import sys
import struct
import platform
import threading
import time
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTabWidget, QComboBox, QLabel, QPushButton,
    QToolBar, QAction, QMenuBar, QFileDialog, QMessageBox,
    QProgressDialog, QInputDialog, QCheckBox, QDialog, QListWidget,
    QListWidgetItem
)
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal, QThread
from PyQt5.QtGui import QIcon

from ui_components import (
    FileSystemTree, HexViewer, DiskInfoPanel, StatusBar,
    ProgressDialog, WorkerThread, DataWipeDialog
)
from disk_utils import DiskManager
from file_recovery import FileRecovery
from fat32_recovery import FAT32Recovery
from ntfs_recovery import NTFSRecovery
from data_wipe import DataWipe

class DiskLoaderWorker(WorkerThread):
    """磁盘加载工作线程"""
    disks_loaded = pyqtSignal(list)
    
    def run(self):
        try:
            disk_manager = DiskManager()
            disks = disk_manager.get_physical_disks()
            self.disks_loaded.emit(disks)
            self.finished.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.finished.emit()
            self.finished.emit()

class RecoveryWorker(WorkerThread):
    """文件恢复工作线程"""
    def __init__(self, recovery_type, disk_path, output_dir, **kwargs):
        super().__init__()
        self.recovery_type = recovery_type
        self.disk_path = disk_path
        self.output_dir = output_dir
        self.kwargs = kwargs
    
    def run(self):
        try:
            self.status_updated.emit(f"开始{self.recovery_type}恢复...")
            
            if self.recovery_type == 'signature':
                # 优先使用磁盘镜像快照恢复
                from file_signature_recovery import FileSignatureRecovery
                
                # 提取文件类型参数
                file_types = self.kwargs.get('file_types', None)
                
                # 使用快照恢复方法
                self.status_updated.emit("正在检查磁盘类型...")
                
                # 检查是否为挂载分区
                is_mounted = (
                    len(self.disk_path) >= 2 and 
                    self.disk_path[1] == ':' and 
                    (len(self.disk_path) == 2 or self.disk_path.endswith('\\'))
                )
                
                if is_mounted:
                    self.status_updated.emit(f"检测到挂载分区 {self.disk_path}，正在创建磁盘镜像快照...")
                else:
                    self.status_updated.emit(f"检测到原始设备 {self.disk_path}，使用直接访问模式...")
                
                result = FileSignatureRecovery.recover_files_by_signature_with_snapshot(
                    self.disk_path, 
                    selected_types=file_types, 
                    save_dir=self.output_dir
                )
                
                # 发送恢复统计信息
                if result and 'files' in result:
                    recovered_count = len(result['files'])
                    self.status_updated.emit(f"恢复完成，共找到 {recovered_count} 个文件")
                    
                    # 按类型统计
                    if 'by_type' in result:
                        type_stats = []
                        for file_type, count in result['by_type'].items():
                            if count > 0:
                                type_stats.append(f"{file_type}: {count}个")
                        if type_stats:
                            self.status_updated.emit(f"文件类型分布: {', '.join(type_stats)}")
                else:
                    self.status_updated.emit("恢复完成，未找到文件")
            elif self.recovery_type == 'signature_legacy':
                # 传统文件签名恢复方法（不使用快照）
                from file_recovery import FileRecovery
                recovery = FileRecovery()
                recovery.progress_updated.connect(self.progress_updated)
                recovery.status_updated.connect(self.status_updated)
                recovery.recover_by_signature(self.disk_path, self.output_dir, **self.kwargs)
            elif self.recovery_type == 'fat32':
                from fat32_recovery import FAT32Recovery
                recovery = FAT32Recovery()
                recovery.progress_updated.connect(self.progress_updated)
                recovery.status_updated.connect(self.status_updated)
                # 从kwargs中获取use_disk_image参数，默认为True
                use_disk_image = self.kwargs.get('use_disk_image', True)
                recovery.recover_files(self.disk_path, self.output_dir, use_disk_image=use_disk_image)
            elif self.recovery_type == 'ntfs':
                from ntfs_recovery import NTFSRecovery
                recovery = NTFSRecovery()
                recovery.progress_updated.connect(self.progress_updated)
                recovery.status_updated.connect(self.status_updated)
                recovery.recover_files(self.disk_path, self.output_dir, use_disk_image=True)
            else:
                raise ValueError(f"不支持的恢复类型: {self.recovery_type}")
            
            self.status_updated.emit(f"{self.recovery_type}恢复完成")
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.status_updated.emit(f"{self.recovery_type}恢复失败: {str(e)}")
            self.error_occurred.emit(f"恢复过程中发生错误: {str(e)}\n\n详细信息:\n{error_details}")
        finally:
            # 确保无论如何都发出完成信号
            self.finished.emit()

class PartitionWipeWorker(WorkerThread):
    """分区擦除工作线程"""
    def __init__(self, disk_path, offset, size):
        super().__init__()
        self.disk_path = disk_path
        self.offset = offset
        self.size = size
    
    def run(self):
        try:
            self.status_updated.emit("正在打开磁盘...")
            
            # 检查磁盘路径是否存在
            if not os.path.exists(self.disk_path):
                raise FileNotFoundError(f"磁盘路径不存在: {self.disk_path}")
            
            # 对于Windows逻辑驱动器，需要特殊处理
            disk_handle = None
            if sys.platform == 'win32' and self.disk_path.endswith('\\'):
                # 逻辑驱动器路径，需要获取对应的物理设备句柄
                drive_letter = self.disk_path[0]
                try:
                    try:
                        import win32file
                        import win32api
                        import ctypes
                    except ImportError as e:
                        raise Exception(f"win32api模块导入失败: {e}。请安装pywin32模块。")
                    
                    # 检查是否有管理员权限
                    if not ctypes.windll.shell32.IsUserAnAdmin():
                        raise Exception("分区擦除需要管理员权限。请以管理员身份运行程序。")
                    
                    # 获取逻辑驱动器对应的物理磁盘路径
                    volume_name = f"\\\\.\\{drive_letter}:"
                    
                    self.status_updated.emit(f"正在以管理员权限打开逻辑驱动器 {self.disk_path}...")
                    
                    # 打开卷句柄进行直接访问
                    disk_handle = win32file.CreateFile(
                        volume_name,
                        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                        win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE,
                        None,
                        win32file.OPEN_EXISTING,
                        win32file.FILE_FLAG_NO_BUFFERING | win32file.FILE_FLAG_WRITE_THROUGH,
                        None
                    )
                    
                    if disk_handle == win32file.INVALID_HANDLE_VALUE:
                        raise Exception(f"无法打开逻辑驱动器 {self.disk_path}。请确保：\n1. 程序以管理员身份运行\n2. 驱动器未被其他程序占用\n3. 驱动器存在且可访问")
                        
                    self.status_updated.emit(f"已成功打开逻辑驱动器 {self.disk_path}")
                    
                except ImportError:
                    raise Exception(f"需要安装pywin32模块才能处理逻辑驱动器 {self.disk_path}")
                except Exception as e:
                    if disk_handle and disk_handle != win32file.INVALID_HANDLE_VALUE:
                        win32file.CloseHandle(disk_handle)
                    # 检查具体的Windows错误代码
                    error_msg = str(e)
                    if "拒绝访问" in error_msg or "Access is denied" in error_msg:
                        raise Exception(f"访问被拒绝。请确保：\n1. 以管理员身份运行程序\n2. 关闭所有使用该驱动器的程序\n3. 驱动器未被系统保护\n\n原始错误: {error_msg}")
                    else:
                        raise Exception(f"打开逻辑驱动器失败: {error_msg}")
            
            # 处理不同类型的磁盘访问
            if disk_handle:  # Windows逻辑驱动器
                try:
                    import win32file
                    
                    # 移动到分区起始位置
                    win32file.SetFilePointer(disk_handle, self.offset, win32file.FILE_BEGIN)
                    
                    # 计算需要写入的块数
                    block_size = 1024 * 1024  # 1MB块
                    total_blocks = (self.size + block_size - 1) // block_size
                    
                    self.status_updated.emit(f"开始擦除分区数据，总大小: {self.size / (1024*1024):.1f} MB")
                    
                    # 创建零填充块
                    zero_block = b'\x00' * block_size
                    
                    for i in range(total_blocks):
                        # 计算当前块的实际大小
                        remaining = self.size - (i * block_size)
                        current_block_size = min(block_size, remaining)
                        
                        # 写入零数据
                        if current_block_size == block_size:
                            win32file.WriteFile(disk_handle, zero_block)
                        else:
                            win32file.WriteFile(disk_handle, b'\x00' * current_block_size)
                        
                        # 更新进度
                        progress = int((i + 1) * 100 / total_blocks)
                        self.progress_updated.emit(progress)
                        self.status_updated.emit(f"已擦除: {(i + 1) * block_size / (1024*1024):.1f} MB / {self.size / (1024*1024):.1f} MB")
                    
                    # 强制刷新到磁盘
                    win32file.FlushFileBuffers(disk_handle)
                    
                    self.status_updated.emit("分区擦除完成")
                    
                finally:
                    # 确保关闭句柄
                    if disk_handle and disk_handle != win32file.INVALID_HANDLE_VALUE:
                        win32file.CloseHandle(disk_handle)
            else:  # 普通文件或物理磁盘
                # 检查文件权限
                if not os.access(self.disk_path, os.W_OK):
                    # 尝试修改文件权限
                    try:
                        import stat
                        current_mode = os.stat(self.disk_path).st_mode
                        os.chmod(self.disk_path, current_mode | stat.S_IWRITE)
                        self.status_updated.emit(f"已修改文件权限: {self.disk_path}")
                    except Exception as perm_error:
                        raise Exception(f"文件权限不足且无法修改权限: {self.disk_path}\n\n解决方案:\n1. 右键文件 -> 属性 -> 取消'只读'属性\n2. 以管理员身份运行程序\n3. 检查文件是否被其他程序占用\n\n原始错误: {str(perm_error)}")
                
                # 打开磁盘文件
                with open(self.disk_path, 'r+b') as disk_file:
                    # 移动到分区起始位置
                    disk_file.seek(self.offset)
                    
                    # 计算需要写入的块数
                    block_size = 1024 * 1024  # 1MB块
                    total_blocks = (self.size + block_size - 1) // block_size
                    
                    self.status_updated.emit(f"开始擦除分区数据，总大小: {self.size / (1024*1024):.1f} MB")
                    
                    # 创建零填充块
                    zero_block = b'\x00' * block_size
                    
                    for i in range(total_blocks):
                        # 计算当前块的实际大小
                        remaining = self.size - (i * block_size)
                        current_block_size = min(block_size, remaining)
                        
                        # 写入零数据
                        if current_block_size == block_size:
                            disk_file.write(zero_block)
                        else:
                            disk_file.write(b'\x00' * current_block_size)
                        
                        # 更新进度
                        progress = int((i + 1) * 100 / total_blocks)
                        self.progress_updated.emit(progress)
                        self.status_updated.emit(f"已擦除: {(i + 1) * block_size / (1024*1024):.1f} MB / {self.size / (1024*1024):.1f} MB")
                    
                    # 强制刷新到磁盘
                    disk_file.flush()
                    os.fsync(disk_file.fileno())
                    
                    self.status_updated.emit("分区擦除完成")
                
        except Exception as e:
            error_msg = str(e)
            # 针对权限错误提供更详细的解决方案
            if "Permission denied" in error_msg or "拒绝访问" in error_msg:
                detailed_error = f"分区擦除失败 - 权限不足:\n\n文件: {self.disk_path}\n\n解决方案:\n"
                detailed_error += "1. 右键文件 -> 属性 -> 安全 -> 取消'只读'属性\n"
                detailed_error += "2. 确保文件未被其他程序打开或占用\n"
                detailed_error += "3. 以管理员身份运行本程序\n"
                detailed_error += "4. 检查文件所在磁盘是否有足够空间\n"
                detailed_error += "5. 如果是网络驱动器，请复制到本地后再操作\n\n"
                detailed_error += f"原始错误: {error_msg}"
                self.error_occurred.emit(detailed_error)
            else:
                self.error_occurred.emit(f"分区擦除失败: {error_msg}")
        finally:
            self.finished.emit()

class WipeWorker(WorkerThread):
    """磁盘擦除工作线程"""
    def __init__(self, disk_path, passes=1, pattern=None):
        super().__init__()
        self.disk_path = disk_path
        self.passes = passes
        self.pattern = pattern
    
    def run(self):
        try:
            wiper = DataWipe()
            wiper.progress_updated.connect(self.progress_updated)
            wiper.status_updated.connect(self.status_updated)
            # 修正参数顺序：disk_path, method, passes
            method = self.pattern if self.pattern else 'zeros'
            wiper.wipe_disk(self.disk_path, method, self.passes)
            self.finished.emit()
        except Exception as e:
            self.error_occurred.emit(str(e))

class DiskRecoveryTool(QMainWindow):
    """磁盘恢复工具主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DISK_recv")
        self.setWindowIcon(QIcon('favicon.ico'))
        self.setGeometry(100, 100, 1200, 800)
        
        # 初始化属性
        self.current_disk = None
        self.current_partition = None  # 当前选择的分区
        self.current_worker = None
        self.disk_manager = DiskManager()
        
        # 初始化UI
        self.init_ui()
        
        # 加载磁盘列表
        self.load_disks()
        
        # 创建状态更新定时器
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(5000)  # 每5秒更新一次状态
    
    def init_ui(self):
        """初始化用户界面"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(2, 2, 2, 2)  # 减少主布局边距
        main_layout.setSpacing(2)  # 减少主布局间距
        
        # 创建主分割器
        self.main_splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(self.main_splitter)
        
        # 创建左侧面板
        self.create_disk_panel()
        
        # 创建右侧面板
        self.create_main_panel()
        
        # 设置分割器初始大小 - 给右侧更多空间
        self.main_splitter.setSizes([280, 920])
        
        # 创建工具栏
        self.create_toolbar()
        
        # 创建菜单栏
        self.create_menu()
        
        # 创建状态栏
        self.status_bar = StatusBar()
        main_layout.addWidget(self.status_bar)
        self.status_bar.set_status("就绪")
    
    def create_disk_panel(self):
        """创建磁盘面板"""
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(2, 2, 2, 2)  # 减少边距
        left_layout.setSpacing(2)  # 减少间距
        
        # 创建左侧垂直分割器
        left_splitter = QSplitter(Qt.Vertical)
        
        # 上半部分：磁盘选择和分区结构
        top_left_widget = QWidget()
        top_left_layout = QVBoxLayout(top_left_widget)
        top_left_layout.setContentsMargins(3, 3, 3, 3)  # 减少边距
        top_left_layout.setSpacing(3)  # 减少间距
        
        # 磁盘选择下拉框
        disk_layout = QHBoxLayout()
        disk_layout.setSpacing(3)  # 减少间距
        disk_layout.addWidget(QLabel("选择磁盘："))
        self.disk_combo = QComboBox()
        self.disk_combo.currentIndexChanged.connect(self.on_disk_selected)
        disk_layout.addWidget(self.disk_combo)
        refresh_button = QPushButton("刷新")
        refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 5px;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-weight: bold;
                font-size: 13px;
                min-width: 60px;
                min-height: 28px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
        """)
        refresh_button.clicked.connect(self.load_disks)
        disk_layout.addWidget(refresh_button)
        
        top_left_layout.addLayout(disk_layout)
        
        # 分区结构标题
        partition_structure_label = QLabel("分区结构")
        partition_structure_label.setStyleSheet("font-family: 'Microsoft YaHei', 'SimHei', '黑体'; font-weight: bold; font-size: 25px; padding: 2px; text-align: center;")
        top_left_layout.addWidget(partition_structure_label)
        
        # 文件系统树（分区结构）
        self.file_tree = FileSystemTree()
        self.file_tree.item_double_clicked.connect(self.on_tree_item_double_clicked)
        self.file_tree.item_clicked.connect(self.on_tree_item_clicked)  # 连接单击事件
        top_left_layout.addWidget(self.file_tree)
        
        left_splitter.addWidget(top_left_widget)
        
        # 下半部分：逻辑分区文件浏览
        bottom_left_widget = QWidget()
        bottom_left_layout = QVBoxLayout(bottom_left_widget)
        bottom_left_layout.setContentsMargins(3, 3, 3, 3)  # 减少边距
        bottom_left_layout.setSpacing(3)  # 减少间距
        
        # 逻辑分区文件浏览标题
        partition_file_label = QLabel("逻辑分区文件浏览")
        partition_file_label.setStyleSheet("font-family: 'Microsoft YaHei', 'SimHei', '黑体'; font-weight: bold; font-size: 25px; padding: 2px; text-align: center;")
        bottom_left_layout.addWidget(partition_file_label)
        
        # 创建逻辑分区文件树
        self.partition_file_tree = FileSystemTree()
        self.partition_file_tree.item_double_clicked.connect(self.on_partition_file_double_clicked)
        bottom_left_layout.addWidget(self.partition_file_tree)
        
        left_splitter.addWidget(bottom_left_widget)
        
        # 设置左侧分割器的初始大小比例 - 优化空间分配
        left_splitter.setSizes([200, 300])  # 给下半部分更多空间
        
        left_layout.addWidget(left_splitter)
        
        # 添加左侧面板到主分割器
        self.main_splitter.addWidget(left_panel)
    
    def create_main_panel(self):
        """创建主面板"""
        # 创建右侧选项卡
        self.tabs = QTabWidget()
        
        # 十六进制查看器选项卡
        self.hex_viewer = HexViewer()
        self.tabs.addTab(self.hex_viewer, "十六进制查看器")
        
        # 磁盘信息选项卡
        self.disk_info_panel = DiskInfoPanel()
        self.tabs.addTab(self.disk_info_panel, "磁盘信息")
        
        # 添加右侧面板到主分割器
        self.main_splitter.addWidget(self.tabs)
    
    def create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setStyleSheet("""
            QToolBar {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
                border-radius: 5px;
                padding: 5px;
                spacing: 3px;
            }
            QToolBar::separator {
                background-color: #dee2e6;
                width: 1px;
                margin: 5px 3px;
            }
            QToolBar QToolButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 8px 12px;
                border-radius: 5px;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-weight: bold;
                font-size: 13px;
                min-width: 80px;
                min-height: 28px;
                margin: 2px;
            }
            QToolBar QToolButton:hover {
                background-color: #2980b9;
            }
            QToolBar QToolButton:pressed {
                background-color: #21618c;
            }
            QToolBar QToolButton[text*="恢复"] {
                background-color: #27ae60;
            }
            QToolBar QToolButton[text*="恢复"]:hover {
                background-color: #229954;
            }
            QToolBar QToolButton[text*="恢复"]:pressed {
                background-color: #1e8449;
            }
            QToolBar QToolButton[text*="擦除"] {
                background-color: #e74c3c;
            }
            QToolBar QToolButton[text*="擦除"]:hover {
                background-color: #c0392b;
            }
            QToolBar QToolButton[text*="擦除"]:pressed {
                background-color: #a93226;
            }
        """)
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
        
        # 虚拟磁盘按钮
        virtual_disk_action = QAction("虚拟磁盘", self)
        virtual_disk_action.setStatusTip("打开虚拟磁盘文件")
        virtual_disk_action.triggered.connect(self.open_virtual_disk)
        toolbar.addAction(virtual_disk_action)
        
        toolbar.addSeparator()
        
        # 文件签名恢复按钮
        file_recovery_action = QAction("文件签名恢复", self)
        file_recovery_action.setStatusTip("通过文件签名恢复文件")
        file_recovery_action.triggered.connect(self.recover_files_by_signature)
        toolbar.addAction(file_recovery_action)
        
        # FAT32恢复按钮
        fat32_recovery_action = QAction("FAT32恢复", self)
        fat32_recovery_action.setStatusTip("恢复FAT32文件系统（支持直接输入逻辑驱动器如F:）")
        fat32_recovery_action.triggered.connect(self.recover_fat32)
        toolbar.addAction(fat32_recovery_action)
        
        # 查看FAT表按钮
        view_fat_action = QAction("查看FAT表", self)
        view_fat_action.setStatusTip("在十六进制窗口查看FAT32文件系统的FAT表")
        view_fat_action.triggered.connect(self.view_fat_table)
        toolbar.addAction(view_fat_action)
        
        # 查看FDT按钮
        view_fdt_action = QAction("查看FDT", self)
        view_fdt_action.setStatusTip("在十六进制窗口查看FAT32文件系统的文件目录表")
        view_fdt_action.triggered.connect(self.view_fdt_table)
        toolbar.addAction(view_fdt_action)
        
        # NTFS恢复按钮
        ntfs_recovery_action = QAction("NTFS恢复", self)
        ntfs_recovery_action.setStatusTip("恢复NTFS文件系统（支持直接输入逻辑驱动器如F:）")
        ntfs_recovery_action.triggered.connect(self.recover_ntfs)
        toolbar.addAction(ntfs_recovery_action)
        
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
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        
        browse_physical_action = QAction("物理磁盘浏览", self)
        browse_physical_action.triggered.connect(self.browse_physical_disk)
        tools_menu.addAction(browse_physical_action)
        
        browse_partition_action = QAction("分区浏览", self)
        browse_partition_action.triggered.connect(self.browse_partition)
        tools_menu.addAction(browse_partition_action)
        
        tools_menu.addSeparator()
        
        view_fat_action = QAction("查看FAT表", self)
        view_fat_action.triggered.connect(self.view_fat_table)
        tools_menu.addAction(view_fat_action)
        
        view_fdt_action = QAction("查看FDT", self)
        view_fdt_action.triggered.connect(self.view_fdt_table)
        tools_menu.addAction(view_fdt_action)
        
        tools_menu.addSeparator()
        
        wipe_action = QAction("数据擦除", self)
        wipe_action.triggered.connect(self.wipe_disk)
        tools_menu.addAction(wipe_action)
        
        wipe_partition_action = QAction("分区擦除", self)
        wipe_partition_action.triggered.connect(self.wipe_partition)
        tools_menu.addAction(wipe_partition_action)
        
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
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def load_disks(self):
        """加载磁盘列表"""
        if self.current_worker:
            return
        
        self.status_bar.set_status("正在加载磁盘列表...")
        self.status_bar.show_progress()
        
        # 创建磁盘加载工作线程
        self.current_worker = DiskLoaderWorker()
        self.current_worker.disks_loaded.connect(self.on_disks_loaded)
        self.current_worker.error_occurred.connect(self.on_worker_error)
        self.current_worker.finished.connect(self.on_worker_finished)
        self.current_worker.start()
    
    def on_disks_loaded(self, disks):
        """磁盘加载完成"""
        self.disk_combo.clear()
        self.disk_combo.addItem("请选择磁盘...", None)
        
        for disk in disks:
            display_text = f"{disk['name']} ({disk['size_human']})"
            self.disk_combo.addItem(display_text, disk)
        
        self.status_bar.set_status(f"已加载 {len(disks)} 个磁盘")
    
    def select_virtual_disk(self):
        """选择虚拟磁盘文件"""
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, 
                "选择虚拟磁盘文件", 
                "", 
                "磁盘镜像文件 (*.img *.raw *.dd *.bin *.iso *.vhd *.vmdk);;所有文件 (*.*)"
            )
            
            if file_path:
                # 获取文件大小
                file_size = os.path.getsize(file_path)
                
                # 创建虚拟磁盘信息
                virtual_disk_info = {
                    'name': f"虚拟磁盘: {os.path.basename(file_path)}",
                    'path': file_path,
                    'size': file_size,
                    'type': 'virtual',
                    'file_system': '未知'
                }
                
                # 设置为当前磁盘
                self.current_disk = virtual_disk_info
                
                # 更新磁盘下拉框显示
                self.disk_combo.addItem(virtual_disk_info['name'], virtual_disk_info)
                self.disk_combo.setCurrentIndex(self.disk_combo.count() - 1)
                
                # 更新状态和信息面板
                self.status_bar.set_status(f"已选择虚拟磁盘: {virtual_disk_info['name']}")
                self.disk_info_panel.set_info(f"虚拟磁盘文件: {file_path}\n大小: {file_size // (1024*1024)} MB")
                
                # 清空文件系统树（虚拟磁盘暂不支持文件系统浏览）
                self.file_tree.clear()
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"选择虚拟磁盘失败: {str(e)}")
    
    def on_disk_selected(self, index):
        """磁盘选择事件"""
        if index <= 0:  # 第一项是提示文本
            self.current_disk = None
            self.file_tree.clear()
            self.partition_file_tree.clear()
            self.disk_info_panel.set_info("请选择一个磁盘")
            return
        
        disk_data = self.disk_combo.itemData(index)
        if disk_data:
            self.current_disk = disk_data
            # 只有物理磁盘才更新磁盘信息和加载文件树
            if disk_data.get('type') != 'virtual':
                self.update_disk_info()
                self.load_file_tree()
                self.load_partition_file_tree()
            else:
                # 虚拟磁盘只更新状态
                self.status_bar.set_status(f"已选择磁盘: {self.current_disk['name']}")
                self.file_tree.clear()
                self.partition_file_tree.clear()
    
    def update_disk_info(self):
        """更新磁盘信息"""
        if not self.current_disk:
            return
        
        try:
            # 获取详细磁盘信息
            disk_info = self.disk_manager.get_disk_info(self.current_disk['path'])
            self.disk_info_panel.set_html(disk_info)
            
            self.status_bar.set_status(f"已选择磁盘: {self.current_disk['name']}")
        except Exception as e:
            self.disk_info_panel.set_info(f"获取磁盘信息失败: {str(e)}")
            self.status_bar.set_status(f"错误: {str(e)}")
    
    def load_file_tree(self):
        """加载文件树"""
        if not self.current_disk:
            return
        
        try:
            self.file_tree.load_disk(self.current_disk['path'])
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载文件树失败: {str(e)}")
    
    def load_partition_file_tree(self):
        """加载逻辑分区文件树 - 显示提示信息"""
        if not self.current_disk:
            return
        
        try:
            self.partition_file_tree.clear_tree()
            
            # 显示提示信息
            info_item = self.partition_file_tree.add_item(None, "💡 请在上方分区结构中选择一个分区", "", "提示", "")
            help_item = self.partition_file_tree.add_item(None, "📋 单击分区可查看其文件结构", "", "帮助", "")
                    
        except Exception as e:
            error_item = self.partition_file_tree.add_item(None, f"初始化分区文件树失败: {str(e)}", "", "错误", "")
    
    def load_partition_file_tree_for_partition(self, partition_info):
        """为指定分区加载文件树"""
        if not self.current_disk or not partition_info:
            self.status_bar.set_status("无法加载分区文件树：缺少磁盘或分区信息")
            return
        
        try:
            from disk_utils import DiskManager
            
            # 清空现有的文件树
            self.partition_file_tree.clear_tree()
            disk_manager = DiskManager()
            
            # 创建分区根节点
            part_name = f"📁 {partition_info.get('type_name', '未知类型')}分区文件"
            part_size = f"{partition_info.get('size_human', '未知大小')}"
            
            root_item = self.partition_file_tree.add_item(None, part_name, part_size, "分区", "")
            
            try:
                # 加载分区文件
                self._load_partition_files(root_item, partition_info, disk_manager)
                
                # 展开根节点
                root_item.setExpanded(True)
                
                # 更新状态栏显示成功信息
                part_type = partition_info.get('type_name', '未知')
                self.status_bar.set_status(f"已加载 {part_type} 分区文件树")
                
            except Exception as e:
                error_item = self.partition_file_tree.add_item(root_item, f"❌ 加载文件失败: {str(e)}", "", "错误", "")
                # 展开根节点以显示错误信息
                root_item.setExpanded(True)
                self.status_bar.set_status(f"加载分区文件树失败: {str(e)}")
                    
        except Exception as e:
            error_item = self.partition_file_tree.add_item(None, f"❌ 加载分区文件树失败: {str(e)}", "", "错误", "")
            self.status_bar.set_status(f"加载分区文件树失败: {str(e)}")
    
    def _load_partition_files(self, parent_item, partition_info, disk_manager):
        """加载分区内的真实文件"""
        try:
            # 首先尝试获取分区的驱动器号
            drive_letter = self._get_partition_drive_letter(partition_info)
            
            if drive_letter:
                # 如果找到驱动器号，直接扫描文件系统
                self._scan_real_filesystem(parent_item, drive_letter)
            else:
                # 如果没有找到特定驱动器号，尝试扫描所有可用驱动器
                self._scan_all_available_drives(parent_item)
                
        except Exception as e:
            error_item = self.partition_file_tree.add_item(parent_item, f"读取文件系统失败: {str(e)}", "", "错误", "")
    
    def _get_partition_drive_letter(self, partition_info):
        """获取分区的驱动器号"""
        try:
            try:
                import win32api
                import win32file
            except ImportError as e:
                print(f"win32api模块导入失败: {e}")
                return None
            
            # 获取所有逻辑驱动器
            drives = win32api.GetLogicalDriveStrings()
            drives = drives.split('\000')[:-1]
            
            # 尝试使用WMI来匹配分区和驱动器号
            try:
                import wmi
                
                # 检查WMI服务是否可用
                try:
                    c = wmi.WMI()
                except Exception as wmi_error:
                    print(f"WMI服务不可用: {wmi_error}")
                    # 如果WMI不可用，尝试简单的驱动器匹配
                    return self._simple_drive_match(drives, partition_info)
                
                # 获取当前磁盘的设备ID
                current_disk_path = self.current_disk['path']
                disk_number = None
                
                # 从路径中提取磁盘号 (如 \\.\PhysicalDrive0 -> 0)
                if 'PhysicalDrive' in current_disk_path:
                    disk_number = int(current_disk_path.split('PhysicalDrive')[1])
                
                if disk_number is not None:
                    # 查找该磁盘上的分区
                    try:
                        for partition in c.Win32_DiskPartition():
                            if partition.DiskIndex == disk_number:
                                # 获取分区的起始扇区
                                partition_start = partition.StartingOffset // 512  # 转换为扇区
                                
                                # 检查是否匹配当前分区信息
                                if 'start_sector' in partition_info:
                                    if abs(partition_start - partition_info['start_sector']) < 100:  # 允许小误差
                                        # 查找该分区对应的逻辑磁盘
                                        try:
                                            for logical_disk in c.Win32_LogicalDiskToPartition():
                                                if logical_disk.Antecedent.DeviceID == partition.DeviceID:
                                                    drive_letter = logical_disk.Dependent.DeviceID + '\\'
                                                    if drive_letter in drives:
                                                        return drive_letter
                                        except Exception as ld_error:
                                            print(f"查询逻辑磁盘映射失败: {ld_error}")
                                            continue
                    except Exception as partition_error:
                        print(f"查询磁盘分区失败: {partition_error}")
                
            except ImportError:
                print("WMI模块未安装，使用简单匹配方法")
                return self._simple_drive_match(drives, partition_info)
            except Exception as e:
                print(f"WMI查询失败: {e}")
                return self._simple_drive_match(drives, partition_info)
            
            # 如果WMI方法失败，尝试简单匹配
            return self._simple_drive_match(drives, partition_info)
            
        except Exception as e:
            print(f"获取驱动器号失败: {e}")
            return None
    
    def _simple_drive_match(self, drives, partition_info):
        """简单的驱动器匹配方法"""
        try:
            # 如果只有一个驱动器，直接返回
            if len(drives) == 1:
                return drives[0]
            
            # 尝试根据分区大小匹配
            if 'size' in partition_info:
                try:
                    import win32file
                except ImportError:
                    print("win32file模块导入失败")
                    return None
                for drive in drives:
                    try:
                        # 获取驱动器大小
                        free_bytes, total_bytes = win32file.GetDiskFreeSpaceEx(drive)[:2]
                        # 如果分区大小接近驱动器大小，认为匹配
                        if abs(total_bytes - partition_info['size']) < (1024 * 1024 * 100):  # 100MB误差
                            return drive
                    except AttributeError:
                        # win32file没有GetDiskFreeSpaceEx函数
                        continue
                    except Exception:
                        continue
            
            # 如果无法匹配，返回None
            return None
            
        except Exception as e:
            print(f"简单驱动器匹配失败: {e}")
            return None
    
    def _scan_real_filesystem(self, parent_item, drive_path):
        """扫描真实的文件系统"""
        try:
            import os
            import stat
            
            # 检查驱动器是否可访问
            if not os.path.exists(drive_path):
                error_item = self.partition_file_tree.add_item(parent_item, f"❌ 驱动器 {drive_path} 不存在或无法访问", "", "错误", "")
                return
            
            # 添加驱动器信息提示
            info_item = self.partition_file_tree.add_item(parent_item, f"💿 正在扫描驱动器: {drive_path}", "", "信息", "")
            
            # 扫描根目录下的文件和文件夹
            try:
                items = os.listdir(drive_path)
                total_items = len(items)
                
                # 限制显示数量，避免界面卡顿
                display_limit = 150
                items = items[:display_limit]
                
                if total_items > display_limit:
                    limit_info = self.partition_file_tree.add_item(parent_item, 
                        f"📊 显示前 {display_limit} 项，共 {total_items} 项", "", "信息", "")
                
                folders = []
                files = []
                inaccessible_items = []
                
                for item in items:
                    item_path = os.path.join(drive_path, item)
                    try:
                        if os.path.isdir(item_path):
                            folders.append(item)
                        else:
                            try:
                                size = os.path.getsize(item_path)
                                size_str = self._format_file_size(size)
                                files.append((item, size_str, item_path))
                            except (PermissionError, OSError):
                                # 文件存在但无法获取大小，仍然添加但标记为无法访问
                                files.append((item, "无法访问", item_path))
                    except (PermissionError, OSError):
                        inaccessible_items.append(item)
                        continue
                
                # 添加统计信息
                stats_item = self.partition_file_tree.add_item(parent_item, 
                    f"📈 统计: {len(folders)} 个文件夹, {len(files)} 个文件", "", "统计", "")
                
                # 添加文件夹
                if folders:
                    folder_section = self.partition_file_tree.add_item(parent_item, "📁 文件夹", "", "分类", "")
                    for folder in sorted(folders):
                        folder_path = os.path.join(drive_path, folder)
                        folder_item = self.partition_file_tree.add_item(folder_section, f"📁 {folder}", "", "文件夹", "",
                                                                       {"path": folder_path, "type": "directory", "is_directory": True})
                        
                        # 为文件夹添加子项（限制深度）
                        try:
                            self._add_folder_contents(folder_item, folder_path, max_depth=2, current_depth=0)
                        except Exception as e:
                            error_item = self.partition_file_tree.add_item(folder_item, f"❌ 无法读取子目录: {str(e)[:30]}", "", "错误", "")
                
                # 添加文件
                if files:
                    file_section = self.partition_file_tree.add_item(parent_item, "📄 文件", "", "分类", "")
                    for file_name, size_str, file_path in sorted(files):
                        file_item = self.partition_file_tree.add_item(file_section, f"📄 {file_name}", size_str, "文件", "",
                                                                     {"path": file_path, "type": "file", "is_directory": False})
                
                # 添加无法访问的项目
                if inaccessible_items:
                    error_section = self.partition_file_tree.add_item(parent_item, "🔒 无法访问的项目", "", "分类", "")
                    for item in inaccessible_items:
                        error_item = self.partition_file_tree.add_item(error_section, f"🔒 {item} (权限不足)", "", "错误", "")
                
                # 如果没有找到任何项目
                if not folders and not files and not inaccessible_items:
                    empty_item = self.partition_file_tree.add_item(parent_item, "📂 目录为空", "", "信息", "")
                
            except PermissionError:
                error_item = self.partition_file_tree.add_item(parent_item, "🔒 权限不足，无法访问此驱动器", "", "错误", "")
                # 提供解决建议
                suggestion_item = self.partition_file_tree.add_item(parent_item, "💡 请以管理员身份运行程序", "", "建议", "")
            except Exception as e:
                error_item = self.partition_file_tree.add_item(parent_item, f"❌ 读取错误: {str(e)[:50]}", "", "错误", "")
                
        except Exception as e:
            error_item = self.partition_file_tree.add_item(parent_item, f"❌ 扫描文件系统失败: {str(e)}", "", "错误", "")
    
    def _add_folder_contents(self, parent_item, folder_path, max_depth=2, current_depth=0):
        """递归添加文件夹内容"""
        if current_depth >= max_depth:
            # 如果达到最大深度，添加一个提示项
            hint_item = self.partition_file_tree.add_item(parent_item, "📂 双击展开更多内容...", "", "提示", "",
                                                         {"path": folder_path, "type": "expandable", "is_directory": True})
            return
            
        try:
            # 检查文件夹是否可访问
            if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
                error_item = self.partition_file_tree.add_item(parent_item, "❌ 文件夹不存在或无法访问", "", "错误", "")
                return
                
            items = os.listdir(folder_path)
            total_items = len(items)
            
            # 限制每个文件夹显示的项目数
            display_limit = 50
            items = items[:display_limit]
            
            if total_items > display_limit:
                limit_info = self.partition_file_tree.add_item(parent_item, 
                    f"📊 显示前 {display_limit} 项，共 {total_items} 项", "", "信息", "")
            
            folders = []
            files = []
            inaccessible_items = []
            
            for item in items:
                item_path = os.path.join(folder_path, item)
                try:
                    if os.path.isdir(item_path):
                        folders.append((item, item_path))
                    else:
                        try:
                            size = os.path.getsize(item_path)
                            size_str = self._format_file_size(size)
                            files.append((item, size_str, item_path))
                        except (PermissionError, OSError):
                            # 文件存在但无法获取大小
                            files.append((item, "无法访问", item_path))
                except (PermissionError, OSError):
                    inaccessible_items.append(item)
                    continue
            
            # 添加文件夹
            if folders:
                folder_display_limit = 15
                for folder_name, folder_full_path in sorted(folders)[:folder_display_limit]:
                    folder_item = self.partition_file_tree.add_item(parent_item, f"📁 {folder_name}", "", "文件夹", "",
                                                                   {"path": folder_full_path, "type": "directory", "is_directory": True})
                    if current_depth < max_depth - 1:
                        try:
                            self._add_folder_contents(folder_item, folder_full_path, max_depth, current_depth + 1)
                        except Exception as e:
                            error_item = self.partition_file_tree.add_item(folder_item, f"❌ 子目录错误: {str(e)[:20]}", "", "错误", "")
                
                # 如果有更多文件夹未显示
                if len(folders) > folder_display_limit:
                    more_folders_item = self.partition_file_tree.add_item(parent_item, 
                        f"📁 ... 还有 {len(folders) - folder_display_limit} 个文件夹", "", "信息", "")
            
            # 添加文件
            if files:
                file_display_limit = 20
                for file_name, size_str, file_path in sorted(files)[:file_display_limit]:
                    file_item = self.partition_file_tree.add_item(parent_item, f"📄 {file_name}", size_str, "文件", "",
                                                                 {"path": file_path, "type": "file", "is_directory": False})
                
                # 如果有更多文件未显示
                if len(files) > file_display_limit:
                    more_files_item = self.partition_file_tree.add_item(parent_item, 
                        f"📄 ... 还有 {len(files) - file_display_limit} 个文件", "", "信息", "")
            
            # 添加无法访问的项目
            if inaccessible_items:
                error_display_limit = 5
                for item in inaccessible_items[:error_display_limit]:
                    error_item = self.partition_file_tree.add_item(parent_item, f"🔒 {item} (权限不足)", "", "错误", "")
                
                if len(inaccessible_items) > error_display_limit:
                    more_inaccessible_item = self.partition_file_tree.add_item(parent_item, 
                        f"🔒 ... 还有 {len(inaccessible_items) - error_display_limit} 个无法访问的项目", "", "信息", "")
            
            # 如果文件夹为空
            if not folders and not files and not inaccessible_items:
                empty_item = self.partition_file_tree.add_item(parent_item, "📂 空文件夹", "", "信息", "")
                
        except PermissionError:
            error_item = self.partition_file_tree.add_item(parent_item, "🔒 权限不足，无法访问此文件夹", "", "错误", "")
        except Exception as e:
            error_item = self.partition_file_tree.add_item(parent_item, f"❌ 错误: {str(e)[:30]}", "", "错误", "")
    
    def _scan_all_available_drives(self, parent_item):
        """扫描所有可用的驱动器"""
        try:
            try:
                import win32api
            except ImportError as e:
                print(f"win32api模块导入失败: {e}")
                error_item = self.partition_file_tree.add_item(
                    parent_item, 
                    "⚠️ win32api模块未安装，无法扫描驱动器", 
                    "", "错误", ""
                )
                return
            import os
            
            # 获取所有逻辑驱动器
            drives = win32api.GetLogicalDriveStrings()
            drives = drives.split('\000')[:-1]
            
            if not drives:
                info_item = self.partition_file_tree.add_item(
                    parent_item, 
                    "⚠️ 未找到可用的驱动器", 
                    "", 
                    "信息", 
                    ""
                )
                return
            
            # 为每个驱动器创建节点
            for drive in drives:
                try:
                    # 检查驱动器是否可访问
                    if os.path.exists(drive):
                        # 获取驱动器类型和标签
                        try:
                            drive_type = win32api.GetDriveType(drive)
                            drive_types = {
                                0: "未知",
                                1: "无效路径", 
                                2: "软盘",
                                3: "硬盘",
                                4: "网络驱动器",
                                5: "光盘",
                                6: "RAM磁盘"
                            }
                            type_name = drive_types.get(drive_type, "未知")
                        except AttributeError:
                            type_name = "硬盘"  # 默认类型
                        except Exception:
                            type_name = "未知"
                        
                        # 尝试获取驱动器标签
                        try:
                            volume_info = win32api.GetVolumeInformation(drive)
                            label = volume_info[0] if volume_info[0] else "本地磁盘"
                        except AttributeError:
                            label = "本地磁盘"  # win32api没有GetVolumeInformation函数
                        except Exception:
                            label = "本地磁盘"
                        
                        # 创建驱动器节点
                        drive_name = f"💾 {drive} ({label}) - {type_name}"
                        drive_item = self.partition_file_tree.add_item(
                            parent_item, 
                            drive_name, 
                            "", 
                            "驱动器", 
                            ""
                        )
                        
                        # 扫描驱动器内容
                        self._scan_real_filesystem(drive_item, drive)
                        
                except Exception as drive_error:
                    error_item = self.partition_file_tree.add_item(
                        parent_item, 
                        f"❌ 驱动器 {drive} 访问失败: {str(drive_error)[:30]}", 
                        "", 
                        "错误", 
                        ""
                    )
                    continue
            
        except Exception as e:
            error_item = self.partition_file_tree.add_item(
                parent_item, 
                f"扫描驱动器失败: {str(e)[:50]}", 
                "", 
                "错误", 
                ""
            )
    
    def _scan_raw_filesystem(self, parent_item, partition_info, disk_manager):
        """通过原始磁盘访问扫描文件系统（备用方法）"""
        try:
            # 检查当前权限状态
            import ctypes
            is_admin = False
            try:
                is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            except:
                pass
            
            if is_admin:
                # 已有管理员权限，但仍无法通过驱动器号访问分区
                info_item = self.partition_file_tree.add_item(
                    parent_item, 
                    "⚠️ 分区未分配驱动器号或文件系统损坏", 
                    "", 
                    "信息", 
                    ""
                )
                
                # 提供可能的解决方案
                solution_item = self.partition_file_tree.add_item(
                    parent_item, 
                    "💡 可能的解决方案:", 
                    "", 
                    "提示", 
                    ""
                )
                
                self.partition_file_tree.add_item(
                    solution_item, 
                    "• 使用磁盘管理工具分配驱动器号", 
                    "", 
                    "建议", 
                    ""
                )
                
                self.partition_file_tree.add_item(
                    solution_item, 
                    "• 使用文件恢复功能恢复文件", 
                    "", 
                    "建议", 
                    ""
                )
                
                self.partition_file_tree.add_item(
                    solution_item, 
                    "• 检查分区是否损坏", 
                    "", 
                    "建议", 
                    ""
                )
                
                # 尝试读取原始分区数据
                try:
                    self._try_raw_partition_access(parent_item, partition_info)
                except Exception as raw_error:
                    error_item = self.partition_file_tree.add_item(
                        parent_item, 
                        f"📁 原始访问失败: {str(raw_error)[:50]}", 
                        "", 
                        "错误", 
                        ""
                    )
            else:
                # 没有管理员权限
                info_item = self.partition_file_tree.add_item(
                    parent_item, 
                    "🔒 需要管理员权限访问此分区", 
                    "", 
                    "信息", 
                    ""
                )
                
                help_item = self.partition_file_tree.add_item(
                    parent_item, 
                    "💡 请右键点击程序图标，选择'以管理员身份运行'", 
                    "", 
                    "提示", 
                    ""
                )
                
                restart_item = self.partition_file_tree.add_item(
                    parent_item, 
                    "🔄 或者重新启动程序并选择管理员权限", 
                    "", 
                    "提示", 
                    ""
                )
            
        except Exception as e:
            error_item = self.partition_file_tree.add_item(
                parent_item, 
                f"分区访问检查失败: {str(e)[:50]}", 
                "", 
                "错误", 
                ""
            )
    
    def _try_raw_partition_access(self, parent_item, partition_info):
        """尝试原始分区访问"""
        try:
            # 添加说明项
            info_item = self.partition_file_tree.add_item(
                parent_item, 
                "📋 尝试读取分区引导扇区...", 
                "", 
                "信息", 
                ""
            )
            
            # 这里可以添加更复杂的原始文件系统读取逻辑
            # 例如读取FAT32、NTFS等文件系统的目录结构
            
            # 暂时添加一个提示项
            note_item = self.partition_file_tree.add_item(
                parent_item, 
                "🔧 原始文件系统读取功能开发中", 
                "", 
                "提示", 
                ""
            )
            
        except Exception as e:
            raise Exception(f"原始分区访问失败: {str(e)}")
    
    def _format_file_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
       
    def _load_file_to_hex_viewer(self, file_path):
        """将文件内容加载到十六进制查看器"""
        try:
            import os
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                QMessageBox.warning(self, "错误", f"文件不存在: {file_path}")
                return
            
            # 检查是否为文件（而不是目录）
            if not os.path.isfile(file_path):
                QMessageBox.warning(self, "错误", f"路径不是文件: {file_path}")
                return
            
            # 获取文件大小
            try:
                file_size = os.path.getsize(file_path)
            except (PermissionError, OSError) as e:
                QMessageBox.warning(self, "权限错误", f"无法获取文件大小: {str(e)}\n\n请检查文件权限或以管理员身份运行程序。")
                return
            
            # 检查文件大小
            max_size = 10 * 1024 * 1024  # 10MB限制
            if file_size > max_size:
                reply = QMessageBox.question(
                    self, 
                    "文件过大", 
                    f"文件大小为 {file_size / (1024*1024):.1f} MB，超过 {max_size / (1024*1024):.0f} MB 限制。\n\n是否只读取前 {max_size / (1024*1024):.0f} MB？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes
                )
                if reply != QMessageBox.Yes:
                    return
                read_size = max_size
            else:
                read_size = file_size
            
            # 读取文件内容
            try:
                with open(file_path, 'rb') as f:
                    data = f.read(read_size)
            except PermissionError:
                QMessageBox.warning(self, "权限错误", f"权限不足，无法读取文件: {file_path}\n\n请检查文件权限或以管理员身份运行程序。")
                return
            except OSError as e:
                QMessageBox.warning(self, "读取错误", f"读取文件时发生错误: {str(e)}")
                return
            
            # 设置十六进制查看器数据
            self.hex_viewer.set_data(data)
            
            # 切换到十六进制查看器选项卡
            self.tabs.setCurrentIndex(0)
            
            # 更新状态栏
            file_name = os.path.basename(file_path)
            if len(data) < file_size:
                self.status_bar.set_status(f"已加载文件: {file_name} ({len(data)} / {file_size} 字节，部分加载)")
            else:
                self.status_bar.set_status(f"已加载文件: {file_name} ({len(data)} 字节)")
            
        except Exception as e:
            QMessageBox.critical(self, "未知错误", f"加载文件时发生未知错误: {str(e)}")
            import traceback
            print(f"_load_file_to_hex_viewer error: {traceback.format_exc()}")
    
    def on_partition_file_double_clicked(self, item_data):
        """逻辑分区文件双击事件"""
        if not item_data:
            return
        
        try:
            # 如果是文件，在十六进制查看器中显示
            if not item_data.get('is_directory', True):
                file_path = item_data.get('path')
                
                if file_path and os.path.exists(file_path):
                    # 读取真实文件内容
                    self._load_file_to_hex_viewer(file_path)
                elif 'offset' in item_data:
                    # 如果有偏移量信息，从磁盘读取
                    disk_path = item_data.get('disk_path', self.current_disk['path'] if self.current_disk else None)
                    
                    if disk_path:
                        # 在十六进制查看器中显示文件内容
                        file_size = item_data.get('size', 1024)
                        self.hex_viewer.load_data_from_disk(disk_path, item_data['offset'], file_size)
                        self.tabs.setCurrentIndex(0)  # 切换到十六进制查看器选项卡
                        
                        # 更新状态栏
                        file_name = item_data.get('file_name', '未知文件')
                        self.status_bar.set_status(f"正在显示文件: {file_name}")
                    else:
                        QMessageBox.warning(self, "错误", "无法获取磁盘路径")
                else:
                    # 如果既没有有效的文件路径，也没有偏移量信息
                    file_name = item_data.get('file_name', '未知文件')
                    QMessageBox.warning(self, "错误", f"无法读取文件 '{file_name}'：文件路径无效且没有磁盘偏移量信息")
            elif item_data.get('is_directory', True):
                # 如果是文件夹，显示提示信息
                folder_name = item_data.get('file_name', '文件夹')
                self.status_bar.set_status(f"已选择文件夹: {folder_name}")
        
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开文件失败: {str(e)}")
    
    def on_tree_item_clicked(self, item_data):
        """文件树项目单击事件 - 用于选择分区并更新文件树"""
        if item_data and item_data.get('type') == 'dbr' and 'partition_info' in item_data:
            # 选择了分区，更新当前选择的分区信息
            self.current_partition = item_data['partition_info']
            # 重新加载分区文件树，显示选中分区的文件
            self.load_partition_file_tree_for_partition(item_data['partition_info'])
            
            # 更新状态栏
            partition_info = item_data['partition_info']
            part_type = partition_info.get('type_name', '未知')
            part_size = partition_info.get('size_human', '未知大小')
            self.status_bar.set_status(f"已选择分区: {part_type} ({part_size}) - 正在加载文件树...")
        elif item_data and item_data.get('type') == 'partition' and 'partition_info' in item_data:
            # 处理其他类型的分区项目
            self.current_partition = item_data['partition_info']
            self.load_partition_file_tree_for_partition(item_data['partition_info'])
            
            partition_info = item_data['partition_info']
            part_type = partition_info.get('type_name', '未知')
            part_size = partition_info.get('size_human', '未知大小')
            self.status_bar.set_status(f"已选择分区: {part_type} ({part_size}) - 正在加载文件树...")
    
    def on_tree_item_double_clicked(self, item_data):
        """文件树项目双击事件"""
        if item_data and 'offset' in item_data:
            # 获取磁盘路径，优先使用item_data中的disk_path，否则使用当前磁盘路径
            disk_path = item_data.get('disk_path', self.current_disk['path'] if self.current_disk else None)
            
            if disk_path:
                # 在十六进制查看器中显示
                self.hex_viewer.load_data_from_disk(disk_path, item_data['offset'])
                self.tabs.setCurrentIndex(0)  # 切换到十六进制查看器选项卡
                
                # 显示项目信息
                if item_data.get('type') == 'mbr':
                    self.status_bar.set_status("正在显示主引导记录 (MBR)")
                elif item_data.get('type') == 'dbr':
                    partition_info = item_data.get('partition_info', {})
                    part_type = partition_info.get('type_name', '未知')
                    self.status_bar.set_status(f"正在显示分区引导记录 (DBR) - {part_type}")
            else:
                QMessageBox.warning(self, "错误", "无法获取磁盘路径")
    
    def browse_physical_disk(self):
        """浏览物理磁盘"""
        if not self.current_disk:
            QMessageBox.warning(self, "警告", "请先选择一个磁盘")
            return
        
        try:
            self.hex_viewer.load_data_from_disk(self.current_disk['path'], 0)
            self.tabs.setCurrentIndex(0)
            self.status_bar.set_status("正在浏览物理磁盘")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法浏览物理磁盘: {str(e)}")
    
    def browse_partition(self):
        """浏览分区"""
        if not self.current_disk:
            QMessageBox.warning(self, "警告", "请先选择一个磁盘")
            return
        
        try:
            from disk_utils import DiskManager
            
            # 获取磁盘分区信息
            disk_manager = DiskManager()
            disk_info = disk_manager.get_disk_info(self.current_disk['path'])
            
            # 检查是否有错误信息
            if 'error' in disk_info:
                QMessageBox.critical(self, "错误", f"获取磁盘信息失败: {disk_info['error']}")
                return
            
            if 'partitions' not in disk_info or not disk_info['partitions']:
                # 提供更详细的信息
                error_msg = "该磁盘没有发现分区。\n\n可能的原因:\n"
                error_msg += "• 磁盘未初始化\n"
                error_msg += "• 磁盘使用GPT分区表（当前仅支持MBR）\n"
                error_msg += "• 磁盘损坏或无法访问\n"
                error_msg += "• 需要管理员权限访问\n\n"
                
                if 'partition_error' in disk_info:
                    error_msg += f"详细错误: {disk_info['partition_error']}"
                
                QMessageBox.information(self, "信息", error_msg)
                return
            
            # 创建分区选择对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("选择分区")
            dialog.setModal(True)
            dialog.resize(600, 400)
            
            layout = QVBoxLayout(dialog)
            
            # 添加磁盘信息标签
            disk_info_text = f"磁盘: {self.current_disk['name']}\n"
            disk_info_text += f"路径: {self.current_disk['path']}\n"
            disk_info_text += f"大小: {self.current_disk.get('size_human', '未知')}"
            disk_info_label = QLabel(disk_info_text)
            disk_info_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc; }")
            layout.addWidget(disk_info_label)
            
            # 添加说明标签
            info_label = QLabel("请选择要浏览的分区:")
            layout.addWidget(info_label)
            
            # 创建分区列表
            partition_list = QListWidget()
            
            valid_partitions = 0
            for i, partition in enumerate(disk_info['partitions']):
                if partition['type'] != 0:  # 跳过空分区
                    valid_partitions += 1
                    status_indicator = "🟢" if partition.get('status', '').lower() == 'active' else "🔴"
                    item_text = f"{status_indicator} 分区 {i+1}: {partition['type_name']} ({partition['size_human']})"
                    item_text += f" - 起始扇区: {partition['start_lba']}, 扇区数: {partition['sectors']}"
                    item_text += f" - 状态: {partition.get('status', '未知')}"
                    
                    list_item = QListWidgetItem(item_text)
                    list_item.setData(Qt.UserRole, partition)
                    partition_list.addItem(list_item)
            
            if partition_list.count() == 0:
                error_msg = "没有找到有效的分区。\n\n"
                error_msg += f"磁盘共有 {len(disk_info['partitions'])} 个分区表项，但都是空分区。\n\n"
                error_msg += "可能的原因:\n"
                error_msg += "• 磁盘分区表损坏\n"
                error_msg += "• 分区被删除但未重新分区\n"
                error_msg += "• 使用了不支持的分区格式\n"
                QMessageBox.information(self, "信息", error_msg)
                return
            
            layout.addWidget(partition_list)
            
            # 添加按钮
            button_layout = QHBoxLayout()
            
            browse_button = QPushButton("浏览分区")
            browse_button.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 5px;
                    font-family: "Microsoft YaHei", "SimHei", "黑体";
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 80px;
                    min-height: 30px;
                }
                QPushButton:hover {
                    background-color: #2980b9;
                }
                QPushButton:pressed {
                    background-color: #21618c;
                }
            """)
            
            wipe_button = QPushButton("擦除分区")
            wipe_button.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 5px;
                    font-family: "Microsoft YaHei", "SimHei", "黑体";
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 80px;
                    min-height: 30px;
                }
                QPushButton:hover {
                    background-color: #c0392b;
                }
                QPushButton:pressed {
                    background-color: #a93226;
                }
            """)
            
            cancel_button = QPushButton("取消")
            cancel_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 5px;
                    font-family: "Microsoft YaHei", "SimHei", "黑体";
                    font-weight: bold;
                    font-size: 14px;
                    min-width: 80px;
                    min-height: 30px;
                }
                QPushButton:hover {
                    background-color: #7f8c8d;
                }
                QPushButton:pressed {
                    background-color: #6c7b7d;
                }
            """)
            
            button_layout.addWidget(browse_button)
            button_layout.addWidget(wipe_button)
            button_layout.addWidget(cancel_button)
            layout.addLayout(button_layout)
            
            # 连接信号
            def on_browse_clicked():
                current_item = partition_list.currentItem()
                if current_item:
                    partition = current_item.data(Qt.UserRole)
                    
                    # 检查分区状态
                    if partition.get('status', '').lower() == 'inactive':
                        reply = QMessageBox.question(
                            dialog, 
                            "分区状态警告", 
                            f"选择的分区状态为 'Inactive'，这可能意味着：\n\n"
                            f"• 分区未被标记为活动分区\n"
                            f"• 分区可能无法正常启动\n"
                            f"• 分区数据可能不完整\n\n"
                            f"是否仍要继续浏览此分区？",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No
                        )
                        if reply == QMessageBox.No:
                            return
                    
                    self.browse_selected_partition(partition)
                    dialog.accept()
                else:
                    QMessageBox.warning(dialog, "警告", "请选择一个分区")
            
            def on_wipe_clicked():
                current_item = partition_list.currentItem()
                if current_item:
                    partition = current_item.data(Qt.UserRole)
                    
                    # 显示严重警告
                    warning_msg = f"⚠️ 危险操作警告 ⚠️\n\n"
                    warning_msg += f"您即将擦除以下分区的所有数据：\n\n"
                    warning_msg += f"分区: {partition['type_name']}\n"
                    warning_msg += f"大小: {partition['size_human']}\n"
                    warning_msg += f"起始扇区: {partition['start_lba']}\n"
                    warning_msg += f"扇区数: {partition['sectors']}\n\n"
                    warning_msg += f"此操作将：\n"
                    warning_msg += f"• 永久删除分区内的所有文件和数据\n"
                    warning_msg += f"• 无法撤销或恢复\n"
                    warning_msg += f"• 使分区无法启动\n\n"
                    warning_msg += f"请确保您已备份重要数据！\n\n"
                    warning_msg += f"确定要继续吗？"
                    
                    reply = QMessageBox.question(
                        dialog,
                        "确认擦除分区",
                        warning_msg,
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    
                    if reply == QMessageBox.Yes:
                        # 二次确认
                        confirm_msg = f"最后确认：\n\n"
                        confirm_msg += f"您确定要擦除分区 {partition['type_name']} ({partition['size_human']}) 吗？\n\n"
                        confirm_msg += f"输入 'WIPE' 来确认此操作："
                        
                        text, ok = QInputDialog.getText(
                            dialog, 
                            "最终确认", 
                            confirm_msg
                        )
                        
                        if ok and text.upper() == 'WIPE':
                            dialog.accept()
                            self.wipe_selected_partition(partition)
                        elif ok:
                            QMessageBox.information(dialog, "取消", "确认文本不正确，操作已取消")
                else:
                    QMessageBox.warning(dialog, "警告", "请选择一个分区")
            
            browse_button.clicked.connect(on_browse_clicked)
            wipe_button.clicked.connect(on_wipe_clicked)
            cancel_button.clicked.connect(dialog.reject)
            
            # 双击也可以浏览
            def on_item_double_clicked(item):
                partition = item.data(Qt.UserRole)
                
                # 检查分区状态
                if partition.get('status', '').lower() == 'inactive':
                    reply = QMessageBox.question(
                        dialog, 
                        "分区状态警告", 
                        f"选择的分区状态为 'Inactive'，这可能意味着：\n\n"
                        f"• 分区未被标记为活动分区\n"
                        f"• 分区可能无法正常启动\n"
                        f"• 分区数据可能不完整\n\n"
                        f"是否仍要继续浏览此分区？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        return
                
                self.browse_selected_partition(partition)
                dialog.accept()
            
            partition_list.itemDoubleClicked.connect(on_item_double_clicked)
            
            # 显示对话框
            dialog.exec_()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"浏览分区失败: {str(e)}")
    
    def browse_selected_partition(self, partition):
        """浏览选定的分区"""
        try:
            # 计算分区起始偏移量
            partition_offset = partition['start_lba'] * 512
            
            # 显示加载状态
            self.status_bar.set_status(f"正在加载分区数据: {partition['type_name']}...")
            
            # 检查分区大小是否合理
            if partition['sectors'] == 0:
                QMessageBox.warning(self, "警告", "分区大小为0，可能是无效分区")
                return
            
            if partition['start_lba'] == 0:
                reply = QMessageBox.question(
                    self, 
                    "分区位置警告", 
                    "分区起始扇区为0，这通常是MBR位置。\n\n"
                    "继续可能会显示主引导记录而不是分区数据。\n\n"
                    "是否继续？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.No:
                    return
            
            # 在十六进制查看器中显示分区引导扇区
            self.hex_viewer.load_data_from_disk(self.current_disk['path'], partition_offset)
            self.tabs.setCurrentIndex(0)  # 切换到十六进制查看器选项卡
            
            # 更新状态栏
            status_msg = f"浏览分区: {partition['type_name']} (起始扇区: {partition['start_lba']}, 状态: {partition.get('status', '未知')})"
            self.status_bar.set_status(status_msg)
            
            # 尝试读取分区文件系统信息
            self.load_partition_filesystem(partition)
            
        except Exception as e:
            error_msg = f"浏览分区失败: {str(e)}\n\n"
            error_msg += "可能的原因:\n"
            error_msg += "• 磁盘访问权限不足\n"
            error_msg += "• 分区数据损坏\n"
            error_msg += "• 磁盘硬件故障\n"
            error_msg += "• 分区表信息错误\n"
            QMessageBox.critical(self, "错误", error_msg)
            self.status_bar.set_status("分区浏览失败")
    
    def wipe_selected_partition(self, partition):
        """擦除选定的分区"""
        try:
            # 计算分区起始偏移量和大小
            partition_offset = partition['start_lba'] * 512
            partition_size = partition['sectors'] * 512
            
            # 创建分区擦除工作线程
            self.start_partition_wipe_worker(
                self.current_disk['path'], 
                partition_offset, 
                partition_size,
                partition['type_name']
            )
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"擦除分区失败: {str(e)}")
    
    def start_partition_wipe_worker(self, disk_path, offset, size, partition_name):
        """启动分区擦除工作线程"""
        if self.current_worker:
            QMessageBox.warning(self, "警告", "已有任务正在运行")
            return
        
        # 显示进度对话框
        self.progress_dialog = ProgressDialog("分区擦除", f"正在擦除分区: {partition_name}...", self)
        self.progress_dialog.show()
        
        # 创建分区擦除工作线程
        self.current_worker = PartitionWipeWorker(disk_path, offset, size)
        self.current_worker.progress_updated.connect(self.progress_dialog.set_progress)
        self.current_worker.status_updated.connect(self.progress_dialog.set_detail)
        self.current_worker.error_occurred.connect(self.on_worker_error)
        self.current_worker.finished.connect(self.on_wipe_finished)
        self.current_worker.start()
    
    def load_partition_filesystem(self, partition):
        """加载分区文件系统信息"""
        try:
            from file_system_reader import FileSystemReader
            
            # 检测文件系统类型
            fs_info = FileSystemReader.detect_filesystem(self.current_disk['path'], partition['start_lba'])
            
            # 构建详细的分区信息
            info_text = f"分区详细信息:\n\n"
            info_text += f"分区索引: {partition.get('index', '未知')}\n"
            info_text += f"分区类型: {partition['type_name']} (0x{partition['type']:02X})\n"
            info_text += f"分区状态: {partition.get('status', '未知')}\n"
            info_text += f"起始扇区: {partition['start_lba']}\n"
            info_text += f"扇区数: {partition['sectors']}\n"
            info_text += f"分区大小: {partition['size_human']}\n"
            info_text += f"起始偏移: 0x{partition['start_lba'] * 512:08X}\n\n"
            
            if fs_info:
                info_text += f"文件系统检测结果:\n"
                info_text += f"文件系统类型: {fs_info.get('filesystem', '未知')}\n\n"
                
                # 添加文件系统特定信息
                for key, value in fs_info.items():
                    if key not in ['filesystem']:
                        info_text += f"{key}: {value}\n"
            else:
                info_text += "文件系统检测结果:\n"
                info_text += "无法识别文件系统类型\n"
                info_text += "可能的原因:\n"
                info_text += "• 分区未格式化\n"
                info_text += "• 文件系统损坏\n"
                info_text += "• 不支持的文件系统类型\n"
                info_text += "• 分区引导扇区损坏\n"
            
            self.disk_info_panel.set_info(info_text)
            
        except Exception as e:
            error_info = f"分区基本信息:\n\n"
            error_info += f"分区类型: {partition['type_name']}\n"
            error_info += f"起始扇区: {partition['start_lba']}\n"
            error_info += f"扇区数: {partition['sectors']}\n"
            error_info += f"分区大小: {partition['size_human']}\n\n"
            error_info += f"文件系统检测失败: {str(e)}\n"
            self.disk_info_panel.set_info(error_info)
            print(f"加载分区文件系统信息失败: {str(e)}")
    
    def recover_files_by_signature(self):
        """通过文件签名恢复文件"""
        if not self.current_disk:
            QMessageBox.warning(self, "警告", "请先选择一个磁盘")
            return
        
        # 选择恢复方式
        recovery_method = self._show_recovery_method_dialog()
        if not recovery_method:
            return
        
        # 选择输出目录
        output_dir = QFileDialog.getExistingDirectory(self, "选择恢复文件保存目录")
        if not output_dir:
            return
        
        # 文件类型选择对话框
        selected_types = self._show_file_type_dialog()
        
        if not selected_types:
            return
        
        self.start_recovery_worker(recovery_method, self.current_disk['path'], output_dir, file_types=selected_types)
    
    def recover_fat32(self):
        """恢复FAT32文件系统"""
        # 初始化磁盘路径变量
        disk_path = None
        
        # 获取磁盘路径
        if self.current_disk:
            disk_path = self.current_disk['path']
        else:
            # 如果没有选中磁盘，提供输入逻辑驱动器的选项
            from PyQt5.QtWidgets import QInputDialog
            
            drive_letter, ok = QInputDialog.getText(
                self, 
                "输入逻辑驱动器", 
                "请输入要恢复的逻辑驱动器（如: F、F:、F:\\）:\n\n" +
                "提示：\n" +
                "- 支持格式：F、F:、F:\\\n" +
                "- 程序会自动检测驱动器是否存在\n" +
                "- 需要管理员权限才能访问驱动器"
            )
            
            if not ok or not drive_letter.strip():
                return
            
            disk_path = drive_letter.strip()
            
            # 验证输入格式
            if not self._validate_drive_input(disk_path):
                QMessageBox.warning(
                    self, 
                    "输入错误", 
                    "无效的驱动器格式！\n\n" +
                    "支持的格式：\n" +
                    "- F（单个字母）\n" +
                    "- F:（字母加冒号）\n" +
                    "- F:\\（完整路径）"
                )
                return
        
        # 检查disk_path是否有效
        if not disk_path:
            QMessageBox.warning(self, "错误", "无法获取有效的磁盘路径")
            return
        
        # 显示FAT32恢复方式选择对话框
        recovery_method = self._show_fat32_recovery_method_dialog()
        if not recovery_method:
            return
        
        output_dir = QFileDialog.getExistingDirectory(self, "选择恢复文件保存目录")
        if not output_dir:
            return
        
        # 根据选择的方法启动恢复
        if recovery_method == 'image':
            self.start_recovery_worker('fat32', disk_path, output_dir, use_disk_image=True)
        else:
            self.start_recovery_worker('fat32', disk_path, output_dir, use_disk_image=False)
    
    def recover_ntfs(self):
        """恢复NTFS文件系统"""
        # 初始化磁盘路径变量
        disk_path = None
        
        # 获取磁盘路径
        if self.current_disk:
            disk_path = self.current_disk['path']
        else:
            # 如果没有选中磁盘，提供输入逻辑驱动器的选项
            from PyQt5.QtWidgets import QInputDialog
            
            drive_letter, ok = QInputDialog.getText(
                self, 
                "输入逻辑驱动器", 
                "请输入要恢复的逻辑驱动器（如: F、F:、F:\\）:\n\n" +
                "提示：\n" +
                "- 支持格式：F、F:、F:\\\n" +
                "- 程序会自动检测驱动器是否存在\n" +
                "- 需要管理员权限才能访问驱动器"
            )
            
            if not ok or not drive_letter.strip():
                return
            
            disk_path = drive_letter.strip()
            
            # 验证输入格式
            if not self._validate_drive_input(disk_path):
                QMessageBox.warning(
                    self, 
                    "输入错误", 
                    "无效的驱动器格式！\n\n" +
                    "支持的格式：\n" +
                    "- F（单个字母）\n" +
                    "- F:（字母加冒号）\n" +
                    "- F:\\（完整路径）"
                )
                return
        
        # 检查disk_path是否有效
        if not disk_path:
            QMessageBox.warning(self, "错误", "无法获取有效的磁盘路径")
            return
        
        output_dir = QFileDialog.getExistingDirectory(self, "选择恢复文件保存目录")
        if not output_dir:
            return
        
        self.start_recovery_worker('ntfs', disk_path, output_dir)
    
    def _validate_drive_input(self, drive_input):
        """验证驱动器输入格式"""
        import re
        
        # 移除空白字符
        drive_input = drive_input.strip()
        
        if not drive_input:
            return False
        
        # 支持的格式：
        # 1. 单个字母：F
        # 2. 字母加冒号：F:
        # 3. 完整路径：F:\
        patterns = [
            r'^[A-Za-z]$',           # F
            r'^[A-Za-z]:$',          # F:
            r'^[A-Za-z]:\\?$'        # F:\ 或 F:\\
        ]
        
        for pattern in patterns:
            if re.match(pattern, drive_input):
                return True
        
        return False
    
    def start_recovery_worker(self, recovery_type, disk_path, output_dir, **kwargs):
        """启动恢复工作线程"""
        if self.current_worker:
            QMessageBox.warning(self, "警告", "已有任务正在运行")
            return
        
        try:
            # 验证参数
            if not recovery_type:
                QMessageBox.warning(self, "错误", "恢复类型不能为空")
                return
            if not disk_path:
                QMessageBox.warning(self, "错误", "磁盘路径不能为空")
                return
            if not output_dir:
                QMessageBox.warning(self, "错误", "输出目录不能为空")
                return
            
            self.status_bar.set_status(f"正在启动{recovery_type}恢复...")
            
            # 创建进度对话框
            self.progress_dialog = ProgressDialog("文件恢复", "正在恢复文件...", self)
            self.progress_dialog.show()
            
            # 创建恢复工作线程
            self.current_worker = RecoveryWorker(recovery_type, disk_path, output_dir, **kwargs)
            self.current_worker.progress_updated.connect(self.progress_dialog.progress_bar.setValue)
            self.current_worker.status_updated.connect(self.progress_dialog.detail_label.setText)
            self.current_worker.error_occurred.connect(self.on_worker_error)
            self.current_worker.finished.connect(self.on_recovery_finished)
            
            # 启动工作线程
            self.current_worker.start()
            self.status_bar.set_status(f"{recovery_type}恢复已启动")
            
        except Exception as e:
            QMessageBox.critical(self, "启动错误", f"启动恢复工作线程失败: {str(e)}")
            self.status_bar.set_status(f"启动{recovery_type}恢复失败")
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()
    
    def on_recovery_finished(self):
        """恢复完成"""
        try:
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()
            
            # 清理工作线程
            if self.current_worker:
                self.current_worker = None
            self.status_bar.hide_progress()
            
            # 使用QTimer延迟显示完成信息，避免事件循环问题
            QTimer.singleShot(100, lambda: self._show_completion_message())
            self.status_bar.set_status("文件恢复完成")
            
        except Exception as e:
            # 如果完成处理出错，至少记录到状态栏
            self.status_bar.set_status(f"完成处理异常: {str(e)}")
            print(f"恢复完成处理异常: {e}")
    
    def _show_completion_message(self):
        """显示完成信息"""
        try:
            QMessageBox.information(self, "完成", "文件恢复完成！\n\n请检查输出目录中的恢复文件。")
        except Exception as e:
            print(f"显示完成信息异常: {e}")
            self.status_bar.set_status("恢复完成（信息显示异常）")
    
    def _show_wipe_completion_message(self):
        """显示擦除完成信息"""
        try:
            QMessageBox.information(self, "完成", "磁盘擦除完成！\n\n所选磁盘已安全擦除。")
        except Exception as e:
            print(f"显示擦除完成信息异常: {e}")
            self.status_bar.set_status("擦除完成（信息显示异常）")
    
    def _show_error_message(self, error_message):
        """显示错误信息"""
        try:
            QMessageBox.critical(self, "错误", f"操作失败:\n\n{error_message}")
        except Exception as e:
            print(f"显示错误信息异常: {e}")
            self.status_bar.set_status("操作失败（信息显示异常）")
      
    def open_virtual_disk(self):
        """打开虚拟磁盘文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "打开虚拟磁盘文件", "",
            "磁盘镜像文件 (*.vhd *.vmdk *.img);;所有文件 (*.*)"
        )
        
        if file_path:
            try:
                # 将虚拟磁盘添加到磁盘列表
                virtual_disk = {
                    'name': os.path.basename(file_path),
                    'path': file_path,
                    'size': os.path.getsize(file_path),
                    'size_human': self.format_size(os.path.getsize(file_path)),
                    'type': 'virtual'
                }
                
                display_text = f"{virtual_disk['name']} ({virtual_disk['size_human']}) [虚拟]"
                self.disk_combo.addItem(display_text, virtual_disk)
                self.disk_combo.setCurrentIndex(self.disk_combo.count() - 1)
                
                self.status_bar.set_status(f"已加载虚拟磁盘: {virtual_disk['name']}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法打开虚拟磁盘: {str(e)}")
    
    def wipe_disk(self):
        """擦除磁盘数据"""
        if not self.current_disk:
            QMessageBox.warning(self, "警告", "请先选择磁盘")
            return
        
        # 检查磁盘类型并给出相应提示
        disk_type = self.current_disk.get('type', 'physical')
        if disk_type == 'virtual':
            reply = QMessageBox.question(
                self, 
                "确认擦除虚拟磁盘", 
                f"您即将擦除虚拟磁盘文件:\n{self.current_disk['path']}\n\n此操作将永久删除虚拟磁盘中的所有数据，无法恢复。\n\n确定要继续吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        else:
            reply = QMessageBox.question(
                self, 
                "确认擦除物理磁盘", 
                f"您即将擦除物理磁盘:\n{self.current_disk['name']}\n\n此操作将永久删除磁盘中的所有数据，无法恢复。\n\n确定要继续吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            
        # 弹出数据擦除对话框
        dialog = DataWipeDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            method, passes = dialog.get_wipe_settings()
            
            # 将UI方法名映射到DataWipe类的方法名
            method_mapping = {
                'zero': 'zeros',
                'random': 'random',
                'dod': 'dod_5220_22_m',
                'dod_7pass': 'dod_7pass',
                'gutmann': 'gutmann'
            }
            
            actual_method = method_mapping.get(method, 'zeros')
            
            # 根据选择的方法确定默认擦除遍数
            if method == 'dod':
                passes = 3  # DoD标准固定3遍
            elif method == 'dod_7pass':
                passes = 7  # DoD 7遍方法固定7遍
            elif method == 'gutmann':
                passes = 35  # Gutmann方法固定35遍
            
            # 传递磁盘路径而不是整个磁盘对象
            self.start_wipe_worker(self.current_disk['path'], actual_method, passes)
    
    def wipe_partition(self):
        """擦除分区数据"""
        if not self.current_disk:
            QMessageBox.warning(self, "警告", "请先选择磁盘")
            return
            
        # 直接调用分区浏览功能，让用户选择要擦除的分区
        self.browse_partition()
    
    def start_wipe_worker(self, disk_path, method='zeros', passes=1):
        """启动擦除工作线程"""
        if self.current_worker:
            QMessageBox.warning(self, "警告", "已有任务正在运行")
            return
        
        # 显示进度对话框
        self.progress_dialog = ProgressDialog("数据擦除", "正在擦除磁盘数据...", self)
        self.progress_dialog.show()
        
        # 创建擦除工作线程 - 修正参数顺序：disk_path, passes, pattern
        self.current_worker = WipeWorker(disk_path, passes, method)
        self.current_worker.progress_updated.connect(self.progress_dialog.set_progress)
        self.current_worker.status_updated.connect(self.progress_dialog.set_detail)
        self.current_worker.error_occurred.connect(self.on_worker_error)
        self.current_worker.finished.connect(self.on_wipe_finished)
        self.current_worker.start()
    
    def on_wipe_finished(self):
        """擦除完成"""
        try:
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()
            
            # 清理工作线程
            if self.current_worker:
                self.current_worker = None
            self.status_bar.hide_progress()
            
            # 使用QTimer延迟显示完成信息，避免事件循环问题
            QTimer.singleShot(100, lambda: self._show_wipe_completion_message())
            self.status_bar.set_status("磁盘擦除完成")
            
        except Exception as e:
            self.status_bar.set_status(f"擦除完成处理异常: {str(e)}")
            print(f"擦除完成处理异常: {e}")
    
    def on_worker_error(self, error_message):
        """工作线程错误处理"""
        import traceback
        
        try:
            # 记录详细错误信息
            print(f"工作线程错误 - 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}, 错误: {error_message}")
            traceback.print_exc()
            
            if hasattr(self, 'progress_dialog'):
                self.progress_dialog.close()
            
            # 清理工作线程
            if self.current_worker:
                self.current_worker = None
            self.status_bar.hide_progress()
            
            # 使用QTimer延迟显示错误信息，避免事件循环问题
            QTimer.singleShot(100, lambda: self._show_error_message(error_message))
            self.status_bar.set_status("操作失败")
            
        except Exception as e:
            # 如果错误处理本身出错，至少记录到状态栏
            self.status_bar.set_status(f"处理错误时发生异常: {str(e)}")
            print(f"错误处理异常: {e}")
    
    def on_worker_finished(self):
        """工作线程完成"""
        self.current_worker = None
        self.status_bar.hide_progress()
    
    def update_status(self):
        """更新状态信息"""
        if self.current_disk:
            self.status_bar.set_status(f"当前磁盘: {self.current_disk['name']}")
        else:
            self.status_bar.set_status("就绪")
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self, "关于磁盘恢复工具",
            "磁盘恢复工具 v1.0\n\n"
            "一个功能强大的磁盘数据恢复工具\n\n"
            "支持功能:\n"
            "• 物理磁盘和分区浏览\n"
            "• 文件签名恢复\n"
            "• FAT32/NTFS文件系统恢复\n"
            "• 十六进制数据查看\n"
            "• 安全数据擦除\n"
            "• 虚拟磁盘支持"
        )
    
    def format_size(self, size):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    
    def _show_recovery_method_dialog(self):
        """显示恢复方式选择对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QRadioButton, QLabel, QFrame
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFont
        
        dialog = QDialog(self)
        dialog.setWindowTitle("选择恢复方式")
        dialog.setFixedSize(500, 350)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        # 设置对话框样式
        dialog.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                font-family: 'Microsoft YaHei', 'SimHei', sans-serif;
            }
            QLabel {
                color: #2c3e50;
                font-size: 14px;
            }
            QRadioButton {
                font-size: 13px;
                color: #2c3e50;
                spacing: 8px;
                padding: 8px;
                background-color: transparent;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid #95a5a6;
                background-color: #ffffff;
            }
            QRadioButton::indicator:checked {
                background-color: #3498db;
                border-color: #3498db;
            }
            QRadioButton::indicator:hover {
                border-color: #3498db;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-weight: bold;
                font-size: 14px;
                min-width: 80px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
            QPushButton#cancelButton {
                background-color: #95a5a6;
            }
            QPushButton#cancelButton:hover {
                background-color: #7f8c8d;
            }
        """)
        
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel("请选择文件签名恢复方式：")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 10px;
                padding: 8px 0px;
            }
        """)
        main_layout.addWidget(title_label)
        
        # 磁盘镜像快照恢复选项
        image_radio = QRadioButton("🛡️ 磁盘镜像快照恢复（推荐）")
        image_radio.setChecked(True)  # 默认选择
        main_layout.addWidget(image_radio)
        
        image_desc = QLabel(
            "• 创建磁盘的逐比特镜像副本进行恢复\n"
            "• 完全隔离，避免对原始磁盘的任何影响\n"
            "• 跨平台支持，适用于所有类型的磁盘\n"
            "• 需要足够的存储空间保存镜像文件"
        )
        image_desc.setStyleSheet("""
            QLabel {
                color: #27ae60;
                font-size: 12px;
                margin-left: 30px;
                margin-bottom: 15px;
                line-height: 1.4;
            }
        """)
        main_layout.addWidget(image_desc)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("QFrame { color: #bdc3c7; }")
        main_layout.addWidget(line)
        
        # 传统恢复选项
        legacy_radio = QRadioButton("⚠️ 传统直接恢复")
        main_layout.addWidget(legacy_radio)
        
        legacy_desc = QLabel(
            "• 直接访问磁盘设备进行扫描\n"
            "• 可能与文件系统产生冲突\n"
            "• 适用于未挂载的磁盘或原始设备\n"
            "• 对挂载分区可能导致访问失败"
        )
        legacy_desc.setStyleSheet("""
            QLabel {
                color: #e74c3c;
                font-size: 12px;
                margin-left: 30px;
                margin-bottom: 15px;
                line-height: 1.4;
            }
        """)
        main_layout.addWidget(legacy_desc)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("确定")
        ok_button.clicked.connect(dialog.accept)
        
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("cancelButton")
        cancel_button.clicked.connect(dialog.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # 显示对话框
        if dialog.exec_() == QDialog.Accepted:
            if image_radio.isChecked():
                return 'signature'  # 使用磁盘镜像快照恢复
            else:
                return 'signature_legacy'  # 使用传统恢复
        
        return None
    
    def _show_fat32_recovery_method_dialog(self):
        """显示FAT32恢复方式选择对话框"""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QPushButton, QFrame
        from PyQt5.QtCore import Qt
        
        dialog = QDialog(self)
        dialog.setWindowTitle("FAT32恢复方式选择")
        dialog.setFixedSize(500, 400)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        # 设置对话框样式
        dialog.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
                border: 1px solid #dee2e6;
            }
            QLabel {
                color: #495057;
                font-family: 'Microsoft YaHei', Arial, sans-serif;
            }
            QRadioButton {
                font-size: 14px;
                font-weight: bold;
                color: #495057;
                spacing: 8px;
                padding: 8px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
            }
            QRadioButton::indicator:unchecked {
                border: 2px solid #6c757d;
                border-radius: 8px;
                background-color: white;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #007bff;
                border-radius: 8px;
                background-color: #007bff;
            }
            QPushButton {
                background-color: #007bff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004085;
            }
            QPushButton#cancelButton {
                background-color: #6c757d;
            }
            QPushButton#cancelButton:hover {
                background-color: #5a6268;
            }
            QPushButton#cancelButton:pressed {
                background-color: #545b62;
            }
        """)
        
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel("请选择FAT32恢复方式：")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 10px;
                padding: 8px 0px;
            }
        """)
        main_layout.addWidget(title_label)
        
        # 磁盘镜像快照恢复选项
        image_radio = QRadioButton("🛡️ 磁盘镜像快照恢复（推荐）")
        image_radio.setChecked(True)  # 默认选择
        main_layout.addWidget(image_radio)
        
        image_desc = QLabel(
            "• 创建磁盘的逐比特镜像副本进行恢复\n"
            "• 完全隔离，避免对原始磁盘的任何影响\n"
            "• 跨平台支持，适用于所有类型的磁盘\n"
            "• 需要足够的存储空间保存镜像文件"
        )
        image_desc.setStyleSheet("""
            QLabel {
                color: #27ae60;
                font-size: 12px;
                margin-left: 30px;
                margin-bottom: 15px;
                line-height: 1.4;
            }
        """)
        main_layout.addWidget(image_desc)
        
        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet("QFrame { color: #bdc3c7; }")
        main_layout.addWidget(line)
        
        # 传统恢复选项
        legacy_radio = QRadioButton("⚠️ 传统直接恢复")
        main_layout.addWidget(legacy_radio)
        
        legacy_desc = QLabel(
            "• 直接访问磁盘设备进行扫描\n"
            "• 可能与文件系统产生冲突\n"
            "• 适用于未挂载的磁盘或原始设备\n"
            "• 对挂载分区可能导致访问失败"
        )
        legacy_desc.setStyleSheet("""
            QLabel {
                color: #e74c3c;
                font-size: 12px;
                margin-left: 30px;
                margin-bottom: 15px;
                line-height: 1.4;
            }
        """)
        main_layout.addWidget(legacy_desc)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("确定")
        ok_button.clicked.connect(dialog.accept)
        
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("cancelButton")
        cancel_button.clicked.connect(dialog.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # 显示对话框
        if dialog.exec_() == QDialog.Accepted:
            if image_radio.isChecked():
                return 'image'  # 使用磁盘镜像快照恢复
            else:
                return 'direct'  # 使用传统恢复
        
        return None
    
    def _show_file_type_dialog(self):
        """显示美化的文件类型选择对话框"""
        from PyQt5.QtWidgets import QDialog, QGridLayout, QGroupBox, QFrame
        from PyQt5.QtCore import Qt
        from PyQt5.QtGui import QFont, QPalette
        
        dialog = QDialog(self)
        dialog.setWindowTitle("选择文件类型")
        dialog.setFixedSize(580, 580)
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        # 设置对话框样式
        dialog.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                font-family: 'Microsoft YaHei', 'SimHei', sans-serif;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                color: #2c3e50;
                border: 2px solid #bdc3c7;
                border-radius: 6px;
                margin-top: 5px;
                padding-top: 4px;
                background-color: #f8f9fa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px 0 6px;
                background-color: #ffffff;
                color: #34495e;
            }
            QCheckBox {
                font-size: 12px;
                color: #2c3e50;
                spacing: 6px;
                padding: 4px;
                background-color: transparent;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 3px;
                border: 2px solid #95a5a6;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #3498db;
                border-color: #3498db;
                background-image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTQiIGhlaWdodD0iMTQiIHZpZXdCb3g9IjAgMCAxNCAxNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTExLjMzMzMgMy41TDUuMjUgOS41ODMzM0wyLjY2NjY3IDciIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPgo=);
                background-repeat: no-repeat;
                background-position: center;
            }
            QCheckBox::indicator:hover {
                border-color: #3498db;
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-weight: bold;
                font-size: 14px;
                min-width: 80px;
                min-height: 30px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
            QPushButton#cancelButton {
                background-color: #95a5a6;
            }
            QPushButton#cancelButton:hover {
                background-color: #7f8c8d;
            }
            QPushButton#selectAllButton {
                background-color: #27ae60;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-size: 13px;
                padding: 6px 12px;
                min-width: 60px;
                min-height: 25px;
            }
            QPushButton#selectAllButton:hover {
                background-color: #229954;
            }
            QPushButton#selectNoneButton {
                background-color: #e74c3c;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-size: 13px;
                padding: 6px 12px;
                min-width: 60px;
                min-height: 25px;
            }
            QPushButton#selectNoneButton:hover {
                background-color: #c0392b;
            }
            QPushButton#selectCommonButton {
                background-color: #f39c12;
                font-family: "Microsoft YaHei", "SimHei", "黑体";
                font-size: 13px;
                padding: 6px 12px;
                min-width: 60px;
                min-height: 25px;
            }
            QPushButton#selectCommonButton:hover {
                background-color: #e67e22;
            }
        """)
        
        main_layout = QVBoxLayout(dialog)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # 标题标签
        title_label = QLabel("请选择要恢复的文件类型：")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 15px;
                font-weight: bold;
                color: #2c3e50;
                margin-bottom: 12px;
                padding: 8px 0px;
            }
        """)
        main_layout.addWidget(title_label)
        
        # 文件类型定义
        file_type_groups = {
            "图片文件": [
                ("jpg", "JPEG 图像文件", "📷"),
                ("png", "PNG 图像文件", "🖼️")
            ],
            "文档文件": [
                ("pdf", "PDF 文档", "📄"),
                ("doc", "Word 文档 (旧版)", "📝"),
                ("docx", "Word 文档 (新版)", "📝"),
                ("xls", "Excel 表格 (旧版)", "📊"),
                ("xlsx", "Excel 表格 (新版)", "📊")
            ],
            "压缩文件": [
                ("zip", "ZIP 压缩文件", "📦"),
                ("rar", "RAR 压缩文件", "📦")
            ]
        }
        
        self.checkboxes = {}
        
        # 创建分组
        for group_name, file_types in file_type_groups.items():
            group_box = QGroupBox(group_name)
            group_layout = QVBoxLayout()
            group_layout.setSpacing(5)
            group_layout.setContentsMargins(12, 8, 12, 8)
            
            for file_type, description, emoji in file_types:
                checkbox = QCheckBox(f"{emoji} {file_type.upper()} - {description}")
                self.checkboxes[file_type] = checkbox
                group_layout.addWidget(checkbox)
            
            group_box.setLayout(group_layout)
            main_layout.addWidget(group_box)
        
        # 快速选择按钮
        quick_select_layout = QHBoxLayout()
        quick_select_layout.setSpacing(10)
        
        select_all_btn = QPushButton("全选")
        select_all_btn.setObjectName("selectAllButton")
        select_all_btn.clicked.connect(lambda: self._toggle_all_checkboxes(True))
        
        select_none_btn = QPushButton("全不选")
        select_none_btn.setObjectName("selectNoneButton")
        select_none_btn.clicked.connect(lambda: self._toggle_all_checkboxes(False))
        
        select_common_btn = QPushButton("常用类型")
        select_common_btn.setObjectName("selectCommonButton")
        select_common_btn.clicked.connect(self._select_common_types)
        
        quick_select_layout.addWidget(select_all_btn)
        quick_select_layout.addWidget(select_none_btn)
        quick_select_layout.addWidget(select_common_btn)
        quick_select_layout.addStretch()
        
        main_layout.addLayout(quick_select_layout)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("确定")
        ok_button.clicked.connect(dialog.accept)
        
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("cancelButton")
        cancel_button.clicked.connect(dialog.reject)
        
        button_layout.addWidget(ok_button)
        button_layout.addWidget(cancel_button)
        
        main_layout.addLayout(button_layout)
        
        # 默认选择常用类型
        self._select_common_types()
        
        # 显示对话框
        if dialog.exec_() == QDialog.Accepted:
            selected_types = [file_type for file_type, checkbox in self.checkboxes.items() 
                            if checkbox.isChecked()]
            if not selected_types:
                QMessageBox.warning(self, "警告", "请至少选择一种文件类型")
                return self._show_file_type_dialog()  # 递归调用直到选择了类型
            return selected_types
        
        return []
    
    def _toggle_all_checkboxes(self, checked):
        """切换所有复选框状态"""
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(checked)
    
    def _select_common_types(self):
        """选择常用文件类型"""
        common_types = ['jpg', 'png', 'pdf', 'docx', 'zip']
        for file_type, checkbox in self.checkboxes.items():
            checkbox.setChecked(file_type in common_types)
    
    def view_fat_table(self):
        """在十六进制窗口查看FAT表"""
        try:
            # 检查是否选择了磁盘
            if not self.current_disk:
                QMessageBox.warning(self, "警告", "请先选择一个磁盘")
                return
            
            disk_path = self.current_disk['path']
            
            # 验证磁盘路径是否存在和可访问
            if not os.path.exists(disk_path):
                QMessageBox.warning(
                    self, "错误", 
                    f"磁盘路径不存在: {disk_path}\n\n"
                    f"可能的原因:\n"
                    f"• 驱动器未连接或已移除\n"
                    f"• 驱动器盘符已更改\n"
                    f"• 需要管理员权限访问\n\n"
                    f"请检查驱动器连接状态或刷新磁盘列表"
                )
                return
            
            # 检查文件访问权限
            try:
                with open(disk_path, 'rb') as test_file:
                    test_file.read(1)  # 尝试读取1字节测试访问权限
            except PermissionError:
                QMessageBox.warning(
                    self, "权限错误", 
                    f"无法访问磁盘: {disk_path}\n\n"
                    f"请以管理员身份运行程序"
                )
                return
            except Exception as e:
                QMessageBox.warning(
                    self, "访问错误", 
                    f"无法访问磁盘: {disk_path}\n\n"
                    f"错误信息: {str(e)}"
                )
                return
            
            # 检查是否为FAT32文件系统
            from fat32_recovery import FAT32Recovery
            recovery = FAT32Recovery()
            
            # 显示进度对话框
            progress_dialog = QProgressDialog("正在读取FAT表...", "取消", 0, 100, self)
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setAutoClose(False)
            progress_dialog.setAutoReset(False)
            progress_dialog.show()
            
            try:
                with open(disk_path, 'rb') as disk_file:
                    # 查找FAT32引导扇区
                    progress_dialog.setLabelText("正在查找FAT32引导扇区...")
                    progress_dialog.setValue(20)
                    QApplication.processEvents()
                    
                    boot_sector = recovery._find_fat32_boot_sector(disk_file)
                    if not boot_sector:
                        QMessageBox.warning(self, "错误", "未找到有效的FAT32引导扇区")
                        return
                    
                    # 解析FAT32参数
                    progress_dialog.setLabelText("正在解析FAT32参数...")
                    progress_dialog.setValue(40)
                    QApplication.processEvents()
                    
                    fat32_info = recovery._parse_fat32_boot_sector(boot_sector)
                    
                    # 读取FAT表
                    progress_dialog.setLabelText("正在读取FAT表数据...")
                    progress_dialog.setValue(60)
                    QApplication.processEvents()
                    
                    # 计算FAT表偏移和大小
                    fat1_offset = fat32_info['partition_offset'] + fat32_info['reserved_sectors'] * fat32_info['bytes_per_sector']
                    fat_size = fat32_info['sectors_per_fat'] * fat32_info['bytes_per_sector']
                    
                    # 读取FAT表原始数据
                    disk_file.seek(fat1_offset)
                    fat_data = disk_file.read(fat_size)
                    
                    progress_dialog.setLabelText("正在加载到十六进制查看器...")
                    progress_dialog.setValue(80)
                    QApplication.processEvents()
                    
                    # 在十六进制查看器中显示FAT表数据
                    self.hex_viewer.set_data(fat_data, fat1_offset)
                    
                    # 切换到十六进制查看器选项卡
                    self.tabs.setCurrentIndex(0)
                    
                    progress_dialog.setValue(100)
                    progress_dialog.close()
                    
                    # 显示成功信息
                    QMessageBox.information(
                        self, "成功", 
                        f"FAT表已加载到十六进制查看器\n\n"
                        f"FAT表偏移: 0x{fat1_offset:X}\n"
                        f"FAT表大小: {fat_size:,} 字节\n"
                        f"扇区数: {fat32_info['sectors_per_fat']:,}\n"
                        f"字节/扇区: {fat32_info['bytes_per_sector']}"
                    )
                    
            except Exception as e:
                progress_dialog.close()
                QMessageBox.critical(self, "错误", f"读取FAT表失败: {str(e)}")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"查看FAT表失败: {str(e)}")
    
    def view_fdt_table(self):
        """在十六进制窗口查看FDT（文件目录表）"""
        try:
            # 检查是否选择了磁盘
            if not self.current_disk:
                QMessageBox.warning(self, "警告", "请先选择一个磁盘")
                return
            
            disk_path = self.current_disk['path']
            
            # 验证磁盘路径是否存在和可访问
            if not os.path.exists(disk_path):
                QMessageBox.warning(
                    self, "错误", 
                    f"磁盘路径不存在: {disk_path}\n\n"
                    f"可能的原因:\n"
                    f"• 驱动器未连接或已移除\n"
                    f"• 驱动器盘符已更改\n"
                    f"• 需要管理员权限访问\n\n"
                    f"请检查驱动器连接状态或刷新磁盘列表"
                )
                return
            
            # 检查文件访问权限
            try:
                with open(disk_path, 'rb') as test_file:
                    test_file.read(1)  # 尝试读取1字节测试访问权限
            except PermissionError:
                QMessageBox.warning(
                    self, "权限错误", 
                    f"无法访问磁盘: {disk_path}\n\n"
                    f"请以管理员身份运行程序"
                )
                return
            except Exception as e:
                QMessageBox.warning(
                    self, "访问错误", 
                    f"无法访问磁盘: {disk_path}\n\n"
                    f"错误信息: {str(e)}"
                )
                return
            
            # 检查是否为FAT32文件系统
            from fat32_recovery import FAT32Recovery
            recovery = FAT32Recovery()
            
            # 显示进度对话框
            progress_dialog = QProgressDialog("正在读取FDT...", "取消", 0, 100, self)
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.setAutoClose(False)
            progress_dialog.setAutoReset(False)
            progress_dialog.show()
            
            try:
                with open(disk_path, 'rb') as disk_file:
                    # 查找FAT32引导扇区
                    progress_dialog.setLabelText("正在查找FAT32引导扇区...")
                    progress_dialog.setValue(20)
                    QApplication.processEvents()
                    
                    boot_sector = recovery._find_fat32_boot_sector(disk_file)
                    if not boot_sector:
                        QMessageBox.warning(self, "错误", "未找到有效的FAT32引导扇区")
                        return
                    
                    # 解析FAT32参数
                    progress_dialog.setLabelText("正在解析FAT32参数...")
                    progress_dialog.setValue(40)
                    QApplication.processEvents()
                    
                    fat32_info = recovery._parse_fat32_boot_sector(boot_sector)
                    
                    # 读取根目录FDT
                    progress_dialog.setLabelText("正在读取根目录FDT数据...")
                    progress_dialog.setValue(60)
                    QApplication.processEvents()
                    
                    # 计算根目录簇的偏移
                    root_cluster = fat32_info['root_cluster']
                    if root_cluster < 2:
                        QMessageBox.warning(self, "错误", f"无效的根目录簇号: {root_cluster}")
                        return
                    
                    # 计算根目录在磁盘上的偏移位置
                    root_offset = fat32_info['data_offset'] + (root_cluster - 2) * fat32_info['cluster_size']
                    
                    # 读取根目录的一个簇数据（通常包含多个目录项）
                    disk_file.seek(root_offset)
                    fdt_data = disk_file.read(fat32_info['cluster_size'])
                    
                    if len(fdt_data) == 0:
                        QMessageBox.warning(self, "错误", "无法读取根目录数据")
                        return
                    
                    progress_dialog.setLabelText("正在加载到十六进制查看器...")
                    progress_dialog.setValue(80)
                    QApplication.processEvents()
                    
                    # 在十六进制查看器中显示FDT数据
                    self.hex_viewer.set_data(fdt_data, root_offset)
                    
                    # 切换到十六进制查看器选项卡
                    self.tabs.setCurrentIndex(0)
                    
                    progress_dialog.setValue(100)
                    progress_dialog.close()
                    
                    # 显示成功信息
                    QMessageBox.information(
                        self, "成功", 
                        f"根目录FDT已加载到十六进制查看器\n\n"
                        f"根目录簇号: {root_cluster}\n"
                        f"FDT偏移: 0x{root_offset:X}\n"
                        f"FDT大小: {len(fdt_data):,} 字节\n"
                        f"簇大小: {fat32_info['cluster_size']} 字节\n"
                        f"字节/扇区: {fat32_info['bytes_per_sector']}\n\n"
                        f"注意: 每个目录项占32字节，包含文件名、属性、\n"
                        f"首簇号、文件大小等信息。已删除文件的第一个\n"
                        f"字节会被标记为0xE5。"
                    )
                    
            except Exception as e:
                progress_dialog.close()
                QMessageBox.critical(self, "错误", f"读取FDT失败: {str(e)}")
                
        except Exception as e:
            QMessageBox.critical(self, "错误", f"查看FDT失败: {str(e)}")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        try:
            if self.current_worker:
                reply = QMessageBox.question(
                    self, "确认退出",
                    "有任务正在运行，确定要退出吗？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                
                if reply == QMessageBox.Yes:
                    try:
                        self.current_worker.terminate()
                        self.current_worker.wait(1000)  # 等待最多1秒
                    except:
                        pass  # 忽略终止线程时的异常
                    event.accept()
                else:
                    event.ignore()
            else:
                event.accept()
        except Exception as e:
            print(f"关闭事件处理异常: {e}")
            event.accept()  # 强制接受关闭事件

def main():
    app = QApplication(sys.argv)
    window = DiskRecoveryTool()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()