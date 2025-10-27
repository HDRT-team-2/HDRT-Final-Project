# benchmark_astar_8dir_maze_barh.py
# ------------------------------------------------------------
# 8방향 A* + 미로형 장애물 + 처리시간 벤치마크/시각화 (한국어 주석)
# ------------------------------------------------------------
import math
import random
import time
import numpy as np
import matplotlib.pyplot as plt

# ============================================================
# A* (8방향) 구현부
# - 대각선 이동 비용 = sqrt(2)
# - "코너 끼기" 방지: 대각선 이동 시 인접 직교 칸 2개 모두가 비어 있어야 함
# - 휴리스틱: Octile distance (8방향에서 admissible)
# ============================================================

def neighbors_8dir(r, c):
    """현재 칸 (r,c)의 8방향 이웃 반환 (상하좌우 + 대각선)"""
    return [
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),           # 상하좌우
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)    # 대각선
    ]

def octile(a, b):
    """Octile distance: 8방향에서 사용하는 허용적(admissible) 휴리스틱"""
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)

def reconstruct_path(came_from, current):
    """부모 포인터(came_from)를 따라 경로 복원 (시작→도착 순서 리스트 반환)"""
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return path[::-1]

def a_star_8dir_no_corner_cut(grid, start, goal):
    """
    A* 8방향 구현 (코너 끼기 방지)
    grid: np.ndarray(uint8) 0=통과, 1=장애물
    start/goal: (row, col)
    """
    H, W = grid.shape

    def in_bounds(r, c): return 0 <= r < H and 0 <= c < W
    def walkable(r, c):  return in_bounds(r, c) and grid[r, c] == 0

    if not walkable(*start) or not walkable(*goal):
        return None

    import heapq
    g_score = {start: 0.0}
    open_heap = [(octile(start, goal), 0.0, start)]  # (f=g+h, g, node)
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

            dr, dc = nr - cr, nc - cc
            # ----- 코너 끼기 방지 -----
            if abs(dr) == 1 and abs(dc) == 1:  # 대각선 이동
                # 대각선 방향으로 끼워 들어가면 안 됨: 두 직교 이웃이 모두 비어 있어야 함
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:
                    continue
                step_cost = math.sqrt(2)
            else:
                step_cost = 1.0
            # ------------------------

            tentative_g = g + step_cost
            if tentative_g >= g_score.get((nr, nc), float("inf")):
                continue

            came_from[(nr, nc)] = cur
            g_score[(nr, nc)] = tentative_g
            f_new = tentative_g + octile((nr, nc), goal)
            heapq.heappush(open_heap, (f_new, tentative_g, (nr, nc)))

    return None  # 경로 없음

# ============================================================
# 미로형 장애물 생성
# - DFS로 "완전미로(perfect maze)" 코어 생성(홀수 크기)
# - n과 크기 맞추기: 최근접 스케일(크론) + 중앙 크롭
# - 도어(구멍) 추가로 난이도 조절, 잡음 벽으로 다양성 추가
# - 시작/도착 주변 clear_margin 만큼 비우기
# ============================================================

def largest_odd_leq(x):
    """x 이하 최대 홀수값 반환 (최소 3 보장)"""
    v = int(x)
    if v < 3: 
        return 3
    if v % 2 == 0:
        v -= 1
    return max(3, v)

