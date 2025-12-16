"""
[통합 시스템] 스태빌라이저 (Lag 대응형) + FCS (탄도 계산 및 이동 예측)

1. 스태빌라이저: 단순화된 P(비례) + FF(피드포워드) 제어를 사용하여 통신 지연(Lag)이 발생해도 포탑이 튀지 않도록 함.
2. FCS: 지형 고도 데이터를 로딩하고, 탄도학을 계산하여 사격 가능 여부 판단 및 이동 좌표를 추천함.
"""
############################ 필요 라이브러리 선언 ###########################
import os
from flask import Flask, request, jsonify
import math
from datetime import datetime

"""
[Simpler is Better] 가변 P + FF 제어기 (Lag 대응형)

기존 PID 제어에서 D(미분)항은 통신 지연(dt 불안정) 시 값이 폭주하여 포탑을 떨게 만듭니다.
따라서 D항을 제거하고, 대신 '목표와의 거리'에 따라 P게인(힘)을 조절하는 방식을 사용합니다.

1. 가변 P 제어:
    - 목표가 멀리 있음 (> 5도): 강한 힘(Kp_fast)으로 빠르게 회전
    - 목표가 가까이 있음 (< 5도): 약한 힘(Kp_slow)으로 천천히 회전 (브레이크 효과)

2. FF (Feed Forward) 제어:
    - 차체가 회전(A/D키)할 때, 그 반대 방향으로 즉시 포탑을 돌려 조준을 유지함 (반응성 극대화)

3. Fire Zone을 추가하여 적 반경 최대 사격거리안에 들어오면 즉각 사격을 추가함
"""

# 현재 시간 기반 파일 이름 생성
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = f"{timestamp}_log.txt"

def write_log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 밀리초 3자리까지
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"{now} - {message}\n")

############################## Flask 추가 ################################
app = Flask(__name__)

##################### IBSM에 보낼 데이터의 기본값 ##########################
qe_command = ""         # 포탑 좌우 회전 명령 (Q/E)
qe_weight = 0           # 포탑 회전 강도 (0.0 ~ 1.0)
rf_command = ""         # 포신 상하 조절 명령 (R/F)
rf_weight = 0           # 포신 조절 강도
fire_command = False    # 발사 허가 여부
fire_target = None  # 조준하고 있는 적의 좌표
new_fire_point = None   # 사격 불가능 시 이동해야 할 추천 좌표
enemy_in_range = False # 적 사정 거리 내 존재 여부

######################## 스태빌라이져용 전역변수 ###########################
# 물체(장애물/적) 조준용 타깃 좌표
aim_target_x = None
aim_target_y = None
aim_target_z = None

########################### FCS용 전역변수 ###############################
# (현재 사용하지 않음 - 향후 확장 시 사용 가능)

########################### 스태빌라이저 기능 #############################
def normalize_angle_deg(angle: float) -> float:
    """
    각도를 -180도 ~ +180도 사이로 변환합니다.
    예: 270도 -> -90도, 370도 -> 10도
    """
    return (angle + 180.0) % 360.0 - 180.0

