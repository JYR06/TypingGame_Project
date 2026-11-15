import os
import socket
import threading
import tkinter as tk
import time

from net_viewer import NetViewer

# ========================================
# 1. 서버 연결 설정
# ========================================
HOST = "127.0.0.1"
PORT = int(os.environ.get("TYPING_PORT", 5000))  # 기본 5000, 테스트용으로 환경변수로 바꿀 수 있음
HEARTBEAT_INTERVAL = 3
HEARTBEAT_TIMEOUT = 9
CONNECT_RETRIES = 20   # 0.5초 간격 → 최대 10초 동안 서버를 기다림

sock = None            # 현재 연결된 소켓
connected = False
connecting = False
generation = 0         # 접속할 때마다 1씩 증가 (= 세션 번호). 예전 연결의 스레드가 새 연결을 건드리지 않게 구분한다.
window_open = True
last_pong = time.time()
state_lock = threading.Lock()   # 위 연결 상태 변수 보호
send_lock = threading.Lock()    # 여러 스레드가 동시에 sendall 하지 않게


# ========================================
# 2. 게임 화면(UI) 디자인 만들기
# ========================================
window = tk.Tk()
window.title("타이핑 워리어: 스미스 씨의 악몽")
ui_scale = max(1.0, window.winfo_fpixels("1i") / 96.0)  # 화면 배율(125%, 150% 등) 반영
window.geometry(f"{int(760 * ui_scale)}x{int(640 * ui_scale)}") # 창 크기
window.configure(bg="#16161a") # 힙한 다크 네이비 배경

viewer = NetViewer(window)  # OSI 7계층 네트워크 뷰어 창


def run_on_ui(fn, *args):
    """네트워크 스레드가 Tkinter 화면을 직접 만지지 않도록 메인 스레드에 맡긴다."""
    if not window_open:
        return
    try:
        window.after(0, fn, *args)
    except (RuntimeError, tk.TclError):
        pass


# 화면에 글자를 띄워주는 함수 (색깔별로!)
def display_message(msg, color_tag):
    chat_box.config(state=tk.NORMAL) # 글자를 쓸 수 있게 잠금 해제
    chat_box.insert(tk.END, msg + "\n", color_tag) # 맨 아래에 글자 추가
    chat_box.see(tk.END) # 스크롤을 항상 맨 아래로!
    chat_box.config(state=tk.DISABLED) # 다시 읽기 전용으로 잠금

def display_from_network(msg, color_tag):
    run_on_ui(display_message, msg, color_tag)

# 안개 방해 효과 함수
def trigger_fog(duration_ms=4000):
    def apply_fog():
        # 문제 및 채팅 영역을 완전히 덮는 어두운 안개 프레임 생성
        fog_frame = tk.Frame(chat_box, bg='#1a1c23')
        fog_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        # 안개 시각 텍스트
        fog_lable = tk.Label(fog_frame, text="🌫️ 짙은 안개가 자욱합니다... 🌫️\n(시야 방해 중)", font=("맑은 고딕", 18, "bold"), fg="#94a1b2", bg="#1a1c23")
        fog_lable.pack(expand=True)
        # 일정 시간(기본 4초) 후 안개 프레임 제거
        window.after(duration_ms, fog_frame.destroy)
    # Tkinter GUI 메인 스레드에서 안전하게 실행되도록 스케줄링
    run_on_ui(apply_fog)


def make_button(parent, text, command, bg="#242629", fg="#fffffe"):
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground="#3a3550",
                     activeforeground="#fffffe", disabledforeground="#5f6c7b", relief=tk.FLAT, bd=0,
                     padx=14, pady=6, font=("맑은 고딕", 10, "bold"), cursor="hand2")


# 위쪽 상태 바: 연결 상태 + 네트워크 뷰어 버튼
status_bar = tk.Frame(window, bg="#242629", padx=12, pady=6)
status_bar.pack(fill=tk.X, side=tk.TOP)
status_label = tk.Label(status_bar, text="● 연결 안 됨", fg="#94a1b2", bg="#242629", font=("맑은 고딕", 10, "bold"))
status_label.pack(side=tk.LEFT)
viewer_btn = make_button(status_bar, "📡 네트워크 뷰어", viewer.toggle, bg="#16161a")
viewer_btn.pack(side=tk.RIGHT)

