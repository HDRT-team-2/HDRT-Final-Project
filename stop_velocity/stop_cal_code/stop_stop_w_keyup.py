import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
plt.rcParams['font.family'] = 'Malgun Gothic'

# 데이터 읽기
stop_method = 'w_keyup'
excel_path = f'stop_velocity/stop_dataset/stop_velocity_{stop_method}.xlsx'
df = pd.read_excel(excel_path)

# 좌표와 시간
x_col, y_col, time_col = 'Player_Pos_X', 'Player_Pos_Y', 'Time'
x = df[x_col].values
y = df[y_col].values
time = df[time_col].values

# 2. 좌표 기반 속도 계산
dx = np.diff(x)
dy = np.diff(y)
dt = np.diff(time)
speed = np.sqrt(dx**2 + dy**2) / dt
speed = np.append(speed, speed[-1])
df['Calc_Speed'] = speed

# 가속도 계산
acceleration = np.diff(speed) / np.diff(time)
acceleration = np.append(acceleration, acceleration[-1])
df['Acceleration'] = acceleration

# 상태 구간 분류
state = []
for i in range(len(speed)):
    if speed[i] < 0.01:
        state.append('stop')
    elif i > 0 and speed[i] < speed[i-1]:
        state.append('decelerating')
    else:
        state.append('moving')
df['State'] = state

# 제동 시작 인덱스
deceleration_start_idx = next((i for i, s in enumerate(state) if s=='decelerating'), None)

# 전진 구간 속도/가속도 통계
moving_idx = [i for i, s in enumerate(state) if s=='moving']
moving_speed_max = speed[moving_idx].max()
moving_speed_mean = speed[moving_idx].mean()
moving_acc_max = acceleration[moving_idx].max()
moving_acc_mean = acceleration[moving_idx].mean()

# 제동 구간 속도/가속도 통계
decelerating_idx = [i for i, s in enumerate(state) if s=='decelerating']
decel_speed_max = speed[decelerating_idx].max()
decel_speed_mean = speed[decelerating_idx].mean()
decel_acc_min = acceleration[decelerating_idx].min()  # 제동가속도는 음수
decel_acc_mean = acceleration[decelerating_idx].mean()

# 시각화
plt.figure(figsize=(14,6))

# 전체 속도
plt.plot(time, speed, color='blue', label='Speed')

# 연속 제동 구간만 빨간 하이라이트
in_decel = False
start_idx = 0
for i, s in enumerate(state):
    if s == 'decelerating' and not in_decel:
        # 제동 시작
        in_decel = True
        start_idx = i
    elif s != 'decelerating' and in_decel:
        # 제동 종료
        in_decel = False
        plt.plot(time[start_idx:i], speed[start_idx:i], color='red', linewidth=2)
if in_decel:
    # 마지막 제동 구간이 끝까지 이어진 경우
    plt.plot(time[start_idx:], speed[start_idx:], color='red', linewidth=2)

# 가속도는 투명도로 표현
plt.fill_between(time, 0, acceleration, color='green', alpha=0.2, label='Acceleration')

plt.title(f'"{stop_method}" Method - 전진/제동 속도 및 가속도')
plt.xlabel('Time [s]')
plt.ylabel('Speed [m/s] & Acceleration [m/s²]')
plt.grid(True)

# 텍스트 정보 추가
textstr = f"""전진 구간:
속력 최대/평균 = {moving_speed_max:.2f}/{moving_speed_mean:.2f} m/s
가속도 최대/평균 = {moving_acc_max:.2f}/{moving_acc_mean:.2f} m/s²

제동 구간:
속력 최대/평균 = {decel_speed_max:.2f}/{decel_speed_mean:.2f} m/s
가속도 최소/평균 = {decel_acc_min:.2f}/{decel_acc_mean:.2f} m/s²
"""
plt.text(0.02, 0.40, textstr, transform=plt.gca().transAxes, fontsize=10,
         verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))

plt.legend()
plt.tight_layout()
plt.savefig(f'stop_velocity/stop_consequence/stop_velocity_{stop_method}.png')
plt.show()
