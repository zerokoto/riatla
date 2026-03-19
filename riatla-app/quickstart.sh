#!/bin/bash
# Quick Start para Riatla App

echo "════════════════════════════════════════════════════════"
echo "  🎭 RIATLA APP - INICIADOR RÁPIDO"
echo "════════════════════════════════════════════════════════"
echo ""

# Detectar SO
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
    echo "🪟 Detectado: Windows (PowerShell)"
    
    # Instalar dependencias
    echo ""
    echo "📦 Instalando dependencias..."
    npm install
    
    echo ""
    echo "✅ Instalación completada."
    echo ""
    echo "Para iniciar la app:"
    echo "  npm start"
    echo ""
    echo "Para desarrollo (con DevTools):"
    echo "  npm run dev"
    echo ""
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "🐧 Detectado: Linux"
    
    # Verificar si Node.js está instalado
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js no está instalado."
        echo "Instálalo desde: https://nodejs.org"
        exit 1
    fi
    
    echo "📦 Instalando dependencias..."
    npm install
    
    echo ""
    echo "✅ Instalación completada."
    echo ""
    echo "Para iniciar la app:"
    echo "  npm start"
    
elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "🍎 Detectado: macOS"
    
    # Verificar si Node.js está instalado
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js no está instalado."
        echo "Instálalo con: brew install node"
        exit 1
    fi
    
    echo "📦 Instalando dependencias..."
    npm install
    
    echo ""
    echo "✅ Instalación completada."
    echo ""
    echo "Para iniciar la app:"
    echo "  npm start"
    
else
    echo "⚠️  SO no reconocido: $OSTYPE"
    echo "Ejecuta manualmente: npm install && npm start"
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo ""
