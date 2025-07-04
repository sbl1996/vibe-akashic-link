# Akashic Link

A simple client-server application to synchronize a mouse click on a host machine, triggered remotely by a participant. Ideal for cooperative actions in games or applications that require precise timing between two users. I originally developed this project to play visual novels (galgames) online with my girlfriend❤️.

## How It Works

The system consists of three main components: a central server, a desktop client for the "Host", and a web interface for the "Participant".

1.  **Server**: A Flask-SocketIO server that listens for "ready" signals from both the Host and the Participant.
2.  **Host Client**: A desktop application (PySide6) run by User A. This user pre-defines a specific coordinate on their screen to be clicked.
3.  **Participant Web UI**: A simple web page visited by User B.

**The Flow:**
1.  The Host runs the desktop app and "locks" a click position on their screen.
2.  The Participant opens the provided server URL in their browser.
3.  Both users click their respective "Ready" buttons.
4.  The server receives both "ready" signals and immediately sends a "Proceed" command to the Host's client.
5.  The Host's client automatically performs a mouse click at the pre-defined coordinate.

---

## Installation & Setup

You need to set up the server (on a machine accessible by both users, like a VPS) and the host client (on the machine that will perform the click).

### 1. Server Setup

The server coordinates the communication. It is recommended to run it on a Linux server.

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/sbl1996/vibe-akashic-link.git
    cd vibe-akashic-link
    ```

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install -r requirements.server.txt
    ```

3.  **Run the server:**
    *   **For development:**
        ```bash
        python server.py
        ```
    *   **For production (recommended):**
        The `scripts/serve.sh` script is provided to manage the server process with Gunicorn.
        ```bash
        # Make the script executable
        chmod +x scripts/serve.sh

        # Start the server on the default port 8080
        ./scripts/serve.sh start

        # To stop the server
        ./scripts/serve.sh stop

        # To check the status
        ./scripts/serve.sh status
        ```
    The server will be running on `0.0.0.0:8080`.

### 2. Host Client Setup

This is the desktop application for the user whose computer will perform the click.

1.  **Navigate to the host directory** from the project root.

2.  **Create a virtual environment and install dependencies:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    pip install PySide6 pyautogui "python-socketio[client]"
    ```

3.  **Configure the server URL:**
    *   In the `host/` directory, copy `config.ini.example` and rename it to `config.ini`.
    *   Edit `host/config.ini` and set the `url` to your server's address. For example:
        ```ini
        [Server]
        url = http://your_server_ip_or_domain:8080
        ```

4.  **Run the client:**
    ```bash
    python host/main.py
    ```

---
## Usage

1.  **Server Admin**: Start the server and share its public URL (e.g., `http://your_server_ip:8080`) with the Host and the Participant.

2.  **Host (User α)**:
    *   Launch the "Dimension Anchor" desktop app (`host/main.py`).
    *   Click **"⚡️ 锁定奇点"**. You have 3 seconds to move your mouse to the desired click location on your screen. The coordinates will be saved.
    *   When you are ready to synchronize, click **"吟唱"**. Your status light (α) will turn green.

3.  **Participant (User β)**:
    *   Open the server URL in a web browser.
    *   Click the button to launch the **"旅人罗盘"**. A small pop-up window will appear.
    *   When you are ready, click **"共鸣"**. Your status light (β) will turn green.

As soon as both users are ready, the Host's computer will instantly perform a mouse click at the locked location, and the status for both users will reset for the next synchronization.