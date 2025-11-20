"""

스테빌라이저 + FCS 코드의 기본 뼈대

"""
############################ 필요 라이브러리 선언 ###########################
import os
from flask import Flask, request, jsonify
import math
import pandas as pd
import numpy as np
import time

############################## Flask 추가 ################################
app = Flask(__name__)

##################### IBSM에 보낼 데이터의 기본값 ##########################
qe_command = ""
qe_weight = 0
rf_command = ""
rf_weight = 0
fire_command = False
fire_target_pos = None
new_fire_point_pos = None

######################## 스태빌라이져용 전역변수 ###########################
# 물체(장애물/적) 조준용 타깃 좌표
aim_target_x = None
aim_target_y = None
aim_target_z = None

# dt 및 "자이로(각속도)" 계산용 상태
prev_time       = None
prev_turret_x   = None   # 이전 프레임 포탑 yaw
prev_turret_y   = None   # 이전 프레임 포탑 pitch

# 웨이포인트 전환 완충용
wp_switch_cooldown = 0

# W 기반 기하학 미래예측용 상수
PREDICT_NOMINAL_MAX_SPEED = 25.0   
PREDICT_BASE_HORIZON      = 0.30   
PREDICT_MAX_HORIZON       = 0.80   
PREDICT_ALPHA_YAW         = 0.60   

########################### FCS용 전역변수 ###############################
altitude_df = None              # csv 파일을 데이터프레임화 시킨 것을 저장할 전역 변수
altitude_grid = None            # altitude_df를 numpy 2d grid화 시킨 것을 저장할 전역변수
altitude_grid_shape = None      # (y크기, x크기) 형태로 그리드 크기 저장할 전역변수

########################### 스태빌라이저 기능 #############################
def normalize_angle_deg(angle: float) -> float:
    """각도를 -180 ~ 180도로 정규화"""
    return (angle + 180.0) % 360.0 - 180.0

