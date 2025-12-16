# TPP(Tank Path Planning) Server + 실시간 시각화

from flask import Flask, request, jsonify
import numpy as np
import matplotlib.pyplot as plt
import heapq
import math
import traceback

app = Flask(__name__)

# -----------------------------
# 전역 설정
# -----------------------------
CELL_SIZE = 5.0   # 맵 한 칸 크기 (m)
MAP_H, MAP_W = 60, 60  # 내부 그리드 크기 (z, x)

# matplotlib 실시간 표시 설정
plt.ion()  # 인터랙티브 모드
fig, ax = plt.subplots(figsize=(8, 8))


# -----------------------------
# 1. 장애물 맵 생성 (60 x 60)
# -----------------------------
def create_obstacle_map(unknowns, cell_size=CELL_SIZE):
    """
    unknowns 리스트를 받아서 (H, W, 2) obstacle_map 생성.
    obstacle_map[:,:,0] == 1 이면 장애물 셀.
    """
    obstacle_map = np.zeros((MAP_H, MAP_W, 2), dtype=np.int16)

    padding = 1  # 셀 단위 padding (대략 1칸 = 5m)
    for obj in unknowns:
        try:
            x_world = obj["position"]["x"]
            z_world = obj["position"]["z"]
        except (KeyError, TypeError):
            continue

        gx = int(round(x_world / cell_size))
        gz = int(round(z_world / cell_size))

        for dx in range(-padding, padding + 1):
            for dz in range(-padding, padding + 1):
                nx, nz = gx + dx, gz + dz
                # 원형 패딩(대략 1칸 반경)
                if dx * dx + dz * dz <= padding * padding:
                    if 0 <= nx < MAP_W and 0 <= nz < MAP_H:
                        obstacle_map[nz, nx, 0] = 1     # occupancy
                        obstacle_map[nz, nx, 1] = 100   # cost (예비용)

    return obstacle_map


# -----------------------------
# 2. A* 경로 탐색 (격자 → 월드 좌표)
# -----------------------------
def path_planning(obstacle_map, start_world, goal_world, cell_size=CELL_SIZE):
    """
    A*로 start_world [x,z] -> goal_world [x,z] 경로 탐색.
    반환: [[x,z], ...] (월드 좌표)  / 경로 없으면 [].
    """
    occ = obstacle_map[:, :, 0]
    h, w = occ.shape  # (MAP_H, MAP_W)

    def in_bounds(gx, gz):
        return 0 <= gx < w and 0 <= gz < h

    def is_free(gx, gz):
        return occ[gz, gx] == 0

    def heuristic(a, b):
        # 유클리드 거리 (격자 상)
        return math.hypot(a[0] - b[0], a[1] - b[1])

    # 월드 → 격자 인덱스
    sx = int(round(start_world[0] / cell_size))
    sz = int(round(start_world[1] / cell_size))
    gx = int(round(goal_world[0] / cell_size))
    gz = int(round(goal_world[1] / cell_size))

    start_idx = (sx, sz)
    goal_idx = (gx, gz)

    # 목표가 맵 밖이거나 장애물이면 실패
    if not in_bounds(gx, gz) or not is_free(gx, gz):
        return []

    open_set = []
    # (F=G+H, G, node(gx,gz), path(list of nodes))
    heapq.heappush(open_set, (heuristic(start_idx, goal_idx), 0.0, start_idx, [start_idx]))
    g_scores = {start_idx: 0.0}

    # 8방향 (상하좌우 + 대각선)
    directions = [
        (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
        (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2)),
    ]

    while open_set:
        f, g, current, path = heapq.heappop(open_set)

        if current == goal_idx:
            # 격자 → 월드 좌표로 변환
            return [[gx_ * cell_size, gz_ * cell_size] for (gx_, gz_) in path]

        # 더 싼 비용으로 이미 방문한 노드면 skip
        if g > g_scores.get(current, float("inf")):
            continue

        cx, cz = current
        for dx, dz, step_cost in directions:
            nx, nz = cx + dx, cz + dz
            if not in_bounds(nx, nz) or not is_free(nx, nz):
                continue

            next_node = (nx, nz)
            new_g = g + step_cost

            if new_g < g_scores.get(next_node, float("inf")):
                g_scores[next_node] = new_g
                f_score = new_g + heuristic(next_node, goal_idx)
                heapq.heappush(open_set, (f_score, new_g, next_node, path + [next_node]))

    # 경로 없음
    return []


