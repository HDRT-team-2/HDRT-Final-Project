"""
- 8방향(대각 포함) 격자에서 A* 탐색을 수행
- 대각선 이동 비용은 sqrt(2)로 설정, **코너 끼기(corner cutting)** 를 방지
- Prim 변형으로 작은(coarse) 격자에서 미로를 만든 뒤, **크론(kron)** 으로 확대하여 미로형 장애물을 생성합니다.
- 다양한 격자 크기(n)에 대해 여러 번(trial) 반복 실행하여 평균 처리시간, 성공률, 경로 길이를 계산 및 시각화합니다.

변수명 약어 설명
----------------
- r, c : row, column (행, 열)
- dr, dc : delta row, delta column (행/열 변화량)
- cur : current node (현재 탐색 중인 노드)
- nr, nc : neighbor row, neighbor column (이웃 노드 좌표)
- g : g-score (시작점으로부터 현재까지의 실제 이동 비용)
- f : f-score (f = g + h, 휴리스틱 포함 총비용)
- h : heuristic (목표까지의 추정 비용)
- came_from : 각 노드의 부모 노드 저장 dict
- grid : 2D 격자 (0=빈칸, 1=벽)
- open_heap : (f, g, node)를 담는 최소 힙
- closed : 이미 방문/확정된 노드 집합
- path : 최종 경로 리스트
- n_rows, n_cols : 격자의 행/열 크기
- t0, t1 : 시간 측정용 타이머 시작/종료 값
- dt_ms : 한 trial의 경과 시간(ms)
- mean_time : n별 평균 처리 시간
- mean_path_len : n별 평균 경로 길이 (성공 trial만)
- success_counts : n별 성공 횟수 리스트
- sample_records : 각 n의 대표 시각화용 데이터 (grid, path, found, time_ms)
"""

import math                                                   # √2, 절댓값 등 수학 함수
import random                                                 # 파이썬 표준 난수(시드 고정/재현성)
import time                                                   # 성능 측정(고해상도 타이머)
import csv                                                    # CSV 결과 저장
import numpy as np                                            # 수치 연산 및 배열 처리
import matplotlib.pyplot as plt                               # 시각화(격자/경로/막대그래프)

# ============================================================
# A* 탐색 관련 함수
# ============================================================

def neighbors_8dir(r, c):
    """현재 좌표 (r, c)의 8방향 이웃(상하좌우 + 대각선) 반환."""
    return [
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),              # 직교(상, 하, 좌, 우)
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)       # 대각(좌상, 우상, 좌하, 우하)
    ]


def diagonal_heuristic(a, b):
    """Octile distance 휴리스틱 계산 (8방향 격자에서 적합)."""
    dx = abs(a[0] - b[0])                                     # 행 차이
    dy = abs(a[1] - b[1])                                     # 열 차이
    return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)       # Octile 거리 공식


def reconstruct_path(came_from, current):
    """부모 노드 정보를 따라 시작 → 목표 경로를 복원."""
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return path[::-1]


