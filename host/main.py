import os
import time
from pathlib import Path
import sys
import pyautogui
import socketio
import configparser
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QLabel,
    QHBoxLayout,
    QMessageBox,
    QFrame,
    QGroupBox,
    QRadioButton,
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer, QPoint
from PySide6.QtGui import QIcon, QKeySequence

pyautogui.FAILSAFE = False


def resource_path(relative_path):
    """获取资源的绝对路径，无论是开发环境还是PyInstaller打包后"""
    try:
        # PyInstaller 创建一个临时文件夹，并把路径存储在 _MEIPASS 中
        base_path = sys._MEIPASS
    except Exception:
        # 在开发环境中，使用文件的当前路径
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def load_or_create_config(parent_window):
    """
    确定配置文件的最终路径。
    如果exe同级目录有config.ini，则使用它。
    如果没有，则从打包的资源中复制一份出来。
    """
    # 确定应用程序的根目录（exe所在目录或脚本所在目录）
    if getattr(sys, "frozen", False):  # 如果是打包后的 exe
        app_dir = Path(sys.executable).parent
    else:  # 如果是直接运行 .py 脚本
        app_dir = Path(__file__).parent

    user_config_path = app_dir / "config.ini"

    # 如果用户配置文件不存在，就从内部模板创建一份
    if not user_config_path.exists():
        QMessageBox.information(
            parent_window,
            "首次运行",
            f"已在以下位置创建默认配置文件:\n{user_config_path}\n请根据需要修改服务器地址。",
        )
        try:
            # resource_path() 会找到打包在exe内部的模板文件
            template_path = resource_path("config.ini")
            with open(template_path, "r", encoding="utf-8") as f_in:
                default_config = f_in.read()
            with open(user_config_path, "w", encoding="utf-8") as f_out:
                f_out.write(default_config)
        except Exception as e:
            # 如果创建失败，这是一个严重问题，需要通知用户
            QMessageBox.critical(
                None,
                "致命错误",
                f"无法创建默认配置文件！\n请检查程序是否有权限在以下目录写入文件：\n{app_dir}\n\n错误: {e}",
            )
            sys.exit(-1)  # 退出程序
    config = configparser.ConfigParser()
    config.read(str(user_config_path), encoding="utf-8")
    return config, user_config_path


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
            self.sio.emit("register_host_client")
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
            self.sio.connect(self.server_url, transports=["websocket"])
            self.sio.wait()
        except socketio.exceptions.ConnectionError as e:
            print(f"无法连接到服务器: {e}")
            self.connection_error.emit()

    def send_ready(self):
        if self.sio.connected:
            self.sio.emit("ready", {"player": "host"})

    def stop(self):
        if self.sio.connected:
            self.sio.disconnect()
        self.quit()
        self.wait()

