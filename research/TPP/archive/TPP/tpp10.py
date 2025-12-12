from flask import Flask, request, jsonify
import numpy as np
import matplotlib
import heapq
import math
import traceback

# 서버 환경 고려해서 GUI 없는 백엔드 사용
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)

# ==============================
# 전역 설정
# ==============================
CELL_SIZE = 5.0          # 한 셀의 실제 길이 (m)
GRID_H, GRID_W = 60, 60  # 내부 연산용 그리드 크기
MAX_JUMP = 10            # LOS 단순화 시 격자 기준 최대 점프 거리 (셀 수)
ENABLE_PLOT = False      # True로 바꾸면 PNG로 시각화 파일 생성


# ==============================
# 1. 시각화 유틸리티 (옵션)
# ==============================
def visualize_map(map_info, cell_size: float):
    """
    map_info: obstacle_map (H, W, 2)
      - map_info[:, :, 0] == 1 인 곳이 장애물
    cell_size: 한 셀의 실제 길이 (m)
    """
    obstacle = map_info[:, :, 0]
    h, w = obstacle.shape  # H(세로, z방향), W(가로, x방향)

    # 축을 실제 미터 단위로 보이게 하기 위해 extent 사용
    x_max = w * cell_size   # 가로 전체 길이 (m)
    y_max = h * cell_size   # 세로 전체 길이 (m)

    plt.figure(figsize=(8, 8))
    plt.imshow(
        obstacle,
        cmap='Reds',
        origin='lower',
        interpolation='nearest',
        vmin=0,
        vmax=1,
        extent=[0, x_max, 0, y_max],  # x,y축에 cell_size 반영
    )
    plt.title('Obstacle Map (Red = Obstacle)')

    # 그리드(격자선)
    plt.grid(True, which='both', linewidth=0.3, alpha=0.5)

    # 축 눈금도 실제 거리 기준으로 (예: 50m 간격)
    tick_step = 50.0
    plt.xticks(np.arange(0, x_max + 1e-6, tick_step))
    plt.yticks(np.arange(0, y_max + 1e-6, tick_step))

    plt.xlim(0, x_max)
    plt.ylim(0, y_max)
    plt.gca().set_aspect('equal')

    plt.tight_layout()
    plt.close()


def visualize_path(obstacle_map, path_world, cell_size: float = CELL_SIZE):
    """
    obstacle_map: (H, W, 2)
    path_world: [[x, z], ...]  (월드 좌표, 미터 단위)
    장애물은 occupancy를, 경로는 월드 좌표 그대로 겹쳐 그림.
    """
    obstacle = obstacle_map[:, :, 0]
    h, w = obstacle.shape

    x_max = w * cell_size
    y_max = h * cell_size

    plt.figure(figsize=(8, 8))
    plt.imshow(
        obstacle,
        cmap='Reds',
        origin='lower',
        interpolation='nearest',
        vmin=0,
        vmax=1,
        extent=[0, x_max, 0, y_max],
    )
    plt.title('Path on Obstacle Map (Red = Obstacle)')
    plt.grid(True, which='both', linewidth=0.3, alpha=0.5)

    tick_step = 50.0
    plt.xticks(np.arange(0, x_max + 1e-6, tick_step))
    plt.yticks(np.arange(0, y_max + 1e-6, tick_step))

    plt.xlim(0, x_max)
    plt.ylim(0, y_max)
    plt.gca().set_aspect('equal')

    if path_world:
        path = np.array(path_world, dtype=float)  # [[x,z], ...]
        plt.plot(
            path[:, 0],
            path[:, 1],
            linewidth=2,
            marker='o',
            markersize=4,
            label='Planned Path',
        )
        plt.legend()

    plt.tight_layout()
    plt.close()


# ==============================
# 2. 맵 및 장애물 처리 로직
# ==============================
def create_obstacle_map(unknowns, cell_size: float = CELL_SIZE):
    """
    unknowns: IBSM에서 넘어오는 unknown 리스트
      - 각 원소: {"position": {"x": ..., "y": ..., "z": ...}, ...}

    내부적으로는 60x60 그리드에 occupancy / cost 채운다.
    """
    height, width = GRID_H, GRID_W
    obstacle_map = np.zeros((height, width, 2), dtype=np.int16)

    padding = 1  # 셀 단위 padding (5m)

    for obj in unknowns:
        try:
            x_coord = obj['position']['x']
            z_coord = obj['position']['z']
        except (KeyError, TypeError):
            continue

        # 월드 좌표 → 그리드 인덱스
        gx = int(round(x_coord / cell_size))
        gz = int(round(z_coord / cell_size))

        for dx in range(-padding, padding + 1):
            for dz in range(-padding, padding + 1):
                nx, nz = gx + dx, gz + dz
                # 원형 padding (유클리드 거리 1 이하만)
                if dx * dx + dz * dz <= padding * padding:
                    if 0 <= nx < width and 0 <= nz < height:
                        obstacle_map[nz, nx, 0] = 1    # occupancy
                        obstacle_map[nz, nx, 1] = 100  # cost (지금은 사용 X)

    return obstacle_map


