// Expresiones faciales (BlendShapes)
function activarExpresion(nombre) {
  if (!currentVRM) return;
  const exp = currentVRM.expressionManager;
  exp.setValue('happy', 0);    // resetea todas
  exp.setValue('neutral', 0);
  exp.setValue(nombre, 1.0);   // activa la deseada
}

// Mover la cabeza (ejemplo: mirar ligeramente arriba)
function mirarArriba() {
  const head = currentVRM.humanoid.getNormalizedBoneNode('head');
  if (head) head.rotation.x = -0.2;
}