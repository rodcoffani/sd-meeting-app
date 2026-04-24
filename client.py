import zmq
import threading
import uuid
import yaml
import pyaudio
import cv2
import numpy as np
import time

client_id = str(uuid.uuid4())

# Load config
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)


def text_publisher(context):
    socket = context.socket(zmq.PUB)
    socket.connect(f"tcp://localhost:{config['broker']['text']['sub_port']}")
    time.sleep(1)
    while True:
        msg = input("[Text] > ")
        socket.send_string(f"{client_id}: {msg}")


def text_subscriber(context):
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{config['broker']['text']['pub_port']}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    while True:
        msg = socket.recv_string()
        print(f"[Text] Received: {msg}")


def audio_publisher(context):
    socket = context.socket(zmq.PUB)
    socket.connect(f"tcp://localhost:{config['broker']['audio']['sub_port']}")
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=config['client']['audio']['channels'],
                    rate=config['client']['audio']['rate'],
                    input=True,
                    frames_per_buffer=config['client']['audio']['chunk'])
    while True:
        data = stream.read(config['client']['audio']['chunk'])
        socket.send(data)


def audio_subscriber(context):
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{config['broker']['audio']['pub_port']}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16,
                    channels=config['client']['audio']['channels'],
                    rate=config['client']['audio']['rate'],
                    output=True)
    while True:
        data = socket.recv()
        stream.write(data)


def video_publisher(context):
    socket = context.socket(zmq.PUB)
    socket.connect(f"tcp://localhost:{config['broker']['video']['sub_port']}")
    cap = cv2.VideoCapture(config['client']['video']['device_index'])
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config['client']['video']['frame_width'])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config['client']['video']['frame_height'])
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        _, buffer = cv2.imencode('.jpg', frame)
        socket.send(buffer)


def video_subscriber(context):
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{config['broker']['video']['pub_port']}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    while True:
        buffer = socket.recv()
        frame = cv2.imdecode(np.frombuffer(buffer, dtype=np.uint8), 1)
        cv2.imshow("Video", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break


if __name__ == "__main__":
    context = zmq.Context()

    threading.Thread(target=text_publisher, args=(context,)).start()
    threading.Thread(target=text_subscriber, args=(context,)).start()
    threading.Thread(target=audio_publisher, args=(context,)).start()
    threading.Thread(target=audio_subscriber, args=(context,)).start()
    threading.Thread(target=video_publisher, args=(context,)).start()
    threading.Thread(target=video_subscriber, args=(context,)).start()
