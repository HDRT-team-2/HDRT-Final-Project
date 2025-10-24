# Stablization의 계산 함수 수정하고자 만든 새로운 계산 함수(다른 코드에서는 Stabilizer 함수로 명시되어 있음)


# -------------------------
# 포탑 Stabilization 계산 함수
# -------------------------
import math

def compute_turret_target(ally_pos, turret_angles, enemy_pos):
    """
    아군 전차 위치와 포탑 각도, 적 전차 위치를 기반으로
    포탑이 바라봐야 할 절대/상대 yaw, pitch 계산

    Parameters
    ----------
    ally_pos : dict
        {'x': float, 'y': float, 'z': float} 아군 전차 위치
    turret_angles : dict
        {'yaw': float, 'pitch': float} 현재 포탑 각도 (deg)
    enemy_pos : dict
        {'x': float, 'y': float, 'z': float} 적 전차 위치

    Returns
    -------
    dict
        {
            'yaw_absolute': float,   # 목표 절대 yaw (0~360°)
            'pitch_absolute': float, # 목표 절대 pitch
            'yaw_relative': float,   # 현재 대비 yaw 차이 (-180~180°)
            'pitch_relative': float  # 현재 대비 pitch 차이
        }
    """
    # -------------------------
    # 위치 차 계산
    # -------------------------
    dx = enemy_pos['x'] - ally_pos['x']  # x축 거리
    dz = enemy_pos['z'] - ally_pos['z']  # z축 거리
    dy = enemy_pos['y'] - ally_pos['y']  # y축 거리 (높이)

    # x-z 평면 거리 계산
    distance_xz = math.hypot(dx, dz)

    # -------------------------
    # 목표 yaw 계산
    # -------------------------
    # atan2(dx, dz)로 북쪽 0°, 시계방향 증가 기준
    yaw_rad = math.atan2(dx, dz)
    target_yaw = math.degrees(yaw_rad)
    if target_yaw < 0:
        target_yaw += 360  # 0~360° 범위로 변환

    # -------------------------
    # 목표 pitch 계산
    # -------------------------
    target_pitch = math.degrees(math.atan2(dy, distance_xz))

    # -------------------------
    # 현재 포탑 대비 상대값 계산
    # -------------------------
    yaw_relative = target_yaw - turret_angles.get('yaw', 0)
    # 상대 yaw 값 범위 조정 (-180 ~ 180)
    if yaw_relative > 180:
        yaw_relative -= 360
    elif yaw_relative < -180:
        yaw_relative += 360

    pitch_relative = target_pitch - turret_angles.get('pitch', 0)

    # -------------------------
    # 결과 반환
    # -------------------------
    return {
        'yaw_absolute': target_yaw,
        'pitch_absolute': target_pitch,
        'yaw_relative': yaw_relative,
        'pitch_relative': pitch_relative
    }

# -------------------------
# 테스트 예시
# -------------------------
input_ally_pos = {'x': 54.4284, 'y': 6.37, 'z': 76.1538}
input_turret_angles = {'yaw': 358.76, 'pitch': 2.7}  # 현재 포탑 각도
input_enemy_pos = {'x': 135.46, 'y': 8.6, 'z': 276.87}  # 적 위치

angles = compute_turret_target(input_ally_pos, input_turret_angles, input_enemy_pos)
print("목표 포탑 각도:", angles)
