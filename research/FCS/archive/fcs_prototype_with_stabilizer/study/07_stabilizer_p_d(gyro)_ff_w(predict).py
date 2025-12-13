"""
[통합 시스템] 스태빌라이저 (Lag 대응형) + FCS (탄도 계산 및 이동 예측)
- Flask 서버로 동작하며 IBSM의 요청(Request)에 따라 제어 명령(Response)을 반환
"""
############################ 필요 라이브러리 선언 ###########################
import os
from flask import Flask, request, jsonify
import math
import pandas as pd
import numpy as np
import time

"""
[Turret Yaw Stabilizer]
전차 포탑의 수평 회전(Yaw)을 제어하는 클래스입니다.

[제어 방식: P + D(Gyro Damping) + FF(Feed-Forward)]
1. P (Proportional): 목표물과의 각도 차이에 비례하여 회전 (스프링 역할)
2. Gyro Damping (D): 현재 회전 속도에 저항하여 오버슈트 및 진동 억제 (댐퍼 역할)
3. FF (Feed-Forward): 차체 선회 입력(A/D) 감지 시, 반대 방향으로 즉시 보상 입력 (예측 제어)
   - I(적분) 제거: 반응성 향상 및 타깃 변경 시 헌팅(Hunting) 방지
4. Predict(예측) : 전진에 대해서 미래를 예측하여 Q/E의 weight 값을 부여
"""

############################## Flask 앱 초기화 ################################
app = Flask(__name__)

##################### IBSM에 보낼 데이터의 기본값 (초기화) ##########################
qe_command = ""      # 포탑 좌우 회전 명령 (Q/E)
qe_weight = 0        # 포탑 좌우 회전 강도
rf_command = ""      # 포신 상하 조절 명령 (R/F)
rf_weight = 0        # 포신 상하 조절 강도
fire_command = False # 발사 트리거
fire_target_pos = None # 조준하고 있는 최종 타겟 좌표
new_fire_point = None  # 사격 불가 시 이동 제안 좌표

######################## 스태빌라이져용 전역변수 ###########################
# 목표물(적) 좌표 저장용 (통신 누락 시 이전 좌표 유지)
aim_target_x = None
aim_target_y = None
aim_target_z = None

# dt(시간변화량) 및 각속도 계산을 위한 이전 프레임 상태 저장
prev_time       = None
prev_turret_x   = None   # 이전 프레임 포탑 Yaw
prev_turret_y   = None   # 이전 프레임 포탑 Pitch (현재 로직에선 Yaw 위주 사용)

# 웨이포인트 전환 시 튀는 현상 방지를 위한 쿨다운 (확장성 대비)
wp_switch_cooldown = 0

# [미래 예측 제어 상수] 전차가 이동 중일 때 조준 오차를 줄이기 위한 파라미터
PREDICT_NOMINAL_MAX_SPEED = 25.0   # 예측 로직이 최대로 동작하는 기준 속도 (km/h 혹은 m/s)
PREDICT_BASE_HORIZON      = 0.30   # 기본 예측 시간 (초) - 너무 짧으면 효과 없음
PREDICT_MAX_HORIZON       = 0.80   # 최대 예측 시간 (초) - 너무 길면 오버슈트 발생
PREDICT_ALPHA_YAW         = 0.60   # 예측값 적용 비율 (0.0: 미적용 ~ 1.0: 완전 적용)

########################### FCS용 전역변수 ###############################
altitude_df = None            # CSV 파일에서 읽은 고도 데이터를 담을 DataFrame
altitude_grid = None          # 고속 조회를 위해 DataFrame을 변환한 2D Numpy Array
altitude_grid_shape = None    # 그리드 맵의 크기 (Y, X)

########################### 스태빌라이저 기능 (포탑 수평 제어) #############################
def normalize_angle_deg(angle: float) -> float:
    """각도를 -180 ~ +180도로 정규화 (최단 회전 경로 계산용)"""
    return (angle + 180.0) % 360.0 - 180.0

