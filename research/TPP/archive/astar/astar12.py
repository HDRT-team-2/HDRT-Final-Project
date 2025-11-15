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

import math
import random
import time
import csv
import numpy as np
import matplotlib.pyplot as plt

# ============================================================
# A* 탐색 관련 함수
# ============================================================

def neighbors_8dir(r, c):
    """
    (보조 함수) 현재 셀 (r, c) 기준으로 8방향 이웃 좌표를 반환합니다.
    - 역할: 상하좌우 및 대각선 방향의 모든 인접 칸을 탐색 후보로 제공합니다.
    - 매개변수: r(int) 행 인덱스, c(int) 열 인덱스
    - 반환값: list[tuple[int,int]] 이웃 좌표 리스트
    """
    return [
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)
    ]


def diagonal_heuristic(a, b):
    """
    (휴리스틱 함수) 8방향 격자에서 사용할 Octile distance를 계산합니다.
    - 역할: A*의 h(n)으로 사용되며, 대각 이동이 가능한 격자에서 admissible(낙관적)한 추정치를 제공합니다.
    - 매개변수: a(tuple[int,int]), b(tuple[int,int]) 비교할 두 좌표(행, 열)
    - 반환값: float 휴리스틱 값
    """
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)


def reconstruct_path(came_from, current):
    """
    (경로 복원) 목표 노드에서 부모 포인터를 따라가며 경로를 재구성합니다.
    - 역할: A*가 목표에 도달한 뒤 시작→목표 순서의 최종 경로를 생성합니다.
    - 매개변수: came_from(dict[tuple,tuple]) 부모 노드 매핑, current(tuple) 도착 노드
    - 반환값: list[tuple[int,int]] 시작에서 목표까지의 좌표 시퀀스
    """
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return path[::-1]


def a_star_8dir_no_corner_cut(grid, start, goal):
    """
    (핵심) 8방향 A* 탐색 알고리즘 구현 (코너 끼기 방지).
    - 역할: 0/1 격자에서 start→goal 최단 경로를 찾습니다.
    - 제약: 대각 이동 시 인접한 두 직교 칸이 모두 빈칸(0)일 때만 허용(코너 끼기 금지).
    - 매개변수:
        grid(np.ndarray): 0=빈칸, 1=장애물인 (H,W) 격자
        start(tuple[int,int]): 시작 좌표 (row, col)
        goal(tuple[int,int]): 목표 좌표 (row, col)
    - 반환값: list[tuple[int,int]] | None  (경로 또는 없음)
    """
    n_rows, n_cols = grid.shape

    def in_bounds(r, c):
        return 0 <= r < n_rows and 0 <= c < n_cols

    def walkable(r, c):
        return in_bounds(r, c) and grid[r, c] == 0

    if not walkable(*start) or not walkable(*goal):
        return None

    import heapq
    g_score = {start: 0.0}
    f_start = diagonal_heuristic(start, goal)
    open_heap = [(f_start, 0.0, start)]
    came_from = {}
    closed = set()

    while open_heap:
        f, g, cur = heapq.heappop(open_heap)
        if cur in closed:
            continue
        closed.add(cur)

        if cur == goal:
            return reconstruct_path(came_from, cur)

        cr, cc = cur
        for nr, nc in neighbors_8dir(cr, cc):
            if not in_bounds(nr, nc) or grid[nr, nc] == 1:
                continue

            dr = nr - cr
            dc = nc - cc

            if abs(dr) == 1 and abs(dc) == 1:
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:
                    continue
                step_cost = math.sqrt(2)
            else:
                step_cost = 1.0

            nxt = (nr, nc)
            tentative_g = g + step_cost

            if nxt in closed and tentative_g >= g_score.get(nxt, float('inf')):
                continue

            if tentative_g < g_score.get(nxt, float('inf')):
                came_from[nxt] = cur
                g_score[nxt] = tentative_g
                f_new = tentative_g + diagonal_heuristic(nxt, goal)
                heapq.heappush(open_heap, (f_new, tentative_g, nxt))

    return None

# ============================================================
# 미로형 장애물 생성 함수
# ============================================================

