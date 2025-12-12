from flask import Flask, request, jsonify
import requests

# info, get_action | Tank Turret Rotation Control
global_QE_command, global_QE_weight, global_RF_command, global_RF_weight = "", 0.0, "", 0.0
# info, get_action | Tank Body Movement Control
global_WS_command, global_WS_weight, global_AD_command, global_AD_weight = "", 0.0, "", 0.0
# info, get_action | Tank Fire Control
global_fire_command = False


def send_fcs(request_data=None):
    external_server = "http://192.168.0.32:5000/get_fcs"
    try:
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        print("fcs_data", ext_result)
        print("fcs_type", type(ext_result))
    except Exception as e:
        print("fcs_except")
        ext_result = {"error": str(e)}
    return ext_result

def send_adcs(request_data=None):
    external_server = "http://192.168.0.124:5000/get_adcs"
    try:
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        print("adcs_data", ext_result)
        print("adcs_type", type(ext_result))
    except Exception as e:
        print("adcs_except")
        ext_result = {"error": str(e)}
    return ext_result

def send_vdrs(request_data=None):
    external_server = "http://192.168.0.15:5000/get_vdrs"
    try:
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        print("vdrs_data", ext_result)
        print("vdrs_type", type(ext_result))
    except Exception as e:
        print("vdrs_except")
        ext_result = {"error": str(e)}
    return ext_result

def send_tpp(request_data=None):
    external_server = "http://192.168.0.132:5000/get_tpp"
    try:
        ext_response = requests.post(external_server, json=request_data, timeout=2)
        ext_result = ext_response.json()
        print("tpp_data", ext_result)
        print("tpp_type", type(ext_result))
    except Exception as e:
        print("tpp_except")
        ext_result = {"error": str(e)}
    return ext_result

# --------------------------------------------------------------------

app = Flask(__name__)

