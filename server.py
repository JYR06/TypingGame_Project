import socket
import threading
import random
import time

HOST = "0.0.0.0"
PORT = 5000

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen()

print("================================")
print("   타이핑 배틀 서버    ")
print("================================")

clients = []
game_active = False       # 게임이 진행 중인지 확인
game_questions = []       # 이번 판에 뽑힌 10개의 문제
player_progress = {}      # 각 플레이어가 몇 번째 문제를 풀고 있는지 기록 (예: {client: 3})
start_time = 0

# (아까 받으신 100개의 질문 리스트를 여기에 넣으세요)
questions = [
    "스위스에서 온 사십 세 스미스 씨",
    "경찰청 철창살은 외철창살이냐 쌍철창살이냐",
    "내가 그린 기린 그림은 잘 그린 기린 그림이고",
    "니가 그린 기린 그림은 못 그린 기린 그림이다",
    "간장 공장 공장장은 강 공장장이고",
    "된장 공장 공장장은 공 공장장이다",
    "들의 콩깍지는 깐 콩깍지인가 안 깐 콩깍지인가",
    "깐 콩깍지면 어떻고 안 깐 콩깍지면 어떠냐",
    "저기 있는 저 뜀틀이 내가 뛸 뜀틀인가",
    "내가 안 뛸 뜀틀인가",
    "앞 집 팥죽은 붉은 팥 풋팥죽이고",
    "뒷 집 콩죽은 햇콩 단콩 콩죽이다",
    "서울특별시 특허허가과 허가과장 허과장",
    "촉촉한 초코칩 나라에 살던 안 촉촉한 초코칩이",
    "안 촉촉한 초코칩 나라의 촉촉한 초코칩을 보고",
    "촉촉한 초코칩이 되고 싶어서 촉촉한 초코칩 나라에 갔는데",
    "철수 책상 철 책상 칠수 책상 찰흙 책상",
    "상표 붙인 큰 깡통은 깐 깡통인가 안 깐 깡통인가",
    "신진 샹송 가수의 신춘 샹송 쇼",
    "중앙청 창살은 쌍창살이고 시청 창살은 외창살이다",
    "한양양장점 옆 한영양장점 한영양장점 옆 한양양장점",
    "고려고 교복은 고급 교복이고 고려고 교복은 고단복이다",
    "작년에 온 솥장수는 새 솥장수이고 금년에 온 솥장수는 헌 솥장수이다",
    "춘천 칠전동 칠십칠 번지 칠순 잔칫날",
    "칠월 칠일은 평창친구 친정 칠순 잔칫날",
    "육십육 세의 신임 시장은 칠십칠 세의 구임 시장을 칭찬했다",
    "대우 로얄 뉴로얄 정통 로얄 뉴로얄",
    "호동이네 포도나무는 청포도나무이고",
    "희동이네 포도나무는 적포도나무이다",
    "숲 속 동굴 속에 숨은 산토끼 삼백 마리",
    "청룡 황룡 백룡 흑룡 비룡 쌍룡",
    "건국 이래 굳건한 국가 권력",
    "박 법학박사 백 법학박사",
    "복잡한 법학부 복학생 곽복학",
    "봄 꿀밤 단 꿀밤 가을 꿀밤 안 단 꿀밤",
    "생각이란 생각하면 생각할수록 생각나는 것이 생각이므로",
    "생각하지 않는 생각이 좋은 생각이라 생각한다",
    "저기 가는 저 상장사가 새 상장사냐 헌 상장사냐",
    "도토리가 문을 도로록 드르륵 두루룩 열었는가",
    "도로록 드르륵 두루룩 닫았는가",
    "김 서방네 구석 자리 호박 단지는",
    "꿀 호박 단지인가 그냥 호박 단지인가",
    "안다미로 담은 백설기 떡 찌는 시루 떡 시루",
    "동해물과 백두산이 마르고 닳도록",
    "멍멍이네 꿀꿀이는 멍멍해도 꿀꿀하고",
    "꿀꿀이네 멍멍이는 꿀꿀해도 멍멍하네",
    "안드로메다 은하계의 외계인 왈왈이",
    "샹젤리제 거리의 샹들리에 숍",
    "가막살나무 꽃 피는 가막살나무 숲",
    "한국관광공사 곽진광 관광과장",
    "정통 중화요리 볶음밥 비빔밥 짬뽕 국물",
    "고기 굽는 고기 불판 위에 굽힌 고기",
    "새우 로제 파스타와 까르보나라 크림 스파게티",
    "모서리가 둥근 직육면체 투명 플라스틱 케이스",
    "저기 저 톨게이트 톨게이트비 통행료 통계",
    "짹짹이네 짹짹이는 짹짹짹 짹짹대고",
    "구구네 구구는 구구구 구구대네",
    "찰리스 아폴로 우주선 승무원 찰스",
    "포카칩과 스윙칩 그리고 꼬깔콘과 콘칩",
    "팥 풋팥죽 콩 풋콩죽 쌀 풋쌀죽",
    "왕 밤빵 당 밤빵 찐 밤빵 생 밤빵",
    "방실방실 방실이 보글보글 보글이",
    "블루베리 스무디와 스트로베리 프라푸치노",
    "알록달록 얼룩덜룩 아롱다롱 어룽더룽",
    "들기름 참기름 콩기름 옥수수기름 산초기름",
    "가나다라마바사아자차카타파하",
    "쌍시옷 쌍지읒 쌍디귿 쌍비읍 쌍기역",
    "백 억 천 억 조 십조 백조 천조 경",
    "나폴나폴 나비가 나풀나풀 날아간다",
    "팔딱팔딱 개구리가 폴짝폴짝 뛰어간다",
    "대관령 삼양목장 푸른 초원 양떼목장",
    "제주특별자치도 서귀포시 표선면 표선리",
    "구름 한 점 없이 맑고 푸른 청명한 가을 하늘",
    "울긋불긋 단풍 든 설악산 대청봉 흔들바위",
    "동해 바다 오징어 서해 바다 쭈꾸미 남해 바다 문어",
    "강원도 평창군 봉평면 메밀밭 메밀꽃 필 무렵",
    "충청북도 청주시 상당구 낭성면 무성리",
    "전라남도 보성군 보성읍 녹차밭 푸른 녹차잎",
    "경상북도 울릉군 울릉읍 독도리 독도 동도 서도",
    "알쏭달쏭 아리송한 알록달록 무지개색 크레파스",
    "구불구불 꼬불꼬불 구비진 대관령 옛길",
    "오르락내리락 엎치락뒤치락 우당탕탕 쿵쾅쿵쾅",
    "바스락바스락 낙엽 밟는 소리 사박사박 눈 밟는 소리",
    "콸콸콸 쏟아지는 시원한 계곡물 졸졸졸 흐르는 시냇물",
    "반짝반짝 빛나는 밤하늘의 은하수 별빛",
    "몽글몽글 피어나는 하얀 뭉게구름 솜사탕",
    "따르릉따르릉 비켜가세요 자전거가 나갑니다 따르르르릉",
    "삐뽀삐뽀 소방차 애앵애앵 구급차 출동",
    "칙칙폭폭 기차 타고 떠나는 즐거운 기차 여행",
    "윙윙윙 날아다니는 꿀벌 웽웽웽 모기 앵앵앵 파리",
    "살랑살랑 부는 봄바람 솔솔솔 부는 산들바람",
    "펄펄 눈이 옵니다 하늘에서 눈이 옵니다",
    "주룩주룩 내리는 장맛비 보슬보슬 봄비 추적추적 가을비",
    "새콤달콤 파인애플 상큼발랄 오렌지 달콤쌉싸름 자몽",
    "바삭바삭 감자튀김 노릇노릇 군만두 쫄깃쫄깃 떡볶이",
    "후루룩 짭짭 맛있는 라면 호로록 호로록 칼국수",
    "치익치익 고기 굽는 소리 지글지글 찌개 끓는 소리",
    "와삭와삭 사과 씹는 소리 아작아작 깍두기 씹는 소리",
    "꿀꺽꿀꺽 시원한 물 마시는 소리 벌컥벌컥 맥주 마시는 소리",
    "쿨쿨쿨 잠자는 아기 새근새근 숨쉬는 강아지"
] 