class SimpleTurretStabilizer:
    """
    [Simpler is Better] 가변 P + FF 제어기 (Lag 대응형)
    
    기존 PID 제어에서 D(미분)항은 통신 지연(dt 불안정) 시 값이 폭주하여 포탑을 떨게 만듭니다.
    따라서 D항을 제거하고, 대신 '목표와의 거리'에 따라 P게인(힘)을 조절하는 방식을 사용합니다.
    
    1. 가변 P 제어:
       - 목표가 멀리 있음 (> 5도): 강한 힘(Kp_fast)으로 빠르게 회전
       - 목표가 가까이 있음 (< 5도): 약한 힘(Kp_slow)으로 천천히 회전 (브레이크 효과)
    
    2. FF (Feed Forward) 제어:
       - 차체가 회전(A/D키)할 때, 그 반대 방향으로 즉시 포탑을 돌려 조준을 유지함 (반응성 극대화)
    """
    def __init__(self):
        # ========= [Yaw: 좌우 제어 변수] =================
        # 1. 원거리 P게인: 목표와 1도 이상 차이날 때 적용. 빠르게 추적.
        self.Kp_fast = 0.04  
        
        # 2. 근거리 P게인: 목표와 1도 이내일 때 적용. 
        #    천천히 움직여서 오버슈트(목표를 지나침)를 방지하는 '브레이크' 역할.
        self.Kp_slow = 0.02  

        # 3. FF게인 (AD 역보상 계수): 
        #    1.0이면 차체 회전 속도만큼 정확히 반대로 돌리려 시도함.
        self.Kff_ad  = 0.999  

        # 4. 정밀 조준 구간 (단위: 도)
        #    이 각도 안으로 들어오면 Kp_slow를 사용하여 감속함.
        self.SLOW_ZONE = 1.0 

        self.YAW_DEADBAND   = 0.5   # 오차가 0.5도 이내면 아예 움직이지 않음 (떨림 방지)
        
        # ======== [Pitch: 상하 제어 변수 추가] ===========
        # self.Kp_pitch = 0.1   # 상하 움직임은 중력을 이겨야 하므로 P게인을 좀 더 높게

        # self.Kff_pitch = 0.0  # (선택) 급정거 시 차체가 앞으로 쏠리는 것을 보상하려면 사용
        
        # self.PITCH_DEADBAND = 0.2

        # ===================================================
        self.MAX_QE         = 2.0   # 모터 최대 출력 제한
        self.MIN_QE_OUTPUT  = 0.01  # 모터 최소 출력 (이것보다 작으면 무시)

    def update(
        self,
        *,
        # 시간 관련 변수는 이제 필요 없지만 인터페이스 유지를 위해 받음
        time_val: float, 
        player_x: float, player_y: float, player_z: float,
        player_turret_x: float,     # 현재 포탑의 절대 Yaw 각도
        target_x: float, target_y: float, target_z: float,
        body_angle_x: float,            # 차체의 절대 Yaw 각도
        AD_command: str,           # 키보드 A/D 입력 상태
        AD_weight: float,      # 키보드 입력 강도
        WS_command: str,
        WS_weight: float,
        player_speed: float,
        body_WS_weight: float = 0.0
        
    ):
        # 1. 목표 지점을 향한 절대 방위각(Target Yaw) 계산
        dx = target_x - player_x
        dz = target_z - player_z
        target_yaw = math.degrees(math.atan2(dx, dz))
        if target_yaw < 0:
            target_yaw += 360.0

        # 2. 현재 오차 계산 (목표 각도 - 내 포탑 각도)
        #    normalize를 통해 -180 ~ 180 사이의 최단 경로 오차를 구함
        yaw_err_now = normalize_angle_deg(target_yaw - player_turret_x)

        # 3. 데드밴드 체크
        #    오차가 매우 작고(0.5도 미만), 플레이어가 차체를 회전시키지 않고 있다면
        #    불필요한 미세 조정을 막기 위해 정지(0.0) 반환
        if abs(yaw_err_now) < self.YAW_DEADBAND and AD_weight < 0.1:
            write_log("스태빌라이저: 데드밴드 내 오차 및 차체 미회전 감지, 포탑 정지")
            return "", 0.0

        # ================= [핵심 제어 로직] =================
        
        # (A) 가변 P 제어: 오차 크기에 따라 회전 힘 결정
        current_kp = 0.0
        if abs(yaw_err_now) > self.SLOW_ZONE:
            # 목표가 멀리 있다 -> Kp_fast로 빠르게 회전
            current_kp = self.Kp_fast
        else:
            # 목표에 거의 다 왔다 -> Kp_slow로 감속하여 부드럽게 안착
            current_kp = self.Kp_slow
            
        P = current_kp * yaw_err_now
        
        # (B) FF 제어 (Feed Forward): 차체 회전 보상
        #     차체가 왼쪽(A)으로 돌면 포탑은 오른쪽(E)으로 돌아야 같은 곳을 볼 수 있음
        FF = 0.0
        write_log(f"스태빌라이저: 차체 AD명령={AD_command}, 가중치={AD_weight:.3f}")
        if AD_command == "A":   # 차체 좌회전
            FF = self.Kff_ad * AD_weight  # 포탑 우회전 힘 추가 (+)
            write_log("차체 좌회전 감지: 포탑 우회전 FF 적용, 힘: {:.3f}".format(FF))
        elif AD_command == "D": # 차체 우회전
            FF = -self.Kff_ad * AD_weight # 포탑 좌회전 힘 추가 (-)
            write_log("차체 우회전 감지: 포탑 좌회전 FF 적용, 힘: {:.3f}".format(FF))

        # (C) 최종 출력 합산
        u = P + FF
        # ==========================================================

        # 4. 하드웨어/게임 엔진 한계에 맞게 출력 제한 (Clamping)
        if u > self.MAX_QE: u = self.MAX_QE
        elif u < -self.MAX_QE: u = -self.MAX_QE

        # 5. 너무 작은 출력은 무시 (모터 보호 및 떨림 방지)
        if abs(u) < self.MIN_QE_OUTPUT:
            write_log("스태빌라이저: 최소 출력 미만 감지, 포탑 정지")
            return "", 0.0

        # 6. 최종 명령 생성 (양수면 E, 음수면 Q)
        write_log("스태빌라이저: 포탑 회전 명령 생성, 명령: {}, 힘: {:.3f}".format("E" if u > 0 else "Q", abs(u)))
        if u > 0:
            return "E", u
        else:
            return "Q", -u

