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
import pandas as pd
import numpy as np

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
enemy_in_range = False  # 적 사정거리 내 존재 여

######################## 스태빌라이져용 전역변수 ###########################
# 물체(장애물/적) 조준용 타깃 좌표
aim_target_x = None
aim_target_y = None
aim_target_z = None

########################### FCS용 전역변수 ###############################
# 맵 데이터(CSV)를 메모리에 로드하여 저장하는 변수들 (매번 파일 읽는 것 방지)
altitude_df = None              # Pandas DataFrame 형태의 고도 데이터
altitude_grid = None            # Numpy 2D 배열 형태의 고도 그리드 (검색 속도 최적화)
altitude_grid_shape = None      # 그리드 크기 (Max Z, Max X)

# 사격 기록 시간 저장을 위한 전역변수
pitch_stuck_start_time = None

# 포구 높이 오프셋 (차체 기준 → 월드 y)
MUZZLE_HEIGHT_OFFSET = 1.5              # 포구 높이는 정확한 높이를 찾을 때까지 계속 조정 필요.

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
# ally_body_angle['y'] 시뮬레이터 버그 보정 함수                               # 차체의 Y각(yaw)이 이상하게 들어오는 버그를 고치는 함수라는 설명
def correct_body_y_angle(raw_body_y: float) -> float:                      # raw_body_y(원래 들어온 차체 Y각)를 받아서 보정된 각도를 돌려주는 함수 정의
    """
    시뮬레이터 버그로 인해 잘못 들어오는 차체 Y축 각도를 보정
    - 180도보다 크면 (예: 355.54) → 360 - 값 (4.46)
    - 180도보다 작으면 (예: 3.91) → -값 (-3.91)
    """                                                                    # 위에 적은 설명을 파이썬이 인식하는 공식 문서 문자열(주석 겸용)로 남겨둠
    if raw_body_y > 180.0:                                                 # 만약 들어온 각도가 180도보다 크다면 (예: 뒤쪽 방향을 가리키는 값)
        return 360.0 - raw_body_y                                          # 360 - 각도로 바꿔서 "앞쪽 기준"의 작은 양수 각도로 바꿔서 반환
    else:                                                                  # 그렇지 않고 180도 이하라면 (얼추 앞쪽 방향 값)
        return -1.0 * raw_body_y                                           # 부호를 반대로 해서 음수 각도로 만들어 반환 (왼쪽/오른쪽 방향을 명확히 하기 위함)

# 2. 발사 각도(고각) 계산 (수치해석)
def find_elevation_angle(x, y, v0, g=9.81):                               # 목표까지의 수평거리 x, 높이 차이 y, 포구초속 v0를 받아서 발사 고각을 계산하는 함수 정의
    # 수평거리가 0에 가깝다면 의미 있는 탄도 계산이 어렵다
    if x <= 0.01:                                                          # 목표와의 수평 거리가 0.01m 이하로 너무 가까우면
        # 거의 같은 위치: 그냥 수평 0도로 처리하거나, 상황에 맞게 None 리턴
        return 0.0 if abs(y) < 0.5 else None                               # 높이차도 거의 없으면 그냥 0도(수평) 반환, 아니면 "계산 불가" 의미로 None 반환

    v2 = v0 * v0                                                           # v0^2 (속도의 제곱)을 미리 계산해서 변수에 저장 (계산 줄이기 위함)
    gx = g * x                                                             # g * x 도 미리 계산해서 저장 (수식 간단히 하기 위함)

    # y = x tanθ - g x^2 / (2 v0^2 cos^2θ)
    # 표준 해석해:
    # tanθ = (v0^2 ± sqrt(v0^4 - g(gx^2 + 2 y v0^2))) / (g x)
    disc = v2 * v2 - g * (g * x * x + 2.0 * y * v2)                        # 판별식(루트 안의 값)을 계산, 값이 음수면 실수 해가 없음

    # 판별식 < 0 이면 실수 해 없음 → 이 속도/거리/고저차로는 도달 불가
    if disc < 0:                                                           # 만약 판별식이 0보다 작으면
        return None                                                        # 실수로 된 발사각이 없으므로 None 반환 (이 속도로는 못 맞춘다는 뜻)

    sqrt_disc = math.sqrt(disc)                                            # 판별식의 제곱근을 계산해서 변수에 저장

    tan1 = (v2 + sqrt_disc) / gx                                          # 첫 번째 해의 tanθ 값을 계산
    tan2 = (v2 - sqrt_disc) / gx                                          # 두 번째 해의 tanθ 값을 계산

    theta1 = math.degrees(math.atan(tan1))                                 # 첫 번째 tanθ 를 각도(도 단위)로 변환
    theta2 = math.degrees(math.atan(tan2))                                 # 두 번째 tanθ 를 각도(도 단위)로 변환

    candidates = []                                                        # 사용 가능한 후보 각도들을 담을 리스트 생성

    # 숫자/NaN 체크 + 물리적으로 말이 되는 범위 제한(-89 ~ 89)
    for th in (theta1, theta2):                                            # 두 개의 각도(theta1, theta2)를 하나씩 th 라는 이름으로 반복
        if not math.isnan(th) and -89.0 < th < 89.0:                       # 각도가 NaN(숫자가 아님)이 아니고, -89도와 89도 사이라면
            candidates.append(th)                                          # 정상적인 후보 각도로 보고 candidates 리스트에 추가

    if not candidates:                                                     # 후보 각도가 하나도 없다면
        return None                                                        # 발사각을 찾을 수 없으므로 None 반환

    # 두 해가 있으면 "절대값이 작은" (더 직사에 가까운) 해를 선택
    best = min(candidates, key=lambda a: abs(a))                           # 후보들 중에서 |각도|가 가장 작은 것(더 직선에 가까운 궤도)을 선택

    return best                                                            # 선택된 발사 고각(도 단위)을 반환

