import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
plt.rc("font", family="NanumGothic")

CSV_PATH = "pid/log_data/drive_log.csv"
CORNER_RATE_THRESH = 10.0   # deg/s
ROLL_WIN = 5

def wrap_deg(a):
    return (a + 180) % 360 - 180

# ------------------------
# 데이터 로드
# ------------------------
df = pd.read_csv(CSV_PATH)

time = df["Time"].to_numpy()
yaw_ref = wrap_deg(df["Player_Turret_X"].to_numpy())
yaw_cur = wrap_deg(df["Player_Body_X"].to_numpy())

# ------------------------
# 코너링 검출
# ------------------------
yaw_ref_diff = np.abs(np.diff(yaw_ref, prepend=yaw_ref[0]))
dt = np.mean(np.diff(time))

yaw_rate = yaw_ref_diff / dt
yaw_rate_smooth = pd.Series(yaw_rate).rolling(ROLL_WIN, center=True, min_periods=1).mean().to_numpy()

is_cornering = yaw_rate_smooth > CORNER_RATE_THRESH
is_straight = ~is_cornering

error = wrap_deg(yaw_ref - yaw_cur)

# ------------------------
# 시각화 : 비전공자용 설명 포함
# ------------------------
plt.figure(figsize=(16,10))

# 선 그리기
plt.plot(time, yaw_ref, label="원하는 방향(목표)", linewidth=3, color="black")
plt.plot(time, yaw_cur, label="전차 실제 방향", linewidth=3, color="blue")

# 코너링/직진 구역 표시
plt.fill_between(time, -200, 200,
                 where=is_cornering,
                 color='red', alpha=0.15,
                 label="급격한 방향 전환 구간(코너링)")

plt.fill_between(time, -200, 200,
                 where=is_straight,
                 color='green', alpha=0.10,
                 label="안정적인 직선 주행 구간")

# ------------------------
# 한국어 설명 박스 추가
# ------------------------
plt.text(0.02, 0.95,
         "🔴 빨간 구간: 전차가 급격하게 방향을 틀어야 하는 구간입니다.\n"
         "    → 목표 방향과 실제 방향의 차이가 커질 수 있어 제어가 어려움.\n\n"
         "🟢 녹색 구간: 전차가 안정적으로 움직이는 구간입니다.\n"
         "    → 두 선이 비슷하게 움직이면 제어 성능이 좋다는 뜻입니다.\n\n"
         "검정색 선 = 목표 방향(경로 계획)\n"
         "파란색 선 = 실제 전차의 움직임\n"
         "두 선의 차이 = 제어 성능을 나타내는 지표",
         transform=plt.gca().transAxes,
         fontsize=12, bbox=dict(facecolor='white', alpha=0.8))

# ------------------------
# 마무리 꾸밈
# ------------------------
plt.title("전차 주행 방향 추종 시각화 (한국어 설명 포함)", fontsize=20)
plt.xlabel("시간 (초)", fontsize=14)
plt.ylabel("방향(Yaw, 도)", fontsize=14)
plt.grid(True)
plt.legend(fontsize=14)
plt.tight_layout()
plt.show()

# ------------------------
# Error subplot도 한국어 설명 추가
# ------------------------
plt.figure(figsize=(16,8))

plt.subplot(2,1,1)
plt.plot(time[is_straight], error[is_straight], color="green")
plt.title("직선 구간에서의 목표 대비 방향 오차", fontsize=16)
plt.xlabel("시간 (초)")
plt.ylabel("오차 (도)")
plt.grid(True)

plt.subplot(2,1,2)
plt.plot(time[is_cornering], error[is_cornering], color="red")
plt.title("코너 구간에서의 목표 대비 방향 오차", fontsize=16)
plt.xlabel("시간 (초)")
plt.ylabel("오차 (도)")
plt.grid(True)

plt.tight_layout()
plt.show()