def handle_client(client, address):
    global game_active, game_questions, player_progress, start_time
    
    print(f"[접속] {address}")
    clients.append(client)

    try:
        while True:
            data = client.recv(1024)
            if not data:
                break

            message = data.decode("utf-8")
            parts = message.split("|", 1) 
            
            if len(parts) == 2: 
                tag = parts[0]  
                content = parts[1].strip() # 띄어쓰기 실수 방지

                if tag == "chat":
                    # 1. 게임 시작 (아무도 게임을 안 하고 있을 때만)
                    if content == "시작" and not game_active:
                        game_active = True
                        game_questions = random.sample(questions, 10) # 10개를 무작위로 뽑음
                        start_time = time.time()
                        
                        # 모든 유저의 진도를 0(1단계)으로 맞추고 첫 문제 전송
                        for c in clients:
                            player_progress[c] = 0
                            c.send("system|\n🚨 게임 시작! 10개의 문장을 먼저 클리어하세요! 🚨".encode("utf-8"))
                            c.send(f"system|▶ [STAGE 1/10]".encode("utf-8"))
                            c.send(f"game|{game_questions[0]}".encode("utf-8"))
                            
                    # 2. 게임 진행 중일 때 (정답 검사)
                    elif game_active and client in player_progress:
                        current_index = player_progress[client] # 이 유저가 풀어야 할 문제 번호
                        expected_answer = game_questions[current_index] # 정답
                        
                        if content == expected_answer:
                            # 정답을 맞히면 다음 단계로!
                            player_progress[client] += 1
                            new_index = player_progress[client]
                            
                            # 10단계를 다 깼다면? (최종 우승!)
                            if new_index == 10:
                                end_time = time.time()
                                record = end_time - start_time
                                total_chars = sum(len(q) for q in game_questions)
                                typing_speed = int((total_chars / record) * 60)
                                
                                for c in clients:
                                    msg = f"notice|🏆 [유저 {address[1]}]님 10단계 최종 우승! 🏆\n 👉 최종 기록: {record:.2f}초 (평균 타자 속도: 약 {typing_speed}타)"
                                    c.send(msg.encode("utf-8"))
                                
                                # 다음 게임을 위해 세팅 초기화
                                game_active = False
                                player_progress.clear()
                                game_questions.clear()
                                
                            else:
                                # 아직 깨는 중이라면 다음 문제 출제
                                for c in clients:
                                    if c != client: # 다른 유저들에게는 진행 상황만 슬쩍 알려줌
                                        c.send(f"system|[유저 {address[1]}]님이 {new_index}단계를 통과했습니다! (현재 {new_index}/10)".encode("utf-8"))
                                
                                client.send(f"system|\n▶ [STAGE {new_index+1}/10]".encode("utf-8"))
                                client.send(f"game|{game_questions[new_index]}".encode("utf-8"))
                                
                        else:
                            # 오타가 났을 때! (본인에게만 에러 메시지 전송)
                            client.send("system|❌ 틀렸습니다! 침착하게 다시 타자를 치세요. ❌".encode("utf-8"))
                            
                    # 3. 평범한 채팅
                    else:
                        for c in clients:
                            response = f"chat|[유저 {address[1]}]: {content}"
                            c.send(response.encode("utf-8"))

    except ConnectionResetError:
        pass
    finally:
        if client in clients:
            clients.remove(client)
            if client in player_progress: # 나간 유저는 진도표에서도 삭제
                del player_progress[client]
        client.close()
        print(f"[퇴장] {address}")

while True:
    client, address = server.accept()
    thread = threading.Thread(target=handle_client, args=(client, address))
    thread.start()