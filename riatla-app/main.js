import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '@pixiv/three-vrm';

const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));

let currentVRM;

loader.load('./models/riatla.vrm', (gltf) => {
  const vrm = gltf.userData.vrm;
  VRMUtils.removeUnnecessaryJoints(vrm.scene); // optimización importante
  currentVRM = vrm;
  scene.add(vrm.scene);
});