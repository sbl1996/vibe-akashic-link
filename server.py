from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'c10a07fe5070c14fb1975fc9fe0398f65e367dc84d089160')
socketio = SocketIO(app, cors_allowed_origins="*")

# 存储游戏会话状态
# 在真实的多房间应用中，你会用一个字典来管理多个房间的状态
# 但对于你们两人使用，一个全局状态就足够了。
game_state = {
    'host_ready': False,
    'participant_ready': False,
    'host_sid': None
}

@app.route('/')
def index():
    """为参与者提供Web界面"""
    return render_template('index.html')

@app.route('/client')
def main():
    """为参与者提供Web界面"""
    server_url = f"http://{request.host}" # 自动获取服务器地址
    print(f"server_url: {server_url}")
    return render_template('main.html', server_url=server_url)

@socketio.on('connect')
def handle_connect():
    # 使用 request.sid 获取当前连接的客户端ID
    print(f'客户端连接: sid={request.sid}')
    # 新客户端连接时，向其单独发送一次最新状态
    emit('status_update', game_state)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f'客户端断开: sid={sid}')
    # 如果断开的是主持人，重置状态以防万一
    if sid == game_state['host_sid']:
        print("主持人已断开，重置游戏。")
        reset_game_state()
        emit('status_update', game_state, broadcast=True)

@socketio.on('ready')
def handle_ready(data):
    """处理玩家的“准备就绪”事件，并在这里捕获SID"""
    player = data.get('player')
    sid = request.sid # 获取发送此事件的客户端的SID

    if player == 'host':
        game_state['host_ready'] = True
        # ✨ 关键修改：在这里，我们捕获并保存主持人的sid
        game_state['host_sid'] = sid
        print(f"主持人已就绪 (SID: {sid})")
    elif player == 'participant':
        game_state['participant_ready'] = True
        print(f"参与者已就绪 (SID: {sid})")

    # 广播状态更新
    emit('status_update', game_state, broadcast=True)

    # 检查是否双方都已就绪
    if game_state['host_ready'] and game_state['participant_ready']:
        host_sid_to_notify = game_state['host_sid']
        
        print(f"双方均已就绪，准备向主持人 (SID: {host_sid_to_notify}) 发送点击指令...")
        
        if host_sid_to_notify:
            # 只向主持人发送“执行点击”指令
            emit('proceed_click', to=host_sid_to_notify)
            print(f"指令已发送至 SID: {host_sid_to_notify}")
        else:
            print("错误：host_sid 未定义，无法发送点击指令！")
        
        # 重置状态并广播
        reset_game_state()
        # 延迟一小下再广播重置状态，给点击事件留出执行时间，提升体验
        socketio.sleep(0.1) 
        emit('status_update', game_state, broadcast=True)
        print("状态已重置")

def reset_game_state():
    """重置准备状态，但保留SID用于断线重连等场景"""
    game_state['host_ready'] = False
    game_state['participant_ready'] = False
    # 注意：我们不清空 host_sid，这样如果主持人没断线，下次点击时仍然有效

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8080, debug=True)