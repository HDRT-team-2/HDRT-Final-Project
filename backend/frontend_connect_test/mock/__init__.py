"""
Mock 데이터 생성 모듈
Frontend 테스트용 가짜 데이터 생성
"""

from .mock_detection import generate_mock_detection, set_detection_update_callback, set_detection_target, stop_detection_loop
from .mock_position import generate_mock_position, set_target_position, set_position_update_callback
from .mock_fire import generate_mock_fire, set_fire_update_callback

__all__ = [
    'generate_mock_detection',
    'generate_mock_position',
    'generate_mock_fire',
    'set_fire_update_callback',
    'set_target_position',
    'set_position_update_callback',
    'set_detection_update_callback',
    'set_detection_target',
    'stop_detection_loop'
]