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

import math  # 수학 상수/함수 사용 (sqrt 등)
import random  # 재현성 있는 난수 시드/생성
import time  # 실행 시간 측정
import csv  # 결과 CSV 저장
import numpy as np  # 수치 연산/배열
import matplotlib.pyplot as plt  # 시각화

# ============================================================
# A* 탐색 관련 함수
# ============================================================

def neighbors_8dir(r, c):  # 8방향 이웃 좌표 생성 유틸
    """
    (보조 함수) 현재 셀 (r, c) 기준으로 8방향 이웃 좌표를 반환합니다.
    - 역할: 상하좌우 및 대각선 방향의 모든 인접 칸을 탐색 후보로 제공합니다.
    - 매개변수: r(int) 행 인덱스, c(int) 열 인덱스
    - 반환값: list[tuple[int,int]] 이웃 좌표 리스트
    """
    return [
        (r-1, c), (r+1, c), (r, c-1), (r, c+1),  # 직교 4방향
        (r-1, c-1), (r-1, c+1), (r+1, c-1), (r+1, c+1)  # 대각 4방향
    ]


def diagonal_heuristic(a, b):  # Octile distance(8방향용) 휴리스틱
    """
    (휴리스틱 함수) 8방향 격자에서 사용할 Octile distance를 계산합니다.
    - 역할: A*의 h(n)으로 사용되며, 대각 이동이 가능한 격자에서 admissible(낙관적)한 추정치를 제공합니다.
    - 매개변수: a(tuple[int,int]), b(tuple[int,int]) 비교할 두 좌표(행, 열)
    - 반환값: float 휴리스틱 값
    """
    dx = abs(a[0] - b[0])  # 행 차이(|dr|)
    dy = abs(a[1] - b[1])  # 열 차이(|dc|)
    return (dx + dy) + (math.sqrt(2) - 2) * min(dx, dy)  # Octile 공식


def reconstruct_path(came_from, current):  # 부모 포인터 따라 경로 복원
    """
    (경로 복원) 목표 노드에서 부모 포인터를 따라가며 경로를 재구성합니다.
    - 역할: A*가 목표에 도달한 뒤 시작→목표 순서의 최종 경로를 생성합니다.
    - 매개변수: came_from(dict[tuple,tuple]) 부모 노드 매핑, current(tuple) 도착 노드
    - 반환값: list[tuple[int,int]] 시작에서 목표까지의 좌표 시퀀스
    """
    path = [current]  # 도착 노드부터 시작
    while current in came_from:  # 시작 노드까지 역추적
        current = came_from[current]
        path.append(current)
    return path[::-1]  # 정방향(시작→도착)으로 뒤집기


