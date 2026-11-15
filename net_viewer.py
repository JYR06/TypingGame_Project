"""
타이핑 배틀 네트워크 뷰어
- 클라이언트가 주고받는 모든 패킷을 OSI 7계층 관점으로 보여주는 창
- 보낼 때는 7계층 → 1계층으로 내려가고(캡슐화), 받을 때는 1계층 → 7계층으로 올라간다(역캡슐화).
- 4~7계층과 IP 주소는 실제 값이고, 1~2계층은 OS·하드웨어가 처리해 파이썬에서 볼 수 없어 설명으로 보여준다.

다른 스레드에서 호출해도 되는 함수: log_packet, session_event, record_rtt
"""
import time
import tkinter as tk
from tkinter import ttk
from collections import deque

BG = "#16161a"
PANEL = "#242629"
FG = "#fffffe"
MUTED = "#94a1b2"
FONT = "맑은 고딕"
MONO = "Consolas"

SEND_COLOR = "#3da9fc"
RECV_COLOR = "#2cb67d"
SESSION_COLOR = "#f9bc60"
HB_COLOR = "#5f6c7b"

LAYERS = [
    (7, "응용", "Application", "#7f5af0"),
    (6, "표현", "Presentation", "#b388ff"),
    (5, "세션", "Session", "#2cb67d"),
    (4, "전송", "Transport", "#3da9fc"),
    (3, "네트워크", "Network", "#f9bc60"),
    (2, "데이터링크", "Data Link", "#ef4565"),
    (1, "물리", "Physical", "#94a1b2"),
]
LAYER_NAME = {num: f"{num}계층 {ko} ({en})" for num, ko, en, _ in LAYERS}

HEARTBEAT_TAGS = ("ping", "pong")
MAX_RECORDS = 500
HEARTBEAT_TIMEOUT = 9

TAG_MEANING = {
    "chat": "채팅 / 답안 문장",
    "game": "출제된 문제 문장",
    "system": "시스템 알림",
    "notice": "우승 공지",
    "item": "아이템 효과 (안개 폭탄)",
    "ping": "살아있니? (생존 확인 요청)",
    "pong": "응, 살아있어 (생존 확인 응답)",
    "ready": "다시 하기 준비 완료",
    "state": "게임 상태 변경 (lobby / countdown / playing / ended)",
}

SESSION_LABEL = {
    "connecting": "연결 시도",
    "connected": "연결됨",
    "closed": "연결 종료",
    "failed": "연결 실패",
}


# ----------------------------------------
# 작은 도우미 함수들
# ----------------------------------------
def blend(color, base, alpha):
    """color를 base 위에 alpha 비율로 섞은 색 (하이라이트용)."""
    c = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(b[k] + (c[k] - b[k]) * alpha) for k in range(3)]
    return "#" + "".join(f"{v:02x}" for v in mixed)


def addr_or_unknown(addr):
    return addr if addr else ("?", "?")


def fmt_addr(addr):
    return f"{addr[0]}:{addr[1]}" if addr else "-"


def is_loopback(ip):
    return str(ip).startswith("127.") or ip == "::1" or ip == "localhost"


def fmt_time(t):
    return time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t * 1000) % 1000:03d}"


def trim(text, n):
    text = text.replace("\n", " ⏎ ")
    return text if len(text) <= n else text[: n - 1] + "…"


def endpoints(rec):
    local, remote = addr_or_unknown(rec["local"]), addr_or_unknown(rec["remote"])
    return (local, remote) if rec["direction"] == "send" else (remote, local)


# ----------------------------------------
# 계층별 요약(그림 옆 한 줄)과 상세 설명
# ----------------------------------------
def layer_summaries(rec):
    if rec["kind"] == "session":
        return session_summaries(rec)
    src, dst = endpoints(rec)
    raw = rec["raw"]
    hb = rec["tag"] in HEARTBEAT_TAGS
    loop = is_loopback(dst[0])
    return {
        7: trim(f'{rec["tag"]} | {rec["content"]}', 30),
        6: f"UTF-8 {len(raw)}B · {raw[:5].hex(' ')} …",
        5: f'세션 #{rec["session"]} · {"하트비트" if hb else "게임 데이터"}',
        4: f"TCP :{src[1]} → :{dst[1]} · {len(raw)}B",
        3: f"IPv4 {src[0]} → {dst[0]}",
        2: "루프백 (OS 내부에서 전달)" if loop else "이더넷/Wi-Fi 프레임",
        1: "신호 변환 없음 (루프백)" if loop else "비트 → 전기/전파 신호",
    }


