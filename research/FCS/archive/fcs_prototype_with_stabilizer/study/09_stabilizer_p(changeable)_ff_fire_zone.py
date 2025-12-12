"""
[통합 시스템] 스태빌라이저 (Lag 대응형) + FCS (탄도 계산 및 이동 예측)

1. 스태빌라이저: 단순화된 P(비례) + FF(피드포워드) 제어를 사용하여 통신 지연(Lag)이 발생해도 포탑이 튀지 않도록 함.
2. FCS: 지형 고도 데이터를 로딩하고, 탄도학을 계산하여 사격 가능 여부 판단 및 이동 좌표를 추천함.
"""
############################ 필요 라이브러리 선언 ###########################
import os
from flask import Flask, request, jsonify
import math
import pandas as pd
import numpy as np
import time
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
############################## Flask 추가 ################################
app = Flask(__name__)

##################### IBSM에 보낼 데이터의 기본값 ##########################
qe_command = ""         # 포탑 좌우 회전 명령 (Q/E)
qe_weight = 0           # 포탑 회전 강도 (0.0 ~ 1.0)
rf_command = ""         # 포신 상하 조절 명령 (R/F)
rf_weight = 0           # 포신 조절 강도
fire_command = False    # 발사 허가 여부
fire_target_pos = None  # 조준하고 있는 적의 좌표
new_fire_point = None   # 사격 불가능 시 이동해야 할 추천 좌표

######################## 스태빌라이져용 전역변수 ###########################
# 물체(장애물/적) 조준용 타깃 좌표
aim_target_x = None
aim_target_y = None
aim_target_z = None

########################### FCS용 전역변수 ###############################
# 맵 데이터(CSV)를 메모리에 로드하여 저장하는 변수들 (매번 파일 읽는 것 방지)
altitude_df = None              # Pandas DataFrame 형태의 고도 데이터
altitude_grid = None            # Numpy 2D 배열 형태의 고도 그리드 (검색 속도 최적화)
altitude_grid_shape = None      # 그리드 크기 (Max Y, Max X)

FIRE_RANGE_FACTOR = 1.0     # 최대 사거리의 100% 지점까지만 실제 운용 사거리로 이용함. 

