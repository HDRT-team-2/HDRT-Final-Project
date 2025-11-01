_fire_update_callback = None
def set_fire_update_callback(cb):
    global _fire_update_callback
    _fire_update_callback = cb

def push_mock_fire_event(target_tracking_id):
    if _fire_update_callback:
        data = generate_mock_fire(target_tracking_id)
        _fire_update_callback(data)
"""
Fire Mock 데이터 생성
발포 이벤트 시뮬레이션
"""

import time

def generate_mock_fire(target_tracking_id):
    """
    Mock Fire 데이터 생성
    
    Args:
        target_tracking_id: 목표 tracking_id
        
    Returns:
        dict: {
            'type': 'fire_event',
            'target_tracking_id': int,
            'timestamp': str
        }
    """
    return {
        'type': 'fire_event',
        'target_tracking_id': target_tracking_id,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S')
    }