class MainWindow(QMainWindow):
    action_completed = Signal()

    def __init__(self):
        super().__init__()
        self.click_pos = None
        self.action_mode = "click"
        self.is_capturing_hotkey = False

        try:
            self.config, self.config_path = load_or_create_config(self)
            self.server_url = self.config.get("Server", "url")
            self.set_pos_delay = self.config.getint("Settings", "set_pos_delay_ms")
            self.hotkey_name = self.config.get("Settings", "hotkey", fallback="RETURN")
            self.update_hotkey_from_name(self.hotkey_name)

        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            QMessageBox.critical(
                self,
                "配置错误",
                f"config.ini 文件格式不正确或缺少必要项。\n错误: {e}\n程序将退出。",
            )
            sys.exit(1)

        self.setWindowTitle("次元之锚")

        icon_path = resource_path("assets/icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            print(f"警告：找不到图标文件: {icon_path}")

        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.init_ui()
        self.apply_stylesheet()

        self.update_pos_button_state(False)

        self.action_completed.connect(self.on_action_finished)

        self.socket_thread = SocketIOThread(self.server_url)
        self.socket_thread.status_updated.connect(self.update_status_ui)
        self.socket_thread.proceed_click.connect(self.perform_action)
        self.socket_thread.connection_error.connect(self.show_connection_error)
        self.socket_thread.connection_success.connect(self.on_connection_success)
        self.socket_thread.start()

    def on_action_finished(self):
        if not self.socket_thread.sio.connected:
            self.ready_button.setEnabled(False)
        else:
            self.ready_button.setEnabled(True)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        # 主布局，负责整体垂直排列，并用伸缩项将其居中
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(15)

        # --- 左侧面板：状态和主操作按钮 ---
        left_panel = QFrame()
        left_panel.setObjectName("mainPanel")
        left_panel_layout = QVBoxLayout(left_panel)
        left_panel_layout.setContentsMargins(20, 15, 20, 15)
        left_panel_layout.setSpacing(15)

        status_panel = QHBoxLayout()
        self.my_status_widget = self.create_status_box("α", "myStatusTitleLabel")
        self.opponent_status_widget = self.create_status_box(
            "β", "opponentStatusTitleLabel"
        )
        status_panel.addWidget(self.my_status_widget)
        status_panel.addWidget(self.opponent_status_widget)

        self.ready_button = QPushButton("吟   唱")
        self.ready_button.setObjectName("readyButton")
        self.ready_button.clicked.connect(self.on_ready_click)
        self.ready_button.setEnabled(False)

        left_panel_layout.addStretch(1)
        left_panel_layout.addLayout(status_panel)
        left_panel_layout.addWidget(self.ready_button)
        left_panel_layout.addStretch(1)

        # --- 右侧面板：所有设置项 ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 5, 0, 5)
        right_layout.setSpacing(10)

        # 动作模式设置
        action_group_box = QGroupBox("动作模式")
        action_layout = QHBoxLayout()

        self.radio_click = QRadioButton("Click")
        self.radio_click.setChecked(True)
        self.radio_click.toggled.connect(self.on_action_mode_changed)

        self.radio_scroll = QRadioButton("Scroll")
        self.radio_scroll.toggled.connect(self.on_action_mode_changed)

        action_layout.addWidget(self.radio_click)
        action_layout.addWidget(self.radio_scroll)
        action_group_box.setLayout(action_layout)

        # 奇点坐标设置
        pos_group_box = QGroupBox("奇点坐标")
        pos_layout = QHBoxLayout(pos_group_box)
        pos_layout.setSpacing(8)
        self.set_pos_button = QPushButton("⚡️ 锁定奇点")
        self.set_pos_button.setObjectName("setPosButton")
        self.set_pos_button.setProperty("locked", "false")
        self.set_pos_button.clicked.connect(self.on_set_pos_click)
        self.set_pos_button.setEnabled(False)
        pos_layout.addWidget(self.set_pos_button)

        # 快捷键设置
        hotkey_group_box = QGroupBox("吟唱按键")
        hotkey_layout = QHBoxLayout(hotkey_group_box)
        self.set_hotkey_button = QPushButton()
        self.set_hotkey_button.setObjectName("setHotkeyButton")
        self.set_hotkey_button.clicked.connect(self.on_set_hotkey_click)
        self.update_hotkey_button_text()  # 设置初始文本
        hotkey_layout.addWidget(self.set_hotkey_button)

        right_layout.addStretch(1)
        right_layout.addWidget(action_group_box)
        right_layout.addWidget(pos_group_box)
        right_layout.addWidget(hotkey_group_box)
        right_layout.addStretch(1)

        left_panel.setFixedWidth(180)
        main_layout.addWidget(left_panel)
        main_layout.addWidget(right_panel)

        self.setFixedSize(360, 200)

    def create_status_box(self, title, object_name):
        widget = QWidget()
        widget.setObjectName("statusBox")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        title_label = QLabel(title)
        title_label.setObjectName(object_name)
        title_label.setAlignment(Qt.AlignCenter)

        status_indicator = QLabel()
        status_indicator.setObjectName("statusIndicator")
        status_indicator.setProperty("ready", "false")

        layout.addWidget(title_label)
        layout.addWidget(status_indicator)
        layout.setAlignment(Qt.AlignCenter)
        return widget

    def apply_stylesheet(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background-color: #282c34;
                color: #abb2bf;
                font-size: 14px;
            }
            #mainPanel {
                background-color: #3a3f4b; /* 比主背景稍亮的颜色 */
                border-radius: 12px;      /* 圆角效果 */
            }
            QGroupBox {
                color: #9da5b4;
                font-size: 11px;
                border: 1px solid #3a3f4b;
                border-radius: 4px;
                margin-top: 1ex;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 3px;
            }
            QRadioButton {
                font-size: 12px;
            }
            #statusBox { background: transparent; }
            #myStatusTitleLabel {
                background: transparent;
                font-weight: bold;
                font-size: 16px;
                padding: 6px 0px;
                color: #61afef;
            }
            #opponentStatusTitleLabel {
                background: transparent;
                font-weight: bold;
                font-size: 16px;
                padding: 6px 0px;
                color: #e06c75;
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
            
            #setPosButton, #setHotkeyButton {
                background-color: #56b6c2;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 4px 12px;
                font-size: 13px;
                font-weight: bold;
            }
            #setPosButton:hover, #setHotkeyButton:hover {
                background-color: #489ba3;
            }
            #setPosButton:disabled {
                background-color: #3a3f4b;
                color: #5c6370;
            }

            #setPosButton[locked="true"] {
                background-color: #98c379;
                color: white;
            }
            #setPosButton[locked="true"]:hover {
                background-color: #82b36a;
            }
        """
        )

    def update_hotkey_from_name(self, key_name):
        """根据按键名称字符串更新Qt.Key值"""
        self.hotkey_name = key_name.upper()
        key_sequence = QKeySequence.fromString(self.hotkey_name)
        if not key_sequence.isEmpty():
            self.hotkey = key_sequence[0]
            print(self.hotkey)
        else:
            fallback_key = "RETURN"
            self.hotkey_name = fallback_key
            self.hotkey = QKeySequence.fromString(fallback_key)[0]
            QMessageBox.warning(
                self, "快捷键警告", f"无法识别的快捷键 '{key_name}'，已重置为 {fallback_key}。"
            )

    def update_hotkey_button_text(self):
        """更新设置快捷键按钮的文本"""
        if self.is_capturing_hotkey:
            self.set_hotkey_button.setText("请按下按键...")
        else:
            self.set_hotkey_button.setText(f"{self.hotkey_name}")

    def save_config(self):
        """保存当前配置到config.ini文件"""
        try:
            self.config.set("Settings", "hotkey", self.hotkey_name)
            with open(self.config_path, "w", encoding="utf-8") as configfile:
                self.config.write(configfile)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存配置文件：\n{e}")

    def keyPressEvent(self, event):
        """重写此方法以捕获和响应快捷键"""
        if self.is_capturing_hotkey:
            key = event.key()
            # 忽略单独的修饰键（Ctrl, Shift, Alt）
            if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
                return

            # 将按键代码转换为可读字符串
            key_name = QKeySequence(key).toString(QKeySequence.NativeText).upper()
            if key_name:
                self.update_hotkey_from_name(key_name)
                self.save_config()

            self.is_capturing_hotkey = False
            self.update_hotkey_button_text()
            event.accept()
            return

        # 如果不是在设置快捷键，并且按下的键是已设定的热键
        if not event.isAutoRepeat() and event.key() == self.hotkey.key():
            if self.ready_button.isEnabled():
                print(f"快捷键 {self.hotkey_name} 按下，触发吟唱。")
                self.on_ready_click()
                event.accept()
                return

        super().keyPressEvent(event)  # 将事件传递给父类

    def on_set_hotkey_click(self):
        """当用户点击“设置快捷键”按钮时调用"""
        self.is_capturing_hotkey = True
        self.update_hotkey_button_text()
        self.set_hotkey_button.setDown(False)  # 立即弹起按钮

    def update_status_ui(self, state):
        self.update_single_status(self.my_status_widget, state["host_ready"])
        self.update_single_status(
            self.opponent_status_widget, state["participant_ready"]
        )
        if self.socket_thread.sio.connected:
            self.ready_button.setEnabled(not state["host_ready"])

    def update_single_status(self, widget, is_ready):
        indicator = widget.findChild(QLabel, "statusIndicator")
        indicator.setProperty("ready", "true" if is_ready else "false")
        indicator.style().unpolish(indicator)
        indicator.style().polish(indicator)

    def update_pos_button_state(self, is_locked):
        """更新锁定奇点按钮的视觉状态和文本。"""
        self.set_pos_button.setProperty("locked", "true" if is_locked else "false")

        if is_locked:
            self.set_pos_button.setText("✔️ 锁定完成")
            if self.click_pos:
                self.set_pos_button.setToolTip(
                    f"奇点已锁定: ({self.click_pos.x}, {self.click_pos.y})"
                )
        else:
            self.set_pos_button.setText("⚡️ 锁定奇点")
            self.set_pos_button.setToolTip(
                f"点击后在 {self.set_pos_delay / 1000:.1f} 秒内捕获鼠标位置"
            )
        self.set_pos_button.style().unpolish(self.set_pos_button)
        self.set_pos_button.style().polish(self.set_pos_button)

    def on_connection_success(self):
        self.ready_button.setEnabled(True) 
        self.set_pos_button.setEnabled(True)
        self.on_action_mode_changed()
        self.update_pos_button_state(False)

    def capture_position(self):
        self.click_pos = pyautogui.position()
        self.update_pos_button_state(True)
        self.show()
        self.raise_()
        self.activateWindow()

    def on_ready_click(self):
        # 增加一个检查，防止在设置快捷键时触发
        if self.is_capturing_hotkey:
            return
        self.ready_button.setEnabled(False)
        self.socket_thread.send_ready()

    def on_set_pos_click(self):
        # 每次点击锁定都应该重置状态，等待新的坐标
        self.update_pos_button_state(False)
        self.click_pos = None
        self.hide()
        QTimer.singleShot(self.set_pos_delay, self.capture_position)

    def on_action_mode_changed(self):
        is_click_mode = self.radio_click.isChecked()
        self.action_mode = "click" if is_click_mode else "scroll"
        print(f"动作模式已切换为: {self.action_mode}")
        if self.socket_thread.sio.connected:
            self.set_pos_button.setEnabled(True)

    def perform_action(self):
        if self.action_mode == "click":
            self.perform_click_action()
        elif self.action_mode == "scroll":
            self.perform_scroll_action()

    def perform_click_action(self):
        if not self.click_pos:
            QMessageBox.warning(self, "警告", "尚未锁定奇点坐标！")
            self.action_completed.emit()
            return

        original_pos = None
        try:
            # 1. 保存鼠标的当前位置
            original_pos = pyautogui.position()
            refocus_pos = (original_pos.x, original_pos.y - 50)

            # 2. 执行点击逻辑
            pyautogui.click(self.click_pos)
            time.sleep(0.1)
            pyautogui.mouseDown(self.click_pos, button="left")
            time.sleep(0.05)
            pyautogui.mouseUp(self.click_pos, button="left")
            time.sleep(0.05)

            pyautogui.click(refocus_pos)
            time.sleep(0.05)

            pyautogui.moveTo(original_pos)
        except Exception as e:
            QMessageBox.warning(self, "干涉错误", f"推进时间线时发生错误:\n{e}")
            if original_pos:
                pyautogui.moveTo(original_pos, duration=0.2)
        finally:
            self.action_completed.emit()

    def perform_scroll_action(self):
        if not self.click_pos:
            QMessageBox.warning(self, "警告", "尚未锁定奇点坐标！")
            self.action_completed.emit() # 即使失败也要发射信号
            return
            
        original_pos = None
        try:
            original_pos = pyautogui.position()
            refocus_pos = (original_pos.x, original_pos.y - 50)

            pyautogui.click(self.click_pos)
            time.sleep(0.1) 
            pyautogui.moveTo(self.click_pos)
            time.sleep(0.05)
            pyautogui.scroll(-120)
            time.sleep(0.05)

            pyautogui.click(refocus_pos)
            time.sleep(0.05)

            pyautogui.moveTo(original_pos)
        except Exception as e:
            QMessageBox.warning(self, "干涉错误", f"执行滚轮操作时发生错误:\n{e}")
        finally:
            self.action_completed.emit()

    def show_connection_error(self):
        QMessageBox.critical(
            self,
            "链接中断",
            f"无法连接至阿克夏中枢: {self.server_url}。请检查config.ini文件和网络连接。",
        )
        self.ready_button.setEnabled(False)
        self.set_pos_button.setEnabled(False)
        self.update_pos_button_state(False)

    def closeEvent(self, event):
        # 确保在关闭时，如果正在设置快捷键，则取消该状态
        if self.is_capturing_hotkey:
            self.is_capturing_hotkey = False
        self.socket_thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
