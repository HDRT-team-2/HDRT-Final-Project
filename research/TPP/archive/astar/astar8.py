# astar8_maze_benchmark.py
# 8방향 A* (대각선 비용 sqrt(2), 코너 끼기 방지) + 미로형 장애물
# - n별 경로 탐색, 처리시간 출력
# - 큰 n(>=100)은 개별 Figure, 작은 n(<100)은 서브플롯으로 시각화
# - 처리시간 가로 막대그래프 출력
# - 시작=파랑, 도착=빨강, 경로=초록

import math
import random
import time
import numpy as np
import matplotlib.pyplot as plt

# ---------------------------
# 8-방향 A* (대각선 비용 = sqrt(2), 코너 끼기 방지)
# ---------------------------

def neighbors_8dir(r, c):
    """상하좌우 + 대각선 이웃."""
    return [
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),           # 직선 4방향
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)    # 대각선 4방향
    ]

def octile_distance(a, b):
    """8방향에서 admissible한 휴리스틱(Octile distance)."""
    dx = abs(a[0] - b[0])
    dy = abs(a[1] - b[1])
    return (dx + dy) + (math.sqrt(2) - 2.0) * min(dx, dy)

def reconstruct_path(came_from, current):
    """came_from를 역추적하여 시작→도착 경로 리스트 반환."""
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    return path[::-1]

def a_star_8dir_no_corner_cut(grid, start, goal):
    """
    8방향 A* 탐색.
    - grid: np.array, 0=빈칸, 1=장애물
    - start/goal: (row, col)
    - 규칙: 대각선 이동 시 양 옆 직교 칸이 모두 비어 있어야 함(코너 끼기 방지).
    반환: 경로 리스트[(r,c), ...] 또는 None
    """
    H, W = grid.shape

    def in_bounds(r, c): return 0 <= r < H and 0 <= c < W
    def walkable(r, c):  return in_bounds(r, c) and grid[r, c] == 0

    if not walkable(*start) or not walkable(*goal):
        return None

    import heapq
    g_score = {start: 0.0}
    f0 = octile_distance(start, goal)
    open_heap = [(f0, 0.0, start)]
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
            # ---- 코너 끼기 방지: 대각선 이동 시 옆 직교 칸 2개 모두 비어 있어야 함 ----
            if abs(dr) == 1 and abs(dc) == 1:
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:
                    continue
                step = math.sqrt(2)
            else:
                step = 1.0
            # -------------------------------------------------------------------

            ng = g + step
            if ng >= g_score.get((nr, nc), float("inf")):
                continue

            came_from[(nr, nc)] = cur
            g_score[(nr, nc)] = ng
            heapq.heappush(open_heap, (ng + octile_distance((nr, nc), goal), ng, (nr, nc)))

    return None

# ---------------------------
# 미로형 장애물 생성
# ---------------------------