def session_summaries(rec):
    info = rec["info"]
    ev = rec["event"]
    if ev == "connecting":
        return {4: "SYN 보내고 응답 기다리는 중", 3: f"목적지 {fmt_addr(info.get('target'))}"}
    if ev == "connected":
        local, remote = addr_or_unknown(rec["local"]), addr_or_unknown(rec["remote"])
        return {
            5: f'세션 #{rec["session"]} 시작',
            4: f'3-way 핸드셰이크 {info.get("handshake_ms", 0):.2f}ms',
            3: f"{local[0]} ⇄ {remote[0]}",
        }
    if ev == "closed":
        return {5: f'세션 #{rec["session"]} 종료', 4: "FIN/RST로 TCP 연결 해제"}
    return {4: "연결 거부됨 (서버 응답 없음)"}


def layer_details(rec):
    """상세 패널에 보여줄 [(계층번호 또는 None, 제목, [줄들])]"""
    if rec["kind"] == "session":
        return session_details(rec)

    src, dst = endpoints(rec)
    raw = rec["raw"]
    text = raw.decode("utf-8", errors="replace")
    tag, content = rec["tag"], rec["content"]
    hb = tag in HEARTBEAT_TAGS
    loop = is_loopback(dst[0])
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    hexdump = raw[:48].hex(" ") + (" …" if len(raw) > 48 else "")

    l7 = [
        "우리가 직접 정한 게임 프로토콜: 태그|내용\\n",
        f"태그 : {tag}  →  {TAG_MEANING.get(tag, '알 수 없는 태그')}",
        f"내용 : {content if content else '(비어 있음)'}",
    ]
    l6 = [
        "글자를 네트워크로 보낼 수 있는 바이트로 바꾸는 단계 (인코딩)",
        f"문자 {len(text)}자 → UTF-8 {len(raw)}바이트",
    ]
    if hangul:
        l6.append(f"한글 {hangul}자 × 3바이트 = {hangul * 3}바이트 (영문·숫자·기호는 1바이트)")
    l6.append(f"16진수: {hexdump}")

    l5 = [f'세션 #{rec["session"]} · 연결된 지 {rec["elapsed"]:.1f}초']
    if hb:
        l5.append("하트비트: 3초마다 ping → pong 으로 서로 살아있는지 확인")
        l5.append(f"{HEARTBEAT_TIMEOUT}초 동안 pong이 없으면 연결이 끊긴 것으로 판단")
    else:
        l5.append("이 세션(연결된 대화) 안에서 주고받는 게임 데이터")

    l4 = [
        "TCP: 순서를 지키고 빠진 데이터는 다시 보내주는 '바이트 스트림'",
        f"포트 {src[1]} → {dst[1]}  (5000 = 서버, 다른 번호 = OS가 임시로 준 내 포트)",
    ]
    if rec["direction"] == "send":
        l4.append(f"sendall()로 {len(raw)}바이트를 OS의 TCP 송신 버퍼에 넘김")
    else:
        l4.append(
            f'recv() 한 번에 {rec["chunk_size"]}바이트 도착 → \\n 기준으로 잘라 '
            f'{rec["chunk_msgs"]}개 메시지 중 {rec["chunk_index"]}번째'
        )
    l4.append("TCP에는 메시지 경계가 없어서, 줄바꿈(\\n)으로 메시지를 구분함")

    l3 = ["IP: 어느 컴퓨터로 보낼지 주소를 정하는 단계", f"{src[0]} → {dst[0]}"]
    if loop:
        l3.append("127.0.0.1 = 루프백 주소. 패킷이 내 컴퓨터 밖으로 나가지 않음")

    if loop:
        l2 = ["루프백이라 실제 이더넷/Wi-Fi 프레임(MAC 주소)이 만들어지지 않음",
              "다른 PC와 통신하면 여기서 MAC 주소가 붙은 프레임이 됨"]
        l1 = ["루프백은 랜선·전파를 쓰지 않고 OS 안에서 바로 전달",
              "다른 PC라면 비트(0/1)가 전기 신호나 전파로 바뀌어 전송됨"]
    else:
        l2 = ["OS와 랜카드가 출발지/목적지 MAC 주소를 붙여 프레임으로 만듦"]
        l1 = ["프레임의 비트(0/1)를 전기 신호(랜선) 또는 전파(Wi-Fi)로 바꿔 전송"]

    return [
        (7, LAYER_NAME[7], l7),
        (6, LAYER_NAME[6], l6),
        (5, LAYER_NAME[5], l5),
        (4, LAYER_NAME[4], l4),
        (3, LAYER_NAME[3], l3),
        (2, LAYER_NAME[2], l2),
        (1, LAYER_NAME[1], l1),
        (None, "참고", ["4~7계층과 IP 주소는 실제 값이에요.",
                       "1~2계층은 OS·하드웨어가 처리해서 파이썬 소켓으로는 볼 수 없어 설명으로 보여줘요."]),
    ]