# 입력창 테두리 (디자인 용도)
input_frame = tk.Frame(window, bg="#242629", pady=10)
input_frame.pack(fill=tk.X, side=tk.BOTTOM)

# 내가 타자를 치는 입력창
entry = tk.Entry(input_frame, bg="#242629", fg="#2cb67d", font=("맑은 고딕", 14, "bold"), bd=0, insertbackground="#2cb67d")
entry.pack(fill=tk.X, padx=20, pady=5)
entry.focus() # 켜자마자 바로 타자를 칠 수 있게 커서 깜빡이기

# 버튼 줄: 다시 하기(준비) / 재접속
button_frame = tk.Frame(window, bg="#16161a", padx=20, pady=6)
button_frame.pack(fill=tk.X, side=tk.BOTTOM)

# 게임 메시지 창 (채팅 내역과 문제가 나오는 곳)
chat_box = tk.Text(window, bg="#16161a", fg="#fffffe", font=("맑은 고딕", 12, "bold"), bd=0, padx=20, pady=20)
chat_box.pack(fill=tk.BOTH, expand=True)
chat_box.config(state=tk.DISABLED) # 마우스로 글자를 수정 못 하게 막음

# 🎨 힙한 네온 색상 태그 설정
chat_box.tag_config("chat", foreground="#94a1b2")       # 일반 채팅: 회색
chat_box.tag_config("game", foreground="#2cb67d", font=("맑은 고딕", 16, "bold")) # 게임 문제: 네온 그린 (크게!)
chat_box.tag_config("system", foreground="#ef4565")     # 시스템 알림: 네온 핑크
chat_box.tag_config("notice", foreground="#7f5af0")     # 공지: 네온 퍼플


# ========================================
# 3. 보내기
# ========================================
def send_packet(tag, content=""):
    """서버와 약속한 줄바꿈 기반 패킷 형식(tag|content\\n)으로 안전하게 전송한다."""
    data = f"{tag}|{content}\n".encode("utf-8")
    with state_lock:
        s = sock if connected else None
        gen = generation
    if s is None:
        return False
    try:
        with send_lock:
            s.sendall(data)
    except OSError:
        drop_connection(gen, "전송 오류")
        return False
    viewer.log_packet("send", tag, content, data)
    return True


# [입 역할] 엔터(Enter) 키를 누르면 메시지 서버로 보내기
def send_message(event=None):
    message = entry.get() # 입력창에 쓴 글자 가져오기
    if message.lower() == "exit":
        close_window()
        return

    if message.strip(): # 비어있지 않을 때만 전송
        if not send_packet("chat", message):
            display_message("[서버와 연결되어 있지 않아요. 🔌 재접속을 눌러 주세요.]", "system")
        entry.delete(0, tk.END) # 보낸 뒤에 입력창 비우기

entry.bind("<Return>", send_message)


# ========================================
# 4. 재시작 기능: 다시 하기(게임) / 재접속(연결)
# ========================================
def press_ready():
    """다시 하기 = 서버에 '준비 완료'를 알린다. 모두 준비하면 3초 카운트다운 후 새 판 시작."""
    if not send_packet("ready"):
        display_message("[서버와 연결되어 있지 않아요. 🔌 재접속을 눌러 주세요.]", "system")


def press_reconnect():
    """재접속 = 지금 연결을 끊고 새 TCP 연결(새 세션)을 맺는다."""
    with state_lock:
        gen = generation
        was_connected = connected
    if was_connected:
        drop_connection(gen, "사용자가 재접속을 요청함", announce=False)
    start_connect()


ready_btn = make_button(button_frame, "🔄 다시 하기 (준비)", press_ready, bg="#7f5af0")
ready_btn.pack(side=tk.LEFT)
reconnect_btn = make_button(button_frame, "🔌 재접속", press_reconnect)
reconnect_btn.pack(side=tk.LEFT, padx=(8, 0))
hint_label = tk.Label(button_frame, text="'/재시작' 입력 = 진행 중인 판 리셋", fg="#5f6c7b", bg="#16161a", font=("맑은 고딕", 9))
hint_label.pack(side=tk.RIGHT)

