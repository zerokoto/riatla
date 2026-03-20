import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';


// ═══════════════════════════════════════════════════════════════════════════
// CONFIGURACIÓN
// Parámetros de conexión y rutas de assets. Modificar según entorno.
// ═══════════════════════════════════════════════════════════════════════════

const WEBSOCKET_URL = 'ws://localhost:8765'; // debe coincidir con WS_PORT en riatla_daemon.py
const VRM_MODEL     = './models/riatla.vrm';

// ═══════════════════════════════════════════════════════════════════════════
// ESTADO GLOBAL
// Variables de ciclo de vida y estado observable de la aplicación.
// ═══════════════════════════════════════════════════════════════════════════

let currentVRM = null;   // instancia VRM activa
let scene, camera, renderer;
let ambientLight, directionalLight; // referencias para control de iluminación
let ws        = null;    // conexión WebSocket activa
let vrmLoaded = false;

/** Estado observable (útil para depuración en consola). */
const state = {
  emocionActual: 'neutral',
  wsConnected: false,
  ultimoComando: 'ninguno'
};

// ═══════════════════════════════════════════════════════════════════════════
// THREE.JS / ESCENA
// Inicialización del renderer, cámara e iluminación.
// ═══════════════════════════════════════════════════════════════════════════

function setupScene() {
  // Canvas
  const canvas = document.getElementById('canvas');
  
  // Escena
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x2d2d44);

  // Ángulo reducido (10°) para acercar el plano facial sin distorsión
  camera = new THREE.PerspectiveCamera(
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
  renderer.outputColorSpace   = THREE.SRGBColorSpace;
  renderer.toneMapping        = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.7;

  // Iluminación
  ambientLight = new THREE.AmbientLight(0xffffff, 1.0);
  scene.add(ambientLight);

  directionalLight = new THREE.DirectionalLight(0xffffff, 0.9);
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
// CARGA DE ASSETS
// Carga del modelo VRM del avatar y del escenario 3D (GLTF/GLB).
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


      // MToon ignora el tonemapping del renderer → hay que forzarlo en cada material
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
      
      activarExpresion('neutral'); // elimina la T-pose inicial


      updateStatus('VRM cargado', true);
      log('✓ Modelo VRM cargado correctamente');
      
      animate(); // arranca el loop de render
    },
    (progress) => {
      const percent = Math.round((progress.loaded / progress.total) * 100);
      log(`Cargando VRM... ${percent}%`);
    },
    (error) => {
      console.error('Error cargando VRM:', error);
      log(`✗ Error cargando modelo: ${error.message || JSON.stringify(error)}`);
      updateStatus('Error cargando VRM', false);
    }
  );
}

/**
 * Carga un escenario GLTF, lo escala para que ocupe ~2.5 m de diámetro
 * y lo centra en el origen. Elimina el escenario anterior si existía.
 * @param {string} path - Ruta relativa al archivo GLTF/GLB.
 */
