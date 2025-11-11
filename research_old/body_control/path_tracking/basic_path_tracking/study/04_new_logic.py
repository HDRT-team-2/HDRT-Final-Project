from flask import Flask, request, jsonify
import math

# -------------------------------------------------------------------
# detect | Integrated Battlefield Situation Management (IBSM)
enemy_detection, enemy_in_fov = False, False # detect API

# info, get_action | Tank Turret Rotation Control
global_QE_command, global_QE_weight, global_RF_command, global_RF_weight = 0.0, 0.0, 0.0, 0.0
# info, get_action | Tank Body Movement Control
global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = 0.0, 0.0, 0.0, 0.0
# info, get_action | Tank Fire Control
global_fire_command = 0.0

# -------------------------------------------------------------------

# info | Waypoint : Linked List
class WaypointNode:
    def __init__(self, x, z):
        self.x = float(x) # pos x
        self.z = float(z) # pos y 
        self.next = None # next node

class WaypointList:
    def __init__(self):
        self.head = None # head node (first waypoint)
        self.tail = None # tail node (last waypoint)
        self._len = 0 # length (number of waypoints)

    def append(self, x, z):
        # Add a new waypoint to the end of the list
        node = WaypointNode(x, z)
        if not self.head:
            self.head = self.tail = node # If list is empty, set head and tail
        else:
            self.tail.next = node # Link new node to the end
            self.tail = node      # Update tail to new node
        self._len += 1
        return node
    
    def peek(self):
        # Return the first waypoint (head) without removing it
        return self.head

    def pop(self):
        # Remove and return the first waypoint (head)
        if not self.head:
            return None
        node = self.head
        self.head = node.next
        if not self.head:
            self.tail = None # If list is now empty, reset tail
        node.next = None
        self._len -= 1
        return node

    def is_empty(self):
        # Check if the waypoint list is empty
        return self.head is None

    def to_list(self):
        # Convert the linked list of waypoints to a Python list of dicts
        out = []
        cur = self.head
        while cur:
            out.append({'x': cur.x, 'z': cur.z})
            cur = cur.next
        return out

# --------------------------------------------------------------------

# Path Planning
waypoints = WaypointList()
# 전체 지도 탐색용 수동 웨이포인트 설정
for idx, y in enumerate(range(5, 296, 5)):
    if idx % 2 == 0:
        waypoints.append(5, y)
        waypoints.append(295, y)
    else:
        waypoints.append(295, y)
        waypoints.append(5, y)

# --------------------------------------------------------------------

def path_finding(): # 경로 탐색 함수
    # not yet
    path = waypoints
    return path

def path_tracking(player_x, player_z, player_body_x, player_speed): # 경로 추적 함수
    print("path_tracking")
    # 커맨드 초기화
    WS_command, WS_weight, AD_command, AD_weight = "", 0.0, "", 0.0

    # path: 여러 개의 웨이포인트로 구성된 경로
    # 초기: 단순 웨이포인트 추적 로직
    # 중장기: 코너링에 대한 Catmull-Rom Spline 보간을 통해 부드러운 경로 생성 및 추적으로 할지

    # (도착 판단 및 웨이포인트 교체)1. 현재 웨이포인트 선택 및 도달 여부 확인
    while True:
        current_waypoint = waypoints.peek()
        print("\n\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!peek!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n")
        if current_waypoint is None:
            # 웨이포인트가 없으면 정지
            WS_command, WS_weight = "STOP", 1.0
            AD_command, AD_weight = "", 0.0
            return WS_command, WS_weight, AD_command, AD_weight
        distance = math.sqrt((current_waypoint.x - player_x)**2 + (current_waypoint.z - player_z)**2)
        print("Distance to Waypoint:", distance)
        # 도착 판단: 웨이포인트에 1.0 미터 이내로 접근했으면 도달한 것으로 간주
        if distance <= 1.0:
            print("\n\n\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!REACHED WAYPOINT!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n\n\n")
            WS_command, WS_weight = "STOP", 1.0
            AD_command, AD_weight = "", 0.0
            waypoints.pop() # 다음 웨이포인트로 교체
            return WS_command, WS_weight, AD_command, AD_weight
        
        # 만약 웨이포인트에 도달하지 않았으면, 루프 탈출
        break

    print("현재 향하는 웨이포인트:", current_waypoint.x, current_waypoint.z)
    # (회전)1. 현재 탱크 위치와 웨이포인트 간의 수평각 계산
    dx = current_waypoint.x - player_x
    dz = current_waypoint.z - player_z
    target_angle = math.degrees(math.atan2(dx, dz)) % 360
    # print("Target Angle:", target_angle)

    # (회전)2. 현재 탱크의 수직각, 수평각을 확인하여 웨이포인트 방향으로 회전 명령 생성
    # - 전속력(weight = 1.0) 회전 수행
    # - 만약, 탱크의 수평각이 목표 수평각보다 5도 이내로 들어오면, 회전 명령 중지
    angle_diff = abs(player_body_x - target_angle)
    # print("Angle Diff:", angle_diff)
    if angle_diff > 20:
        
        if (player_body_x - target_angle + 360) % 360 > 180:
            AD_command, AD_weight = "D", 1.0
            # print("Rotate D 1.0")
        else:
            AD_command, AD_weight = "A", 1.0
            # print("Rotate A 1.0")

    # (회전) 3. 회전 명령 중지 후, 만약, 탱크의 수평각이 목표 수평각보다 1도 이상 크거나, 작으면, 반대로 역 조정 명령 생성
    elif angle_diff > 0.8:
        AD_command, AD_weight = "", 0.0 # 명령 초기화
        if player_body_x - target_angle > 0.5:
            # print("Rotate A 0.05")
            AD_command, AD_weight = "A", 0.05
        elif player_body_x - target_angle < -0.5:
            # print("Rotate D 0.05")
            AD_command, AD_weight = "D", 0.05
    # (회전) 4. 만약, 탱크의 회전각이 웨이포인트 방향과 일치하면, 저속 전진 명령 생성
    elif angle_diff <= 0.8:
        WS_command, WS_weight = "W", 0.3
        # print("Move W 0.3")

    return WS_command, WS_weight, AD_command, AD_weight