def session_details(rec):
    info = rec["info"]
    ev = rec["event"]
    local, remote = addr_or_unknown(rec["local"]), addr_or_unknown(rec["remote"])
    if ev == "connecting":
        target = info.get("target")
        return [
            (4, LAYER_NAME[4], [f"connect() 호출 → OS가 서버 {fmt_addr(target)}에 연결 요청 (SYN 전송)",
                                "서버가 꺼져 있으면 0.5초 간격으로 다시 시도"]),
            (3, LAYER_NAME[3], [f"목적지 IP {target[0] if target else '?'}"]),
        ]
    if ev == "connected":
        return [
            (5, LAYER_NAME[5], [f'세션 #{rec["session"]} 시작: 이제부터 게임 메시지를 주고받는 \'대화\'가 열림',
                                f"하트비트(ping/pong)로 유지되고, {HEARTBEAT_TIMEOUT}초 동안 응답이 없으면 끊김으로 판단"]),
            (4, LAYER_NAME[4] + " · 3-way 핸드셰이크", [
                "① 내 PC → 서버 : SYN      (연결하자)",
                "② 서버 → 내 PC : SYN-ACK  (좋아, 나도)",
                "③ 내 PC → 서버 : ACK      (확인)",
                f'걸린 시간: {info.get("handshake_ms", 0):.2f} ms',
                f"내 포트 {local[1]} = OS가 임시로 정해준 번호(ephemeral port), 서버 포트 = {remote[1]}",
            ]),
            (3, LAYER_NAME[3], [f"{local[0]} ⇄ {remote[0]}"]
             + (["127.0.0.1 = 루프백: 같은 컴퓨터 안에서 통신"] if is_loopback(remote[0]) else [])),
        ]
    if ev == "closed":
        return [
            (5, LAYER_NAME[5], [f'세션 #{rec["session"]} 종료 · 이유: {info.get("reason", "?")}',
                                f'유지 시간 {rec.get("duration", 0):.1f}초']),
            (4, LAYER_NAME[4], ["TCP 연결 해제: 정상 종료는 FIN, 강제 종료는 RST 패킷",
                                "재접속하면 새 핸드셰이크 + 새 임시 포트로 새 세션이 열림"]),
        ]
    return [
        (4, LAYER_NAME[4], ["서버가 연결을 받아주지 않음 (서버가 꺼져 있거나 포트가 다름)",
                            info.get("reason", "")]),
    ]


def anim_sequence(rec):
    if rec["kind"] == "session":
        return {"connecting": [4, 3], "connected": [3, 4, 5], "closed": [5, 4]}.get(rec["event"], [4])
    return [7, 6, 5, 4, 3, 2, 1] if rec["direction"] == "send" else [1, 2, 3, 4, 5, 6, 7]