def a_star_8dir_no_corner_cut(grid, start, goal):  # 코너 끼기 방지 8방향 A*
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
    n_rows, n_cols = grid.shape  # 격자 크기(행, 열)

    def in_bounds(r, c):  # 좌표 유효성 검사 람다
        return 0 <= r < n_rows and 0 <= c < n_cols

    def walkable(r, c):  # 통행 가능(0) 여부
        return in_bounds(r, c) and grid[r, c] == 0

    if not walkable(*start) or not walkable(*goal):  # 시작/목표 유효성
        return None

    import heapq  # 우선순위 큐(최소 힙)
    g_score = {start: 0.0}  # 시작 g=0
    f_start = diagonal_heuristic(start, goal)  # 시작 f=h(start)
    open_heap = [(f_start, 0.0, start)]  # (f, g, node) 튜플 저장
    came_from = {}  # 자식→부모 포인터
    closed = set()  # 방문 확정 집합

    while open_heap:  # 탐색 루프
        f, g, cur = heapq.heappop(open_heap)  # f 최소 노드 pop
        if cur in closed:  # 이미 확정된 노드 스킵
            continue
        closed.add(cur)

        if cur == goal:  # 목표 도달 시 경로 복원
            return reconstruct_path(came_from, cur)

        cr, cc = cur  # 현재 좌표 언패킹
        for nr, nc in neighbors_8dir(cr, cc):  # 8방향 이웃 순회
            if not in_bounds(nr, nc) or grid[nr, nc] == 1:  # 격자 밖/벽 차단
                continue

            dr = nr - cr  # 행 변화량
            dc = nc - cc  # 열 변화량

            # 대각선 이동 시 코너 끼기 방지: 인접 직교 2칸이 모두 비어야 함
            if abs(dr) == 1 and abs(dc) == 1:
                if grid[cr + dr, cc] == 1 or grid[cr, cc + dc] == 1:
                    continue
                step_cost = math.sqrt(2)  # 대각 비용 √2
            else:
                step_cost = 1.0  # 직교 비용 1

            nxt = (nr, nc)  # 다음 노드 좌표
            tentative_g = g + step_cost  # 후보 g값

            if nxt in closed and tentative_g >= g_score.get(nxt, float('inf')):
                continue  # 더 나쁜 경로면 스킵

            if tentative_g < g_score.get(nxt, float('inf')):  # 더 좋은 경로 발견
                came_from[nxt] = cur  # 부모 갱신
                g_score[nxt] = tentative_g
                f_new = tentative_g + diagonal_heuristic(nxt, goal)  # f=g+h
                heapq.heappush(open_heap, (f_new, tentative_g, nxt))  # 큐 삽입

    return None  # 경로 없음

# ============================================================
# 미로형 장애물 생성 함수
# ============================================================

def generate_coarse_maze(H, W, rng):  # Prim 변형으로 coarse 미로 생성
    """
    (미로 생성) Prim 알고리즘 변형으로 작은(coarse) 격자의 미로(0=길, 1=벽)를 생성합니다.
    - 역할: 전체 벽에서 시작해 무작위로 벽을 허물며 길을 확장, 미로 형태를 만듭니다.
    - 매개변수:
        H(int), W(int): coarse 격자 크기(홀수 권장, 내부에서 홀수로 보정)
        rng(random.Random): 재현성 있는 난수 발생기
    - 반환값: np.ndarray shape=(H,W), dtype=uint8  (0=길, 1=벽)
    """
    H = max(3, H | 1)  # 짝수면 |1로 홀수화
    W = max(3, W | 1)  # 최소 3 보장
    maze = np.ones((H, W), dtype=np.uint8)  # 전부 벽(1)로 초기화
    sr, sc = 1, 1  # 시작 셀(홀수 좌표)
    maze[sr, sc] = 0  # 시작은 길(0)

    walls = []  # 후보 벽 리스트 (nr, nc, pr, pc)

    def add_walls(r, c):  # 셀(r,c) 기준 2칸 떨어진 벽을 후보에 추가
        for dr, dc in [(-2,0),(2,0),(0,-2),(0,2)]:
            nr, nc = r+dr, c+dc
            if 0 <= nr < H and 0 <= nc < W and maze[nr, nc] == 1:
                walls.append((nr, nc, r, c))  # 벽 좌표와 부모 셀 저장

    add_walls(sr, sc)  # 초기 이웃 벽 등록

    while walls:  # 벽 리스트 소진될 때까지
        idx = rng.randrange(len(walls))  # 무작위 선택
        wr, wc, pr, pc = walls.pop(idx)  # 벽 좌표/부모 꺼내기
        mr, mc = (wr+pr)//2, (wc+pc)//2  # 중간 벽 셀(허물 대상)
        if maze[wr, wc] == 1:  # 아직 벽이면
            maze[wr, wc] = 0  # 통로로 변경
            maze[mr, mc] = 0  # 중간 벽도 허물기
            add_walls(wr, wc)  # 새 셀에서 확장

    return maze  # 0=길, 1=벽


