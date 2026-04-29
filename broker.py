import zmq
import threading
import yaml


def broker():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    context = zmq.Context()

    online_users = []
    rooms = {}

    text_pub = context.socket(zmq.PUB)
    text_pub.bind(f"tcp://*:{config['broker']['text']['pub_port']}")
    text_sub = context.socket(zmq.SUB)
    text_sub.bind(f"tcp://*:{config['broker']['text']['sub_port']}")
    text_sub.setsockopt_string(zmq.SUBSCRIBE, "")

    audio_pub = context.socket(zmq.PUB)
    audio_pub.bind(f"tcp://*:{config['broker']['audio']['pub_port']}")
    audio_sub = context.socket(zmq.SUB)
    audio_sub.bind(f"tcp://*:{config['broker']['audio']['sub_port']}")
    audio_sub.setsockopt_string(zmq.SUBSCRIBE, "")

    video_pub = context.socket(zmq.PUB)
    video_pub.bind(f"tcp://*:{config['broker']['video']['pub_port']}")
    video_sub = context.socket(zmq.SUB)
    video_sub.bind(f"tcp://*:{config['broker']['video']['sub_port']}")
    video_sub.setsockopt_string(zmq.SUBSCRIBE, "")

    control = context.socket(zmq.REP)
    control.bind(f"tcp://*:{config['broker']['control']['port']}")

    def handle_control():
        while True:
            try:
                msg = control.recv_string()
                parts = msg.split(":", 1)
                cmd = parts[0]

                if cmd == "LOGIN":
                    username = parts[1] if len(parts) > 1 else ""
                    if username and username not in online_users:
                        online_users.append(username)
                    control.send_string("OK")

                elif cmd == "LIST_USERS":
                    control.send_string(",".join(online_users))

                elif cmd == "LIST_ROOMS":
                    room_list = [f"{r}:{len(rooms[r])}" for r in rooms]
                    control.send_string(",".join(room_list))

                elif cmd == "CREATE_ROOM":
                    room_name = parts[1] if len(parts) > 1 else ""
                    if room_name and room_name not in rooms:
                        rooms[room_name] = []
                        control.send_string("OK")
                    else:
                        control.send_string("ERROR:Room exists")

                elif cmd == "JOIN_ROOM":
                    data = parts[1].split(":") if len(parts) > 1 else []
                    room_name = data[0] if data else ""
                    username = data[1] if len(data) > 1 else ""
                    if room_name in rooms and username:
                        if username not in rooms[room_name]:
                            rooms[room_name].append(username)
                        control.send_string("OK")
                    else:
                        control.send_string("ERROR:Room not found")

                elif cmd == "LEAVE_ROOM":
                    data = parts[1].split(":") if len(parts) > 1 else []
                    room_name = data[0] if data else ""
                    username = data[1] if len(data) > 1 else ""
                    if room_name in rooms and username in rooms[room_name]:
                        rooms[room_name].remove(username)
                        control.send_string("OK")
                    else:
                        control.send_string("ERROR:Room or user not found")

                else:
                    control.send_string("ERROR:Unknown command")
            except Exception as e:
                control.send_string(f"ERROR:{e}")

    def relay_media():
        poller = zmq.Poller()
        poller.register(text_sub, zmq.POLLIN)
        poller.register(audio_sub, zmq.POLLIN)
        poller.register(video_sub, zmq.POLLIN)

        while True:
            events = dict(poller.poll())

            if text_sub in events:
                msg = text_sub.recv_string()
                text_pub.send_string(msg)

            if audio_sub in events:
                data = audio_sub.recv()
                audio_pub.send(data)

            if video_sub in events:
                data = video_sub.recv()
                video_pub.send(data)

    threading.Thread(target=handle_control, daemon=True).start()
    threading.Thread(target=relay_media, daemon=True).start()

    print("Broker running...")
    relay_media()


if __name__ == "__main__":
    broker()