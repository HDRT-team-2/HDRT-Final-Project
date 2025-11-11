import os

# 현재 파일(settings.py)의 위치를 기준으로 경로를 설정
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 입력 영상이 들어있는 폴더
# 이 폴더 아래에 4개 맵 폴더(Forest and River, Country Road, Wildness Dry, Simple Flat)가 있어야 함
INPUT_DIR = os.path.join(BASE_DIR, "INPUT")

# 추출된 프레임이 저장될 폴더
# 실행 시 자동으로 지워지고 다시 만들어짐
OUTPUT_DIR = os.path.join(BASE_DIR, "OUTPUT")

# 프레임 추출 간격 (초 단위)
# 2로 설정하면 "2초마다 1장"씩 추출됨
FRAME_INTERVAL = 2