# 전역 스태빌라이저 인스턴스 생성
yaw_stabilizer = SimpleTurretStabilizer()

def turret_control(request_data: dict):
    """
    IBSM에서 들어온 데이터를 파싱하여 스태빌라이저(yaw_stabilizer)를 실행시키는 래퍼 함수
    """
    global qe_command, qe_weight, aim_target_x, aim_target_y, aim_target_z
    
    # 1) JSON 데이터 파싱 (안전하게 기본값 처리)
    time_val = float(request_data.get("time", 0.0))

    ally_pos   = request_data.get("ally_body_pos", {}) or {}
    ally_ang   = request_data.get("ally_body_angle", {}) or {}
    turret_ang = request_data.get("ally_turret_angle", {}) or {}
    target_pos = request_data.get("ibsm_target", {}) or {}

    player_x = float(ally_pos.get("x", 0.0))
    player_y = float(ally_pos.get("y", 0.0))
    player_z = float(ally_pos.get("z", 0.0))

    player_turret_x = float(turret_ang.get("x", 0.0))   # 포탑 Yaw
    body_angle_x = float(ally_ang.get("y", 0.0))            # 차체 Yaw
    player_speed = float(request_data.get("ally_speed", 0.0))

    # 차체 제어 명령 파싱 (FF 제어에 사용)
    AD_command = request_data.get("AD_command", "")
    AD_weight = float(request_data.get("AD_weight", 0.0))
    WS_command = request_data.get("WS_command", "")
    WS_weight = float(request_data.get("WS_weight", 0.0))
    write_log(f"차체 제어 명령 수신 - AD: {AD_command} (가중치: {AD_weight:.3f}), WS: {WS_command} (가중치: {WS_weight:.3f})")

    # 2) 타깃 설정 (IBSM에서 온 타깃이 없으면 이전 타깃 유지)
    if "x" in target_pos and "y" in target_pos and "z" in target_pos:
        target_x = float(target_pos.get("x", 0.0))
        target_y = float(target_pos.get("y", 0.0))
        target_z = float(target_pos.get("z", 0.0))
        aim_target_x, aim_target_y, aim_target_z = target_x, target_y, target_z
        
    elif aim_target_x is not None:
        target_x, target_y, target_z = aim_target_x, aim_target_y, aim_target_z
    else:
        # 타깃이 아예 없으면 아무것도 안 함
        return qe_command, qe_weight

    # 3) 스태빌라이저 업데이트 실행
    write_log("스태빌라이저 업데이트 실행: 타깃 좌표 x={:.2f}, y={:.2f}, z={:.2f}".format(target_x, target_y, target_z))
    QE_cmd, QE_w = yaw_stabilizer.update(
        time_val=time_val,
        player_x=player_x,
        player_y=player_y,
        player_z=player_z,
        player_turret_x=player_turret_x,
        target_x=target_x,
        target_y=target_y,
        target_z=target_z,
        body_angle_x=body_angle_x,
        AD_command=AD_command,
        AD_weight=AD_weight,
        player_speed=player_speed,
        WS_command=WS_command,
        WS_weight=WS_weight
    )

    # 전역 변수에 결과 저장 (나중에 반환됨)
    qe_command = QE_cmd
    qe_weight  = QE_w

