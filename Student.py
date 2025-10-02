import asyncio
import getpass
import json
import os
import random
import pygame
import websockets
import heapq
import consts
from collections import deque

pygame.init()
icon_image = pygame.image.load("data/icon2.png")
pygame.display.set_icon(icon_image)

class SnakeMovement:
    def __init__(self, snake_body, sight, traverse, size, map_data, steps):
        self.snake_body = snake_body
        self.sight = sight
        self.traverse = traverse
        self.size = size
        self.map = map_data
        self.steps = steps
        self.stones = []
        for col in range(len(self.map)):
            for row in range(len(self.map[col])):
                if self.map[col][row] == consts.Tiles.STONE:
                    self.stones.append((col, row))

        self.Nx = 3
        self.Ny = 3

        self.recently_visited = set()

    def set_recently_visited(self, visited_positions):
        self.recently_visited = visited_positions

    def locate_food(self):
        for row, row_data in self.sight.items():
            for col, tile in row_data.items():
                if tile == consts.Tiles.FOOD or tile == consts.Tiles.SUPER:
                    return int(row), int(col)
        return None

    def tile_cost(self, next_pos):
        x, y = next_pos
        tile = self.sight.get(str(x), {}).get(str(y), None)

        if not (0 <= x < self.size[0] and 0 <= y < self.size[1]):
            return 10000

        if not self.traverse:
            if tile in [consts.Tiles.STONE, consts.Tiles.SNAKE]:
                return 10000
            if (x, y) in map(tuple, self.snake_body):
                return 10000
            base_cost = 0 if tile in [consts.Tiles.FOOD, consts.Tiles.SUPER] else 1
        else:
            if tile == consts.Tiles.SNAKE or (x, y) in map(tuple, self.snake_body):
                return 10000
            if tile == consts.Tiles.STONE:
                base_cost = 1
            elif tile in [consts.Tiles.FOOD, consts.Tiles.SUPER]:
                base_cost = 0
            else:
                base_cost = 1

        min_dist_body = min(abs(x - bx) + abs(y - by) for (bx, by) in self.snake_body)
        if min_dist_body == 1:
            base_cost += 5   
        elif min_dist_body == 2:
            base_cost += 2  

        if self.stones:
            min_dist_stone = min(abs(x - sx) + abs(y - sy) for (sx, sy) in self.stones)
            if min_dist_stone == 1:
                base_cost += 2 
            elif min_dist_stone == 2:
                base_cost += 1 

        dist_left = x
        dist_right = (self.size[0] - 1) - x
        dist_top = y
        dist_bottom = (self.size[1] - 1) - y
        min_dist_edge = min(dist_left, dist_right, dist_top, dist_bottom)
        if min_dist_edge == 0:
            base_cost += 5
        elif min_dist_edge == 1:
            base_cost += 2

        if next_pos in self.recently_visited:
            base_cost += 5

        return base_cost

    def calculate_heuristic(self, current, goal):
        heuristic = abs(current[0] - goal[0]) + abs(current[1] - goal[1])
        x, y = current
        dist_left = x
        dist_right = (self.size[0] - 1) - x
        dist_top = y
        dist_bottom = (self.size[1] - 1) - y
        min_edge = min(dist_left, dist_right, dist_top, dist_bottom)
        if min_edge <= 1:
            heuristic += 5
        return heuristic

    def get_neighbors(self, current):
        x, y = current
        pot = [(x+1, y), (x-1, y), (x, y+1), (x, y-1)]
        valid = []
        for nx, ny in pot:
            if 0 <= nx < self.size[0] and 0 <= ny < self.size[1]:
                tile = self.sight.get(str(nx), {}).get(str(ny), None)
                if tile != consts.Tiles.SNAKE:
                    valid.append((nx, ny))
        return valid

    def a_star_algorithm(self, start, goal):
        frontier = []
        heapq.heappush(frontier, (0, start))
        came_from = {start: None}
        cost_so_far = {start: 0}
        while frontier:
            _, current = heapq.heappop(frontier)
            if current == goal:
                break
            for next_pos in self.get_neighbors(current):
                new_cost = cost_so_far[current] + self.tile_cost(next_pos)
                if next_pos not in cost_so_far or new_cost < cost_so_far[next_pos]:
                    cost_so_far[next_pos] = new_cost
                    priority = new_cost + self.calculate_heuristic(goal, next_pos)
                    heapq.heappush(frontier, (priority, next_pos))
                    came_from[next_pos] = current
        return self.reconstruct_path(came_from, start, goal)

    def reconstruct_path(self, came_from, start, goal):
        if goal not in came_from:
            return []
        path = []
        current = goal
        while current != start:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path

    def get_next_direction(self, path):
        if not path:
            return ""
        head_x, head_y = self.snake_body[0]
        nx, ny = path[0]
        if nx > head_x:
            return "d"
        elif nx < head_x:
            return "a"
        elif ny > head_y:
            return "s"
        elif ny < head_y:
            return "w"
        return ""

    def total_quadrants(self):
        return self.Nx * self.Ny

    def get_quadrant_bbox(self, qid):
        w, h = self.size
        quad_w = w // self.Nx
        quad_h = h // self.Ny
        qx = qid % self.Nx
        qy = qid // self.Nx
        min_x = qx * quad_w
        max_x = (qx+1) * quad_w
        if qx == self.Nx - 1:
            max_x = w
        min_y = qy * quad_h
        max_y = (qy+1) * quad_h
        if qy == self.Ny - 1:
            max_y = h
        return (min_x, max_x, min_y, max_y)

    def quadrant_center(self, qid):
        min_x, max_x, min_y, max_y = self.get_quadrant_bbox(qid)
        cx = (min_x + max_x) // 2
        cy = (min_y + max_y) // 2
        return (cx, cy)

    def pick_random_distant_coordinate_in_bbox(self, bbox, head_pos, min_dist=10, max_tries=100):
        min_x, max_x, min_y, max_y = bbox
        snake_positions = set(map(tuple, self.snake_body))
        def manhattan(a, b):
            return abs(a[0] - b[0]) + abs(a[1] - b[1])
        for _ in range(max_tries):
            x = random.randint(min_x, max_x - 1)
            y = random.randint(min_y, max_y - 1)
            if (x, y) in snake_positions:
                continue
            if self.map[x][y] == consts.Tiles.STONE:
                continue
            dist = manhattan(head_pos, (x, y))
            if dist < min_dist:
                continue
            path = self.a_star_algorithm(head_pos, (x, y))
            if path:
                return (x, y)
        return None

    def generate_target_for_quadrant(self, qid, head_pos):
        bbox = self.get_quadrant_bbox(qid)
        return self.pick_random_distant_coordinate_in_bbox(bbox, head_pos, min_dist=10, max_tries=100)


