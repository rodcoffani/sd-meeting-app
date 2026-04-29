# PLAN - Distributed Meeting App

## Project Overview

A distributed video conferencing application supporting video, audio, and text communication.
Multiple users can participate in individual calls or group rooms.
Built in Python 3 with ZeroMQ for async communication.

---

## Step 0: User Interface

### 0.1 Goal

Build a GUI for login and room management using **tkinter**

### 0.2 Login Screen

- Username input field
- "Connect" button

### 0.3 Main Screen (Before Call)

```txt
┌─────────────────────────────────────────────────────────────┐
│  SD Meeting App                        [User: username]     │
├─────────────────────────────────────────────────────────────┤
│                     VIDEO PREVIEW                           │
│            ┌───────────────────────────────────┐            │
│            │                                   │            │
│            │       (local camera feed)         │            │
│            │                                   │            │
│            └───────────────────────────────────┘            │
├─────────────────────────────────────────────────────────────┤
│                    ONLINE USERS          ROOMS              │
│   ┌────────────────────┐         ┌────────────────────┐     │
│   │ User 1             │         │ room_001           │     │
│   │ User 2             │         │ room_002           │     │
│   │ User 3             │         │ meeting            │     │
│   └────────────────────┘         └────────────────────┘     │
├─────────────────────────────────────────────────────────────┤
│ Connect to: [________________] [Join] [Create room]         │
└─────────────────────────────────────────────────────────────┘
```

### 0.4 Call Screen (Replaces Main During Call)

```txt
┌──────────────────────────────────────────────────────────────┐
│  SD Meeting App - room_001                 [Leave]           │
├──────────────────────────────────────────────────────────────┤
│                     VIDEO AREA                               │
│  ┌──────────────────────────┐  ┌─────────────────────────┐   │
│  │                          │  │                         │   │
│  │    (remote video 1)      │  │    (remote video 2)     │   │
│  │                          │  │                         │   │
│  └──────────────────────────┘  └─────────────────────────┘   │
├──────────────────────────────────────────────────────────────┤
│ CHAT                                                         │
│ ┌─────────────────────────────────────────────────────────┐  │
│ │ User1: Hello                                            │  │
│ │ User2: Hi!                                              │  │
│ └─────────────────────────────────────────────────────────┘  │
│ Text: [____________________________________________] [Send]  │
└──────────────────────────────────────────────────────────────┘
```

### 0.5 Interface Requirements

| Component              | Description                                        |
| ---------------------- | -------------------------------------------------- |
| **Video Preview**      | Shows local camera (before/during call)            |
| **Online Users**       | Left column - displays logged-in users             |
| **Rooms**              | Right column - displays available rooms            |
| **Input field**        | Enter room name or username to connect to          |
| **Join button**        | Join existing room or start 1:1 call               |
| **Create room button** | Create new room (name must be unique)              |
| **Leave button**       | Exit current room/call (shown during call)         |
| **Chat area**          | Text messages (replaces participants list in call) |
| **Send button**        | Send text message in chat                          |

### 0.6 Key Points

- **No participants list** - replaced by chat area during call
- **No polling** - participants know they're connected by video/audio
- **Same window** - video and chat together
- **Room names must be unique** - if duplicate, show error
- **Leave button** - available during call and from main screen

### 0.7 Flow

1. Login → enter username → connect
2. Main screen → shows video preview + online users + rooms
3. Enter target in text field
4. Click **Join** or **Create room**
5. Call screen replaces main screen
6. Click **Leave** to exit call

---

## Step 1: Dynamic Architecture with Multiple Brokers

### 1.1 Goal

Implement multiple brokers (none room-specific) that communicate via ZeroMQ, with brokers selected via round-robin

### 1.2 Approach

- **Multiple equal brokers** - any broker can handle any room or individual call
- **Registry broker** - tracks available brokers and rooms (can be one of the brokers)
- **Router/Dealer** pattern for client control messages
- **PUB/SUB** for media distribution
- Room assigned to broker via round-robin when created

### 1.3 Architecture