def _randomized_prims_maze(h, w, rng):
    """
    Randomized Prim's Algorithm로 (h x w) 미로 생성.
    - 벽=1, 길=0
    - (홀수,홀수) 위치로 통로를 뚫어 나가는 전형적 구현
    """
    # 홀수 크기로 강제(미로 핵심은 홀수 격자에서 생성이 자연스러움)
    if h % 2 == 0: h += 1
    if w % 2 == 0: w += 1

    maze = np.ones((h, w), dtype=np.uint8)
    sr, sc = 1, 1
    maze[sr, sc] = 0

    frontier = []
    def add_frontier(r, c):
        for dr, dc in [(-2,0),(2,0),(0,-2),(0,2)]:
            nr, nc = r + dr, c + dc
            if 1 <= nr < h-1 and 1 <= nc < w-1 and maze[nr, nc] == 1:
                frontier.append((nr, nc, r, c))

    add_frontier(sr, sc)

    while frontier:
        idx = rng.randrange(len(frontier))
        r, c, pr, pc = frontier.pop(idx)
        if maze[r, c] == 1:
            # parent와 현재 사이 벽 제거
            maze[(r+pr)//2, (c+pc)//2] = 0
            maze[r, c] = 0
            add_frontier(r, c)

    return maze  # 1=벽, 0=길

def make_maze_obstacles_grid(n, obstacle_ratio=0.2, seed=None, clear_margin=1):
    """
    n x n 그리드에 '미로형 장애물'을 배치.
    - 내부적으로 큰 미로를 만든 다음, n 크기에 맞도록 '균등 샘플링'으로 축소
    - 결과: 0=빈칸, 1=장애물
    - obstacle_ratio는 '대략적' 목표(미로 성격상 정확히 맞추지 않을 수 있음)
    - start=(n-1,n-1), goal=(0,0)은 항상 비워두고, 가장자리 여유(clear_margin)도 0으로 정리
    """
    rng = random.Random(seed)

    if n <= 0:
        return np.zeros((n, n), dtype=np.uint8)

    # (1) 큰 미로 생성(스케일업)
    scale = 7  # 클수록 복잡/부드러운 패턴
    H_big = max(5, n * scale + 1)  # 홀수 보장
    W_big = max(5, n * scale + 1)
    big_maze = _randomized_prims_maze(H_big, W_big, rng)  # 1=벽, 0=길

    # (2) 균등 샘플링으로 n x n 축소  (np.ix_ 주의: 언더바 1개!)
    rows = np.linspace(0, H_big - 1, n).astype(int)
    cols = np.linspace(0, W_big - 1, n).astype(int)
    sampled = big_maze[np.ix_(rows, cols)]  # ← 여기 오타가 자주 남(np.ix_)

    grid = sampled.copy().astype(np.uint8)

    # (3) 가장자리/시작/도착 여유 공간 확보
    grid[:clear_margin, :] = 0
    grid[-clear_margin:, :] = 0
    grid[:, :clear_margin] = 0
    grid[:, -clear_margin:] = 0

    # (4) 시작/도착 보장
    grid[0, 0] = 0
    grid[n-1, n-1] = 0

    # (5) 장애물 비율이 너무 높을 경우 일부 벽을 랜덤으로 제거하여 완화(옵션)
    current_ratio = grid.mean()  # 1의 비율
    if current_ratio > obstacle_ratio:
        want_remove = int((current_ratio - obstacle_ratio) * n * n)
        wall_positions = [(r, c) for r in range(n) for c in range(n) if grid[r, c] == 1]
        rng.shuffle(wall_positions)
        removed = 0
        for r, c in wall_positions:
            if removed >= want_remove:
                break
            # 시작/도착/가장자리 여유 침해 금지
            if (r, c) in [(0, 0), (n-1, n-1)]:
                continue
            if r < clear_margin or r >= n - clear_margin or c < clear_margin or c >= n - clear_margin:
                continue
            grid[r, c] = 0
            removed += 1

    # 최종 안전 보장
    grid[0, 0] = 0
    grid[n-1, n-1] = 0
    return grid  # 0=빈칸, 1=장애물

# ---------------------------
# 메인: 여러 n에 대해 실행 & 시각화
# ---------------------------

if __name__ == "__main__":
    # n 목록(큰 것부터 작은 것까지)
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]

    # 미로형 장애물의 대략적 비율(요청: 0.2에서 원하는 모양이 잘 나왔다고 함)
    obstacle_ratio = 0.20
    base_seed = 12345   # 재현성용 시드
    clear_margin = 1    # 테두리 여유(1~2 정도 권장)

    timings_ms = []
    results = []  # (n, found, path_len or False, grid, start, goal, path or None)

    # --- 각 n에 대해 경로 탐색 & 시간 측정 ---
    for n in n_values:
        start = (n - 1, n - 1)
        goal = (0, 0)

        grid = make_maze_obstacles_grid(
            n,
            obstacle_ratio=obstacle_ratio,
            seed=base_seed + n,
            clear_margin=clear_margin
        )

        t0 = time.perf_counter()
        path = a_star_8dir_no_corner_cut(grid, start, goal)
        t1 = time.perf_counter()
        elapsed_ms = (t1 - t0) * 1000.0

        timings_ms.append(elapsed_ms)

        if path is None:
            results.append((n, False, False, grid, start, goal, None))
            print(f"n={n:>3} | found=False | path_len=False | time={elapsed_ms:.2f} ms")
        else:
            results.append((n, True, len(path), grid, start, goal, path))
            print(f"n={n:>3} | found=True  | path_len={len(path)} | time={elapsed_ms:.2f} ms")

    # --- 격자 시각화: 큰 n 개별, 작은 n 서브플롯 ---
    big_ns = [n for n in n_values if n >= 100]
    small_ns = [n for n in n_values if n < 100]

    # 큰 격자(>=100): 각 n 별로 개별 figure
    for n in big_ns:
        rec = next(r for r in results if r[0] == n)
        found, path_len, grid, start, goal, path = rec[1], rec[2], rec[3], rec[4], rec[5], rec[6]
        time_ms = timings_ms[n_values.index(n)]

        plt.figure(figsize=(6.5, 6.5))
        plt.title(
            f"Grid {n}x{n} | obstacles≈{int(grid.mean()*n*n)} | "
            f"path_len={path_len if found else 'False'} | time={time_ms:.2f} ms"
        )
        plt.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
        # 시작(파랑), 도착(빨강)
        plt.scatter([start[1]], [start[0]], s=36, c="blue", marker="s", label="Start")
        plt.scatter([goal[1]], [goal[0]], s=36, c="red", marker="s", label="Goal")
        # 경로(초록)
        if found and path:
            ys = [r for r, c in path]
            xs = [c for r, c in path]
            plt.plot(xs, ys, linewidth=1.4, c="green")
        plt.legend(loc="upper right")
        plt.tight_layout()

    # 작은 격자(<100): 서브플롯 배치(보기에 적당한 cols=4)
    if small_ns:
        cols = 4
        rows = int(math.ceil(len(small_ns) / cols))
        plt.figure(figsize=(4.2*cols, 4.2*rows))
        for idx, n in enumerate(small_ns, 1):
            rec = next(r for r in results if r[0] == n)
            found, path_len, grid, start, goal, path = rec[1], rec[2], rec[3], rec[4], rec[5], rec[6]
            time_ms = timings_ms[n_values.index(n)]

            ax = plt.subplot(rows, cols, idx)
            ax.set_title(f"n={n} | len={path_len if found else 'False'}\n{time_ms:.2f} ms", fontsize=10)
            ax.imshow(grid, cmap="gray_r", origin="upper", interpolation="nearest")
            ax.scatter([start[1]], [start[0]], s=28, c="blue", marker="s")
            ax.scatter([goal[1]], [goal[0]], s=28, c="red", marker="s")
            if found and path:
                ys = [r for r, c in path]
                xs = [c for r, c in path]
                ax.plot(xs, ys, linewidth=1.2, c="green")
            ax.set_xticks([])
            ax.set_yticks([])
        plt.tight_layout()

    # --- 처리시간 가로 막대그래프 (x=시간, y=n) ---
    plt.figure(figsize=(8, max(6, len(n_values)*0.35)))
    y_pos = np.arange(len(n_values))
    plt.barh(y_pos, timings_ms)
    plt.yticks(y_pos, [str(n) for n in n_values])
    plt.xlabel("A* time (ms)")
    plt.ylabel("Grid size n")
    plt.title("A* 8-dir (no corner cutting) on Maze-like Obstacles")
    for i, v in enumerate(timings_ms):
        plt.text(v + (max(timings_ms) * 0.01 if max(timings_ms) > 0 else 0.02),
                 i, f"{v:.2f} ms", va="center", fontsize=8)
    plt.tight_layout()

    plt.show()
