# SD Meeting App

Sistema de videoconferência distribuído, resiliente e escalável, construído com Python 3 e ZeroMQ.

## Integrantes

| Nome | RA |
|---|---|
| Rodrigo Coffani | 800345 |
| Pedro Yuji Teixeira Harada | 800636 |
| Murilo de Miranda Silva | 812069 |
| Guilherme Barbosa | 811692 |
| Sérgio Felipe Bezerra Rabelo | 812205 |

---

## Visão geral

```
┌──────────────────────────────────────────────────────┐
│                      Registry                        │  ← Service Discovery (REQ/REP)
│                  (porta 5500)                        │
└──────────────┬───────────────────────────────────────┘
               │ register / heartbeat / query_room
       ┌───────┴────────┐
       ▼                ▼
┌─────────────┐   ┌─────────────┐       Inter-broker
│  Broker-0   │◄─►│  Broker-1   │  ←  ROUTER/DEALER + heartbeat PUB/SUB
│  Salas A-D  │   │  Salas E-H  │
└──────┬──────┘   └──────┬──────┘
       │ PULL/PUB        │ PULL/PUB
  ┌────┴────┐       ┌────┴────┐
  │  alice  │       │  carol  │   ← PUSH/SUB/DEALER (texto, áudio, vídeo)
  │   bob   │       │         │
  └─────────┘       └─────────┘
```

### Padrões ZeroMQ utilizados

| Padrão | Sockets | Uso |
|---|---|---|
| **PUSH → PULL** | Cliente → Broker | Envio de mídia (texto, áudio, vídeo) com backpressure |
| **PUB → SUB** | Broker → Clientes | Distribuição por sala (topic filter `"text:A"`, `"audio:F"`) |
| **DEALER ↔ ROUTER** | Cliente ↔ Broker | Controle: login, ACK de texto, presença, leave |
| **DEALER → ROUTER** | Broker → Broker | Relay inter-broker (mensagens para salas de outros brokers) |
| **PUB → SUB** | Broker → Broker | Heartbeat entre brokers (topic `"hb"`) |
| **REQ → REP** | Brokers/Clientes → Registry | Service discovery, registro, heartbeat |

### QoS por tipo de mídia

| Canal | Estratégia |
|---|---|
| **Texto** | ACK do broker + reenvio automático (até 5 tentativas, intervalo 200 ms) |
| **Áudio** | Sem garantia — real-time, tolerante a perda de pacotes |
| **Vídeo** | FPS e qualidade JPEG adaptativos (15→5 fps, 70%→30%) via backpressure |

---

## Estrutura de arquivos

```
sd-meeting-app/
├── registry.py       ← Service Discovery (REQ/REP)
├── broker.py         ← Broker distribuído com rooms, QoS, inter-broker, heartbeat
├── client.py         ← Cliente CLI resiliente com reconexão automática
├── client_gui.py     ← Cliente com interface gráfica (Tkinter)
├── run_demo.py       ← Demo automatizado: falha de broker + reconexão
├── config.yaml       ← Configurações de portas, QoS, salas e cluster
├── requirements.txt  ← Dependências Python
├── run_registry.sh   ← Atalho para subir o registry
├── run_broker.sh     ← Atalho para subir um broker (aceita índice)
├── run_client.sh     ← Atalho para subir o cliente CLI
└── run_demo.sh       ← Atalho para a demo
```

---

## Pré-requisitos

- Python 3.11+
- Sistema Debian/Ubuntu (ou WSL no Windows)
- Microfone e câmera (opcionais — o sistema funciona em modo texto sem hardware)

---

## Instalação (primeira vez)

```bash
cd ~/sd-meeting-app

# Criar ambiente virtual e instalar dependências
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> **No Windows (PowerShell):** instale as dependências no Python nativo do Windows
> para ter suporte a câmera e áudio:
> ```powershell
> pip install pyzmq opencv-python PyAudio Pillow PyYAML numpy
> ```

---

## Como rodar

### Opção 1 — Demo automatizado 

Executa tudo automaticamente: registry, 2 brokers, 3 clientes, simula falha de broker e reconexão.

```bash
source venv/bin/activate
python3 run_demo.py

