**시뮬레이션 API 요약**
**사용(O)**
기능	                            설명					호출 함수
Detect :					Detect Mode 클릭 시 호출		def detect()
Get Action :				Tracking Mode 클릭 시 호출		def get_action()
Info :					정보 전달 시 호출				def info()
Update Bullet :	                포탄이 충돌한 위치 및  정보전달	def update_bullet()
Start	Start : 				버튼 클릭 시 호출				def start()
Collision :				        장애물 충돌 시 호출				def collision()


**사용(X)** 
기능							 설명					       호출 함수
Set Destination			목적지 설정 시 호출				def set_destination()
Update Obstacle			장애물 추가 시 호출				def update_obstacle()
Init					        초기 변환 함수				        def init()

---
**시뮬레이션 모드별 함수 호출 로그
① 앞으로 가면서 인식 + 포 발사**
Mode: Tracking Mode / Detect Mode / Log Mode

get_action → detect → get_action → detect → info
→ get_action → detect → update_bullet → info
→ get_action → detect → info → get_action → info
→ detect → get_action → info → detect → get_action
→ info → detect → get_action → info → get_action
→ detect → info → get_action → info → detect → get_action
→ info → detect → get_action → info → detect → get_action
→ info → get_action → info → detect → info → get_action
→ detect → info → get_action → detect → info → get_action
→ detect → info → get_action → update_bullet → info
→ detect → get_action → info → get_action → detect → info
→ get_action → detect → info → get_action → info → detect
→ get_action → info → detect → get_action → info → detect
→ get_action → info → get_action → info → detect → info
→ get_action → detect → info → get_action → detect → info
→ get_action → info → update_bullet → get_action → detect
→ info → get_action → detect → info → get_action → info
→ detect → get_action → detect → info → get_action → info
→ detect → get_action → info → detect → get_action → info
→ get_action → info → detect → get_action → detect → info
→ get_action → detect → info → get_action → detect → info
→ get_action → info → update_bullet → get_action → detect
→ info → get_action → detect → info → get_action → info
→ detect → get_action → info → detect → get_action → info
→ get_action → detect → info → get_action → detect → info
→ get_action → info → detect → get_action → info → detect
→ get_action → info → get_action → detect → info → start

---
**② 앞으로 가면서 인식 + 포 발사 + 장애물 충돌**
Mode: Tracking Mode / Detect Mode / Log Mode

get_action → info → detect → update_bullet → info
→ get_action → detect → info → get_action → info → detect
→ get_action → info → get_action → detect → info → get_action
→ collision → detect → collision → collision → info → collision
→ get_action → info → collision → detect → get_action → info
→ collision → detect → get_action → info → collision → collision
→ collision → detect → get_action → info → get_action → info
→ detect → info → get_action → collision → detect → info
→ get_action → info → detect → get_action → info → get_action
→ detect → update_bullet → info → get_action → collision
→ detect → collision → collision → info → collision → collision
→ collision → collision → collision → collision → get_action
→ collision → collision → collision → info → collision
→ collision → detect → get_action → info → detect → get_action
→ info → get_action → detect → info → get_action → info
→ detect → info → get_action → detect → info → get_action
→ info → detect → get_action → info → detect → get_action
→ info → update_bullet → get_action → detect → info → get_action
→ info → detect → get_action → info → detect → get_action
→ info → detect → get_action → info → detect → get_action
→ info → info → get_action → detect → info → get_action
→ detect → info → get_action → detect → info → get_action
→ detect → info → get_action → detect → info → get_action
→ detect → info → get_action → detect → info → start

---
**①번의 경우 
[info ,get_action ,detect]**
 1. get_action → detect → info : 21회
 2. get_action → info → detect : 19회
 3. detect → get_action → info : 16회
 **4. detect → info → get_action : 22회**
 5. info → get_action → detect : 17회
 6. info → detect → get_action : 18회
 
---
**②번의 경우
[collision ,get_action ,detect][3가지]**
1. collision → get_action → detect : 0회
2. collision → get_action → info : 1회
3. collision → detect → get_action : 2회
4. collision → detect → info : 1회
5. collision → info → get_action : 0회
6. collision → info → detect : 0회
7. get_action → collision → detect : 1회
8. get_action → collision → info : 0회
9. get_action → detect → collision : 0회
10. **get_action → detect → info : 4회**
11.  get_action → info → collision : 3회
12. **get_action → info → detect : 4회**
13. detect → collision → get_action : 0회
14. detect → collision → info : 0회
15. detect → get_action → collision : 0회
16. **detect → get_action → info : 4회**
17. detect → info → collision : 0회
18. **detect → info → get_action : 4회**
19. info → collision → get_action : 1회
20. info → collision → detect : 2회
21. info → get_action → collision : 1회
22. info → get_action → detect : 3회
23. info → detect → collision : 0회
24. info → detect → get_action : 3회

