"""
약 20km/h로 주행(W키 키다운) 후 정지(W키 키업)했을 때의 로그에 대해서
정지하는 구간에 대해서만 주로 해석하는 코드입니다.
'서로 다른 속도에서, 가속력을 제거(W키업)했을 때 제동거리와 제동시간이 과연 선형적으로 변화하는가?'에 대해서만 알아보기 위한 간단한 실험입니다.
주행 모듈 내 API를 통해 제어하지 않고 얻은 로그를 활용하였습니다.
"""

import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LinearRegression
from itertools import groupby
from operator import itemgetter

plt.rcParams['font.family'] = 'Malgun Gothic'

v = 40

# 데이터 불러오기
df = pd.read_excel(f"research/body_control/path_planning/tank_deaccelerate/data/tank_velocity_{v}.xlsx")
time_sec = df.iloc[:, 1].values
pos_z = df.iloc[:, 5].values  # Player_Pos_Z

# 속도 계산
linear_velocity = np.zeros_like(pos_z)
dt = np.diff(time_sec)
linear_velocity[1:] = np.diff(pos_z) / dt

# 가속도 계산
linear_acceleration = np.zeros_like(pos_z)
linear_acceleration[1:] = np.diff(linear_velocity) / dt

# 정지 직전 감속 구간 식별
decel_mask = linear_acceleration < 0
decel_indices = np.where(decel_mask)[0]

def get_longest_continuous(indices):
    groups = []
    for k, g in groupby(enumerate(indices), lambda x: x[0]-x[1]):
        group = list(map(itemgetter(1), g))
        groups.append(group)
    return groups[-1]  # 마지막 그룹(정지 직전) 선택

if len(decel_indices) > 0:
    last_decel_group = get_longest_continuous(decel_indices)
    decel_time = time_sec[last_decel_group]
    decel_velocity = linear_velocity[last_decel_group]
    decel_acceleration = linear_acceleration[last_decel_group]
    decel_position = pos_z[last_decel_group]
else:
    decel_time = decel_velocity = decel_acceleration = decel_position = np.array([])

# 정지 직전 구간 선형회귀
if len(decel_time) > 1:
    # 속도 회귀
    model_v = LinearRegression()
    model_v.fit(decel_time.reshape(-1,1), decel_velocity)
    v_pred = model_v.predict(decel_time.reshape(-1,1))
    
    # 가속도 회귀
    model_a = LinearRegression()
    model_a.fit(decel_time.reshape(-1,1), decel_acceleration)
    a_pred = model_a.predict(decel_time.reshape(-1,1))
else:
    v_pred = a_pred = []

# 시각화
plt.figure(figsize=(14, 10))

# 위치
plt.subplot(3,1,1)
plt.plot(time_sec, pos_z, color='blue', label="위치")
plt.plot(decel_time, decel_position, color='red', linewidth=2, label="정지 직전 감속 구간")
plt.ylabel("위치 (m)")
plt.title("장비 주행 및 정지 직전 감속 분석")
plt.legend()
plt.grid(True)

# 속도
plt.subplot(3,1,2)
plt.plot(time_sec, linear_velocity, color='green', label="속도")
plt.plot(decel_time, decel_velocity, 'ro', label="감속 구간 속도")
if len(v_pred) > 0:
    plt.plot(decel_time, v_pred, 'r--', label="속도 선형회귀")
plt.axhline(0, color='black', linestyle='--')
plt.ylabel("속도 (m/s)")
plt.legend()
plt.grid(True)

# 가속도
plt.subplot(3,1,3)
plt.plot(time_sec, linear_acceleration, color='purple', label="가속도")
plt.plot(decel_time, decel_acceleration, 'ro', label="감속 구간 가속도")
if len(a_pred) > 0:
    plt.plot(decel_time, a_pred, 'r--', label="가속도 선형회귀")
plt.axhline(0, color='black', linestyle='--')
plt.xlabel("시간 (s)")
plt.ylabel("가속도 (m/s²)")
plt.legend()
plt.grid(True)

plt.tight_layout()

plt.savefig(f'source/research/body_control/path_planning/tank_deaccelerate/tank_deaccelerate_{v}km.png')
plt.show()

# 정지 직전 감속 통계 및 선형회귀 기울기 출력
if len(decel_time) > 0:
    braking_distance = decel_position[-1] - decel_position[0]
    braking_time = decel_time[-1] - decel_time[0]
    
    print(f"시속 40km 정지 직전 감속 통계")
    print(f"감속 시작 시간: {decel_time[0]:.2f} s, 정지 시간: {decel_time[-1]:.2f} s")
    print(f"감속 시간: {braking_time:.2f} s")
    print(f"감속 시작 위치: {decel_position[0]:.2f} m, 정지 위치: {decel_position[-1]:.2f} m")
    print(f"감속 거리: {braking_distance:.2f} m")
    print(f"최대 감속: {np.min(decel_acceleration):.2f} m/s²")
    
    print("\n정지 직전 감속 구간 속도 및 가속도:")
    print(f"{'시간(s)':>8} | {'속도(m/s)':>10} | {'가속도(m/s²)':>12}")
    print("-"*36)
    for t, v, a in zip(decel_time, decel_velocity, decel_acceleration):
        print(f"{t:8.2f} | {v:10.3f} | {a:12.3f}")
    
    if len(v_pred) > 0:
        print(f"\n속도 선형회귀: {model_v.coef_[0]:.3f} m/s")
    if len(a_pred) > 0:
        print(f"가속도 선형회귀: {model_a.coef_[0]:.3f} m/s²")
else:
    print("정지 직전 감속 구간이 존재하지 않습니다.")