def a_star_8dir_no_corner_cut(grid, start, goal):
    """
    8방향 A* 탐색 (코너 끼기 방지 포함)

    매개변수 설명:
    - grid : np.ndarray, 0은 빈칸, 1은 장애물
    - start : (row, col), 시작 좌표
    - goal : (row, col), 목표 좌표

    내부 변수 설명:
    - f : 총 예상 비용 (f = g + h)
    - g : 실제 이동 비용
    - cur : 현재 탐색 중인 노드
    - open_heap : (f, g, node)의 튜플을 담는 최소 힙
    - came_from : 각 노드의 부모 노드 저장 dict
    - closed : 이미 방문 및 확정된 노드 집합
    - dr, dc : 현재(cur)에서 다음 노드까지의 행/열 이동량
    """
    n_rows, n_cols = grid.shape

    def in_bounds(r, c):
        return 0 <= r < n_rows and 0 <= c < n_cols             # 경계 체크

    def walkable(r, c):
        return in_bounds(r, c) and grid[r, c] == 0             # 통행 가능(0)인지

    if not walkable(*start) or not walkable(*goal):            # 시작/도착이 막히면 실패
        return None

    import heapq                                               # 우선순위 큐
    g_score = {start: 0.0}                                     # 시작점의 g=0
    f_start = diagonal_heuristic(start, goal)                  # 시작점의 f=g+h
    open_heap = [(f_start, 0.0, start)]                        # (f, g, node)
    came_from = {}                                             # 부모 포인터
    closed = set()                                             # 확정 노드 집합

    while open_heap:                                           # 오픈 리스트가 빌 때까지
        f, g, cur = heapq.heappop(open_heap)                   # f가 최소인 노드 선택
        if cur in closed:                                      # 이미 처리된 노드면 스킵
            continue
        closed.add(cur)

        if cur == goal:                                        # 목표 도달 → 경로 복원
            return reconstruct_path(came_from, cur)

        cr, cc = cur                                           # 현재 좌표 분해
        for nr, nc in neighbors_8dir(cr, cc):                  # 8방향 이웃 순회
            if not in_bounds(nr, nc) or grid[nr, nc] == 1:     # 경계 밖/벽은 스킵
                continue

            dr = nr - cr                                       # 행 이동량(Δrow)
            dc = nc - cc                                       # 열 이동량(Δcol)

            # 대각선 이동 시 코너 끼기 방지: 인접 직교 칸 2개가 모두 비어 있어야 함
            if abs(dr) == 1 and abs(dc) == 1:
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:
                    continue
                step_cost = math.sqrt(2)                        # 대각 이동 비용
            else:
                step_cost = 1.0                                 # 직교 이동 비용

            nxt = (nr, nc)                                     # 다음 노드 좌표
            tentative_g = g + step_cost                        # 후보 g

            # 이미 더 좋은 g가 있으면 스킵
            if nxt in closed and tentative_g >= g_score.get(nxt, float('inf')):
                continue

            # 더 좋은 경로 발견 시 갱신
            if tentative_g < g_score.get(nxt, float('inf')):
                came_from[nxt] = cur
                g_score[nxt] = tentative_g
                f_new = tentative_g + diagonal_heuristic(nxt, goal)
                heapq.heappush(open_heap, (f_new, tentative_g, nxt))

    return None                                                # 경로 없음


# ============================================================
# 미로형 장애물 생성
# ============================================================

def generate_coarse_maze(H, W, rng):
    """
    작은 격자에서 Prim 변형으로 0=길, 1=벽 형태의 미로를 생성.

    변수 설명:
    - H, W : 격자 크기(홀수 권장)
    - rng : random.Random 인스턴스(재현성 유지용)
    - maze : H×W 배열, 0=길, 1=벽
    - walls : 벽 후보 리스트 [(벽행, 벽열, 부모행, 부모열)]
    - (sr, sc) : 시작 셀 좌표
    - (wr, wc) : 후보 벽 셀 좌표
    - (mr, mc) : 벽과 길 사이의 중간 셀
    """
    H = max(3, H | 1)                                         # 홀수 보정
    W = max(3, W | 1)
    maze = np.ones((H, W), dtype=np.uint8)                    # 전체 벽(1)
    sr, sc = 1, 1                                             # 시작 좌표(내부 홀수)
    maze[sr, sc] = 0                                          # 시작 셀 → 길(0)

    walls = []                                                # 인접 벽 후보 리스트

    def add_walls(r, c):                                      # (r,c)에서 두 칸 떨어진 이웃을 후보에 추가
        for dr, dc in [(-2,0),(2,0),(0,-2),(0,2)]:
            nr, nc = r+dr, c+dc
            if 0 <= nr < H and 0 <= nc < W and maze[nr, nc] == 1:
                walls.append((nr, nc, r, c))                  # (벽 좌표, 부모 길 좌표)

    add_walls(sr, sc)                                         # 초기 후보 등록

    while walls:                                              # 후보가 남는 동안 반복
        idx = rng.randrange(len(walls))                       # 무작위 후보 선택
        wr, wc, pr, pc = walls.pop(idx)                       # 선택한 후보 pop
        mr, mc = (wr+pr)//2, (wc+pc)//2                       # 중간 벽 위치(연결 통로)
        if maze[wr, wc] == 1:                                 # 아직 벽이면 허물어 길 연결
            maze[wr, wc] = 0
            maze[mr, mc] = 0
            add_walls(wr, wc)                                 # 새로 열린 길 주변 후보 추가

    return maze