game_state = "lobby"


def set_game_state(state):
    """서버가 보내주는 state 패킷에 맞춰 '다시 하기' 버튼 모양을 바꾼다."""
    global game_state
    game_state = state
    update_buttons()


def update_buttons():
    with state_lock:
        is_connected, is_connecting = connected, connecting
    if is_connecting:
        reconnect_btn.config(text="⏳ 연결 중...", state=tk.DISABLED)
    else:
        reconnect_btn.config(text="🔌 재접속", state=tk.NORMAL)

    if not is_connected:
        ready_btn.config(text="🔄 다시 하기 (준비)", state=tk.DISABLED, bg="#242629")
    elif game_state == "playing":
        ready_btn.config(text="🎮 게임 진행 중", state=tk.DISABLED, bg="#242629")
    elif game_state == "countdown":
        ready_btn.config(text="⏳ 곧 시작!", state=tk.DISABLED, bg="#242629")
    else:
        ready_btn.config(text="🔄 다시 하기 (준비)", state=tk.NORMAL, bg="#7f5af0")

    if is_connected:
        status_label.config(text=f"● 연결됨 · 세션 #{generation} · 서버 {HOST}:{PORT}", fg="#2cb67d")
    elif is_connecting:
        status_label.config(text=f"● 연결 중... ({HOST}:{PORT})", fg="#f9bc60")
    else:
        status_label.config(text="● 연결 끊김 · 🔌 재접속을 눌러 주세요", fg="#ef4565")


# ========================================
# 5. 연결 / 끊기
# ========================================
def start_connect():
    global connecting
    with state_lock:
        if connecting or connected:
            return
        connecting = True
    update_buttons()
    display_message(f"[서버 {HOST}:{PORT} 에 연결 중...]", "system")
    threading.Thread(target=connect_worker, daemon=True).start()


def connect_worker():
    """서버가 켜질 때까지 잠시 재시도하면서 TCP 연결을 맺는다."""
    global sock, connected, connecting, generation, last_pong
    viewer.session_event("connecting", target=(HOST, PORT))
    s = None
    handshake_ms = 0.0
    for _ in range(CONNECT_RETRIES):
        if not window_open:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        t0 = time.perf_counter()
        try:
            s.connect((HOST, PORT))  # 이 순간 OS가 TCP 3-way 핸드셰이크를 한다
            handshake_ms = (time.perf_counter() - t0) * 1000
            break
        except OSError:
            s.close()
            s = None
            time.sleep(0.5)

    if s is None:
        with state_lock:
            connecting = False
        viewer.session_event("failed", reason=f"{HOST}:{PORT} 에 {CONNECT_RETRIES}번 시도했지만 응답 없음")
        display_from_network("[서버에 연결할 수 없습니다. 서버를 켠 뒤 🔌 재접속을 눌러 주세요.]", "system")
        run_on_ui(update_buttons)
        return

    with state_lock:
        generation += 1
        gen = generation
        sock = s
        connected = True
        connecting = False
        last_pong = time.time()
    viewer.session_event("connected", local=s.getsockname(), remote=s.getpeername(),
                         handshake_ms=handshake_ms, session=gen)
    display_from_network(f"[서버 연결됨 · 세션 #{gen} · 내 포트 {s.getsockname()[1]}]", "notice")
    threading.Thread(target=receive_loop, args=(s, gen), daemon=True).start()
    threading.Thread(target=heartbeat_loop, args=(gen,), daemon=True).start()
    run_on_ui(update_buttons)


def drop_connection(gen, reason, announce=True):
    """연결을 정리한다. 이미 정리됐거나 예전 세션(gen)이면 아무것도 하지 않는다."""
    global connected, sock
    with state_lock:
        if gen != generation or not connected:
            return
        connected = False
        s = sock
        sock = None
    try:
        s.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    s.close()
    viewer.session_event("closed", reason=reason)
    if announce:
        display_from_network(f"[연결이 끊어졌습니다: {reason}] 🔌 재접속 버튼으로 다시 연결할 수 있어요.", "system")
    run_on_ui(update_buttons)


