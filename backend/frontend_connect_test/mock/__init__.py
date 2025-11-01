"""
Mock 데이터 생성 모듈
Frontend 테스트용 가짜 데이터 생성
"""

from .mock_detection import generate_mock_detection
from .mock_position import generate_mock_position
from .mock_fire import generate_mock_fire

__all__ = [
    'generate_mock_detection',
    'generate_mock_position',
    'generate_mock_fire'
]