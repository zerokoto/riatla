import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';
import { KTX2Loader } from 'three/examples/jsm/loaders/KTX2Loader.js';
//import { RGBELoader } from 'three/addons/loaders/RGBELoader.js';
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js';

//const path = require('path');

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

// Estado del shake de cámara
const cameraShake = {
  basePos: null,  // se inicializa al cargar el mundo
  time: 0
};

function setupScene() {
  // Canvas
  const canvas = document.getElementById('canvas');
  
  // Escena
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x2d2d44);

  // Ángulo reducido (10°) para acercar el plano facial sin distorsión
  camera = new THREE.PerspectiveCamera(
    13,
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
  ambientLight = new THREE.AmbientLight(0xffffff, 1.2);
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

// ═══════════════════════════════════════════════════════════════════════════
// CONFIGURACIÓN DE MUNDOS
// ═══════════════════════════════════════════════════════════════════════════

const WORLDS = {
  Studio: {
    path:     './world/Studio/studio.glb',
    scale:    6,
    rotation: Math.PI/2,
    offset:   { x: -2, y: -0.5, z: 0 },
    hdr:      './textures/space.hdr',   // ← añadir
    camera:   { pos: [3, 1.8, 6], lookAt: [0, 1.2, 0] }
  },
  TinyRoom: {
    path:     './world/TinyRoom/TinyRoom.glb',
    scale:    2.5,
    rotation: -Math.PI/8,
    offset:   { x: -0.2, y: 0, z: -0.5 },
    hdr:      './textures/studio.hdr',            // ← añadir
    camera:   { pos: [3, 1.8, 6], lookAt: [0, 1.2, 0] }
  },
  Space: {
    path:     './world/Space/space.glb',
    scale:    4,
    rotation: Math.PI + 0.1,
    hdr:      './textures/space.hdr',           // ← añadir
    camera:   { pos: [3, 1.8, 6], lookAt: [0, 1.2, 0] }
  },
  DND: {
    path:     './world/Dnd/dnd.glb',
    scale:    20,
    rotation: 0,
    offset:   { x: -6, y: -0.5, z: -4 },
    hdr:      './textures/space.hdr',           // ← añadir
    camera:   { pos: [3, 1.8, 6], lookAt: [0, 1.2, 0] }
  }
};

function loadWorld(nombre = 'TinyRoom') {
  const config = WORLDS[nombre];
  if (!config) {
    log(`✗ Mundo desconocido: ${nombre}`);
    return;
  }

  scene.children
    .filter(obj => obj.userData.isWorld)
    .forEach(obj => scene.remove(obj));

  const { pos, lookAt } = config.camera;
  camera.position.set(...pos);
  camera.lookAt(...lookAt);
  cameraShake.basePos = null;

  // Cargar HDR específico del mundo
  if (config.hdr) {
    const pmremGenerator = new THREE.PMREMGenerator(renderer);
    pmremGenerator.compileEquirectangularShader();

    new RGBELoader().load(
      config.hdr,
      (texture) => {
        const envMap = pmremGenerator.fromEquirectangular(texture).texture;
        scene.environment = envMap;
        texture.dispose();
        pmremGenerator.dispose();
        log(`✓ HDR cargado: ${config.hdr}`);
      },
      undefined,
      (err) => log(`✗ Error HDR: ${err.message}`)
    );
  }

  const ktx2Loader = new KTX2Loader()
    .setTranscoderPath('three/examples/jsm/libs/basis/')
    .detectSupport(renderer);

  const loader = new GLTFLoader();
  loader.setKTX2Loader(ktx2Loader);

  loader.load(
    config.path,
    (gltf) => {
      const world = gltf.scene;
      world.userData.isWorld     = true;
      world.userData.nombreMundo = nombre;

      const box  = new THREE.Box3().setFromObject(world);
      const size = box.getSize(new THREE.Vector3());

      const scale = config.scale / Math.max(size.x, size.z);
      world.scale.setScalar(scale);

      world.position.set(0, 0, 0);
      world.rotation.set(0, 0, 0);

      box.setFromObject(world);
      const scaledCenter = box.getCenter(new THREE.Vector3());
      const scaledMin    = box.min;

      world.position.set(-scaledCenter.x, -scaledMin.y, -scaledCenter.z);
      world.rotation.y = config.rotation;

      if (config.offset) {
        world.position.x += config.offset.x;
        world.position.y += config.offset.y;
        world.position.z += config.offset.z;
      }

      scene.add(world);
      log(`✓ Mundo: ${nombre} (escala: ${scale.toFixed(3)}, size: ${size.x.toFixed(1)}x${size.y.toFixed(1)}x${size.z.toFixed(1)})`);
    },
    (progress) => {
      const pct = Math.round((progress.loaded / progress.total) * 100);
      log(`Cargando ${nombre}... ${pct}%`);
    },
    (error) => {
      log(`✗ Error cargando ${nombre}: ${error.message}`);
    }
  );
}


// ═══════════════════════════════════════════════════════════════════════════
// CONFIGURACIÓN DE OBJETOS
// ═══════════════════════════════════════════════════════════════════════════

const OBJECTS = {
  libro: {
    path:     './props/book.glb',
    scale:    0.05,
    position: { x: 0.2, y: 1.1, z: 0.2 },  // delante del avatar, a su altura
    rotation: { x: 0,   y: Math.PI/4 + Math.PI,   z: 0 }  // rotación para que quede abierto y legible
  },
  musica: {
    path:     './props/music.glb',
    scale:    0.003,
    position: { x: 0, y: 1.5, z: 0 },  // delante del avatar, a su altura
    rotation: { x: 0,   y: 0,   z: 0 }  // rotación para que quede abierto y legible
  },
  comida: {
    path:     './props/food.glb',
    scale:    1.4,
    position: { x: -0.1, y: 1.15, z: 0.5 },  // delante del avatar, a su altura
    rotation: { x: 0,   y: Math.PI/16,   z: -Math.PI/8 }  // rotación para que quede abierto y legible
  },
  bebida: {
    path:     './props/drink.glb',
    scale:    0.9,
    position: { x: 0.28, y: 1.15, z: 0 },  // delante del avatar, a su altura
    rotation: { x: 0,   y: Math.PI/16,   z: -Math.PI/16 }  // rotación para que quede abierto y legible
  },
  timer: {
    path:     './props/timer.glb',
    scale:    0.8,
    position: { x: -0.27, y: 1.4, z: 0 },  // delante del avatar, a su altura
    rotation: { x: 0,   y: Math.PI/16,   z: Math.PI/8 }  // rotación para que quede abierto y legible
  },
  dnd: {
    path:     './props/dnd.glb',
    scale:    0.1,
    position: { x: -0.25, y: 1.5, z: 0 },  // delante del avatar, a su altura
    rotation: { x: Math.PI/8,   y: Math.PI/2,   z: 0 }  // rotación para que quede abierto y legible
  }

};

// ── Gestión de objetos activos ─────────────────────────────────────────────

const objetosActivos = {};  // { [nombre]: THREE.Object3D }

function addObjeto(nombre) {
  const config = OBJECTS[nombre];
  if (!config) {
    log(`✗ Objeto desconocido: ${nombre}`);
    return;
  }

  // Si ya existe, quitarlo primero
  if (objetosActivos[nombre]) removeObjeto(nombre);

  const loader = new GLTFLoader();
  loader.load(
    config.path,
    (gltf) => {
      const obj = gltf.scene;
      obj.userData.isObjeto   = true;
      obj.userData.nombreObj  = nombre;

      // Escala directa (no adaptativa — los props tienen tamaño conocido)
      obj.scale.setScalar(config.scale);

      obj.position.set(config.position.x, config.position.y, config.position.z);
      obj.rotation.set(config.rotation.x, config.rotation.y, config.rotation.z);

            // ── Animaciones del GLB ──────────────────────────────────────────────
      if (gltf.animations && gltf.animations.length > 0) {
        const mixer = new THREE.AnimationMixer(obj);
        gltf.animations.forEach(clip => {
          mixer.clipAction(clip).play();
        });
        obj.userData.mixer = mixer;
        log(`✓ Objeto ${nombre}: ${gltf.animations.length} animación(es)`);
      }

      config._seed = Math.random() * Math.PI * 2;
      scene.add(obj);
      objetosActivos[nombre] = obj;
      log(`✓ Objeto añadido: ${nombre}`);


      // Si es un libro, pausar mirada y centrarla en el libro
      if (nombre.startsWith('libro')) {
        miradaState.mirandoLibro = true;
        if (miradaState.timer) clearTimeout(miradaState.timer);
        // Mirar ligeramente hacia abajo y hacia donde está el libro
        miradaState.targetX =  0.2;  // ligeramente abajo (leyendo)
        miradaState.targetY = 0.2;   // hacia su izq donde está el libro

        // Pausar animación de muñeca izquierda si está bailando
        musicaState._brazoIzqBloqueado = true;  // ← añadir

        // Esperar a que cualquier pose anterior termine (lerp ~800ms)
        setTimeout(() => {
          if (!objetosActivos[nombre]) return; // por si lo quitaron antes
          lerpHueso(currentVRM, 'leftUpperArm', { x: Math.PI/10, y: -Math.PI/10, z: -Math.PI/4 });
          lerpHueso(currentVRM, 'leftLowerArm', { x: 0,          y: -Math.PI/2,  z: 0          });
          lerpHueso(currentVRM, 'leftHand',     { x: -Math.PI/2, y: 0,           z: 0          });
          iniciarLerp();
        }, 900); // 900ms > duración del lerp (800ms)
      }
    },
    undefined,
    (error) => log(`✗ Error cargando objeto ${nombre}: ${error.message}`)
  );
}

function removeObjeto(nombre) {
  const obj = objetosActivos[nombre];
  if (!obj) {
    log(`⚠ Objeto no activo: ${nombre}`);
    return;
  }

  if (obj.userData.mixer) {
    obj.userData.mixer.stopAllAction();
    obj.userData.mixer.uncacheRoot(obj);
  }
  scene.remove(obj);
  delete objetosActivos[nombre];
  log(`✓ Objeto eliminado: ${nombre}`);
  // Si era un libro, comprobar si quedan más libros activos
  if (nombre.startsWith('libro')) {
    const quedanLibros = Object.keys(objetosActivos).some(n => n.startsWith('libro'));
    if (!quedanLibros) {
      miradaState.mirandoLibro = false;
      musicaState._brazoIzqBloqueado = false; 

      // Devolver brazo a pose de reposo
      lerpHueso(currentVRM, 'leftUpperArm', { x: 0, y: 0, z: -1.2 });
      lerpHueso(currentVRM, 'leftLowerArm', { x: 0, y: 0, z: -0.2 });
      lerpHueso(currentVRM, 'leftHand',     { x: 0, y: 0, z:  0   });
      iniciarLerp();

      // Reactivar mirada despreocupada solo si no hay emoción activa
      if (expresionState.actual === 'neutral') {
        miradaState.targetX = 0;
        miradaState.targetY = 0;
        miradaState.activa  = true;
        programarSiguienteMirada();
      }
    }
  }
}

function removeAllObjetos() {
  Object.keys(objetosActivos).forEach(removeObjeto);
  log('Objetos limpiados');
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

function poseClosed(vrm) {
  const lado = Math.random() < 0.5 ? 1 : -1;

  // Cabeza inclinada hacia adelante (dormida)
  lerpHueso(vrm, 'head', { x:  0.25, y: lado * 0.05, z: lado * 0.03 });
  lerpHueso(vrm, 'neck', { x:  0.20, y: 0,           z: 0            });

  // Brazos completamente caídos y relajados
  lerpHueso(vrm, 'leftUpperArm',  { x:  0.1, y: 0, z: -1.4 });
  lerpHueso(vrm, 'rightUpperArm', { x:  0.1, y: 0, z:  1.4 });
  lerpHueso(vrm, 'leftLowerArm',  { x:  0,   y: 0, z: -0.1 });
  lerpHueso(vrm, 'rightLowerArm', { x:  0,   y: 0, z:  0.1 });
  lerpHueso(vrm, 'leftHand',      { x:  0.1, y: 0, z:  0   });
  lerpHueso(vrm, 'rightHand',     { x:  0.1, y: 0, z:  0   });

  iniciarLerp();
  removeAllObjetos();
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
  const expresiones = ['happy', 'angry', 'sad', 'relaxed', 'surprised', 'neutral','closed'];
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
  // Brazos completos
  lerpHueso(vrm, 'leftUpperArm',  { x: 0, y: 0, z: -1.2 });
  lerpHueso(vrm, 'rightUpperArm', { x: 0, y: 0, z:  1.2 });
  lerpHueso(vrm, 'leftLowerArm',  { x: 0, y: 0, z: -0.2 });
  lerpHueso(vrm, 'rightLowerArm', { x: 0, y: 0, z:  0.2 });
  lerpHueso(vrm, 'leftHand',      { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'rightHand',     { x: 0, y: 0, z:  0   });
  // Cabeza y cuello
  lerpHueso(vrm, 'head',          { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'neck',          { x: 0, y: 0, z:  0   });
  // Hombros
  lerpHueso(vrm, 'leftShoulder',  { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'rightShoulder', { x: 0, y: 0, z:  0   });
  // Torso
  lerpHueso(vrm, 'spine',         { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'chest',         { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'hips',          { x: 0, y: 0, z:  0   });
  iniciarLerp();
}

// ── Neutral: reset completo a estado base ──────────────────────────────────

/**
 * Revierte cualquier emoción activa: expresión + pose + parpadeo + mirada idle.
 * Puede llamarse desde cualquier estado para volver a la base.
 */
function activarNeutral() {
  if (!currentVRM) return;

  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  // Reactivar parpadeo si estaba desactivado (p.ej. desde closed)
  if (!parpadeoState.activo) animacion_parpadeo(true);

  activarExpresion('neutral');
  poseNeutral(currentVRM);

  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = false;
  miradaState.activa   = true;
  programarSiguienteMirada();

  expresionState.actual = 'neutral';
  log('Expresión: neutral');
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

  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  if (musicaState.activa && musicaState.modo === 'metal') {
    musicaState.modo = 'normal';
  }

  if (miradaState.timer) clearTimeout(miradaState.timer);
  miradaState.activa   = false;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = true;

  setTimeout(() => {
    miradaState.bloqueada = false;
  }, 900);

  removeAllObjetos();
  activarExpresion('angry');
  poseAngry(currentVRM); // poseAngry fija miradaState.targetX/Y

  expresionState.actual = 'angry';
  log(`Expresión: angry (${duracionSegundos}s)`);

  expresionState.timerReset = setTimeout(() => {
    desactivarAngry();
  }, duracionSegundos * 1000);
}

/** Revierte la emoción angry: expresión neutral + pose reposo + reactiva mirada idle. */
function desactivarAngry() {
  if (!currentVRM) return;

  activarExpresion('neutral');
  poseNeutral(currentVRM);

  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = false;
  miradaState.activa   = true;
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

  if (musicaState.activa && musicaState.modo === 'metal') {
    musicaState.modo = 'normal';
  }

  if (miradaState.timer) clearTimeout(miradaState.timer);
  miradaState.activa   = false;
  miradaState.targetX  = 0.15;  // ligeramente abajo (tristeza)
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = true;

  setTimeout(() => {
    miradaState.bloqueada = false;
  }, 900);

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

  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = false;
  miradaState.activa   = true;
  programarSiguienteMirada();

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde sad)');
}


// ── Pose happy ──────────────────────────────────────────────────────────────

/**
 * Postura alegre y abierta: cabeza levantada y ladeada, brazos ligeramente
 * separados del cuerpo en actitud receptiva y energética.
 */
function poseHappy(vrm) {
  const lado = Math.random() < 0.5 ? 1 : -1;

  // Cabeza ligeramente levantada y ladeada — actitud alegre y abierta
  lerpHueso(vrm, 'head', { x: -0.05, y: lado * 0.1,  z: lado * 0.06 });
  lerpHueso(vrm, 'neck', { x: -0.03, y: lado * 0.05, z: lado * 0.03 });

  // Brazos ligeramente abiertos — postura receptiva y energética
  lerpHueso(vrm, 'leftUpperArm',  { x:  0.05, y: -0.08, z: -1.0  });
  lerpHueso(vrm, 'rightUpperArm', { x:  0.05, y:  0.08, z:  1.0  });
  lerpHueso(vrm, 'leftLowerArm',  { x:  0.1,  y:  0,    z: -0.15 });
  lerpHueso(vrm, 'rightLowerArm', { x:  0.1,  y:  0,    z:  0.15 });
  lerpHueso(vrm, 'leftHand',      { x:  0,    y:  0,    z:  0    });
  lerpHueso(vrm, 'rightHand',     { x:  0,    y:  0,    z:  0    });

  iniciarLerp();
}

/**
 * Activa la emoción "happy": expresión facial + pose abierta + auto-reset.
 * La mirada idle se reactiva tras la transición (avatar alerta y comunicativo).
 * @param {number} duracionSegundos - Tiempo hasta volver a neutral (default: 30 s).
 */
function activarHappy(duracionSegundos = 30) {
  if (!currentVRM) return;

  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  // Mirada ligeramente arriba — apertura y energía positiva
  miradaState.targetX  = -0.05;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = true;

  // Desbloquear y reactivar mirada idle al terminar el lerp
  setTimeout(() => {
    miradaState.bloqueada = false;
    miradaState.activa    = true;
    programarSiguienteMirada();
  }, 900);

  activarExpresion('happy');
  poseHappy(currentVRM);

  expresionState.actual = 'happy';
  log(`Expresión: happy (${duracionSegundos}s)`);

  expresionState.timerReset = setTimeout(() => {
    desactivarHappy();
  }, duracionSegundos * 1000);
}

/** Revierte la emoción happy: expresión neutral + pose reposo + reactiva mirada idle. */
function desactivarHappy() {
  if (!currentVRM) return;

  activarExpresion('neutral');
  poseNeutral(currentVRM);

  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = false;
  miradaState.activa   = true;
  programarSiguienteMirada();

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde happy)');
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

  // Ambos brazos explícitamente — incluyendo manos y codos
  lerpHueso(vrm, 'leftUpperArm',  { x: 0, y: 0, z: -1.5 });
  lerpHueso(vrm, 'rightUpperArm', { x: 0, y: 0.5, z: 1.5 });
  lerpHueso(vrm, 'leftLowerArm',  { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'rightLowerArm', { x: 0, y: 0, z:  0   });
  lerpHueso(vrm, 'leftHand',      { x: 0, y: 0, z:  0   }); // ← reset mano de lectura
  lerpHueso(vrm, 'rightHand',     { x: 0, y: 0, z:  0   });

  iniciarLerp();
  removeAllObjetos();
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

  if (musicaState.activa && musicaState.modo === 'metal') {
    musicaState.modo = 'normal';
  }

  // Resetear mirada antes de bloquear
  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;  // ← forzar reset inmediato
  miradaState.currentY = 0;
  miradaState.bloqueada = true;  // ← bloquear durante el lerp

  // Desbloquear cuando el lerp termine (~800ms)
  setTimeout(() => {
    miradaState.bloqueada = false;
  }, 900);

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

  // Resetear completamente la mirada antes de reactivar
  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = false;

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde relaxed)');
}




// ── Pose closed ──────────────────────────────────────────────────────────


function activarClosed(duracionSegundos = 60) {
  if (!currentVRM) return;

  if (expresionState.timerReset) {
    clearTimeout(expresionState.timerReset);
    expresionState.timerReset = null;
  }

  if (musicaState.activa && musicaState.modo === 'metal') {
    musicaState.modo = 'normal';
  }

  // Pausar parpadeo — los ojos ya están cerrados
  animacion_parpadeo(false);  // ← añadir
  // Pausar mirada
  miradaState.activa   = false;
  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = true;

  setTimeout(() => {
    miradaState.bloqueada = false;
  }, 900);

  activarExpresion('closed');
  poseClosed(currentVRM);

  expresionState.actual = 'closed';
  log(`Expresión: closed (${duracionSegundos}s)`);

  expresionState.timerReset = setTimeout(() => {
    desactivarClosed();
  }, duracionSegundos * 1000);
}

function desactivarClosed() {
  if (!currentVRM) return;
  activarExpresion('neutral');
  poseNeutral(currentVRM);

  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = false;

  // Reactivar parpadeo al despertar
  animacion_parpadeo(true);   // ← añadir
  miradaState.activa = true;
  programarSiguienteMirada();

  expresionState.actual = 'neutral';
  log('Expresión: neutral (desde closed)');
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

  if (musicaState.activa && musicaState.modo === 'metal') {
    musicaState.modo = 'normal';
  }

  if (miradaState.timer) clearTimeout(miradaState.timer);
  miradaState.activa   = false;
  miradaState.targetX  = -0.1;  // ligeramente arriba (acompasa la cabeza)
  miradaState.targetY  =  0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = true;

  setTimeout(() => {
    miradaState.bloqueada = false;
  }, 900);

  removeAllObjetos();
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

  miradaState.targetX  = 0;
  miradaState.targetY  = 0;
  miradaState.currentX = 0;
  miradaState.currentY = 0;
  miradaState.bloqueada = false;
  miradaState.activa   = true;
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

/**
 * Mueve uno o varios huesos a rotaciones indicadas.
 * Acepta lerp suave o asignación directa.
 * 
 * Payload WebSocket:
 * { "accion": "hueso",
 *   "parametros": {
 *     "huesos": [
 *       { "nombre": "head",  "x": 0.1, "y": -0.2, "z": 0 },
 *       { "nombre": "neck",  "x": 0.05, "y": -0.1, "z": 0 }
 *     ],
 *     "duracion": 500,   // ms, opcional — default 800
 *     "lerp": true       // opcional — default true
 *   }
 * }
 */
function moverHuesos(huesos, duracionMs = 800, usarLerp = true) {
  if (!currentVRM) return;

  huesos.forEach(({ nombre, x = 0, y = 0, z = 0 }) => {
    if (usarLerp) {
      lerpHueso(currentVRM, nombre, { x, y, z }, duracionMs);
    } else {
      // Asignación directa sin interpolación
      const hueso = currentVRM.humanoid.getNormalizedBoneNode(nombre);
      if (hueso) {
        hueso.rotation.x = x;
        hueso.rotation.y = y;
        hueso.rotation.z = z;
      }
    }
  });

  if (usarLerp) iniciarLerp();
  log(`Huesos: ${huesos.map(h => h.nombre).join(', ')}`);
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
  animarObjetos(); 
  animarCamara();
  renderer.render(scene, camera);
}

// ── Animación de objetos flotantes ─────────────────────────────────────────

let objetoTime = 0;

function animarObjetos() {
  objetoTime += 0.01;

  Object.entries(objetosActivos).forEach(([nombre, obj]) => {
    const config = OBJECTS[nombre];
    if (!config) return;

    // Actualizar animaciones del GLB
    if (obj.userData.mixer) {
      obj.userData.mixer.update(1 / 60);
    }

    const seed = config._seed ?? 0;

    // Flotación vertical
    const floatY = Math.sin(objetoTime       + seed) * 0.01;
    // Flotación horizontal — frecuencia irracional respecto a Y
    const floatX = Math.sin(objetoTime * 0.7 + seed + 1.3) * 0.01;

    obj.position.y = config.position.y + floatY;
    obj.position.x = config.position.x + floatX;

    // Rotación lenta sobre Y para dar sensación de objeto mágico/ingrávido
    //obj.rotation.y = config.rotation.y + objetoTime * 0.3;
    // Sin rotacion:
    obj.rotation.y = config.rotation.y;
  });
}


// ── Shake de cámara ────────────────────────────────────────────────────────────
function animarCamara() {
  if (!cameraShake.basePos) {
    cameraShake.basePos = camera.position.clone();
  }

  cameraShake.time += 0.008;
  const t = cameraShake.time;

  // Frecuencias irracionales entre sí → movimiento no periódico
  const offsetX = Math.sin(t * 0.7  + 1.3) * 0.006  // ← antes 0.0015
                + Math.sin(t * 1.3  + 0.5) * 0.003;  // ← antes 0.0008
  const offsetY = Math.sin(t * 0.9  + 2.1) * 0.005  // ← antes 0.0012
                + Math.sin(t * 1.7  + 1.1) * 0.002;  // ← antes 0.0006

  camera.position.x = cameraShake.basePos.x + offsetX;
  camera.position.y = cameraShake.basePos.y + offsetY;
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
  timer:    null,
  mirandoLibro: false,
  bloqueada:    false
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

  const espera = randomEntre(10000, 20000); // 20-40s mirando a un lado

  miradaState.timer = setTimeout(() => {
    // Mover a posición random
    miradaState.targetY = gradosARadianes(randomGrados(35));
    miradaState.targetX = gradosARadianes(randomGrados(20));
    log(`Mirada → H:${Math.round(miradaState.targetY * 180 / Math.PI)}° V:${Math.round(miradaState.targetX * 180 / Math.PI)}°`);

    // Después de la espera, volver al centro
    const esperaCentro = randomEntre(10000, 15000); // 1-5s en el centro
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
  if (miradaState.bloqueada) return;  // ← añadir al inicio

  const head = currentVRM.humanoid.getNormalizedBoneNode('head');
  if (!head) return;

  if (miradaState.mirandoLibro && miradaState.activa) {
    miradaState.activa = false;
    if (miradaState.timer) clearTimeout(miradaState.timer);
  }

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

const MUSICA_FADE_SPEED = 0.001 //0.015; // ~1.1 s a 60 FPS para ir de 0 a 1

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
  const mod3 = (0.50 + 0.10 * Math.sin(t * 0.023 + r3))*0.5; // modula la frecuencia base del sway 0.90

  // ── Caderas y columna: sway en S ──────────────────────────────────────────
  // FRECUENCIA FIJA — mod3 solo modula amplitud, no velocidad
  const swayBase = Math.sin(t * 0.9);  // frecuencia fija

  const hips = humanoid.getNormalizedBoneNode('hips');
  if (hips)  hips.rotation.z  =  swayBase         * 0.02  * mod3 * amp * 0;

  const spine = humanoid.getNormalizedBoneNode('spine');
  if (spine) spine.rotation.z = -swayBase         * 0.025 * mod3 * amp;

  const chest = humanoid.getNormalizedBoneNode('chest');
  if (chest) chest.rotation.z = -Math.sin(t * 0.9 + 0.4) * 0.02 * mod3 * amp;

  // ── Brazos superiores ─────────────────────────────────────────────────────
  const swayArm = Math.sin(t + Math.PI);
  if (leftArm && !musicaState._brazoIzqBloqueado) {  // ← condición
    leftArm.rotation.z = -1.2 + swayArm               * 0.03  * mod1 * amp;
    leftArm.rotation.x =        Math.sin(t * 2 + 1.0) * 0.015 * mod2 * amp;
  }
  if (rightArm) {
    rightArm.rotation.z = 1.2 - swayArm               * 0.03  * mod1 * amp;
    rightArm.rotation.x =       Math.sin(t * 2)        * 0.015 * mod2 * amp;
  }

  // ── Antebrazos ────────────────────────────────────────────────────────────
  const swayLower = Math.sin(t * 1.5 + 0.5);
  if (leftLower && !musicaState._brazoIzqBloqueado) {  // ← condición
    leftLower.rotation.z = -0.2 + swayLower * 0.02 * mod2 * amp;
  }
  if (rightLower) {
    rightLower.rotation.z = 0.2 - swayLower * 0.02 * mod2 * amp;
  }

  // ── Muñecas ───────────────────────────────────────────────────────────────
  if (leftHand && !musicaState._brazoIzqBloqueado) {  // ← condición
    leftHand.rotation.z = Math.sin(t * 2 + 1.2 + r1) * 0.03 * mod1 * amp;
    leftHand.rotation.x = Math.sin(t * 1.4 + r2)      * 0.02 * mod2 * amp;
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
      head.rotation.x = (0.02 + bang * 0.08) * amp *0.5;  // 0.02 reposo → 0.16 nod máximo
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
//   emocion_happy                       → expresión + pose + auto-reset (parametros.duracion)
//   emocion_neutral                     → reset completo a estado base
//   emocion_angry                       → expresión + pose + auto-reset (parametros.duracion)
//   emocion_sad                         → expresión + pose + auto-reset (parametros.duracion)
//   emocion_relaxed                     → expresión + pose + auto-reset (parametros.duracion)
//   emocion_surprised                   → expresión + pose + auto-reset (parametros.duracion)
//   emocion_closed                      → expresión + pose + auto-reset (parametros.duracion)
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
      activarHappy(parametros.duracion ?? 30);
      break;
      
    case 'escuchar':
    case 'emocion_neutral':
      activarNeutral();
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

    case 'emocion_closed':
      activarClosed(parametros.duracion ?? 10);
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
      activarNeutral();
      log('Reset ejecutado');
      break;

    case 'world': {
      const nombre = parametros.nombre ?? parametros.path ?? 'TinyRoom';
      loadWorld(nombre);
      break;
    }
    
    case 'world_rotation': {
      const worldObj = scene.children.find(obj => obj.userData.isWorld);
      if (worldObj) worldObj.rotation.y = parametros.y;
      break;
    }

    case 'world_luz': {
      const encendida = parametros.estado === 'on';
      ambientLight.intensity     = encendida ? 1.2 : 0.3;
      directionalLight.intensity = encendida ? 0.8 : 0.3;
      log(`Iluminación: ${parametros.estado}`);
      break;
    }

    case 'world_musica':
      animacion_musica(parametros.estado === 'on', parametros.modo ?? 'normal');
      break;

    case 'objeto': {
      const { nombre, accion: accionObj = 'add' } = parametros;
      if (!nombre) break;
      if (accionObj === 'remove') removeObjeto(nombre);
      else if (accionObj === 'clear') removeAllObjetos();
      else addObjeto(nombre);
      break;
    }

    case 'hueso': {
      const { huesos = [], duracion = 800, lerp = true } = parametros;
      if (huesos.length > 0) moverHuesos(huesos, duracion, lerp);
      break;
    }
      
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
  loadWorld('TinyRoom');
  loadVRM();
  connectWebSocket();
});
