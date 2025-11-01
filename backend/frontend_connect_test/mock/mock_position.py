"""
Position Mock 데이터 생성
랜덤 위치 이동 시뮬레이션
"""

import random



# 현재 위치 상태
current_position = {
    'x': 0.0,
    'y': 0.0
}

# 목표 위치 상태 (None이면 이동 없음)
target_position = None

# 콜백 함수 (test_server에서 등록)
position_update_callback = None

# 이동 루프 제어
moving = False

def generate_mock_position():
    """
    Mock Position 데이터 생성 (목표 좌표가 있으면 해당 좌표까지 이동)
    """
    global current_position, target_position
    step = 2.0  # 한 번에 이동할 최대 거리
    updated = False
    if target_position:
        dx = target_position[0] - current_position['x']
        dy = target_position[1] - current_position['y']
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist < step:
            current_position['x'] = target_position[0]
            current_position['y'] = target_position[1]
            target_position = None  # 도달하면 목표 해제
            updated = True
        else:
            current_position['x'] += step * dx / dist
            current_position['y'] += step * dy / dist
            updated = True
    # 범위 제한 (0 ~ 300)
    current_position['x'] = max(0, min(300, current_position['x']))
    current_position['y'] = max(0, min(300, current_position['y']))
    return {
        'type': 'position_update',
        'x': round(current_position['x'], 2),
        'y': round(current_position['y'], 2)
    }, updated

def set_position_update_callback(cb):
    global position_update_callback
    position_update_callback = cb

def start_position_update_loop():
    import threading, time
    global moving
    if moving:
        return
    moving = True
    def loop():
        global moving
        while moving:
            pos, updated = generate_mock_position()
            if updated and position_update_callback:
                position_update_callback(pos)
            time.sleep(0.5)
    threading.Thread(target=loop, daemon=True).start()

def stop_position_update_loop():
    global moving
    moving = False

def set_target_position(x, y):
    """목표 좌표를 설정하면 해당 좌표까지 이동 시작"""
    global target_position
    target_position = (float(x), float(y))
    # 이동 루프가 꺼져 있으면 자동 시작
    start_position_update_loop()

def reset_position():
    """위치 초기화"""
    global current_position
    current_position = {
        'x': 0.0,
        'y': 0.0
    }