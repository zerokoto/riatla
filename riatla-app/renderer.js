import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
// import { VRMLoaderPlugin, VRMUtils, MToonMaterialPlugin } from '@pixiv/three-vrm';


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
    // Close to face, so we can see expressions clearly, but not too close to avoid distortion
    10,
    window.innerWidth / window.innerHeight,
    0.1,
    1000
  );
  camera.position.set(3, 1.8, 6);
  camera.lookAt(0, 1.2, 0);

  // Renderer
  renderer = new THREE.WebGLRenderer({ 
    canvas: canvas, 
    antialias: true, 
    alpha: true 
  });
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setPixelRatio(window.devicePixelRatio);
 renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;  // vuelve al original
  renderer.toneMappingExposure = 0.7;

  // Iluminación
  const ambientLight = new THREE.AmbientLight(0xffffff, 1.0);
  scene.add(ambientLight);

  const directionalLight = new THREE.DirectionalLight(0xffffff, 1.0);
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
//  loader.register((parser) => new VRMLoaderPlugin(parser, {
//    mtoonMaterialPlugin: new MToonMaterialPlugin(parser, {
//      renderer: renderer
//    })
//  }));

  log(`Intentando cargar: ${VRM_MODEL}`);
  
  loader.load(
    VRM_MODEL,
    (gltf) => {
      const vrm = gltf.userData.vrm;
      VRMUtils.removeUnnecessaryJoints(vrm.scene);


      // MToon 3.x necesita esto para colores correctos
      vrm.scene.traverse((obj) => {
        if (obj.isMesh) {
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          mats.forEach((mat) => {
            // MToon ignora el tonemapping del renderer, hay que forzarlo en el material
            mat.tonemapped = false;
            mat.needsUpdate = true;
          });
        }
      });
            
      currentVRM = vrm;
      scene.add(vrm.scene);
      vrm.scene.rotation.y = Math.PI / 7;
      aplicarPoseReposo(vrm);
      vrmLoaded = true;
      
      // Eliminar T pose para que se vea mas natural al cargar
      activarExpresion('neutral');


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

function loadWorld(path = './world/TinyRoom.gltf') {
  const loader = new GLTFLoader();
  loader.load(
    path,
    (gltf) => {
      const world = gltf.scene;
      world.userData.isWorld = true;

      const box = new THREE.Box3().setFromObject(world);
      const size = box.getSize(new THREE.Vector3());
      const center = box.getCenter(new THREE.Vector3());

      // El mundo mide 680 unidades reales → queremos ~4m
      // 4 / 680 = 0.00588... pero el VRM ya está en metros
      // Así que la escala correcta es:
      const scale = 2.5 / Math.max(size.x, size.z);  // → ~0.006
      world.scale.setScalar(scale);

      // Recentrar DESPUÉS de escalar
      box.setFromObject(world);
      const scaledCenter = box.getCenter(new THREE.Vector3());
      const scaledMin = box.min;

      // Centrar en X/Z, apoyar el suelo en Y=0
      world.position.set(
        -scaledCenter.x,
        -scaledMin.y,
        -scaledCenter.z
      );

      scene.add(world);
      log(`✓ Escenario cargado (escala: ${scale.toFixed(3)}, size: ${size.x.toFixed(1)}x${size.y.toFixed(1)}x${size.z.toFixed(1)})`);
    },
    (progress) => {
      const pct = Math.round((progress.loaded / progress.total) * 100);
      log(`Cargando escenario... ${pct}%`);
    },
    (error) => {
      log(`✗ Error escenario: ${error.message}`);
    }
  );
}

function aplicarPoseReposo(vrm) {
  const { humanoid } = vrm;

  // Brazos
  const leftArm  = humanoid.getNormalizedBoneNode('leftUpperArm');
  const rightArm = humanoid.getNormalizedBoneNode('rightUpperArm');
  if (leftArm)  leftArm.rotation.z  = -1.2;
  if (rightArm) rightArm.rotation.z =  1.2;

  // Codos (opcional, más natural)
  const leftLower  = humanoid.getNormalizedBoneNode('leftLowerArm');
  const rightLower = humanoid.getNormalizedBoneNode('rightLowerArm');
  if (leftLower)  leftLower.rotation.z  = -0.2;
  if (rightLower) rightLower.rotation.z =  0.2;

  // Dedos — misma rotación para ambas manos
  const dedos = [
    'IndexProximal', 'IndexIntermediate', 'IndexDistal',
    'MiddleProximal', 'MiddleIntermediate', 'MiddleDistal',
    'RingProximal',   'RingIntermediate',   'RingDistal',
    'LittleProximal', 'LittleIntermediate', 'LittleDistal',
  ];

  dedos.forEach(dedo => {
    const L = humanoid.getNormalizedBoneNode(`left${dedo}`);
    const R = humanoid.getNormalizedBoneNode(`right${dedo}`);
    if (L) L.rotation.z = -0.3;  // cierre suave
    if (R) R.rotation.z =  0.3;
  });

  // Pulgares — eje distinto
  const pulgares = ['ThumbProximal', 'ThumbDistal', 'ThumbMetacarpal'];
  pulgares.forEach(pulgar => {
    const L = humanoid.getNormalizedBoneNode(`left${pulgar}`);
    const R = humanoid.getNormalizedBoneNode(`right${pulgar}`);
    if (L) { L.rotation.z = -0.3; L.rotation.y =  0.3; }
    if (R) { R.rotation.z =  0.3; R.rotation.y = -0.3; }
  });

}



// ═══════════════════════════════════════════════════════════════════════════
// ANIMACIÓN Y EXPRESIONES
// ═══════════════════════════════════════════════════════════════════════════

function activarExpresion(nombre) {
  if (!currentVRM || !currentVRM.expressionManager) return;

  const exp = currentVRM.expressionManager;

  // three-vrm 3.x: usar getExpressionTrackName para listar, o resetear manualmente
  const expresiones = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral'];
  expresiones.forEach(name => {
    try { exp.setValue(name, 0); } catch(e) {}
  });

  // Activar la deseada
  try {
    exp.setValue(nombre, 1.0);
    state.emocionActual = nombre;
    log(`Expresión: ${nombre}`);
  } catch(e) {
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

// Variable global para el tiempo de respiración
let breathTime = 0;

function animate() {
  requestAnimationFrame(animate);
  
  if (currentVRM) {
    currentVRM.update(1 / 60); // 60 FPS
    animarRespiracion();
  }
  
  renderer.render(scene, camera);
}
 

function animarRespiracion() {
  if (!currentVRM) return;
  const { humanoid } = currentVRM;

  breathTime += 0.008; // ← velocidad: más alto = más rápido

  const breath = Math.sin(breathTime) * 0.02; // ← intensidad: más alto = más pronunciado

  // Pecho sube y baja
  const chest = humanoid.getNormalizedBoneNode('chest');
  if (chest) {
    chest.rotation.x = breath;
  }

  // Columna acompaña ligeramente
  const spine = humanoid.getNormalizedBoneNode('spine');
  if (spine) {
    spine.rotation.x = breath * 0.5;
  }

  // Hombros suben y bajan con el pecho
  const leftShoulder  = humanoid.getNormalizedBoneNode('leftShoulder');
  const rightShoulder = humanoid.getNormalizedBoneNode('rightShoulder');
  if (leftShoulder)  leftShoulder.rotation.z = -breath * 0.5;
  if (rightShoulder) rightShoulder.rotation.z =  breath * 0.5;
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

    case 'pose_reposo':
      if (currentVRM) aplicarPoseReposo(currentVRM);
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

    case 'world':
      const { path } = parametros;
      if (path) {
        // Limpiar mundo anterior
        scene.children
          .filter(obj => obj.userData.isWorld)
          .forEach(obj => scene.remove(obj));
        loadWorld(path);
      }
      break;
    
    case 'world_rotation':
      const worldObj = scene.children.find(obj => obj.userData.isWorld);
      if (worldObj) worldObj.rotation.y = parametros.y;
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
  loadWorld();
  loadVRM();
  connectWebSocket();
});