class TurretYawStabilizer:
    """
    [수정됨] P + Gyro Damping + Feed-Forward 제어기
    - I(적분) 제거: 반응성 향상, 오버슈트 제거
    - Gyro Damping: 외부 충격(지형)에 대한 즉각적인 저항
    """
    def __init__(self):
        # dt & gyro 계산용 상태
        self.prev_time     = None
        self.prev_turret_x = None
        self.prev_turret_y = None

        # [삭제됨] 적분(I) 관련 변수들 (yaw_int, limits 등) 제거

        # 파라미터 (튜닝포인트)
        self.Kp_yaw       = 0.045   # P게인: 목표를 쫓아가는 힘
        self.Kd_yaw_gyro  = 0.015   # D게인: 흔들림을 잡아주는 힘 (자이로 감쇠)

        self.YAW_DEADBAND   = 0.5
        self.GYRO_DEADBAND  = 1.0
        self.AD_DEADBAND    = 0.05
        self.MAX_QE         = 1.0
        self.MIN_QE_OUTPUT  = 0.02

        # [추가] 미래 예측 튀는 것 방지용 상수
        self.MAX_GEOM_DELTA = 12.0

    # ------------------------------------------------------------------
    # 시간 / 자이로 계산
    # ------------------------------------------------------------------
    def _compute_dt_and_gyro(self, time_val, turret_x, turret_y):
        # 기본 dt (fallback)
        dt = 0.016

        # dt 계산
        if self.prev_time is None:
            self.prev_time = time_val
        else:
            dt_raw = time_val - self.prev_time
            if dt_raw > 0:
                dt = dt_raw
            self.prev_time = time_val

        # 각속도 계산
        if self.prev_turret_x is None or self.prev_turret_y is None:
            gyro_yaw_rate = 0.0
        else:
            dyaw = normalize_angle_deg(turret_x - self.prev_turret_x)
            if dt > 0.0:
                gyro_yaw_rate = dyaw / dt
            else:
                gyro_yaw_rate = 0.0

        self.prev_turret_x = turret_x
        self.prev_turret_y = turret_y

        return dt, gyro_yaw_rate

    # ------------------------------------------------------------------
    # 메인 Yaw 제어 (QE_command / QE_weight 계산)
    # ------------------------------------------------------------------
    def update(
        self,
        *,
        time_val: float,
        player_x: float,
        player_y: float,
        player_z: float,
        player_turret_x: float,     # 포탑 yaw
        target_x: float,
        target_y: float,
        target_z: float,
        body_yaw: float,            # 차체 yaw
        body_AD_cmd: str,
        body_AD_weight: float,
        player_speed: float,
        body_WS_weight: float = 0.0 # [추가] 전진 가중치
    ):
        # dt / 자이로 계산
        dt, gyro_yaw_rate = self._compute_dt_and_gyro(time_val, player_turret_x, 0.0)

        # 1) 타겟까지의 yaw 오차 계산
        dx = target_x - player_x
        dz = target_z - player_z
        
        # atan2(dx, dz): IBSM 좌표계 기준
        target_yaw = math.degrees(math.atan2(dx, dz))
        if target_yaw < 0:
            target_yaw += 360.0

        yaw_err_now = normalize_angle_deg(target_yaw - player_turret_x)
        
        # ---------------------------------------------------------
        # [복구됨] 기하학적 미래 예측 (W Prediction)
        # ---------------------------------------------------------
        yaw_err_target = yaw_err_now
        
        # 전진 중일 때만 예측 수행
        eff_weight = body_WS_weight if body_WS_weight > 0 else (player_speed / PREDICT_NOMINAL_MAX_SPEED)
        
        if eff_weight > 0.01 and player_speed > 0.1:
            horizon = PREDICT_BASE_HORIZON + (PREDICT_MAX_HORIZON - PREDICT_BASE_HORIZON) * eff_weight
            horizon = max(0.10, min(horizon, PREDICT_MAX_HORIZON))

            forward_dist = player_speed * horizon
            heading_rad = math.radians(body_yaw)
            
            # 미래 위치
            future_x = player_x + forward_dist * math.sin(heading_rad)
            future_z = player_z + forward_dist * math.cos(heading_rad)

            # 미래 타겟 각도
            dx_f = target_x - future_x
            dz_f = target_z - future_z
            target_yaw_f = math.degrees(math.atan2(dx_f, dz_f))
            if target_yaw_f < 0: target_yaw_f += 360.0

            err_f_raw = normalize_angle_deg(target_yaw_f - player_turret_x)
            
            # 튀는 값 방지 (Outlier Filter)
            delta_f = normalize_angle_deg(err_f_raw - yaw_err_now)
            if abs(delta_f) > self.MAX_GEOM_DELTA:
                # 너무 튀면 현재값 기준 제한된 만큼만 이동
                yaw_err_target = yaw_err_now + self.MAX_GEOM_DELTA * math.copysign(1.0, delta_f)
            else:
                # 예측값과 현재값을 블렌딩 (Alpha 0.6)
                yaw_err_target = (1.0 - PREDICT_ALPHA_YAW) * yaw_err_now + PREDICT_ALPHA_YAW * err_f_raw

        # 2) Deadband Check
        if abs(yaw_err_target) < self.YAW_DEADBAND and abs(gyro_yaw_rate) < self.GYRO_DEADBAND:
            return "", 0.0

        # 3) Feed-Forward (AD 보상)
        u_ff = 0.0
        K_FF_AD = 0.4
        if body_AD_cmd == "D":
            u_ff = -K_FF_AD * float(body_AD_weight)
        elif body_AD_cmd == "A":
            u_ff = +K_FF_AD * float(body_AD_weight)

        # 4) P-Gyro Control Calculation (I 제거됨)
        # P 제어: 목표 지향
        P = self.Kp_yaw * yaw_err_target
        
        # D 제어: 자이로(속도) 감쇠 (Active Damping)
        # 오차의 미분이 아니라, 현재 회전 속도를 반대로 억제함
        D = -self.Kd_yaw_gyro * gyro_yaw_rate 

        # 최종 합산
        u = P + D + u_ff

        # 5) 출력 클램프
        if u > self.MAX_QE:
            u = self.MAX_QE
        elif u < -self.MAX_QE:
            u = -self.MAX_QE

        # 최소 출력 확인
        if abs(u) < self.MIN_QE_OUTPUT:
            return "", 0.0

        # 6) Q / E 결정 (방향이 반대라면 여기서 Q, E를 서로 바꾸세요)
        if u > 0:
            return "E", u
        else:
            return "Q", -u