# ========================================
# 6. 듣기 / 하트비트
# ========================================
def handle_packet(tag, content):
    global last_pong
    content = content.replace("\\n", "\n")  # 서버가 '\\n' 기호로 바꿔 보낸 줄바꿈 복원
    # 하트비트 패킷은 화면에 출력하지 않는다.
    if tag == "ping":
        send_packet("pong", content)
    elif tag == "pong":
        with state_lock:
            last_pong = time.time()
        try:
            rtt_ms = (time.perf_counter_ns() // 1000 - int(content)) / 1000
            viewer.record_rtt(rtt_ms)
        except ValueError:
            pass
    # 1. 일반 채팅 (회색)
    elif tag == "chat":
        display_from_network(content, "chat")
    # 2. 게임 문제 (네온 그린 + 크고 두껍게)
    elif tag == "game":
        display_from_network(f" 👉  {content}\n", "game")
    # 3. 오타 경고나 현재 스테이지 알림 (네온 핑크)
    elif tag == "system":
        display_from_network(content, "system")
    # 4. 우승자 공지 (네온 퍼플)
    elif tag == "notice":
        display_from_network("\n=========================================", "notice")
        display_from_network(content, "notice")
        display_from_network("=========================================\n", "notice")
    # 5. 아이템 효과 수신
    elif tag == "item":
        if content == "fog":
            trigger_fog(4000)
    # 6. 게임 상태 (다시 하기 버튼 모양 바꾸기)
    elif tag == "state":
        run_on_ui(set_game_state, content)


# [귀 역할] 서버 소식을 계속 듣기
def receive_loop(s, gen):
    # 바이트 단위로 모아야 한글(3바이트)이 recv 경계에서 잘려도 깨지지 않는다.
    buffer = b""
    reason = "서버가 연결을 닫음"
    try:
        while True:
            data = s.recv(4096)
            if not data:
                break
            buffer += data
            lines = buffer.split(b"\n")
            buffer = lines.pop()  # 마지막 조각은 아직 \n이 안 온 미완성 메시지
            for i, line in enumerate(lines, 1):
                text = line.decode("utf-8", errors="replace")
                if "|" not in text:
                    continue
                tag, content = text.split("|", 1)
                viewer.log_packet("recv", tag, content, line + b"\n",
                                  chunk_size=len(data), chunk_index=i, chunk_msgs=len(lines))
                handle_packet(tag, content)
    except OSError as e:
        reason = f"네트워크 오류 ({e.__class__.__name__})"
    drop_connection(gen, reason)


def heartbeat_loop(gen):
    """3초마다 ping을 보내고, 9초 안에 pong이 없으면 연결 끊김으로 처리한다."""
    while window_open:
        time.sleep(HEARTBEAT_INTERVAL)
        with state_lock:
            if gen != generation or not connected:
                return
            age = time.time() - last_pong
        if age > HEARTBEAT_TIMEOUT:
            drop_connection(gen, f"하트비트 시간 초과 ({HEARTBEAT_TIMEOUT}초 동안 pong 없음)")
            return
        # 마이크로초 타임스탬프를 실어 보내면 서버가 그대로 돌려줘서 왕복 시간(RTT)을 잴 수 있다.
        send_packet("ping", str(time.perf_counter_ns() // 1000))


def close_window():
    global window_open, connected
    window_open = False
    with state_lock:
        connected = False
        s = sock
    if s is not None:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        s.close()
    window.destroy()


# 시작할 때 환영 인사
display_message("🎮 타이핑 워리어에 오신 것을 환영합니다!", "notice")
display_message("'🔄 다시 하기' 버튼(또는 '시작' 입력)으로 준비하세요. 모두 준비하면 3초 뒤 시작해요.", "chat")
display_message("'/재시작'을 입력하면 진행 중인 판을 리셋해요. 📡 네트워크 뷰어에서 패킷을 OSI 7계층으로 볼 수 있어요.\n", "chat")

update_buttons()
start_connect()

# 화면(UI) 띄우기 시작! (이 코드가 있어야 화면이 계속 켜져있어요)
window.protocol("WM_DELETE_WINDOW", close_window)
window.mainloop()