# -----------------------------
# 3. LOS(Line of Sight) 검사
# -----------------------------
def check_line_of_sight(obstacle_map, p1_world, p2_world, cell_size=CELL_SIZE):
    """
    두 월드 좌표 [x,z] 사이를 직선으로 갔을 때,
    중간에 장애물이 있는지 검사 (Bresenham 기반).
    True  = 직선 이동 가능
    False = 중간에 장애물 있음
    """
    occ = obstacle_map[:, :, 0]

    # 월드 → 격자
    x1 = int(round(p1_world[0] / cell_size))
    z1 = int(round(p1_world[1] / cell_size))
    x2 = int(round(p2_world[0] / cell_size))
    z2 = int(round(p2_world[1] / cell_size))

    dx = abs(x2 - x1)
    dz = abs(z2 - z1)
    sx = 1 if x1 < x2 else -1
    sz = 1 if z1 < z2 else -1
    err = dx - dz

    gx, gz = x1, z1
    h, w = occ.shape

    while True:
        # 시작 셀은 이미 안전하다고 가정, 중간/목표 셀만 검사
        if (gx != x1 or gz != z1):
            if not (0 <= gx < w and 0 <= gz < h):
                return False  # 맵 밖으로 나가면 실패로 처리
            if occ[gz, gx] == 1:
                return False  # 장애물 발견

        if gx == x2 and gz == z2:
            break

        e2 = 2 * err
        if e2 > -dz:
            err -= dz
            gx += sx
        if e2 < dx:
            err += dx
            gz += sz

    return True


# -----------------------------
# 4. LOS 기반 경로 단순화
# -----------------------------
def smooth_waypoints(waypoints_world, obstacle_map, cell_size=CELL_SIZE):
    """
    A*가 만든 길고 꺾인 경로(월드좌표)를 LOS 기반으로 단순화.
    입력: [[x,z], ...]  (월드 좌표)
    출력: [[x,z], ...]  (중간 불필요 지점 제거)
    """
    if not waypoints_world or len(waypoints_world) <= 2:
        return waypoints_world

    simplified = [waypoints_world[0]]
    anchor_idx = 0
    i = 1

    while i < len(waypoints_world):
        anchor = waypoints_world[anchor_idx]
        current = waypoints_world[i]

        if check_line_of_sight(obstacle_map, anchor, current, cell_size):
            # anchor → current까지 직선이 뚫림 → 더 멀리 시도
            i += 1
        else:
            # 바로 전 점(i-1)이 최대 직진 가능한 지점
            simplified.append(waypoints_world[i - 1])
            anchor_idx = i - 1
            # i는 그대로 두고, 새 anchor 기준으로 다음 LOS 검사

    # 마지막 점이 빠졌으면 추가
    if simplified[-1] != waypoints_world[-1]:
        simplified.append(waypoints_world[-1])

    return simplified