# 전역 스태빌라이저 인스턴스
yaw_stabilizer = TurretYawStabilizer()

def turret_control(request_data: dict):
    """
    IBSM → FCS 래퍼 함수
    """
    global qe_command, qe_weight, aim_target_x, aim_target_y, aim_target_z

    # 1) 데이터 파싱
    time_val = float(request_data.get("time", 0.0))

    ally_pos   = request_data.get("ally_body_pos", {}) or {}
    ally_ang   = request_data.get("ally_body_angle", {}) or {}
    turret_ang = request_data.get("ally_turret_angle", {}) or {}
    target_pos = request_data.get("ibsm_target_pos", {}) or {}

    player_x = float(ally_pos.get("x", 0.0))
    player_y = float(ally_pos.get("y", 0.0))
    player_z = float(ally_pos.get("z", 0.0))

    player_turret_x = float(turret_ang.get("x", 0.0))   # yaw
    
    body_yaw = float(ally_ang.get("y", 0.0))            # 차체 yaw

    player_speed = float(request_data.get("ally_speed", 0.0))

    # AD/WS 명령 – IBSM에서 내려준 값 사용
    body_AD_cmd    = request_data.get("AD_command", "")
    body_AD_weight = float(request_data.get("AD_weight", 0.0))
    body_WS_weight = float(request_data.get("WS_weight", 0.0)) # WS 추가

    # 2) 타깃 선택
    if "x" in target_pos and "y" in target_pos and "z" in target_pos:
        target_x = float(target_pos.get("x", 0.0))
        target_y = float(target_pos.get("y", 0.0))
        target_z = float(target_pos.get("z", 0.0))
        aim_target_x, aim_target_y, aim_target_z = target_x, target_y, target_z

    elif aim_target_x is not None:
        target_x, target_y, target_z = aim_target_x, aim_target_y, aim_target_z
    else:
        return qe_command, qe_weight

    # 3) 스태빌라이저 업데이트
    QE_cmd, QE_w = yaw_stabilizer.update(
        time_val=time_val,
        player_x=player_x,
        player_y=player_y,
        player_z=player_z,
        player_turret_x=player_turret_x,
        target_x=target_x,
        target_y=target_y,
        target_z=target_z,
        body_yaw=body_yaw,
        body_AD_cmd=body_AD_cmd,
        body_AD_weight=body_AD_weight,
        player_speed=player_speed,
        body_WS_weight=body_WS_weight # 파라미터 전달
    )

    qe_command = QE_cmd
    qe_weight  = QE_w

