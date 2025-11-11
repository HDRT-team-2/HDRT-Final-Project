# astar_planner.py
from heapq import heappush, heappop

def heuristic(a, b, metric="octile"):
    ax, ay = a
    bx, by = b
    dx = abs(ax - bx)
    dy = abs(ay - by)
    if metric == "manhattan":
        return dx + dy
    if metric == "euclidean":
        return (dx*dx + dy*dy) ** 0.5
    # Octile distance (good for 8-connected grids; diagonal cost = 1.414)
    dmin, dmax = min(dx, dy), max(dx, dy)
    return 1.41421356237 * dmin + (dmax - dmin)

def neighbors(p, grid_w, grid_h, diagonal=True):
    x, y = p
    nbrs4 = [(x+1,y),(x-1,y),(x,y+1),(x,y-1)]
    if not diagonal:
        return [q for q in nbrs4 if 0 <= q[0] < grid_w and 0 <= q[1] < grid_h]
    nbrs8 = nbrs4 + [(x+1,y+1),(x-1,y-1),(x+1,y-1),(x-1,y+1)]
    return [q for q in nbrs8 if 0 <= q[0] < grid_w and 0 <= q[1] < grid_h]

def astar(start, goal, grid_w, grid_h, obstacles=None, diagonal=True):
    """
    A* pathfinding on a grid.
    - start, goal: (x, y) integer cells
    - grid_w, grid_h: grid size (e.g., 300, 300)
    - obstacles: set of (x, y) cells that are blocked
    - diagonal: allow 8-connected motion if True (default)
    Returns: list of (x, y) from start to goal (inclusive). Empty list if no path.
    """
    if obstacles is None:
        obstacles = set()

    if start == goal:
        return [start]

    if start in obstacles or goal in obstacles:
        return []

    # Costs
    straight_cost = 1.0
    diag_cost = 1.41421356237

    open_heap = []
    heappush(open_heap, (0.0, start))
    came_from = {}
    g_score = {start: 0.0}
    f_score = {start: heuristic(start, goal, metric="octile" if diagonal else "manhattan")}

    closed = set()

    while open_heap:
        _, current = heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            # reconstruct
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        closed.add(current)
        for nb in neighbors(current, grid_w, grid_h, diagonal=diagonal):
            if nb in obstacles or nb in closed:
                continue

            # Prevent corner cutting for diagonal moves
            if diagonal and (nb[0] != current[0] and nb[1] != current[1]):
                cx, cy = current
                nx, ny = nb
                if (nx, cy) in obstacles or (cx, ny) in obstacles:
                    continue

            step_cost = diag_cost if (nb[0] != current[0] and nb[1] != current[1]) else straight_cost
            tentative = g_score[current] + step_cost
            if tentative < g_score.get(nb, float('inf')):
                came_from[nb] = current
                g_score[nb] = tentative
                f = tentative + heuristic(nb, goal, metric="octile" if diagonal else "manhattan")
                f_score[nb] = f
                heappush(open_heap, (f, nb))

    return []  # no path
