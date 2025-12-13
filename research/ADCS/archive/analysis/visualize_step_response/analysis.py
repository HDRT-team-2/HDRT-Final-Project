import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import correlate
from scipy.fft import fft, fftfreq
plt.rc("font", family="NanumGothic")
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['axes.formatter.use_mathtext'] = False

# ======================================
# 1. CSV 로드
# ======================================
CSV_PATH = "pid/log_data/drive_log.csv"

df = pd.read_csv(CSV_PATH)

required = ["Time", "Player_Turret_X", "Player_Body_X"]
for c in required:
    if c not in df.columns:
        raise ValueError(f"CSV에 '{c}' 컬럼이 없습니다.")

time = df["Time"].to_numpy(dtype=float)
yaw_ref = df["Player_Turret_X"].to_numpy(dtype=float)
yaw_cur = df["Player_Body_X"].to_numpy(dtype=float)


# ======================================
# 2. 각도 wrap
# ======================================
def wrap_deg(a):
    return (a + 180) % 360 - 180

yaw_ref = wrap_deg(yaw_ref)
yaw_cur = wrap_deg(yaw_cur)


# ======================================
# 3. Tracking Error 계산
# ======================================
error = wrap_deg(yaw_ref - yaw_cur)

RMS = np.sqrt(np.mean(error**2))
MAE = np.mean(np.abs(error))
MAX_ERR = np.max(np.abs(error))

# ======================================
# 4. 코너링/직진 자동 분류
# ======================================
yaw_diff = np.abs(np.diff(yaw_ref, prepend=yaw_ref[0]))
dt = np.mean(np.diff(time))
yaw_rate = yaw_diff / dt

yaw_rate_smooth = (
    pd.Series(yaw_rate).rolling(5, min_periods=1, center=True).mean().to_numpy()
)

CORNER_THRESHOLD = 10
is_corner = yaw_rate_smooth > CORNER_THRESHOLD
is_straight = ~is_corner


# ======================================
# 5. Cross-correlation 기반 Delay
# ======================================
ref_z = yaw_ref - np.mean(yaw_ref)
cur_z = yaw_cur - np.mean(yaw_cur)

corr = correlate(cur_z, ref_z, mode="full")
lags = np.arange(-len(ref_z) + 1, len(ref_z))
lag_index = np.argmax(corr)
lag_samples = lags[lag_index]
time_delay = lag_samples * dt


# ======================================
# 6. FFT 분석
# ======================================
N = len(time)
Y_ref = fft(yaw_ref)
Y_cur = fft(yaw_cur)
freq = fftfreq(N, d=dt)

pos = freq > 0
freq_pos = freq[pos]
mag_ref = np.abs(Y_ref[pos])
mag_cur = np.abs(Y_cur[pos])


# ======================================
# 7A. 첫 번째 Figure (Tracking + Error)
# ======================================
plt.figure(figsize=(16, 10))

# -------------------------------------
# Subplot 1: Tracking
# -------------------------------------
ax1 = plt.subplot(2, 1, 1)

ax1.fill_between(time, -200, 200,
                 where=is_corner,
                 color='red', alpha=0.15,
                 label="코너링 구간")

ax1.fill_between(time, -200, 200,
                 where=is_straight,
                 color='green', alpha=0.10,
                 label="직선 주행 구간")

ax1.plot(time, yaw_ref, label="목표 방향(경로 기반)", linewidth=2, color="black")
ax1.plot(time, yaw_cur, label="전차 실제 방향", linewidth=2, color="blue")

ax1.set_title("전차 방향 추종(Tracking)", fontsize=16)
ax1.set_xlabel("시간 (s)")
ax1.set_ylabel("Yaw (도)")
ax1.grid(True)
ax1.legend(fontsize=10)

# 한국어 설명
ax1.text(0.02, 0.90,
         "코너링 구간: 큰 조향 → 에러 증가 가능성 높음\n"
         "직선 구간: 안정적 제어 구간\n\n"
         "검정 = 목표 / 파랑 = 실제",
         transform=ax1.transAxes,
         fontsize=10, bbox=dict(facecolor='white', alpha=0.7))

# -------------------------------------
# Subplot 2: Error(t)
# -------------------------------------
ax2 = plt.subplot(2, 1, 2)
ax2.plot(time, error, color="red", label="방향 오차")
ax2.axhline(0, color="black", linewidth=1)
ax2.grid(True)

ax2.set_title(f"오차 분석 — RMS={RMS:.2f}, MAE={MAE:.2f}, 최고 오차={MAX_ERR:.2f}", fontsize=15)
ax2.set_xlabel("시간 (s)")
ax2.set_ylabel("오차(도)")

plt.tight_layout()
plt.show()


# ======================================
# 7B. 두 번째 Figure (Cross-correlation + FFT)
# ======================================
plt.figure(figsize=(16, 10))

# -------------------------------------
# Subplot 3: Cross-correlation
# -------------------------------------
ax3 = plt.subplot(2, 1, 1)
ax3.plot(lags * dt, corr, color="purple")
ax3.axvline(time_delay, color="orange", linestyle="--",
            label=f"검출된 지연 시간: {time_delay:.3f}초")
ax3.grid(True)
ax3.set_title("목표 vs 실제 방향 신호 상관 분석(시간 지연)", fontsize=16)
ax3.set_xlabel("지연(Lag) [초]")
ax3.set_ylabel("상관도")
ax3.legend()

# -------------------------------------
# Subplot 4: Frequency Response
# -------------------------------------
ax4 = plt.subplot(2, 1, 2)
ax4.semilogy(freq_pos, mag_ref, label="목표 방향")
ax4.semilogy(freq_pos, mag_cur, label="실제 방향")

ax4.grid(True)
ax4.set_title("주파수 스펙트럼 분석(진동성/제어 품질)", fontsize=16)
ax4.set_xlabel("주파수 (Hz)")
ax4.set_ylabel("Magnitude")
ax4.legend()

plt.tight_layout()
plt.show()
