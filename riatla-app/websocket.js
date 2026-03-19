// websocket.js
const ws = new WebSocket('ws://localhost:8765'); // tu daemon Python

ws.onmessage = (event) => {
  const comando = JSON.parse(event.data);
  ejecutarComando(comando);
};

function ejecutarComando(comando) {
  switch (comando.accion) {
    case 'hablar':    activarExpresion('happy'); break;
    case 'escuchar':  activarExpresion('neutral'); break;
    case 'alerta':    activarExpresion('surprised'); break;
    // añade los que uses en tu daemon
  }
}