import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
plt.rcParams['font.family'] = 'Malgun Gothic'

def process_and_plot(df, stop_method, ax, min_running_time=17.0):
    """
    min_running_time: 주행 시작 후 최소 이 시간 이상 경과 후 감속을 제동으로 간주 [s]
    """
    x_col, y_col, time_col = 'Player_Pos_X', 'Player_Pos_Y', 'Time'
    x = df[x_col].values
    y = df[y_col].values
    time = df[time_col].values

    # 속도 계산 (좌표 기반)
    dx = np.diff(x)
    dy = np.diff(y)
    dt = np.diff(time)
    dt[dt == 0] = 1e-6  # 0으로 나눔 방지
    speed = np.sqrt(dx**2 + dy**2) / dt
    speed = np.append(speed, speed[-1])

    # 이동 평균 필터로 속도 스무딩
    window = 5
    smooth_speed = np.convolve(speed, np.ones(window)/window, mode='same')

    df['Calc_Speed'] = smooth_speed

    # 가속도 계산 및 스무딩
    acc = np.diff(smooth_speed) / np.diff(time)
    acc = np.append(acc, acc[-1])
    acc_smooth = np.convolve(acc, np.ones(window)/window, mode='same')
    df['Acceleration'] = acc_smooth

    # 상태 초기화
    state = ['stop' if s < 0.01 else 'moving' for s in smooth_speed]

    # 주행 시작 시점
    moving_start_idx = next((i for i, s in enumerate(state) if s == 'moving'), 0)
    running_start_time = time[moving_start_idx]

    # 제동 구간 탐지
    min_decel_duration = 1.5  # 최소 감속 지속 시간 [s]
    min_decel_drop = 0.2      # 최소 속도 감소량 [m/s]

    decel_flags = np.zeros_like(smooth_speed, dtype=bool)
    in_decel = False
    start_idx = 0

    for i in range(moving_start_idx + 1, len(smooth_speed)):
        if time[i] - running_start_time < min_running_time:
            continue

        # 감속 구간 조건
        if (smooth_speed[i] < smooth_speed[i - 1]) and (acc_smooth[i] < -0.01):
            if not in_decel:
                in_decel = True
                start_idx = i - 1
        else:
            if in_decel:
                duration = time[i - 1] - time[start_idx]
                delta_v = smooth_speed[start_idx] - smooth_speed[i - 1]
                # 짧거나 미미한 감속은 무시(전진 가속 시의 노면 노이즈를 무시하고 실 제동거리만 측정하기 위함)
                if duration >= min_decel_duration and delta_v >= min_decel_drop:
                    decel_flags[start_idx:i] = True
                in_decel = False

    if in_decel:
        duration = time[-1] - time[start_idx]
        delta_v = smooth_speed[start_idx] - smooth_speed[-1]
        if duration >= min_decel_duration and delta_v >= min_decel_drop:
            decel_flags[start_idx:] = True

    # 제동 구간 병합
    # 작은 gap은 무시하고 연결
    for i in range(1, len(decel_flags) - 1):
        if not decel_flags[i] and decel_flags[i - 1] and decel_flags[i + 1]:
            decel_flags[i] = True

    # 상태 업데이트
    for i in range(len(state)):
        if decel_flags[i]:
            state[i] = 'decelerating'

    df['State'] = state

    # 통계
    moving_idx = [i for i, s in enumerate(state) if s == 'moving']
    decel_idx = [i for i, s in enumerate(state) if s == 'decelerating']

    moving_speed_max = smooth_speed[moving_idx].max() if moving_idx else 0
    moving_speed_mean = smooth_speed[moving_idx].mean() if moving_idx else 0
    moving_acc_max = acc_smooth[moving_idx].max() if moving_idx else 0
    moving_acc_mean = acc_smooth[moving_idx].mean() if moving_idx else 0

    decel_speed_max = smooth_speed[decel_idx].max() if decel_idx else 0
    decel_speed_mean = smooth_speed[decel_idx].mean() if decel_idx else 0
    decel_acc_min = acc_smooth[decel_idx].min() if decel_idx else 0
    decel_acc_mean = acc_smooth[decel_idx].mean() if decel_idx else 0

    if decel_idx:
        decel_time = time[decel_idx[-1]] - time[decel_idx[0]]
        decel_distance = np.sum(np.sqrt(np.diff(x[decel_idx])**2 + np.diff(y[decel_idx])**2))
    else:
        decel_time = 0
        decel_distance = 0

    # 시각화
    ax.plot(time, smooth_speed, color='blue', label='Speed')

    in_decel = False
    for i, s in enumerate(state):
        if s == 'decelerating' and not in_decel:
            in_decel = True
            start_idx = i
        elif s != 'decelerating' and in_decel:
            in_decel = False
            ax.plot(time[start_idx:i], smooth_speed[start_idx:i], color='red', linewidth=2)
            ax.axvline(time[start_idx], color='red', linestyle='--', linewidth=1)
            ax.axvline(time[i - 1], color='red', linestyle='--', linewidth=1)
    if in_decel:
        ax.plot(time[start_idx:], smooth_speed[start_idx:], color='red', linewidth=2)

    # 가속도 영역
    ax.fill_between(time, 0, acc_smooth, color='green', alpha=0.2, label='Acceleration')

    ax.set_title(f'{stop_method} Method')
    ax.set_xlabel('Time [s]')
    ax.set_ylabel('Speed [m/s] & Acceleration [m/s²]')
    ax.grid(True)

    textstr = f"""전진 구간:
속력 최대/평균 = {moving_speed_max:.2f}/{moving_speed_mean:.2f} m/s
가속도 최대/평균 = {moving_acc_max:.2f}/{moving_acc_mean:.2f} m/s²

제동 구간 (주행 17초 이후):
속력 최대/평균 = {decel_speed_max:.2f}/{decel_speed_mean:.2f} m/s
가속도 최소/평균 = {decel_acc_min:.2f}/{decel_acc_mean:.2f} m/s²
제동 거리 = {decel_distance:.2f} m
제동 시간 = {decel_time:.2f} s
"""
    ax.text(0.02, 0.95, textstr, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.7))
    ax.legend()

# 메인
methods = ['s', 'stop', 'w_keyup']
fig, axes = plt.subplots(3, 1, figsize=(10, 14))

for ax, method in zip(axes, methods):
    excel_path = f'research/body_control/path_planning/stop_velocity/data/stop_velocity_{method}.xlsx'
    df = pd.read_excel(excel_path)
    process_and_plot(df, method, ax, min_running_time=17.0)

plt.tight_layout()
# plt.savefig('research/body_control/path_planning/stop_velocity/study/visualization/stop_all_methods.png')
plt.show()