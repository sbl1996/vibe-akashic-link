from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'c10a07fe5070c14fb1975fc9fe0398f65e367dc84d089160')
socketio = SocketIO(app, cors_allowed_origins="*")

# --- 状态管理 ---
# desktop_host_sid: 存储桌面客户端的SID，它是动作的唯一执行者。
# game_state: 存储当前一轮的准备状态。
desktop_host_sid = None
game_state = {
    'host_ready': False,
    'participant_ready': False,
}

@app.route('/')
def index():
    """提供角色选择页面"""
    return render_template('index.html')

@app.route('/client')
def main():
    """为参与者提供主操作界面"""
    server_url = f"http://{request.host}"
    # 从URL参数获取角色，默认为 'participant'
    role = request.args.get('role', 'participant')
    print(f"为角色 {role} 生成客户端页面，服务器地址: {server_url}")
    return render_template('main.html', server_url=server_url, role=role)

@socketio.on('connect')
def handle_connect():
    print(f'客户端连接: sid={request.sid}')
    # 新客户端连接时，向其单独发送一次最新状态
    emit('status_update', game_state)

@socketio.on('disconnect')
def handle_disconnect():
    global desktop_host_sid
    sid = request.sid
    print(f'客户端断开: sid={sid}')
    # 如果断开的是桌面主程序，这是个严重问题
    if sid == desktop_host_sid:
        print("!!! 警告：桌面主程序已断开！重置所有状态。 !!!")
        desktop_host_sid = None
        # 因为主程序断了，游戏无法继续，重置准备状态
        reset_game_state()
        emit('status_update', game_state, broadcast=True)

@socketio.on('register_host_client')
def handle_register_host():
    """
    专门用于桌面客户端注册自己身份的事件。
    """
    global desktop_host_sid
    desktop_host_sid = request.sid
    print(f"桌面主程序已注册，SID: {desktop_host_sid}")
    # 同时，如果桌面客户端重连，我们也重置游戏状态
    reset_game_state()
    emit('status_update', game_state, broadcast=True)

@socketio.on('ready')
def handle_ready(data):
    """处理玩家的“准备就绪”事件"""
    player = data.get('player')

    if player == 'host':
        game_state['host_ready'] = True
        print(f"角色 'host' (α) 已就绪 (来自 SID: {request.sid})")
    elif player == 'participant':
        game_state['participant_ready'] = True
        print(f"角色 'participant' (β) 已就绪 (来自 SID: {request.sid})")

    emit('status_update', game_state, broadcast=True)

    if game_state['host_ready'] and game_state['participant_ready']:
        print("双方均已就绪，准备向桌面主程序发送点击指令...")
        
        if desktop_host_sid:
            emit('proceed_click', to=desktop_host_sid)
            print(f"指令已发送至桌面主程序 SID: {desktop_host_sid}")
        else:
            print("错误：桌面主程序未连接，无法发送点击指令！")
        
        # 重置状态并广播
        reset_game_state()
        # 延迟一小下再广播重置状态，给点击事件留出执行时间，提升体验
        socketio.sleep(0.1) 
        emit('status_update', game_state, broadcast=True)
        print("状态已重置")

def reset_game_state():
    """重置准备状态"""
    game_state['host_ready'] = False
    game_state['participant_ready'] = False

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)