def generate_coarse_maze(H, W, rng):
    """
    (미로 생성) Prim 알고리즘 변형으로 작은(coarse) 격자의 미로(0=길, 1=벽)를 생성합니다.
    - 역할: 전체 벽에서 시작해 무작위로 벽을 허물며 길을 확장, 미로 형태를 만듭니다.
    - 매개변수:
        H(int), W(int): coarse 격자 크기(홀수 권장, 내부에서 홀수로 보정)
        rng(random.Random): 재현성 있는 난수 발생기
    - 반환값: np.ndarray shape=(H,W), dtype=uint8  (0=길, 1=벽)
    """
    H = max(3, H | 1)
    W = max(3, W | 1)
    maze = np.ones((H, W), dtype=np.uint8)
    sr, sc = 1, 1
    maze[sr, sc] = 0

    walls = []

    def add_walls(r, c):
        for dr, dc in [(-2,0),(2,0),(0,-2),(0,2)]:
            nr, nc = r+dr, c+dc
            if 0 <= nr < H and 0 <= nc < W and maze[nr, nc] == 1:
                walls.append((nr, nc, r, c))

    add_walls(sr, sc)

    while walls:
        idx = rng.randrange(len(walls))
        wr, wc, pr, pc = walls.pop(idx)
        mr, mc = (wr+pr)//2, (wc+pc)//2
        if maze[wr, wc] == 1:
            maze[wr, wc] = 0
            maze[mr, mc] = 0
            add_walls(wr, wc)

    return maze