```txt
┌─────────────────────────────────────────────────┐
│                Registry Broker                  │
│  ┌───────────────────────────────────────────┐  │
│  │  Broker Registry                          │  │
│  │  - broker_1: {addr, load, rooms}          │  │
│  │  - broker_2: {addr, load, rooms}          │  │
│  └───────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────┐  │
│  │  Room Registry                            │  │
│  │  - room_001: {broker_1, [user1, user2]}   │  │
│  │  - room_002: {broker_2, [user3]}          │  │
│  │  - call_1:1: {broker_1, [user1, user4]}   │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
         ▲                        ▲
         │                        │
┌────────┴────────┐    ┌────────┴────────┐
│   Broker 1      │◄──►│   Broker 2      │
│  (handles rooms │    │  (handles rooms │
│   assigned to   │    │   assigned to   │
│   it)           │    │   it)           │
└─────────────────┘    └─────────────────┘
         │                        │
┌────────┴────────┐    ┌────────┴────────┐
│   Client 1      │    │   Client 2      │
│   (user1)       │    │   (user3)       │
└─────────────────┘    └─────────────────┘
```

### Implementation Details

- All brokers equal, none room-specific
- Registry maintains broker list and room-to-broker mapping
- Inter-broker communication via ZeroMQ (PUB/SUB or Router) for state sync
- Message types:
  - `BROKER_REGISTER` - Broker registers with registry
  - `ROOM_CREATE` - Request room creation (registry assigns broker)
  - `JOIN_ROOM` - Join existing room

---

## Step 2: Service Discovery with Broadcast

### 2.1 Goal

Clients discover available brokers via broadcast and are assigned via round-robin

### 2.2 Approach

- Use **broadcast discovery**: Client broadcasts on a well-known port
- Registry maintains list of available brokers with their load
- Client receives broker list from registry, selects via round-robin

### 2.3 Process

1. Client broadcasts `DISCOVER_BROKER` message
2. Registry responds with `BROKER_LIST` (list of available brokers)
3. Client selects broker via round-robin from list
4. Client connects to selected broker for room/media

### 2.4 Registry State

- Maintains `{broker_id: {addr, load, status}}` - available brokers
- Maintains `{room_id: {broker_id, users: [user_ids]}}` - active rooms
- Maintains `{user_id: broker_id}` - user-to-broker mapping
- On room create → assign broker with lowest load (round-robin)
- On room join → notify broker handling that room

### 2.5 Message Types

- `DISCOVER_BROKER` - Client broadcasts to find broker
- `BROKER_AVAILABLE` - Broker responds with address/ports
- `LIST_ROOMS` - Request list of active rooms
- `ROOM_INFO` - Response with room details

---

## Step 3: Fault Tolerance with Heartbeat

### 3.1 Goal

Detect broker failures and reconnect

### 3.2 Approach

- Heartbeat via **REQ/REP** every **3 seconds**
- Client pings broker; broker responds with `PONG`
- If 3 consecutive pings fail → broker considered dead

### 3.3 Implementation

```python
# Client side
HEARTBEAT_INTERVAL = 3  # seconds
MAX_MISSES = 3

def heartbeat_thread(socket):
    while True:
        try:
            socket.send_string("PING")
            socket.recv_string(zmq.NOBLOCK)
            consecutive_misses = 0
        except:
            consecutive_misses += 1
            if consecutive_misses >= MAX_MISSES:
                reconnect()
        sleep(HEARTBEAT_INTERVAL)
```

### 3.4 Failover

- On broker failure, client re-broadcasts to find new broker
- Registry reassigns rooms from failed broker to available brokers
- If client was in room, client rejoins via new broker

---

## Step 4: QoS Implementation

### 4.1 Goal

Ensure quality per media type

| Media | Requirement   | Implementation                           |
| ----- | ------------- | ---------------------------------------- |
| Text  | Reliability   | Retry + Acknowledgment                   |
| Audio | Low latency   | Buffer with timestamps, drop late frames |
| Video | Adaptive rate | Frame drop (skip every Nth frame)        |

### 4.2 Text (Reliability)

- Add sequence numbers to messages
- Sender retries if no ACK within timeout
- Receiver ACKs each message

### 4.3 Audio (Buffer + Latency)

```python
# Buffer with timestamps
audio_buffer = deque(maxlen=10)

def play_audio(data):
    recv_time = time.time()
    # Sort by timestamp, play in order
    audio_buffer.append((data.timestamp, data))
    audio_buffer.sort()
    play(audio_buffer[0])

# Drop frames older than 100ms
```

### 4.4 Video (Adaptive Frame Drop)

```python
# Skip frames under high load
frame_counter = 0
drop_every_n = 1

def should_drop_frame():
    global drop_every_n
    if load > threshold:
        drop_every_n = 2  # drop every other frame
    else:
        drop_every_n = 1
    return frame_counter % drop_every_n != 0
```

---

## Step 5: Async with Threading

### 5.1 Goal