############################### FCS 기능 ################################
# ally_body_angle['y'] 시뮬레이터 버그 보정 함수
def correct_body_y_angle(raw_body_y: float) -> float:
    """
    시뮬레이터 버그로 인해 잘못 들어오는 차체 Y축 각도를 보정
    - 180도보다 크면 (예: 355.54) → 360 - 값 (4.46)
    - 180도보다 작으면 (예: 3.91) → -값 (-3.91)
    """
    if raw_body_y > 180.0:
        return 360.0 - raw_body_y
    else:
        return -1.0 * raw_body_y

# 2. 발사 각도(고각) 계산 (수치해석)
def find_elevation_angle(x, y, v0, g=9.81):
    low = 0.01
    high = math.radians(89)
    for _ in range(1000):
        mid = (low + high) / 2
        cos2 = math.cos(mid) ** 2
        tan = math.tan(mid)
        y_calc = x * tan - (g * x**2) / (2 * v0**2 * cos2)
        if abs(y_calc - y) < 1e-6:
            return math.degrees(mid)
        if y_calc < y:
            low = mid
        else:
            high = mid
    return None

def calculate_rf(elevation_angle, ally_turret_angle_y, max_angle=10.0, dead_zone=0.1, min_weight=0.1, max_weight=1.0):
    """
    계산된 발사 고각과 현재 포탑 수직 각도의 차이에 따라 RF 명령 생성
    
    Args:
        elevation_angle: 계산된 발사 고각 (degrees)
        ally_turret_angle_y: 현재 포탑의 수직 각도 (degrees)
        max_angle: 이 각도 이상 차이 나면 항상 max_weight (default: 10.0)
        dead_zone: 이 각도보다 차이가 작으면 weight=0 (멈춤) (default: 0.1)
        min_weight: 최소 weight 값 (default: 0.3)
        max_weight: 최대 weight 값 (default: 1.0)
    
    Returns:
        RF_command: 'R' (상승) 또는 'F' (하강) 또는 '' (정지)
        RF_weight: 제어 강도 (0.0 ~ 1.0)
    """
    # 각도 차이 계산 (목표 - 현재)
    angle_diff = elevation_angle - ally_turret_angle_y
    diff = abs(angle_diff)
    
    # weight 계산 (angle_to_weight 로직 통합)
    if diff < dead_zone:
        # 목표 각도와의 차이가 dead_zone보다 작을 경우, 0을 반환, 회전 멈춤
        weight = 0.0
    elif diff >= max_angle:
        # 목표 각도와의 차이가 최대 max_angle보다 클 경우, 무조건 최대 파워로 회전
        weight = max_weight
    else:
        # dead_zone ~ max_angle 사이를 min_weight ~ max_weight로 선형 매핑
        t = (diff - dead_zone) / (max_angle - dead_zone)
        weight = min_weight + (max_weight - min_weight) * t
    
    # weight가 0이면 정지
    if weight == 0.0:
        return "", 0.0
    
    # 양수면 R (상승), 음수면 F (하강)
    if angle_diff > 0:
        return "R", weight
    else:
        return "F", weight