def make_maze_obstacles_grid(n, obstacle_ratio=0.4, seed=123, block_size=6, clear_margin=1):
    """
    최종 n×n 격자(0=빈칸, 1=장애물)를 생성.

    주요 변수:
    - n : 격자 크기
    - obstacle_ratio : 목표 벽 비율(0~1)
    - seed : 난수 시드
    - block_size : 확대 비율 (벽 두께 조절)
    - clear_margin : 테두리 여백 폭
    - fine : 확대된 격자
    - grid : 최종 n×n 격자
    """
    rng = random.Random(seed)
    Hc = max(3, (n // block_size) | 1)
    Wc = max(3, (n // block_size) | 1)

    # 1) 작은 미로 생성(0=길, 1=벽)
    coarse = generate_coarse_maze(Hc, Wc, rng)

    # 2) block_size배로 확장: 셀을 block_size×block_size 블록으로 펼침
    fine = np.kron(coarse, np.ones((block_size, block_size), dtype=np.uint8))

    # 3) n×n 크기에 맞게 중앙 크롭 또는 패딩
    Hf, Wf = fine.shape
    if Hf < n or Wf < n:                                      # 목표보다 작으면 패딩
        pad_r = max(0, n - Hf)
        pad_c = max(0, n - Wf)
        fine = np.pad(
            fine,
            ((pad_r//2, pad_r - pad_r//2), (pad_c//2, pad_c - pad_c//2)),
            mode="edge"                                       # 가장자리 값 복제로 패딩
        )

    sr = (fine.shape[0] - n)//2                               # 중앙 기준 크롭 시작 행
    sc = (fine.shape[1] - n)//2                               # 중앙 기준 크롭 시작 열
    grid = fine[sr:sr+n, sc:sc+n].copy()                      # n×n으로 잘라 복사

    # 4) 가장자리 여백과 시작/도착 보장
    grid[:clear_margin, :] = 0
    grid[:, :clear_margin] = 0
    grid[-clear_margin:, :] = 0
    grid[:, -clear_margin:] = 0
    grid[0, 0] = 0
    grid[n-1, n-1] = 0

    # 5) 벽 비율 보정(랜덤 토글)
    cur_ratio = grid.mean()                                   # 현재 벽 비율
    target = obstacle_ratio
    rng_np = np.random.default_rng(seed + 999)                # NumPy RNG(샘플링)

    if cur_ratio > target:                                    # 벽이 너무 많음 → 벽→길
        wall_pos = np.argwhere(grid == 1)
        need = int((cur_ratio - target) * n * n)
        if need > 0 and len(wall_pos) > 0:
            idx = rng_np.choice(len(wall_pos), size=min(need, len(wall_pos)), replace=False)
            for r, c in wall_pos[idx]:
                grid[r, c] = 0
    elif cur_ratio < target:                                  # 벽이 너무 적음 → 길→벽
        free_pos = np.argwhere(grid == 0)
        need = int((target - cur_ratio) * n * n)
        if need > 0 and len(free_pos) > 0:
            idx = rng_np.choice(len(free_pos), size=min(need, len(free_pos)), replace=False)
            for r, c in free_pos[idx]:
                grid[r, c] = 1
        # 시작/도착은 다시 비움
        grid[0, 0] = 0
        grid[n-1, n-1] = 0

    return grid


# ============================================================
# 실행 / 벤치마크 및 시각화
# ============================================================

if __name__ == "__main__":
    # (1) 실험 설정값 ---------------------------------------------------------
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]  # 테스트할 n 목록(큰→작은)
    obstacle_ratio = 0.20                                      # 목표 벽 비율(예: 20%)
    base_seed = 12345                                          # 시드 기반(재현성)
    trials_per_n = 10                                          # 각 n 당 반복 횟수
    block_size = 4                                             # 미로 확대 배율(벽 굵기 조절)
    clear_margin = 1                                           # 테두리 여백 폭(시작/종료 막힘 방지)

    # (2) 통계 수집 컨테이너 --------------------------------------------------
    avg_time_ms = []                                           # n별 평균 처리시간(ms)
    avg_path_len_success = []                                  # n별 (성공 trial만) 평균 경로 길이
    success_counts = []                                        # n별 성공 횟수
    sample_records = {}                                        # 시각화 샘플: {n: (grid, path, found, time_ms)}

    # CSV 헤더
    csv_rows = [("n", "trials", "success", "avg_time_ms", "avg_path_len_success")]

    # (3) n 값 루프 -----------------------------------------------------------
    for n in n_values:
        start = (n-1, n-1)                                     # 시작: 우하단 모서리
        goal = (0, 0)                                          # 목표: 좌상단 모서리

        times = []                                             # trial별 처리시간(ms)
        path_lens = []                                         # 성공 trial의 경로 길이
        success = 0                                            # 성공 카운트
        sample_saved = False                                   # 첫 trial을 샘플로 저장했는지 여부

        # (4) trial 루프 ------------------------------------------------------
        for t in range(trials_per_n):
            seed = base_seed + n*1000 + t                      # n과 trial t로부터 파생 시드

            # 4-1) 미로형 장애물 그리드 생성
            grid = make_maze_obstacles_grid(
                n,
                obstacle_ratio=obstacle_ratio,
                seed=seed,
                block_size=block_size,
                clear_margin=clear_margin
            )

            # 4-2) A* 실행 및 시간 측정
            t0 = time.perf_counter()                           # 시작 시각
            path = a_star_8dir_no_corner_cut(grid, start, goal)
            t1 = time.perf_counter()                           # 종료 시각
            dt_ms = (t1 - t0) * 1000.0                         # 경과 시간(ms)
            times.append(dt_ms)

            # 4-3) 성공/경로 길이 기록
            if path is not None:
                success += 1
                path_lens.append(len(path))

            # 4-4) 첫 trial을 샘플로 저장(시각화용)
            if not sample_saved:
                sample_records[n] = (grid, path, path is not None, dt_ms)
                sample_saved = True

        # (5) n별 통계 집계 --------------------------------------------------
        mean_time = float(np.mean(times)) if times else 0.0
        mean_path_len = float(np.mean(path_lens)) if path_lens else 0.0

        avg_time_ms.append(mean_time)
        avg_path_len_success.append(mean_path_len)
        success_counts.append(success)

        # 콘솔 요약 출력
        print(
            f"n={n:>3} | trials={trials_per_n} | success={success:<2} | "
            f"avg_time={mean_time:.2f} ms | avg_path_len_success={mean_path_len:.1f}"
        )

        # CSV에 한 행 추가
        csv_rows.append((n, trials_per_n, success, round(mean_time, 4), round(mean_path_len, 2)))

    # (6) CSV 저장 ------------------------------------------------------------
    csv_path = "benchmark_results.csv"                         # CSV 파일 경로
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(csv_rows)
    print(f"[saved] {csv_path}")                               # 저장 로그

    # (7) 시각화: 2×2 묶음 이미지 -------------------------------------------
    def draw_one(ax, n, record):
        """하나의 서브플롯(ax)에 n×n grid와 경로를 그림."""
        grid, path, found, time_ms = record
        ax.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
        start = (n-1, n-1)
        goal = (0, 0)
        ax.scatter([start[1]], [start[0]], s=35, c="blue", marker="s")   # 시작(파랑)
        ax.scatter([goal[1]], [goal[0]], s=35, c="red", marker="s")     # 목표(빨강)

        if found and path is not None:
            ys = [r for r, c in path]
            xs = [c for r, c in path]
            ax.plot(xs, ys, linewidth=1.4, c="green")                     # 경로(초록)
            title_len = len(path)
        else:
            title_len = "False"

        ax.set_title(f"n={n} | len={title_len}\nsample={time_ms:.2f} ms", fontsize=10)
        ax.set_xticks([])
        ax.set_yticks([])

    # n 목록을 4개씩 잘라 2×2 배치로 그림을 저장/표시
    batch_size = 4
    batches = [n_values[i:i+batch_size] for i in range(0, len(n_values), batch_size)]

    for bidx, batch in enumerate(batches, 1):
        fig, axes = plt.subplots(2, 2, figsize=(8, 8))
        axes = axes.ravel()
        for i in range(4):
            ax = axes[i]
            if i < len(batch):
                n = batch[i]
                rec = sample_records[n]
                draw_one(ax, n, rec)
            else:
                ax.axis("off")
        plt.tight_layout()
        out_path = f"grids_batch_{bidx:02d}.jpg"               # 저장 파일명(JPG)
        plt.savefig(out_path, dpi=180)
        print(f"[saved] {out_path}")
        plt.show()                                             # 환경에 따라 생략 가능
        plt.close(fig)

    # (8) n별 평균 처리시간 막대그래프 ---------------------------------------
    fig = plt.figure(figsize=(8, max(6, len(n_values)*0.35)))
    y_pos = np.arange(len(n_values))

    plt.barh(y_pos, avg_time_ms)                               # 가로 막대: 평균 시간(ms)
    plt.yticks(y_pos, [str(n) for n in n_values])
    plt.xlabel("Average A* time (ms)")
    plt.ylabel("Grid size n")
    plt.title("A* 8-dir (no corner cutting) - Avg Runtime by Grid Size")

    # 각 막대 끝에 수치 라벨 표시
    mmax = max(avg_time_ms) if avg_time_ms else 0.0
    for i, v in enumerate(avg_time_ms):
        plt.text(v + (mmax * 0.01 if mmax > 0 else 0.02), i, f"{v:.2f} ms", va="center", fontsize=8)

    plt.tight_layout()
    bar_path = "runtime_barh.jpg"                               # 저장 파일명(JPG)
    plt.savefig(bar_path, dpi=180)
    print(f"[saved] {bar_path}")                                # 저장 로그
    plt.show()                                                  # 그래프 표시(환경에 따라 생략 가능)
    plt.close(fig)                                              # 자원 정리
