import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import math
import numpy as np
import os
import urllib.request

# ==============================================================================
# 1. 한글 폰트 자동 설정 (깨짐 방지용)
# ==============================================================================
# 실행 환경에 폰트가 없으면 네이버 나눔고딕을 자동으로 다운로드합니다.
font_filename = 'NanumGothic.ttf'
font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"

if not os.path.exists(font_filename):
    print(f"한글 폰트({font_filename})가 없어 다운로드합니다...")
    try:
        urllib.request.urlretrieve(font_url, font_filename)
        print("다운로드 완료!")
    except Exception as e:
        print(f"폰트 다운로드 실패: {e}\n한글이 깨질 수 있습니다.")

# 폰트 설정 적용
try:
    font_prop = fm.FontProperties(fname=font_filename)
    plt.rc('font', family=font_prop.get_name())
    plt.rcParams['axes.unicode_minus'] = False # 마이너스(-) 기호 깨짐 방지
    print("한글 폰트 설정 완료.")
except:
    print("폰트 설정 실패. 기본 폰트를 사용합니다.")

# ==============================================================================
# 2. 파라미터 및 데이터 설정
# ==============================================================================
# [A] ADCS 도착 판정 기준
NORMAL_THRESHOLD = 7.0   # 경유지 도착 범위
FINAL_THRESHOLD = 3.0    # 최종 사격 위치 도착 범위
MAX_FIRING_RANGE = 129.73 # 시뮬레이터 최대 사거리

# [B] 사용자 데이터 (로그 파일 경로 & TPP 웨이포인트)
LOG_FILE_PATH = "research/ADCS/archive/analysis/tracking_analysis/log.txt"  # <-- 로그 파일 경로를 여기에 맞춰주세요!

# TPP에서 생성된 웨이포인트 리스트 (복사해오신 것)
TPP_PATH_DATA = [
   {'x': 5.0, 'y': 0.0, 'z': 5.0},
   {'x': 265.0, 'y': 0.0, 'z': 10.0},
   {'x': 275.0, 'y': 0.0, 'z': 20.0},
   {'x': 265.0, 'y': 0.0, 'z': 30.0},
   {'x': 30.0, 'y': 0.0, 'z': 30.0},
   {'x': 20.0, 'y': 0.0, 'z': 40.0},
   {'x': 150.0, 'y': 0.0, 'z': 140.0},
   {'x': 245.0, 'y': 0.0, 'z': 140.0},
   {'x': 255.0, 'y': 0.0, 'z': 150.0},
   {'x': 295.0, 'y': 0.0, 'z': 295.0}
#    163.82183734642092, 'y': 11.628571428571428, 'z': 183.0285640572736
]

# FCS 타겟 위치
FCS_TARGET_POS_X = 250.0
FCS_TARGET_POS_Z = 280.0

