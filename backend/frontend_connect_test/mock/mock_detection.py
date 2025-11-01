"""
Detection Mock 데이터 생성
랜덤 탐지 객체 생성 (person, tank, car, truck)
"""

import random
import time
from .mock_fire import push_mock_fire_event

# 객체 클래스 ID
CLASS_IDS = {
    'OTHER': 0,
    'CAR2': 1,
    'CAR3': 2,
    'CAR4': 3,
    'HUMAN1': 4,
    'TANK1': 5,
    'ROCK1': 6,
    'ROCK2': 7,
    'MINE1': 8,
    'WALL2': 9,
    'WALL2X10': 10,
}

RANDOM_CLASS_IDS = [
    CLASS_IDS['CAR2'],
    CLASS_IDS['CAR3'],
    CLASS_IDS['CAR4'],
    CLASS_IDS['HUMAN1'],
    CLASS_IDS['TANK1'],
    CLASS_IDS['ROCK1'],
    CLASS_IDS['ROCK2'],
    CLASS_IDS['MINE1'],
    CLASS_IDS['WALL2'],
    CLASS_IDS['WALL2X10'],
    CLASS_IDS['OTHER'],
]


# 추적 ID 카운터
tracking_id_counter = 1


# Detection push 구조를 위한 콜백 등록 및 목표 기반 mock 생성
_detection_update_callback = None
_detection_target = None
_detection_loop_thread = None
_detection_loop_running = False

def set_detection_update_callback(cb):
    global _detection_update_callback
    _detection_update_callback = cb

def set_detection_target(x, y):
    """
    목표 좌표가 들어오면 detection mock 데이터 생성 루프를 시작
    """
    global _detection_target, _detection_loop_running, _detection_loop_thread
    _detection_target = (x, y)
    if not _detection_loop_running:
        _detection_loop_running = True
        import threading
        def loop():
            while _detection_loop_running and _detection_target is not None:
                data = generate_mock_detection_with_target(_detection_target)
                if _detection_update_callback:
                    _detection_update_callback(data)
                time.sleep(2.0)
        _detection_loop_thread = threading.Thread(target=loop, daemon=True)
        _detection_loop_thread.start()

def stop_detection_loop():
    global _detection_loop_running
    _detection_loop_running = False

def generate_mock_detection_with_target(target):
    """
    목표 좌표가 들어온 이후부터 랜덤 detection 객체를 생성 (객체 위치는 랜덤)
    """
    return generate_mock_detection()

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
    
    # 1~2개의 랜덤 객체 생성
    num_objects = random.randint(1, 2)
    objects = []
    
    for _ in range(num_objects):
        # 랜덤 클래스 선택
        class_id = random.choice(RANDOM_CLASS_IDS)

        obj = {
        'tracking_id': tracking_id_counter,
        'class_id': class_id,
        'x': round(random.uniform(0, 300), 2),
        'y': round(random.uniform(0, 300), 2),
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
        }

        # tank 객체면 fire 이벤트도 mock으로 push
        if class_id == CLASS_IDS['TANK1']:
            push_mock_fire_event(obj['tracking_id'])

        objects.append(obj)
        tracking_id_counter += 1
    
    return {
        'type': 'detection_update',
        'objects': objects
    }

def reset_tracking_id():
    """추적 ID 카운터 초기화"""
    global tracking_id_counter
    tracking_id_counter = 1