# [최적화] 이전 프레임의 적 위치와 계산 결과를 기억하기 위한 캐시 변수
# 매 프레임마다 미세하게 변하는 적 위치 때문에 탱크가 덜덜거리는 현상을 막기 위함 (Hysteresis)
prev_enemy_x = None         # 직전에 계산했던 적 X
prev_enemy_y = None         # 직전에 계산했던 적 Y 
prev_enemy_z = None         # 직전에 계산했던 적 Z
cached_move_x = None        # 캐싱된 이동 목표 X
cached_move_y = None        # 캐싱된 이동 목표 Y 
cached_move_z = None        # 캐싱된 이동 목표 Z

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
        # ========= [1. 계단식 P제어 설정 (변경됨)] =================
        # 기존 Kp_fast, Kp_slow를 3단계 레벨로 확장
        
        # Level 3 (원거리): 오차가 10도 이상일 때. 풀 파워로 빠르게 추적.
        self.Kp_Level_3 = 0.10 
        
        # Level 2 (중거리): 오차가 3~10도일 때. 적당히 감속하며 접근.
        self.Kp_Level_2 = 0.04 
        
        # Level 1 (근거리): 오차가 3도 미만일 때. 아주 정밀하게 주차.
        self.Kp_Level_1 = 0.01 

        # 구간 설정 (단위: 도)
        self.ZONE_FAR = 10.0   # 이 각도보다 크면 Level 3
        self.ZONE_MID = 3.0    # 이 각도보다 크면 Level 2
        
        # 데드밴드 (기존 유지, 0.5도 이내면 정지)
        self.YAW_DEADBAND = 0.5 

        # ========= [2. D제어 변수 (기존 유지)] =================
        self.Kd_yaw = 0.002       # D게인 (떨림이 심하면 줄이고, 못 멈추면 늘림)
        self.prev_yaw_error = None
        self.prev_time = None

        # ========= [3. FF제어 변수 (기존 유지)] =================
        self.Kff_ad = 1.0         # 차체 회전 역보상

        # ========= [4. 기타 설정] =================
        self.MAX_QE = 15.0        # 모터 최대 출력
        self.MIN_QE_OUTPUT = 0.01 # 최소 출력

    def update(
        self,
        *,
        time_val: float, 
        player_x: float, player_y: float, player_z: float,
        player_turret_x: float,     # 현재 포탑의 절대 Yaw 각도
        target_x: float, target_y: float, target_z: float,
        body_yaw: float,            # 차체의 절대 Yaw 각도
        body_AD_cmd: str,           # 키보드 A/D 입력 상태
        body_AD_weight: float,      # 키보드 입력 강도
        player_speed: float,
        body_WS_weight: float = 0.0
    ):
        # 1. 목표 지점을 향한 절대 방위각(Target Yaw) 계산
        dx = target_x - player_x
        dz = target_z - player_z
        target_yaw = math.degrees(math.atan2(dx, dz))
        # normalize_angle_deg 함수가 외부에 있다고 가정
        yaw_err_now = normalize_angle_deg(target_yaw - player_turret_x)
        abs_error = abs(yaw_err_now)

        # 2. 데드밴드 체크
        if abs_error < self.YAW_DEADBAND and body_AD_weight < 0.1:
            self.prev_yaw_error = yaw_err_now
            self.prev_time = time_val
            return "", 0.0

        # ================= [제어 로직 시작] =================
        
        # (A) dt(시간 변화량) 계산
        dt = 0.0
        if self.prev_time is not None:
            dt = time_val - self.prev_time
            
        # (B) 계단식 P (비례) 항 계산: 오차 구간에 따라 게인 선택 [핵심 변경 사항]
        current_kp = 0.0
        
        if abs_error >= self.ZONE_FAR:
            # 목표가 아주 멀다 -> Level 3 (Fastest)
            current_kp = self.Kp_Level_3
            
        elif abs_error >= self.ZONE_MID:
            # 중간 거리다 -> Level 2 (Medium)
            current_kp = self.Kp_Level_2
            
        else:
            # 거의 다 왔다 -> Level 1 (Slow/Precision)
            current_kp = self.Kp_Level_1
            
        P = current_kp * yaw_err_now

        # (C) FF (피드포워드) 항 계산
        FF = 0.0
        if body_AD_cmd == "A":   # 차체 좌회전
            FF = self.Kff_ad * body_AD_weight  # 포탑 우회전 힘 (+)
        elif body_AD_cmd == "D": # 차체 우회전
            FF = -self.Kff_ad * body_AD_weight # 포탑 좌회전 힘 (-)

        # (D) 최종 출력 합산
        u = P + FF

        # ==========================================================

        # 상태 업데이트
        self.prev_yaw_error = yaw_err_now
        self.prev_time = time_val

        # 4. 하드웨어 출력 제한
        if u > self.MAX_QE: u = self.MAX_QE
        elif u < -self.MAX_QE: u = -self.MAX_QE

        # 5. 최소 출력 무시
        if abs(u) < self.MIN_QE_OUTPUT:
            return "", 0.0

        # 6. 최종 명령 생성
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
    body_yaw = float(ally_ang.get("y", 0.0))            # 차체 Yaw
    player_speed = float(request_data.get("ally_speed", 0.0))

    # 차체 제어 명령 파싱 (FF 제어에 사용)
    body_AD_cmd    = request_data.get("AD_command", "")
    body_AD_weight = float(request_data.get("AD_weight", 0.0))
    body_WS_weight = float(request_data.get("WS_weight", 0.0))

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

    # 전역 변수에 결과 저장 (나중에 반환됨)
    qe_command = QE_cmd
    qe_weight  = QE_w

