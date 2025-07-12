import socket
import threading
import json
import random
import time

TILE_SIZE = 20
GRID_WIDTH = 40
GRID_HEIGHT = 30
APPLE_COUNT = 5
TICK_RATE = 10

class GameServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind((host, port))
        self.srv.listen()
        print(f"Server listening on {host}:{port}")

        self.clients = []
        self.lock = threading.Lock()

        self.apples = []
        self.spawn_apples()

        self.snakes = {}
        self.next_id = 0

    def spawn_apples(self):
        self.apples.clear()
        while len(self.apples) < APPLE_COUNT:
            pos = (random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1))
            if pos not in self.apples:
                self.apples.append(pos)

    def start(self):
        threading.Thread(target=self.accept_clients, daemon=True).start()
        self.game_loop()

    def accept_clients(self):
        while True:
            client, addr = self.srv.accept()
            print(f"Client connected from {addr}")
            client_id = self.next_id
            self.next_id += 1

            with self.lock:
                pos = self.find_spawn_position()
                snake_body = [pos, (pos[0] - 1, pos[1]), (pos[0] - 2, pos[1])]
                self.snakes[client_id] = {
                    "body": snake_body,
                    "dir": (1, 0),
                    "alive": True,
                    "grow": 0
                }

            self.clients.append((client_id, client))
            threading.Thread(target=self.handle_client, args=(client_id, client), daemon=True).start()

    def find_spawn_position(self):
        attempts = 0
        safe_margin = 5

        while attempts < 1000:
            x = random.randint(safe_margin, GRID_WIDTH - safe_margin - 1)
            y = random.randint(safe_margin, GRID_HEIGHT - safe_margin - 1)
            candidate = (x, y)

            # Avoid spawning on snakes or apples
            collision = False
            for s in self.snakes.values():
                if candidate in s["body"]:
                    collision = True
                    break
            if candidate in self.apples:
                collision = True

            if not collision:
                return candidate

            attempts += 1

        return (GRID_WIDTH // 2, GRID_HEIGHT // 2)

    def handle_client(self, client_id, client):
        try:
            while True:
                data = client.recv(1024).decode()
                if not data:
                    break
                msg = json.loads(data)
                with self.lock:
                    if "dir" in msg and self.snakes.get(client_id, {}).get("alive", False):
                        dx, dy = msg["dir"]
                        current_dir = self.snakes[client_id]["dir"]
                        if (dx, dy) != (-current_dir[0], -current_dir[1]):
                            self.snakes[client_id]["dir"] = (dx, dy)

                    if msg.get("respawn", False):
                        if not self.snakes.get(client_id, {}).get("alive", True):
                            pos = self.find_spawn_position()
                            self.snakes[client_id]["body"] = [
                                pos, (pos[0] - 1, pos[1]), (pos[0] - 2, pos[1])
                            ]
                            self.snakes[client_id]["dir"] = (1, 0)
                            self.snakes[client_id]["alive"] = True
                            self.snakes[client_id]["grow"] = 0
        except Exception as e:
            print(f"Client {client_id} error: {e}")
        finally:
            client.close()
            print(f"Client {client_id} disconnected")
            with self.lock:
                # Fully remove snake and client so reconnecting starts fresh
                if client_id in self.snakes:
                    del self.snakes[client_id]
                self.clients = [(cid, c) for cid, c in self.clients if cid != client_id]

    def game_loop(self):
        while True:
            time.sleep(1 / TICK_RATE)
            with self.lock:
                self.update_game()
                self.send_state()

    def update_game(self):
        for cid, s in list(self.snakes.items()):
            if not s["alive"]:
                continue

            head_x, head_y = s["body"][0]
            dx, dy = s["dir"]
            new_head = (head_x + dx, head_y + dy)

            # Check wall collision
            if not (0 <= new_head[0] < GRID_WIDTH and 0 <= new_head[1] < GRID_HEIGHT):
                s["alive"] = False
                continue

            # Self collision
            if new_head in s["body"]:
                s["alive"] = False
                continue

            # Collision with other snakes
            for ocid, osnake in self.snakes.items():
                if ocid != cid and osnake["alive"] and new_head in osnake["body"]:
                    s["alive"] = False
                    break

            if not s["alive"]:
                continue

            # Move head
            s["body"].insert(0, new_head)

            # Check apple collision
            if new_head in self.apples:
                s["grow"] += 1
                self.apples.remove(new_head)
                # Respawn apple
                while True:
                    pos = (random.randint(0, GRID_WIDTH - 1), random.randint(0, GRID_HEIGHT - 1))
                    collision = False
                    for sn in self.snakes.values():
                        if pos in sn["body"]:
                            collision = True
                            break
                    if pos in self.apples:
                        collision = True
                    if not collision:
                        self.apples.append(pos)
                        break

            # Remove tail if not growing
            if s["grow"] > 0:
                s["grow"] -= 1
            else:
                s["body"].pop()

    def send_state(self):
        state = {
            "apples": self.apples,
            "snakes": {
                cid: {
                    "body": s["body"],
                    "alive": s["alive"]
                } for cid, s in self.snakes.items()
            }
        }
        msg = json.dumps(state).encode()
        for cid, client in self.clients:
            try:
                client.sendall(msg + b"\n")
            except:
                pass

if __name__ == "__main__":
    server = GameServer()
    server.start()
