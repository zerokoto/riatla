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
      animacion_mirardespreocupada(true);
      animacion_parpadeo(true);
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


// ── Estado de expresiones complejas ───────────────────────────────────────
const expresionState = {
  actual: 'neutral',
  timerReset: null,
  lerpActivo: {},   // huesos en transición: { nombreHueso: {from, to, progress} }
  lerpRAF: null
};

// ── Lerp suave para huesos ─────────────────────────────────────────────────

function lerpHueso(vrm, nombreHueso, targetRotation, duracionMs = 800) {
  const hueso = vrm.humanoid.getNormalizedBoneNode(nombreHueso);
  if (!hueso) return;

  expresionState.lerpActivo[nombreHueso] = {
    from: {
      x: hueso.rotation.x,
      y: hueso.rotation.y,
      z: hueso.rotation.z
    },
    to: targetRotation,
    progress: 0,
    duracion: duracionMs
  };
}

function tickLerpHuesos() {
  if (!currentVRM) return;
  const activos = expresionState.lerpActivo;
  let hayActivos = false;

  for (const [nombreHueso, lerp] of Object.entries(activos)) {
    const hueso = currentVRM.humanoid.getNormalizedBoneNode(nombreHueso);
    if (!hueso) continue;

    lerp.progress = Math.min(lerp.progress + (16 / lerp.duracion), 1.0);
    // easeInOut para movimiento natural
    const t = lerp.progress < 0.5
      ? 2 * lerp.progress * lerp.progress
      : 1 - Math.pow(-2 * lerp.progress + 2, 2) / 2;

    hueso.rotation.x = lerp.from.x + (lerp.to.x - lerp.from.x) * t;
    hueso.rotation.y = lerp.from.y + (lerp.to.y - lerp.from.y) * t;
    hueso.rotation.z = lerp.from.z + (lerp.to.z - lerp.from.z) * t;

    if (lerp.progress < 1.0) hayActivos = true;
    else delete activos[nombreHueso];
  }

  if (hayActivos) {
    expresionState.lerpRAF = requestAnimationFrame(tickLerpHuesos);
  }
}

function iniciarLerp() {
  if (expresionState.lerpRAF) cancelAnimationFrame(expresionState.lerpRAF);
  expresionState.lerpRAF = requestAnimationFrame(tickLerpHuesos);
}

// ── Pose neutral (brazos en reposo) ───────────────────────────────────────

