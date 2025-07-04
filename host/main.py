import os
import time
import sys
import pyautogui
import socketio
import configparser
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QPushButton, QLabel, QHBoxLayout, QMessageBox, QFrame)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QIcon

pyautogui.FAILSAFE = False

def get_application_path():
    """获取应用程序的根目录，兼容脚本运行和PyInstaller打包"""
    if getattr(sys, 'frozen', False):
        # 如果是PyInstaller打包的.exe文件
        return os.path.dirname(sys.executable)
    else:
        # 如果是直接运行的.py脚本
        return os.path.dirname(os.path.abspath(__file__))

def load_or_create_config(parent_window):
    """加载或创建 config.ini 文件"""
    path = get_application_path()
    config_file = os.path.join(path, 'config.ini')
    
    config = configparser.ConfigParser()

    if not os.path.exists(config_file):
        # 如果配置文件不存在，则创建并写入默认值
        print("未找到 config.ini，正在创建默认配置...")
        config['Server'] = {'url': 'http://127.0.0.1:8802'}
        config['Settings'] = {'set_pos_delay_ms': '3000'}
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write("# --- Sync Tool Config ---\n\n")
            config.write(f)
        QMessageBox.information(parent_window, "首次运行", 
                                f"已在以下位置创建默认配置文件:\n{config_file}\n请根据需要修改服务器地址。")
    
    # 读取配置文件
    config.read(config_file, encoding='utf-8')
    return config