############################### FCS 기능 ################################
# FCS 기능에 사용할 함수들
# 맵 종류에 맞는 Altatude Map csv 파일을 읽어와서 판다스 데이터프레임에 저장, 그리고 넘파이 2D그리드화(최초 1회)
def check_maptype(maptype: int):
    global altitude_df, altitude_grid, altitude_grid_shape

    if getattr(check_maptype, "_loaded_mt", None) == maptype and altitude_df is not None:
        return  # 이전과 같은 맵이라면, 맵 정보 재로딩을 하지 않음.

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    altitude_map_csv_path = os.path.join(BASE_DIR, "map_csvs")

    csv_file_names = {
        0: "00_forest_and_river_300x300.csv",
        1: "01_country_road_300x300.csv",
        2: "02_wildness_dry_300x300.csv",
        3: "03_simple_flat_300x300.csv",
    }

    if maptype not in csv_file_names:
        raise ValueError(f"Invalid map type: {maptype}")
    
    csv_path = os.path.join(altitude_map_csv_path, csv_file_names[maptype])

    altitude_df = pd.read_csv(csv_path)
    
    x_arr = altitude_df["x"].to_numpy(dtype=int)     # 데이터프레임의 x값들을 numpy 배열로 변환
    y_arr = altitude_df["y"].to_numpy(dtype=int)     # 데이터프레임의 y값들을 numpy 배열로 변환
    z_arr = altitude_df["z"].to_numpy(dtype=float)   # 데이터프레임의 z값들을 numpy 배열로 변환
    max_x = x_arr.max()                     # x 그리드 최대값
    max_y = y_arr.max()                     # y 그리드 최대값
    grid = np.zeros((max_y + 1, max_x + 1), dtype=float)        # 고도값들을 저장할 0으로만 가득 찬 2차원 배열 준비
    grid[y_arr, x_arr] = z_arr              # 각 (y, x)에 고도값(z)들을 넣기
    altitude_grid = grid                    # 위 2차원 넘파이 배열을 전역변수화
    altitude_grid_shape = grid.shape        # 위 2차원 넘파이 배열의 크기의 전역변수화
    check_maptype._loaded_mt = maptype      # 로딩한 맵 타입을 저장, 다음 로딩에는 생략할 수 있게 

# x와 y값을 입력받아 csv로 만든 넘파이 그리드를 참고해 z값(고도)을 반환하는 매서드
def altitude_calculator(x, y):
    global altitude_grid, altitude_grid_shape

    if altitude_grid is None:
        return 0                    # 맵 고도값 그리드가 없을 경우, 0을 반환하는 예외처리
    
    xi = int(round(x))              # 매서드로 들어온 x값의 소숫점 단위 이하를 제거
    yi = int(round(y))              # 매서드로 들어온 y값의 소숫점 단위 이하를 제거
    max_y, max_x = altitude_grid_shape              # 그리드 배열의 크기 불러오기
    if 0 <= yi < max_y and 0 <= xi < max_x:         # 매서드로 들어온 x, y값이 그리드 안에 해당할 경우,
        return float(altitude_grid[yi, xi])         # 해당하는 고도값 반환
    else:
        return 0                    # 들어온 x, y값이 그리드 범위를 넘어가는 숫자일 경우 0을 반환하는 예외처리

# 고각 계산기 매서드
# 수평거리 x, 높이차 y, 포구속도 v0이 주어졌을때, 어떤 발사각 θ에서 명중하는지 찾는 함수
def find_elevation_angle(x, y, v0, gravity, prefer_low=True):
    # 수평거리 x, 높이차 y, 포구속도 v0가 주어졌을 때 탄도 해(발사각)를 반환(deg), 해가 없으면 None
    # - prefer_low=True면 |각도|가 더 작은 해를 우선 반환
    if x <= 0.0:
        return None
    # 판별식
    v2 = v0 * v0
    term = v2 * v2 - gravity * (gravity * x * x + 2.0 * y * v2)
    if term < 0.0:
        return None  # 물리적으로 닿을 수 없는 위치
    sqrt_term = math.sqrt(term)
    # tan(theta) 두 해
    t1 = (v2 + sqrt_term) / (gravity * x)
    t2 = (v2 - sqrt_term) / (gravity * x)
    candidates = []
    for t in (t1, t2):
        angle = math.atan(t)  # rad
        # 여기서 angle은 -90°~+90° 범위
        candidates.append(angle)
    if not candidates:
        return None
    if prefer_low:
        angle = min(candidates, key=lambda a: abs(a))
    else:
        angle = max(candidates, key=lambda a: abs(a))
    return math.degrees(angle)