# -----------------------------
# 5. 실시간 시각화 (matplotlib 창)
# -----------------------------
def update_live_map(obstacle_map, start_world, target_world, waypoints_world, cell_size=CELL_SIZE):
    """
    obstacle_map : (H, W, 2)
    start_world  : [x,z]
    target_world : [x,z]
    waypoints_world : [[x,z], ...]
    """
    global fig, ax

    occ = obstacle_map[:, :, 0]
    h, w = occ.shape
    x_max = w * cell_size
    y_max = h * cell_size

    ax.clear()

    # 장애물 맵 (좌표계를 실제 미터로 맞춤)
    ax.imshow(
        occ,
        cmap="Reds",
        origin="lower",
        interpolation="nearest",
        vmin=0,
        vmax=1,
        extent=[0, x_max, 0, y_max],
    )

    ax.set_title("TPP Live Map (Red = Obstacle)")
    ax.grid(True, which="both", linewidth=0.3, alpha=0.5)

    tick_step = 50.0
    ax.set_xticks(np.arange(0, x_max + 1e-6, tick_step))
    ax.set_yticks(np.arange(0, y_max + 1e-6, tick_step))
    ax.set_xlim(0, x_max)
    ax.set_ylim(0, y_max)
    ax.set_aspect("equal")

    # 아군 위치 (파란 점)
    ax.scatter(start_world[0], start_world[1], c="blue", s=80, marker="o", label="Ally")

    # 목표 위치 (초록 X)
    ax.scatter(target_world[0], target_world[1], c="green", s=80, marker="x", label="Target")

    # 경로 (검은 선)
    if waypoints_world:
        wp = np.array(waypoints_world, dtype=float)
        ax.plot(
            wp[:, 0],
            wp[:, 1],
            c="black",
            linewidth=2,
            marker="o",
            markersize=4,
            label="Path",
        )

    ax.legend(loc="upper right")

    fig.canvas.draw()
    plt.pause(0.001)  # 이벤트 루프 돌려서 화면 갱신


# -----------------------------
# 6. Flask 핸들러
# -----------------------------
@app.route("/get_tpp", methods=["POST"])
def get_tpp():
    try:
        request_data = request.get_json()
    except Exception as e:
        return jsonify({"status": "ERR", "message": f"Invalid JSON: {str(e)}"}), 400

    try:
        ally_pos   = request_data["ally_body_pos"]   # {'x', 'y', 'z'}
        target_pos = request_data["target_pos"]      # {'x', 'y', 'z'}
        unknowns   = request_data.get("unknowns", [])  # 장애물들

        # 1) 장애물 맵 생성 (60x60)
        obstacle_map = create_obstacle_map(unknowns, cell_size=CELL_SIZE)

        # 2) A* 경로 탐색 (X,Z 평면)
        start_2d  = [ally_pos["x"],   ally_pos["z"]]
        target_2d = [target_pos["x"], target_pos["z"]]

        raw_waypoints_2d = path_planning(obstacle_map, start_2d, target_2d, cell_size=CELL_SIZE)

        # 3) 경로 없음 처리 + 시각화
        if not raw_waypoints_2d:
            update_live_map(obstacle_map, start_2d, target_2d, [], cell_size=CELL_SIZE)
            response_data = {
                "waypoints": [],
                "target_pos": target_pos,
            }
            return jsonify(response_data)

        # 4) LOS 기반 경로 단순화
        waypoints_2d = smooth_waypoints(raw_waypoints_2d, obstacle_map, cell_size=CELL_SIZE)

        # 5) 실시간 시각화 업데이트
        update_live_map(obstacle_map, start_2d, target_2d, waypoints_2d, cell_size=CELL_SIZE)

        # 6) IBSM으로 보내는 최종 waypoints (list of dict)
        waypoints_dict = [
            {"x": float(x), "y": 0.0, "z": float(z)} for x, z in waypoints_2d
        ]

        response_data = {
            "waypoints": waypoints_dict,
            "target_pos": target_pos,
        }
        return jsonify(response_data)

    except Exception as e:
        return jsonify({
            "status": "ERR",
            "message": f"Path planning failed: {str(e)}",
            "traceback": traceback.format_exc(),
        }), 500


# -----------------------------
# 7. 메인
# -----------------------------
if __name__ == "__main__":
    # 개발용 서버 실행
    # debug=True일 때 Flask가 두 번 실행되는 느낌이 들면,
    # debug=False로 바꾸거나, WERKZEUG_RUN_MAIN 체크를 추가해도 됨.
    plt.show(block=False)  # 창 하나 띄워두고 계속 갱신
    app.run(host="0.0.0.0", port=5000, debug=True)