def find_new_fire_point(ally_pos, ibsm_target, corrected_body_y, muzzle_velocity=61, G=9.81):
    """
    적을 중심으로 한 원(반지름 30m) 위에서 현재 아군 전차 위치와 가장 가까운 점을 찾아 반환
    
    원의 방정식: (x - center_x)^2 + (z - center_z)^2 = radius^2
    현재 위치에서 원의 중심으로 향하는 방향벡터를 구하고, 
    원 위의 가장 가까운 점 = 중심 - 방향벡터 * 반지름
    """
    # 적 위치를 원의 중심으로 설정
    center_x = ibsm_target['x']
    center_z = ibsm_target['z']
    radius = 80.0  # 원의 반지름 (100m)
    
    # 현재 아군 위치에서 적(원의 중심)까지의 벡터
    dx = center_x - ally_pos['x']
    dz = center_z - ally_pos['z']
    distance_to_center = math.sqrt(dx**2 + dz**2)
    
    write_log(f"적과의 2D 수평 거리: {distance_to_center:.2f} m")
    write_log(f"적 중심 반지름 {radius}m 원 위의 가장 가까운 점 계산")
    
    if distance_to_center > 0:
        # 중심으로 향하는 단위 벡터
        unit_x = dx / distance_to_center
        unit_z = dz / distance_to_center
        
        # 원 위의 가장 가까운 점 = 중심 - (단위벡터 * 반지름)
        # 즉, 아군에서 적 방향으로 가되 적으로부터 반지름만큼 떨어진 지점
        move_x = center_x - unit_x * radius
        move_y = 0.0
        move_z = center_z - unit_z * radius
        
        # 계산된 점이 실제로 원 위에 있는지 검증 (디버깅용)
        verify_distance = math.sqrt((move_x - center_x)**2 + (move_z - center_z)**2)
        write_log(f"원 위의 점까지 중심거리 검증: {verify_distance:.2f}m (목표: {radius}m)")
        
        write_log(f"추천 이동 좌표 (적 중심 원 테두리):")
        write_log(f"이동 좌표: x={move_x:.2f}, y={move_y:.2f}, z={move_z:.2f}")
        
        return {"x": move_x, "y": move_y, "z": move_z}
    else:
        write_log("적과 같은 위치에 있습니다.")
        return None

# FCS 기능 메인
def fcs_function(request_data):
    global rf_command, rf_weight, fire_command, fire_target, new_fire_point, enemy_in_range
    
    # 전역 변수 초기화 (매 요청마다 초기화)
    rf_command = ""
    rf_weight = 0.0
    fire_command = False
    fire_target = None
    new_fire_point = None
    enemy_in_range = False

    # requset_data 파싱
    time = request_data.get("time", 0.0)
    ally_body_pos = request_data.get("ally_body_pos", {})
    ally_body_angle = request_data.get("ally_body_angle", {})
    ally_speed = request_data.get("ally_speed", 0.0)
    ally_turret_angle = request_data.get("ally_turret_angle", {})
    ibsm_target = request_data.get("ibsm_target", {})
    map_type = request_data.get("map_type", 0)
    AD_command = request_data.get("AD_command", "")
    AD_weight = request_data.get("AD_weight", 0.0)
    WS_command = request_data.get("WS_command", "")
    WS_weight = request_data.get("WS_weight", 0.0)

    # ally_body_angle['y'] 버그 조치(y축 각도가 0~360도로 반대 방향으로 들어오는 문제)
    raw_body_y = ally_body_angle.get('y', 0.0)
    corrected_body_y = correct_body_y_angle(raw_body_y)
    write_log(f"ally_body_angle['y'] 원본: {raw_body_y:.2f} → 보정됨: {corrected_body_y:.2f}")

    # 물리 상수
    G = 9.81 # 중력가속도
    muzzle_velocity = 61 # 포탄의 초기속도(61m/s)

    # 1. 수평거리 및 고저차 계산
    dx = ibsm_target['x'] - ally_body_pos['x']
    dy = ibsm_target['z'] - ally_body_pos['z']
    horizontal_distance = math.sqrt(dx**2 + dy**2)
    height_diff = ibsm_target['y'] - ally_body_pos['y'] # y축이 고도임

    elevation_angle = find_elevation_angle(horizontal_distance, height_diff, muzzle_velocity, G)
    if elevation_angle is not None:
        write_log(f"적 전차를 맞추기 위한 발사 고각: {elevation_angle:.2f}도")
    else:
        write_log("적 전차를 맞출 수 있는 발사 고각을 찾지 못했습니다.")

    # 4. 포탑 수직 각도 제한 체크 (기준: 차체 수직각 +15도 ~ -5도, 최대 10도까지 허용)
    turret_min_angle = corrected_body_y - 4
    turret_max_angle = corrected_body_y + 9  # 최대 10도까지만 허용
    write_log(f"포탑 수직 각도 제한: {turret_min_angle:.2f}도 ~ {turret_max_angle:.2f}도 (최대 -5도, 10도 기준)")

    if elevation_angle is not None:
        if turret_min_angle <= elevation_angle <= turret_max_angle:
            enemy_in_range = True
            write_log(f"발사 고각({elevation_angle:.2f}도)는 포탑 수직 각도 제한 내에 있습니다. (최대 10도 기준), 조준 및 사격을 개시합니다.")
            
            # 5. RF 제어 명령 생성
            rf_command, rf_weight = calculate_rf(elevation_angle, ally_turret_angle['y'])
            write_log(f"RF 명령: {rf_command}, RF 강도: {rf_weight:.2f}")
            
            # 6. 사격 명령 생성 (수평/수직 각도가 모두 정렬되었을 때만 발사)
            # 수평 방위각 계산
            azimuth_rad = math.atan2(dy, dx)
            azimuth_deg_math = math.degrees(azimuth_rad)
            azimuth_deg_12oclock = (90 - azimuth_deg_math) % 360
            
            # 수평 각도 오차 계산
            x_angle_diff = normalize_angle_deg(azimuth_deg_12oclock - ally_turret_angle['x'])
            
            # 수직 각도 오차 계산
            y_angle_diff = elevation_angle - ally_turret_angle['y']
            
            write_log(f"수평 각도 오차: {x_angle_diff:.2f}도, 수직 각도 오차: {y_angle_diff:.2f}도")
            
            # 허용 오차 범위 내에 있으면 발사
            YAW_TOLERANCE = 0.5   # 수평 오차 허용 범위 (도)
            PITCH_TOLERANCE = 0.1 # 수직 오차 허용 범위 (도)
            
            if abs(x_angle_diff) < YAW_TOLERANCE and abs(y_angle_diff) < PITCH_TOLERANCE:
                fire_command = True
                fire_target = ibsm_target
                write_log("사격 조건 충족! 발사 명령 전송")
            else:
                fire_command = False
                write_log(f"조준 중... (수평: {abs(x_angle_diff):.2f}/{YAW_TOLERANCE}도, 수직: {abs(y_angle_diff):.2f}/{PITCH_TOLERANCE}도)") 
            
        else:
            write_log(f"발사 고각({elevation_angle:.2f}도)는 포탑 수직 각도 제한({turret_min_angle:.2f}도 ~ {turret_max_angle:.2f}도, 최대 10도 기준)를 벗어납니다. 사격이 가능한 새로운 위치를 계산합니다.")
            new_fire_point = find_new_fire_point(ally_body_pos, ibsm_target, corrected_body_y)
            write_log(f"새로운 사격 위치 추천: {new_fire_point}")
    else:
        write_log("사격이 가능한 새로운 위치를 계산합니다.")
        new_fire_point = find_new_fire_point(ally_body_pos, ibsm_target, corrected_body_y)
        write_log(f"새로운 사격 위치 추천: {new_fire_point}")

