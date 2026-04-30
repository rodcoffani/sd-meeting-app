# SD Meeting App

Sistema de videoconferência distribuído, resiliente e escalável, construído com Python 3 e ZeroMQ.

## Integrantes

| Nome                         | RA     |
| ---------------------------- | ------ |
| Rodrigo Coffani              | 800345 |
| Pedro Yuji Teixeira Harada   | 800636 |
| Murilo de Miranda Silva      | 812069 |
| Guilherme Barbosa            | 811692 |
| Sérgio Felipe Bezerra Rabelo | 812205 |

## Pré-requisitos

- Python 3.11+
- Sistema Linux (ou WSL/PowerShell no Windows)
- Microfone e câmera (opcionais)

## Instalação

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## Como rodar

**Demo automatizado** (tudo em um comando):

```bash
source venv/bin/activate && python3 run_demo.py
```

**Manual com GUI** (abra 4 terminais):

```bash
# Terminal 1: Registry
python3 registry.py
# Terminal 2: Broker-0
python3 broker.py 0
# Terminal 3: Broker-1
python3 broker.py 1
# Terminal 4+: Clientes
python3 client_gui.py
```

**Manual com CLI** (abra 4 terminais como acima, terminal 4+):

```bash
python3 client.py --username alice --room A
python3 client.py --username bob --room B --no-av
```

**Scripts shell** (alternativamente):

```bash
chmod +x run_*.sh
./run_registry.sh &
./run_broker.sh 0 &
./run_broker.sh 1 &
./run_client.sh --username alice --room A
```

Veja [PLAN.md](PLAN.md) para arquitetura técnica completa, QoS, padrões ZMQ e detalhes de implementação.