# ==============================================================================
# 3. 시각화 로직
# ==============================================================================
def visualize_maneuver(log_file, tpp_waypoints, target_x, target_z, max_range, final_threshold):
    # 1. 로그 데이터 로드
    try:
        # 쉼표(,)로 구분된 CSV 파일 읽기
        df = pd.read_csv(log_file, sep=',')
    except FileNotFoundError:
        print(f"오류: '{log_file}' 파일을 찾을 수 없습니다.")
        return
    except Exception as e:
        print(f"파일 읽기 오류: {e}")
        return

    # 2. 데이터 추출
    # TPP 계획 경로
    path_x = [wp['x'] for wp in tpp_waypoints]
    path_z = [wp['z'] for wp in tpp_waypoints]
    
    # 실제 주행 궤적
    try:
        track_x = df['Player_Pos_X'].values
        track_z = df['Player_Pos_Z'].values
    except KeyError:
        print("오류: 로그 파일 내에 'Player_Pos_X' 또는 'Player_Pos_Z' 컬럼이 없습니다.")
        return
    
    # 주요 지점 정의
    start_x, start_z = track_x[0], track_z[0]
    final_stop_x, final_stop_z = track_x[-1], track_z[-1] # 전차가 멈춘 곳 (P)
    fcs_wp_x, fcs_wp_z = path_x[-1], path_z[-1]           # TPP가 준 사격 위치 (W)

    # 거리 오차 계산
    dist_P_W = math.hypot(final_stop_x - fcs_wp_x, final_stop_z - fcs_wp_z) # 정지점 <-> 목표점
    dist_P_T = math.hypot(final_stop_x - target_x, final_stop_z - target_z) # 정지점 <-> 적군 타겟

    # --------------------------------------------------------------------------
    # 4. 그래프 그리기
    # --------------------------------------------------------------------------
    plt.figure(figsize=(12, 12))
    ax = plt.gca()
    ax.set_aspect('equal', adjustable='box') # 비율 1:1 고정

    # (1) TPP 계획 경로 (검은 점선)
    plt.plot(path_x, path_z, 'k--', label='계획된 경로 (TPP)', linewidth=1.0, alpha=0.6)
    plt.scatter(path_x[:-1], path_z[:-1], color='green', marker='o', s=50, label='경유지 (WayPoint)')

    # (2) 실제 주행 궤적 (파란 실선)
    plt.plot(track_x, track_z, 'b-', label='실제 전차의 주행 궤적', linewidth=2.0, alpha=0.8)
    plt.scatter(start_x, start_z, color='lime', s=80, marker='D', label='시작 지점')
    
    # (3) 최종 정지 지점 (빨간 별)
    plt.scatter(final_stop_x, final_stop_z, color='red', s=200, marker='*', zorder=10, label='최종 정지 지점 (P)')

    # (4) 타겟 및 최대 사거리 (보라색)
    plt.scatter(target_x, target_z, color='purple', s=150, marker='X', zorder=5, label='타겟 위치 (T)')
    # 최대 사거리 원 그리기
    max_range_circle = plt.Circle((target_x, target_z), max_range, 
                                  color='purple', fill=False, linestyle=':', linewidth=1.5, alpha=0.6, 
                                  label=f'최대 사거리 ({max_range}m)')
    ax.add_patch(max_range_circle)

    # (5) 도착 판정 영역 그리기
    # - 일반 경유지 (7m 초록원)
    for px, pz in zip(path_x[:-1], path_z[:-1]):
        circle = plt.Circle((px, pz), NORMAL_THRESHOLD, color='green', fill=True, alpha=0.1)
        ax.add_patch(circle)
    
    # - 최종 사격 위치 (3m 빨간원)
    final_wp_circle = plt.Circle((fcs_wp_x, fcs_wp_z), final_threshold, 
                                 color='red', fill=True, alpha=0.15, linewidth=1.5, linestyle='-',
                                 label=f'도착 판정 반경 ({final_threshold}m)')
    ax.add_patch(final_wp_circle)
    plt.scatter(fcs_wp_x, fcs_wp_z, color='red', s=100, marker='s', zorder=5, label='사격 목표 위치 (W)')

    # (6) 분석 정보 텍스트 박스 (우측 상단)
    info_text = (f"[최종 진단]\n"
                 f"정지점(P) -> 목표점(W): {dist_P_W:.2f} m\n"
                 f"정지점(P) -> 타겟(T):  {dist_P_T:.2f} m\n"
                 f"(최대 사거리 제한: {max_range} m)")
    
    # 박스 위치 설정 (좌표축 기준)
    plt.text(0.30, 0.98, info_text, transform=ax.transAxes, fontsize=12,
             verticalalignment='top', horizontalalignment='right',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='black'))

    # 그래프 스타일
    plt.title('ADCS 경로 추종 및 정밀 정지 분석', fontsize=18, pad=20)
    plt.xlabel('X 좌표 (m)', fontsize=12)
    plt.ylabel('Z 좌표 (m)', fontsize=12)
    plt.xlim(0, 300)
    plt.ylim(0, 300)
    plt.legend(loc='lower right', fontsize=10, framealpha=0.9)
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)

    # 저장 및 출력
    output_filename = 'research/ADCS/archive/analysis/tracking_analysis/track_analysis.png'
    plt.savefig(output_filename, dpi=150, bbox_inches='tight')
    print(f"\n✅ 시각화 완료! '{output_filename}' 파일이 생성되었습니다.")
    plt.show()

# ==============================================================================
# 4. 실행
# ==============================================================================
if __name__ == "__main__":
    visualize_maneuver(LOG_FILE_PATH, TPP_PATH_DATA, FCS_TARGET_POS_X, FCS_TARGET_POS_Z, MAX_FIRING_RANGE, FINAL_THRESHOLD)