class TurretYawStabilizer:
    """
    [Turret Yaw Stabilizer]
    제어 방식: P + Gyro Damping + Feed-Forward + Future Prediction
    목표: 전차의 기동(회전, 전진) 중에도 목표물을 놓치지 않고 안정적으로 조준
    """
    def __init__(self):
        # 상태 변수 초기화
        self.prev_time     = None
        self.prev_turret_x = None
        self.prev_turret_y = None

        # [제어 게인 튜닝]
        self.Kp_yaw       = 0.045   # P게인: 목표 추적 반응성 (스프링 강도)
        self.Kd_yaw_gyro  = 0.015   # D게인: 흔들림 억제 (댐퍼 강도)

        # [임계값 설정]
        self.YAW_DEADBAND   = 0.5   # 0.5도 이내 오차는 무시 (떨림 방지)
        self.GYRO_DEADBAND  = 1.0   # 회전 속도가 미미하면 정지로 간주
        self.AD_DEADBAND    = 0.05  # 조향 입력 데드밴드
        self.MAX_QE         = 1.0   # 최대 출력 제한
        self.MIN_QE_OUTPUT  = 0.02  # 최소 출력 제한

        # [미래 예측 안전장치]
        self.MAX_GEOM_DELTA = 12.0  # 예측 로직이 현재 조준각을 12도 이상 확 틀어버리지 않도록 제한

    # ------------------------------------------------------------------
    # 내부 함수: dt(시간차) 및 자이로(각속도) 계산
    # ------------------------------------------------------------------
    def _compute_dt_and_gyro(self, time_val, turret_x, turret_y):
        dt = 0.016 # 기본값 (60FPS 기준)

        # 시간 차이 계산
        if self.prev_time is None:
            self.prev_time = time_val
        else:
            dt_raw = time_val - self.prev_time
            if dt_raw > 0:
                dt = dt_raw
            self.prev_time = time_val

        # 각속도(deg/s) 계산
        if self.prev_turret_x is None or self.prev_turret_y is None:
            gyro_yaw_rate = 0.0
        else:
            dyaw = normalize_angle_deg(turret_x - self.prev_turret_x)
            if dt > 0.0:
                gyro_yaw_rate = dyaw / dt
            else:
                gyro_yaw_rate = 0.0

        # 상태 업데이트
        self.prev_turret_x = turret_x
        self.prev_turret_y = turret_y

        return dt, gyro_yaw_rate

    # ------------------------------------------------------------------
    # 메인 업데이트 함수: 최종 QE 명령 계산
    # ------------------------------------------------------------------
    def update(
        self,
        *,
        time_val: float,
        player_x: float,
        player_y: float,
        player_z: float,
        player_turret_x: float,     # 현재 포탑 Yaw
        target_x: float,
        target_y: float,
        target_z: float,
        body_yaw: float,            # 차체 Yaw
        body_AD_cmd: str,           # 차체 조향 명령 (A/D)
        body_AD_weight: float,      # 차체 조향 강도
        player_speed: float,        # 현재 속도
        body_WS_weight: float = 0.0 # 전진 가중치
    ):
        # 1. 자이로(회전속도) 계산
        dt, gyro_yaw_rate = self._compute_dt_and_gyro(time_val, player_turret_x, 0.0)

        # 2. 기본 목표 각도 계산 (현재 위치 기준)
        dx = target_x - player_x
        dz = target_z - player_z
        target_yaw = math.degrees(math.atan2(dx, dz))
        if target_yaw < 0:
            target_yaw += 360.0

        # 현재 단순 오차
        yaw_err_now = normalize_angle_deg(target_yaw - player_turret_x)
        
        # ---------------------------------------------------------
        # [미래 예측 로직] (W Prediction)
        # 내가 전진하고 있다면, 잠시 후 도달할 위치를 기준으로 조준점을 미리 수정함
        # ---------------------------------------------------------
        yaw_err_target = yaw_err_now
        
        # 전진 가중치 또는 속도 비율 계산
        eff_weight = body_WS_weight if body_WS_weight > 0 else (player_speed / PREDICT_NOMINAL_MAX_SPEED)
        
        # 일정 속도 이상일 때만 예측 수행
        if eff_weight > 0.01 and player_speed > 0.1:
            # 예측 시간(Horizon) 동적 설정: 속도가 빠를수록 더 먼 미래를 봄
            horizon = PREDICT_BASE_HORIZON + (PREDICT_MAX_HORIZON - PREDICT_BASE_HORIZON) * eff_weight
            horizon = max(0.10, min(horizon, PREDICT_MAX_HORIZON))

            forward_dist = player_speed * horizon           # 예측 이동 거리
            heading_rad = math.radians(body_yaw)            # 현재 진행 방향
            
            # 미래의 내 위치 예측
            future_x = player_x + forward_dist * math.sin(heading_rad)
            future_z = player_z + forward_dist * math.cos(heading_rad)

            # 미래 위치 기준 타겟 각도 재계산
            dx_f = target_x - future_x
            dz_f = target_z - future_z
            target_yaw_f = math.degrees(math.atan2(dx_f, dz_f))
            if target_yaw_f < 0: target_yaw_f += 360.0

            err_f_raw = normalize_angle_deg(target_yaw_f - player_turret_x)
            
            # [안전장치] 예측값이 너무 튀면(Outlier) 제한
            delta_f = normalize_angle_deg(err_f_raw - yaw_err_now)
            if abs(delta_f) > self.MAX_GEOM_DELTA:
                # 튀는 경우: 최대 허용치만큼만 반영
                yaw_err_target = yaw_err_now + self.MAX_GEOM_DELTA * math.copysign(1.0, delta_f)
            else:
                # 정상: 현재 오차와 예측 오차를 Alpha 비율로 섞음 (Smoothing)
                yaw_err_target = (1.0 - PREDICT_ALPHA_YAW) * yaw_err_now + PREDICT_ALPHA_YAW * err_f_raw

        # 3. Deadband Check (오차가 작으면 제어 중지)
        if abs(yaw_err_target) < self.YAW_DEADBAND and abs(gyro_yaw_rate) < self.GYRO_DEADBAND:
            return "", 0.0

        # 4. Feed-Forward (선회 보상)
        # 차체가 도는 방향의 반대 방향으로 힘을 미리 가함
        u_ff = 0.0
        K_FF_AD = 0.4
        if body_AD_cmd == "D":      # 우회전 시
            u_ff = -K_FF_AD * float(body_AD_weight) # 좌측으로 보상
        elif body_AD_cmd == "A":    # 좌회전 시
            u_ff = +K_FF_AD * float(body_AD_weight) # 우측으로 보상

        # 5. P-Gyro 제어 (Main Logic)
        # P: 목표(예측된 목표) 지향
        P = self.Kp_yaw * yaw_err_target
        
        # D: 자이로 댐핑 (관성 억제)
        D = -self.Kd_yaw_gyro * gyro_yaw_rate 

        # 최종 출력 합산
        u = P + D + u_ff

        # 6. 출력 제한 (Clamping)
        if u > self.MAX_QE:
            u = self.MAX_QE
        elif u < -self.MAX_QE:
            u = -self.MAX_QE

        # 최소 출력 미만 무시
        if abs(u) < self.MIN_QE_OUTPUT:
            return "", 0.0

        # 7. 명령(Q/E) 결정
        if u > 0:
            return "E", u
        else:
            return "Q", -u