async def agent_loop(server_address="localhost:8000", agent_name="student"):
    async with websockets.connect(f"ws://{server_address}/player") as websocket:
        await websocket.send(json.dumps({"cmd": "join", "name": agent_name}))
        from collections import deque
        recent_positions = deque(maxlen=10)
        initial_state = None
        data = json.loads(await websocket.recv())
        print(data)
        if 'map' in data:
            map_data = data['map']
            size = data['size']
        else:
            map_data = None
            size = (0, 0)
        visited_quadrants = set()
        current_qid = None
        current_target = None
        while True:
            try:
                state = json.loads(await websocket.recv())
                print(state)
                if initial_state is None:
                    initial_state = state
                else:
                    snake_body = state['body']
                    head_pos = tuple(snake_body[0])
                    recent_positions.append(head_pos)
                    sight = state['sight']
                    traverse = state['traverse']
                    steps = state['step']
                    movement = SnakeMovement(snake_body, sight, traverse, size, map_data, steps)
                    movement.set_recently_visited(set(recent_positions))
                    food_position = movement.locate_food()
                    if current_target is None or head_pos == current_target:
                        if current_qid is not None:
                            visited_quadrants.add(current_qid)
                        if len(visited_quadrants) == movement.total_quadrants():
                            visited_quadrants.clear()
                        all_quads = list(range(movement.total_quadrants()))
                        not_visited = [q for q in all_quads if q not in visited_quadrants]
                        if not not_visited:
                            visited_quadrants.clear()
                            not_visited = all_quads
                        current_qid = random.choice(not_visited)
                        candidate_target = movement.generate_target_for_quadrant(current_qid, head_pos)
                        if candidate_target is None:
                            visited_quadrants.add(current_qid)
                            not_visited = [q for q in all_quads if q not in visited_quadrants]
                            if not not_visited:
                                visited_quadrants.clear()
                                not_visited = all_quads
                            current_qid = random.choice(not_visited)
                            candidate_target = movement.generate_target_for_quadrant(current_qid, head_pos)
                        current_target = candidate_target if candidate_target else head_pos
                    if food_position:
                        path_food = movement.a_star_algorithm(head_pos, food_position)
                        if path_food:
                            key = movement.get_next_direction(path_food)
                        else:
                            path_target = movement.a_star_algorithm(head_pos, current_target)
                            key = movement.get_next_direction(path_target)
                    else:
                        path_target = movement.a_star_algorithm(head_pos, current_target)
                        key = movement.get_next_direction(path_target)
                    print(f"Sending key: {key}")
                    await websocket.send(json.dumps({"cmd": "key", "key": key}))
            except websockets.exceptions.ConnectionClosedError:
                print("Disconnected by server.")
                break

loop = asyncio.get_event_loop()
SERVER = os.environ.get("SERVER", "localhost")
PORT = os.environ.get("PORT", "8000")
NAME = os.environ.get("NAME", getpass.getuser())
loop.run_until_complete(agent_loop(f"{SERVER}:{PORT}", NAME))