def generate_perfect_maze_odd(M, seed=None):
    """
    홀수 MxM 완전미로 생성 (1=벽, 0=길)
    - 격자 전체를 벽(1)으로 채우고, 홀수 좌표를 셀로 보고 2칸씩 이동하며 벽을 허무는 DFS
    """
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random

    maze = np.ones((M, M), dtype=np.uint8)
    # 방문 가능한 셀 좌표(홀수,홀수) 중 하나를 시작점으로
    start_r = rng.randrange(1, M, 2)
    start_c = rng.randrange(1, M, 2)
    maze[start_r, start_c] = 0

    stack = [(start_r, start_c)]
    # 2칸 이동 방향(상하좌우)
    dirs = [(-2, 0), (2, 0), (0, -2), (0, 2)]

    while stack:
        r, c = stack[-1]
        rng.shuffle(dirs)
        carved = False
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            if 1 <= nr < M-1 and 1 <= nc < M-1 and maze[nr, nc] == 1:
                # 중간 벽 허물기
                maze[r + dr//2, c + dc//2] = 0
                maze[nr, nc] = 0
                stack.append((nr, nc))
                carved = True
                break
        if not carved:
            stack.pop()

    return maze  # 0=길(통과), 1=벽(장애물)

def punch_random_doors(grid, fraction=0.15, seed=None):
    """
    벽(1) 중 일부를 랜덤으로 허물어 길(0)로 만들어 '지나갈 구멍'을 만든다.
    fraction: 전체 벽 수 대비 비율 (0.0 ~ 1.0)
    """
    if fraction <= 0:
        return grid
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random

    H, W = grid.shape
    wall_positions = [(r, c) for r in range(H) for c in range(W) if grid[r, c] == 1]
    k = int(len(wall_positions) * fraction)
    for (r, c) in rng.sample(wall_positions, k=min(k, len(wall_positions))):
        grid[r, c] = 0
    return grid

def add_salt_pepper_walls(grid, ratio=0.02, seed=None):
    """
    빈 칸(0) 중 일부를 벽(1)로 바꿔 '지뢰밭 느낌의 잡음'을 약간 추가
    ratio: 전체 칸 대비 비율
    """
    if ratio <= 0:
        return grid
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random

    H, W = grid.shape
    free_positions = [(r, c) for r in range(H) for c in range(W) if grid[r, c] == 0]
    k = int(H * W * ratio)
    for (r, c) in rng.sample(free_positions, k=min(k, len(free_positions))):
        grid[r, c] = 1
    return grid

def fit_to_n(maze_core, n):
    """
    미로 코어(odd x odd)를 목표 크기 n x n에 맞추는 함수
    - 스케일 인자 s = ceil(n / M) 로 크론(최근접 이웃) 확대
    - 중앙을 n x n으로 크롭하여 반환
    """
    M = maze_core.shape[0]
    s = max(1, int(np.ceil(n / M)))
    up = np.kron(maze_core, np.ones((s, s), dtype=np.uint8))  # 최근접 확장
    H, W = up.shape
    # 중앙 크롭 (H,W >= n 보장)
    rs = (H - n) // 2
    cs = (W - n) // 2
    return up[rs:rs + n, cs:cs + n].copy()

def make_maze_obstacles_grid(
    n,
    door_fraction=0.20,     # 벽 중 도어로 뚫을 비율 (0.0 ~ 1.0) -> 값이 클수록 쉬워짐
    noise_ratio=0.00,       # 길 중 일부를 벽으로 바꿔 잡음 추가 (0.0 ~ 0.2 정도 추천)
    clear_margin=2,         # 시작/도착 주변을 비울 여백(맨해튼 반경이 아닌 정사각형 패치)
    seed=None
):
    """
    n x n 미로 기반 장애물 그리드 생성 (0=통과, 1=장애물)
    1) 홀수 크기 M으로 완전미로 생성
    2) 최근접 스케일로 확대 후 중앙 크롭하여 n에 맞춤
    3) 도어/잡음으로 난이도 및 모양 다양화
    4) start/goal 및 주변 clear_margin 만큼 비우기
    """
    # 1) 미로 코어 생성 (홀수)
    #    n이 작아도 최소 3x3은 보장
    M = largest_odd_leq(max(3, n // 2 * 2 + 1))  # n/2보다 약간 큰 홀수로 생성 → 스케일 여유
    maze_core = generate_perfect_maze_odd(M, seed=seed)  # 0=길, 1=벽

    # 2) n 크기에 맞게 스케일링 후 중앙 크롭
    grid = fit_to_n(maze_core, n)  # 0=길, 1=벽

    # 3) 도어/잡음으로 난이도/다양성 조절
    grid = punch_random_doors(grid, fraction=door_fraction, seed=seed)
    grid = add_salt_pepper_walls(grid, ratio=noise_ratio, seed=seed)

    # 4) 시작/도착 및 주변 clear_margin 만큼 비우기
    grid[0:clear_margin+1, 0:clear_margin+1] = 0                 # goal 주변
    grid[n-1-clear_margin:n, n-1-clear_margin:n] = 0             # start 주변
    # 정확히 start/goal 위치도 비워두기
    grid[0, 0] = 0
    grid[n-1, n-1] = 0
    return grid

# ============================================================
# 메인: 여러 n에 대해 실행 & 시각화
# - 큰 격자(>=100)는 개별 Figure
# - 작은 격자(<100)는 Subplot으로 모아보기
# - 마지막 처리시간 가로 막대그래프 (x=시간, y=n)
# ============================================================

if __name__ == "__main__":
    # 실험할 그리드 크기들
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]

    # 미로/난이도 파라미터 (원하는 모양 나오면 여기만 조절)
    door_fraction = 0.30   # 벽의 30%를 추가 개구부로 뚫어 복잡도 완화
    noise_ratio   = 0.02   # 길 일부를 벽으로 변환해 지저분함(지뢰밭 느낌) 약간 추가
    clear_margin  = 2      # 시작/도착 주변 여유
    base_seed     = 12345  # 재현성 위해 n마다 base_seed+n 사용

    timings_ms = []
    results = []  # (n, found, path_len/False, grid, start, goal, [path or None])

    # ---------- 각 n에 대해 미로 생성 → A* → 시간 측정 ----------
    for n in n_values:
        start = (n-1, n-1)  # 우하단
        goal  = (0, 0)      # 좌상단

        grid = make_maze_obstacles_grid(
            n,
            door_fraction=door_fraction,
            noise_ratio=noise_ratio,
            clear_margin=clear_margin,
            seed=base_seed + n
        )

        t0 = time.perf_counter()
        path = a_star_8dir_no_corner_cut(grid, start, goal)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0

        timings_ms.append(elapsed_ms)
        if path is None:
            results.append((n, False, False, grid, start, goal, None))
        else:
            results.append((n, True, len(path), grid, start, goal, path))

    # ---------- 시각화: 큰 n 개별, 작은 n 한 장에 ----------
    big_ns = [n for n in n_values if n >= 100]
    small_ns = [n for n in n_values if n < 100]

    # 큰 격자(>=100): 각자 크게 보기
    for n in big_ns:
        rec = next(r for r in results if r[0] == n)
        found, path_len, grid, start, goal, path = rec[1], rec[2], rec[3], rec[4], rec[5], rec[6]
        time_ms = timings_ms[n_values.index(n)]

        plt.figure(figsize=(7, 7))
        plt.title(f"Grid {n}x{n} | obstacles≈{int(np.sum(grid==1))} | "
                  f"path_len={path_len if found else 'False'} | time={time_ms:.2f} ms")
        plt.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
        # 시작(파랑), 도착(빨강)
        plt.scatter([start[1]], [start[0]], s=40, c="blue", marker="s", label="Start")
        plt.scatter([goal[1]], [goal[0]], s=40, c="red",  marker="s", label="Goal")
        # 경로(초록)
        if found and path:
            ys = [r for r, c in path]
            xs = [c for r, c in path]
            plt.plot(xs, ys, linewidth=1.6, c="green")
        plt.legend(loc="upper right")
        plt.tight_layout()

    # 작은 격자(<100): Subplot으로 모아보기
    if small_ns:
        cols = 4
        rows = int(math.ceil(len(small_ns) / cols))
        plt.figure(figsize=(4*cols, 4*rows))
        for idx, n in enumerate(small_ns, 1):
            rec = next(r for r in results if r[0] == n)
            found, path_len, grid, start, goal, path = rec[1], rec[2], rec[3], rec[4], rec[5], rec[6]
            time_ms = timings_ms[n_values.index(n)]

            ax = plt.subplot(rows, cols, idx)
            ax.set_title(f"n={n} | len={path_len if found else 'False'}\n{time_ms:.2f} ms", fontsize=10)
            ax.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
            ax.scatter([start[1]], [start[0]], s=30, c="blue", marker="s")
            ax.scatter([goal[1]], [goal[0]], s=30, c="red",  marker="s")
            if found and path:
                ys = [r for r, c in path]
                xs = [c for r, c in path]
                ax.plot(xs, ys, linewidth=1.3, c="green")
            ax.set_xticks([])
            ax.set_yticks([])
        plt.tight_layout()

    # ---------- 처리시간 가로 막대그래프 (x=시간, y=n) ----------
    plt.figure(figsize=(8, max(6, len(n_values)*0.35)))
    y_pos = np.arange(len(n_values))
    plt.barh(y_pos, timings_ms)
    plt.yticks(y_pos, [str(n) for n in n_values])
    plt.xlabel("A* time (ms)")
    plt.ylabel("Grid size n")
    plt.title("A* 8-dir (no-corner-cut) Runtime by Grid Size (Maze Obstacles)")
    # 막대 옆에 수치 표시
    mx = max(timings_ms) if timings_ms else 0.0
    for i, v in enumerate(timings_ms):
        plt.text(v + (mx * 0.01 if mx > 0 else 0.02), i, f"{v:.2f} ms", va="center", fontsize=8)
    plt.tight_layout()

    plt.show()

