#!/bin/bash

# --- 基础配置 ---
APP_NAME="server:app"
BIND_HOST="0.0.0.0"
DEFAULT_PORT="8080"
WORKERS=1
WORKER_CLASS="eventlet"

# --- 参数处理 ---
ACTION=$1
# 如果提供了第二个参数（端口），则使用它，否则使用默认端口
# 语法 ${2:-$DEFAULT_PORT} 表示如果 $2 未设置或为空，则使用 $DEFAULT_PORT
PORT=${2:-$DEFAULT_PORT}

# --- 动态配置（基于端口）---
# 根据端口号生成唯一的 PID 和日志文件名，以支持多实例
PID_FILE="gunicorn_${PORT}.pid"
LOG_FILE="server_${PORT}.log" # 每个实例使用独立的日志文件
# 组合成 Gunicorn 需要的绑定地址
BIND_ADDR="${BIND_HOST}:${PORT}"

# --- 函数 ---

# 检查服务是否正在运行
is_running() {
    # 检查是否有 gunicorn 进程正在监听指定的 BIND_ADDR
    if pgrep -f "gunicorn.*${BIND_ADDR}" > /dev/null; then
        return 0 # 正在运行
    fi
    return 1 # 未运行
}

# 启动服务
start() {
    if is_running; then
        MASTER_PID=$(pgrep -f "gunicorn: master \[${APP_NAME}\].*${BIND_ADDR}")
        echo "Gunicorn is already running on port ${PORT} (PID: ${MASTER_PID:-"N/A"})."
        return 1
    fi

    echo "Starting Gunicorn on port ${PORT}..."
    nohup gunicorn --pid ${PID_FILE} \
                   --worker-class ${WORKER_CLASS} \
                   -w ${WORKERS} \
                   --bind ${BIND_ADDR} \
                   ${APP_NAME} > ${LOG_FILE} 2>&1 &

    # 等待一小会儿，然后检查是否成功
    sleep 2
    if is_running; then
        echo "Gunicorn started successfully on port ${PORT} (PID: $(cat "$PID_FILE"))."
        echo "Log file: ${LOG_FILE}"
    else
        echo "Failed to start Gunicorn on port ${PORT}. Check ${LOG_FILE} for details."
        # 如果启动失败，清理可能遗留的无效 PID 文件
        if [ -f "$PID_FILE" ]; then
            rm "$PID_FILE"
        fi
        return 1
    fi
}

# 停止服务
stop() {
    echo "Attempting to stop Gunicorn on port ${PORT}..."

    # 使用 pgrep -f 来查找包含特定绑定地址的 gunicorn 进程
    PIDS=$(pgrep -f "gunicorn.*${BIND_ADDR}")

    if [ -z "$PIDS" ]; then
        echo "Gunicorn is not running on port ${PORT}."
        # 清理可能残留的无效 PID 文件
        if [ -f "$PID_FILE" ]; then
            echo "Cleaning up stale PID file: ${PID_FILE}"
            rm -f "$PID_FILE"
        fi
        return 1
    fi

    echo "Found Gunicorn processes with PIDs: $PIDS. Sending SIGTERM for graceful shutdown..."
    # 首先尝试优雅关闭 (SIGTERM)
    kill $PIDS > /dev/null 2>&1

    # 等待几秒钟让它们自己退出
    sleep 3

    # 再次检查是否还有进程残留
    PIDS_AFTER_TERM=$(pgrep -f "gunicorn.*${BIND_ADDR}")
    if [ -n "$PIDS_AFTER_TERM" ]; then
        echo "Graceful shutdown failed. Forcing shutdown (SIGKILL)..."
        # 如果还有残留，则强制杀死 (SIGKILL)
        kill -9 $PIDS_AFTER_TERM
    fi
    
    # 清理 PID 文件
    if [ -f "$PID_FILE" ]; then
        rm -f "$PID_FILE"
    fi
    
    echo "Gunicorn on port ${PORT} stopped."
}

# 显示特定端口的服务状态
status_port() {
    local target_port=$1
    local target_bind_addr="${BIND_HOST}:${target_port}"
    local target_pid_file="gunicorn_${target_port}.pid"

    PIDS=$(pgrep -f "gunicorn.*${target_bind_addr}")
    if [ -n "$PIDS" ]; then
        echo "Gunicorn is RUNNING on port ${target_port}."
        echo "----------------------------------------"
        echo "Processes found:"
        # 使用 ps 命令显示更详细的进程信息
        ps -f -p $PIDS
        echo "----------------------------------------"
    else
        echo "Gunicorn is NOT RUNNING on port ${target_port}."
        # 如果进程不在但 PID 文件还在，提示用户
        if [ -f "$target_pid_file" ]; then
            echo "Warning: Stale PID file found: ${target_pid_file}"
        fi
    fi
}

# 扫描所有正在运行的实例
status_all() {
    echo "Scanning for all running Gunicorn instances for app '${APP_NAME}'..."
    
    # 使用 pgrep -af 查找所有匹配的进程，并获取其完整的命令行参数
    # 然后用 grep 筛选出包含 '--bind' 参数的主进程
    local instances=$(pgrep -af "gunicorn.*${APP_NAME}" | grep '\--bind')

    if [ -z "$instances" ]; then
        echo "No running Gunicorn instances found."
        return
    fi

    echo ""
    echo "Found the following running instance(s):"
    echo "===================================================="
    printf "%-10s %-10s %s\n" "STATUS" "PORT" "MASTER_PID"
    echo "----------------------------------------------------"

    # 逐行处理找到的实例
    echo "$instances" | while IFS= read -r line; do
        # 从命令行中提取 PID
        local pid=$(echo "$line" | awk '{print $1}')
        # 使用 Bash 正则表达式从命令行中提取端口号
        if [[ "$line" =~ --bind[[:space:]]+[0-9.]+:([0-9]+) ]]; then
            local port="${BASH_REMATCH[1]}"
            printf "%-10s %-10s %s\n" "RUNNING" "$port" "$pid"
        fi
    done
    echo "===================================================="
    echo "Use './serve.sh status <PORT>' for more details."
    echo ""
}

# --- 主逻辑 ---

case "$ACTION" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        echo "Restarting Gunicorn on port ${PORT}..."
        stop
        # 稍微等待一下，确保端口已释放
        sleep 1
        start
        ;;
    status)
        # 如果提供了第二个参数 (端口号)，则显示特定端口的状态
        if [ -n "$2" ]; then
            status_port "$2"
        else
            # 否则，扫描并显示所有正在运行的实例
            status_all
        fi
        ;;
    *)
        echo "A management script for Gunicorn."
        echo ""
        echo "Usage: $0 {start|stop|restart|status} [port]"
        echo "  port (optional): The port to use. Defaults to ${DEFAULT_PORT}."
        echo ""
        echo "Examples:"
        echo "  ./serve.sh start          # Start on default port ${DEFAULT_PORT}"
        echo "  ./serve.sh start 9000     # Start on port 9000"
        echo "  ./serve.sh stop 9000      # Stop the instance on port 9000"
        echo "  ./serve.sh status         # Scan and list all running instances"
        echo "  ./serve.sh status 9000    # Show detailed status for port 9000"
        exit 1
        ;;
esac

exit 0