from flask import Flask, request, jsonify
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import heapq
import math
import traceback

# 서버 환경 고려해서 GUI 없는 백엔드 사용
matplotlib.use('Agg')

app = Flask(__name__)

# ------------------------------
# 전역 설정
# ------------------------------
CELL_SIZE = 5.0         # 한 셀의 실제 크기 (m)
GRID_H, GRID_W = 60, 60 # 내부 계산용 그리드 크기


# ------------------------------
# 1. 시각화 유틸 (옵션)
# ------------------------------
def visualize_map(obstacle_map, cell_size=CELL_SIZE):
    """
    obstacle_map: numpy array (H, W, 2)
      - obstacle_map[:, :, 0] == 1 인 곳이 장애물
    cell_size: 한 셀의 실제 길이 (m)
    """
    obstacle = obstacle_map[:, :, 0]
    h, w = obstacle.shape

    # 실제 거리 단위(m)로 축 설정
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
        extent=[0, x_max, 0, y_max],  # x: 0~x_max, y: 0~y_max (m)
    )
    plt.title('Obstacle Map (Red = Obstacle)')
    plt.grid(True, which='both', linewidth=0.3, alpha=0.5)

    tick_step = 50.0  # 50m 간격으로 눈금 표시 (필요하면 조절)
    plt.xticks(np.arange(0, x_max + 1e-6, tick_step))
    plt.yticks(np.arange(0, y_max + 1e-6, tick_step))

    plt.xlim(0, x_max)
    plt.ylim(0, y_max)
    plt.gca().set_aspect('equal')

    plt.tight_layout()
    # 서버에서 그냥 그림만 보고 싶다면 show
    # (실제 서버환경에선 보통 savefig를 쓰지만, 요구사항에 따라 show만 사용)
    plt.show()
    plt.close()