# Com pausas mais longas entre os passos:
python3 run_demo.py --slow
```

---

### Opção 2 — Manual com interface gráfica

Abra **4 terminais**:

**Terminal 1 — Registry (service discovery):**
```bash
cd ~/sd-meeting-app && source venv/bin/activate
python3 registry.py
```

**Terminal 2 — Broker-0 (gerencia salas A, B, C, D):**
```bash
cd ~/sd-meeting-app && source venv/bin/activate
python3 broker.py 0
```

**Terminal 3 — Broker-1 (gerencia salas E, F, G, H):**
```bash
cd ~/sd-meeting-app && source venv/bin/activate
python3 broker.py 1
```

**Terminal 4 — Cliente com GUI:**
```bash
cd ~/sd-meeting-app && source venv/bin/activate
python3 client_gui.py
```

Repita o Terminal 4 quantas vezes quiser para ter múltiplos participantes.

---

### Opção 3 — Manual com cliente CLI (sem interface gráfica)

Mesmos terminais 1, 2 e 3 acima. Para o cliente:

```bash
# Usuário alice na sala A (sem áudio/vídeo — modo texto puro)
python3 client.py --username alice --room A --no-av

# Usuário bob na sala A (com áudio e vídeo se hardware disponível)
python3 client.py --username bob --room A

# Usuário carol na sala F (broker diferente do alice e bob)
python3 client.py --username carol --room F --no-av
```

> Adicione `2>/dev/null` para suprimir mensagens de erro do ALSA/JACK no WSL.

---

### Opção 4 — Scripts shell

```bash
chmod +x run_registry.sh run_broker.sh run_client.sh run_demo.sh

./run_registry.sh              # terminal 1
./run_broker.sh 0              # terminal 2 — broker para salas A-D
./run_broker.sh 1              # terminal 3 — broker para salas E-H
./run_client.sh --username alice --room A --no-av   # terminal 4
./run_demo.sh                  # OU: demo completo em 1 terminal
```

---

## Distribuição de salas por broker

| Broker | Índice | Salas | Portas (pub/pull/ctrl) |
|---|---|---|---|
| Broker-0 | `0` | A, B, C, D | 5551–5560 |
| Broker-1 | `1` | E, F, G, H | 5651–5660 |
| Broker-2 | `2` | I, J, K    | 5751–5760 |
| Registry | — | — | 5500 |

Para subir um terceiro broker:
```bash
python3 broker.py 2
```

---

## Testando tolerância a falhas

Com o sistema rodando (manual ou demo), simule uma falha:

1. Identifique o PID do broker-0: veja no terminal onde ele está rodando
2. Mate o processo:
   ```bash
   kill -9 <PID>
   # ou simplesmente Ctrl+C no terminal do broker
   ```
3. Aguarde ~8 segundos — clientes detectam via heartbeat timeout
4. Suba um novo broker na mesma posição:
   ```bash
   python3 broker.py 0
   ```
5. Clientes reconectam automaticamente

---

## Interface gráfica — controles

| Botão | Ação |
|---|---|
| 🎤 Mutar mic | Para de enviar áudio (microfone silenciado) |
| 📷 Câmera off | Para de enviar vídeo (self-preview mostra placeholder) |
| 🔊 Audio off | Para de reproduzir o áudio recebido |
| 🚪 Sair | Sai da sala com confirmação, volta para login |

A reconexão após falha de broker é automática — a janela mostra "⚠ Reconectando..." e se recupera sem intervenção do usuário.

---

## Observações sobre WSL

No WSL (Windows Subsystem for Linux), câmera e áudio não estão disponíveis por padrão. Use `--no-av` no cliente CLI ou simplesmente ignore os erros do ALSA — o chat de texto funciona normalmente.

Para testar áudio e vídeo no Windows, rode o `client_gui.py` diretamente no Python nativo do Windows (com as dependências instaladas via `pip` no PowerShell), enquanto registry e brokers ficam no WSL — o `localhost` é compartilhado entre os dois ambientes.
