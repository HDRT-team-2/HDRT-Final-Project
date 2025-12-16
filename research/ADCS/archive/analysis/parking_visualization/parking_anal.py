import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os
import urllib.request

log_pile = 'research/ADCS/archive/analysis/parking_anal/log.txt'

# ==============================================================================
# 1. 한글 폰트 설정
# ==============================================================================
font_filename = 'NanumGothic.ttf'
font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
if not os.path.exists(font_filename):
    try: urllib.request.urlretrieve(font_url, font_filename)
    except: pass
try:
    font_prop = fm.FontProperties(fname=font_filename)
    plt.rc('font', family=font_prop.get_name())
    plt.rcParams['axes.unicode_minus'] = False 
except: pass

# ==============================================================================
# 2. 로그 분석 로직
# ==============================================================================
def analyze_parking_behavior(log_file):
    try:
        # 데이터 로드 (csv or space-separated)
        df = pd.read_csv(log_file, sep=',') 
    except:
        print(f"오류: '{log_file}' 파일을 읽을 수 없습니다.")
        return

    # 마지막 15초 데이터만 추출 (종료 직전 상황 분석)
    if 'Time' not in df.columns:
        print("Time 컬럼이 없습니다.")
        return
        
    end_time = df['Time'].iloc[-1]
    start_analysis_time = max(0, end_time - 15.0)
    
    # 데이터 필터링
    mask = df['Time'] >= start_analysis_time
    df_tail = df[mask].copy()
    
    time = df_tail['Time'].values
    speed = df_tail['Player_Speed'].values
    
    # 마지막 지점(목표)과의 거리 재계산 (로그에 Distance가 있지만 확인차)
    final_x = df['Player_Pos_X'].iloc[-1]
    final_z = df['Player_Pos_Z'].iloc[-1]
    
    # 각 시점에서의 잔여 거리 계산 (목표점은 마지막 정지 위치로 가정)
    # 실제로는 TPP 목표점이겠지만, 로그만으로는 정지점이 목표 근처라 가정하고 패턴 분석
    dist_to_stop = ((df_tail['Player_Pos_X'] - final_x)**2 + (df_tail['Player_Pos_Z'] - final_z)**2)**0.5

    # --------------------------------------------------------
    # 그래프 그리기
    # --------------------------------------------------------
    fig, ax1 = plt.subplots(figsize=(12, 6))

    # 속도 그래프 (파란색)
    line1 = ax1.plot(time, speed, 'b-', label='속도 (m/s)', linewidth=2)
    ax1.set_xlabel('시간 (초)')
    ax1.set_ylabel('속도 (m/s)', color='b')
    ax1.tick_params(axis='y', labelcolor='b')
    ax1.grid(True, linestyle='--', alpha=0.5)

    # 거리 그래프 (빨간 점선)
    ax2 = ax1.twinx()
    line2 = ax2.plot(time, dist_to_stop, 'r--', label='남은 거리 (m)', linewidth=2, alpha=0.7)
    ax2.set_ylabel('목표까지 거리 (m)', color='r')
    ax2.tick_params(axis='y', labelcolor='r')

    # 범례 통합
    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='upper left')

    plt.title(f'종료 직전 15초 주행 분석 ("깔짝임" 현상 진단)', fontsize=14)
    
    # 진동(Jitter) 감지 텍스트
    # 속도가 0 근처에서 자주 등락하는지 확인
    zero_crossings = ((speed[:-1] > 0.1) & (speed[1:] < 0.1)).sum()
    
    info_text = f"정지/출발 반복 횟수: {zero_crossings}회\n(높을수록 '깔짝임' 심함)"
    plt.text(0.02, 0.85, info_text, transform=ax1.transAxes, 
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    output_filename = 'research/ADCS/archive/parking_visualization/parking_jitter_analysis.png'
    plt.savefig(output_filename)
    print(f"분석 완료! 결과 이미지 저장됨: {output_filename}")
    plt.show()

# 실행 (로그 파일명이 다르면 여기서 수정하세요)
if __name__ == "__main__":
    analyze_parking_behavior("research/ADCS/archive/analysis/parking_visualization/log.txt")