# ==============================
# 3. A* 경로 탐색
# ==============================
def path_planning(obstacle_map, start, goal, cell_size: float = CELL_SIZE):
    """
    obstacle_map: (H, W, 2)
    start, goal: [x, z] (월드 좌표, m 단위)
    반환: [[x, z], ...] (월드 좌표)
    """
    occ = obstacle_map[:, :, 0]
    height, width = occ.shape

    def in_bounds(x, z):
        return 0 <= x < width and 0 <= z < height

    def is_free(x, z):
        return occ[z, x] == 0

    def heuristic(a, b):
        # 유클리드 거리 (격자 기준)
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # 월드 좌표 → 격자 인덱스
    start_idx = (int(round(start[0] / cell_size)), int(round(start[1] / cell_size)))
    goal_idx = (int(round(goal[0] / cell_size)), int(round(goal[1] / cell_size)))

    # 목표점이 맵 밖이거나 장애물이면 경로 탐색 불가
    if not in_bounds(goal_idx[0], goal_idx[1]) or not is_free(goal_idx[0], goal_idx[1]):
        return []

    open_set = []
    # (F = G + H, G, current_node, path)
    heapq.heappush(open_set, (heuristic(start_idx, goal_idx), 0.0, start_idx, [start_idx]))

    g_scores = {start_idx: 0.0}

    # 8방향 (상하좌우+대각선)
    directions = [
        (-1, 0, 1.0), (1, 0, 1.0),
        (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
        (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2)),
    ]

    while open_set:
        est_total, cost, current, path = heapq.heappop(open_set)

        if current == goal_idx:
            # grid 인덱스를 실제 좌표(중앙 또는 셀 위치)로 변환해서 반환
            return [[x * cell_size, z * cell_size] for (x, z) in path]

        # 이미 더 싼 비용으로 방문했던 노드라면 skip
        if cost > g_scores.get(current, float('inf')):
            continue

        x, z = current
        for dx, dz, move_cost in directions:
            nx, nz = x + dx, z + dz
            next_node = (nx, nz)

            if not in_bounds(nx, nz) or not is_free(nx, nz):
                continue

            new_cost = cost + move_cost

            if new_cost < g_scores.get(next_node, float('inf')):
                g_scores[next_node] = new_cost
                f_score = new_cost + heuristic(next_node, goal_idx)
                heapq.heappush(open_set, (f_score, new_cost, next_node, path + [next_node]))

    # 경로 없음
    return []


# ==============================
# 4. LOS & 경로 단순화
# ==============================
def check_line_of_sight(obstacle_map, p1_coord, p2_coord, cell_size: float = CELL_SIZE):
    """
    두 실제 좌표 [x, z] 사이에 장애물이 있는지 확인
    - p1_coord, p2_coord: 월드 좌표
    - Bresenham을 격자 단위로 사용
    """
    occ = obstacle_map[:, :, 0]
    h, w = occ.shape

    # 월드 좌표 → 격자 인덱스
    x1 = int(round(p1_coord[0] / cell_size))
    z1 = int(round(p1_coord[1] / cell_size))
    x2 = int(round(p2_coord[0] / cell_size))
    z2 = int(round(p2_coord[1] / cell_size))

    dx = abs(x2 - x1)
    dz = abs(z2 - z1)
    sx = 1 if x1 < x2 else -1
    sz = 1 if z1 < z2 else -1
    err = dx - dz

    curr_x, curr_z = x1, z1

    while True:
        # 시작점은 이미 안전하다고 가정하고, 중간/끝점에서만 장애물 검사
        if (curr_x != x1 or curr_z != z1):
            if not (0 <= curr_x < w and 0 <= curr_z < h):
                # 맵 밖으로 나가면 LOS 실패로 간주
                return False
            if occ[curr_z, curr_x] == 1:
                return False  # 장애물 발견

        if curr_x == x2 and curr_z == z2:
            break

        e2 = 2 * err
        if e2 > -dz:
            err -= dz
            curr_x += sx
        if e2 < dx:
            err += dx
            curr_z += sz

    return True  # 장애물 없음 (LOS 성공)