function poseNeutral(vrm) {
  lerpHueso(vrm, 'leftUpperArm',  { x: 0, y: 0, z: -1.2 });
  lerpHueso(vrm, 'rightUpperArm', { x: 0, y: 0, z:  1.2 });
  lerpHueso(vrm, 'leftLowerArm',  { x: 0, y: 0, z: -0.2 });
  lerpHueso(vrm, 'rightLowerArm', { x: 0, y: 0, z:  0.2 });
  lerpHueso(vrm, 'head',          { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'neck',          { x: 0, y: 0, z:  0   });
  iniciarLerp();
}

// ── Pose angry ─────────────────────────────────────────────────────────────

function poseAngry(vrm) {
  // Lado random: izquierda o derecha
  const lado = Math.random() < 0.5 ? 1 : -1;

  // Brazos cruzados
  // Brazo derecho encima, brazo izquierdo debajo (clásico cruce)
  lerpHueso(vrm, 'rightUpperArm', { x:  0.3, y: -0.2, z:  0.8 });
  lerpHueso(vrm, 'rightLowerArm', { x:  0.0, y: -1.2, z:  0.3 });
  lerpHueso(vrm, 'leftUpperArm',  { x:  0.3, y:  0.2, z: -0.8 });
  lerpHueso(vrm, 'leftLowerArm',  { x:  0.0, y:  1.2, z: -0.3 });

  // Cabeza girada y levantada al lado random
  // pero los ojos compensan mirando a cámara (via lookAt del expressionManager)
  lerpHueso(vrm, 'neck', {
    x: -0.15,                          // levantada (barbilla arriba)
    y:  lado * 0.3,                    // girada al lado random
    z:  lado * 0.05                    // leve inclinación
  });
  lerpHueso(vrm, 'head', {
    x: -0.1,
    y:  lado * 0.25,
    z:  lado * 0.05
  });

  // Ojos compensan la rotación de la cabeza mirando a cámara
  if (vrm.expressionManager) {
    // Mover los ojos en dirección contraria al giro de la cabeza
    miradaState.targetY = -lado * 0.2;
    miradaState.targetX =  0.1;        // ligeramente arriba (mirada altiva)
  }

  iniciarLerp();
}

// ── Activar expresión angry completa ──────────────────────────────────────

function activarAngry(duracionSegundos = 10) {
  if (!currentVRM) return;

  // Cancelar reset anterior si existe
  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  // Pausar mirada despreocupada
  miradaState.activo = false;

  // Expresión facial
  activarExpresion('angry');

  // Pose corporal con transición suave
  poseAngry(currentVRM);

  expresionState.actual = 'angry';
  log(`Expresión: angry (${duracionSegundos}s)`);

  // Reset automático
  expresionState.timerReset = setTimeout(() => {
    desactivarAngry();
  }, duracionSegundos * 1000);
}

function desactivarAngry() {
  if (!currentVRM) return;

  // Volver expresión facial a neutral
  activarExpresion('neutral');

  // Volver pose corporal a reposo
  poseNeutral(currentVRM);

  // Centrar mirada y reactivar animación
  miradaState.targetX = 0;
  miradaState.targetY = 0;
  miradaState.activo = true;
  programarSiguienteMirada();

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde angry)');
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
    animarMirada();
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

// ── Estado de la animación ─────────────────────────────────────────────────
const miradaState = {
  activa: false,
  targetX: 0,      // objetivo arriba/abajo
  targetY: 0,      // objetivo izquierda/derecha
  currentX: 0,     // posición actual interpolada
  currentY: 0,
  timer: null
};

// ── Helpers ────────────────────────────────────────────────────────────────

function randomEntre(min, max) {
  return Math.random() * (max - min) + min;
}

function randomGrados(maxGrados) {
  // Positivo o negativo, sin superar maxGrados
  const grados = randomEntre(5, maxGrados);
  return Math.random() < 0.5 ? grados : -grados;
}

function gradosARadianes(grados) {
  return grados * (Math.PI / 180);
}

// ── Animación ──────────────────────────────────────────────────────────────

function programarSiguienteMirada() {
  if (!miradaState.activa) return;

  const espera = randomEntre(20000, 40000); // 20-40s mirando a un lado

  miradaState.timer = setTimeout(() => {
    // Mover a posición random
    miradaState.targetY = gradosARadianes(randomGrados(35));
    miradaState.targetX = gradosARadianes(randomGrados(20));
    log(`Mirada → H:${Math.round(miradaState.targetY * 180 / Math.PI)}° V:${Math.round(miradaState.targetX * 180 / Math.PI)}°`);

    // Después de la espera, volver al centro
    const esperaCentro = randomEntre(5000, 10000); // 5-10s en el centro
    miradaState.timer = setTimeout(() => {
      miradaState.targetX = 0;
      miradaState.targetY = 0;
      log('Mirada → centro');

      // Una vez en el centro, programar el siguiente giro
      programarSiguienteMirada();
    }, esperaCentro);

  }, espera);
}

function animacion_mirardespreocupada(activar = true) {
  miradaState.activa = activar;

  if (!activar) {
    // Detener — limpiar timer y volver al centro suavemente
    if (miradaState.timer) clearTimeout(miradaState.timer);
    miradaState.targetX = 0;
    miradaState.targetY = 0;
    log('Mirada despreocupada desactivada');
    return;
  }

  log('Mirada despreocupada activada');
  programarSiguienteMirada();
}

// ── En animate() — interpolar suavemente hacia el objetivo ─────────────────
// Llama esto dentro de animate(), igual que animarRespiracion()

function animarMirada() {
  if (!currentVRM) return;

  const head = currentVRM.humanoid.getNormalizedBoneNode('head');
  if (!head) return;

  // Lerp suave hacia el objetivo (0.02 = lento y natural)
  miradaState.currentX += (miradaState.targetX - miradaState.currentX) * 0.02;
  miradaState.currentY += (miradaState.targetY - miradaState.currentY) * 0.02;

  head.rotation.x = miradaState.currentX;
  head.rotation.y = miradaState.currentY;
}



// ── Estado del parpadeo ────────────────────────────────────────────────────
const parpadeoState = {
  activo: true,
  timer: null
};

function programarSiguienteParpadeo() {
  if (!parpadeoState.activo) return;

  // Parpadeo cada 4-8 segundos (humano real: 3-5s)
  const espera = randomEntre(4000, 8000);

  parpadeoState.timer = setTimeout(async () => {
    await ejecutarParpadeo();
    programarSiguienteParpadeo();
  }, espera);
}

async function ejecutarParpadeo() {
  if (!currentVRM?.expressionManager) return;
  const exp = currentVRM.expressionManager;

  // A veces parpadea doble (como los humanos)
  const doble = Math.random() < 0.15;

  await cerrarOjos(exp);

  if (doble) {
    await abrirOjos(exp);
    await esperar(80);
    await cerrarOjos(exp);
  }

  await abrirOjos(exp);
}

function cerrarOjos(exp) {
  return new Promise(resolve => {
    let v = 0;
    const intervalo = setInterval(() => {
      v = Math.min(v + 0.25, 1.0);  // ← velocidad cierre
      try { exp.setValue('blink', v); } catch(e) {}
      if (v >= 1.0) {
        clearInterval(intervalo);
        resolve();
      }
    }, 16); // ~60fps
  });
}

function abrirOjos(exp) {
  return new Promise(resolve => {
    let v = 1.0;
    const intervalo = setInterval(() => {
      v = Math.max(v - 0.22, 0);    // ← velocidad apertura (más lento que el cierre)
      try { exp.setValue('blink', v); } catch(e) {}
      if (v <= 0) {
        clearInterval(intervalo);
        resolve();
      }
    }, 16);
  });
}

function esperar(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function animacion_parpadeo(activar = true) {
  parpadeoState.activo = activar;

  if (!activar) {
    if (parpadeoState.timer) clearTimeout(parpadeoState.timer);
    if (currentVRM?.expressionManager) {
      try { currentVRM.expressionManager.setValue('blink', 0); } catch(e) {}
    }
    log('Parpadeo desactivado');
    return;
  }

  log('Parpadeo activado');
  programarSiguienteParpadeo();
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
  console.log('Comando recibido:', JSON.stringify(comando)); // ← añadir
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
      const duracion = parametros.duracion ?? 20;
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

    case 'mirada_despreocupada':
      animacion_mirardespreocupada(parametros.activa ?? true);
      break;

    case 'parpadeo':
      animacion_parpadeo(parametros.activa ?? true);
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
