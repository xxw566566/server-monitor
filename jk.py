# jk.py - 服务器性能监控客户端（图形化展示版 - 数据库加密版 - 智能告警版 - 完全可配置版 - 系统托盘版）
import requests
import time
from datetime import datetime, timedelta
from collections import defaultdict
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
from plyer import notification
import json
from collections import deque
import sqlite3
import os
from cryptography.fernet import Fernet
import base64
import hashlib
import pystray
from PIL import Image, ImageDraw

class DatabaseManager:
    """数据库管理类"""
    
    def __init__(self, db_path='server_monitor.db'):
        self.db_path = db_path
        self.key_file = 'monitor.key'
        self.cipher = self._get_cipher()
        self.init_database()
    
    def _get_cipher(self):
        """获取加密密钥"""
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            # 生成新密钥
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
        return Fernet(key)
    
    def encrypt(self, text):
        """加密文本"""
        if not text:
            return ""
        return self.cipher.encrypt(text.encode()).decode()
    
    def decrypt(self, encrypted_text):
        """解密文本"""
        if not encrypted_text:
            return ""
        try:
            return self.cipher.decrypt(encrypted_text.encode()).decode()
        except Exception:
            return ""
    
    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建服务器表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                encrypted_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建配置表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_server(self, name, url, key):
        """添加服务器"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            encrypted_key = self.encrypt(key)
            cursor.execute('''
                INSERT INTO servers (name, url, encrypted_key)
                VALUES (?, ?, ?)
            ''', (name, url, encrypted_key))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def update_server(self, old_url, name, url, key):
        """更新服务器"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            encrypted_key = self.encrypt(key)
            cursor.execute('''
                UPDATE servers 
                SET name=?, url=?, encrypted_key=?, updated_at=CURRENT_TIMESTAMP
                WHERE url=?
            ''', (name, url, encrypted_key, old_url))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def delete_server(self, url):
        """删除服务器"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM servers WHERE url=?', (url,))
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted
    
    def get_all_servers(self):
        """获取所有服务器"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT name, url, encrypted_key FROM servers ORDER BY id')
        rows = cursor.fetchall()
        conn.close()
        
        servers = []
        for name, url, encrypted_key in rows:
            servers.append({
                'name': name,
                'url': url,
                'key': self.decrypt(encrypted_key)
            })
        return servers
    
    def save_setting(self, key, value):
        """保存配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (key, str(value)))
        conn.commit()
        conn.close()
    
    def get_setting(self, key, default=None):
        """获取配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT value FROM settings WHERE key=?', (key,))
        row = cursor.fetchone()
        conn.close()
        
        return row[0] if row else default
    
    def save_all_settings(self, settings):
        """批量保存配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for key, value in settings.items():
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, str(value)))
        
        conn.commit()
        conn.close()
    
    def get_all_settings(self):
        """获取所有配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT key, value FROM settings')
        rows = cursor.fetchall()
        conn.close()
        
        return {key: value for key, value in rows}


class AlertTracker:
    """告警追踪器 - 实现智能告警逻辑"""
    
    def __init__(self, time_window=600, verify_count=3, enable_smart_alert=True):
        """
        初始化告警追踪器
        :param time_window: 时间窗口（秒），默认600秒（10分钟）
        :param verify_count: 验证次数，默认3次
        :param enable_smart_alert: 是否启用智能告警
        """
        self.time_window = time_window
        self.verify_count = verify_count
        self.enable_smart_alert = enable_smart_alert
        
        # 存储每个服务器的异常记录 {server_url: [(timestamp, metric_name, value), ...]}
        self.alert_history = defaultdict(list)
        
        # 存储已发送通知的服务器 {server_url: {metric_name: timestamp}}
        self.notified_servers = defaultdict(dict)
    
    def record_alert(self, server_url, metric_name, value):
        """
        记录一次告警
        :param server_url: 服务器URL
        :param metric_name: 指标名称 (cpu/memory/load)
        :param value: 指标值
        """
        current_time = datetime.now()
        
        # 清理超过时间窗口的旧记录
        self.alert_history[server_url] = [
            (ts, name, val) for ts, name, val in self.alert_history[server_url]
            if (current_time - ts).total_seconds() <= self.time_window
        ]
        
        # 添加新记录
        self.alert_history[server_url].append((current_time, metric_name, value))
    
    def should_verify(self, server_url, metric_name):
        """
        检查是否应该进行连续验证
        :param server_url: 服务器URL
        :param metric_name: 指标名称
        :return: True如果在时间窗口内检测到异常
        """
        if not self.enable_smart_alert:
            return True  # 如果禁用智能告警，总是进行验证（即立即通知）
        
        current_time = datetime.now()
        
        # 统计时间窗口内该指标的异常次数
        count = sum(
            1 for ts, name, _ in self.alert_history[server_url]
            if name == metric_name and (current_time - ts).total_seconds() <= self.time_window
        )
        
        return count > 0
    
    def should_notify(self, server_url, metric_name):
        """
        检查是否应该发送通知
        :param server_url: 服务器URL
        :param metric_name: 指标名称
        :return: True如果应该发送通知
        """
        # 检查是否最近已经通知过（时间窗口内不重复通知相同指标）
        if metric_name in self.notified_servers[server_url]:
            last_notify_time = self.notified_servers[server_url][metric_name]
            if (datetime.now() - last_notify_time).total_seconds() < self.time_window:
                return False
        
        return True
    
    def mark_notified(self, server_url, metric_name):
        """
        标记已发送通知
        :param server_url: 服务器URL
        :param metric_name: 指标名称
        """
        self.notified_servers[server_url][metric_name] = datetime.now()
    
    def clear_alerts(self, server_url, metric_name):
        """
        清除告警记录（当指标恢复正常时调用）
        :param server_url: 服务器URL
        :param metric_name: 指标名称
        """
        self.alert_history[server_url] = [
            (ts, name, val) for ts, name, val in self.alert_history[server_url]
            if name != metric_name
        ]
        
        # 清除通知记录
        if metric_name in self.notified_servers[server_url]:
            del self.notified_servers[server_url][metric_name]


