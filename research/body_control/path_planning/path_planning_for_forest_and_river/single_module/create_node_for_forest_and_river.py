import math

waypoints = WaypointList()

def create_nodes(z, z_move, buffer_distance, waypoints):
    """
    z0: 시작 z (위에서 아래로 진행)
    z_move: 줄 간격(세로 이동)
    buffer_distance: 좌/우 안전 버퍼 (좌측 시작 x로 사용)
    waypoints: WaypointList 인스턴스 (append(x, z))

    강 경계는 z-구간별 최대 안전 x로 단순화해 선택합니다.
    """
    # 1) z 상한 (버퍼만큼 아래 여유 두기)
    z_limit = 300 - buffer_distance
    if z >= z_limit:
        return waypoints

    # 2) z-구간별 최대 안전 x 정의(필요시 값만 바꾸면 됨)
    zones = [
        (30, 145),
        (120, 175),
        (300, 205),
    ]

    def max_safe_x_for(z):
        # z가 속한 첫 구간의 x를 반환
        for z_top, mx in zones:
            if z < z_top:
                return mx
        return zones[-1][1]  # 안전망

    # 3) 줄 개수 미리 산출 (마지막 줄 포함, 세로 이동 노드는 마지막에 추가하지 않음)
    n_lines = int(math.floor((z_limit - z) / z_move)) + 1

    for i in range(n_lines):
        cz = z + i * z_move
        mx = max_safe_x_for(cz)

        if i % 2 == 0:
            sx, ex = buffer_distance, mx
        else:
            sx, ex = mx, buffer_distance

        # 가로 주행
        waypoints.append(sx, cz)
        waypoints.append(ex, cz)

        # 다음 줄로 내려가는 세로 이동 (마지막 줄은 생략)
        if i < n_lines - 1:
            waypoints.append(ex, cz + z_move)

    return waypoints


create_nodes(300, z_move=10, buffer_distance=5, waypoints=waypoints)

print(waypoints.to_list())