# 전역 스태빌라이저 인스턴스 생성
yaw_stabilizer = TurretYawStabilizer()

def turret_control(request_data: dict):
    """ IBSM 데이터를 받아 스태빌라이저 업데이트 """
    global qe_command, qe_weight, aim_target_x, aim_target_y, aim_target_z
    
    # 데이터 파싱
    time_val = float(request_data.get("time", 0.0))
    ally_pos   = request_data.get("ally_body_pos", {}) or {}
    turret_ang = request_data.get("ally_turret_angle", {}) or {}
    ally_ang   = request_data.get("ally_body_angle", {}) or {}
    target_pos = request_data.get("ibsm_target", {}) or {}

    player_x = float(ally_pos.get("x", 0.0))
    player_y = float(ally_pos.get("y", 0.0))
    player_z = float(ally_pos.get("z", 0.0))
    player_turret_x = float(turret_ang.get("x", 0.0))
    body_yaw = float(ally_ang.get("y", 0.0))
    player_speed = float(request_data.get("ally_speed", 0.0))

    body_AD_cmd    = request_data.get("AD_command", "")
    body_AD_weight = float(request_data.get("AD_weight", 0.0))
    body_WS_weight = float(request_data.get("WS_weight", 0.0))

    # 타깃 업데이트
    if "x" in target_pos and "y" in target_pos and "z" in target_pos:
        target_x = float(target_pos.get("x", 0.0))
        target_y = float(target_pos.get("y", 0.0))
        target_z = float(target_pos.get("z", 0.0))
        aim_target_x, aim_target_y, aim_target_z = target_x, target_y, target_z
    elif aim_target_x is not None:
        target_x, target_y, target_z = aim_target_x, aim_target_y, aim_target_z
    else:
        return qe_command, qe_weight

    # 스태빌라이저 계산 수행
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
        body_WS_weight=body_WS_weight
    )

    qe_command = QE_cmd
    qe_weight  = QE_w

