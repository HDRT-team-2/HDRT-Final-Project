"""
Detection Mock 데이터 생성
랜덤 탐지 객체 생성 (person, tank, car, truck)
"""

import random
import time

# 객체 클래스 ID
CLASS_IDS = {
    'PERSON': 0,
    'TANK': 1,
    'CAR': 2,
    'TRUCK': 7
}

# 추적 ID 카운터
tracking_id_counter = 1

def generate_mock_detection():
    """
    Mock Detection 데이터 생성
    
    Returns:
        dict: {
            'type': 'detection_update',
            'objects': [
                {
                    'tracking_id': int,
                    'class_id': int,
                    'x': float,
                    'y': float,
                    'timestamp': str
                }
            ]
        }
    """
    global tracking_id_counter
    
    # 1~3개의 랜덤 객체 생성
    num_objects = random.randint(1, 3)
    objects = []
    
    for _ in range(num_objects):
        # 랜덤 클래스 선택
        class_id = random.choice([
            CLASS_IDS['PERSON'],
            CLASS_IDS['TANK'],
            CLASS_IDS['CAR'],
            CLASS_IDS['TRUCK']
        ])
        
        objects.append({
            'tracking_id': tracking_id_counter,
            'class_id': class_id,
            'x': round(random.uniform(0, 300), 2),
            'y': round(random.uniform(0, 300), 2),
            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
        })
        
        tracking_id_counter += 1
    
    return {
        'type': 'detection_update',
        'objects': objects
    }

def reset_tracking_id():
    """추적 ID 카운터 초기화"""
    global tracking_id_counter
    tracking_id_counter = 1