class ServerCard(tk.Frame):
    """服务器监控卡片"""
    
    def __init__(self, parent, server_info, on_delete_callback, on_refresh_callback):
        super().__init__(parent, relief='raised', borderwidth=2, bg='#ffffff')
        self.server_info = server_info
        self.on_delete_callback = on_delete_callback
        self.on_refresh_callback = on_refresh_callback
        self.history_data = {
            'cpu': deque(maxlen=20),
            'memory': deque(maxlen=20),
            'load': deque(maxlen=20)
        }
        
        # 设置最小尺寸
        self.config(width=400, height=450)
        
        self.setup_ui()
    
    def setup_ui(self):
        """设置UI"""
        # 头部区域
        header_frame = tk.Frame(self, bg='#2196F3', height=40)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        # 服务器名称
        tk.Label(header_frame, text=f"🖥️ {self.server_info['name']}", 
                bg='#2196F3', fg='white', 
                font=('Arial', 12, 'bold')).pack(side='left', padx=10, pady=5)
        
        # 状态指示器
        self.status_label = tk.Label(header_frame, text="●", 
                                     bg='#2196F3', fg='#FFC107',
                                     font=('Arial', 16))
        self.status_label.pack(side='right', padx=5)
        
        # 刷新按钮
        refresh_btn = tk.Button(header_frame, text="🔄", 
                               command=self.refresh_card,
                               bg='#00BCD4', fg='white',
                               font=('Arial', 10, 'bold'),
                               relief='flat', cursor='hand2',
                               width=3)
        refresh_btn.pack(side='right', padx=2)
        
        # 删除按钮
        delete_btn = tk.Button(header_frame, text="✖", 
                               command=self.delete_card,
                               bg='#f44336', fg='white',
                               font=('Arial', 10, 'bold'),
                               relief='flat', cursor='hand2',
                               width=3)
        delete_btn.pack(side='right', padx=2)
        
        # 内容区域
        content_frame = tk.Frame(self, bg='#ffffff', padx=10, pady=10)
        content_frame.pack(fill='both', expand=True)
        
        # URL信息
        url_label = tk.Label(content_frame, 
                            text=self.server_info['url'],
                            bg='#ffffff', fg='#666666',
                            font=('Arial', 9))
        url_label.pack(anchor='w', pady=(0, 10))
        
        # CPU使用率
        self.create_metric_display(content_frame, "CPU使用率", 'cpu')
        
        # 内存使用率
        self.create_metric_display(content_frame, "内存使用", 'memory')
        
        # 系统负载
        self.create_metric_display(content_frame, "系统负载", 'load')
        
        # 磁盘使用率
        self.create_metric_display(content_frame, "磁盘使用", 'disk')
        
        # 底部信息栏
        self.info_frame = tk.Frame(content_frame, bg='#f5f5f5', height=60)
        self.info_frame.pack(fill='x', pady=(10, 0))
        self.info_frame.pack_propagate(False)
        
        self.info_label = tk.Label(self.info_frame, 
                                   text="等待数据...",
                                   bg='#f5f5f5', fg='#666666',
                                   font=('Courier', 8),
                                   justify='left')
        self.info_label.pack(padx=5, pady=5, anchor='w')
        
        # 最后更新时间
        self.update_time_label = tk.Label(content_frame,
                                         text="",
                                         bg='#ffffff', fg='#999999',
                                         font=('Arial', 8))
        self.update_time_label.pack(pady=(5, 0))
    
    def create_metric_display(self, parent, label_text, metric_type):
        """创建指标显示组件"""
        frame = tk.Frame(parent, bg='#ffffff')
        frame.pack(fill='x', pady=5)
        
        # 标签和数值
        top_frame = tk.Frame(frame, bg='#ffffff')
        top_frame.pack(fill='x')
        
        tk.Label(top_frame, text=label_text, 
                bg='#ffffff', fg='#333333',
                font=('Arial', 9)).pack(side='left')
        
        value_label = tk.Label(top_frame, text="0.0%", 
                              bg='#ffffff', fg='#2196F3',
                              font=('Arial', 10, 'bold'))
        value_label.pack(side='right')
        
        # 进度条容器
        progress_container = tk.Frame(frame, bg='#e0e0e0', height=25)
        progress_container.pack(fill='x', pady=(3, 0))
        progress_container.pack_propagate(False)
        
        # 进度条
        progress_bar = tk.Frame(progress_container, bg='#4CAF50', height=25)
        progress_bar.place(x=0, y=0, relwidth=0, relheight=1)
        
        # 百分比文本
        percent_label = tk.Label(progress_container, text="0%",
                                bg='#e0e0e0', fg='#333333',
                                font=('Arial', 9, 'bold'))
        percent_label.place(relx=0.5, rely=0.5, anchor='center')
        
        # 保存引用
        setattr(self, f'{metric_type}_value_label', value_label)
        setattr(self, f'{metric_type}_progress_bar', progress_bar)
        setattr(self, f'{metric_type}_percent_label', percent_label)
        setattr(self, f'{metric_type}_container', progress_container)
    
    def update_metric(self, metric_type, value, max_value=100, detail_text=""):
        """更新指标显示"""
        percent = min(100, (value / max_value * 100)) if max_value > 0 else 0
        
        # 更新数值标签
        value_label = getattr(self, f'{metric_type}_value_label')
        if metric_type == 'load':
            value_label.config(text=f"{value:.2f}")
        else:
            value_label.config(text=f"{value:.1f}% {detail_text}")
        
        # 更新进度条
        progress_bar = getattr(self, f'{metric_type}_progress_bar')
        percent_label = getattr(self, f'{metric_type}_percent_label')
        container = getattr(self, f'{metric_type}_container')
        
        # 根据百分比改变颜色
        if percent >= 90:
            color = '#f44336'  # 红色 - 严重
            percent_label.config(bg=color, fg='white')
        elif percent >= 80:
            color = '#FF9800'  # 橙色 - 警告
            percent_label.config(bg=color, fg='white')
        elif percent >= 70:
            color = '#FFC107'  # 黄色 - 注意
            percent_label.config(bg='#e0e0e0', fg='#333333')
        else:
            color = '#4CAF50'  # 绿色 - 正常
            percent_label.config(bg='#e0e0e0', fg='#333333')
        
        progress_bar.config(bg=color)
        progress_bar.place(relwidth=percent/100)
        percent_label.config(text=f"{percent:.1f}%")
        
        # 保存历史数据
        if metric_type in self.history_data:
            self.history_data[metric_type].append(value)
    
    def update_data(self, data):
        """更新服务器数据"""
        try:
            # 更新状态指示器
            self.status_label.config(fg='#4CAF50')  # 绿色表示在线
            
            # CPU
            cpu_percent = data['cpu']['percent']
            cpu_count = data['cpu']['count']
            self.update_metric('cpu', cpu_percent, detail_text=f"({cpu_count}核)")
            
            # 内存
            memory = data['memory']
            memory_percent = memory['percent']
            memory_detail = f"({memory['used_gb']:.1f}G/{memory['total_gb']:.1f}G)"
            self.update_metric('memory', memory_percent, detail_text=memory_detail)
            
            # 负载
            load = data['load']
            load1_percent = load.get('load1_percent', 0)
            load_detail = f"({load['load1']:.2f}, {load['load5']:.2f}, {load['load15']:.2f})"
            self.update_metric('load', load1_percent, detail_text=load_detail)
            
            # 磁盘
            disk = data['disk']
            disk_percent = disk['percent']
            disk_detail = f"({disk['used_gb']:.1f}G/{disk['total_gb']:.1f}G)"
            self.update_metric('disk', disk_percent, detail_text=disk_detail)
            
            # 更新底部信息
            system = data['system']
            info_text = (
                f"主机: {system['hostname']} | "
                f"系统: {system['platform']} {system['platform_release']} | "
                f"架构: {system['architecture']}"
            )
            self.info_label.config(text=info_text)
            
            # 更新时间
            update_time = datetime.now().strftime('%H:%M:%S')
            self.update_time_label.config(text=f"最后更新: {update_time}")
            
        except Exception as e:
            print(f"更新数据失败: {e}")
    
    def set_error_status(self, error_msg="连接失败"):
        """设置错误状态"""
        self.status_label.config(fg='#f44336')  # 红色表示离线
        self.info_label.config(text=f"❌ {error_msg}")
        
        # 重置所有进度条
        for metric in ['cpu', 'memory', 'load', 'disk']:
            progress_bar = getattr(self, f'{metric}_progress_bar', None)
            if progress_bar:
                progress_bar.place(relwidth=0)
    
    def refresh_card(self):
        """刷新卡片数据"""
        if self.on_refresh_callback:
            self.on_refresh_callback(self.server_info)
    
    def delete_card(self):
        """删除卡片"""
        if self.on_delete_callback:
            self.on_delete_callback(self.server_info)