# 0~1 사이의 최적의 weight 값을 계산해 반환하는 매서드 (rf_weight 계산용)
def angle_to_weight(angle_diff_deg, max_angle=30.0, min_weight=0.0, max_weight=1.0, dead_zone=0.5):
    # angle_diff_deg: 목표 각도와의 차이
    # max_angle: 이 각도 이상 차이 나면 항상 max_weight
    # dead_zone: 이 각도보다 차이가 작으면 weight=0 (멈춤)
    diff = abs(angle_diff_deg)      # 목표 각도와의 차이를 절댓값만 남기는 가공

    if diff < dead_zone:            # 목표 각도와의 차이가 dead_zone보다 작을 경우, 0을 반환, 회전 멈춤. 미세한 각도차이는 보정 안하기
        return 0.0
    if diff >= max_angle:           # 목표 각도외의 차이가 최대 max_angle보다 클 경우, 무조건 최대 파워로 회전
        return max_weight           # 기본값 기준 1.0 반환

    # 위 두가지 경우에서 걸러지지 않은 나머지 상황
    t = (diff - dead_zone) / (max_angle - dead_zone)
    return min_weight + (max_weight - min_weight) * t   # dead_zone ~ max_angle 사이를 0~1로 선형 매핑해 반환  

# 각도를 -180 ~ 180도로 정규화 (FCS용)
def normalize_angle_deg_for_fcs(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


# FCS 기능 메인
def fcs_function(request_data : dict):
    global rf_command, rf_weight, fire_command, fire_target_pos, new_fire_point_pos

    # 매 프레임 초기화 (stale 값 방지)
    rf_command = ""
    rf_weight  = 0.0
    fire_command = False
    new_fire_point_pos = None
    fire_target_pos = None
    
    # IBSM으로 부터 읽어온 값들을 계산에 쓰기 위한 변수로 저장(payload 누락에 대한 예외처리, 0 추가.)
    data =  request_data

    maptype = int(data.get("map_type", 0))      # 맵 타입
    check_maptype(maptype)
    enemy_pos_x = float(data.get("ibsm_target_pos", {}).get("x", 0))    # 적 x좌표 (시뮬레이터 기준)
    enemy_pos_y = float(data.get("ibsm_target_pos", {}).get("y", 0))    # 적 y좌표 (시뮬레이터 기준, 고도)
    enemy_pos_z = float(data.get("ibsm_target_pos", {}).get("z", 0))    # 적 z좌표 (시뮬레이터 기준)
    my_pos_x = float(data.get("ally_body_pos", {}).get("x", 0))     # 내 x좌표 (시뮬레이터 기준)
    my_pos_y = float(data.get("ally_body_pos", {}).get("y", 0))     # 내 y좌표 (시뮬레이터 기준, 고도)
    my_pos_z = float(data.get("ally_body_pos", {}).get("z", 0))     # 내 z좌표 (시뮬레이터 기준)
    my_turret_x = float(data.get("ally_turret_angle", {}).get("x", 0))    # 내 포탑 수평 기울기
    my_turret_y = float(data.get("ally_turret_angle", {}).get("y", 0))    # 내 포탑 수직 기울기
    my_chassis_x = float(data.get("ally_body_angle", {}).get("x", 0))    # 내 차체 x 기울기
    my_chassis_y = float(data.get("ally_body_angle", {}).get("y", 0))    # 내 차체 y 기울기
    my_chassis_z = float(data.get("ally_body_angle", {}).get("z", 0))    # 내 차체 z 기울기
    simulator_time = float(data.get("time", 0))                     # IDMS 기준 시간
    my_speed = float(data.get("ally_speed", 0))                     # 내 차체의 속도
    enemy_alt = altitude_calculator(enemy_pos_x, enemy_pos_z)   #위 읽어온 csv altatude map을 기반으로 현재 고도를 판단
    my_alt = altitude_calculator(my_pos_x, my_pos_z)  # 위 읽어온 csv altatude map을 기반으로 현재 고도를 판단
    G = 9.81 # 중력가속도
    muzzle_velocity = 61 # 포탄의 초기속도(61m/s)
    fire_target_pos = {"x": enemy_pos_x, "y": enemy_alt, "z": enemy_pos_z}  #사격해야 할 적의 좌표
    
    print(data)  # IBSM에서 수신받은 값들 출력

    print(f'내 높이 : {my_alt}')
    print(f'적 높이 : {enemy_alt}')

    # 계산 1. 거리 및 고저차 계산
    dx = enemy_pos_x - my_pos_x
    dz = enemy_pos_z - my_pos_z
    horizontal_distance = math.hypot(dx, dz)    # 수평거리 계산
    height_diff = enemy_pos_y - my_pos_y        # 고저차

    # 계산 2. 탄도해 계산
    elevation_angle = None
    if horizontal_distance > 0.1:   # 적과 내가 거의 같은 위치이면 탄도 계산 무의미
        elevation_angle = find_elevation_angle(horizontal_distance, height_diff, muzzle_velocity, G)

    # 계산 3. 포신 상하 조절 (RF커맨드, RF가중치)
    if elevation_angle is None:         # 만약, find_elevation_angle로 탄도상 명중 가능한 각도를 못찾을 경우
        rf_command = ""
        rf_weight = 0.0
    else:                               # find_elevation_angle로 탄도상 명중 가능한 각도를 찾는데 성공했을 경우
        if elevation_angle > my_turret_y:
            rf_command = "R"
        elif elevation_angle < my_turret_y:
            rf_command = "F"
        else:
            rf_command = ""
            rf_weight = 0.0
        
        if rf_command != "":
            delta_pitch = elevation_angle - my_turret_y
            rf_weight = angle_to_weight(delta_pitch, max_angle=20.0, dead_zone=0.5)
        print(f"보낸 RF 커맨드 : {rf_command}, RF 가중치 : {rf_weight}")

    # 계산 4. 방위각 계산
    azimuth_rad = math.atan2(dz, dx)                         # 기본 atan2 각도
    azimuth_deg_math = math.degrees(azimuth_rad)             # 일반적인 수학 좌표계 기준
    azimuth_deg_12clock = (90.0 - azimuth_deg_math) % 360.0  # 시계방향 12시를 0도로 가정하고 시계방향으로 증가
    print(f"적 방위각(12시 기준, 시계방향): {azimuth_deg_12clock:.2f} deg")

    # 계산 5. 포탑 수직 각도 제한 확인
    chassis_pitch = normalize_angle_deg_for_fcs(my_chassis_x)   # 차체 각도 정규화
    turret_pitch = normalize_angle_deg_for_fcs(my_turret_y)    # 포신 피치 정규화

    elev_angle_norm = None
    if elevation_angle is not None: # 탄도해가 무사히 계산되었을 경우, 탄도해도 정규화.
        elev_angle_norm = normalize_angle_deg_for_fcs(elevation_angle)

    # 예: 차체 pitch 기준 -5 ~ +10
    turret_min_angle = chassis_pitch - 5.0   # 최저 -5도까지만 허용
    turret_max_angle = chassis_pitch + 10.0   # 최대 10도까지만 허용

    in_elev_limit = False
    if elevation_angle is not None:
        in_elev_limit = (turret_min_angle <= elev_angle_norm <= turret_max_angle)
        print(
            f"포탑 수직 제한: [{turret_min_angle:.2f}, {turret_max_angle:.2f}] "
            f"→ 필요고각 {elevation_angle:.2f} → in_elev_limit={in_elev_limit}"
        )
    
    # 계산 6. 사거리 계산 (발사각 10도 기준)
    theta_deg = 10.0
    theta_rad = math.radians(theta_deg)
    range_10deg = (muzzle_velocity ** 2) * math.sin(2.0 * theta_rad) / G    # 포물선 최대 사거리 공식: R = v² * sin(2θ) / g 사용
    print(f"발사각 10도 기준 이론 사거리: {range_10deg:.2f} m")

    # 사격 가능여부 최종 평가
    has_solution = (elevation_angle is not None)    # 탄도 해 존재 여부
    elev_ok = has_solution and in_elev_limit        # 수직 각도 제약 만족 여부
    yaw_err = normalize_angle_deg_for_fcs(azimuth_deg_12clock - my_turret_x)    # 포탑 정렬 여부
    pitch_err = 0.0
    if elev_angle_norm is not None:
        pitch_err = normalize_angle_deg_for_fcs(elev_angle_norm - turret_pitch)
    yaw_aligned   = abs(yaw_err)   < 1.0   # 1도 이내
    pitch_aligned = abs(pitch_err) < 1.0   # 1도 이내
    #speed_ok = abs(my_speed) < 5.0         # 차체 사격가능 안정성 평가 1 : 속도가 5 미만인가?
    #AD_ok = abs(AD_weight) < 0.3        # 차체 사격가능 안정성 평가 2 : AD가중치가 0.3 미만인가?
    #WS_ok = abs(WS_weight) < 0.3        # 차체 사격가능 안정성 평가 3 : WS가중치가 0.3 미만인가?

    can_fire_now = has_solution and elev_ok and yaw_aligned and pitch_aligned

    # 이동해야 할 위치 계산 후, x,y 좌표를 반환하는 계산기 매서드 (적 전차 방향으로 사정거리만큼 접근)
    def get_move_position(my_x, my_z, enemy_x, enemy_z, move_distance):
        dx = enemy_x - my_x
        dz = enemy_z - my_z
        total_distance = math.hypot(dx, dz)
        if total_distance == 0.0:                   # 내가 적 좌표와 같은 x,z에 있을 경우, 0으로 나누는것 방지용
            return my_x, my_z                       # 그냥 원래 x, z좌표 반환
        ratio = (total_distance - move_distance) / total_distance   # 전체 거리 중 필요한 거리 만큼만 적 방향으로 이동
        new_x = my_x + dx * ratio
        new_z = my_z + dz * ratio
        return new_x, new_z                         # 새로 가야할 x좌표, z좌표를 반환
    
    need_move_for_range = (horizontal_distance > range_10deg)
    need_move_for_elev = not elev_ok  # 고각 제한 밖이면 위치를 바꿀 필요가 있다고 가정

    if not can_fire_now and (need_move_for_range or need_move_for_elev):
        fire_command = False
        # 적 방향으로 range_10deg 만큼 떨어진 지점으로 접근 제안
        move_x, move_z = get_move_position(my_pos_x, my_pos_z, enemy_pos_x, enemy_pos_z, range_10deg)
        h = altitude_calculator(move_x, move_z)
        new_fire_point_pos = {
            "x": move_x,
            "y": h,
            "z": move_z
        }
        print("즉시 불가. 이동 추천 좌표:", new_fire_point_pos)
    
    else:
        fire_command = can_fire_now
        if fire_command:
            print("사격 가능 : IBSM에게 사격 허가.")
        else:
            print("기준은 만족 못 했지만, 이동 필요까지는 아님 (정렬/안정 기다리는 상태).")
    


##################### IBSM이 호출할 FCS의 엔드포인트 #######################
@app.post("/get_fcs")
def get_fcs():
    # IBSM에서 받아온 데이터를 저장
    request_data = request.get_json(force=True, silent=True) or {}
    #print("IBSM으로 부터 받은 데이터 : ", request_data)

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
        "fire_target_pos" : fire_target_pos,        # 사격 대상, dict형, {"x": 15.0, "y": 25.0, "z": 0.0}
        "new_fire_point_pos" : new_fire_point_pos   # 현 위치 즉시 사격 불가 시 사격 가능 지점, dict형, {"x": 15.0, "y": 25.0, "z": 0.0}
    }
    #print("IBSM으로 보낼 데이터 : ", response_data)

    # 호출자(IBSM)에게 결과 반환
    return jsonify(response_data)


################################ 메인매서드 ################################
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)