---
**②번의 경우
[collision ,get_action ,detect ,info ][4가지]**
1. collision → get_action → detect → info : 0회
2. collision → get_action → info → detect : 0회
3.  **collision → detect → get_action → info : 4회**
4. collision → detect → info → get_action : 1회
5. collision → info → get_action → detect : 0회
6. collision → info → detect → get_action : 0회
7. get_action → collision → detect → info : 1회
8. get_action → collision → info → detect : 0회
9. get_action → detect → collision → info : 0회
10. get_action → detect → info → collision : 0회
11. get_action → info → collision → detect : 2회
12. get_action → info → detect → collision : 0회
13. detect → collision → get_action → info : 0회
14. detect → collision → info → get_action : 0회
15. detect → get_action → collision → info : 0회
16. detect → get_action → info → collision : 2회
17. detect → info → collision → get_action : 0회
18. detect → info → get_action → collision : 2회
19. info → collision → get_action → detect : 0회
20. info → collision → detect → get_action : 2회
21. info → get_action → collision → detect : 3회
22. info → get_action → detect → collision : 0회
23. info → detect → collision → get_action : 0회
24. info → detect → get_action → collision : 0회
---

**포의 발사 시간 분석**
**[Tracking Mode(X) : 6초]**
💥 Bullet Impact at X=60.02005, Y=7.903808, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:56:56] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=7.891617, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:57:02] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=7.900435, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:57:08] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=7.907436, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:57:14] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=9.698483, Z=46.25045, Target=Car005_9
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:57:19] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02004, Y=7.892193, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:57:26] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=9.698513, Z=46.25045, Target=Car005_9
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:57:31] "POST /update_bullet HTTP/1.1" 200 -
 
**[Tracking Mode(O) : 6초]**
💥 Bullet Impact at X=60.02005, Y=9.692477, Z=46.25045, Target=Car005_9
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:51:50] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=9.691355, Z=46.25045, Target=Car005_9
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:51:57] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=7.897007, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:52:03] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=7.898819, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:52:09] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=7.895025, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:52:15] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=9.68893, Z=46.25045, Target=Car005_9
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:52:21] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=7.898316, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:52:27] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=9.698794, Z=46.25045, Target=Car005_9
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:52:33] "POST /update_bullet HTTP/1.1" 200 -
💥 Bullet Impact at X=60.02005, Y=7.897918, Z=69.77045, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 13:52:39] "POST /update_bullet HTTP/1.1" 200 -

**초반에는 7초가 나왔지만 이후에는 6초로 통일됨 // 원인은 초반에 버튼을 잘못 눌러서 발생됨**

---
**포탄이 발생했을 때 로그**
[수동]
💥 Bullet Impact at X=43.06729, Y=7.90379, Z=70.9642, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 14:35:36] "POST /update_bullet HTTP/1.1" 200 - 
**update_bullet만 출력됨(get_action[포 발사]표시 X)**

---
[자동]
📨 Position received: x=60.0, y=8.0, z=27.23
🎯 Turret received: x=0.0, y=0.0
함수이름 : get_action
127.0.0.1 - - [15/Oct/2025 15:25:30] "POST /get_action HTTP/1.1" 200 -
📨 Position received: x=59.97, y=7.97, z=27.49
🎯 Turret received: x=7.2, y=0.53
함수이름 : get_action
127.0.0.1 - - [15/Oct/2025 15:25:31] "POST /get_action HTTP/1.1" 200 -
💥 Bullet Impact at X=60.90352, Y=7.901774, Z=69.76095, Target=terrain
함수이름 : update_bullet
127.0.0.1 - - [15/Oct/2025 15:25:31] "POST /update_bullet HTTP/1.1" 200 -
📨 Position received: x=59.93, y=7.98, z=28.36
🎯 Turret received: x=47.73, y=3.2
함수이름 : get_action
127.0.0.1 - - [15/Oct/2025 15:25:31] "POST /get_action HTTP/1.1" 200 -
📨 Position received: x=59.94, y=8.0, z=29.66
🎯 Turret received: x=31.06, y=5.6
함수이름 : get_action
127.0.0.1 - - [15/Oct/2025 15:25:32] "POST /get_action HTTP/1.1" 200 -
**get_action, update_bullet 출력됨(get_action[포 발사]표시 O)**