# ----------------------------------------
# 뷰어 창
# ----------------------------------------
class NetViewer:
    def __init__(self, root):
        self.root = root
        self.win = tk.Toplevel(root)
        self.win.title("네트워크 뷰어 · OSI 7계층")
        self.win.configure(bg=BG)
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        # 화면 배율(125%, 150% 등)에 맞춰 그림 크기도 같이 키운다.
        self.scale = max(1.0, self.win.winfo_fpixels("1i") / 96.0)
        self.win.geometry(f"{self.px(1180)}x{self.px(740)}")
        self.win.minsize(self.px(960), self.px(640))

        self.local = None
        self.remote = None
        self.session = 0
        self.connected = False
        self.connected_at = None
        self.last_pong = None
        self.rtts = deque(maxlen=40)
        self.records = {}
        self.order = deque()
        self.next_id = 0
        self.stats = {"send": [0, 0], "recv": [0, 0]}
        self.anim_queue = []
        self.animating = False
        self.hold_until = 0
        self.hide_hb = tk.BooleanVar(master=self.win, value=False)
        self.autoscroll = tk.BooleanVar(master=self.win, value=True)

        self._style()
        self._build_top()
        body = tk.Frame(self.win, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        left = tk.Frame(body, bg=BG)
        left.pack(side=tk.LEFT, fill=tk.Y)
        right = tk.Frame(body, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(12, 0))
        self._build_stack(left)
        self._build_rtt(left)
        self._build_log(right)
        self._tick()

    def px(self, value):
        return int(round(value * self.scale))

    # ---------- 창 보이기/숨기기 ----------
    def show(self):
        self.win.deiconify()
        self.win.lift()

    def hide(self):
        self.win.withdraw()

    def toggle(self):
        if self.win.state() == "withdrawn":
            self.show()
        else:
            self.hide()

    # ---------- 다른 스레드에서 호출하는 API ----------
    def _post(self, fn, *args):
        try:
            self.root.after(0, fn, *args)
        except (RuntimeError, tk.TclError):
            pass  # 창이 이미 닫힘

    def log_packet(self, direction, tag, content, raw, chunk_size=None, chunk_index=None, chunk_msgs=None):
        self._post(self._on_packet, direction, tag, content, raw, chunk_size, chunk_index, chunk_msgs)

    def session_event(self, kind, **info):
        self._post(self._on_session, kind, info)

    def record_rtt(self, ms):
        self._post(self._on_rtt, ms)

    # ---------- 스타일 ----------
    def _style(self):
        st = ttk.Style(self.win)
        st.theme_use("clam")
        st.configure("Net.Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                     rowheight=self.px(24), font=(FONT, 9), borderwidth=0)
        st.configure("Net.Treeview.Heading", background="#1f1f24", foreground=MUTED,
                     font=(FONT, 9, "bold"), relief="flat")
        st.map("Net.Treeview", background=[("selected", "#3a3550")])
        st.configure("Net.Vertical.TScrollbar", background=PANEL, troughcolor=BG, borderwidth=0, arrowcolor=MUTED)

    # ---------- 위쪽 상태 바 ----------
    def _build_top(self):
        top = tk.Frame(self.win, bg=PANEL, padx=12, pady=8)
        top.pack(fill=tk.X, padx=12, pady=12)
        row1 = tk.Frame(top, bg=PANEL)
        row1.pack(fill=tk.X)
        row2 = tk.Frame(top, bg=PANEL)
        row2.pack(fill=tk.X, pady=(4, 0))

        self.dot = tk.Label(row1, text="●", fg=MUTED, bg=PANEL, font=(FONT, 16))
        self.dot.pack(side=tk.LEFT)
        self.status_lbl = tk.Label(row1, text="연결 안 됨", fg=FG, bg=PANEL, font=(FONT, 12, "bold"))
        self.status_lbl.pack(side=tk.LEFT, padx=(6, 16))
        self.addr_lbl = tk.Label(row1, text="", fg=MUTED, bg=PANEL, font=(MONO, 10))
        self.addr_lbl.pack(side=tk.LEFT)

        for text, var, cmd in (("하트비트 숨기기", self.hide_hb, self._rebuild_tree),
                               ("자동 스크롤", self.autoscroll, None)):
            tk.Checkbutton(row1, text=text, variable=var, command=cmd, bg=PANEL, fg=FG, selectcolor=BG,
                           activebackground=PANEL, activeforeground=FG, font=(FONT, 9),
                           bd=0, highlightthickness=0).pack(side=tk.RIGHT, padx=(8, 0))

        self.hb_lbl = tk.Label(row2, text="", fg=MUTED, bg=PANEL, font=(FONT, 9))
        self.hb_lbl.pack(side=tk.LEFT)
        self.count_lbl = tk.Label(row2, text="", fg=MUTED, bg=PANEL, font=(FONT, 9))
        self.count_lbl.pack(side=tk.RIGHT)

    # ---------- 왼쪽: OSI 7계층 그림 ----------
    def _build_stack(self, parent):
        P = self.px
        self.layer_h, gap, top = P(54), P(6), P(40)
        width = P(420)
        self.stack_w = width
        height = top + 7 * (self.layer_h + gap) + P(26)
        c = tk.Canvas(parent, width=width, height=height, bg=BG, highlightthickness=0)
        c.pack()
        self.stack = c
        self.dir_text = c.create_text(P(4), P(16), anchor="w", text="패킷을 기다리는 중...",
                                      fill=MUTED, font=(FONT, 9, "bold"), width=width - P(8))
        self.layer_items = {}
        self.layer_y = {}
        for i, (num, ko, en, color) in enumerate(LAYERS):
            y = top + i * (self.layer_h + gap)
            self.layer_y[num] = y
            rect = c.create_rectangle(P(2), y, width - P(2), y + self.layer_h, fill=PANEL, outline=color, width=1)
            c.create_rectangle(P(2), y, P(44), y + self.layer_h, fill=color, outline=color)
            c.create_text(P(23), y + self.layer_h / 2, text=str(num), fill=BG, font=(FONT, 15, "bold"))
            c.create_text(P(54), y + P(15), anchor="w", text=f"{ko} · {en}", fill=color, font=(FONT, 9, "bold"))
            summary = c.create_text(P(54), y + P(38), anchor="w", text="", fill=FG, font=(MONO, 9))
            self.layer_items[num] = (rect, summary, color)
        c.create_text(width / 2, height - P(12), text="⇅  127.0.0.1 루프백  ⇅  서버",
                      fill=MUTED, font=(FONT, 9))
        self.chip = c.create_rectangle(0, 0, 0, 0, fill=SEND_COLOR, outline="", state="hidden")
        self.chip_text = c.create_text(0, 0, text="", fill=BG, font=(FONT, 9, "bold"), state="hidden")

    def _set_summaries(self, summaries):
        for num, (_, summary, _) in self.layer_items.items():
            self.stack.itemconfig(summary, text=summaries.get(num, ""))

    def _highlight(self, num, on):
        rect, _, color = self.layer_items[num]
        if on:
            self.stack.itemconfig(rect, fill=blend(color, BG, 0.35), width=3)
        else:
            self.stack.itemconfig(rect, fill=PANEL, width=1)

    def _move_chip(self, num, label, color):
        y = self.layer_y[num]
        x2 = self.stack_w - self.px(8)
        x1 = x2 - self.px(64)
        self.stack.coords(self.chip, x1, y + self.px(6), x2, y + self.px(24))
        self.stack.coords(self.chip_text, (x1 + x2) / 2, y + self.px(15))
        self.stack.itemconfig(self.chip, fill=color, state="normal")
        self.stack.itemconfig(self.chip_text, text=label, state="normal")

    def _hide_chip(self):
        self.stack.itemconfig(self.chip, state="hidden")
        self.stack.itemconfig(self.chip_text, state="hidden")

    def _direction_caption(self, rec):
        if rec["kind"] == "session":
            return f'● 세션 이벤트: {SESSION_LABEL.get(rec["event"], rec["event"])}', SESSION_COLOR
        if rec["direction"] == "send":
            return "⬇ 송신: 7 → 1계층으로 내려가며 포장 (캡슐화) → 서버", SEND_COLOR
        return "⬆ 수신: 서버 → 1 → 7계층으로 올라가며 풀기 (역캡슐화)", RECV_COLOR

    def _chip_style(self, rec):
        if rec["kind"] == "session":
            return "TCP", SESSION_COLOR
        color = HB_COLOR if rec["tag"] in HEARTBEAT_TAGS else (SEND_COLOR if rec["direction"] == "send" else RECV_COLOR)
        return rec["tag"][:6], color

    def _enqueue_anim(self, rec):
        if time.time() < self.hold_until:
            return  # 사용자가 로그를 보고 있는 동안은 그림을 덮어쓰지 않음
        if rec["kind"] == "packet" and rec["tag"] in HEARTBEAT_TAGS and self.hide_hb.get():
            return
        self.anim_queue.append(rec)
        if len(self.anim_queue) > 3:
            self.anim_queue = self.anim_queue[-3:]
        if not self.animating:
            self._next_anim()

    def _next_anim(self):
        if not self.anim_queue:
            self.animating = False
            return
        self.animating = True
        rec = self.anim_queue.pop(0)
        caption, color = self._direction_caption(rec)
        self.stack.itemconfig(self.dir_text, text=caption, fill=color)
        self._set_summaries({})
        seq = anim_sequence(rec)
        fast = rec["kind"] == "packet" and rec["tag"] in HEARTBEAT_TAGS
        self._anim_step(rec, seq, layer_summaries(rec), 0, 45 if fast else 120)

    def _anim_step(self, rec, seq, summaries, i, step_ms):
        try:
            if i > 0:
                self._highlight(seq[i - 1], False)
            if i == len(seq):
                self.win.after(250, self._hide_chip)
                self.win.after(150, self._next_anim)
                return
            num = seq[i]
            label, color = self._chip_style(rec)
            self._highlight(num, True)
            self.stack.itemconfig(self.layer_items[num][1], text=summaries.get(num, ""))
            self._move_chip(num, label, color)
            self.win.after(step_ms, self._anim_step, rec, seq, summaries, i + 1, step_ms)
        except tk.TclError:
            pass

    # ---------- 왼쪽 아래: RTT 그래프 ----------
    def _build_rtt(self, parent):
        self.rtt_canvas = tk.Canvas(parent, width=self.px(420), height=self.px(130), bg=PANEL, highlightthickness=0)
        self.rtt_canvas.pack(pady=(self.px(10), 0))
        self._draw_rtt()

    def _draw_rtt(self):
        P = self.px
        c = self.rtt_canvas
        c.delete("all")
        c.create_text(P(10), P(14), anchor="w", text="하트비트 RTT (ping→pong 왕복)", fill=MUTED, font=(FONT, 9, "bold"))
        x0, x1, y0, y1 = P(12), P(408), P(44), P(120)
        c.create_line(x0, y1, x1, y1, fill="#3a3a44")
        if not self.rtts:
            c.create_text(P(210), P(80), text="아직 측정값이 없어요 (3초마다 측정)", fill=HB_COLOR, font=(FONT, 9))
            return
        top = max(max(self.rtts) * 1.25, 1.0)
        n = self.rtts.maxlen
        pts = []
        for i, v in enumerate(self.rtts):
            x = x0 + (x1 - x0) * i / (n - 1)
            y = y1 - (y1 - y0) * (v / top)
            pts += [x, y]
        if len(pts) >= 4:
            c.create_line(*pts, fill=RECV_COLOR, width=2, smooth=True)
        c.create_oval(pts[-2] - 3, pts[-1] - 3, pts[-2] + 3, pts[-1] + 3, fill=RECV_COLOR, outline="")
        c.create_text(x1, P(32), anchor="e", text=f"현재 {self.rtts[-1]:.2f} ms · 최대 {max(self.rtts):.2f} ms",
                      fill=RECV_COLOR, font=(MONO, 9, "bold"))
        c.create_text(x0, y0 - 2, anchor="nw", text=f"{top:.1f}ms", fill=HB_COLOR, font=(MONO, 8))

    # ---------- 오른쪽: 패킷 로그 + 상세 ----------
    def _build_log(self, parent):
        tk.Label(parent, text="패킷 로그  ·  한 줄을 클릭하면 계층별 상세가 나와요",
                 fg=MUTED, bg=BG, font=(FONT, 10, "bold")).pack(anchor="w", pady=(0, 6))
        paned = tk.PanedWindow(parent, orient=tk.VERTICAL, bg=BG, sashwidth=6, bd=0)
        paned.pack(fill=tk.BOTH, expand=True)

        tree_frame = tk.Frame(paned, bg=BG)
        cols = ("time", "dir", "tag", "content", "bytes")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="Net.Treeview")
        for col, title, width, anchor in (("time", "시간", 95, "w"), ("dir", "방향", 70, "w"),
                                          ("tag", "태그", 80, "w"), ("content", "내용", 340, "w"),
                                          ("bytes", "바이트", 60, "e")):
            self.tree.heading(col, text=title, anchor=anchor)
            self.tree.column(col, width=self.px(width), anchor=anchor, stretch=(col == "content"))
        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview, style="Net.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.tag_configure("send", foreground=SEND_COLOR)
        self.tree.tag_configure("recv", foreground=RECV_COLOR)
        self.tree.tag_configure("session", foreground=SESSION_COLOR)
        self.tree.tag_configure("hb", foreground=HB_COLOR)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        detail_frame = tk.Frame(paned, bg=BG)
        self.detail = tk.Text(detail_frame, bg=PANEL, fg=FG, font=(MONO, 10), bd=0, padx=12, pady=10,
                              wrap=tk.WORD, height=14)
        dsb = ttk.Scrollbar(detail_frame, orient=tk.VERTICAL, command=self.detail.yview, style="Net.Vertical.TScrollbar")
        self.detail.configure(yscrollcommand=dsb.set)
        self.detail.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dsb.pack(side=tk.RIGHT, fill=tk.Y)
        for num, _, _, color in LAYERS:
            self.detail.tag_config(f"L{num}", foreground=color, font=(FONT, 10, "bold"))
        self.detail.tag_config("Lnone", foreground=MUTED, font=(FONT, 9, "bold"))
        self.detail.tag_config("title", foreground=FG, font=(FONT, 11, "bold"))
        self.detail.tag_config("muted", foreground=MUTED)
        self._write_detail_placeholder()

        paned.add(tree_frame, minsize=150)
        paned.add(detail_frame, minsize=150)

    def _write_detail_placeholder(self):
        self.detail.config(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        self.detail.insert(tk.END, "패킷을 선택하면 OSI 7계층별로 무슨 일이 일어났는지 보여줘요.\n\n", "title")
        self.detail.insert(tk.END, "· 파란색 → 내가 보낸 패킷 (7→1계층, 캡슐화)\n"
                                   "· 초록색 → 내가 받은 패킷 (1→7계층, 역캡슐화)\n"
                                   "· 노란색 → 연결/종료 같은 세션 이벤트 (TCP 핸드셰이크)\n"
                                   "· 회색   → 하트비트 ping/pong\n", "muted")
        self.detail.config(state=tk.DISABLED)

    def _show_detail(self, rec):
        self.detail.config(state=tk.NORMAL)
        self.detail.delete("1.0", tk.END)
        if rec["kind"] == "session":
            head = f'{fmt_time(rec["time"])}  ● 세션 이벤트 · {SESSION_LABEL.get(rec["event"], rec["event"])}\n\n'
        else:
            arrow = "→ 송신" if rec["direction"] == "send" else "← 수신"
            head = f'{fmt_time(rec["time"])}  {arrow} · {rec["tag"]} · {len(rec["raw"])}바이트\n\n'
        self.detail.insert(tk.END, head, "title")
        for num, title, lines in layer_details(rec):
            self.detail.insert(tk.END, f"[{title}]\n", f"L{num}" if num else "Lnone")
            for line in lines:
                self.detail.insert(tk.END, f"   {line}\n", "muted" if num is None else ())
            self.detail.insert(tk.END, "\n")
        self.detail.config(state=tk.DISABLED)

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if not sel:
            return
        rec = self.records.get(int(sel[0]))
        if not rec:
            return
        self._show_detail(rec)
        # 선택한 패킷을 그림에도 표시하고, 5초간 새 애니메이션이 덮어쓰지 않게 한다.
        self.hold_until = time.time() + 5
        caption, color = self._direction_caption(rec)
        self.stack.itemconfig(self.dir_text, text=caption + "  (선택한 패킷)", fill=color)
        self._set_summaries(layer_summaries(rec))

    # ---------- 레코드 관리 ----------
    def _visible(self, rec):
        return not (rec["kind"] == "packet" and rec["tag"] in HEARTBEAT_TAGS and self.hide_hb.get())

    def _insert_row(self, rec):
        if rec["kind"] == "session":
            values = (fmt_time(rec["time"]), "● 세션", SESSION_LABEL.get(rec["event"], rec["event"]),
                      trim(self._session_line(rec), 70), "")
            tags = ("session",)
        else:
            hb = rec["tag"] in HEARTBEAT_TAGS
            values = (fmt_time(rec["time"]), "→ 송신" if rec["direction"] == "send" else "← 수신",
                      rec["tag"], trim(rec["content"], 70), len(rec["raw"]))
            tags = ("hb",) if hb else (rec["direction"],)
        iid = str(rec["id"])
        self.tree.insert("", tk.END, iid=iid, values=values, tags=tags)
        if self.autoscroll.get():
            self.tree.see(iid)

    def _session_line(self, rec):
        info = rec["info"]
        if rec["event"] == "connected":
            return f'{fmt_addr(rec["local"])} ⇄ {fmt_addr(rec["remote"])} · 핸드셰이크 {info.get("handshake_ms", 0):.2f}ms'
        if rec["event"] == "closed":
            return f'{info.get("reason", "")} · {rec.get("duration", 0):.1f}초 유지'
        if rec["event"] == "connecting":
            return f'{fmt_addr(info.get("target"))} 에 TCP 연결 요청'
        return info.get("reason", "")

    def _add_record(self, rec):
        rec["id"] = self.next_id
        self.next_id += 1
        self.records[rec["id"]] = rec
        self.order.append(rec["id"])
        while len(self.order) > MAX_RECORDS:
            old = self.order.popleft()
            self.records.pop(old, None)
            if self.tree.exists(str(old)):
                self.tree.delete(str(old))
        if self._visible(rec):
            self._insert_row(rec)
        self._enqueue_anim(rec)

    def _rebuild_tree(self):
        self.tree.delete(*self.tree.get_children())
        for rid in self.order:
            rec = self.records[rid]
            if self._visible(rec):
                self._insert_row(rec)

    # ---------- 이벤트 처리 (메인 스레드) ----------
    def _on_packet(self, direction, tag, content, raw, chunk_size, chunk_index, chunk_msgs):
        now = time.time()
        rec = {
            "kind": "packet", "time": now, "direction": direction, "tag": tag, "content": content,
            "raw": raw, "chunk_size": chunk_size, "chunk_index": chunk_index, "chunk_msgs": chunk_msgs,
            "session": self.session, "local": self.local, "remote": self.remote,
            "elapsed": now - self.connected_at if self.connected_at else 0.0,
        }
        self.stats[direction][0] += 1
        self.stats[direction][1] += len(raw)
        self._add_record(rec)

    def _on_session(self, kind, info):
        now = time.time()
        rec = {"kind": "session", "time": now, "event": kind, "info": info}
        if kind == "connecting":
            self._set_status("연결 중...", SESSION_COLOR)
        elif kind == "connected":
            self.local, self.remote = info.get("local"), info.get("remote")
            self.session = info.get("session", self.session + 1)
            self.connected = True
            self.connected_at = now
            self.last_pong = now
            self.rtts.clear()
            self._draw_rtt()
            self._set_status(f"연결됨 · 세션 #{self.session}", RECV_COLOR)
            self.addr_lbl.config(text=f"내 PC {fmt_addr(self.local)}  ⇄  서버 {fmt_addr(self.remote)}")
            self.win.title(f"네트워크 뷰어 · OSI 7계층 · 내 포트 {self.local[1] if self.local else '?'}")
        elif kind == "closed":
            rec["duration"] = now - self.connected_at if self.connected_at else 0.0
            self.connected = False
            self.connected_at = None
            self._set_status("연결 끊김", "#ef4565")
        elif kind == "failed":
            self._set_status("연결 실패", "#ef4565")
        rec["session"] = self.session
        rec["local"], rec["remote"] = self.local, self.remote
        self._add_record(rec)

    def _on_rtt(self, ms):
        self.rtts.append(max(ms, 0.0))
        self.last_pong = time.time()
        self._draw_rtt()

    def _set_status(self, text, color):
        self.dot.config(fg=color)
        self.status_lbl.config(text=text)

    def _tick(self):
        try:
            if self.connected and self.last_pong:
                age = time.time() - self.last_pong
                color = "#ef4565" if age > HEARTBEAT_TIMEOUT * 2 / 3 else MUTED
                self.hb_lbl.config(text=f"💓 마지막 pong {age:.1f}초 전  ({HEARTBEAT_TIMEOUT}초 넘으면 끊김 판정)", fg=color)
            else:
                self.hb_lbl.config(text="💓 하트비트 없음 (연결 안 됨)", fg=MUTED)
            s, r = self.stats["send"], self.stats["recv"]
            self.count_lbl.config(text=f"송신 {s[0]}개 / {s[1]:,}B    수신 {r[0]}개 / {r[1]:,}B")
            self.win.after(500, self._tick)
        except tk.TclError:
            pass