Separate capture, send, receive, render into independent threads

### 5.2 Thread Architecture

```txt
Main Thread (control)
├── Text Threads
│   ├── text_capture_thread  → input() → send
│   └── text_render_thread   ← receive → print
├── Audio Threads
│   ├── audio_capture_thread → read mic → send
│   └── audio_render_thread  ← receive → play speaker
└── Video Threads
    ├── video_capture_thread → read cam → send
    └── video_render_thread   ← receive → display
```

### 5.3 Implementation

```python
threads = []

# Start all threads
threads.append(threading.Thread(target=text_capture, args=(ctx,)))
threads.append(threading.Thread(target=text_render, args=(ctx,)))
threads.append(threading.Thread(target=audio_capture, args=(ctx,)))
threads.append(threading.Thread(target=audio_render, args=(ctx,)))
threads.append(threading.Thread(target=video_capture, args=(ctx,)))
threads.append(threading.Thread(target=video_render, args=(ctx,)))

for t in threads:
    t.start()
```

### 5.4 Thread-safe Queues

```python
from queue import Queue

text_queue = Queue()
audio_queue = Queue()
video_queue = Queue()
```

---

## Step 6: Identity and Room Management

### 6.1 Goal

Minimal login (username only), show online users and existing rooms

### 6.2 Login

```python
# Simple login on startup
username = input("Enter username: ")
socket.send_string(f"LOGIN:{username}")
```

### 6.3 Online Users

- Broker maintains `{user_id: socket}`
- On LOGIN → add to active users
- On DISCONNECT → remove
- `LIST_USERS` command returns all online users

### 6.4 Room Commands

- `CREATE_ROOM:<room_name>` - Create new room
- `JOIN_ROOM:<room_name>` - Join existing room
- `LEAVE_ROOM` - Leave current room
- `LIST_ROOMS` - List available rooms

### 6.5 Implementation in Broker

```python
rooms = {}  # {room_id: {users: [], broker_addr: str}}
online_users = {}  # {user_id: socket}
```

---

## Configuration

All settings managed via `config.yaml`:

```yaml
broker:
  discovery:
    broadcast_port: 5550
  registry:
    pub_port: 5551
    sub_port: 5552
  text:
    pub_port: 5553
    sub_port: 5554
  audio:
    pub_port: 5555
    sub_port: 5556
  video:
    pub_port: 5557
    sub_port: 5558

client:
  audio:
    rate: 44100
    channels: 1
    chunk: 1024
  video:
    device_index: 0
    frame_width: 640
    frame_height: 480
  heartbeat:
    interval: 3
    max_misses: 3

qos:
  text:
    retry_timeout: 2
  audio:
    buffer_size: 10
    max_latency_ms: 100
  video:
    frame_drop_threshold: 0.8
```

---

## Message Protocol

### Control Messages (Client ↔ Broker)

```txt
DISCOVER_BROKER -> BROKER_LIST
LOGIN:<username> -> OK
LIST_ROOMS -> room1,room2
CREATE_ROOM:<room_id> -> OK:<broker_addr>
JOIN_ROOM:<room_id> -> OK
LEAVE_ROOM -> OK
PING -> PONG
```

### Inter-Broker Messages (Broker ↔ Registry)

```txt
BROKER_REGISTER:<broker_id>:<addr> -> OK
BROKER_HEARTBEAT -> OK
ROOM_CREATE:<room_id> -> ASSIGN_BROKER:<broker_id>
ROOM_JOIN:<room_id> -> OK
ROOM_LEAVE:<room_id> -> OK
```

### Media Messages

```txt
TEXT:<seq>:<timestamp>:<content>
AUDIO:<seq>:<timestamp>:<data>
VIDEO:<seq>:<timestamp>:<frame_data>
```

---

## Execution Flow

### Starting the System

1. Start Registry Broker (runs first):

   ```bash
   ./run_broker.sh --registry
   ```

2. Start Worker Brokers (any number):

   ```bash
   ./run_broker.sh  # worker broker, registers with registry
   ```

3. Start Clients:

   ```bash
   ./run_client.sh
   ```

### Client Flow

1. User enters username
2. Client broadcasts to discover brokers
3. Registry responds with broker list
4. Client selects broker via round-robin
5. Client connects, creates/joins room
6. Media flows via broker's pub/sub channels
7. User can create/join rooms or call individual users
8. Media flows via pub/sub channels

---

## Dependencies

- Python 3.x
- pyzmq
- pyaudio
- opencv-python
- numpy
- pyyaml
