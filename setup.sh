#!/bin/bash

# ============================================================
#  setup.sh — Configuração automática do ambiente
#  Sistemas Distribuídos - core_distribuidos
# ============================================================

set -e  # Para o script se qualquer comando falhar

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup - core_distribuidos${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ------------------------------------------------------------
# 1. Verifica se python3 está instalado
# ------------------------------------------------------------
echo -e "${YELLOW}[1/5] Verificando Python3...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Python3 não encontrado. Instalando...${NC}"
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pip python3-venv
else
    echo -e "${GREEN}  Python3 encontrado: $(python3 --version)${NC}"
fi

# ------------------------------------------------------------
# 2. Verifica dependências do sistema (PortAudio + ufw)
# ------------------------------------------------------------
echo ""
echo -e "${YELLOW}[2/5] Verificando dependências do sistema...${NC}"

if ! dpkg -s portaudio19-dev &> /dev/null; then
    echo "  Instalando PortAudio (necessário para pyaudio)..."
    sudo apt-get update -qq
    sudo apt-get install -y portaudio19-dev
else
    echo -e "${GREEN}  PortAudio já instalado.${NC}"
fi

if ! dpkg -s pulseaudio &> /dev/null; then
    echo "  Instalando PulseAudio..."
    sudo apt-get install -y pulseaudio
else
    echo -e "${GREEN}  PulseAudio já instalado.${NC}"
fi

# ------------------------------------------------------------
# 3. Cria a venv (se ainda não existir)
# ------------------------------------------------------------
echo ""
echo -e "${YELLOW}[3/5] Configurando ambiente virtual (venv)...${NC}"

VENV_DIR="venv"

if [ -d "$VENV_DIR" ]; then
    echo -e "${GREEN}  venv já existe. Pulando criação.${NC}"
else
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}  venv criada em ./$VENV_DIR${NC}"
fi

# Ativa a venv
source "$VENV_DIR/bin/activate"
echo -e "${GREEN}  venv ativada.${NC}"

# ------------------------------------------------------------
# 4. Instala as bibliotecas Python
# ------------------------------------------------------------
echo ""
echo -e "${YELLOW}[4/5] Instalando bibliotecas Python...${NC}"

pip install --upgrade pip -q
pip install pyzmq pyyaml pyaudio opencv-python numpy

echo -e "${GREEN}  Bibliotecas instaladas com sucesso.${NC}"

# ------------------------------------------------------------
# 5. Inicia o PulseAudio (se não estiver rodando)
# ------------------------------------------------------------
echo ""
echo -e "${YELLOW}[5/5] Verificando PulseAudio...${NC}"

if pulseaudio --check 2>/dev/null; then
    echo -e "${GREEN}  PulseAudio já está rodando.${NC}"
else
    pulseaudio --start
    echo -e "${GREEN}  PulseAudio iniciado.${NC}"
fi

# ------------------------------------------------------------
# Liberação de portas (opcional)
# ------------------------------------------------------------
if command -v ufw &> /dev/null; then
    echo ""
    echo -e "${YELLOW}[Extra] Liberando portas no firewall (5551-5556)...${NC}"
    sudo ufw allow 5551:5556/tcp 2>/dev/null || true
    echo -e "${GREEN}  Portas liberadas.${NC}"
fi

# ------------------------------------------------------------
# Concluído
# ------------------------------------------------------------
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Setup concluído!${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  Para rodar o broker:"
echo -e "    ${YELLOW}source venv/bin/activate && python3 broker.py${NC}"
echo ""
echo "  Para rodar o cliente:"
echo -e "    ${YELLOW}source venv/bin/activate && python3 client.py${NC}"
echo ""
echo "  Ou use os atalhos:"
echo -e "    ${YELLOW}./run_broker.sh${NC}"
echo -e "    ${YELLOW}./run_client.sh${NC}"
echo ""
