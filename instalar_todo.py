# instalar_librerias.py
import subprocess
import sys
import os

def instalar_todo():
    print("=" * 60)
    print("🔧 INSTALADOR DE LIBRERÍAS - SISTEMA DE CONTROL DE ACCESO")
    print("=" * 60)
    
    # Lista completa de librerías necesarias
    librerias = [
        "opencv-python==4.8.1.78",
        "pytesseract==0.3.10",
        "numpy==1.24.3",
        "pandas==2.0.3",
        "matplotlib==3.7.2",
        "pillow==10.0.1",
        "psycopg2-binary==2.9.9"
    ]
    
    print("\n📋 Librerías a instalar:")
    for i, lib in enumerate(librerias, 1):
        print(f"   {i}. {lib}")
    
    print("\n🚀 Iniciando instalación...\n")
    
    # Actualizar pip primero
    print("📦 Actualizando pip...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    
    # Instalar librerías
    for libreria in librerias:
        print(f"\n📦 Instalando {libreria}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", libreria])
            print(f"   ✅ {libreria} instalada")
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Error instalando {libreria}: {e}")
    
    print("\n" + "=" * 60)
    print("🔍 VERIFICANDO INSTALACIÓN")
    print("=" * 60)
    
    # Verificar cada importación
    verificaciones = [
        ("cv2", "opencv-python"),
        ("pytesseract", "pytesseract"),
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("matplotlib.pyplot", "matplotlib"),
        ("PIL", "pillow"),
        ("psycopg2", "psycopg2-binary")
    ]
    
    todo_ok = True
    for modulo, nombre in verificaciones:
        try:
            if modulo == "matplotlib.pyplot":
                __import__("matplotlib.pyplot")
                import matplotlib
                print(f"✅ {nombre:20} → {matplotlib.__version__}")
            elif modulo == "PIL":
                __import__("PIL")
                from PIL import Image
                print(f"✅ {nombre:20} → {Image.__version__}")
            else:
                module = __import__(modulo)
                version = getattr(module, "__version__", "desconocida")
                print(f"✅ {nombre:20} → {version}")
        except ImportError as e:
            print(f"❌ {nombre:20} → Error: {e}")
            todo_ok = False
    
    print("\n" + "=" * 60)
    if todo_ok:
        print("✨ ¡TODAS LAS LIBRERÍAS INSTALADAS CORRECTAMENTE!")
        print("✅ Ya puedes ejecutar tu programa Vehicle.py")
    else:
        print("⚠️ Algunas librerías tienen problemas")
    print("=" * 60)
    
    # Guardar requirements
    with open('requirements.txt', 'w') as f:
        subprocess.check_call([sys.executable, "-m", "pip", "freeze"], stdout=f)
    print("\n📄 Archivo requirements.txt creado")
    
    input("\nPresiona Enter para salir...")

if __name__ == "__main__":
    try:
        instalar_todo()
    except KeyboardInterrupt:
        print("\n\n❌ Instalación cancelada por el usuario")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        input("\nPresiona Enter para salir...")