@app.route('/info', methods=['POST'])
def info():
    global global_QE_command, global_QE_weight, global_RF_command, global_RF_weight
    global global_WS_command, global_WS_weight, global_AD_command, global_AD_weight
    global global_fire_command
    
    request_data = request.get_json(force=True)
    if not request_data:
        return jsonify({"error": "No JSON received"}), 400

    time = request_data["time"]
    distance = request_data["distance"]

    player_x = request_data["playerPos"]["x"]
    player_y = request_data["playerPos"]["y"]
    player_z = request_data["playerPos"]["z"]

    player_speed = request_data["playerSpeed"]
    player_health = request_data["playerHealth"]
    player_turret_x = request_data["playerTurretX"]
    player_turret_y = request_data["playerTurretY"]
    player_body_x = request_data["playerBodyX"]
    player_body_y = request_data["playerBodyY"]
    player_body_z = request_data["playerBodyZ"]

    enemy_x = request_data["enemyPos"]["x"]
    enemy_y = request_data["enemyPos"]["y"]
    enemy_z = request_data["enemyPos"]["z"]

    enemy_speed = request_data["enemySpeed"]
    enemy_health = request_data["enemyHealth"]
    enemy_turret_x = request_data["enemyTurretX"]
    enemy_turret_y = request_data["enemyTurretY"]
    enemy_body_x = request_data["enemyBodyX"]
    enemy_body_y = request_data["enemyBodyY"]
    enemy_body_z = request_data["enemyBodyZ"]

    request_data_vdrs = {
        "time" : time, # 시뮬레이터 시각
        "ally_body_pos": {"x": player_x, "y": player_y, "z": player_z}, # 아군 전차 차체 X, Y, Z 위치
        "ally_body_angle": {"x": player_turret_x, "y": player_turret_y}, # 아군 전차 차체 X, Y, Z 각도
        "ally_speed": player_speed, # 아군 전차 속도(m/s)
        "waypoints": [ # 경로
            [123, 132, 123],
            [123, 132, 123],
            [123, 132, 123]
        ]
    }
    # send_vdrs(request_data_vdrs)

    request_data_tpp = {
        "time" : time, # 시뮬레이터 시각
        "ally_body_pos": {"x": player_x, "y": player_y, "z": player_z}, # 아군 전차 차체 X, Y, Z 위치
        "target_pos" : {"x": enemy_x, "y": enemy_y, "z": enemy_z}, # 목적지 X, Y, Z 좌표
        "map_info" : { "test": "test"} # IBSM 전장 상황 정보
    }
    send_tpp(request_data_tpp)

    request_data_fcs = {
        "time" : time, # 시뮬레이터 시각
        "ally_body_pos": {"x": player_x, "y": player_y, "z": player_z}, # 아군 전차 차체 X, Y, Z 속도
        "ally_body_angle": {"x": player_body_x, "y": player_body_y, "z": player_body_z}, # 아군 전차 차체 X, Y, Z 각도
        "ally_speed": player_speed, # 아군 전차 속도(m/s)
        "ally_turret_angle": {"x": player_turret_x, "y": player_turret_y}, # 아군 전차 포탑 X, Y 각도
        "ibsm_target_pos" : {"x": enemy_x, "y": enemy_y, "z": enemy_z}, # IBSM 상의 타겟 X, Y, Z 좌표
        "may_type" : 0 # 현재 맵 유형
    }
    fcs_data = send_fcs(request_data_fcs)
    global_QE_command = fcs_data['QE_command']
    global_QE_weight = fcs_data['QE_weight']
    global_RF_command = fcs_data['RF_command']
    global_RF_weight = fcs_data['RF_weight']
    global_fire_command = fcs_data['fire_command']

    request_data_adcs = {
        "time" : time, # 시뮬레이터 시각
        "ally_body_pos": {"x": player_x, "y": player_y, "z": player_z}, # 아군 전차 차체 X, Y, Z 속도
        "ally_body_angle": {"x": player_body_x, "y": player_body_y, "z": player_body_z}, # 아군 전차 차체 X, Y, Z 각도
        "ally_speed": player_speed, # 아군 전차 속도(m/s)
        "ally_turret_angle": {"x": player_turret_x, "y": player_turret_y}, # 아군 전차 포탑 X, Y 각도
        "ibsm_target_pos" : {"x": enemy_x, "y": enemy_y, "z": enemy_z}, # IBSM 상의 타겟 X, Y, Z 좌표
        "may_type" : 0 # 현재 맵 유형
    }
    adcs_data = send_adcs(request_data_adcs)
    global_WS_command = adcs_data['WS_command']
    global_WS_weight = adcs_data['WS_weight']
    global_AD_command = adcs_data['AD_command']
    global_AD_weight = adcs_data['AD_weight']
    print("global_WS_command:", global_WS_command, "global_WS_weight:", global_WS_weight)
    print("global_AD_command:", global_AD_command, "global_AD_weight:", global_AD_weight)
    return jsonify({"status": "success", "control": ""})

@app.route('/get_action', methods=['POST'])
def get_action():
    request_data = request.get_json(force=True)
    if not request_data:
        return jsonify({"error": "No JSON received"}), 400

    # 기존에 계산된 명령어와 가중치에 따라 행동 결정
    action = {
        "moveWS":  {"command": global_WS_command, "weight": global_WS_weight},
        "moveAD":  {"command": global_AD_command, "weight": global_AD_weight},
        "turretQE": {"command": global_QE_command, "weight": global_QE_weight},
        "turretRF": {"command": global_RF_command, "weight": global_RF_weight},
        "fire": global_fire_command
    }

    print("action:", action)

    return jsonify(action)

#Endpoint called when the episode starts
@app.route('/init', methods=['GET'])
def init():
    config = {
        "startMode": "start",  # Options: "start" or "pause"
        "blStartX": 0,  #Blue Start Position
        "blStartY": 10,
        "blStartZ": 0,
        "rdStartX": 300, #Red Start Position
        "rdStartY": 10,
        "rdStartZ": 150,
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

@app.route('/')
def home():
    return 'Hello, World!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