function loadWorld(path = './world/TinyRoom.gltf') {
  const loader = new GLTFLoader();
  loader.load(
    path,
    (gltf) => {
      const world = gltf.scene;
      world.userData.isWorld = true;

      const box  = new THREE.Box3().setFromObject(world);
      const size = box.getSize(new THREE.Vector3());

      // Escalar para que el eje mayor ocupe ~2.5 m (unidades VRM = metros)
      const scale = 2.5 / Math.max(size.x, size.z);
      world.scale.setScalar(scale);

      // Recentrar DESPUÉS de escalar
      box.setFromObject(world);
      const scaledCenter = box.getCenter(new THREE.Vector3());
      const scaledMin    = box.min;

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

// ═══════════════════════════════════════════════════════════════════════════
// POSES CORPORALES
// Posiciones de huesos que definen el lenguaje corporal del avatar.
// aplicarPoseReposo() se aplica directamente al cargar; durante runtime
// se usan poseNeutral() / poseAngry() con lerp para transiciones suaves.
// ═══════════════════════════════════════════════════════════════════════════

/** Pose de reposo inicial: brazos caídos y dedos semiencogidos (sin lerp). */
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

  // Dedos — cierre suave en ambas manos
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

  // Pulgares — eje de rotación diferente al resto de los dedos
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

/**
 * Resetea todas las expresiones faciales a 0 y activa la indicada al 100%.
 * Operación atómica: solo puede haber una expresión activa a la vez.
 * @param {string} nombre - Nombre de la expresión VRM ('happy', 'angry', etc.)
 */
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
/** @type {{ actual: string, timerReset: number|null, lerpActivo: Object, lerpRAF: number|null }} */
const expresionState = {
  actual:     'neutral',
  timerReset: null,
  lerpActivo: {},   // { [nombreHueso]: { from, to, progress, duracion } }
  lerpRAF:    null
};

// ── Sistema Lerp (transiciones suaves de huesos) ──────────────────────────
// Interpola rotaciones de huesos frame a frame mediante requestAnimationFrame.

/**
 * Registra un hueso para interpolación suave hacia targetRotation.
 * @param {object} vrm            - Instancia VRM activa.
 * @param {string} nombreHueso    - Nombre del hueso normalizado (camelCase VRM).
 * @param {{ x, y, z }} targetRotation - Rotación destino en radianes.
 * @param {number} duracionMs     - Duración de la transición en ms (default: 800).
 */
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

/** Tick RAF: avanza todos los lerps activos con easing easeInOut. */
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

/** Arranca (o reinicia) el loop de interpolación de huesos. */
function iniciarLerp() {
  if (expresionState.lerpRAF) cancelAnimationFrame(expresionState.lerpRAF);
  expresionState.lerpRAF = requestAnimationFrame(tickLerpHuesos);
}

// ── Poses con transición suave ─────────────────────────────────────────────

/** Transición suave de vuelta a la pose de reposo. */
function poseNeutral(vrm) {
  lerpHueso(vrm, 'leftUpperArm',  { x: 0, y: 0, z: -1.2 });
  lerpHueso(vrm, 'rightUpperArm', { x: 0, y: 0, z:  1.2 });
  lerpHueso(vrm, 'leftLowerArm',  { x: 0, y: 0, z: -0.2 });
  lerpHueso(vrm, 'rightLowerArm', { x: 0, y: 0, z:  0.2 });
  lerpHueso(vrm, 'leftHand',      { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'rightHand',     { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'head',          { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'neck',          { x: 0, y: 0, z:  0   });
  iniciarLerp();
}

// ── Pose angry ─────────────────────────────────────────────────────────────
/**
 * Brazos cruzados, cabeza levantada y girada a un lado aleatorio.
 * Los ojos compensan el giro para mantener contacto visual con la cámara.
 */
function poseAngry(vrm) {
  // Lado aleatorio para dar variedad entre activaciones
  const lado = Math.random() < 0.5 ? 1 : -1;

  // Brazos cruzados: derecho abajo, izquierdo arriba (cruce clásico)
    lerpHueso(vrm, 'rightUpperArm', { x:  0.3,  y:  0.9,  z:  1.0 });
    lerpHueso(vrm, 'leftUpperArm',  { x:  0.28, y: -1.0,  z:  -0.5 });

    lerpHueso(vrm, 'rightLowerArm', { x:  0.2,  y:  2.0,  z:  0.0 });
    lerpHueso(vrm, 'leftLowerArm',  { x:  0.0,  y: -2.0,  z:  0.0 });

    // Muñeca izquierda rotada
    //lerpHueso(vrm, 'leftHand',      { x:  -1.0,  y: 0.1,  z: 0.0 }); // y= horizontal izquierda; x = rotado horario
    // lerpHueso(vrm, 'rightHand',      { x:  -0.5,  y: 0.4,  z: -0.7 }); // y= horizontal izquierda; x = rotado horario

    // Mano derecha (debajo): palma mirando hacia arriba/dentro
    lerpHueso(vrm, 'rightHand', { x:  0.3,  y: 0.6,  z:  -1.2 });

    // Mano izquierda (encima): palma mirando hacia abajo/dentro  
    lerpHueso(vrm, 'leftHand',  { x: -0.3,  y:  0.3,  z:  0.5 });

  // Cabeza levantada (barbilla arriba) y girada al lado aleatorio
  lerpHueso(vrm, 'neck', {
    x: -0.15,        // barbilla arriba
    y:  lado * 0.3,  // giro lateral
    z:  lado * 0.05  // leve inclinación
  });
  lerpHueso(vrm, 'head', {
    x: -0.1,
    y:  lado * 0.25,
    z:  lado * 0.05
  });

  // Ojos en dirección contraria al giro → mantienen contacto visual con la cámara
  if (vrm.expressionManager) {
    miradaState.targetY = -lado * 0.2;
    miradaState.targetX =  0.1; // ligeramente arriba (mirada altiva)
  }

  iniciarLerp();
}

// ── Activar / desactivar emoción angry ────────────────────────────────────

/**
 * Activa la emoción "angry" completa: expresión facial + pose corporal + auto-reset.
 * Pausa la animación idle de mirada durante la duración indicada.
 * @param {number} duracionSegundos - Tiempo hasta volver a neutral (default: 10 s).
 */
function activarAngry(duracionSegundos = 10) {
  if (!currentVRM) return;

  // Cancelar reset anterior si existe
  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  // Pausar mirada despreocupada
  miradaState.activa = false;

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

/** Revierte la emoción angry: expresión neutral + pose reposo + reactiva mirada idle. */
function desactivarAngry() {
  if (!currentVRM) return;

  // Volver expresión facial a neutral
  activarExpresion('neutral');

  // Volver pose corporal a reposo
  poseNeutral(currentVRM);

  // Centrar mirada y reactivar animación
  miradaState.targetX = 0;
  miradaState.targetY = 0;
  miradaState.activa = true;
  programarSiguienteMirada();

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde angry)');
}


// ── Pose sad ────────────────────────────────────────────────────────────────

/**
 * Cabeza caída, hombros hundidos, brazos pegados al cuerpo.
 */
function poseSad(vrm) {
  const lado = Math.random() < 0.5 ? 1 : -1;

  // Cabeza inclinada hacia abajo, leve giro aleatorio
  lerpHueso(vrm, 'head', { x:  0.2, y: lado * 0.1, z: lado * 0.04 });
  lerpHueso(vrm, 'neck', { x:  0.15, y: lado * 0.05, z: 0 });

  // Brazos caídos, hombros hundidos hacia adelante
  lerpHueso(vrm, 'leftUpperArm',  { x:  0.12, y: 0, z: -0.9 });
  lerpHueso(vrm, 'rightUpperArm', { x:  0.12, y: 0, z:  0.9 });
  lerpHueso(vrm, 'leftLowerArm',  { x:  0,    y: 0, z: -0.1 });
  lerpHueso(vrm, 'rightLowerArm', { x:  0,    y: 0, z:  0.1 });

  iniciarLerp();
}

/**
 * Activa la emoción "sad": expresión facial + pose corporal + auto-reset.
 * @param {number} duracionSegundos - Tiempo hasta volver a neutral (default: 15 s).
 */
function activarSad(duracionSegundos = 15) {
  if (!currentVRM) return;

  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  // Mirada ligeramente hacia abajo
  miradaState.activa = false;
  miradaState.targetX =  0.15;
  miradaState.targetY =  0;

  activarExpresion('sad');
  poseSad(currentVRM);

  expresionState.actual = 'sad';
  log(`Expresión: sad (${duracionSegundos}s)`);

  expresionState.timerReset = setTimeout(() => {
    desactivarSad();
  }, duracionSegundos * 1000);
}

/** Revierte la emoción sad: expresión neutral + pose reposo + reactiva mirada idle. */
function desactivarSad() {
  if (!currentVRM) return;

  activarExpresion('neutral');
  poseNeutral(currentVRM);

  miradaState.targetX = 0;
  miradaState.targetY = 0;
  miradaState.activa  = true;
  programarSiguienteMirada();

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde sad)');
}


// ── Pose relaxed ────────────────────────────────────────────────────────────

/**
 * Cabeza suavemente inclinada a un lado, brazos relajados y ligeramente abiertos.
 */
function poseRelaxed(vrm) {
  const lado = Math.random() < 0.5 ? 1 : -1;

  // Cabeza ladeada con suavidad
  lerpHueso(vrm, 'head', { x: 0, y: lado * 0.1, z: lado * 0.08 });
  lerpHueso(vrm, 'neck', { x: 0, y: lado * 0.06, z: lado * 0.04 });

  // Brazos un poco más abiertos que en reposo
  lerpHueso(vrm, 'leftUpperArm',  { x: 0, y: 0, z: -1.5 });
  lerpHueso(vrm, 'rightUpperArm', { x: 0, y: 0.5, z:  1.5 });
  lerpHueso(vrm, 'leftLowerArm',  { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'rightLowerArm', { x: 0, y: 0, z:  0   });

  iniciarLerp();
}

/**
 * Activa la emoción "relaxed": expresión facial + pose corporal + auto-reset.
 * La animación de mirada idle permanece activa para mayor naturalidad.
 * @param {number} duracionSegundos - Tiempo hasta volver a neutral (default: 20 s).
 */
function activarRelaxed(duracionSegundos = 20) {
  if (!currentVRM) return;

  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  activarExpresion('relaxed');
  poseRelaxed(currentVRM);

  expresionState.actual = 'relaxed';
  log(`Expresión: relaxed (${duracionSegundos}s)`);

  expresionState.timerReset = setTimeout(() => {
    desactivarRelaxed();
  }, duracionSegundos * 1000);
}

/** Revierte la emoción relaxed: expresión neutral + pose reposo. */
function desactivarRelaxed() {
  if (!currentVRM) return;

  activarExpresion('neutral');
  poseNeutral(currentVRM);

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde relaxed)');
}


// ── Pose surprised ──────────────────────────────────────────────────────────

/**
 * Cabeza ligeramente echada hacia atrás, brazos abiertos y levantados.
 */
function poseSurprised(vrm) {
  // Cabeza hacia atrás (barbilla arriba)
  lerpHueso(vrm, 'head', { x: -0.1, y: 0, z: 0 });
  lerpHueso(vrm, 'neck', { x: -0.08, y: 0, z: 0 });

  // Brazos levantados y abiertos — reacción de sobresalto
  lerpHueso(vrm, 'leftUpperArm',  { x:  0,   y: -0.3, z: -0.7 });
  lerpHueso(vrm, 'rightUpperArm', { x:  0,   y:  0.3, z:  0.7 });
  lerpHueso(vrm, 'leftLowerArm',  { x:  0.4, y:  0,   z: -0.2 });
  lerpHueso(vrm, 'rightLowerArm', { x:  0.4, y:  0,   z:  0.2 });

  iniciarLerp();
}

/**
 * Activa la emoción "surprised": expresión facial + pose corporal + auto-reset.
 * Pausa la animación idle de mirada y la dirige ligeramente hacia arriba.
 * @param {number} duracionSegundos - Tiempo hasta volver a neutral (default: 5 s).
 */
function activarSurprised(duracionSegundos = 5) {
  if (!currentVRM) return;

  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  // Mirada ligeramente hacia arriba (acompasa la cabeza echada atrás)
  miradaState.activa  = false;
  miradaState.targetX = -0.1;
  miradaState.targetY =  0;

  activarExpresion('surprised');
  poseSurprised(currentVRM);

  expresionState.actual = 'surprised';
  log(`Expresión: surprised (${duracionSegundos}s)`);

  expresionState.timerReset = setTimeout(() => {
    desactivarSurprised();
  }, duracionSegundos * 1000);
}

/** Revierte la emoción surprised: expresión neutral + pose reposo + reactiva mirada idle. */
function desactivarSurprised() {
  if (!currentVRM) return;

  activarExpresion('neutral');
  poseNeutral(currentVRM);

  miradaState.targetX = 0;
  miradaState.targetY = 0;
  miradaState.activa  = true;
  programarSiguienteMirada();

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde surprised)');
}


/**
 * Rota la cabeza hacia coordenadas exactas (sin lerp).
 * Útil para comandos externos puntuales vía WebSocket.
 * @param {number} x @param {number} y @param {number} z
 */
function mirarHacia(x, y, z) {
  if (!currentVRM || !currentVRM.humanoid) return;
  
  const head = currentVRM.humanoid.getNormalizedBoneNode('head');
  if (head) {
    head.rotation.x = x;
    head.rotation.y = y;
    head.rotation.z = z;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// LOOP PRINCIPAL
// Bucle de render a ~60 FPS. Solo arranca cuando el VRM está cargado.
// ═══════════════════════════════════════════════════════════════════════════

// Variable global para el tiempo de respiración
let breathTime = 0;

function animate() {
  requestAnimationFrame(animate);
  
  if (currentVRM) {
    currentVRM.update(1 / 60);
    animarRespiracion();
    animarMirada();
    animarMusica();
  }
  
  renderer.render(scene, camera);
}


// ── Respiración ────────────────────────────────────────────────────────────
// Movimiento sutil del pecho, columna y hombros. Se llama cada frame.

function animarRespiracion() {
  if (!currentVRM) return;
  const { humanoid } = currentVRM;

  breathTime += 0.008; // velocidad del ciclo

  const breath = Math.sin(breathTime) * 0.02; // amplitud del movimiento

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
// ANIMACIÓN — MIRADA
// Movimiento ocular/cefálico idle: la cabeza gira periódicamente hacia puntos
// aleatorios y vuelve al centro. Se pausa durante emociones activas.
// animarMirada() se llama cada frame en animate() para interpolación continua.
// ═══════════════════════════════════════════════════════════════════════════

const miradaState = {
  activa:   false, // true = animación idle activa
  targetX:  0,     // objetivo rotación cabeza (arriba/abajo)
  targetY:  0,     // objetivo rotación cabeza (izq/dcha)
  currentX: 0,     // posición interpolada actual
  currentY: 0,
  timer:    null
};

// ── Helpers de ángulos ──────────────────────────────────────────────────────

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

// ── Lógica de programación ──────────────────────────────────────────────────

/** Programa el siguiente movimiento de mirada (se llama recursivamente). */
function programarSiguienteMirada() {
  if (!miradaState.activa) return;

  const espera = randomEntre(20000, 40000); // 20-40s mirando a un lado

  miradaState.timer = setTimeout(() => {
    // Mover a posición random
    miradaState.targetY = gradosARadianes(randomGrados(35));
    miradaState.targetX = gradosARadianes(randomGrados(20));
    log(`Mirada → H:${Math.round(miradaState.targetY * 180 / Math.PI)}° V:${Math.round(miradaState.targetX * 180 / Math.PI)}°`);

    // Después de la espera, volver al centro
    const esperaCentro = randomEntre(1000, 5000); // 1-5s en el centro
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
    if (miradaState.timer) clearTimeout(miradaState.timer);
    miradaState.targetX = 0;
    miradaState.targetY = 0;
    log('Mirada despreocupada desactivada');
    return;
  }

  log('Mirada despreocupada activada');
  programarSiguienteMirada();
}

/** Interpola suavemente la cabeza hacia miradaState.target. Se llama en animate(). */
function animarMirada() {
  if (!currentVRM) return;

  const head = currentVRM.humanoid.getNormalizedBoneNode('head');
  if (!head) return;

  // Factor 0.02 = movimiento lento y natural
  miradaState.currentX += (miradaState.targetX - miradaState.currentX) * 0.02;
  miradaState.currentY += (miradaState.targetY - miradaState.currentY) * 0.02;

  head.rotation.x = miradaState.currentX;
  head.rotation.y = miradaState.currentY;
}


// ═══════════════════════════════════════════════════════════════════════════
// ANIMACIÓN — PARPADEO
// Parpadeo autónomo aleatorio con doble parpadeo ocasional (15 % de casos).
// ═══════════════════════════════════════════════════════════════════════════

const parpadeoState = {
  activo: true,
  timer:  null
};

function programarSiguienteParpadeo() {
  if (!parpadeoState.activo) return;

  // Intervalo humano real: 3-5 s. Usamos 4-8 s para ser más sutil.
  parpadeoState.timer = setTimeout(async () => {
    await ejecutarParpadeo();
    programarSiguienteParpadeo();
  }, randomEntre(4000, 8000));
}

async function ejecutarParpadeo() {
  if (!currentVRM?.expressionManager) return;
  const exp   = currentVRM.expressionManager;
  const doble = Math.random() < 0.15; // doble parpadeo ocasional

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
      v = Math.min(v + 0.25, 1.0);
      try { exp.setValue('blink', v); } catch(e) {}
      if (v >= 1.0) {
        clearInterval(intervalo);
        resolve();
      }
    }, 16);
  });
}

function abrirOjos(exp) {
  return new Promise(resolve => {
    let v = 1.0;
    const intervalo = setInterval(() => {
      v = Math.max(v - 0.22, 0); // apertura más lenta que el cierre
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

/**
 * Activa o desactiva la animación de parpadeo autónomo.
 * @param {boolean} activar
 */
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
// ANIMACIÓN — MÚSICA / BAILE SUTIL
// Balanceo corporal idle cuando hay música activa.
// Simula el movimiento involuntario de alguien esperando en la barra de una
// disco: sway lateral de cintura, rebote contralateral de brazos y muñecas,
// cabezeo suave al ritmo. No toca los ejes gestionados por animarRespiracion
// (.x de spine/chest) ni por animarMirada (.x/.y de head).
// Al desactivar, los huesos vuelven a pose de reposo con lerp suave.
// ═══════════════════════════════════════════════════════════════════════════

const musicaState = {
  activa:     false,
  tiempo:     0,
  intensidad: 0,      // 0 = parado, 1 = baile completo — se interpola en cada frame
  fadeDir:    0,      // +1 = fade-in, -1 = fade-out, 0 = estable
  modo:       'normal', // 'normal' | 'metal'
  // Seeds de aleatoriedad: regenerados en cada activación para que cada
  // sesión de baile sea diferente. Frecuencias irracionales entre sí para
  // evitar ciclos perceptibles en cualquier ventana de tiempo razonable.
  r1: 0, r2: 0, r3: 0
};

const MUSICA_FADE_SPEED = 0.015; // ~1.1 s a 60 FPS para ir de 0 a 1

/**
 * Animación de baile sutil: sway lateral del cuerpo + rebote de brazos y muñecas.
 * - La intensidad sube/baja suavemente según fadeDir (transición entrada/salida).
 * - Tres moduladores lentos con frecuencias irracionales rompen la periodicidad.
 * - Las seeds se regeneran en cada activación para variedad entre sesiones.
 * Llamada cada frame en animate().
 */
function animarMusica() {
  if (!currentVRM) return;
  if (!musicaState.activa && musicaState.intensidad <= 0) return;

  const { humanoid } = currentVRM;

  // ── Fade in / fade out ────────────────────────────────────────────────────
  if (musicaState.fadeDir !== 0) {
    musicaState.intensidad = Math.max(0, Math.min(1,
      musicaState.intensidad + musicaState.fadeDir * MUSICA_FADE_SPEED
    ));

    if (musicaState.fadeDir === -1 && musicaState.intensidad <= 0) {
      // Fade-out completado → limpiar huesos y detener del todo
      musicaState.fadeDir = 0;
      ['hips', 'spine', 'chest'].forEach(nombre => {
        const hueso = humanoid.getNormalizedBoneNode(nombre);
        if (hueso) hueso.rotation.z = 0;
      });
      poseNeutral(currentVRM);
      return;
    }
    if (musicaState.fadeDir === 1 && musicaState.intensidad >= 1) {
      musicaState.fadeDir = 0;
    }
  }

  const amp = musicaState.intensidad;
  if (amp <= 0) return;

  // Metal: tempo ligeramente más rápido (≈ 110 BPM base vs ≈ 70 BPM normal)
  const tickSpeed = musicaState.modo === 'metal' ? 0.09 : 0.06;
  musicaState.tiempo += tickSpeed;
  const t  = musicaState.tiempo;
  const { r1, r2, r3 } = musicaState;

  // ── Moduladores de aleatoriedad ───────────────────────────────────────────
  // Frecuencias primas entre sí → periodo de repetición > 30 minutos reales
  const mod1 = 0.65 + 0.35 * Math.sin(t * 0.031 + r1); // modula amplitud brazos
  const mod2 = 0.65 + 0.35 * Math.sin(t * 0.017 + r2); // modula amplitud antebrazos y cuello
  const mod3 = 0.50 + 0.10 * Math.sin(t * 0.023 + r3); // modula la frecuencia base del sway 0.90

  // ── Caderas y columna: sway en S ──────────────────────────────────────────
  // FRECUENCIA FIJA — mod3 solo modula amplitud, no velocidad
  const swayBase = Math.sin(t * 0.9);  // frecuencia fija

  const hips = humanoid.getNormalizedBoneNode('hips');
  if (hips)  hips.rotation.z  =  swayBase         * 0.02  * mod3 * amp;

  const spine = humanoid.getNormalizedBoneNode('spine');
  if (spine) spine.rotation.z = -swayBase         * 0.025 * mod3 * amp;

  const chest = humanoid.getNormalizedBoneNode('chest');
  if (chest) chest.rotation.z = -Math.sin(t * 0.9 + 0.4) * 0.02 * mod3 * amp;

  // ── Brazos superiores ────────────────────────────────────────────────────
  const swayArm = Math.sin(t + Math.PI);  // frecuencia fija
  if (leftArm) {
    leftArm.rotation.z = -1.2 + swayArm              * 0.03  * mod1 * amp;
    leftArm.rotation.x =        Math.sin(t * 2 + 1.0) * 0.015 * mod2 * amp;
  }
  if (rightArm) {
    rightArm.rotation.z = 1.2 - swayArm               * 0.03  * mod1 * amp;
    rightArm.rotation.x =       Math.sin(t * 2)        * 0.015 * mod2 * amp;
  }

  // ── Antebrazos ────────────────────────────────────────────────────────────
  const swayLower = Math.sin(t * 1.5 + 0.5);  // frecuencia fija
  if (leftLower)  leftLower.rotation.z  = -0.2 + swayLower * 0.02 * mod2 * amp;
  if (rightLower) rightLower.rotation.z =  0.2 - swayLower * 0.02 * mod2 * amp;

  // ── Muñecas: al doble de frecuencia, fase aleatoria ──────────────────────
  const leftHand  = humanoid.getNormalizedBoneNode('leftHand');
  const rightHand = humanoid.getNormalizedBoneNode('rightHand');
  if (leftHand) {
    leftHand.rotation.z = Math.sin(t * 2 + 1.2 + r1)    * 0.03 * mod1 * amp;
    leftHand.rotation.x = Math.sin(t * 1.4 + r2)        * 0.02 * mod2 * amp;
  }
  if (rightHand) {
    rightHand.rotation.z = Math.sin(t * 2 + r2)         * 0.03 * mod1 * amp;
    rightHand.rotation.x = Math.sin(t * 1.4 + 0.8 + r3) * 0.02 * mod2 * amp;
  }

  // ── Cuello: cabezeo; head.rotation.x/.y → animarMirada ───────────────────
  let ritmoVisible;
  const neck = humanoid.getNormalizedBoneNode('neck');
  // ── Cuello ────────────────────────────────────────────────────────────────
  if (neck) {
    ritmoVisible = Math.sin(t + 0.6);  // ← guardar aquí
    neck.rotation.z = -ritmoVisible      * 0.025 * mod3 * amp;
    neck.rotation.y =  Math.sin(t * 0.5 + r2) * 0.03  * mod1 * amp;
    neck.rotation.x =  Math.abs(Math.sin(t))  * 0.02  * mod2 * amp;
  }

  // ── Heavy metal: headbang dominante ──────────────────────────────────────
  // Perfil asimétrico: Math.pow(max(0,sin),0.6) pasa rápido por el punto alto
  // (cabeza erguida) y baja lentamente hacia adelante — motion de headbang real.
  // Se ejecuta DESPUÉS de animarMirada (order en animate()), por lo que
  // sobreescribe head.rotation.x con seguridad.
  if (musicaState.modo === 'metal') {
    const head = humanoid.getNormalizedBoneNode('head');
    const bang  = Math.pow(Math.max(0, Math.sin(t * 1.5)), 0.85);
    ritmoVisible = bang;
    if (head) {
      head.rotation.x = (0.02 + bang * 0.08) * amp;  // 0.02 reposo → 0.16 nod máximo
      head.rotation.y = miradaState.currentY;          // preservar giro lateral de mirada
    }
    
    if (neck) {
      neck.rotation.x = (0.015 + bang * 0.04) * amp;  // cuello acompaña el cabezazo
    }
  }

  // ── Dedo índice ───────────────────────────────────────────────────────────
  if (!musicaState._dedoSeed) musicaState._dedoSeed = Math.random() < 0.5 ? 'left' : 'right';
  const ladoDedo = musicaState._dedoSeed;

  const dedoProximal     = humanoid.getNormalizedBoneNode(`${ladoDedo}IndexProximal`);
  const dedoIntermediate = humanoid.getNormalizedBoneNode(`${ladoDedo}IndexIntermediate`);

  if (dedoProximal && ritmoVisible !== undefined) {
    dedoProximal.rotation.z     = (ladoDedo === 'left' ? -0.3 : 0.3) + ritmoVisible * 0.15 * amp;
    dedoIntermediate.rotation.z = (ladoDedo === 'left' ? -0.3 : 0.3) + ritmoVisible * 0.10 * amp;
  }

}

/**
 * Activa o desactiva la animación de baile sutil con fade gradual.
 * Al activar, regenera las seeds de aleatoriedad para que la sesión sea única.
 * Al desactivar, el fade-out termina de forma natural en animarMusica().
 * @param {boolean} activar
 * @param {'normal'|'metal'} modo - Estilo de baile (default: 'normal').
 */
function animacion_musica(activar = true, modo = 'normal') {
  if (activar) {
    musicaState.r1      = Math.random() * Math.PI * 2;
    musicaState.r2      = Math.random() * Math.PI * 2;
    musicaState.r3      = Math.random() * Math.PI * 2;
    musicaState.modo    = modo;
    musicaState.activa  = true;
    musicaState.fadeDir = 1;
    musicaState._dedoSeed = null;  // ← se sorteará de nuevo en el primer frame
    log(`Música activada (${modo})`);
  } else {
    musicaState.activa  = false;
    musicaState.fadeDir = -1;
    log('Música desactivada');
  }
}


// ═══════════════════════════════════════════════════════════════════════════
// WEBSOCKET
// Conexión al daemon Python. Reconexión automática cada 3 s si se pierde.
// El renderer solo recibe comandos; nunca envía datos al daemon.
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
// COMANDOS
// Despacha los mensajes JSON recibidos por WebSocket a las funciones
// correspondientes. Estructura del mensaje: { accion, parametros }
//
// Acciones disponibles:
//   emocion_happy / neutral             → expresión simple
//   emocion_angry                       → expresión + pose + auto-reset (parametros.duracion)
//   emocion_sad                         → expresión + pose + auto-reset (parametros.duracion)
//   emocion_relaxed                     → expresión + pose + auto-reset (parametros.duracion)
//   emocion_surprised                   → expresión + pose + auto-reset (parametros.duracion)
//   hablar                 → alias de emocion_happy
//   escuchar               → alias de emocion_neutral
//   alerta                 → alias de emocion_surprised
//   pose_reposo            → aplica pose corporal de reposo
//   mirar                  → rota cabeza a (x, y, z) exactos
//   mirada_despreocupada   → activa/desactiva animación idle de mirada
//   parpadeo               → activa/desactiva parpadeo autónomo
//   reset                  → neutral + mirada centrada
//   world                  → carga escenario desde parametros.path
//   world_rotation         → rota el escenario parametros.y radianes
//   world_luz              → iluminación on/off (parametros.estado: 'on' | 'off')
//   world_musica           → baile sutil on/off (parametros.estado: 'on' | 'off')
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
      activarSurprised(parametros.duracion ?? 5);
      break;
      
    case 'emocion_angry':
      activarAngry(parametros.duracion ?? 20);
      break;
      
    case 'emocion_sad':
      activarSad(parametros.duracion ?? 15);
      break;
      
    case 'emocion_relaxed':
      activarRelaxed(parametros.duracion ?? 10);
      break;

    case 'pose_reposo':
      if (currentVRM) aplicarPoseReposo(currentVRM);
      break;
      
    case 'mirar': {
      const { x = 0, y = 0, z = 0 } = parametros;
      mirarHacia(x, y, z);
      log(`Mirando hacia: (${x}, ${y}, ${z})`);
      break;
    }

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

    case 'world': {
      const { path } = parametros;
      if (path) {
        scene.children
          .filter(obj => obj.userData.isWorld)
          .forEach(obj => scene.remove(obj));
        loadWorld(path);
      }
      break;
    }
    
    case 'world_rotation': {
      const worldObj = scene.children.find(obj => obj.userData.isWorld);
      if (worldObj) worldObj.rotation.y = parametros.y;
      break;
    }

    case 'world_luz': {
      const encendida = parametros.estado === 'on';
      ambientLight.intensity     = encendida ? 1.0 : 0.3;
      directionalLight.intensity = encendida ? 0.9 : 0.3;
      log(`Iluminación: ${parametros.estado}`);
      break;
    }

    case 'world_musica':
      animacion_musica(parametros.estado === 'on', parametros.modo ?? 'normal');
      break;
      
    default:
      log(`⚠ Acción desconocida: ${accion}`);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// UI HELPERS
// Actualización del indicador de estado y del log de debug en pantalla.
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
// INICIALIZACIÓN
// Punto de entrada: arranca todos los subsistemas cuando la página está lista.
// ═══════════════════════════════════════════════════════════════════════════

window.addEventListener('load', () => {
  log('Inicializando Riatla...');
  setupScene();
  loadWorld();
  loadVRM();
  connectWebSocket();
});
