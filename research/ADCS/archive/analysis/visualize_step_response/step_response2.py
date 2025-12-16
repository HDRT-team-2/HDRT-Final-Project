import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# =========================
# 사용자 설정
# =========================
CSV_PATH = "pid/log_data/drive_log.csv"
STEP_THRESH_DEG = 20.0       # 급격한 yaw 변화 감지 threshold
WINDOW_AFTER_STEP = 300      # step 이후 분석할 샘플 개수
SETTLING_BAND_DEG = 5.0      # ±5도 밴드

# =========================
# 유틸 함수
# =========================
def wrap_deg(a):
    """각도를 -180~180 범위로 래핑."""
    return (a + 180) % 360 - 180

def compute_step_metrics(t, ref, cur, band_deg=5.0):
    """step response의 주요 제어공학 지표 계산."""
    t = np.asarray(t, float)
    ref = wrap_deg(np.asarray(ref, float))
    cur = wrap_deg(np.asarray(cur, float))
    
    n = len(t)
    out = dict(rise_time=np.nan, overshoot_pct=np.nan, settling_time=np.nan, ss_error=np.nan)
    if n < 5:
        return out

    # step 크기
    ref0, ref1 = ref[0], ref[-1]
    amp = wrap_deg(ref1 - ref0)
    if abs(amp) < 1e-6:
        # 거의 변화 없을 때
        out["ss_error"] = np.nanmedian(wrap_deg(cur - ref1)[-5:])
        return out

    # 정규화
    y = wrap_deg(cur - ref0) / amp

    # rise time
    if amp > 0:
        idx10 = np.where(y >= 0.1)[0]
        idx90 = np.where(y >= 0.9)[0]
    else:
        idx10 = np.where(y <= -0.1)[0]
        idx90 = np.where(y <= -0.9)[0]

    if len(idx10) and len(idx90):
        out["rise_time"] = t[idx90[0]] - t[idx10[0]]

    # overshoot
    over = wrap_deg(cur - ref1)
    peak = np.max(over) if amp > 0 else np.min(over)
    out["overshoot_pct"] = (peak / abs(amp)) * 100.0

    # settling time
    within = np.abs(wrap_deg(cur - ref1)) <= band_deg
    for i in range(n):
        if np.all(within[i:]):
            out["settling_time"] = t[i] - t[0]
            break

    # steady-state error
    tail = max(5, n // 10)
    out["ss_error"] = np.nanmedian(wrap_deg(cur - ref1)[-tail:])
    return out

# =========================
# 데이터 로드
# =========================
df = pd.read_csv(CSV_PATH)

time = df["Time"].to_numpy(float)

# current yaw
yaw_cur = wrap_deg(df["Player_Body_X"].to_numpy(float))

# target yaw (ref)
yaw_ref = wrap_deg(df["Player_Turret_X"].to_numpy(float))

# =========================
# step-like 이벤트 찾기 (첫 번째 코너링)
# =========================
yaw_diff = np.abs(np.diff(yaw_ref, prepend=yaw_ref[0]))

step_candidates = np.where(yaw_diff > STEP_THRESH_DEG)[0]

if len(step_candidates) == 0:
    raise RuntimeError("⚠ 첫 번째 코너링(step-like event)을 찾지 못했습니다. threshold 조정 필요.")

step_idx = step_candidates[0]   # 첫 번째 코너링만 사용

print(f"✅ 첫 번째 코너링 감지됨: index {step_idx}, 시간 {time[step_idx]:.2f}s")

# =========================
# step 응답 구간 잘라내기
# =========================
end_idx = min(len(time), step_idx + WINDOW_AFTER_STEP)

t_seg = time[step_idx:end_idx] - time[step_idx]
ref_seg = yaw_ref[step_idx:end_idx]
cur_seg = yaw_cur[step_idx:end_idx]

# =========================
# 정규화
# =========================
ref0 = ref_seg[0]
ref1 = ref_seg[-1]
amp = wrap_deg(ref1 - ref0)

if abs(amp) < 1e-6:
    raise RuntimeError("⚠ step amplitude(목표 yaw 변화량)가 너무 작아서 step response 분석 불가능.")

y_norm = wrap_deg(cur_seg - ref0) / amp
r_norm = np.ones_like(y_norm)  # reference normalized to 1

# =========================
# step metrics 계산
# =========================
metrics = compute_step_metrics(t_seg, ref_seg, cur_seg, band_deg=SETTLING_BAND_DEG)

print("\n===== Step Response Metrics (First Cornering) =====")
for k, v in metrics.items():
    print(f"{k}: {v}")

# =========================
# 시각화
# =========================
plt.figure(figsize=(12, 6))
plt.plot(t_seg, r_norm, 'k--', linewidth=2, label="Reference (Normalized)")
plt.plot(t_seg, y_norm, 'b-', linewidth=2, label="Response (Normalized)")

plt.title("Normalized Step Response (First Cornering)", fontsize=16)
plt.xlabel("Time (s)", fontsize=14)
plt.ylabel("Normalized Amplitude", fontsize=14)
plt.grid(True)

# overshoot 표시
if not np.isnan(metrics["overshoot_pct"]):
    peak_idx = np.argmax(y_norm)
    plt.scatter(t_seg[peak_idx], y_norm[peak_idx], color='red', s=80,
                label=f"Overshoot: {metrics['overshoot_pct']:.1f}%")

# settling time 표시
if not np.isnan(metrics["settling_time"]):
    st = metrics["settling_time"]
    plt.axvline(st, color='orange', linestyle='--',
                label=f"Settling Time: {st:.2f}s")

# steady-state error 표시
plt.text(0.02, 0.95,
         f"Steady-State Error: {metrics['ss_error']:.2f}°",
         transform=plt.gca().transAxes,
         fontsize=12,
         bbox=dict(facecolor='white', alpha=0.8))

plt.legend(fontsize=12)
plt.tight_layout()
plt.show()