def make_maze_obstacles_grid(n, obstacle_ratio=0.4, seed=123, block_size=6, clear_margin=1):
    """
    (최종 격자 생성) coarse 미로를 확대/보정하여 A* 탐색용 n×n 격자를 만듭니다.
    - 역할: 작은 미로를 block_size배로 확장, 중앙 크롭/패딩, 테두리 확보, 목표 벽 비율로 보정.
    - 매개변수:
        n(int): 최종 격자 한 변 길이
        obstacle_ratio(float): 목표 벽 비율(0~1)
        seed(int): 난수 시드(재현성)
        block_size(int): 확대 배율(벽 두께 조절)
        clear_margin(int): 테두리 여백(시작/종료 보장)
    - 반환값: np.ndarray shape=(n,n), dtype=uint8  (0=빈칸, 1=벽)
    """
    rng = random.Random(seed)
    Hc = max(3, (n // block_size) | 1)
    Wc = max(3, (n // block_size) | 1)

    coarse = generate_coarse_maze(Hc, Wc, rng)
    fine = np.kron(coarse, np.ones((block_size, block_size), dtype=np.uint8))

    Hf, Wf = fine.shape
    if Hf < n or Wf < n:
        pad_r = max(0, n - Hf)
        pad_c = max(0, n - Wf)
        fine = np.pad(
            fine,
            ((pad_r//2, pad_r - pad_r//2), (pad_c//2, pad_c - pad_c//2)),
            mode="edge"
        )

    sr = (fine.shape[0] - n)//2
    sc = (fine.shape[1] - n)//2
    grid = fine[sr:sr+n, sc:sc+n].copy()

    grid[:clear_margin, :] = 0
    grid[:, :clear_margin] = 0
    grid[-clear_margin:, :] = 0
    grid[:, -clear_margin:] = 0
    grid[0, 0] = 0
    grid[n-1, n-1] = 0

    cur_ratio = grid.mean()
    target = obstacle_ratio
    rng_np = np.random.default_rng(seed + 999)

    if cur_ratio > target:
        wall_pos = np.argwhere(grid == 1)
        need = int((cur_ratio - target) * n * n)
        if need > 0 and len(wall_pos) > 0:
            idx = rng_np.choice(len(wall_pos), size=min(need, len(wall_pos)), replace=False)
            for r, c in wall_pos[idx]:
                grid[r, c] = 0
    elif cur_ratio < target:
        free_pos = np.argwhere(grid == 0)
        need = int((target - cur_ratio) * n * n)
        if need > 0 and len(free_pos) > 0:
            idx = rng_np.choice(len(free_pos), size=min(need, len(free_pos)), replace=False)
            for r, c in free_pos[idx]:
                grid[r, c] = 1
        grid[0, 0] = 0
        grid[n-1, n-1] = 0

    return grid

# ============================================================
# 실행 / 벤치마크 및 시각화
# ============================================================

if __name__ == "__main__":
    # ============================================================
    # 메인 실행부(Main): 실험 설정 → 벤치마크 반복 실행 → 결과 저장/시각화
    # ※ 함수/메서드 정의부는 그대로 두고, 메인 흐름만 상세 설명을 덧붙였습니다.
    # ============================================================

    # (1) 실험 설정값 ---------------------------------------------------------
    # n_values        : 테스트할 격자 한 변의 길이 목록(큰→작은 순).
    # obstacle_ratio  : 최종 격자에서 벽(1)의 목표 비율. 값이 클수록 길이 좁아지고 난이도가 증가.
    # base_seed       : 난수 시드의 기준값. n과 trial 인덱스에 따라 파생 시드를 만들어 재현성 보장.
    # trials_per_n    : 각 n에 대해 몇 번 반복(trial)하여 평균을 낼지.
    # block_size      : coarse 미로를 확대할 스케일. 클수록 벽이 굵고 통로가 넓어짐.
    # clear_margin    : 격자 가장자리에서 비워둘 여백(셀 단위). 시작/종료가 막히는 상황을 방지.
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]
    obstacle_ratio = 0.20
    base_seed = 12345
    trials_per_n = 10
    block_size = 4
    clear_margin = 1

    # (2) 통계 수집 컨테이너 --------------------------------------------------
    # avg_time_ms           : n별 평균 A* 실행시간(ms).
    # avg_path_len_success  : n별 성공한 경우에만 집계한 평균 경로 길이(스텝 수).
    # success_counts        : n별 성공(trial에서 경로가 존재한 횟수).
    # sample_records        : n별 첫 번째 trial의 샘플(시각화용) 데이터를 저장.
    avg_time_ms = []
    avg_path_len_success = []
    success_counts = []
    sample_records = []

    # csv_rows : CSV로 저장할 표 형태 데이터의 헤더를 먼저 정의.
    csv_rows = [("n", "trials", "success", "avg_time_ms", "avg_path_len_success")]

    # (3) n 값 루프 -----------------------------------------------------------
    # 각 격자 크기(n)에 대해 동일한 실험을 반복하여 성능/성공률/경로 길이를 확인.
    for n in n_values:
        start = (n-1, n-1)
        goal = (0, 0)
        times = []
        path_lens = []
        success = 0
        sample_saved = False

        for t in range(trials_per_n):
            seed = base_seed + n*1000 + t
            grid = make_maze_obstacles_grid(
                n,
                obstacle_ratio=obstacle_ratio,
                seed=seed,
                block_size=block_size,
                clear_margin=clear_margin
            )

            t0 = time.perf_counter()
            path = a_star_8dir_no_corner_cut(grid, start, goal)
            t1 = time.perf_counter()
            dt_ms = (t1 - t0) * 1000.0
            times.append(dt_ms)

            if path is not None:
                success += 1
                path_lens.append(len(path))

            if not sample_saved:
                # 주: 여기선 간단히 튜플 저장, 실제 위 버전에선 dict 사용 가능
                sample_records.append((n, grid, path, path is not None, dt_ms))
                sample_saved = True

        mean_time = float(np.mean(times)) if times else 0.0
        mean_path_len = float(np.mean(path_lens)) if path_lens else 0.0

        avg_time_ms.append(mean_time)
        avg_path_len_success.append(mean_path_len)
        success_counts.append(success)

        print(
            f"n={n:>3} | trials={trials_per_n} | success={success:<2} | "
            f"avg_time={mean_time:.2f} ms | avg_path_len_success={mean_path_len:.1f}"
        )

        csv_rows.append((n, trials_per_n, success, round(mean_time, 4), round(mean_path_len, 2)))

    csv_path = "benchmark_results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(csv_rows)
    print(f"[saved] {csv_path}")

    # 시각화 파트(간소 버전). 필요시 이전 상세 버전으로 되돌릴 수 있습니다.
    fig = plt.figure(figsize=(8, max(6, len(n_values)*0.35)))
    y_pos = np.arange(len(n_values))
    plt.barh(y_pos, avg_time_ms)
    plt.yticks(y_pos, [str(n) for n in n_values])
    plt.xlabel("Average A* time (ms)")
    plt.ylabel("Grid size n")
    plt.title("A* 8-dir (no corner cutting) - Avg Runtime by Grid Size")
    mmax = max(avg_time_ms) if avg_time_ms else 0.0
    for i, v in enumerate(avg_time_ms):
        plt.text(v + (mmax * 0.01 if mmax > 0 else 0.02), i, f"{v:.2f} ms", va="center", fontsize=8)
    plt.tight_layout()
    bar_path = "runtime_barh.jpg"
    plt.savefig(bar_path, dpi=180)
    print(f"[saved] {bar_path}")
    plt.show()
    plt.close(fig)