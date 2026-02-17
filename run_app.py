# -*- coding: utf-8 -*-
"""Script para ejecutar el Sistema de Control Vehicular - Modo Simplificado (Solo Estadísticas)"""

import sys
from Vehiculo import SistemaControlAccesoPostgreSQL

def main():
    """Ejecuta la aplicación"""
    print("="*70)
    print("🚗 SISTEMA DE CONTROL DE ACCESO VEHICULAR - MODO SOLO ESTADÍSTICAS")
    print("Conjunto Residencial 'Los Alamos'")
    print("="*70)
    print("\n📊 La aplicación mostrará SOLO ESTADÍSTICAS en tiempo real")
    print("   Las opciones de entrada/salida han sido deshabilitadas\n")
    
    try:
        # Intentar conexión con valores por defecto
        print("Intentando conectar a PostgreSQL con configuración por defecto...")
        print("(host=localhost, database=control_acceso, user=postgres)\n")
        
        db_config = {
            'host': 'localhost',
            'database': 'control_acceso',
            'user': 'postgres',
            'password': '',
            'port': 5432
        }
        
        # Crear y ejecutar la aplicación
        app = SistemaControlAccesoPostgreSQL(db_config)
        app.ejecutar()
        
    except KeyboardInterrupt:
        print("\n\n👋 Aplicación terminada por el usuario")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Si PostgreSQL no está disponible, la aplicación usará modo fallback con datos en memoria")
        
        # Forzar modo fallback
        print("\nIniciando en MODO FALLBACK (Memoria)...\n")
        try:
            app = SistemaControlAccesoPostgreSQL({})
            app.ejecutar()
        except Exception as e2:
            print(f"Error en modo fallback: {e2}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
