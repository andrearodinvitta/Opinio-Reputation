#!/bin/bash
# Reputation Shield - Script de Inicio con Túnel Cloudflare para NFC
echo "============================================================"
echo "  🛡️ INICIANDO REPUTATION SHIELD & REVIEW FUNNEL           "
echo "============================================================"

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Detener procesos anteriores si están en puerto 8080 o túnel
kill -9 $(lsof -t -i :8080) 2>/dev/null
pkill -f "cloudflared tunnel.*8080" 2>/dev/null
sleep 1

# Iniciar servidor Python en segundo plano
echo "🚀 Iniciando servidor backend..."
python3 server.py &
SERVER_PID=$!

# Iniciar túnel Cloudflare seguro para móviles / NFC
if [ -f "./bin/cloudflared" ]; then
  echo "🌐 Conectando túnel público HTTPS Cloudflare (para móviles y NFC)..."
  ./bin/cloudflared tunnel --url http://localhost:8080 > tunnel.log 2>&1 &
  TUNNEL_PID=$!

  # Esperar a que el túnel genere la URL
  sleep 4
  PUBLIC_URL=$(grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' tunnel.log | tail -n 1)
  
  echo ""
  echo "============================================================"
  echo " ⭐ SISTEMA LISTO PARA USAR EN MÓVILES Y TARJETAS NFC ⭐"
  echo "============================================================"
  echo " > Panel de Control: $PUBLIC_URL/login"
  echo " > Enlace NFC Demo:   $PUBLIC_URL/r/liso-y-sedoso"
  echo " > Servidor Local:    http://localhost:8080"
  echo "============================================================"
fi

trap "kill $SERVER_PID $TUNNEL_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
