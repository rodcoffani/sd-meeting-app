import zmq
import yaml


def broker():
    # Load config
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    context = zmq.Context()

    # --- Socket Setup ---
    # Text channel
    text_pub = context.socket(zmq.PUB)
    text_pub.bind(f"tcp://*:{config['broker']['text']['pub_port']}")
    text_sub = context.socket(zmq.SUB)
    text_sub.bind(f"tcp://*:{config['broker']['text']['sub_port']}")
    text_sub.setsockopt_string(zmq.SUBSCRIBE, "")

    # Audio channel
    audio_pub = context.socket(zmq.PUB)
    audio_pub.bind(f"tcp://*:{config['broker']['audio']['pub_port']}")
    audio_sub = context.socket(zmq.SUB)
    audio_sub.bind(f"tcp://*:{config['broker']['audio']['sub_port']}")
    audio_sub.setsockopt_string(zmq.SUBSCRIBE, "")

    # Video channel
    video_pub = context.socket(zmq.PUB)
    video_pub.bind(f"tcp://*:{config['broker']['video']['pub_port']}")
    video_sub = context.socket(zmq.SUB)
    video_sub.bind(f"tcp://*:{config['broker']['video']['sub_port']}")
    video_sub.setsockopt_string(zmq.SUBSCRIBE, "")

    # --- Poller Setup ---
    poller = zmq.Poller()
    poller.register(text_sub, zmq.POLLIN)
    poller.register(audio_sub, zmq.POLLIN)
    poller.register(video_sub, zmq.POLLIN)

    print("Broker running (Poller Mode)...")

    while True:
        # poll() returns a list of sockets that have data ready
        events = dict(poller.poll())

        # Check Text Channel
        if text_sub in events:
            msg = text_sub.recv_string()
            text_pub.send_string(msg)

        # Check Audio Channel
        if audio_sub in events:
            msg = audio_sub.recv()
            audio_pub.send(msg)

        # Check Video Channel
        if video_sub in events:
            msg = video_sub.recv()
            video_pub.send(msg)


if __name__ == "__main__":
    broker()