def calculate_rf(elevation_angle, ally_turret_angle_y,                     # 발사 고각과 현재 포탑 수직각을 비교해서 R/F 명령과 강도를 계산하는 함수 정의
                 max_angle=10.0, dead_zone=0.1, min_weight=0.1, 
                 max_weight=1.0):
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
    """                                                                    # 위는 함수 사용법 설명용 긴 주석

    # 각도 차이 계산 (목표 - 현재)
    angle_diff = elevation_angle - ally_turret_angle_y                     # 목표 발사각에서 현재 포탑 수직각을 뺀 값 = 얼마나 더 올리거나 내려야 하는지
    diff = abs(angle_diff)                                                 # 각도 차이의 절대값 (양수로 만든 값, 차이 크기만 필요할 때 사용)

    # weight 계산 (angle_to_weight 로직 통합)
    if diff < dead_zone:                                                   # 각도 차이가 dead_zone(0.1도)보다 작으면
        # 목표 각도와의 차이가 dead_zone보다 작을 경우, 0을 반환, 회전 멈춤
        weight = 0.0                                                       # 너무 잘 맞춰져 있으니 더 이상 움직이지 않도록 weight = 0
    elif diff >= max_angle:                                                # 각도 차이가 max_angle(10도) 이상이면
        # 목표 각도와의 차이가 최대 max_angle보다 클 경우, 무조건 최대 파워로 회전
        weight = max_weight                                                # 최대 파워로 빨리 맞추기 위해 weight = max_weight(1.0)
    else:                                                                  # dead_zone과 max_angle 사이면
        # dead_zone ~ max_angle 사이를 min_weight ~ max_weight로 선형 매핑
        t = (diff - dead_zone) / (max_angle - dead_zone)                   # 각도차를 0~1 사이의 비율로 환산
        weight = min_weight + (max_weight - min_weight) * t                # 그 비율에 따라 min_weight~max_weight 사이 값으로 보간해서 weight 설정

    # weight가 0이면 정지
    if weight == 0.0:                                                      # 계산 결과 weight가 0이면
        return "", 0.0                                                     # 명령은 공백(멈춤), 강도는 0 반환

    # 양수면 R (상승), 음수면 F (하강)
    if angle_diff > 0:                                                     # 목표각이 현재각보다 크면(더 위로 올려야 하면)
        return "R", weight                                                 # 포신을 올리는 "R" 명령과 weight 반환
    else:                                                                  # 목표각이 더 작으면(내려야 하면)
        return "F", weight                                                 # 포신을 내리는 "F" 명령과 weight 반환

def find_new_fire_point(ally_pos, ibsm_target, corrected_body_y,          # 지금 위치에서 사격이 안될 때, 적 주변 원 위의 "새로운 사격 위치"를 찾는 함수 정의
                        muzzle_velocity=61, G=9.81):
    """
    적을 중심으로 한 원(반지름 30m) 위에서 현재 아군 전차 위치와 가장 가까운 점을 찾아 반환
    
    원의 방정식: (x - center_x)^2 + (z - center_z)^2 = radius^2
    현재 위치에서 원의 중심으로 향하는 방향벡터를 구하고, 
    원 위의 가장 가까운 점 = 중심 - 방향벡터 * 반지름
    """                                                                    # 어떤 원 위의 점을 찾는지에 대한 설명
    # 적 위치를 원의 중심으로 설정
    center_x = ibsm_target['x']                                            # 적의 x좌표를 원의 중심 x로 사용
    center_z = ibsm_target['z']                                            # 적의 z좌표를 원의 중심 z로 사용
    radius = 80.0  # 원의 반지름 (100m)                                    # 적을 중심으로 반지름 80m짜리 원 위에 우리가 설 위치를 정함

    # 현재 아군 위치에서 적(원의 중심)까지의 벡터
    dx = center_x - ally_pos['x']                                          # 적 중심 - 아군 x = 아군에서 적으로 향하는 x방향 거리
    dz = center_z - ally_pos['z']                                          # 적 중심 - 아군 z = 아군에서 적으로 향하는 z방향 거리
    distance_to_center = math.sqrt(dx**2 + dz**2)                          # 피타고라스 공식으로 아군~적 중심까지의 2D 수평 거리 계산

    write_log(f"적과의 2D 수평 거리: {distance_to_center:.2f} m")         # 로그에 적과의 수평 거리를 기록
    write_log(f"적 중심 반지름 {radius}m 원 위의 가장 가까운 점 계산")     # "원 위의 가장 가까운 점"을 계산 중임을 로그로 남김

    if distance_to_center > 0:                                             # 적과의 거리가 0보다 크면 (같은 위치가 아니라면)
        # 중심으로 향하는 단위 벡터
        unit_x = dx / distance_to_center                                   # 아군→적 방향의 x성분을 1m 길이 기준으로 만든 값
        unit_z = dz / distance_to_center                                   # 아군→적 방향의 z성분을 1m 길이 기준으로 만든 값

        # 원 위의 가장 가까운 점 = 중심 - (단위벡터 * 반지름)
        # 즉, 아군에서 적 방향으로 가되 적으로부터 반지름만큼 떨어진 지점
        move_x = center_x - unit_x * radius                                # 적 중심에서 반지름만큼 뒤로 뺀 x좌표 = 원 위의 x
        move_y = 0.0                                                       # y(고도)는 일단 0으로 둠 (필요하면 따로 고도맵에서 보정 가능)
        move_z = center_z - unit_z * radius                                # 적 중심에서 반지름만큼 뒤로 뺀 z좌표 = 원 위의 z

        # 계산된 점이 실제로 원 위에 있는지 검증 (디버깅용)
        verify_distance = math.sqrt((move_x - center_x)**2 + (move_z - center_z)**2)  # 우리가 계산한 점이 중심에서 얼마나 떨어졌는지 다시 계산
        write_log(f"원 위의 점까지 중심거리 검증: {verify_distance:.2f}m (목표: {radius}m)")  # 목표 반지름과 잘 맞는지 로그에 출력

        write_log(f"추천 이동 좌표 (적 중심 원 테두리):")                   # "추천 이동 좌표"라는 설명 로그
        write_log(f"이동 좌표: x={move_x:.2f}, y={move_y:.2f}, z={move_z:.2f}")  # 실제 이동할 좌표를 로그에 출력

        return {"x": move_x, "y": move_y, "z": move_z}                     # 추천 이동 좌표를 딕셔너리 형태로 반환
    else:                                                                  # distance_to_center가 0이면 (적과 완전히 같은 위치라면)
        write_log("적과 같은 위치에 있습니다.")                            # 적과 같은 위치라는 로그를 남기고
        return None                                                        # 이동 좌표는 의미 없으니 None 반환

# 0~360 도(또는 그 이상)로 들어오는 각도를 -180 ~ +180도로 정규화하는 매서드
def normalize_angle_deg_180(angle: float) -> float:                        # 0~360 등으로 들어오는 각을 -180~+180 범위로 바꾸는 함수 정의
    return (angle + 180.0) % 360.0 - 180.0                                 # angle에 180을 더해서 0~360으로 만든 뒤, 다시 -180~+180으로 되돌리는 수식

# 맵 종류에 맞는 Altatude Map csv 파일을 읽어와서 판다스 데이터프레임에 저장, 그리고 넘파이 2D그리드화(최초 1회만)
def check_maptype(maptype: int):                                           # maptype(맵 종류 번호)을 받아서 해당 고도맵을 로딩하는 함수 정의
    # 맵 종류에 따라 해당하는 지형 고도(CSV) 파일을 로드하여 메모리(Numpy Grid)에 캐싱.
    # 이미 로드된 맵이라면 다시 읽지 않아 성능을 최적화함.
    global altitude_df, altitude_grid, altitude_grid_shape                 # 함수 안에서도 전역 변수 altitude_df, altitude_grid, altitude_grid_shape 를 사용하겠다고 선언

    # 이미 같은 맵이 로드되어 있다면 패스
    if getattr(check_maptype, "_loaded_mt", None) == maptype and altitude_df is not None:  # 이전에 로딩했던 maptype과 같고, altitude_df도 비어있지 않다면
        return  # 이전과 같은 맵이라면, 맵 정보 재로딩을 하지 않음.             # 이미 로딩된 맵이므로 다시 읽지 않고 그냥 함수 종료

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))                  # 현재 파이썬 파일이 있는 폴더 경로를 BASE_DIR에 저장
    altitude_map_csv_path = os.path.join(BASE_DIR, "map_csvs")             # BASE_DIR 아래의 "map_csvs" 폴더를 합쳐서 CSV들이 있는 폴더 경로를 만듦

    # 맵 ID별 파일명 매핑
    csv_file_names = {                                                     # 맵 타입 번호에 따라 어떤 CSV 파일을 쓸지 사전으로 매핑
        0: "00_forest_and_river_300x300.csv",                              # map_type 0 → 숲과 강 맵
        1: "01_country_road_300x300.csv",                                  # map_type 1 → 시골길 맵
        2: "02_wildness_dry_300x300.csv",                                  # map_type 2 → 황무지 맵
        3: "03_simple_flat_300x300.csv",                                   # map_type 3 → 단순 평지 맵
    }

    if maptype not in csv_file_names:                                      # 들어온 maptype이 위 사전에 없다면
        raise ValueError(f"Invalid map type: {maptype}")                   # 잘못된 맵 타입이라고 에러를 발생시킴

    csv_path = os.path.join(altitude_map_csv_path, csv_file_names[maptype])# 선택된 맵 타입에 해당하는 CSV 파일의 전체 경로를 만든다

    altitude_df = pd.read_csv(csv_path)                                    # pandas를 이용해 해당 CSV 파일을 읽어서 데이터프레임에 저장

    x_arr = altitude_df["x"].to_numpy(dtype=int)                           # 데이터프레임의 x 컬럼을 정수형 numpy 배열로 변환
    y_arr = altitude_df["y"].to_numpy(dtype=float)                         # 데이터프레임의 y(고도) 컬럼을 실수형 numpy 배열로 변환
    z_arr = altitude_df["z"].to_numpy(dtype=int)                           # 데이터프레임의 z 컬럼을 정수형 numpy 배열로 변환
    max_x = x_arr.max()                                                    # x의 최대값(지도의 가로 크기 - 1)을 구함
    max_z = z_arr.max()                                                    # z의 최대값(지도의 세로 크기 - 1)을 구함
    grid = np.zeros((max_z + 1, max_x + 1), dtype=float)                   # (세로크기, 가로크기) 만큼 0.0으로 채워진 2D 배열을 만듦
    grid[z_arr, x_arr] = y_arr                                             # 각 (z, x) 위치에 해당하는 고도값(y)을 채워 넣음
    altitude_grid = grid                                                   # 만들어진 2D 배열을 전역변수 altitude_grid로 저장
    altitude_grid_shape = grid.shape                                       # grid의 크기(세로, 가로)를 altitude_grid_shape에 저장
    check_maptype._loaded_mt = maptype                                     # 현재 로딩한 맵 타입을 함수 속성으로 기록해 두어, 다음에 비교할 수 있게 함

# 고도맵을 바탕으로 포탄의 포물선을 미리 대조해서, 쏴봤자 언덕에 막히는걸 판단하게 하고 안쏘게 하는 매서드
def check_trajectory_collision(elevation_angle : float,                    # 발사 고각, 아군 위치, 적 위치를 받아서 궤도가 지형과 부딪히는지 확인하는 함수 정의
                               ally_body_pos : dict, 
                               ibsm_target : dict) -> bool:
    # True : 포탄이 지형에 안 걸리고 목표로 날아갈 수 있음, False : 포탄이 중간에 지형에 걸림.
    global altitude_grid, altitude_grid_shape                              # 전역으로 저장해 둔 고도 그리드와 그 크기를 사용하겠다는 선언

    # 맵 고도값 그리드가 없을 경우, 지형을 0 높이 평지로 가정
    if altitude_grid is None:                                              # altitude_grid가 아직 준비되지 않았다면
        return True                                                        # 지형이 없다고 보고, 막히는 것이 없다고 가정해서 True 반환

    G = 9.81                                                               # 중력 가속도(9.81m/s^2)를 상수로 저장
    step = 1.0                                                             # 탄도 궤적을 따라갈 때, 1m 간격으로 점을 찍어서 검사
    muzzle_clearance = 5.0                                                 # 포구에서 5m 정도는 그냥 지나간다고 보고, 그 이후부터 검사
    target_ignore = 3.0                                                    # 목표 바로 근처 3m 정도는 충돌 검사에서 제외 (목표 차량 모델 때문에)
    clearance = 0.5                                                        # 포탄 궤적과 지형 사이 최소 여유 높이 0.5m를 요구
    muzzle_velocity = 61.0                                                 # 포구초속 61m/s를 상수로 사용

    # 수평 백터/거리 확인
    dx = ibsm_target["x"] - ally_body_pos["x"]                             # 적과 아군의 x좌표 차이
    dz = ibsm_target["z"] - ally_body_pos["z"]                             # 적과 아군의 z좌표 차이
    horizontal_distance = math.sqrt(dx*dx + dz*dz)                         # 피타고라스로 두 점 사이의 수평 거리 계산
    if horizontal_distance <= 0.1:                                         # 수평거리 0.1m 이하이면 사실상 같은 위치
        # 적과 나 사이의 거리가 0.1 이하(거의 같은거리)면 계산할 필요 없으니 바로 True
        return True                                                        # 충돌 검사 의미가 거의 없으므로 그냥 True 반환

    ux = dx / horizontal_distance                                          # 아군→적 방향의 단위벡터 x 성분
    uz = dz / horizontal_distance                                          # 아군→적 방향의 단위벡터 z 성분

    # 각도와 탄속 계산
    theta = math.radians(elevation_angle)                                  # 발사 고각(도)를 라디안 값으로 변환
    cos2 = math.cos(theta)**2                                              # cos(θ)^2 값을 미리 계산해서 저장
    tan = math.tan(theta)                                                  # tan(θ) 값도 미리 계산해서 저장

    max_z, max_x = altitude_grid_shape                                     # 고도 그리드의 세로 크기(max_z), 가로 크기(max_x)를 가져옴

    # s를 따라가며 궤적 vs 지형 비교
    s = muzzle_clearance                                                   # s는 포구에서부터의 수평 거리, 처음에는 muzzle_clearance(5m)에서 시작
    end = max(0.0, horizontal_distance - target_ignore)                    # 검사 끝 지점은 목표까지 거리에서 target_ignore(3m)를 뺀 지점

    while s < end:                                                         # s가 end보다 작을 동안 1m씩 늘려가며 반복
        # 월드 좌표
        x_world = ally_body_pos["x"] + ux * s                              # 포구 위치에서 s만큼 단위벡터 방향으로 이동한 x좌표
        z_world = ally_body_pos["z"] + uz * s                              # 포구 위치에서 s만큼 단위벡터 방향으로 이동한 z좌표

        # 궤적 y (포신 높이 기준)
        y_traj = (ally_body_pos["y"]                                       # 포구의 기본 높이에서 시작해서
                  + s * tan                                                # s만큼 전진하며 고각에 따른 상승량을 더하고
                  - (G * s**2) / (2 * muzzle_velocity**2 * cos2))          # 포물선 운동 공식에 따라 중력 때문에 떨어지는 양을 빼줌

        # 지형 고도
        xi = int(math.floor(x_world))                                      # x_world를 내림해서 그리드 셀의 x 인덱스로 사용
        zi = int(math.floor(z_world))                                      # z_world를 내림해서 그리드 셀의 z 인덱스로 사용

        # 범위 밖이면 지형을 0으로 가정 (맵 밖)
        if xi < 0 or zi < 0 or xi + 1 >= max_x or zi + 1 >= max_z:         # 만약 이 인덱스 주변이 고도 그리드 범위를 벗어나면
            y_ground = 0.0                                                 # 맵 밖을 0m 높이 평지라고 가정
        else:                                                              # 그리드 범위 안에 있을 경우
            # 주변 4개 셀 높이
            Q11 = altitude_grid[zi,     xi    ]                            # 왼쪽 위 셀의 고도값
            Q21 = altitude_grid[zi,     xi + 1]                            # 오른쪽 위 셀의 고도값
            Q12 = altitude_grid[zi + 1, xi    ]                            # 왼쪽 아래 셀의 고도값
            Q22 = altitude_grid[zi + 1, xi + 1]                            # 오른쪽 아래 셀의 고도값

            # x값과 z값의 내부 비율 (0 ~ 1)
            dx_local = x_world - xi                                        # 셀 왼쪽에서부터의 x 위치 (0~1 사이 실수)
            dz_local = z_world - zi                                        # 셀 위쪽에서부터의 z 위치 (0~1 사이 실수)

            # 쌍선형 보간
            y_ground = (                                                   # 네 개의 셀 고도값을 이용해 현재 위치의 지형 높이를 부드럽게 계산
                Q11 * (1 - dx_local) * (1 - dz_local) +                    # 왼위 고도 * 그 위치에 대한 가중치
                Q21 * dx_local       * (1 - dz_local) +                    # 오른위 고도 * 그 위치에 대한 가중치
                Q12 * (1 - dx_local) * dz_local       +                    # 왼아래 고도 * 그 위치에 대한 가중치
                Q22 * dx_local       * dz_local                            # 오른아래 고도 * 그 위치에 대한 가중치
            )

        # 4. 충돌 판정
        if y_traj < y_ground + clearance:                                  # 포탄 궤적 높이가 지형 높이 + 여유높이보다 낮아지는 순간
            return False  # 언덕/지형에 걸림                                 # 언덕에 부딪힌 것으로 보고 False 반환

        s += step                                                          # 아직 안 부딪혔다면 s를 1m 증가시키고 다음 위치로 이동

    return True  # 끝까지 충돌 없음                                        # while 문을 전부 돌 동안 한 번도 걸리지 않았다면 True 반환 (중간에 안 막힘)

# 적과 나의 거리에 따라, 피치 허용오차를 다르게 (멀리 있을수록 뻑뻑하게, 가까이 있을수록 관대하게) 하는 매서드
def compute_pitch_tolerance_deg(distance_m: float) -> float:               # 수평 거리(m)를 받아 그에 따른 고각 허용 오차(도)를 계산하는 함수 정의
    #수평 거리와 '허용 높이 오차(m)'를 기반으로 허용 수직각 오차(도)를 계산.
    #가까운 거리에서는 더 느슨, 멀어질수록 조금 더 빡빡.

    d = max(distance_m, 0.0)  # 음수 방어

    # 1) 근거리: 매우 관대하게
    if d <= 30.0:
        return 3.0  # 근접전은 ±3도까지 허용

    # 2) 원거리: 엄격하게
    if d >= 150.0:
        return 1.0  # 장거리 사격은 ±1.0도 이내로만

    # 3) 중간 거리: 30m ~ 150m 사이를 선형 보간
    #   d = 30  → 3.0도
    #   d = 150 → 0.5도
    t = (d - 30.0) / (150.0 - 30.0)      # 0 ~ 1
    tolerance = 3.0 + (1.0 - 3.0) * t    # 3.0 → 1.0로 줄어듦

    return tolerance

# 사격 시각화를 위한 사격 기록 저장 매서드
def shooting_record(map_type, ally_body_pos, ibsm_target, elevation_angle):
    """
    사격이 실제로 이루어졌을 때 호출되는 기록 함수.

    - shooting_record_YYYYMMDD_HHMMSS.txt 파일을 생성하고,
      그 안에 map_type / 아군 위치 / 적 위치 / 발사 고각을
      텍스트 로그 형식(key=value)으로 기록한다.
    """
    try:
        # 안전한 형 변환
        mt = int(map_type)

        ally_x = float(ally_body_pos.get("x", 0.0))
        ally_y = float(ally_body_pos.get("y", 0.0))
        ally_z = float(ally_body_pos.get("z", 0.0))

        tgt_x = float(ibsm_target.get("x", 0.0))
        tgt_y = float(ibsm_target.get("y", 0.0))
        tgt_z = float(ibsm_target.get("z", 0.0))

        elev = float(elevation_angle) if elevation_angle is not None else 0.0

        # 타임스탬프 & 파일명
        now = datetime.now()
        ts_str = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 밀리초 3자리
        fname = "shooting_record_" + now.strftime("%Y%m%d_%H%M%S") + ".txt"

        # 텍스트 로그 작성
        with open(fname, "w", encoding="utf-8") as f:
            f.write(f"timestamp={ts_str}\n")
            f.write(f"map_type={mt}\n")
            f.write("\n")
            f.write(f"ally_x={ally_x}\n")
            f.write(f"ally_y={ally_y}\n")
            f.write(f"ally_z={ally_z}\n")
            f.write("\n")
            f.write(f"target_x={tgt_x}\n")
            f.write(f"target_y={tgt_y}\n")
            f.write(f"target_z={tgt_z}\n")
            f.write("\n")
            f.write(f"elevation_angle_deg={elev}\n")

        write_log(f"shooting_record: 사격 기록 파일 저장 완료 -> {fname}")

    except Exception as e:
        write_log(f"shooting_record 실행 중 오류: {e}")

# FCS 기능 메인
def fcs_function(request_data):  # IBSM에서 들어온 request_data를 받아, FCS 전체 로직을 실행하는 메인 함수 정의
    global rf_command, rf_weight, fire_command, fire_target, new_fire_point, pitch_stuck_start_time, enemy_in_range

    # 전역 변수 초기화 (매 요청마다 초기화)
    rf_command = ""
    rf_weight = 0.0
    fire_command = False
    fire_target = None
    new_fire_point = None
    enemy_in_range = False

    # requset_data 파싱
    time_val        = request_data.get("time", 0.0)
    ally_body_pos   = request_data.get("ally_body_pos", {})
    ally_body_angle = request_data.get("ally_body_angle", {})
    ally_speed      = request_data.get("ally_speed", 0.0)
    ally_turret_angle = request_data.get("ally_turret_angle", {})
    ibsm_target     = request_data.get("ibsm_target", {})
    map_type        = request_data.get("map_type", 0)
    AD_command      = request_data.get("AD_command", "")
    AD_weight       = request_data.get("AD_weight", 0.0)
    WS_command      = request_data.get("WS_command", "")
    WS_weight       = request_data.get("WS_weight", 0.0)

    # --- 포구 월드 좌표 ---
    muzzle_pos = {
        "x": float(ally_body_pos.get("x", 0.0)),
        "y": float(ally_body_pos.get("y", 0.0)) + MUZZLE_HEIGHT_OFFSET,
        "z": float(ally_body_pos.get("z", 0.0)),
    }

    # 고도맵 로딩 (altitude_grid 준비)
    try:
        check_maptype(int(map_type))
    except Exception as e:
        write_log(f"지형 고도맵 로딩 실패: map_type={map_type}, error={e}")

    # ---------- 0. 차체 yaw 보정 (수평 방위각용) ----------
    raw_body_y = ally_body_angle.get('y', 0.0)
    corrected_body_y = correct_body_y_angle(raw_body_y)
    write_log(f"ally_body_angle['y'] 원본(yaw): {raw_body_y:.2f} → 보정됨: {corrected_body_y:.2f}")

    # ---------- 0-1. 차체 pitch / roll 보정 (로그용) ----------
    raw_body_pitch = ally_body_angle.get('x', 0.0)
    raw_body_roll  = ally_body_angle.get('z', 0.0)

    body_pitch = normalize_angle_deg_180(raw_body_pitch)
    body_roll  = normalize_angle_deg_180(raw_body_roll)

    write_log(
        f"ally_body_angle 보정: pitch 원본={raw_body_pitch:.2f}도 → {body_pitch:.2f}도, "
        f"roll 원본={raw_body_roll:.2f}도 → {body_roll:.2f}도"
    )

    # ---------- 0-2. 포탑 yaw (수평 방위각용) ----------
    turret_yaw = ally_turret_angle.get('x', 0.0)

    # ---------- 0-3. 포탑 피치: IBSM이 주는 값을 '월드 기준 포신 피치'로 가정 ----------
    turret_pitch_world = normalize_angle_deg_180(ally_turret_angle.get('y', 0.0))
    write_log(
        f"포탑 수직각(월드 기준): {turret_pitch_world:.2f}도 "
        f"(IBSM ally_turret_angle['y'] 기반)"
    )

    # 물리 상수
    G = 9.81
    muzzle_velocity = 61.0

    # ---------------- 1. 수평거리 및 고저차 계산 ----------------
    dx = ibsm_target['x'] - ally_body_pos['x']
    dz = ibsm_target['z'] - ally_body_pos['z']
    horizontal_distance = math.sqrt(dx**2 + dz**2)

    height_diff = ibsm_target['y'] - muzzle_pos['y']
    write_log(f"수평 거리: {horizontal_distance:.2f}m, 고저차(적 - 포구): {height_diff:.2f}m")

    # ---------------- 2. 발사 고각 계산 (월드 기준) ----------------
    elevation_angle = find_elevation_angle(horizontal_distance, height_diff, muzzle_velocity, G)

    elevation_world = None
    if elevation_angle is not None:
        elevation_world = elevation_angle
        enemy_in_range = True   # 탄도 해가 존재한다는 것은 이론상 사거리 안에 있다는 뜻.
        write_log(f"적 전차를 맞추기 위한 발사 고각(월드 기준): {elevation_world:.2f}도")
    else:
        enemy_in_range = False  # 탄도 해가 없다는 것은 사거리 밖이라는 뜻.
        write_log("적 전차를 맞출 수 있는 발사 고각(월드 기준)을 찾지 못했습니다.")
        # 탄도 해 자체가 없으면, 여기서 바로 새 위치 추천
        new_fire_point = find_new_fire_point(ally_body_pos, ibsm_target, corrected_body_y)
        write_log(f"새로운 사격 위치 추천 (탄도 해 없음): {new_fire_point}")
        return

    # ---------------- 3. 지형 충돌 검사 (월드 기준 발사각 사용) ----------------
    clear_terrain = check_trajectory_collision(elevation_world, muzzle_pos, ibsm_target)

    if clear_terrain is False:
        write_log("탄도 궤적이 지형에 막힙니다. 사격을 중지하고 새로운 사격 위치를 계산합니다.")
        new_fire_point = find_new_fire_point(ally_body_pos, ibsm_target, corrected_body_y)
        write_log(f"새로운 사격 위치 추천 (지형 차폐): {new_fire_point}")
        return

    # ---------------- 4. RF 제어 명령 생성 (완전 월드 기준) ----------------
    rf_command, rf_weight = calculate_rf(
        elevation_world,      # 목표: 월드 기준 발사 고각
        turret_pitch_world    # 현재: 월드 기준 포신 피치
    )
    write_log(f"RF 명령: {rf_command}, RF 강도: {rf_weight:.2f}")

    # ---------------- 5. 사격 명령 생성 (월드 기준 조준 오차로만 판단) ----------------
    # 수평 방향(azimuth) 계산
    azimuth_rad = math.atan2(dz, dx)
    azimuth_deg_math = math.degrees(azimuth_rad)
    azimuth_deg_12oclock = (90.0 - azimuth_deg_math) % 360.0

    x_angle_diff = normalize_angle_deg(azimuth_deg_12oclock - turret_yaw)

    # 수직 오차는 월드 기준
    y_angle_diff = elevation_world - turret_pitch_world

    write_log(
        f"수평 각도 오차(월드 기준): {x_angle_diff:.2f}도, "
        f"수직 각도 오차(월드 기준): {y_angle_diff:.2f}도"
    )

    YAW_TOLERANCE = 0.5
    pitch_tolerance = compute_pitch_tolerance_deg(horizontal_distance)

    # ======== [포신 피치 stuck 감지] ========
    # 허용 오차 밖인데, 계속 그 상태로 오래 있으면 "기구 한계에 걸렸다"고 판단
    if abs(y_angle_diff) > pitch_tolerance:
        # 피치를 강하게 움직이려고 시도 중인지도 같이 본다 (rf_weight는 이번 프레임 계산값)
        if rf_weight > 0.8:
            if pitch_stuck_start_time is None:
                pitch_stuck_start_time = time_val
                write_log("피치 오차가 허용 범위를 벗어남 → stuck 타이머 시작")
            else:
                stuck_duration = time_val - pitch_stuck_start_time
                if stuck_duration > 1.0:  # 1초 이상 계속 이 상태면 기구 한계로 간주
                    write_log(
                        f"피치 오차가 {stuck_duration:.2f}s 동안 줄지 않고 "
                        f"허용오차({pitch_tolerance:.2f}도)를 초과 → "
                        f"포신이 기구 한계에 도달한 것으로 판단, 새로운 사격 위치 계산"
                    )
                    new_fire_point = find_new_fire_point(ally_body_pos, ibsm_target, corrected_body_y)
                    write_log(f"새로운 사격 위치 추천(피치 stuck): {new_fire_point}")
                    # 이 프레임에서는 발사/조준 로직 중단
                    fire_command = False
                    rf_command = ""
                    rf_weight = 0.0
                    return
        else:
            # 충분히 세게 돌리려고 하지 않는다면 stuck 타이머 리셋
            if pitch_stuck_start_time is not None:
                write_log("피치 오차는 크지만, 강하게 움직이지 않고 있어 stuck 타이머 리셋")
            pitch_stuck_start_time = None
    else:
        # 허용 오차 안으로 들어왔다면 stuck 아님
        if pitch_stuck_start_time is not None:
            write_log("피치 오차가 허용 범위 안으로 들어와 stuck 타이머 리셋")
        pitch_stuck_start_time = None
    # ======== [stuck 감지 끝] ========

    if abs(x_angle_diff) < YAW_TOLERANCE and abs(y_angle_diff) < pitch_tolerance:
        fire_command = True
        fire_target = ibsm_target
        write_log("사격 조건 충족! 발사 명령 전송")
        # shooting_record(map_type, ally_body_pos, ibsm_target, elevation_world)
    else:
        fire_command = False
        write_log(
            f"조준 중... (수평: {abs(x_angle_diff):.2f}/{YAW_TOLERANCE}도, "
            f"수직: {abs(y_angle_diff):.2f}/{pitch_tolerance}도)"
        )

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
        "new_fire_point" : new_fire_point,  # 현 위치 즉시 사격 불가 시 사격 가능 지점, dict형, {"x": 15.0, "y": 25.0, "z": 0.0}
        "enemy_in_range" : enemy_in_range   # 사정 범위 내인지 여부 (탄도 가능성, 탄도 해 존재)
    }
    # debug: log flags explicitly for easier tracing
    write_log(f"FCS flags: enemy_in_range={enemy_in_range}")
    write_log(f"FCS 반환 데이터: {response_data}")

    # 호출자(IBSM)에게 결과 반환
    return jsonify(response_data)


################################ 메인매서드 ################################
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)