def smooth_waypoints(waypoints, obstacle_map, cell_size: float = CELL_SIZE):
    """
    LOS 검사를 통해 경로 단순화 및 최적화
    입력: [[x, z], ...] (월드 좌표)
    - 너무 멀리 점프하는 LOS는 MAX_JUMP로 제한
    """
    if not waypoints or len(waypoints) <= 2:
        return waypoints

    simplified = [waypoints[0]]
    anchor_idx = 0
    i = 1

    while i < len(waypoints):
        anchor_point = waypoints[anchor_idx]
        current_point = waypoints[i]

        # 앵커에서 현재 포인트까지의 격자 기준 거리
        dx_grid = (current_point[0] - anchor_point[0]) / cell_size
        dz_grid = (current_point[1] - anchor_point[1]) / cell_size
        grid_dist = math.hypot(dx_grid, dz_grid)

        # 한 번에 너무 멀리 LOS 시도하지 않도록 제한
        if grid_dist > MAX_JUMP:
            # 직전 점이 최대 허용 직선 구간
            simplified.append(waypoints[i - 1])
            anchor_idx = i - 1
            # i는 그대로 두고, 새 anchor 기준으로 다시 검사
            continue

        los_success = check_line_of_sight(obstacle_map, anchor_point, current_point, cell_size=cell_size)

        if los_success:
            # 앵커에서 i번째까지 직선 가능 → 더 멀리 도전
            i += 1
        else:
            # 직전 i-1가 최대 직진 가능 지점
            simplified.append(waypoints[i - 1])
            anchor_idx = i - 1
            # i는 그대로 두고, 새 anchor 기준으로 다시 검사

    # 마지막 웨이포인트 보장
    if simplified[-1] != waypoints[-1]:
        simplified.append(waypoints[-1])

    return simplified


# ==============================
# 5. Flask 핸들러
# ==============================
@app.route('/get_tpp', methods=['POST'])
def get_tpp():
    try:
        request_data = request.get_json()
    except Exception as e:
        return jsonify({"status": "ERR", "message": f"Invalid JSON: {str(e)}"}), 400

    try:
        ally_pos = request_data['ally_body_pos']   # {'x','y','z'}
        target_pos = request_data['target_pos']    # {'x','y','z'}
        unknowns = request_data.get('unknowns', [])

        # 1. 맵 생성
        obstacle_map = create_obstacle_map(unknowns, cell_size=CELL_SIZE)

        if ENABLE_PLOT:
            visualize_map(obstacle_map, cell_size=CELL_SIZE)

        # 2. A* 경로 탐색 (X, Z 평면)
        start_2d = [ally_pos['x'],   ally_pos['z']]
        target_2d = [target_pos['x'], target_pos['z']]

        # 2-0. 먼저 직선으로 갈 수 있으면 A* 자체를 생략 (연산량 크게 절감)
        if check_line_of_sight(obstacle_map, start_2d, target_2d, cell_size=CELL_SIZE):
            waypoints_2d = [start_2d, target_2d]
        else:
            # 2-1. A* 실행
            raw_waypoints_2d = path_planning(obstacle_map, start_2d, target_2d, cell_size=CELL_SIZE)

            # 경로가 없으면 빈 결과 반환
            if not raw_waypoints_2d:
                response_data = {
                    "waypoints": [],
                    "target_pos": target_pos,
                }
                return jsonify(response_data)

            # 2-2. LOS 단순화 (MAX_JUMP 적용)
            waypoints_2d = smooth_waypoints(raw_waypoints_2d, obstacle_map, cell_size=CELL_SIZE)

        if ENABLE_PLOT:
            visualize_path(obstacle_map, waypoints_2d, cell_size=CELL_SIZE)

        # 3. 3D dict 포맷으로 변환: X, Y=0.0, Z
        waypoints_dict = [
            {"x": float(x), "y": 0.0, "z": float(z)} for x, z in waypoints_2d
        ]

        # 4. 응답 데이터 구성 (IBSM 요구사항: waypoints + target_pos만)
        response_data = {
            "waypoints": waypoints_dict,
            "target_pos": target_pos,
        }

        return jsonify(response_data)

    except Exception as e:
        # 디버깅용 자세한 에러 반환
        return jsonify({
            "status": "ERR",
            "message": f"Path planning failed: {str(e)}",
            "traceback": traceback.format_exc(),
        }), 500


if __name__ == '__main__':
    # dev server
    app.run(host='0.0.0.0', port=5000, debug=True)
