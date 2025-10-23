# stabilizer에 터렛 회전 계산과 명령 생성을 통합해 get_action에서 호출만으로 자동회전 명령할 수 있는 코드 

"""
def stabilizer(ally_x, ally_y, ally_z, enemy_x, enemy_y, enemy_z):
    
    # ally_x, ally_y, ally_z: 아군 전차 좌표
    # enemy_x, enemy_y, enemy_z: 적 전차 좌표

    # 반환: QE/RF 터렛 명령과 가중치


    global player_turret_x, player_turret_y  # 현재 터렛 각도 전역 변수 사용

    # 아군과 적 전차 간 상대 위치 계산
    dx = enemy_x - ally_x  # X축 차이
    dz = enemy_z - ally_z  # Z축 차이
    dy = enemy_y - ally_y  # Y축 차이 (높이)

    # XZ 평면 거리 계산
    distance_xz = math.hypot(dx, dz)
    target_pitch = math.degrees(math.atan2(dy, distance_xz))  # 포신 상하 각도

    # 목표 yaw 계산 (터렛 좌/우 회전 각도)
    yaw_rad = math.atan2(dx, dz)
    target_yaw = math.degrees(yaw_rad)
    if target_yaw < 0:
        target_yaw += 360  # 음수 보정

    # --- 터렛 Q/E 회전 명령 계산 ---
    turret_qe_command = ""
    turret_qe_weight = 0.0
    yaw_angle_diff = target_yaw - player_turret_x  # 목표 yaw와 현재 터렛 yaw 차이
    if abs(yaw_angle_diff) > 1.0:  # 오차 1도 이상일 때만 회전
        turret_qe_command = "Q" if yaw_angle_diff < 0 else "E"  # 좌/우 선택
        turret_qe_weight = 1.0 if abs(yaw_angle_diff) >= 10.0 else 0.1  # 가중치 (큰 차이면 강하게)

    # --- 터렛 R/F 회전 명령 계산 ---
    turret_rf_command = ""
    turret_rf_weight = 0.0
    pitch_angle_diff = target_pitch - player_turret_y  # 목표 pitch와 현재 터렛 pitch 차이
    if abs(pitch_angle_diff) > 1.0:  # 오차 1도 이상
        turret_rf_command = "R" if pitch_angle_diff > 0 else "F"  # 상/하 선택
        turret_rf_weight = 1.0 if abs(pitch_angle_diff) >= 10.0 else 0.1  # 가중치

    # 계산된 명령과 가중치를 반환
    return turret_qe_command, turret_qe_weight, turret_rf_command, turret_rf_weight


# --- /get_action 엔드포인트 ---
@app.route('/get_action', methods=['POST'])
def get_action():
    global player_x, player_y, player_z, player_turret_x, player_turret_y
    global enemy_x, enemy_y, enemy_z

    # stabilizer 호출: 현재 좌표 기반으로 터렛 회전 명령 생성
    QE_command, QE_weight, RF_command, RF_weight = stabilizer(
        player_x, player_y, player_z, 
        enemy_x, enemy_y, enemy_z
    )

    # 주행 명령 없이 터렛 회전만 반환
    action = {
        "moveWS": {"command": "S", "weight": 0.0},  # 전진/후진 명령 없음
        "moveAD": {"command": "", "weight": 0.0},   # 좌/우 이동 없음
        "turretQE": {"command": QE_command, "weight": QE_weight},  # 좌/우 회전
        "turretRF": {"command": RF_command, "weight": RF_weight},  # 상/하 회전
        "fire": False  # 발사 없음
    }

    # JSON 형태로 반환
    return jsonify(action)
    
    """