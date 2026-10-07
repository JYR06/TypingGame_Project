import socket
import threading
import tkinter as tk

# ========================================
# 1. 서버 연결 설정
# ========================================
HOST = "127.0.0.1"
PORT = 5000

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((HOST, PORT))

# ========================================
# 2. 게임 화면(UI) 디자인 만들기
# ========================================
window = tk.Tk()
window.title("타이핑 워리어: 스미스 씨의 악몽")
window.geometry("700x600") # 창 크기
window.configure(bg="#16161a") # 힙한 다크 네이비 배경

# 화면에 글자를 띄워주는 함수 (색깔별로!)
def display_message(msg, color_tag):
    chat_box.config(state=tk.NORMAL) # 글자를 쓸 수 있게 잠금 해제
    chat_box.insert(tk.END, msg + "\n", color_tag) # 맨 아래에 글자 추가
    chat_box.see(tk.END) # 스크롤을 항상 맨 아래로!
    chat_box.config(state=tk.DISABLED) # 다시 읽기 전용으로 잠금

# 게임 메시지 창 (채팅 내역과 문제가 나오는 곳)
chat_box = tk.Text(window, bg="#16161a", fg="#fffffe", font=("맑은 고딕", 12, "bold"), bd=0, padx=20, pady=20)
chat_box.pack(fill=tk.BOTH, expand=True)
chat_box.config(state=tk.DISABLED) # 마우스로 글자를 수정 못 하게 막음

# 🎨 힙한 네온 색상 태그 설정
chat_box.tag_config("chat", foreground="#94a1b2")       # 일반 채팅: 회색
chat_box.tag_config("game", foreground="#2cb67d", font=("맑은 고딕", 16, "bold")) # 게임 문제: 네온 그린 (크게!)
chat_box.tag_config("system", foreground="#ef4565")     # 시스템 알림: 네온 핑크
chat_box.tag_config("notice", foreground="#7f5af0")     # 공지: 네온 퍼플

# 입력창 테두리 (디자인 용도)
input_frame = tk.Frame(window, bg="#242629", pady=10)
input_frame.pack(fill=tk.X, side=tk.BOTTOM)

# 내가 타자를 치는 입력창
entry = tk.Entry(input_frame, bg="#242629", fg="#2cb67d", font=("맑은 고딕", 14, "bold"), bd=0, insertbackground="#2cb67d")
entry.pack(fill=tk.X, padx=20, pady=5)
entry.focus() # 켜자마자 바로 타자를 칠 수 있게 커서 깜빡이기

# ========================================
# 3. 보내고 듣는 기능 연결하기
# ========================================

# [입 역할] 엔터(Enter) 키를 누르면 메시지 서버로 보내기
def send_message(event=None):
    message = entry.get() # 입력창에 쓴 글자 가져오기
    if message.lower() == "exit":
        window.quit()
        return
        
    if message.strip(): # 비어있지 않을 때만 전송
        send_data = f"chat|{message}"
        client.send(send_data.encode("utf-8"))
        entry.delete(0, tk.END) # 보낸 뒤에 입력창 비우기

# 엔터키랑 전송 함수 연결
window.bind("<Return>", send_message)

# [귀 역할] 24시간 서버 소식 듣기
# [귀 역할] 24시간 서버 소식 듣기
def receive_message():
    while True:
        try:
            data = client.recv(1024)
            if not data:
                break
            
            response = data.decode("utf-8")
            parts = response.split("|", 1)
            
            if len(parts) == 2:
                tag = parts[0]
                content = parts[1]
                
                # 1. 일반 채팅 (회색)
                if tag == "chat":
                    display_message(content, "chat")
                    
                # 2. 게임 문제 (네온 그린 + 크고 두껍게)
                elif tag == "game":
                    display_message(f" 👉  {content}\n", "game")
                    
                # 3. 오타 경고나 현재 스테이지 알림 (네온 핑크)
                elif tag == "system":
                    display_message(content, "system")
                    
                # 4. 우승자 공지 (네온 퍼플)
                elif tag == "notice":
                    display_message(f"\n=========================================", "notice")
                    display_message(content, "notice")
                    display_message(f"=========================================\n", "notice")
            else:
                display_message(response, "system")
                
        except:
            display_message("[서버와 연결이 끊어졌습니다.]", "system")
            break

# 시작할 때 환영 인사
display_message("🎮 타이핑 워리어에 오신 것을 환영합니다!", "notice")
display_message("채팅창에 '시작'을 입력하면 게임이 시작됩니다.\n", "chat")

# 듣기 스레드(귀) 시작
receive_thread = threading.Thread(target=receive_message)
receive_thread.daemon = True
receive_thread.start()

# 화면(UI) 띄우기 시작! (이 코드가 있어야 화면이 계속 켜져있어요)
window.mainloop()

# 창을 닫으면 서버와 연결 종료
client.close()