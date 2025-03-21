import json
import socket
from _thread import *


class Server:
    def __init__(self, num_players, host="0.0.0.0", port=0):
        self.host = host
        self.port = port
        self.num_players = num_players
        self.server_socket = None
        self.active_clients = 0

        # Game state
        self.players = {}
        self.paddles = {}
        self.lock = allocate_lock()
        # TODO: have server loop and try multiple ports if default in use


    def handle_client(self, client_socket, client_addr):
        print(f"[+] {client_addr} connected") # validate connection
        self.active_clients += 1

        while True:
            try:
                # size of information we're trying to receive
                # TODO: increase if insufficient (!takes longer!)
                data = client_socket.recv(2048).decode('utf-8')
                if not data:
                    print("No data")
                    break

                message = json.loads(data)
                action = message.get('action')
                player_id = message.get('player_id') # unique

            # ----
            # TODO: handle game action cases
            # ex. join, update position, grab/lock paddle, release paddle, etc.
            # ----

            except Exception as e:
                print(f"[-] Error: {e}")
                break

        # remove player
        with self.lock:
            if player_id in self.players:
                paddle_id = self.players[player_id]['paddle_id']
                # remove player and corresponding paddle
                del self.players[player_id]
                del self.addles[paddle_id]
        print(f"[-] {client_addr} disconnected")
        client_socket.close()
        self.active_clients -=1

        # shutdown if no clients
        if self.active_clients == 0:
            print("[*] No active clients. Shutting down server.")
            self.stop_server()


    def start_server(self):

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.bind((self.host, self.port))

            # see if anything on port
            self.server_socket.listen()
            print(f"Server started, listening on {self.host}:{self.get_port_num()}")

            # continuously look for connections
            while True:
                # accept new connection
                client_socket, client_addr = self.server_socket.accept()
                print("Connection from: ", client_addr)

                start_new_thread(self.handle_client, (client_socket, client_addr))

        except KeyboardInterrupt:
            print("\nServer shutting down...")


    def stop_server(self):
        """Stops the server."""
        if self.server_socket:
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