##################### IBSM이 호출할 FCS의 엔드포인트 #######################
@app.post("/get_fcs")
def get_fcs():
    # IBSM에서 받아온 데이터를 저장
    request_data = request.get_json(force=True, silent=True) or {}
    write_log(f"FCS 수신 데이터: {request_data}")

    # 스태빌라이저 (QE)
    turret_control(request_data)

    # FCS (RF + fire + 사격 불가시 새 이동 지점)
    fcs_function(request_data)

    # IBSM으로 보낼 데이터 : 
    response_data = {
        "QE_command" : qe_command,          # 포탑 좌 / 우 회전 방향 제어, string형, 'Q' 혹은 'E'
        "QE_weight" : qe_weight,            # 포탑 좌 / 우 회전 세기, float형
        "RF_command" : rf_command,          # 포신 상 / 하 방향 제어, string형, 'R' 혹은 'F'
        "RF_weight" : rf_weight,            # 포신 상 / 하 세기, float형
        "fire_command" : fire_command,      # 사격 여부, bool형, True or False
        "fire_target" : fire_target,        # 사격 대상, dict형, {"x": 15.0, "y": 25.0, "z": 0.0}
        "new_fire_point" : new_fire_point,   # 현 위치 즉시 사격 불가 시 사격 가능 지점, dict형, {"x": 15.0, "y": 25.0, "z": 0.0}
        "enemy_in_range" : enemy_in_range   # 사정 범위 내인지 여부(탄도 가능성)
    }
    # debug: log flags explicitly for easier tracing
    write_log(f"FCS flags: enemy_in_range={enemy_in_range}")
    write_log(f"FCS 반환 데이터: {response_data}")

    # 호출자(IBSM)에게 결과 반환
    return jsonify(response_data)


################################ 메인매서드 ################################ㅉ
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)