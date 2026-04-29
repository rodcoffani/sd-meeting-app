import zmq
import threading
import uuid
import yaml

client_id = str(uuid.uuid4())

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


class Client:
    def __init__(self):
        self.username = ""
        self.context = zmq.Context()

        self.control_socket = None
        self.text_pub = None
        self.text_sub = None
        self.audio_pub = None
        self.audio_sub = None
        self.video_pub = None
        self.video_sub = None

        self.online_users = []
        self.rooms = []
        self.current_room = None

    def login(self, username):
        self.username = username
        self.connect_to_broker()
        self.populate_mock_data()

    def connect_to_broker(self):
        self.control_socket = self.context.socket(zmq.REQ)
        self.control_socket.connect(
            f"tcp://localhost:{config['broker']['text']['pub_port']}"
        )

        self.text_pub = self.context.socket(zmq.PUB)
        self.text_pub.connect(f"tcp://localhost:{config['broker']['text']['sub_port']}")

        self.text_sub = self.context.socket(zmq.SUB)
        self.text_sub.connect(f"tcp://localhost:{config['broker']['text']['pub_port']}")
        self.text_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        self.audio_pub = self.context.socket(zmq.PUB)
        self.audio_pub.connect(
            f"tcp://localhost:{config['broker']['audio']['sub_port']}"
        )

        self.audio_sub = self.context.socket(zmq.SUB)
        self.audio_sub.connect(
            f"tcp://localhost:{config['broker']['audio']['pub_port']}"
        )
        self.audio_sub.setsockopt_string(zmq.SUBSCRIBE, "")

        self.video_pub = self.context.socket(zmq.PUB)
        self.video_pub.connect(
            f"tcp://localhost:{config['broker']['video']['sub_port']}"
        )

        self.video_sub = self.context.socket(zmq.SUB)
        self.video_sub.connect(
            f"tcp://localhost:{config['broker']['video']['pub_port']}"
        )
        self.video_sub.setsockopt_string(zmq.SUBSCRIBE, "")

    def populate_mock_data(self):
        self.online_users = ["user1", "user2", "user3"]
        self.rooms = ["room_001", "room_002", "meeting"]

    def get_online_users(self):
        return self.online_users

    def get_rooms(self):
        return self.rooms

    def join_room(self, target):
        if target not in self.online_users and target not in self.rooms:
            return False

        self.current_room = target
        return True

    def create_room(self, room_name):
        if room_name in self.rooms:
            return False

        self.rooms.append(room_name)
        self.current_room = room_name
        return True

    def leave_room(self):
        self.current_room = None

    def send_text_message(self, message):
        if self.text_pub:
            try:
                self.text_pub.send_string(f"{self.username}: {message}")
            except:
                pass


def main():
    client = Client()
    print("Client initialized. Use interface.py to run the GUI.")


if __name__ == "__main__":
    main()