############################### FCS 기능 ################################
# FCS 기능에 사용할 함수들
# 맵 종류에 맞는 Altatude Map csv 파일을 읽어와서 판다스 데이터프레임에 저장, 그리고 넘파이 2D그리드화(최초 1회)
def check_maptype(maptype: int):
    """
    맵 종류에 따라 해당하는 지형 고도(CSV) 파일을 로드하여 메모리(Numpy Grid)에 캐싱.
    이미 로드된 맵이라면 다시 읽지 않아 성능을 최적화함.
    """
    global altitude_df, altitude_grid, altitude_grid_shape

    # 이미 같은 맵이 로드되어 있다면 패스
    if getattr(check_maptype, "_loaded_mt", None) == maptype and altitude_df is not None:
        return  # 이전과 같은 맵이라면, 맵 정보 재로딩을 하지 않음.

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
    global rf_command, rf_weight, fire_command, fire_target_pos, new_fire_point
    global prev_enemy_x, prev_enemy_y, prev_enemy_z
    global cached_move_x, cached_move_y, cached_move_z

    # IBSM으로부터 받아온 request_data들을 사용하기 위해 변수로 저장.
    data =  request_data    

    # 매 프레임 초기화 (stale 값 방지)
    rf_command = ""
    rf_weight  = 0.0
    fire_command = False
    new_fire_point = None
    fire_target_pos = None
    
    # IBSM으로 부터 읽어온 값들을 계산에 쓰기 위한 변수로 저장(payload 누락에 대한 예외처리, 0 추가.)
    data =  request_data

    # IBSM으로부터 받은 타겟의 존재 여부 확인 : 적을 상대하는게 아닌, 스태빌라이저만 필요할 때, FCS는 실행시키지 않게 하기
    ibsm_target = data.get("ibsm_target")
    if (not isinstance(ibsm_target, dict) or "x" not in ibsm_target or "y" not in ibsm_target or "z" not in ibsm_target):
        return   # 더 이상 계산하지 않고 바로 종료, 추가로 위에서 매 프레임 초기화를 하기 때문에 fire_target_pos도 None으로 반환

    # IBSM으로 부터 읽어온 값들을 계산에 쓰기 위한 변수로 저장(payload 누락에 대한 예외처리, 0 추가.)
    maptype = int(data.get("map_type", 0))      # 맵 타입
    check_maptype(maptype)
    enemy_pos_x = float(data.get("ibsm_target", {}).get("x", 0))    # 적 x좌표 (시뮬레이터 기준)
    enemy_pos_y = float(data.get("ibsm_target", {}).get("y", 0))    # 적 y좌표 (시뮬레이터 기준, 고도)
    enemy_pos_z = float(data.get("ibsm_target", {}).get("z", 0))    # 적 z좌표 (시뮬레이터 기준)
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

    # 1. 최대 사거리 반지름 설정 (R)
    MAX_FIRE_RANGE = range_10deg * FIRE_RANGE_FACTOR
    print(f"최대 사거리(반지름 R): {MAX_FIRE_RANGE:.2f} m")

    # 2. 원형 방정식에 따른 사격 가능 구역 판별
    #    공식: (x - xe)^2 + (z - ze)^2 <= R^2
    #    여기서 horizontal_distance는 sqrt((x-xe)^2 + (z-ze)^2) 입니다.
    dx = enemy_pos_x - my_pos_x
    dz = enemy_pos_z - my_pos_z
    horizontal_distance = math.hypot(dx, dz)
    
    # 원의 내부(Inside Circle)에 있는지 확인
    in_range = (horizontal_distance <= MAX_FIRE_RANGE)

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

    # 최종 사격 가능 여부 판단
    # 원 안에 있고(in_range), 탄도해가 있고(has_solution), 각도가 맞아야(elev_ok, aligned) 함
    can_fire_now = has_solution and elev_ok and yaw_aligned and pitch_aligned and in_range

    # 이동해야 할 위치 계산 후, x,y 좌표를 반환하는 계산기 매서드 (적 전차 방향으로 사정거리만큼 접근)
    def get_circular_edge_position(my_x, my_z, enemy_x, enemy_z, move_distance):
        dx = enemy_x - my_x
        dz = enemy_z - my_z
        total_distance = math.hypot(dx, dz)
        if total_distance == 0.0:                   # 내s가 적 좌표와 같은 x,z에 있을 경우, 0으로 나누는것 방지용
            return my_x, my_z                       # 그냥 원래 x, z좌표 반환
        ratio = (total_distance - move_distance) / total_distance   # 전체 거리 중 필요한 거리 만큼만 적 방향으로 이동
        new_x = my_x + dx * ratio
        new_z = my_z + dz * ratio
        return new_x, new_z                         # 새로 가야할 x좌표, z좌표를 반환

    # 이동 필요 여부 판단 (원 밖으로 나갔으면 이동해야 함)
    need_move_for_range = not in_range  
    need_move_for_elev = not elev_ok  # 고각 제한 밖이면 위치를 바꿀 필요가 있다고 가정

    # 수정사항 : 현재 사격이동좌표가 계속 변동이 일어나 이것을 저장하고 범위내(5%)에 일정하면 저장된 좌표로 이동하는걸로 계산
    if not can_fire_now and (need_move_for_range or need_move_for_elev):
        fire_command = False
        
        use_cached_data = False 

        # 1. 이전에 저장된 적 좌표(X, Y, Z)가 모두 있는지 확인
        if (prev_enemy_x is not None and 
            prev_enemy_y is not None and 
            prev_enemy_z is not None):
            
            # 2. 오차 범위(5%) 계산 (Y 포함)
            margin_x = max(abs(prev_enemy_x * 0.05), 0.1)
            margin_y = max(abs(prev_enemy_y * 0.05), 0.1)
            margin_z = max(abs(prev_enemy_z * 0.05), 0.1)

            # 3. 현재 적 위치와 이전 적 위치 차이 계산
            diff_x = abs(enemy_pos_x - prev_enemy_x)
            diff_y = abs(enemy_pos_y - prev_enemy_y)
            diff_z = abs(enemy_pos_z - prev_enemy_z)

            # 4. X, Y, Z 모두 오차 범위 이내여야 함
            if (diff_x <= margin_x and 
                diff_y <= margin_y and 
                diff_z <= margin_z):
                use_cached_data = True

        # 분기 처리
        if use_cached_data:
            # 저장해뒀던 X, Y(h), Z 모두 재사용
            move_x = cached_move_x
            h      = cached_move_y  # 저장해둔 높이값 불러오기
            move_z = cached_move_z
            
        else:
            # ================= [핵심 수정 부분] =================
            # 사거리 밖(원 밖)이라면, 원의 경계선(둘레) 좌표를 계산하여 반환
            # 원형 방정식: (x - xe)^2 + (z - ze)^2 = R^2 인 지점 찾기
            
            move_x, move_z = get_circular_edge_position(
                my_pos_x, my_pos_z,       # 내 위치
                enemy_pos_x, enemy_pos_z, # 적 위치 (원의 중심)
                MAX_FIRE_RANGE            # 반지름 (R)
            )
            # ====================================================

            h = altitude_calculator(move_x, move_z) # 높이 계산
            
            # 적 좌표(Y포함)와 결과값(h포함) 저장
            prev_enemy_x = enemy_pos_x
            prev_enemy_y = enemy_pos_y  # 현재 적 Y 저장
            prev_enemy_z = enemy_pos_z
            
            cached_move_x = move_x
            cached_move_y = h           # 계산된 높이 저장
            cached_move_z = move_z

        new_fire_point = {
            "x": move_x,
            "y": h,
            "z": move_z
        }
        print("사격 불가. 이동 추천 좌표(원형 경계):", new_fire_point)

    else:
        fire_command = can_fire_now
        if fire_command:
            print("사격 가능 (원형 구역 내 진입 완료)")
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
        "new_fire_point" : new_fire_point   # 현 위치 즉시 사격 불가 시 사격 가능 지점, dict형, {"x": 15.0, "y": 25.0, "z": 0.0}
    }
    #print("IBSM으로 보낼 데이터 : ", response_data)

    # 호출자(IBSM)에게 결과 반환
    return jsonify(response_data)


################################ 메인매서드 ################################
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)