def make_maze_obstacles_grid(n, obstacle_ratio=0.4, seed=123, block_size=6, clear_margin=1):  # 최종 n×n 격자 생성
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
    rng = random.Random(seed)  # Python Random(미로 선택용)
    Hc = max(3, (n // block_size) | 1)  # coarse 높이(홀수)
    Wc = max(3, (n // block_size) | 1)  # coarse 너비(홀수)

    coarse = generate_coarse_maze(Hc, Wc, rng)  # coarse 미로(0/1)
    fine = np.kron(coarse, np.ones((block_size, block_size), dtype=np.uint8))  # 크론으로 확대

    Hf, Wf = fine.shape  # 확대된 격자 크기
    if Hf < n or Wf < n:  # 부족하면 패딩
        pad_r = max(0, n - Hf)  # 행 패딩 수
        pad_c = max(0, n - Wf)  # 열 패딩 수
        fine = np.pad(
            fine,
            ((pad_r//2, pad_r - pad_r//2), (pad_c//2, pad_c - pad_c//2)),
            mode="edge"  # 가장자리 복제 패딩
        )

    sr = (fine.shape[0] - n)//2  # 중앙 크롭 시작 행
    sc = (fine.shape[1] - n)//2  # 중앙 크롭 시작 열
    grid = fine[sr:sr+n, sc:sc+n].copy()  # 최종 n×n 그리드

    # 테두리 여백 확보 및 시작/도착 보장
    grid[:clear_margin, :] = 0
    grid[:, :clear_margin] = 0
    grid[-clear_margin:, :] = 0
    grid[:, -clear_margin:] = 0
    grid[0, 0] = 0  # goal(0,0) 비우기
    grid[n-1, n-1] = 0  # start(n-1,n-1) 비우기

    cur_ratio = grid.mean()  # 현재 벽 비율(평균)
    target = obstacle_ratio  # 목표 벽 비율
    rng_np = np.random.default_rng(seed + 999)  # NumPy RNG(샘플링용)

    if cur_ratio > target:  # 벽이 너무 많으면 일부 제거
        wall_pos = np.argwhere(grid == 1)  # 벽 좌표 목록
        need = int((cur_ratio - target) * n * n)  # 제거 수 추정
        if need > 0 and len(wall_pos) > 0:
            idx = rng_np.choice(len(wall_pos), size=min(need, len(wall_pos)), replace=False)
            for r, c in wall_pos[idx]:
                grid[r, c] = 0  # 벽→빈칸
    elif cur_ratio < target:  # 벽이 적으면 일부 추가
        free_pos = np.argwhere(grid == 0)  # 빈칸 좌표 목록
        need = int((target - cur_ratio) * n * n)  # 추가 수 추정
        if need > 0 and len(free_pos) > 0:
            idx = rng_np.choice(len(free_pos), size=min(need, len(free_pos)), replace=False)
            for r, c in free_pos[idx]:
                grid[r, c] = 1  # 빈칸→벽
        grid[0, 0] = 0  # goal 보장
        grid[n-1, n-1] = 0  # start 보장

    return grid  # 0=빈칸, 1=벽

# ============================================================
# 실행 / 벤치마크 및 시각화
# ============================================================

if __name__ == "__main__":  # 스크립트 실행 진입점
    # ============================================================
    # 메인 실행부(Main): 실험 설정 → 벤치마크 반복 실행 → 결과 저장/시각화
    # ※ 함수/메서드 정의부는 그대로 두고, 메인 흐름만 상세 설명을 덧붙였습니다.
    # ============================================================

    # (1) 실험 설정값 ---------------------------------------------------------
    n_values = [300, 200, 150, 100, 60, 50, 30, 20, 15, 10, 5, 4, 3, 2, 1]  # 실험할 격자 크기 목록
    obstacle_ratio = 0.20  # 목표 벽 비율(난이도)
    base_seed = 12345  # 기본 난수 시드
    trials_per_n = 10  # 각 n별 반복 횟수
    block_size = 4  # 확대 배율(벽 두께 조절)
    clear_margin = 1  # 테두리 여백(시작/목표 보장)

    # (2) 통계 수집 컨테이너 --------------------------------------------------
    avg_time_ms = []  # n별 평균 실행시간(ms)
    avg_path_len_success = []  # n별 평균 경로 길이(성공만)
    success_counts = []  # n별 성공 trial 수
    sample_records = []  # 시각화용 샘플 (n, grid, path, found, time_ms)

    csv_rows = [("n", "trials", "success", "avg_time_ms", "avg_path_len_success")]  # CSV 헤더

    # (3) n 값 루프 -----------------------------------------------------------
    for n in n_values:  # 각 격자 크기에 대해
        start = (n-1, n-1)  # 시작 좌표(우하단)
        goal = (0, 0)  # 목표 좌표(좌상단)
        times = []  # 각 trial의 실행시간(ms)
        path_lens = []  # 성공 시 경로 길이 저장
        success = 0  # 성공 카운터
        sample_saved = False  # 샘플 1회만 저장 플래그

        for t in range(trials_per_n):  # trial 반복
            seed = base_seed + n*1000 + t  # 파생 시드(재현성)
            grid = make_maze_obstacles_grid(
                n,
                obstacle_ratio=obstacle_ratio,
                seed=seed,
                block_size=block_size,
                clear_margin=clear_margin
            )  # 실험용 격자 생성

            t0 = time.perf_counter()  # 타이머 시작
            path = a_star_8dir_no_corner_cut(grid, start, goal)  # A* 실행
            t1 = time.perf_counter()  # 타이머 종료
            dt_ms = (t1 - t0) * 1000.0  # 경과(ms)
            times.append(dt_ms)

            if path is not None:  # 경로 찾음
                success += 1
                path_lens.append(len(path))  # 스텝 수 기록

            if not sample_saved:  # 첫 trial 결과를 샘플로 저장
                sample_records.append((n, grid, path, path is not None, dt_ms))
                sample_saved = True

        mean_time = float(np.mean(times)) if times else 0.0  # 평균 시간
        mean_path_len = float(np.mean(path_lens)) if path_lens else 0.0  # 평균 경로 길이(성공)

        avg_time_ms.append(mean_time)
        avg_path_len_success.append(mean_path_len)
        success_counts.append(success)

        print(
            f"n={n:>3} | trials={trials_per_n} | success={success:<2} | "
            f"avg_time={mean_time:.2f} ms | avg_path_len_success={mean_path_len:.1f}"
        )  # 진행 상황 로그

        csv_rows.append((n, trials_per_n, success, round(mean_time, 4), round(mean_path_len, 2)))  # CSV 행 추가

    csv_path = "benchmark_results.csv"  # CSV 저장 경로
    with open(csv_path, "w", newline="", encoding="utf-8") as f:  # CSV 파일 열기
        writer = csv.writer(f)
        writer.writerows(csv_rows)  # 내용 기록
    print(f"[saved] {csv_path}")

    # 시각화: n 대비 평균 실행시간 가로 막대
    fig = plt.figure(figsize=(8, max(6, len(n_values)*0.35)))  # 그림 객체
    y_pos = np.arange(len(n_values))  # y축 위치 인덱스
    plt.barh(y_pos, avg_time_ms)  # 가로 막대
    plt.yticks(y_pos, [str(n) for n in n_values])  # y tick 라벨
    plt.xlabel("Average A* time (ms)")  # x축 라벨
    plt.ylabel("Grid size n")  # y축 라벨
    plt.title("A* 8-dir (no corner cutting) - Avg Runtime by Grid Size")  # 제목
    mmax = max(avg_time_ms) if avg_time_ms else 0.0  # 최대값(라벨 오프셋용)
    for i, v in enumerate(avg_time_ms):
        plt.text(v + (mmax * 0.01 if mmax > 0 else 0.02), i, f"{v:.2f} ms", va="center", fontsize=8)  # 막대 오른쪽 값
    plt.tight_layout()  # 레이아웃 정리
    bar_path = "runtime_barh.jpg"  # 저장 파일명
    plt.savefig(bar_path, dpi=180)  # 이미지 저장
    print(f"[saved] {bar_path}")
    plt.show()  # 화면 표시(노트북 환경)
    plt.close(fig)  # 리소스 정리
