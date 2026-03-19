import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

// ═══════════════════════════════════════════════════════════════════════════
// CONFIGURACIÓN
// ═══════════════════════════════════════════════════════════════════════════

const WEBSOCKET_URL = 'ws://localhost:8765'; // tu daemon Python
const VRM_MODEL = './models/riatla.vrm';

// ═══════════════════════════════════════════════════════════════════════════
// STATE
// ═══════════════════════════════════════════════════════════════════════════

let currentVRM = null;
let scene, camera, renderer;
let ws = null;
let vrmLoaded = false;

const state = {
  emocionActual: 'neutral',
  wsConnected: false,
  ultimoComando: 'ninguno'
};

// ═══════════════════════════════════════════════════════════════════════════
// THREE.JS SETUP
// ═══════════════════════════════════════════════════════════════════════════

function setupScene() {
  // Canvas
  const canvas = document.getElementById('canvas');
  
  // Escena
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x2d2d44);

  // Cámara
  camera = new THREE.PerspectiveCamera(
    45,
    window.innerWidth / window.innerHeight,
    0.1,
    1000
  );
  camera.position.set(0, 1.5, 2);
  camera.lookAt(0, 1.2, 0);

  // Renderer
  renderer = new THREE.WebGLRenderer({ 
    canvas: canvas, 
    antialias: true, 
    alpha: true 
  });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.outputEncoding = THREE.sRGBColorSpace;

  // Iluminación
  const ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
  scene.add(ambientLight);

  const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
  directionalLight.position.set(1, 2, 2);
  scene.add(directionalLight);

  // Responsive
  window.addEventListener('resize', onWindowResize);
}

function onWindowResize() {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}

// ═══════════════════════════════════════════════════════════════════════════
// VRM LOADING
// ═══════════════════════════════════════════════════════════════════════════

function loadVRM() {
  const loader = new GLTFLoader();
  loader.register((parser) => new VRMLoaderPlugin(parser));

  log(`Intentando cargar: ${VRM_MODEL}`);
  
  loader.load(
    VRM_MODEL,
    (gltf) => {
      const vrm = gltf.userData.vrm;
      VRMUtils.removeUnnecessaryJoints(vrm.scene);
      
      currentVRM = vrm;
      scene.add(vrm.scene);
      vrmLoaded = true;
      
      updateStatus('VRM cargado', true);
      log('✓ Modelo VRM cargado correctamente');
      
      // Iniciar animación cuando el VRM esté listo
      animate();
    },
    (progress) => {
      const percent = Math.round((progress.loaded / progress.total) * 100);
      log(`Cargando VRM... ${percent}%`);
    },
    (error) => {
      console.error('Error cargando VRM:', error);
      const errorMsg = error.message || JSON.stringify(error);
      log(`✗ Error cargando modelo: ${errorMsg}`);
      updateStatus('Error cargando VRM', false);
    }
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// ANIMACIÓN Y EXPRESIONES
// ═══════════════════════════════════════════════════════════════════════════

function activarExpresion(nombre) {
  if (!currentVRM || !currentVRM.expressionManager) return;

  const exp = currentVRM.expressionManager;
  
  // Resetear todas las expresiones
  exp.forEach((name) => exp.setValue(name, 0));
  
  // Activar la deseada
  if (exp.hasExpression(nombre)) {
    exp.setValue(nombre, 1.0);
    state.emocionActual = nombre;
    log(`Expresión: ${nombre}`);
  } else {
    log(`⚠ Expresión no encontrada: ${nombre}`);
  }
}

function mirarHacia(x, y, z) {
  if (!currentVRM || !currentVRM.humanoid) return;
  
  const head = currentVRM.humanoid.getNormalizedBoneNode('head');
  if (head) {
    head.rotation.x = x;
    head.rotation.y = y;
    head.rotation.z = z;
  }
}

function animate() {
  requestAnimationFrame(animate);
  
  if (currentVRM) {
    currentVRM.update(1 / 60); // 60 FPS
  }
  
  renderer.render(scene, camera);
}

// ═══════════════════════════════════════════════════════════════════════════
// WEBSOCKET
// ═══════════════════════════════════════════════════════════════════════════

function connectWebSocket() {
  try {
    ws = new WebSocket(WEBSOCKET_URL);

    ws.onopen = () => {
      state.wsConnected = true;
      updateStatus('Conectado', true);
      log('✓ WebSocket conectado');
    };

    ws.onmessage = (event) => {
      try {
        const comando = JSON.parse(event.data);
        ejecutarComando(comando);
      } catch (error) {
        console.error('Error parseando comando:', error);
        log('⚠ Comando JSON inválido');
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      updateStatus('Error WebSocket', false);
      log('✗ Error en WebSocket');
    };

    ws.onclose = () => {
      state.wsConnected = false;
      updateStatus('Desconectado', false);
      log('✗ WebSocket cerrado (reintentando...)');
      
      // Reconectar después de 3 segundos
      setTimeout(connectWebSocket, 3000);
    };
  } catch (error) {
    console.error('Error conectando WebSocket:', error);
    updateStatus('Error de conexión', false);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// COMANDO EJECUTOR
// ═══════════════════════════════════════════════════════════════════════════

function ejecutarComando(comando) {
  const { accion, parametros = {} } = comando;
  
  state.ultimoComando = accion;
  
  switch (accion) {
    case 'hablar':
    case 'emocion_happy':
      activarExpresion('happy');
      break;
      
    case 'escuchar':
    case 'emocion_neutral':
      activarExpresion('neutral');
      break;
      
    case 'alerta':
    case 'emocion_surprised':
      activarExpresion('surprised');
      break;
      
    case 'emocion_angry':
      activarExpresion('angry');
      break;
      
    case 'emocion_sad':
      activarExpresion('sad');
      break;
      
    case 'emocion_relaxed':
      activarExpresion('relaxed');
      break;
      
    case 'mirar':
      const { x = 0, y = 0, z = 0 } = parametros;
      mirarHacia(x, y, z);
      log(`Mirando hacia: (${x}, ${y}, ${z})`);
      break;
      
    case 'reset':
      activarExpresion('neutral');
      mirarHacia(0, 0, 0);
      log('Reset ejecutado');
      break;
      
    default:
      log(`⚠ Acción desconocida: ${accion}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// UI HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function updateStatus(message, connected) {
  const statusEl = document.getElementById('status');
  statusEl.textContent = `WebSocket: ${message}`;
  statusEl.className = connected ? 'connected' : 'disconnected';
}

const debugLogs = [];
const MAX_LOGS = 8;

function log(message) {
  const timestamp = new Date().toLocaleTimeString('es-ES');
  const logEntry = `[${timestamp}] ${message}`;
  
  debugLogs.unshift(logEntry);
  if (debugLogs.length > MAX_LOGS) {
    debugLogs.pop();
  }
  
  const debugEl = document.getElementById('debug');
  debugEl.innerHTML = debugLogs.map(l => `<div>${l}</div>`).join('');
}

// ═══════════════════════════════════════════════════════════════════════════
// INICIO
// ═══════════════════════════════════════════════════════════════════════════

window.addEventListener('load', () => {
  log('Inicializando Riatla...');
  setupScene();
  loadVRM();
  connectWebSocket();
});