class SocketIOThread(QThread):
    status_updated = Signal(dict)
    proceed_click = Signal()
    connection_error = Signal()
    connection_success = Signal()

    def __init__(self, server_url):
        super().__init__()
        self.server_url = server_url
        self.sio = socketio.Client(logger=True, engineio_logger=True)
        self.setup_events()

    def setup_events(self):
        @self.sio.event
        def connect():
            print("成功连接到服务器！")
            self.connection_success.emit()

        @self.sio.event
        def connect_error(data):
            print(f"连接失败: {data}")
            self.connection_error.emit()

        @self.sio.event
        def disconnect():
            print("与服务器断开连接。")

        @self.sio.event
        def status_update(data):
            self.status_updated.emit(data)

        @self.sio.event
        def proceed_click():
            print("!!! 收到 'proceed_click' 事件 !!!")
            self.proceed_click.emit()

    def run(self):
        try:
            self.sio.connect(self.server_url, transports=['websocket']) # 明确使用websocket
            self.sio.wait()
        except socketio.exceptions.ConnectionError as e:
            print(f"无法连接到服务器: {e}")
            self.connection_error.emit()

    def send_ready(self):
        if self.sio.connected:
            self.sio.emit('ready', {'player': 'host'})

    def stop(self):
        if self.sio.connected:
            self.sio.disconnect()
        self.quit()
        self.wait()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.click_pos = None

        try:
            self.config = load_or_create_config(self)
            self.server_url = self.config.get('Server', 'url')
            self.set_pos_delay = self.config.getint('Settings', 'set_pos_delay_ms')
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            QMessageBox.critical(self, "配置错误", f"config.ini 文件格式不正确或缺少必要项。\n错误: {e}\n程序将退出。")
            sys.exit(1) # 退出程序

        self.setWindowTitle("次元之锚")

        app_path = get_application_path()
        icon_path = os.path.join(app_path, 'assets', 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print(f"警告：找不到图标文件: {icon_path}")

        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.init_ui()
        self.apply_stylesheet()
        
        self.socket_thread = SocketIOThread(self.server_url)
        self.socket_thread.status_updated.connect(self.update_status_ui)
        self.socket_thread.proceed_click.connect(self.perform_click)
        self.socket_thread.connection_error.connect(self.show_connection_error)
        self.socket_thread.connection_success.connect(self.on_connection_success)
        self.socket_thread.start()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        # 主布局，负责整体垂直排列，并用伸缩项将其居中
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10) # 减小窗口边距
        main_layout.setSpacing(10)

        # --- 1. 创建核心的“卡片”面板 ---
        main_panel = QFrame()
        main_panel.setObjectName("mainPanel") # 为它设置一个ID，方便用CSS美化
        panel_layout = QVBoxLayout(main_panel)
        panel_layout.setContentsMargins(20, 15, 20, 15) # 卡片内部的边距
        panel_layout.setSpacing(15) # 卡片内元素的间距

        # --- 2. 创建上半部分的状态指示灯布局 ---
        status_panel = QHBoxLayout()
        self.my_status_widget = self.create_status_box("α")
        self.opponent_status_widget = self.create_status_box("β")
        status_panel.addWidget(self.my_status_widget)
        status_panel.addWidget(self.opponent_status_widget)

        # --- 3. 创建按钮，并直接添加到卡片布局中 ---
        self.ready_button = QPushButton("吟   唱") 
        self.ready_button.setObjectName("readyButton")
        self.ready_button.clicked.connect(self.on_ready_click)
        self.ready_button.setEnabled(False)

        # --- 4. 将状态指示灯和按钮依次添加到卡片布局中 ---
        panel_layout.addLayout(status_panel)
        panel_layout.addWidget(self.ready_button)

        # --- 5. 创建下方的设置面板 ---
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setObjectName("line")

        settings_panel = QHBoxLayout()
        self.set_pos_button = QPushButton("⚡️ 锁定奇点")
        self.set_pos_button.clicked.connect(self.on_set_pos_click)
        self.set_pos_button.setEnabled(False)
        self.pos_label = QLabel("NULL")
        self.pos_label.setObjectName("infoLabel")
        settings_panel.addWidget(self.set_pos_button)
        settings_panel.addWidget(self.pos_label)
        
        # --- 6. 将所有组件按顺序添加到主布局中 ---
        main_layout.addStretch(1) # 添加一个伸缩项，将内容向下推
        main_layout.addWidget(main_panel)
        main_layout.addWidget(line)
        main_layout.addLayout(settings_panel)
        main_layout.addStretch(1) # 添加另一个，实现垂直居中

        # 调整窗口尺寸以适应新布局
        self.setFixedSize(200, 220)

    def create_status_box(self, title):
        widget = QWidget()
        widget.setObjectName("statusBox")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(3)
        
        title_label = QLabel(title)
        title_label.setObjectName("statusTitleLabel")
        title_label.setAlignment(Qt.AlignCenter)
        
        status_indicator = QLabel()
        status_indicator.setObjectName("statusIndicator")
        status_indicator.setProperty("ready", "false")
        
        layout.addWidget(title_label)
        layout.addWidget(status_indicator)
        layout.setAlignment(Qt.AlignCenter)
        return widget

    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #282c34;
                color: #abb2bf;
                font-size: 14px;
            }
            #mainPanel {
                background-color: #3a3f4b; /* 比主背景稍亮的颜色 */
                border-radius: 12px;      /* 圆角效果 */
            }
            #statusBox {
                background: transparent;
            }
            #statusTitleLabel {
                background: transparent;
                font-weight: bold;
                font-size: 16px;
                padding: 6px 0px;
            }
            #statusIndicator {
                background-color: #e5c07b;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
                border-radius: 12px;
                border: 1px solid rgba(0,0,0,0.1);
            }
            #statusIndicator[ready="true"] {
                background-color: #98c379;
            }
            #readyButton {
                background-color: #61afef;
                color: white;
                font-size: 20px;
                font-weight: bold;
                padding: 10px 5px;
                border: none;
                border-radius: 8px;
            }
            #readyButton:hover { background-color: #528ab9; }
            #readyButton:disabled { background-color: #4b5263; color: #888; }
            #line { color: #3a3f4b; }
            QPushButton {
                background: transparent;
                border: none;
                font-weight: bold;
                font-size: 13px;
                padding: 4px;
            }
            #infoLabel { font-size: 11px; color: #5c6370; }
        """)

    def update_status_ui(self, state):
        self.update_single_status(self.my_status_widget, state['host_ready'])
        self.update_single_status(self.opponent_status_widget, state['participant_ready'])
        if self.socket_thread.sio.connected:
            self.ready_button.setEnabled(not state['host_ready'])

    def update_single_status(self, widget, is_ready):
        indicator = widget.findChild(QLabel, "statusIndicator")
        indicator.setProperty("ready", "true" if is_ready else "false")
        indicator.style().unpolish(indicator)
        indicator.style().polish(indicator)
        
    def on_connection_success(self):
        self.ready_button.setEnabled(True)
        self.set_pos_button.setEnabled(True)
        
    def capture_position(self):
        self.click_pos = pyautogui.position()
        self.pos_label.setText(f"({self.click_pos.x}, {self.click_pos.y})")
        self.show()

    def on_ready_click(self):
        self.ready_button.setEnabled(False)
        self.socket_thread.send_ready()

    def on_set_pos_click(self):
        self.pos_label.setText("3秒内校准...")
        self.hide()
        QTimer.singleShot(self.set_pos_delay, self.capture_position)

    def perform_click(self):
        if self.click_pos:
            try:
                # 1. 保存鼠标的当前位置
                original_pos = pyautogui.position()

                # 2. 执行方案一中成功的点击逻辑
                # 第一次点击，确保游戏窗口激活
                pyautogui.click(self.click_pos)
                time.sleep(0.1) # 等待窗口激活

                # 在已激活的窗口上，模拟一次完整的按下和抬起
                # pyautogui.moveTo(self.click_pos) # 这步可以省略，因为mouseDown/Up会自动移动
                pyautogui.mouseDown(self.click_pos, button='left')
                time.sleep(0.05) # 模拟按下的瞬间
                pyautogui.mouseUp(self.click_pos, button='left')
                
                # 3. 将鼠标平滑移回原始位置
                time.sleep(0.05)
                pyautogui.moveTo(original_pos)

            except Exception as e:
                QMessageBox.warning(self, "干涉错误", f"推进时间线时发生错误:\n{e}")
                if 'original_pos' in locals():
                    pyautogui.moveTo(original_pos, duration=0.2)
        else:
            QMessageBox.warning(self, "警告", "尚未锁定奇点坐标！")
            if self.socket_thread.sio.connected:
                self.ready_button.setEnabled(True)

    def show_connection_error(self):
        QMessageBox.critical(self, "链接中断", f"无法连接至阿克夏中枢: {self.server_url}。请检查config.ini文件和网络连接。")
        self.ready_button.setEnabled(False)
        self.set_pos_button.setEnabled(False)
    
    def closeEvent(self, event):
        self.socket_thread.stop()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())