############################### FCS 기능 (화력 제어 시스템) ################################

# 1. 맵 데이터 로딩 (CSV -> Numpy Grid)
def check_maptype(maptype: int):
    """
    맵 ID에 해당하는 CSV 고도 데이터를 로드하여 전역 변수(altitude_grid)에 저장
    최초 1회 혹은 맵이 바뀔 때만 실행됨 (성능 최적화)
    """
    global altitude_df, altitude_grid, altitude_grid_shape

    # 이미 로드된 맵이면 생략
    if getattr(check_maptype, "_loaded_mt", None) == maptype and altitude_df is not None:
        return 

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    altitude_map_csv_path = os.path.join(BASE_DIR, "map_csvs")

    # 맵 ID별 파일명 매핑
    csv_file_names = {
        0: "00_forest_and_river_300x300.csv",
        1: "01_country_road_300x300.csv",
        2: "02_wildness_dry_300x300.csv",
        3: "03_simple_flat_300x300.csv",
    }

    if maptype not in csv_file_names:
        raise ValueError(f"Invalid map type: {maptype}")
    
    csv_path = os.path.join(altitude_map_csv_path, csv_file_names[maptype])

    # Pandas로 CSV 읽기 -> Numpy 변환 (속도 향상)
    altitude_df = pd.read_csv(csv_path)
    x_arr = altitude_df["x"].to_numpy(dtype=int)
    y_arr = altitude_df["y"].to_numpy(dtype=int)
    z_arr = altitude_df["z"].to_numpy(dtype=float)
    
    max_x = x_arr.max()
    max_y = y_arr.max()
    
    # 2D 그리드 생성 및 데이터 채우기
    grid = np.zeros((max_y + 1, max_x + 1), dtype=float)
    grid[y_arr, x_arr] = z_arr
    
    altitude_grid = grid
    altitude_grid_shape = grid.shape
    check_maptype._loaded_mt = maptype

# 2. 고도 조회 (Grid Lookup)
def altitude_calculator(x, y):
    """ (x, y) 좌표의 지형 높이(z값)를 반환 """
    global altitude_grid, altitude_grid_shape

    if altitude_grid is None:
        return 0 
    
    xi = int(round(x))
    yi = int(round(y))
    max_y, max_x = altitude_grid_shape
    
    # 그리드 범위 내인지 확인
    if 0 <= yi < max_y and 0 <= xi < max_x:
        return float(altitude_grid[yi, xi])
    else:
        return 0 # 맵 밖은 높이 0 처리

# 3. 탄도학 계산 (Ballistics Solution)
def find_elevation_angle(x, y, v0, gravity, prefer_low=True):
    """
    수평거리(x), 높이차(y), 포구속도(v0)가 주어졌을 때 명중 가능한 발사각(theta) 계산
    물리 공식: y = x*tan(θ) - (g*x^2) / (2*v0^2*cos^2(θ)) 의 역산
    """
    if x <= 0.0: return None

    v2 = v0 * v0
    # 판별식 (Discriminant) 확인: 사거리가 닿는지 확인
    # term = v^4 - g(gx^2 + 2yv^2)
    term = v2 * v2 - gravity * (gravity * x * x + 2.0 * y * v2)
    
    if term < 0.0: return None  # 사거리 부족 (닿을 수 없음)
    
    sqrt_term = math.sqrt(term)
    
    # 두 가지 해(직사/곡사) 계산
    t1 = (v2 + sqrt_term) / (gravity * x)
    t2 = (v2 - sqrt_term) / (gravity * x)
    
    candidates = []
    for t in (t1, t2):
        angle = math.atan(t) # 라디안
        candidates.append(angle)
    
    if not candidates: return None

    # 낮은 각도(직사) 우선 선택
    if prefer_low:
        angle = min(candidates, key=lambda a: abs(a))
    else:
        angle = max(candidates, key=lambda a: abs(a))
        
    return math.degrees(angle)

# 4. 각도 차이를 모터 출력(Weight)으로 변환
def angle_to_weight(angle_diff_deg, max_angle=30.0, min_weight=0.0, max_weight=1.0, dead_zone=0.5):
    """ 각도 차이가 클수록 강하게, 작을수록 약하게 회전 """
    diff = abs(angle_diff_deg)
    if diff < dead_zone:
        return 0.0
    if diff >= max_angle:
        return max_weight

    t = (diff - dead_zone) / (max_angle - dead_zone)
    return min_weight + (max_weight - min_weight) * t