def stabilizer(player_x, player_y, player_turret_x, player_turret_y, enemy_x, enemy_y):
    QE_command, QE_weight, RF_command, RF_weight = 0.0, 0.0, 0.0, 0.0
    # not yet
    return QE_command, QE_weight, RF_command, RF_weight

def fire_calculation(): # 사격 계산 함수
    # not yet
    QE_command, QE_weight, RF_command, RF_weight, fire_command = 0.0, 0.0, 0.0, 0.0, False
    return QE_command, QE_weight, RF_command, RF_weight, fire_command

def turret_control(enemy_detection, enemy_in_fov, player_x, player_y, player_turret_x, player_turret_y, enemy_x, enemy_y): # 포탑 제어 함수

    if enemy_detection == True and enemy_in_fov == False: # 적이 탐지되었지만, 시야에 없는 경우
        QE_command, QE_weight, RF_command, RF_weight = stabilizer(player_x, player_y, player_turret_x, player_turret_y, enemy_x, enemy_y) # 스테빌 라이저로 마지막으로 포착된 적 위치에 조준 안정화

    elif enemy_detection == True and enemy_in_fov == True: # 적이 탐지되고, 시야에 있는 경우
        QE_command, QE_weight, RF_command, RF_weight, fire_command = fire_calculation() # 사격 계산 수행하여 조준 및 사격 명령

    return QE_command, QE_weight, RF_command, RF_weight, fire_command

def body_control(player_x, player_z, player_body_x, player_speed): # 차체 제어 함수
    print("body_control")
    # path = path_finding() # 경로 탐색 함수
    path = waypoints # 수동 경로 할당

    WS_command, WS_weight, AD_command, AD_weight = path_tracking(player_x, player_z, player_body_x, player_speed)
    
    return WS_command, WS_weight, AD_command, AD_weight

# --------------------------------------------------------------------

app = Flask(__name__) # Flask 앱 생성
# --------------------------------------------------------------------

@app.route('/info', methods=['POST'])
def info():
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight # turret
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight # body
    global enemy_detection, enemy_in_fov # detect API

    data = request.get_json(force=True)
    if not data:
        return jsonify({"error": "No JSON received"}), 400

    time = data["time"]
    distance = data["distance"]

    player_x = data["playerPos"]["x"]
    player_y = data["playerPos"]["y"]
    player_z = data["playerPos"]["z"]

    player_speed = data["playerSpeed"]
    player_health = data["playerHealth"]
    player_turret_x = data["playerTurretX"]
    player_turret_y = data["playerTurretY"]
    player_body_x = data["playerBodyX"]
    player_body_y = data["playerBodyY"]
    player_body_z = data["playerBodyZ"]

    enemy_x = data["enemyPos"]["x"]
    enemy_y = data["enemyPos"]["y"]
    enemy_z = data["enemyPos"]["z"]

    enemy_speed = data["enemySpeed"]
    enemy_health = data["enemyHealth"]
    enemy_turret_x = data["enemyTurretX"]
    enemy_turret_y = data["enemyTurretY"]
    enemy_body_x = data["enemyBodyX"]
    enemy_body_y = data["enemyBodyY"]
    enemy_body_z = data["enemyBodyZ"]

    # Turret Control
    # QE_command, QE_weight, RF_command, RF_weight, fire_command = turret_control(enemy_detection, enemy_in_fov, player_x, player_y, player_turret_x, player_turret_y, enemy_x, enemy_y)

    # Body Control
    global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = body_control(player_x, player_z, player_body_x, player_speed)

    return jsonify({"status": "success", "control": ""})

# --------------------------------------------------------------------

@app.route('/get_action', methods=['POST'])
def get_action():
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight # turret
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight # body
    global global_fire_command # fire

    # 기존에 계산된 명령어와 가중치에 따라 행동 결정
    action = {
        "moveWS":  {"command": global_WS_command, "weight": global_WS_weight},
        "moveAD":  {"command": global_AD_command, "weight": global_AD_weight},
        "turretQE": {"command": global_QE_command, "weight": global_QE_weight},
        "turretRF": {"command": global_RF_command, "weight": global_RF_weight},
        "fire":     global_fire_command
    }
    
    return jsonify(action)

# --------------------------------------------------------------------

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": 0,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 0,
        "rdStartX": 59, #Red Start Position
        "rdStartY": 10,
        "rdStartZ": 280,
        "trackingMode": True,
        "detactMode": False,
        "logMode": True,
        "enemyTracking": False,
        "saveSnapshot": False,
        "saveLog": True,
        "saveLidarData": False,
        "lux": 30000
    }
    print("🛠️ Initialization config sent via /init:", config)
    return jsonify(config)

# --------------------------------------------------------------------

@app.route('/start', methods=['GET'])
def start():
    print("🚀 /start command received")
    return jsonify({"control": ""})

# --------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

# --------------------------------------------------------------------