def visualize_path(obstacle_map, waypoints, cell_size=CELL_SIZE):
    """
    obstacle_map: (H, W, 2)
    waypoints: list of dict [{x, y, z}, ...] (월드 좌표, m 단위)
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

    if waypoints:
        xs = [wp["x"] for wp in waypoints]
        zs = [wp["z"] for wp in waypoints]
        plt.plot(
            xs,
            zs,
            linewidth=2,
            marker='o',
            markersize=4,
            label='Planned Path',
        )
        plt.legend()

    plt.tight_layout()
    plt.show()
    plt.close()


# ------------------------------
# 2. 맵 및 장애물 처리
# ------------------------------
def create_obstacle_map(unknowns, cell_size=CELL_SIZE):
    """
    unknowns 리스트를 기반으로 내부 60x60 (GRID_H x GRID_W) 장애물 맵 생성
    obstacle_map[z, x, 0] == 1 이면 장애물
    """
    obstacle_map = np.zeros((GRID_H, GRID_W, 2), dtype=np.int16)

    padding = 1  # 셀 단위 padding (5m)
    for obj in unknowns:
        pos = obj.get("position", {})
        try:
            x_world = float(pos["x"])
            z_world = float(pos["z"])
        except (KeyError, ValueError, TypeError):
            continue

        gx = int(round(x_world / cell_size))
        gz = int(round(z_world / cell_size))

        for dx in range(-padding, padding + 1):
            for dz in range(-padding, padding + 1):
                nx = gx + dx
                nz = gz + dz
                if dx * dx + dz * dz <= padding * padding:
                    if 0 <= nx < GRID_W and 0 <= nz < GRID_H:
                        obstacle_map[nz, nx, 0] = 1   # occupancy
                        obstacle_map[nz, nx, 1] = 100 # cost (옵션)

    return obstacle_map


# ------------------------------
# 3. A* 경로 탐색 (grid 기반)
# ------------------------------
def path_planning_grid(obstacle_map, start_world, goal_world, cell_size=CELL_SIZE):
    """
    A* 알고리즘으로 grid 경로 탐색
    start_world, goal_world: [x, z] (월드 좌표, m)
    반환: grid 경로 [(gx, gz), ...]  (grid index)
    """
    occ = obstacle_map[:, :, 0]
    h, w = occ.shape

    def in_bounds(gx, gz):
        return 0 <= gx < w and 0 <= gz < h

    def is_free(gx, gz):
        return occ[gz, gx] == 0

    def heuristic(a, b):
        return math.hypot(a[0] - b[0], a[1] - b[1])

    start_g = (int(round(start_world[0] / cell_size)),
               int(round(start_world[1] / cell_size)))
    goal_g = (int(round(goal_world[0] / cell_size)),
              int(round(goal_world[1] / cell_size)))

    # 목표가 맵 밖이거나 장애물이면 경로 없음
    if not in_bounds(*goal_g) or not is_free(*goal_g):
        return []

    open_set = []
    heapq.heappush(open_set, (heuristic(start_g, goal_g), 0.0, start_g, [start_g]))

    g_scores = {start_g: 0.0}

    # 8방향
    directions = [
        (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
        (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2)),
    ]

    while open_set:
        est_total, cost, current, path = heapq.heappop(open_set)

        if current == goal_g:
            return path  # grid 경로 그대로 반환

        if cost > g_scores.get(current, float('inf')):
            continue

        x, z = current
        for dx, dz, move_cost in directions:
            nx, nz = x + dx, z + dz
            if not in_bounds(nx, nz) or not is_free(nx, nz):
                continue

            nxt = (nx, nz)
            new_cost = cost + move_cost

            if new_cost < g_scores.get(nxt, float('inf')):
                g_scores[nxt] = new_cost
                f_score = new_cost + heuristic(nxt, goal_g)
                heapq.heappush(open_set, (f_score, new_cost, nxt, path + [nxt]))

    return []  # 경로 없음


# ------------------------------
# 4. LOS & 경로 단순화 (grid 기준)
# ------------------------------
def bresenham_line(gx0, gz0, gx1, gz1):
    """격자 좌표 사이를 잇는 Bresenham 라인 (폐구간)"""
    dx = abs(gx1 - gx0)
    dz = -abs(gz1 - gz0)
    sx = 1 if gx0 < gx1 else -1
    sz = 1 if gz0 < gz1 else -1
    err = dx + dz

    x, z = gx0, gz0
    while True:
        yield x, z
        if x == gx1 and z == gz1:
            break
        e2 = 2 * err
        if e2 >= dz:
            err += dz
            x += sx
        if e2 <= dx:
            err += dx
            z += sz


def line_blocked_grid(p0, p1, occ):
    """
    p0, p1: (gx, gz)
    occ: obstacle_map[:, :, 0]
    두 점 사이 직선에 장애물이 있으면 True
    """
    gx0, gz0 = p0
    gx1, gz1 = p1
    h, w = occ.shape

    for gx, gz in bresenham_line(gx0, gz0, gx1, gz1):
        # 시작/끝점은 허용, 그 사이만 검사
        if (gx, gz) != p0 and (gx, gz) != p1:
            if not (0 <= gx < w and 0 <= gz < h):
                return True  # 맵 밖은 막힌 것으로 취급
            if occ[gz, gx] == 1:
                return True
    return False


def simplify_path_los_grid(grid_path, obstacle_map):
    """
    grid_path: [(gx, gz), ...]
    obstacle_map: (H, W, 2)
    LOS 기반으로 경로 단순화
    """
    if not grid_path:
        return []
    if len(grid_path) <= 2:
        return grid_path

    occ = obstacle_map[:, :, 0]
    simplified = [grid_path[0]]
    i = 0
    n = len(grid_path)

    while i < n - 1:
        j = i + 1
        # i에서 j+1까지 직선이 뚫려 있으면 j를 늘림
        while j + 1 < n and not line_blocked_grid(grid_path[i], grid_path[j + 1], occ):
            j += 1
        simplified.append(grid_path[j])
        i = j

    return simplified


# ------------------------------
# 5. Flask 핸들러
# ------------------------------
@app.route('/get_tpp', methods=['POST'])
def get_tpp():
    try:
        request_data = request.get_json()
    except Exception as e:
        return jsonify({"status": "ERR", "message": f"Invalid JSON: {str(e)}"}), 400

    try:
        ally_pos = request_data["ally_body_pos"]
        target_pos = request_data["target_pos"]
        unknowns = request_data.get("unknowns", [])

        # 1) 맵 생성 (60x60 내부 그리드)
        obstacle_map = create_obstacle_map(unknowns, cell_size=CELL_SIZE)

        # 2) A* 경로 탐색 (grid 기준)
        start_world = [ally_pos["x"], ally_pos["z"]]
        goal_world  = [target_pos["x"], target_pos["z"]]
        grid_path   = path_planning_grid(obstacle_map, start_world, goal_world, cell_size=CELL_SIZE)

        # 경로가 없으면 빈 결과
        if not grid_path:
            return jsonify({
                "waypoints": [],
                "target_pos": target_pos,
            })

        # 3) LOS 기반 grid 경로 단순화
        grid_path_simplified = simplify_path_los_grid(grid_path, obstacle_map)

        # 4) grid → world 변환 + dict로 바로 생성
        #    여기서 처음 생성되는 waypoints가 곧 최종 list-of-dict 형태
        ally_y = float(ally_pos.get("y", 0.0))
        waypoints = []
        for gx, gz in grid_path_simplified:
            wx = gx * CELL_SIZE
            wz = gz * CELL_SIZE
            waypoints.append({
                "x": float(wx),
                "y": ally_y,   # 동일 평면 이동을 가정
                "z": float(wz),
            })

        # (옵션) 시각화가 필요하면 아래 주석 해제
        # visualize_map(obstacle_map, cell_size=CELL_SIZE)
        # visualize_path(obstacle_map, waypoints, cell_size=CELL_SIZE)

        # 5) IBSM으로 보내는 최종 출력
        response_data = {
            "waypoints": waypoints,   # list of dict
            "target_pos": target_pos, # 그대로 echo
        }
        return jsonify(response_data)

    except Exception as e:
        return jsonify({
            "status": "ERR",
            "message": f"Path planning failed: {str(e)}",
            "traceback": traceback.format_exc(),
        }), 500


if __name__ == '__main__':
    # dev server
    app.run(host='0.0.0.0', port=5000, debug=True)
