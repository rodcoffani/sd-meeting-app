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

        self.message_callback = None
        self.video_callback = None
        self.audio_callback = None
        self.lists_callback = None

    def login(self, username):
        self.username = username
        self.connect_to_broker()
        self.start_receive_threads()
        self.refresh_lists()

    def connect_to_broker(self):
        self.control_socket = self.context.socket(zmq.REQ)
        self.control_socket.connect(
            f"tcp://localhost:{config['broker']['control']['port']}"
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

    def start_receive_threads(self):
        threading.Thread(target=self._text_receive, daemon=True).start()
        threading.Thread(target=self._video_receive, daemon=True).start()
        threading.Thread(target=self._audio_receive, daemon=True).start()

    def _text_receive(self):
        while True:
            try:
                msg = self.text_sub.recv_string()
                if self.message_callback:
                    self.message_callback(msg)
            except:
                pass

    def _video_receive(self):
        while True:
            try:
                data = self.video_sub.recv()
                if self.video_callback:
                    self.video_callback(data)
            except:
                pass

    def _audio_receive(self):
        while True:
            try:
                data = self.audio_sub.recv()
                if self.audio_callback:
                    self.audio_callback(data)
            except:
                pass

    def set_message_callback(self, callback):
        self.message_callback = callback

    def set_video_callback(self, callback):
        self.video_callback = callback

    def set_audio_callback(self, callback):
        self.audio_callback = callback

    def set_lists_callback(self, callback):
        self.lists_callback = callback

    def refresh_lists(self):
        try:
            self.control_socket.send_string(f"LIST_USERS")
            users = self.control_socket.recv_string()
            self.online_users = users.split(",") if users else []

            self.control_socket.send_string(f"LIST_ROOMS")
            room_data = self.control_socket.recv_string()
            self.rooms = [r.split(":")[0] for r in room_data.split(",")] if room_data else []

            if self.lists_callback:
                self.lists_callback(self.online_users, self.rooms)
        except:
            self.online_users = []
            self.rooms = []

    def get_online_users(self):
        return self.online_users

    def get_rooms(self):
        return self.rooms

    def join_room(self, target):
        try:
            self.control_socket.send_string(f"JOIN_ROOM:{target}:{self.username}")
            resp = self.control_socket.recv_string()
            if resp == "OK":
                self.current_room = target
                self.refresh_lists()
                return True
        except:
            pass
        return False

    def create_room(self, room_name):
        try:
            self.control_socket.send_string(f"CREATE_ROOM:{room_name}")
            resp = self.control_socket.recv_string()
            if resp == "OK":
                self.current_room = room_name
                self.refresh_lists()
                return True
        except:
            pass
        return False

    def leave_room(self):
        if self.current_room:
            try:
                self.control_socket.send_string(
                    f"LEAVE_ROOM:{self.current_room}:{self.username}"
                )
                self.control_socket.recv_string()
            except:
                pass
        self.current_room = None
        self.refresh_lists()

    def send_text_message(self, message):
        if self.text_pub:
            try:
                self.text_pub.send_string(f"{self.username}: {message}")
            except:
                pass

    def send_video_frame(self, frame_data):
        if self.video_pub:
            try:
                self.video_pub.send(frame_data)
            except:
                pass

    def send_audio_data(self, audio_data):
        if self.audio_pub:
            try:
                self.audio_pub.send(audio_data)
            except:
                pass


def main():
    client = Client()
    print("Client initialized. Use interface.py to run the GUI.")


if __name__ == "__main__":
    main()