# FCS용 각도 정규화
def normalize_angle_deg_for_fcs(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


# -----------------------------------------------------------
# [FCS 메인 함수] - 포신 고각 제어 및 사격 판단
# -----------------------------------------------------------
def fcs_function(request_data : dict):
    global rf_command, rf_weight, fire_command, fire_target_pos, new_fire_point
    
    # 1. 초기화 (매 프레임 리셋)
    rf_command = ""
    rf_weight  = 0.0
    fire_command = False
    new_fire_point = None
    fire_target_pos = None
    
    data = request_data

    # 타겟 데이터 유효성 검사
    ibsm_target = data.get("ibsm_target")
    if (not isinstance(ibsm_target, dict) or "x" not in ibsm_target):
        return # 타겟 없으면 FCS 종료

    # 2. 데이터 파싱
    maptype = int(data.get("map_type", 0))
    check_maptype(maptype) # 맵 로드

    # 좌표 및 상태 정보
    enemy_pos_x = float(data.get("ibsm_target", {}).get("x", 0))
    enemy_pos_z = float(data.get("ibsm_target", {}).get("z", 0))
    
    my_pos_x = float(data.get("ally_body_pos", {}).get("x", 0))
    my_pos_z = float(data.get("ally_body_pos", {}).get("z", 0))
    
    # 고도 계산 (Y좌표)
    enemy_alt = altitude_calculator(enemy_pos_x, enemy_pos_z)
    my_alt = altitude_calculator(my_pos_x, my_pos_z)
    
    enemy_pos_y = enemy_alt
    my_pos_y = my_alt

    # 각도 정보
    my_turret_x = float(data.get("ally_turret_angle", {}).get("x", 0)) # Yaw
    my_turret_y = float(data.get("ally_turret_angle", {}).get("y", 0)) # Pitch
    my_chassis_x = float(data.get("ally_body_angle", {}).get("x", 0))  # 차체 Pitch

    # 물리 상수
    G = 9.81
    muzzle_velocity = 61 # m/s
    fire_target_pos = {"x": enemy_pos_x, "y": enemy_alt, "z": enemy_pos_z}

    # 3. 거리 및 고저차 계산
    dx = enemy_pos_x - my_pos_x
    dz = enemy_pos_z - my_pos_z
    horizontal_distance = math.hypot(dx, dz)
    height_diff = enemy_pos_y - my_pos_y

    # 4. 탄도해(Elevation Angle) 계산
    elevation_angle = None
    if horizontal_distance > 0.1:
        elevation_angle = find_elevation_angle(horizontal_distance, height_diff, muzzle_velocity, G)

    # 5. 포신 제어 (RF Command 생성)
    if elevation_angle is None:
        # 사거리 밖이거나 계산 불가
        rf_command = ""
        rf_weight = 0.0
    else:
        # 목표 각도와 현재 포신 각도 비교
        if elevation_angle > my_turret_y:
            rf_command = "R" # Raise
        elif elevation_angle < my_turret_y:
            rf_command = "F" # Fall (Lower)
        
        # 가중치 계산 (PID 제어 대신 간단한 비례 제어)
        if rf_command != "":
            delta_pitch = elevation_angle - my_turret_y
            rf_weight = angle_to_weight(delta_pitch, max_angle=20.0, dead_zone=0.5)

    # 6. 방위각(Yaw) 정렬 확인
    azimuth_rad = math.atan2(dz, dx)
    azimuth_deg_math = math.degrees(azimuth_rad)
    azimuth_deg_12clock = (90.0 - azimuth_deg_math) % 360.0 # 시뮬레이터 좌표계 변환

    # 7. 포탑 수직 각도 제한(Limit) 확인
    # 차체(Chassis)가 기울어지면 포탑의 가동 범위도 같이 기울어짐을 반영
    chassis_pitch = normalize_angle_deg_for_fcs(my_chassis_x)
    turret_pitch = normalize_angle_deg_for_fcs(my_turret_y)
    
    # 차체 각도 기준 -5도 ~ +10도 제한
    turret_min_angle = chassis_pitch - 5.0
    turret_max_angle = chassis_pitch + 10.0
    
    in_elev_limit = False
    elev_angle_norm = None
    
    if elevation_angle is not None:
        elev_angle_norm = normalize_angle_deg_for_fcs(elevation_angle)
        in_elev_limit = (turret_min_angle <= elev_angle_norm <= turret_max_angle)

    # 8. 이론적 최대 사거리 계산 (발사각 10도 기준)
    # 현재 포신 제한(10도) 내에서 쏠 수 있는 최대 거리
    theta_deg = 10.0
    theta_rad = math.radians(theta_deg)
    range_10deg = (muzzle_velocity ** 2) * math.sin(2.0 * theta_rad) / G

    # 9. 최종 사격 가능 여부 판단
    has_solution = (elevation_angle is not None)     # 물리적으로 닿는가?
    elev_ok = has_solution and in_elev_limit         # 포신 각도 제한 내인가?
    
    # 포탑 정렬 상태 확인 (Yaw & Pitch 오차 1도 이내)
    yaw_err = normalize_angle_deg_for_fcs(azimuth_deg_12clock - my_turret_x)
    pitch_err = 0.0
    if elev_angle_norm is not None:
        pitch_err = normalize_angle_deg_for_fcs(elev_angle_norm - turret_pitch)
        
    yaw_aligned   = abs(yaw_err)   < 1.0
    pitch_aligned = abs(pitch_err) < 1.0

    can_fire_now = has_solution and elev_ok and yaw_aligned and pitch_aligned

    # 10. 사격 불가 시 이동 지점(Waypoint) 제안
    # 조건: 현재 쏠 수 없는데(can_fire_now False), 이유가 사거리 부족 or 각도 제한 때문이라면
    need_move_for_range = (horizontal_distance > range_10deg)
    need_move_for_elev = not elev_ok

    def get_move_position(my_x, my_z, enemy_x, enemy_z, move_distance):
        """ 적 방향으로 일정 거리만큼 전진한 좌표 계산 """
        dx = enemy_x - my_x
        dz = enemy_z - my_z
        total_distance = math.hypot(dx, dz)
        if total_distance == 0.0: return my_x, my_z
        
        # 현재 위치에서 적 방향으로 이동하되, 최대 사거리(range_10deg) 안쪽으로 들어가도록 비율 계산
        ratio = (total_distance - move_distance) / total_distance
        new_x = my_x + dx * ratio
        new_z = my_z + dz * ratio
        return new_x, new_z

    if not can_fire_now and (need_move_for_range or need_move_for_elev):
        fire_command = False
        # 사거리가 닿는 지점까지 이동 제안
        move_x, move_z = get_move_position(my_pos_x, my_pos_z, enemy_pos_x, enemy_pos_z, range_10deg)
        h = altitude_calculator(move_x, move_z) # 해당 지점의 높이 조회
        new_fire_point = {
            "x": move_x,
            "y": h,
            "z": move_z
        }
        print("사격 불가. 이동 추천 좌표 생성:", new_fire_point)
    else:
        fire_command = can_fire_now
        if fire_command:
            print(">>> 사격 허가 (Fire Command: True) <<<")
        else:
            print("사격 대기 중 (정렬 중이거나 안정화 대기)")


##################### API 엔드포인트 (IBSM 통신용) #######################
@app.post("/get_fcs")
def get_fcs():
    """
    [Main Entry Point]
    1. IBSM 요청 데이터 수신
    2. Turret Control (스태빌라이저) 실행
    3. FCS Function (화력 제어) 실행
    4. 최종 JSON 응답 반환
    """
    # JSON 데이터 수신 (force=True: 헤더 상관없이 파싱)
    request_data = request.get_json(force=True, silent=True) or {}

    # 1. 스태빌라이저 실행 -> qe_command, qe_weight 업데이트
    turret_control(request_data)

    # 2. FCS 실행 -> rf_command, fire_command, new_fire_point 업데이트
    fcs_function(request_data)

    # 3. 응답 데이터 구성
    response_data = {
        "QE_command" : qe_command,          # 포탑 회전 (좌우)
        "QE_weight" : qe_weight,            # 회전 속도
        "RF_command" : rf_command,          # 포신 각도 (상하)
        "RF_weight" : rf_weight,            # 각도 조절 속도
        "fire_command" : fire_command,      # 발사 허가
        "fire_target_pos" : fire_target_pos,# 조준점
        "new_fire_point" : new_fire_point   # 이동 제안 좌표
    }

    return jsonify(response_data)


################################ 서버 실행 ################################
if __name__ == "__main__":
    # 호스트 0.0.0.0으로 설정하여 외부 접속 허용, 디버그 모드 활성화
    app.run(host='0.0.0.0', port=5000, debug=True)