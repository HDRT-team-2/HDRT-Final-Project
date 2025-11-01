"""
Position Mock 데이터 생성
랜덤 위치 이동 시뮬레이션
"""

import random

# 현재 위치 상태
current_position = {
    'x': 150.0,
    'y': 150.0,
    'angle': 0.0
}

def generate_mock_position():
    """
    Mock Position 데이터 생성
    
    Returns:
        dict: {
            'type': 'position_update',
            'x': float,
            'y': float,
            'angle': float
        }
    """
    global current_position
    
    # 랜덤 이동 (-1 ~ 1)
    current_position['x'] += random.uniform(-1, 1)
    current_position['y'] += random.uniform(-1, 1)
    current_position['angle'] += random.uniform(-5, 5)
    
    # 범위 제한 (0 ~ 300)
    current_position['x'] = max(0, min(300, current_position['x']))
    current_position['y'] = max(0, min(300, current_position['y']))
    
    # 각도 정규화 (0 ~ 360)
    current_position['angle'] = current_position['angle'] % 360
    
    return {
        'type': 'position_update',
        'x': round(current_position['x'], 2),
        'y': round(current_position['y'], 2),
        'angle': round(current_position['angle'], 2)
    }

def reset_position():
    """위치 초기화"""
    global current_position
    current_position = {
        'x': 150.0,
        'y': 150.0,
        'angle': 0.0
    }