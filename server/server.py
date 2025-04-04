import json
import socket
from _thread import *
import uuid

class Server:
    def __init__(self, num_players, host="0.0.0.0", port=0):
        self.host = host
        self.port = port
        self.num_players = num_players
        self.server_socket = None
        self.active_clients = 0
        self.running = False
        # Game state
        self.players = {}
        self.paddles = {}
        self.lock = allocate_lock()
        self.game_state = {
            "paddles": {},
            "puck": {"position": [1280//2,720//2], "velocity": [0,0]},
            "score": {"left": 0, "right": 0}
        }


    def handle_client(self, client_socket, client_addr):
        print(f"[+] {client_addr} connected") # validate connection
        self.active_clients += 1
        player_id = None

        try:
            while True:
                # size of information we're trying to receive
                # TODO: increase if insufficient (!takes longer!)
                data = client_socket.recv(2048).decode('utf-8')
                if not data:
                    print("No data")
                    break

                message = json.loads(data)
                action = message.get('action')

                # GAME ACTION CASES

                # ---
                # PLAYER JOINS
                # ---

                if action == 'disconnect':
                    player_id = message.get('player_id')
                    break
                elif action == "join":
                    player_id = str(uuid.uuid4()) # unique

                    # register player and assign paddle
                    with self.lock:
                        if player_id not in self.players:
                            # paddle id is same as player id
                            paddle_id = player_id
                            self.players[player_id] = {"paddle_id": paddle_id, "position": None, "client_socket": client_socket}
                            # initialize paddle state having no lock (none implies available)
                            self.paddles[paddle_id] = {"locked_by": None, "position": None}
                            self.game_state["paddles"][paddle_id] = {"position": [0, 0], "velocity": [0, 0]}
                            print(f"Player {player_id} joined with paddle {paddle_id}")
                        else:
                            # player rejoins/already exists
                            paddle_id = self.players[player_id]["paddle_id"]

                    # acknowledge
                    ack = json.dumps({"action": "join_ack", "player_id": player_id, "paddle_id": paddle_id, "game_state": self.game_state})
                    client_socket.sendall(ack.encode('utf-8'))
                    self.broadcast_game_state()

                # ---
                # Other actions (besides "join")
                # ---
                else:
                    # requires player_id
                    player_id = message.get("player_id")
                    if not player_id or player_id not in self.players:
                        # reject requests without valid player_id
                        error_msg = json.dumps({
                            "action": "error",
                            "message": "Invalid or missing player_id"
                        })
                        client_socket.sendall(error_msg.encode('utf-8'))
                        self.broadcast_game_state()
                        continue

                    # ---
                    # UPDATE POSITION
                    # ---
                    if action == "update_position":
                        # client sends position for its player's paddle
                        player_id = message.get("player_id")
                        position = message.get("position")

                        with self.lock:
                            if player_id in self.players:
                                paddle_id = self.players[player_id]["paddle_id"]
                                self.players[player_id]["position"] = position
                                self.paddles[paddle_id]["position"] = position
                                self.game_state["paddles"][paddle_id]["position"] = position
                                print(f"Updated position for player {player_id}'s paddle {paddle_id} to {position}")

                        #acknowledge
                        ack = json.dumps({"action": "update_ack", "player_id": player_id})
                        client_socket.sendall(ack.encode('utf-8'))
                        self.broadcast_game_state()

                    # ---
                    # GRAB PADDLE
                    # ---
                    elif action == "grab_paddle":
                        # client wants to lock this paddle
                        player_id = message.get("player_id")
                        requested_paddle = message.get("paddle_id")

                        with self.lock:
                            if requested_paddle in self.paddles: # paddle exists
                                if self.paddles[requested_paddle]["locked_by"] is None: # paddle not alr claimed
                                    self.paddles[requested_paddle]["locked_by"] = player_id
                                    self.players[player_id]["paddle_id"] = requested_paddle

                                    print(f"Player {player_id} successfully grabbed paddle {requested_paddle}")
                                    ack = json.dumps({
                                        "action": "grab_ack",
                                        "status": "success",
                                        "paddle_id": requested_paddle
                                    })
                                else: # paddle alr claimed
                                    print(f"Player {player_id} failed to grab paddle {requested_paddle} (already locked)")
                                    ack = json.dumps({
                                        "action": "grab_ack",
                                        "status": "failed",
                                        "paddle_id": requested_paddle,
                                        "reason": "paddle already locked"
                                    })
                            else: # paddle doesnt exist
                                print(f"Player {player_id} requested to grab invalid paddle")
                                ack = json.dumps({
                                    "action": "grab_ack",
                                    "status": "failed",
                                    "paddle_id": requested_paddle,
                                    "reason": "invalid paddle"
                                })
                        client_socket.sendall(ack.encode('utf-8'))
                        self.broadcast_game_state()

                    # ---
                    # RELEASE PADDLE
                    # ---
                    elif action == "release_paddle":
                        # client wants to release this paddle
                        player_id = message.get("player_id")
                        released_paddle = message.get("paddle_id")

                        with self.lock:
                            if released_paddle in self.paddles: # paddle exists
                                if self.paddles[released_paddle]["locked_by"] == player_id: # ensure paddle alr claimed (by this player)
                                    self.paddles[released_paddle]["locked_by"] = None

                                    print(f"Player {player_id} released paddle {released_paddle}")
                                    ack = json.dumps({
                                        "action": "release_ack",
                                        "status": "success",
                                        "paddle_id": released_paddle
                                    })
                                # TODO: server needs to retry releasing until it works (no fail case possible)
                                else:# paddle alr claimed (by other player)
                                    print(f"Player {player_id} failed to release paddle {released_paddle} (already locked)")
                                    ack = json.dumps({
                                        "action": "release_ack",
                                        "status": "failed",
                                        "paddle_id": released_paddle,
                                        "reason": "you do not own this paddle"
                                    })
                            else: # paddle doesnt exist
                                print(f"Player {player_id} requested to release invalid paddle")
                                ack = json.dumps({
                                    "action": "release_ack",
                                    "status": "failed",
                                    "reason": "invalid paddle"
                                })
                        client_socket.sendall(ack.encode('utf-8'))
                        self.broadcast_game_state()

        except Exception as e:
            print(f"[-] Error: {e}")

        finally:
            if player_id:
                with self.lock:
                    if player_id in self.players:
                        paddle_id = self.players[player_id]['paddle_id']
                        # remove player and corresponding paddle
                        del self.players[player_id]
                        del self.paddles[paddle_id]
                        del self.game_state["paddles"][paddle_id]
                print(f"[-] {client_addr} disconnected")
                client_socket.close()
                self.active_clients -= 1
                self.broadcast_game_state()

            # shutdown if no clients
            if self.active_clients == 0:
                print("[*] No active clients. Shutting down server.")
                self.stop_server()


    def start_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind((self.host, self.port))
            self.running = True
            # see if anything on port
            self.server_socket.listen()
            print(f"Server started, listening on {self.host}:{self.get_port_num()}")

            # continuously look for connections
            while self.running:
                try:
                    # accept new connection
                    client_socket, client_addr = self.server_socket.accept()
                    print("Connection from: ", client_addr)

                    start_new_thread(self.handle_client, (client_socket, client_addr))
                except Exception as e:
                    if not self.running:
                        break
        except KeyboardInterrupt:
            print("\nServer shutting down...")

    # send game state to all connected clients
    def broadcast_game_state(self):
        with self.lock:
            game_state_message = json.dumps({
                "action": "state_update",
                "game_state": self.game_state
            })
            for player in self.players.values():
                player["client_socket"].sendall(game_state_message.encode('utf-8'))

    # ---
    # scoring
    # ---
    def handle_goal(self, scoring_side):
        with self.lock:
            if scoring_side == "left":
                self.game_state["score"]["left"] += 1
            elif scoring_side == "right":
                self.game_state["score"]["right"] += 1
            self.reset_puck()
            self.broadcast_game_state()

    def reset_puck(self):
        self.game_state["puck"]["position"] = [1280 // 2, 720 // 2]
        self.game_state["puck"]["velocity"] = [0, 0]


    def stop_server(self):
        """Stops the server."""
        if self.server_socket:
            self.running = False
            self.server_socket.close()
            self.server_socket = None
        print("Server stopped.")

    def get_port_num(self):
        """returns dynamicly assigned port number after bind"""
        if self.server_socket is not None:
            return self.server_socket.getsockname()[1]
        return None


if __name__ == "__main__":
    server = Server(num_players=2) #initalized with 2 players
    server.start_server()
