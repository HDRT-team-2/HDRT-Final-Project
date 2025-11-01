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
            'timestamp': str,
            'result': str
        }
    """
    return {
        'type': 'fire_event',
        'target_tracking_id': target_tracking_id,
        'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S'),
        'result': 'success'  # success, miss
    }