class ServerMonitor:
    def __init__(self):
        self.window = tk.Tk()
        self.window.title("服务器性能监控系统")
        self.window.geometry("1400x900")
        self.window.configure(bg='#f5f5f5')
        
        # 初始化数据库管理器
        self.db = DatabaseManager()
        
        # 系统托盘相关
        self.tray_icon = None
        self.is_hidden = False
        
        # 监控参数
        self.cpu_threshold = 80.0
        self.load_threshold = 80.0
        self.memory_threshold = 85.0
        self.check_interval = 15
        self.verify_count = 3  # 智能告警验证次数
        self.verify_interval = 1  # 验证检测间隔（秒）
        self.enable_smart_alert = True  # 是否启用智能告警
        self.alert_time_window = 600  # 告警时间窗口（秒）
        
        # 初始化告警追踪器
        self.alert_tracker = AlertTracker(
            time_window=self.alert_time_window,
            verify_count=self.verify_count,
            enable_smart_alert=self.enable_smart_alert
        )
        
        self.monitoring = False
        self.monitor_thread = None
        
        # 数据存储
        self.servers = []
        self.server_cards = {}
        self.card_row_frames = []  # 存储卡片行容器
        
        self.setup_ui()
        
        # 加载保存的配置
        self.load_config()
        
        # 创建系统托盘图标
        self.create_tray_icon()
    
    def create_tray_icon(self):
        """创建系统托盘图标"""
        # 创建一个简单的图标
        def create_image():
            # 创建一个64x64的图标
            width = 64
            height = 64
            color1 = (33, 150, 243)  # 蓝色
            color2 = (255, 255, 255)  # 白色
            
            image = Image.new('RGB', (width, height), color1)
            dc = ImageDraw.Draw(image)
            
            # 绘制一个简单的服务器图标
            dc.rectangle([16, 20, 48, 28], fill=color2)
            dc.rectangle([16, 32, 48, 40], fill=color2)
            dc.rectangle([16, 44, 48, 52], fill=color2)
            
            return image
        
        # 创建托盘菜单
        menu = pystray.Menu(
            pystray.MenuItem('显示主窗口', self.show_window, default=True),
            pystray.MenuItem('隐藏主窗口', self.hide_window),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('退出程序', self.quit_app)
        )
        
        # 创建托盘图标
        self.tray_icon = pystray.Icon(
            "server_monitor",
            create_image(),
            "服务器监控系统",
            menu
        )
    
    def show_window(self, icon=None, item=None):
        """显示主窗口"""
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()
        self.is_hidden = False
    
    def hide_window(self, icon=None, item=None):
        """隐藏主窗口到系统托盘"""
        self.window.withdraw()
        self.is_hidden = True
        
        # 如果托盘图标还没运行，启动它
        if self.tray_icon and not self.tray_icon.visible:
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
    
    def quit_app(self, icon=None, item=None):
        """退出应用程序"""
        if self.monitoring:
            self.monitoring = False
            time.sleep(0.5)
        
        # 停止托盘图标
        if self.tray_icon:
            self.tray_icon.stop()
        
        # 销毁窗口
        try:
            self.window.quit()
            self.window.destroy()
        except:
            pass
    
    def on_closing(self):
        """关闭窗口时的处理"""
        # 创建选择对话框
        dialog = tk.Toplevel(self.window)
        dialog.title("退出选项")
        dialog.geometry("450x250")
        dialog.transient(self.window)
        dialog.grab_set()
        dialog.resizable(False, False)
        
        # 设置对话框居中
        dialog.update_idletasks()
        x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
        y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # 主框架
        main_frame = tk.Frame(dialog, bg='#ffffff', padx=20, pady=20)
        main_frame.pack(fill='both', expand=True)
        
        # 标题
        title_label = tk.Label(
            main_frame,
            text="请选择操作",
            font=('Arial', 14, 'bold'),
            bg='#ffffff',
            fg='#333333'
        )
        title_label.pack(pady=(0, 15))
        
        # 提示信息
        if self.monitoring:
            info_text = "⚠️ 监控正在运行中..."
            info_color = '#FF9800'
        else:
            info_text = "ℹ️ 监控已停止"
            info_color = '#666666'
        
        info_label = tk.Label(
            main_frame,
            text=info_text,
            font=('Arial', 10),
            bg='#ffffff',
            fg=info_color
        )
        info_label.pack(pady=(0, 20))
        
        # 按钮框架
        button_frame = tk.Frame(main_frame, bg='#ffffff')
        button_frame.pack(pady=10)
        
        def minimize_to_tray():
            """最小化到系统托盘"""
            dialog.destroy()
            self.hide_window()
            self.log("📌 程序已最小化到系统托盘", 'info')
        
        def exit_program():
            """退出程序"""
            dialog.destroy()
            self.quit_app()
        
        def cancel_action():
            """取消操作"""
            dialog.destroy()
        
        # 最小化到托盘按钮
        minimize_btn = tk.Button(
            button_frame,
            text="📌 最小化到托盘",
            command=minimize_to_tray,
            bg='#2196F3',
            fg='white',
            font=('Arial', 11, 'bold'),
            relief='flat',
            cursor='hand2',
            width=15,
            height=2
        )
        minimize_btn.pack(side='left', padx=5)
        
        # 退出程序按钮
        exit_btn = tk.Button(
            button_frame,
            text="❌ 退出程序",
            command=exit_program,
            bg='#f44336',
            fg='white',
            font=('Arial', 11, 'bold'),
            relief='flat',
            cursor='hand2',
            width=15,
            height=2
        )
        exit_btn.pack(side='left', padx=5)
        
        # 取消按钮
        cancel_btn = tk.Button(
            button_frame,
            text="↩️ 取消",
            command=cancel_action,
            bg='#9E9E9E',
            fg='white',
            font=('Arial', 11, 'bold'),
            relief='flat',
            cursor='hand2',
            width=10,
            height=2
        )
        cancel_btn.pack(side='left', padx=5)
        
        # 提示文本
        tip_label = tk.Label(
            main_frame,
            text="💡 提示: 最小化到托盘后，程序将在后台继续运行\n可通过系统托盘图标重新打开窗口",
            font=('Arial', 9),
            bg='#ffffff',
            fg='#666666',
            justify='center'
        )
        tip_label.pack(pady=(20, 0))
        
    def save_config(self):
        """保存配置到数据库"""
        try:
            settings = {
                'cpu_threshold': self.cpu_threshold,
                'memory_threshold': self.memory_threshold,
                'load_threshold': self.load_threshold,
                'check_interval': self.check_interval,
                'verify_count': self.verify_count,
                'verify_interval': self.verify_interval,
                'enable_smart_alert': self.enable_smart_alert,
                'alert_time_window': self.alert_time_window
            }
            
            self.db.save_all_settings(settings)
            self.log(f"💾 配置已保存到数据库", 'success')
            return True
        except Exception as e:
            self.log(f"❌ 保存配置失败: {str(e)}", 'error')
            return False
    
    def load_config(self):
        """从数据库加载配置"""
        try:
            # 加载设置
            settings = self.db.get_all_settings()
            
            if settings:
                self.cpu_threshold = float(settings.get('cpu_threshold', 80.0))
                self.memory_threshold = float(settings.get('memory_threshold', 85.0))
                self.load_threshold = float(settings.get('load_threshold', 80.0))
                self.check_interval = int(settings.get('check_interval', 15))
                self.verify_count = int(settings.get('verify_count', 3))
                self.verify_interval = int(settings.get('verify_interval', 1))
                self.enable_smart_alert = settings.get('enable_smart_alert', 'True') == 'True'
                self.alert_time_window = int(settings.get('alert_time_window', 600))
                
                # 更新UI
                self.cpu_threshold_var.set(str(self.cpu_threshold))
                self.memory_threshold_var.set(str(self.memory_threshold))
                self.load_threshold_var.set(str(self.load_threshold))
                self.check_interval_var.set(str(self.check_interval))
                self.verify_count_var.set(str(self.verify_count))
                self.verify_interval_var.set(str(self.verify_interval))
                self.smart_alert_var.set(self.enable_smart_alert)
                self.alert_window_var.set(str(self.alert_time_window))
            
            # 加载服务器列表
            self.servers = self.db.get_all_servers()
            
            # 创建服务器卡片和树视图项
            for server_info in self.servers:
                self.create_server_card(server_info)
                self.server_tree.insert('', 'end', 
                                      values=(server_info['name'], 
                                             server_info['url']))
            
            self.update_server_count()
            if self.servers:
                self.log(f"✅ 已从数据库加载 {len(self.servers)} 个服务器配置", 'success')
            
        except Exception as e:
            self.log(f"❌ 加载配置失败: {str(e)}", 'error')
            messagebox.showerror("加载失败", f"加载配置失败:\n{str(e)}")
        
    def setup_ui(self):
        """设置UI"""
        # 顶部控制栏
        self.setup_top_bar()
        
        # 中间内容区域（使用Notebook）
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # 服务器监控标签页
        self.monitor_tab = tk.Frame(self.notebook, bg='#f5f5f5')
        self.notebook.add(self.monitor_tab, text='📊 服务器监控')
        
        # 创建滚动区域
        self.setup_monitor_tab()
        
        # 服务器管理标签页
        self.manage_tab = tk.Frame(self.notebook, bg='#ffffff')
        self.notebook.add(self.manage_tab, text='⚙️ 服务器管理')
        self.setup_manage_tab()
        
        # 日志标签页
        self.log_tab = tk.Frame(self.notebook, bg='#ffffff')
        self.notebook.add(self.log_tab, text='📋 监控日志')
        self.setup_log_tab()
        
        # 底部状态栏
        self.setup_status_bar()
    
    def setup_top_bar(self):
        """设置顶部控制栏"""
        top_frame = tk.Frame(self.window, bg='#2196F3', height=80)
        top_frame.pack(fill='x', padx=0, pady=0)
        top_frame.pack_propagate(False)
        
        # 标题
        title_frame = tk.Frame(top_frame, bg='#2196F3')
        title_frame.pack(side='left', padx=20, pady=10)
        
        tk.Label(title_frame, text="🖥️ 服务器性能监控系统",
                bg='#2196F3', fg='white',
                font=('Arial', 18, 'bold')).pack(anchor='w')
        
        tk.Label(title_frame, text="实时监控您的服务器性能状态 | 🔒 数据加密保护 | 🧠 智能告警 | ⚙️ 完全可配置",
                bg='#2196F3', fg='#E3F2FD',
                font=('Arial', 10)).pack(anchor='w')
        
        # 控制按钮
        button_frame = tk.Frame(top_frame, bg='#2196F3')
        button_frame.pack(side='right', padx=20)
        
        self.start_button = tk.Button(button_frame, text="▶ 开始监控",
                                      command=self.start_monitoring,
                                      bg='#4CAF50', fg='white',
                                      font=('Arial', 11, 'bold'),
                                      width=12, height=2,
                                      relief='flat', cursor='hand2')
        self.start_button.pack(side='left', padx=5)
        
        self.stop_button = tk.Button(button_frame, text="⏸ 停止监控",
                                     command=self.stop_monitoring,
                                     bg='#FF9800', fg='white',
                                     font=('Arial', 11, 'bold'),
                                     width=12, height=2,
                                     relief='flat', cursor='hand2',
                                     state='disabled')
        self.stop_button.pack(side='left', padx=5)
        
        refresh_button = tk.Button(button_frame, text="🔄 刷新全部",
                                   command=self.refresh_all_servers,
                                   bg='#00BCD4', fg='white',
                                   font=('Arial', 11, 'bold'),
                                   width=10, height=2,
                                   relief='flat', cursor='hand2')
        refresh_button.pack(side='left', padx=5)
    
    def setup_monitor_tab(self):
        """设置监控标签页"""
        # 创建Canvas和Scrollbar
        canvas = tk.Canvas(self.monitor_tab, bg='#f5f5f5')
        scrollbar = ttk.Scrollbar(self.monitor_tab, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg='#f5f5f5')
        
        # 绑定滚动事件
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 布局
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 鼠标滚轮绑定
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # 空状态提示
        self.empty_label = tk.Label(self.scrollable_frame,
                                    text="📭 暂无服务器\n\n请在「服务器管理」标签页中添加服务器",
                                    bg='#f5f5f5', fg='#999999',
                                    font=('Arial', 14))
        self.empty_label.pack(pady=100)
    
    def setup_manage_tab(self):
        """设置管理标签页"""
        # 配置面板
        config_frame = tk.LabelFrame(self.manage_tab, text="⚙️ 监控配置",
                                    font=('Arial', 11, 'bold'),
                                    bg='#ffffff', padx=15, pady=15)
        config_frame.pack(fill='x', padx=20, pady=20)
        
        # 第一行 - 阈值配置
        row1 = tk.Frame(config_frame, bg='#ffffff')
        row1.pack(fill='x', pady=5)
        
        tk.Label(row1, text="CPU阈值(%):", bg='#ffffff',
                font=('Arial', 10)).pack(side='left', padx=5)
        self.cpu_threshold_var = tk.StringVar(value="80")
        tk.Entry(row1, textvariable=self.cpu_threshold_var,
                width=10, font=('Arial', 10)).pack(side='left', padx=5)
        
        tk.Label(row1, text="内存阈值(%):", bg='#ffffff',
                font=('Arial', 10)).pack(side='left', padx=5)
        self.memory_threshold_var = tk.StringVar(value="85")
        tk.Entry(row1, textvariable=self.memory_threshold_var,
                width=10, font=('Arial', 10)).pack(side='left', padx=5)
        
        tk.Label(row1, text="负载阈值(%):", bg='#ffffff',
                font=('Arial', 10)).pack(side='left', padx=5)
        self.load_threshold_var = tk.StringVar(value="80")
        tk.Entry(row1, textvariable=self.load_threshold_var,
                width=10, font=('Arial', 10)).pack(side='left', padx=5)
        
        # 第二行 - 检测配置
        row2 = tk.Frame(config_frame, bg='#ffffff')
        row2.pack(fill='x', pady=5)
        
        tk.Label(row2, text="检测间隔(秒):", bg='#ffffff',
                font=('Arial', 10)).pack(side='left', padx=5)
        self.check_interval_var = tk.StringVar(value="15")
        tk.Entry(row2, textvariable=self.check_interval_var,
                width=10, font=('Arial', 10)).pack(side='left', padx=5)
        
        # 第三行 - 智能告警配置
        row3 = tk.Frame(config_frame, bg='#ffffff')
        row3.pack(fill='x', pady=5)
        
        self.smart_alert_var = tk.BooleanVar(value=True)
        smart_alert_check = tk.Checkbutton(row3, 
                                          text="启用智能告警",
                                          variable=self.smart_alert_var,
                                          command=self.toggle_smart_alert,
                                          bg='#ffffff',
                                          font=('Arial', 10, 'bold'),
                                          fg='#2196F3')
        smart_alert_check.pack(side='left', padx=5)
        
        tk.Label(row3, text="告警时间窗口(秒):", bg='#ffffff',
                font=('Arial', 10)).pack(side='left', padx=5)
        self.alert_window_var = tk.StringVar(value="600")
        self.alert_window_entry = tk.Entry(row3, textvariable=self.alert_window_var,
                                           width=10, font=('Arial', 10))
        self.alert_window_entry.pack(side='left', padx=5)
        
        tk.Label(row3, text="(默认600秒=10分钟)", bg='#ffffff', fg='#666666',
                font=('Arial', 9)).pack(side='left', padx=5)
        
        # 第四行 - 验证检测配置
        row4 = tk.Frame(config_frame, bg='#ffffff')
        row4.pack(fill='x', pady=5)
        
        tk.Label(row4, text="连续验证次数:", bg='#ffffff',
                font=('Arial', 10)).pack(side='left', padx=5)
        self.verify_count_var = tk.StringVar(value="3")
        self.verify_count_entry = tk.Entry(row4, textvariable=self.verify_count_var,
                                           width=10, font=('Arial', 10))
        self.verify_count_entry.pack(side='left', padx=5)
        
        tk.Label(row4, text="验证间隔(秒):", bg='#ffffff',
                font=('Arial', 10)).pack(side='left', padx=5)
        self.verify_interval_var = tk.StringVar(value="1")
        self.verify_interval_entry = tk.Entry(row4, textvariable=self.verify_interval_var,
                                              width=10, font=('Arial', 10))
        self.verify_interval_entry.pack(side='left', padx=5)
        
        tk.Label(row4, text="(每次验证的间隔时间)", bg='#ffffff', fg='#666666',
                font=('Arial', 9)).pack(side='left', padx=5)
        
        # 保存配置按钮
        tk.Button(row4, text="💾 保存配置",
                 command=self.save_settings,
                 bg='#607D8B', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2').pack(side='left', padx=20)
        
        # 智能告警说明
        self.smart_alert_info_frame = tk.Frame(config_frame, bg='#E3F2FD', 
                                              relief='solid', borderwidth=1)
        self.smart_alert_info_frame.pack(fill='x', pady=10)
        
        tk.Label(self.smart_alert_info_frame, text="🧠 智能告警机制:",
                bg='#E3F2FD', fg='#1976D2',
                font=('Arial', 10, 'bold')).pack(anchor='w', padx=10, pady=(5, 2))
        
        self.smart_alert_info_text = tk.Label(self.smart_alert_info_frame,
                                             text="",
                                             bg='#E3F2FD', fg='#424242',
                                             font=('Arial', 9), justify='left')
        self.smart_alert_info_text.pack(anchor='w', padx=20, pady=(0, 5))
        
        self.update_smart_alert_info()
        
        # 服务器添加面板
        add_frame = tk.LabelFrame(self.manage_tab, text="➕ 添加服务器",
                                 font=('Arial', 11, 'bold'),
                                 bg='#ffffff', padx=15, pady=15)
        add_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        # 服务器名称
        name_row = tk.Frame(add_frame, bg='#ffffff')
        name_row.pack(fill='x', pady=5)
        tk.Label(name_row, text="服务器名称:", bg='#ffffff',
                font=('Arial', 10), width=12, anchor='w').pack(side='left')
        self.server_name_entry = tk.Entry(name_row, font=('Arial', 10), width=40)
        self.server_name_entry.pack(side='left', padx=5, fill='x', expand=True)
        
        # 服务器地址
        url_row = tk.Frame(add_frame, bg='#ffffff')
        url_row.pack(fill='x', pady=5)
        tk.Label(url_row, text="服务器地址:", bg='#ffffff',
                font=('Arial', 10), width=12, anchor='w').pack(side='left')
        self.server_url_entry = tk.Entry(url_row, font=('Arial', 10), width=40)
        self.server_url_entry.pack(side='left', padx=5, fill='x', expand=True)
        
        # 服务器密钥
        key_row = tk.Frame(add_frame, bg='#ffffff')
        key_row.pack(fill='x', pady=5)
        tk.Label(key_row, text="访问密钥:", bg='#ffffff',
                font=('Arial', 10), width=12, anchor='w').pack(side='left')
        self.server_key_entry = tk.Entry(key_row, font=('Arial', 10), 
                                         width=40, show='*')
        self.server_key_entry.pack(side='left', padx=5, fill='x', expand=True)
        
        # 按钮行
        button_row = tk.Frame(add_frame, bg='#ffffff')
        button_row.pack(fill='x', pady=(10, 0))
        
        tk.Button(button_row, text="🔍 测试连接",
                 command=self.test_connection,
                 bg='#FF9800', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2',
                 width=12).pack(side='left', padx=5)
        
        tk.Button(button_row, text="➕ 添加服务器",
                 command=self.add_server,
                 bg='#4CAF50', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2',
                 width=12).pack(side='left', padx=5)
        
        # 服务器列表面板
        list_frame = tk.LabelFrame(self.manage_tab, text="📋 服务器列表",
                                  font=('Arial', 11, 'bold'),
                                  bg='#ffffff', padx=15, pady=15)
        list_frame.pack(fill='both', expand=True, padx=20, pady=(0, 20))
        
        # 工具栏
        toolbar = tk.Frame(list_frame, bg='#ffffff')
        toolbar.pack(fill='x', pady=(0, 10))
        
        tk.Button(toolbar, text="🗑️ 删除选中",
                 command=self.remove_selected_server,
                 bg='#f44336', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2').pack(side='left', padx=5)
        
        tk.Button(toolbar, text="✏️ 修改配置",
                 command=self.edit_selected_server,
                 bg='#2196F3', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2').pack(side='left', padx=5)
        
        # 创建树形视图
        columns = ('name', 'url')
        self.server_tree = ttk.Treeview(list_frame, columns=columns,
                                       show='headings', height=10)
        
        self.server_tree.heading('name', text='服务器名称')
        self.server_tree.heading('url', text='服务器地址')
        
        self.server_tree.column('name', width=200)
        self.server_tree.column('url', width=500)
        
        # 双击编辑
        self.server_tree.bind('<Double-Button-1>', lambda e: self.edit_selected_server())
        
        # 滚动条
        tree_scroll = ttk.Scrollbar(list_frame, orient="vertical",
                                   command=self.server_tree.yview)
        self.server_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.server_tree.pack(side='left', fill='both', expand=True)
        tree_scroll.pack(side='right', fill='y')
    
    def toggle_smart_alert(self):
        """切换智能告警"""
        self.enable_smart_alert = self.smart_alert_var.get()
        
        # 更新告警追踪器
        self.alert_tracker.enable_smart_alert = self.enable_smart_alert
        
        # 更新说明文字
        self.update_smart_alert_info()
        
        # 启用/禁用相关输入框
        if self.enable_smart_alert:
            self.alert_window_entry.config(state='normal')
            self.verify_count_entry.config(state='normal')
            self.verify_interval_entry.config(state='normal')
        else:
            self.alert_window_entry.config(state='disabled')
            self.verify_count_entry.config(state='disabled')
            self.verify_interval_entry.config(state='disabled')
    
    def update_smart_alert_info(self):
        """更新智能告警说明"""
        if self.smart_alert_var.get():
            verify_count = self.verify_count_var.get()
            verify_interval = self.verify_interval_var.get()
            window_seconds = self.alert_window_var.get()
            
            try:
                window_minutes = int(window_seconds) // 60
            except:
                window_minutes = 10
            
            info_text = (
                f"• 启用后：检测到超过阈值 → 触发连续验证机制 → 连续{verify_count}次（每{verify_interval}秒一次）都超过阈值才发送通知\n"
                f"• 时间窗口内（{window_minutes}分钟）同一指标不会重复通知\n"
                f"• 避免因瞬时波动导致的误报，确保告警的准确性"
            )
            self.smart_alert_info_frame.config(bg='#E3F2FD')
            self.smart_alert_info_text.config(bg='#E3F2FD', fg='#424242', text=info_text)
        else:
            info_text = (
                "• 禁用后：检测到超过阈值 → 立即发送通知\n"
                "• 不进行连续验证，可能会有误报\n"
                "• 适用于对实时性要求极高的场景"
            )
            self.smart_alert_info_frame.config(bg='#FFF3E0')
            self.smart_alert_info_text.config(bg='#FFF3E0', fg='#E65100', text=info_text)
    
    def setup_log_tab(self):
        """设置日志标签页"""
        # 工具栏
        toolbar = tk.Frame(self.log_tab, bg='#f5f5f5', height=50)
        toolbar.pack(fill='x', padx=10, pady=10)
        toolbar.pack_propagate(False)
        
        tk.Button(toolbar, text="🗑️ 清空日志",
                 command=self.clear_log,
                 bg='#9E9E9E', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2').pack(side='left', padx=5)
        
        tk.Button(toolbar, text="💾 导出日志",
                 command=self.export_log,
                 bg='#607D8B', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2').pack(side='left', padx=5)
        
        # 日志文本区域
        self.log_text = scrolledtext.ScrolledText(self.log_tab,
                                                  font=('Courier', 9),
                                                  bg='#ffffff')
        self.log_text.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # 配置标签
        self.log_text.tag_config('info', foreground='#2196F3')
        self.log_text.tag_config('success', foreground='#4CAF50')
        self.log_text.tag_config('warning', foreground='#FF9800')
        self.log_text.tag_config('error', foreground='#f44336')
        self.log_text.tag_config('alert', foreground='#f44336',
                                font=('Courier', 9, 'bold'))
        self.log_text.tag_config('verify', foreground='#9C27B0',
                                font=('Courier', 9, 'bold'))
    
    def setup_status_bar(self):
        """设置状态栏"""
        status_frame = tk.Frame(self.window, bg='#E0E0E0', height=35)
        status_frame.pack(fill='x', side='bottom')
        status_frame.pack_propagate(False)
        
        self.status_label = tk.Label(status_frame, text="● 状态: 未启动",
                                     bg='#E0E0E0', fg='#666666',
                                     font=('Arial', 10))
        self.status_label.pack(side='left', padx=15)
        
        self.server_count_label = tk.Label(status_frame,
                                          text="服务器数量: 0",
                                          bg='#E0E0E0', fg='#666666',
                                          font=('Arial', 10))
        self.server_count_label.pack(side='left', padx=15)
        
        # 智能告警状态
        self.smart_alert_status_label = tk.Label(status_frame, 
                                                 text="🧠 智能告警: 已启用",
                                                 bg='#E0E0E0', fg='#9C27B0',
                                                 font=('Arial', 10))
        self.smart_alert_status_label.pack(side='left', padx=15)
        
        # 数据库加密状态
        tk.Label(status_frame, text="🔒 数据库加密保护",
                bg='#E0E0E0', fg='#4CAF50',
                font=('Arial', 10)).pack(side='left', padx=15)
        
        self.time_label = tk.Label(status_frame, text="",
                                  bg='#E0E0E0', fg='#666666',
                                  font=('Arial', 10))
        self.time_label.pack(side='right', padx=15)
        
        self.update_time_display()
    
    def update_time_display(self):
        """更新时间显示"""
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.time_label.config(text=current_time)
        self.window.after(1000, self.update_time_display)
    
    def update_smart_alert_status(self):
        """更新智能告警状态显示"""
        if self.enable_smart_alert:
            self.smart_alert_status_label.config(
                text=f"🧠 智能告警: 已启用 (验证{self.verify_count}次,窗口{self.alert_time_window//60}分钟)",
                fg='#9C27B0'
            )
        else:
            self.smart_alert_status_label.config(
                text="🧠 智能告警: 已禁用",
                fg='#FF5722'
            )
    
    def save_settings(self):
        """保存设置"""
        try:
            self.cpu_threshold = float(self.cpu_threshold_var.get())
            self.memory_threshold = float(self.memory_threshold_var.get())
            self.load_threshold = float(self.load_threshold_var.get())
            self.check_interval = int(self.check_interval_var.get())
            self.verify_count = int(self.verify_count_var.get())
            self.verify_interval = int(self.verify_interval_var.get())
            self.enable_smart_alert = self.smart_alert_var.get()
            self.alert_time_window = int(self.alert_window_var.get())
            
            if self.check_interval < 5:
                messagebox.showwarning("警告", "检测间隔不能小于5秒！")
                return
            
            if self.verify_count < 1:
                messagebox.showwarning("警告", "连续验证次数至少为1次！")
                return
            
            if self.verify_interval < 1:
                messagebox.showwarning("警告", "验证间隔至少为1秒！")
                return
            
            if self.alert_time_window < 60:
                messagebox.showwarning("警告", "告警时间窗口不能小于60秒！")
                return
            
            # 更新告警追踪器
            self.alert_tracker.verify_count = self.verify_count
            self.alert_tracker.enable_smart_alert = self.enable_smart_alert
            self.alert_tracker.time_window = self.alert_time_window
            
            # 更新状态栏
            self.update_smart_alert_status()
            
            # 更新说明文字
            self.update_smart_alert_info()
                
        except ValueError as e:
            messagebox.showerror("错误", f"配置参数错误: {str(e)}")
            return
        
        if self.save_config():
            messagebox.showinfo("成功", "配置已保存到数据库！")
    
    def add_server(self):
        """添加服务器"""
        name = self.server_name_entry.get().strip()
        url = self.server_url_entry.get().strip()
        key = self.server_key_entry.get().strip()
        
        if not name or not url or not key:
            messagebox.showwarning("警告", "请填写完整的服务器信息！")
            return
        
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        
        # 检查是否已存在
        for server in self.servers:
            if server['url'] == url:
                messagebox.showwarning("警告", "该服务器已存在！")
                return
        
        # 保存到数据库
        if not self.db.add_server(name, url, key):
            messagebox.showerror("错误", "添加服务器失败！可能已存在相同地址的服务器。")
            return
        
        server_info = {
            'name': name,
            'url': url,
            'key': key
        }
        
        self.servers.append(server_info)
        self.server_tree.insert('', 'end', values=(name, url))
        
        # 创建服务器卡片
        self.create_server_card(server_info)
        
        self.log(f"✅ 已添加服务器: {name} ({url}) [密钥已加密存储]", 'success')
        self.update_server_count()
        
        # 清空输入框
        self.server_name_entry.delete(0, tk.END)
        self.server_url_entry.delete(0, tk.END)
        self.server_key_entry.delete(0, tk.END)
    
    def edit_selected_server(self):
        """修改选中的服务器配置"""
        selection = self.server_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要修改的服务器！")
            return
        
        item = selection[0]
        values = self.server_tree.item(item, 'values')
        url = values[1]
        
        # 查找服务器信息
        server_info = None
        for s in self.servers:
            if s['url'] == url:
                server_info = s
                break
        
        if not server_info:
            return
        
        # 创建编辑对话框
        edit_window = tk.Toplevel(self.window)
        edit_window.title(f"修改服务器配置 - {server_info['name']}")
        edit_window.geometry("500x300")
        edit_window.transient(self.window)
        edit_window.grab_set()
        
        # 设置对话框居中
        edit_window.update_idletasks()
        x = (edit_window.winfo_screenwidth() // 2) - (edit_window.winfo_width() // 2)
        y = (edit_window.winfo_screenheight() // 2) - (edit_window.winfo_height() // 2)
        edit_window.geometry(f"+{x}+{y}")
        
        # 主框架
        main_frame = tk.Frame(edit_window, bg='#ffffff', padx=20, pady=20)
        main_frame.pack(fill='both', expand=True)
        
        # 服务器名称
        name_frame = tk.Frame(main_frame, bg='#ffffff')
        name_frame.pack(fill='x', pady=10)
        tk.Label(name_frame, text="服务器名称:", bg='#ffffff',
                font=('Arial', 10), width=12, anchor='w').pack(side='left')
        name_var = tk.StringVar(value=server_info['name'])
        name_entry = tk.Entry(name_frame, textvariable=name_var,
                             font=('Arial', 10))
        name_entry.pack(side='left', fill='x', expand=True, padx=5)
        
        # 服务器地址
        url_frame = tk.Frame(main_frame, bg='#ffffff')
        url_frame.pack(fill='x', pady=10)
        tk.Label(url_frame, text="服务器地址:", bg='#ffffff',
                font=('Arial', 10), width=12, anchor='w').pack(side='left')
        url_var = tk.StringVar(value=server_info['url'])
        url_entry = tk.Entry(url_frame, textvariable=url_var,
                            font=('Arial', 10))
        url_entry.pack(side='left', fill='x', expand=True, padx=5)
        
        # 服务器密钥
        key_frame = tk.Frame(main_frame, bg='#ffffff')
        key_frame.pack(fill='x', pady=10)
        tk.Label(key_frame, text="访问密钥:", bg='#ffffff',
                font=('Arial', 10), width=12, anchor='w').pack(side='left')
        key_var = tk.StringVar(value=server_info['key'])
        key_entry = tk.Entry(key_frame, textvariable=key_var,
                            font=('Arial', 10), show='*')
        key_entry.pack(side='left', fill='x', expand=True, padx=5)
        
        # 提示信息
        tip_label = tk.Label(main_frame,
                            text="💡 提示: 修改后会立即保存并更新监控卡片",
                            bg='#ffffff', fg='#666666',
                            font=('Arial', 9))
        tip_label.pack(pady=10)
        
        # 按钮框架
        button_frame = tk.Frame(main_frame, bg='#ffffff')
        button_frame.pack(pady=20)
        
        def save_changes():
            new_name = name_var.get().strip()
            new_url = url_var.get().strip()
            new_key = key_var.get().strip()
            
            if not new_name or not new_url or not new_key:
                messagebox.showwarning("警告", "请填写完整的服务器信息！", parent=edit_window)
                return
            
            if not new_url.startswith(('http://', 'https://')):
                new_url = 'http://' + new_url
            
            # 检查URL是否与其他服务器冲突
            if new_url != server_info['url']:
                for s in self.servers:
                    if s['url'] == new_url:
                        messagebox.showwarning("警告", "该服务器地址已被使用！", parent=edit_window)
                        return
            
            # 更新数据库
            if self.db.update_server(server_info['url'], new_name, new_url, new_key):
                # 更新内存中的数据
                old_url = server_info['url']
                server_info['name'] = new_name
                server_info['url'] = new_url
                server_info['key'] = new_key
                
                # 更新树视图
                self.server_tree.item(item, values=(new_name, new_url))
                
                # 如果URL改变，需要更新卡片
                if old_url != new_url:
                    # 删除旧卡片
                    if old_url in self.server_cards:
                        self.server_cards[old_url].destroy()
                        del self.server_cards[old_url]
                    
                    # 重建所有卡片以保持布局
                    self.rebuild_all_cards()
                else:
                    # 只更新卡片信息
                    if new_url in self.server_cards:
                        # 更新卡片的服务器信息
                        self.server_cards[new_url].server_info = server_info
                
                self.log(f"✏️ 已更新服务器配置: {new_name}", 'success')
                messagebox.showinfo("成功", "服务器配置已更新！", parent=edit_window)
                edit_window.destroy()
            else:
                messagebox.showerror("错误", "更新失败！", parent=edit_window)
        
        tk.Button(button_frame, text="💾 保存",
                 command=save_changes,
                 bg='#4CAF50', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2',
                 width=10).pack(side='left', padx=5)
        
        tk.Button(button_frame, text="❌ 取消",
                 command=edit_window.destroy,
                 bg='#9E9E9E', fg='white',
                 font=('Arial', 10, 'bold'),
                 relief='flat', cursor='hand2',
                 width=10).pack(side='left', padx=5)
    
    def rebuild_all_cards(self):
        """重建所有服务器卡片"""
        # 清除所有旧卡片
        for card in self.server_cards.values():
            card.destroy()
        self.server_cards.clear()
        
        # 清除所有行容器
        for row_frame in self.card_row_frames:
            row_frame.destroy()
        self.card_row_frames.clear()
        
        # 隐藏空状态提示
        if self.servers:
            self.empty_label.pack_forget()
        else:
            self.empty_label.pack(pady=100)
            return
        
        # 重新创建所有卡片
        for server_info in self.servers:
            self.create_server_card(server_info)
    
    def create_server_card(self, server_info):
        """创建服务器卡片"""
        # 隐藏空状态提示
        self.empty_label.pack_forget()
        
        # 每行显示3个卡片
        cards_per_row = 3
        current_row_index = len(self.server_cards) // cards_per_row
        
        # 检查是否需要创建新行
        if len(self.server_cards) % cards_per_row == 0:
            row_frame = tk.Frame(self.scrollable_frame, bg='#f5f5f5')
            row_frame.pack(fill='x', padx=10, pady=10)
            self.card_row_frames.append(row_frame)
        else:
            row_frame = self.card_row_frames[-1]
        
        # 创建卡片
        card = ServerCard(row_frame, server_info, 
                         on_delete_callback=self.delete_server_from_card,
                         on_refresh_callback=self.refresh_single_server)
        card.pack(side='left', padx=10, pady=10)
        
        self.server_cards[server_info['url']] = card
    
    def delete_server_from_card(self, server_info):
        """从卡片删除服务器"""
        if messagebox.askyesno("确认删除", 
                              f"确定要删除服务器 '{server_info['name']}' 吗？"):
            # 从数据库删除
            if self.db.delete_server(server_info['url']):
                # 从内存中删除
                self.servers = [s for s in self.servers if s['url'] != server_info['url']]
                
                # 从树视图中删除
                for item in self.server_tree.get_children():
                    values = self.server_tree.item(item, 'values')
                    if values[1] == server_info['url']:
                        self.server_tree.delete(item)
                        break
                
                # 重建所有卡片以保持布局
                self.rebuild_all_cards()
                
                self.log(f"🗑️ 已删除服务器: {server_info['name']}", 'warning')
                self.update_server_count()
    
    def refresh_single_server(self, server_info):
        """刷新单个服务器"""
        self.log(f"🔄 正在刷新服务器: {server_info['name']}...", 'info')
        
        def refresh_thread():
            self.check_server(server_info)
            self.log(f"✅ 服务器 {server_info['name']} 刷新完成", 'success')
        
        threading.Thread(target=refresh_thread, daemon=True).start()
    
    def remove_selected_server(self):
        """删除选中的服务器"""
        selection = self.server_tree.selection()
        if not selection:
            messagebox.showwarning("警告", "请先选择要删除的服务器！")
            return
        
        item = selection[0]
        values = self.server_tree.item(item, 'values')
        name = values[0]
        url = values[1]
        
        if messagebox.askyesno("确认删除", f"确定要删除服务器 '{name}' 吗？"):
            # 从数据库删除
            if self.db.delete_server(url):
                # 从内存中删除
                self.servers = [s for s in self.servers if s['url'] != url]
                
                # 从树视图中删除
                self.server_tree.delete(item)
                
                # 重建所有卡片
                self.rebuild_all_cards()
                
                self.log(f"🗑️ 已删除服务器: {name}", 'warning')
                self.update_server_count()
    
    def test_connection(self):
        """测试连接"""
        name = self.server_name_entry.get().strip()
        url = self.server_url_entry.get().strip()
        key = self.server_key_entry.get().strip()
        
        if not url or not key:
            messagebox.showwarning("警告", "请填写服务器地址和密钥！")
            return
        
        if not url.startswith(('http://', 'https://')):
            url = 'http://' + url
        
        server_info = {
            'name': name or '测试服务器',
            'url': url,
            'key': key
        }
        
        self.log(f"🔍 正在测试连接: {url}...", 'info')
        self.log(f"   开始连续{self.verify_count}次连接测试 (每次间隔{self.verify_interval}秒)...", 'info')
        
        def test_thread():
            success_count = 0
            
            for i in range(self.verify_count):
                if i > 0:
                    time.sleep(self.verify_interval)
                
                result = self.check_server(server_info, test_mode=True)
                
                if result:
                    success_count += 1
                    self.log(f"   ✅ 第{i+1}/{self.verify_count}次测试: 连接成功", 'success')
                else:
                    self.log(f"   ❌ 第{i+1}/{self.verify_count}次测试: 连接失败", 'error')
            
            self.show_test_result(success_count)
        
        threading.Thread(target=test_thread, daemon=True).start()
    
    def show_test_result(self, success_count):
        """显示测试结果"""
        if success_count == self.verify_count:
            self.log(f"✅ 连续检测全部成功 ({success_count}/{self.verify_count})", 'success')
            messagebox.showinfo("测试成功", 
                              f"服务器连接正常！\n连续检测成功率: {success_count}/{self.verify_count}")
        elif success_count > 0:
            self.log(f"⚠️ 连续检测部分成功 ({success_count}/{self.verify_count})", 'warning')
            messagebox.showwarning("测试部分成功", 
                                 f"服务器连接不稳定！\n连续检测成功率: {success_count}/{self.verify_count}\n\n建议:\n1. 检查网络连接\n2. 检查服务器稳定性")
        else:
            self.log(f"❌ 连续检测全部失败 ({success_count}/{self.verify_count})", 'error')
            messagebox.showerror("测试失败", 
                               f"服务器连接失败！\n连续检测成功率: {success_count}/{self.verify_count}\n\n请检查:\n1. 服务器地址是否正确\n2. 密钥是否正确\n3. 服务器是否在线")
    
    def verify_alert(self, server_info, metric_name, value):
        """
        验证告警 - 连续检测确认
        :param server_info: 服务器信息
        :param metric_name: 指标名称
        :param value: 初始检测值
        :return: True如果验证通过（连续N次都超过阈值）
        """
        self.log(f"🔍 [{server_info['name']}] 触发{metric_name}告警验证机制 (初始值: {value:.1f}%)", 'verify')
        self.log(f"   开始连续{self.verify_count}次验证检测 (每次间隔{self.verify_interval}秒)...", 'verify')
        
        exceeded_count = 0
        threshold_map = {
            'CPU': self.cpu_threshold,
            '内存': self.memory_threshold,
            '负载': self.load_threshold
        }
        threshold = threshold_map.get(metric_name, 80)
        
        for i in range(self.verify_count):
            time.sleep(self.verify_interval)  # 每次检测间隔
            
            # 进行单次检测
            data = self.check_server(server_info, silent_mode=True)
            
            if data:
                # 获取对应指标的值
                current_value = 0
                if metric_name == 'CPU':
                    current_value = data['cpu']['percent']
                elif metric_name == '内存':
                    current_value = data['memory']['percent']
                elif metric_name == '负载':
                    current_value = data['load'].get('load1_percent', 0)
                
                # 检查是否超过阈值
                if current_value > threshold:
                    exceeded_count += 1
                    self.log(f"   ✅ 第{i+1}/{self.verify_count}次验证: {metric_name}={current_value:.1f}% (超过阈值{threshold}%)", 'verify')
                else:
                    self.log(f"   ❌ 第{i+1}/{self.verify_count}次验证: {metric_name}={current_value:.1f}% (未超过阈值{threshold}%)", 'info')
            else:
                self.log(f"   ❌ 第{i+1}/{self.verify_count}次验证: 连接失败", 'error')
        
        # 判断是否所有检测都超过阈值
        all_exceeded = (exceeded_count == self.verify_count)
        
        if all_exceeded:
            self.log(f"🚨 [{server_info['name']}] {metric_name}告警验证通过！连续{exceeded_count}次检测都超过阈值", 'alert')
        else:
            self.log(f"ℹ️ [{server_info['name']}] {metric_name}告警验证未通过 ({exceeded_count}/{self.verify_count}次超过阈值)", 'info')
        
        return all_exceeded
    
    def check_server(self, server_info, test_mode=False, silent_mode=False):
        """
        检查服务器性能
        :param server_info: 服务器信息
        :param test_mode: 测试模式（只返回True/False）
        :param silent_mode: 静默模式（不更新UI和日志，用于验证检测）
        """
        try:
            headers = {
                'Authorization': f'Bearer {server_info["key"]}'
            }
            
            response = requests.get(f"{server_info['url']}/metrics",
                                   headers=headers, timeout=10)
            
            if response.status_code == 401:
                if not test_mode and not silent_mode:
                    self.log(f"🔐 [{server_info['name']}] 认证失败 - 密钥错误!", 'error')
                    if server_info['url'] in self.server_cards:
                        self.server_cards[server_info['url']].set_error_status("认证失败")
                return None
            
            if response.status_code == 200:
                data = response.json()
                
                if test_mode:
                    return True
                
                if silent_mode:
                    return data
                
                # 更新卡片数据
                if server_info['url'] in self.server_cards:
                    self.server_cards[server_info['url']].update_data(data)
                
                cpu = data['cpu']['percent']
                memory = data['memory']['percent']
                load = data['load'].get('load1_percent', 0)
                
                # 检查阈值 - 使用智能告警机制
                alerts = []
                metrics_exceeded = {}
                
                if cpu > self.cpu_threshold:
                    alerts.append(f"CPU: {cpu:.1f}%")
                    metrics_exceeded['CPU'] = cpu
                
                if memory > self.memory_threshold:
                    alerts.append(f"内存: {memory:.1f}%")
                    metrics_exceeded['内存'] = memory
                
                if load > self.load_threshold:
                    alerts.append(f"负载: {load:.1f}%")
                    metrics_exceeded['负载'] = load
                
                if metrics_exceeded:
                    # 有指标超过阈值
                    for metric_name, metric_value in metrics_exceeded.items():
                        # 记录告警
                        self.alert_tracker.record_alert(server_info['url'], metric_name, metric_value)
                        
                        # 检查是否需要验证（根据智能告警设置）
                        if self.alert_tracker.should_verify(server_info['url'], metric_name):
                            # 检查是否应该发送通知（避免重复通知）
                            if self.alert_tracker.should_notify(server_info['url'], metric_name):
                                # 如果启用智能告警，进行连续验证
                                if self.enable_smart_alert:
                                    self.log(f"⚠️ [{server_info['name']}] 检测到{metric_name}超过阈值: {metric_value:.1f}%", 'warning')
                                    
                                    verified = self.verify_alert(server_info, metric_name, metric_value)
                                    
                                    if verified:
                                        # 验证通过，发送系统通知
                                        alert_msg = f"⚠️ [{server_info['name']}] {metric_name}持续超过阈值！"
                                        self.log(alert_msg, 'alert')
                                        
                                        self.show_notification(
                                            f"🚨 服务器性能警告 - {server_info['name']}",
                                            f"{metric_name}持续超过阈值！\n当前值: {metric_value:.1f}%\n阈值: {self.cpu_threshold if metric_name=='CPU' else (self.memory_threshold if metric_name=='内存' else self.load_threshold)}%\n\n请立即检查服务器状态！"
                                        )
                                        
                                        # 标记已通知
                                        self.alert_tracker.mark_notified(server_info['url'], metric_name)
                                    else:
                                        # 验证未通过，可能是瞬时波动
                                        self.log(f"ℹ️ [{server_info['name']}] {metric_name}可能为瞬时波动，未发送通知", 'info')
                                else:
                                    # 未启用智能告警，直接通知
                                    alert_msg = f"⚠️ [{server_info['name']}] {metric_name}超过阈值: {metric_value:.1f}%"
                                    self.log(alert_msg, 'alert')
                                    
                                    self.show_notification(
                                        f"🚨 服务器性能警告 - {server_info['name']}",
                                        f"{metric_name}超过阈值！\n当前值: {metric_value:.1f}%\n阈值: {self.cpu_threshold if metric_name=='CPU' else (self.memory_threshold if metric_name=='内存' else self.load_threshold)}%\n\n请立即检查服务器状态！"
                                    )
                                    
                                    # 标记已通知
                                    self.alert_tracker.mark_notified(server_info['url'], metric_name)
                    
                    # 记录当前状态
                    if not silent_mode:
                        msg = f"⚠️ [{server_info['name']}] " + ", ".join(alerts)
                        self.log(msg, 'warning')
                else:
                    # 所有指标正常
                    if not silent_mode:
                        msg = f"✅ [{server_info['name']}] CPU:{cpu:.1f}% 内存:{memory:.1f}% 负载:{load:.1f}%"
                        self.log(msg, 'success')
                    
                    # 清除所有告警记录
                    for metric_name in ['CPU', '内存', '负载']:
                        self.alert_tracker.clear_alerts(server_info['url'], metric_name)
                
                return data
            else:
                if not silent_mode:
                    self.log(f"❌ [{server_info['name']}] HTTP {response.status_code}", 'error')
                    if server_info['url'] in self.server_cards:
                        self.server_cards[server_info['url']].set_error_status(f"HTTP {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            if not silent_mode:
                self.log(f"⏱️ [{server_info['name']}] 连接超时", 'error')
                if server_info['url'] in self.server_cards:
                    self.server_cards[server_info['url']].set_error_status("连接超时")
            return None
        except requests.exceptions.ConnectionError:
            if not silent_mode:
                self.log(f"🔌 [{server_info['name']}] 连接失败", 'error')
                if server_info['url'] in self.server_cards:
                    self.server_cards[server_info['url']].set_error_status("连接失败")
            return None
        except Exception as e:
            if not silent_mode:
                self.log(f"❌ [{server_info['name']}] 错误: {str(e)}", 'error')
                if server_info['url'] in self.server_cards:
                    self.server_cards[server_info['url']].set_error_status(str(e))
            return None
    
    def refresh_all_servers(self):
        """刷新所有服务器数据"""
        if not self.servers:
            messagebox.showinfo("提示", "请先添加服务器！")
            return
        
        self.log("🔄 开始刷新所有服务器数据...", 'info')
        
        def refresh_thread():
            for server_info in self.servers:
                self.check_server(server_info)
                time.sleep(0.5)
            self.log("✅ 所有服务器数据刷新完成", 'success')
        
        threading.Thread(target=refresh_thread, daemon=True).start()
    
    def monitor_loop(self):
        """监控循环"""
        self.log("="*80, 'info')
        self.log("🚀 开始服务器性能监控...", 'info')
        self.log(f"📊 监控服务器数量: {len(self.servers)}", 'info')
        self.log(f"⏱️  检测间隔: {self.check_interval}秒", 'info')
        
        if self.enable_smart_alert:
            self.log(f"🧠 智能告警: 已启用", 'info')
            self.log(f"   ├─ 时间窗口: {self.alert_time_window}秒 ({self.alert_time_window//60}分钟)", 'info')
            self.log(f"   ├─ 验证机制: 检测到超阈值 → 连续{self.verify_count}次验证(每{self.verify_interval}秒一次) → 全部超过才通知", 'info')
            self.log(f"   └─ 防重复: 时间窗口内同一指标不会重复通知", 'info')
        else:
            self.log(f"🧠 智能告警: 已禁用 (检测到超阈值立即通知)", 'warning')
        
        self.log(f"🔒 数据库加密: 已启用", 'info')
        self.log("="*80, 'info')
        
        while self.monitoring:
            # 检查所有服务器
            for server_info in self.servers[:]:
                if not self.monitoring:
                    break
                self.check_server(server_info)
            
            if self.monitoring:
                self.log(f"⏸️ 等待 {self.check_interval} 秒后继续下一轮检测...", 'info')
                time.sleep(self.check_interval)
                
        self.log("⏹️ 监控已停止", 'warning')
    
    def start_monitoring(self):
        """开始监控"""
        if not self.servers:
            messagebox.showwarning("警告", "请先添加服务器！")
            return
        
        if self.monitoring:
            return
        
        # 更新配置参数
        try:
            self.cpu_threshold = float(self.cpu_threshold_var.get())
            self.memory_threshold = float(self.memory_threshold_var.get())
            self.load_threshold = float(self.load_threshold_var.get())
            self.check_interval = int(self.check_interval_var.get())
            self.verify_count = int(self.verify_count_var.get())
            self.verify_interval = int(self.verify_interval_var.get())
            self.enable_smart_alert = self.smart_alert_var.get()
            self.alert_time_window = int(self.alert_window_var.get())
            
            # 更新告警追踪器
            self.alert_tracker.verify_count = self.verify_count
            self.alert_tracker.enable_smart_alert = self.enable_smart_alert
            self.alert_tracker.time_window = self.alert_time_window
            
        except ValueError:
            messagebox.showerror("错误", "配置参数格式错误！")
            return
        
        self.monitoring = True
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.status_label.config(text="● 状态: 监控中", fg='#4CAF50')
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """停止监控"""
        if not self.monitoring:
            return
        
        self.monitoring = False
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.status_label.config(text="● 状态: 已停止", fg='#FF9800')
        
        self.log("⏸️ 正在停止监控...", 'warning')
    
    def show_notification(self, title, message):
        """显示系统通知"""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="服务器监控系统",
                timeout=10
            )
        except Exception as e:
            print(f"通知发送失败: {e}")
    
    def log(self, message, level='info'):
        """记录日志"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_message = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_message, level)
        self.log_text.see(tk.END)
    
    def clear_log(self):
        """清空日志"""
        if messagebox.askyesno("确认", "确定要清空所有日志吗？"):
            self.log_text.delete(1.0, tk.END)
            self.log("📝 日志已清空", 'info')
    
    def export_log(self):
        """导出日志"""
        try:
            from tkinter import filedialog
            
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
                initialfile=f"monitor_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            
            if filename:
                log_content = self.log_text.get(1.0, tk.END)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(log_content)
                
                self.log(f"💾 日志已导出到: {filename}", 'success')
                messagebox.showinfo("成功", f"日志已导出到:\n{filename}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败:\n{str(e)}")
    
    def update_server_count(self):
        """更新服务器数量显示"""
        count = len(self.servers)
        self.server_count_label.config(text=f"服务器数量: {count}")
        
        # 更新空状态提示
        if count == 0:
            self.empty_label.pack(pady=100)
        else:
            self.empty_label.pack_forget()
    
    def run(self):
        """运行应用"""
        # 绑定关闭事件
        self.window.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 启动托盘图标（在后台线程中）
        if self.tray_icon:
            threading.Thread(target=self.tray_icon.run, daemon=True).start()
        
        self.window.mainloop()


def main():
    """主函数"""
    app = ServerMonitor()
    app.run()


if __name__ == '__main__':
    main()


