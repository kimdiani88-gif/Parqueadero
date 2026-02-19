# -*- coding: utf-8 -*-
"""Sistema de Control de Acceso Vehicular - PostgreSQL (CORREGIDO: Liquidación funcional + ESTILO MEJORADO + COLORES OPTIMIZADOS)"""

# =============================================================================
# INSTALACIÓN DE DEPENDENCIAS (ejecutar en terminal)
# =============================================================================
"""
pip install opencv-python pytesseract numpy pandas matplotlib pillow psycopg2-binary
"""

import cv2
import pytesseract
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from PIL import Image
import io
import time
import re
import os
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk, filedialog
import threading
import psycopg2
from psycopg2 import sql, Error
from psycopg2.extras import RealDictCursor

import shutil

# Configurar pytesseract (ajustar ruta según tu instalación)
def _find_tesseract():
    # 1) Respect environment variables if provided
    env = os.environ.get('TESSERACT_CMD') or os.environ.get('TESSERACT_PATH')
    if env and os.path.exists(env):
        return env

    # 2) Check PATH
    which = shutil.which('tesseract')
    if which:
        return which

    # 3) Common installation locations
    if os.name == 'nt':
        candidates = [r'C:\Program Files\Tesseract-OCR\tesseract.exe',
                      r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe']
    else:
        candidates = ['/usr/bin/tesseract', '/usr/local/bin/tesseract']

    for c in candidates:
        if os.path.exists(c):
            return c

    return None

tesseract_path = _find_tesseract()
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    print('WARNING: tesseract binary not found. Install Tesseract and/or set the TESSERACT_CMD environment variable.')
    if os.name == 'nt':
        # keep the conventional default so user sees intended path in code
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

# =============================================================================
# GESTOR DE BASE DE DATOS POSTGRESQL
# =============================================================================

class PostgreSQLManager:
    """Gestor de base de datos PostgreSQL con manejo de errores mejorado"""
    
    def __init__(self, config=None):
        """
        Inicializa el gestor de base de datos PostgreSQL
        config: diccionario con configuración de conexión
        """
        self.config = config or {}
        self.connection = None
        self.cursor = None
        self.conectado = False
        
        # Configuración por defecto
        self.db_config = {
            'host': config.get('host', 'localhost'),
            'database': config.get('database', 'control_acceso'),
            'user': config.get('user', 'postgres'),
            'password': config.get('password', ''),
            'port': config.get('port', 5432)
        }
        
        # Intentar conectar
        if self.conectar():
            self.crear_estructura_bd()
            self.insertar_datos_iniciales()
    
    def conectar(self):
        """Establece conexión con la base de datos PostgreSQL"""
        try:
            self.connection = psycopg2.connect(**self.db_config)
            self.connection.autocommit = False
            self.cursor = self.connection.cursor(cursor_factory=RealDictCursor)
            self.conectado = True
            print(f"✅ Conectado a PostgreSQL en {self.db_config['host']}/{self.db_config['database']}")
            return True
        except Exception as e:
            print(f"❌ Error conectando a PostgreSQL: {e}")
            self.conectado = False
            self.connection = None
            self.cursor = None
            return False
    
    def verificar_conexion(self):
        """Verifica si la conexión está activa"""
        if not self.conectado or not self.connection or not self.cursor:
            return False
        try:
            # Probar la conexión con una consulta simple
            self.cursor.execute("SELECT 1")
            return True
        except:
            self.conectado = False
            return False
    
    def crear_estructura_bd(self):
        """Crea la estructura de la base de datos"""
        if not self.verificar_conexion():
            print("⚠️ No hay conexión a la base de datos para crear estructura")
            return False
        
        try:
            # Tabla residentes
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS residentes (
                    id SERIAL PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    apartamento VARCHAR(20) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Tabla parqueaderos
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS parqueaderos (
                    id SERIAL PRIMARY KEY,
                    numero INTEGER UNIQUE NOT NULL,
                    estado VARCHAR(10) CHECK (estado IN ('LIBRE','OCUPADO')) DEFAULT 'LIBRE',
                    residente_id INTEGER UNIQUE,
                    FOREIGN KEY (residente_id) REFERENCES residentes(id)
                )
            """)
            
            # Tabla placas
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS placas (
                    id SERIAL PRIMARY KEY,
                    residente_id INTEGER NOT NULL,
                    placa VARCHAR(10) UNIQUE NOT NULL,
                    FOREIGN KEY (residente_id) REFERENCES residentes(id) ON DELETE CASCADE
                )
            """)
            
            # Tabla registros_visitantes
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS registros_visitantes (
                    id SERIAL PRIMARY KEY,
                    placa VARCHAR(10) NOT NULL,
                    parqueadero_id INTEGER NOT NULL,
                    hora_entrada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    hora_salida TIMESTAMP,
                    total_horas NUMERIC(5,2),
                    valor_pagado NUMERIC(10,2),
                    FOREIGN KEY (parqueadero_id) REFERENCES parqueaderos(id)
                )
            """)
            
            # Función para calcular el pago
            self.cursor.execute("""
                CREATE OR REPLACE FUNCTION calcular_pago()
                RETURNS TRIGGER AS $$
                DECLARE
                    horas NUMERIC;
                BEGIN
                    horas := EXTRACT(EPOCH FROM (NEW.hora_salida - NEW.hora_entrada)) / 3600;
                    NEW.total_horas := ROUND(horas,2);
                    
                    -- Cálculo de tarifa: primeras 5 horas a $1000/hora (o fracción), después tarifa plena de $10000
                    IF horas <= 5 THEN
                        NEW.valor_pagado := CEIL(horas) * 1000;
                    ELSE
                        NEW.valor_pagado := 10000;
                    END IF;
                    
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            
            # Trigger
            self.cursor.execute("""
                DROP TRIGGER IF EXISTS trigger_calculo_pago ON registros_visitantes;
                
                CREATE TRIGGER trigger_calculo_pago
                BEFORE UPDATE ON registros_visitantes
                FOR EACH ROW
                WHEN (NEW.hora_salida IS NOT NULL)
                EXECUTE FUNCTION calcular_pago();
            """)
            
            self.connection.commit()
            print("✅ Estructura de base de datos creada/verificada")
            return True
            
        except Exception as e:
            print(f"Error creando estructura: {e}")
            if self.connection:
                self.connection.rollback()
            return False
    
    def insertar_datos_iniciales(self):
        """Inserta datos iniciales de ejemplo"""
        if not self.verificar_conexion():
            return False
        
        try:
            # Verificar si ya hay datos
            self.cursor.execute("SELECT COUNT(*) as count FROM residentes")
            result = self.cursor.fetchone()
            if result and result['count'] > 0:
                return True
            
            # Insertar residentes
            residentes_data = [
                ('Juan Pérez', '101'),
                ('María Gómez', '202'),
                ('Carlos López', '303'),
                ('Ana Martínez', '404'),
                ('Pedro Sánchez', '505')
            ]
            
            placas_data = ['ABC123', 'DEF456', 'GHI789', 'JKL012', 'MNO345']
            
            for i, (nombre, apto) in enumerate(residentes_data):
                # Insertar residente
                self.cursor.execute(
                    "INSERT INTO residentes (nombre, apartamento) VALUES (%s, %s) RETURNING id",
                    (nombre, apto)
                )
                residente_id = self.cursor.fetchone()['id']
                
                # Insertar parqueadero para residente (números 1-5)
                self.cursor.execute(
                    "INSERT INTO parqueaderos (numero, residente_id) VALUES (%s, %s)",
                    (i + 1, residente_id)
                )
                
                # Insertar placa
                self.cursor.execute(
                    "INSERT INTO placas (residente_id, placa) VALUES (%s, %s)",
                    (residente_id, placas_data[i])
                )
            
            # Insertar parqueaderos adicionales para visitantes (números 6-10)
            for i in range(6, 11):
                self.cursor.execute(
                    "INSERT INTO parqueaderos (numero) VALUES (%s)",
                    (i,)
                )
            
            self.connection.commit()
            print("✅ Datos iniciales insertados correctamente")
            return True
            
        except Exception as e:
            print(f"Error insertando datos iniciales: {e}")
            if self.connection:
                self.connection.rollback()
            return False
    
    # ============= CONSULTAS PRINCIPALES =============
    
    def verificar_placa_residente(self, placa):
        """Verifica si una placa es de residente"""
        if not self.verificar_conexion():
            return None
        
        try:
            query = """
                SELECT r.nombre, r.apartamento, p.numero AS parqueadero, p.estado
                FROM placas pl
                JOIN residentes r ON pl.residente_id = r.id
                JOIN parqueaderos p ON p.residente_id = r.id
                WHERE pl.placa = %s
            """
            self.cursor.execute(query, (placa,))
            return self.cursor.fetchone()
        except Exception as e:
            print(f"Error en verificar_placa_residente: {e}")
            return None
    
    def registrar_entrada_visitante(self, placa, parqueadero_id):
        """Registra entrada de visitante"""
        if not self.verificar_conexion():
            return None
        
        try:
            # Insertar registro de visitante
            self.cursor.execute("""
                INSERT INTO registros_visitantes (placa, parqueadero_id)
                VALUES (%s, %s)
                RETURNING id
            """, (placa, parqueadero_id))
            
            registro_id = self.cursor.fetchone()['id']
            
            # Actualizar estado del parqueadero
            self.cursor.execute("""
                UPDATE parqueaderos
                SET estado = 'OCUPADO'
                WHERE id = %s
            """, (parqueadero_id,))
            
            self.connection.commit()
            return registro_id
            
        except Exception as e:
            print(f"Error registrando entrada: {e}")
            if self.connection:
                self.connection.rollback()
            return None
    
    def registrar_salida_visitante(self, registro_id, parqueadero_id):
        """Registra salida de visitante (el trigger calcula el pago automáticamente)"""
        if not self.verificar_conexion():
            return None
        
        try:
            # Actualizar hora de salida (el trigger calculará automáticamente)
            self.cursor.execute("""
                UPDATE registros_visitantes
                SET hora_salida = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING total_horas, valor_pagado, hora_salida
            """, (registro_id,))
            
            resultado = self.cursor.fetchone()
            
            # Liberar parqueadero
            self.cursor.execute("""
                UPDATE parqueaderos
                SET estado = 'LIBRE'
                WHERE id = %s
            """, (parqueadero_id,))
            
            # Si el trigger no devolvió valores, intentar cálculo manual
            if resultado is None or resultado.get('valor_pagado') is None:
                self.cursor.execute("SELECT hora_entrada, hora_salida FROM registros_visitantes WHERE id = %s", (registro_id,))
                fila = self.cursor.fetchone()
                if fila and fila.get('hora_entrada') and fila.get('hora_salida'):
                    he = fila['hora_entrada']
                    hs = fila['hora_salida']
                    # Asegurar tipos datetime
                    if isinstance(he, str):
                        he = datetime.fromisoformat(he.replace('Z', '+00:00'))
                    if isinstance(hs, str):
                        hs = datetime.fromisoformat(hs.replace('Z', '+00:00'))
                    
                    if he.tzinfo:
                        he = he.replace(tzinfo=None)
                    if hs.tzinfo:
                        hs = hs.replace(tzinfo=None)
                    
                    horas = (hs - he).total_seconds() / 3600
                    if horas <= 5:
                        valor = int(np.ceil(horas)) * 1000
                    else:
                        valor = 10000
                    resultado = {'total_horas': round(horas, 2), 'valor_pagado': valor, 'hora_salida': hs}

            self.connection.commit()
            return resultado
            
        except Exception as e:
            print(f"Error registrando salida: {e}")
            if self.connection:
                self.connection.rollback()
            return None
    
    def obtener_parqueaderos_libres_visitantes(self):
        """Obtiene parqueaderos libres para visitantes"""
        if not self.verificar_conexion():
            return []
        
        try:
            self.cursor.execute("""
                SELECT id, numero 
                FROM parqueaderos 
                WHERE residente_id IS NULL 
                AND estado = 'LIBRE'
                ORDER BY numero
            """)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error obteniendo parqueaderos libres: {e}")
            return []
    
    def marcar_parqueadero_ocupado(self, numero_parqueadero):
        """Marca un parqueadero como OCUPADO (para residentes)"""
        if not self.verificar_conexion():
            return False
        
        try:
            self.cursor.execute("""
                UPDATE parqueaderos
                SET estado = 'OCUPADO'
                WHERE numero = %s
            """, (numero_parqueadero,))
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Error marcando parqueadero como ocupado: {e}")
            if self.connection:
                self.connection.rollback()
            return False
    
    def marcar_parqueadero_libre(self, numero_parqueadero):
        """Marca un parqueadero como LIBRE (para residentes)"""
        if not self.verificar_conexion():
            return False
        
        try:
            self.cursor.execute("""
                UPDATE parqueaderos
                SET estado = 'LIBRE'
                WHERE numero = %s
            """, (numero_parqueadero,))
            self.connection.commit()
            return True
        except Exception as e:
            print(f"Error marcando parqueadero como libre: {e}")
            if self.connection:
                self.connection.rollback()
            return False
    
    def obtener_visitante_activo_por_placa(self, placa):
        """Obtiene un visitante activo por su placa"""
        if not self.verificar_conexion():
            return None
        
        try:
            self.cursor.execute("""
                SELECT rv.id, rv.placa, rv.hora_entrada, rv.parqueadero_id, p.numero as parqueadero
                FROM registros_visitantes rv
                JOIN parqueaderos p ON rv.parqueadero_id = p.id
                WHERE rv.placa = %s AND rv.hora_salida IS NULL
                ORDER BY rv.hora_entrada DESC
                LIMIT 1
            """, (placa,))
            return self.cursor.fetchone()
        except Exception as e:
            print(f"Error obteniendo visitante activo: {e}")
            return None
    
    def obtener_visitantes_activos(self):
        """Obtiene todos los visitantes activos"""
        if not self.verificar_conexion():
            return []
        
        try:
            self.cursor.execute("""
                SELECT rv.id, rv.placa, rv.hora_entrada, p.numero as parqueadero
                FROM registros_visitantes rv
                JOIN parqueaderos p ON rv.parqueadero_id = p.id
                WHERE rv.hora_salida IS NULL
                ORDER BY rv.hora_entrada
            """)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error obteniendo visitantes activos: {e}")
            return []
    
    def obtener_historial_visitantes(self, limit=100):
        """Obtiene el historial de visitantes"""
        if not self.verificar_conexion():
            return []
        
        try:
            self.cursor.execute("""
                SELECT rv.id, rv.placa, rv.hora_entrada, rv.hora_salida, 
                       rv.total_horas, rv.valor_pagado, p.numero as parqueadero
                FROM registros_visitantes rv
                JOIN parqueaderos p ON rv.parqueadero_id = p.id
                WHERE rv.hora_salida IS NOT NULL
                ORDER BY rv.hora_salida DESC
                LIMIT %s
            """, (limit,))
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error obteniendo historial: {e}")
            return []
    
    def obtener_estado_parqueaderos(self):
        """Obtiene el estado de todos los parqueaderos con datos de residentes"""
        if not self.verificar_conexion():
            return []
        
        try:
            self.cursor.execute("""
                SELECT p.id, p.numero, p.estado, 
                       r.nombre as residente, r.apartamento,
                       (SELECT pl.placa FROM placas pl 
                        WHERE pl.residente_id = r.id LIMIT 1) as placa
                FROM parqueaderos p
                LEFT JOIN residentes r ON p.residente_id = r.id
                ORDER BY p.numero
            """)
            return self.cursor.fetchall()
        except Exception as e:
            print(f"Error obteniendo estado parqueaderos: {e}")
            return []
    
    def obtener_estadisticas(self):
        """Obtiene estadísticas generales"""
        stats = {
            'total_parqueaderos': 0,
            'ocupados': 0,
            'visitantes_activos': 0,
            'total_recaudado': 0,
            'recaudado_hoy': 0
        }
        
        if not self.verificar_conexion():
            return stats
        
        try:
            # Total parqueaderos
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos")
            result = self.cursor.fetchone()
            stats['total_parqueaderos'] = result['count'] if result else 0
            
            # Parqueaderos ocupados
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE estado = 'OCUPADO'")
            result = self.cursor.fetchone()
            stats['ocupados'] = result['count'] if result else 0
            
            # Visitantes activos
            self.cursor.execute("SELECT COUNT(*) as count FROM registros_visitantes WHERE hora_salida IS NULL")
            result = self.cursor.fetchone()
            stats['visitantes_activos'] = result['count'] if result else 0
            
            # Total recaudado
            self.cursor.execute("SELECT COALESCE(SUM(valor_pagado), 0) as total FROM registros_visitantes")
            result = self.cursor.fetchone()
            stats['total_recaudado'] = float(result['total']) if result else 0
            
            # Recaudado hoy
            self.cursor.execute("""
                SELECT COALESCE(SUM(valor_pagado), 0) as total 
                FROM registros_visitantes 
                WHERE DATE(hora_salida) = CURRENT_DATE
            """)
            result = self.cursor.fetchone()
            stats['recaudado_hoy'] = float(result['total']) if result else 0
            
            return stats
            
        except Exception as e:
            print(f"Error obteniendo estadísticas: {e}")
            return stats
    
    def obtener_estadisticas_por_tipo(self):
        """Obtiene estadísticas separadas por tipo de parqueadero"""
        stats = {
            'residentes': {
                'total': 0,
                'ocupados': 0,
                'libres': 0,
                'ingresos': 0
            },
            'visitantes': {
                'total': 0,
                'ocupados': 0,
                'libres': 0,
                'ingresos': 0,
                'activos': 0
            }
        }
        
        if not self.verificar_conexion():
            return stats
        
        try:
            # PARQUEADEROS DE RESIDENTES
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE residente_id IS NOT NULL")
            result = self.cursor.fetchone()
            stats['residentes']['total'] = result['count'] if result else 0
            
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE residente_id IS NOT NULL AND estado = 'OCUPADO'")
            result = self.cursor.fetchone()
            stats['residentes']['ocupados'] = result['count'] if result else 0
            
            stats['residentes']['libres'] = stats['residentes']['total'] - stats['residentes']['ocupados']
            
            # PARQUEADEROS DE VISITANTES
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE residente_id IS NULL")
            result = self.cursor.fetchone()
            stats['visitantes']['total'] = result['count'] if result else 0
            
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE residente_id IS NULL AND estado = 'OCUPADO'")
            result = self.cursor.fetchone()
            stats['visitantes']['ocupados'] = result['count'] if result else 0
            
            stats['visitantes']['libres'] = stats['visitantes']['total'] - stats['visitantes']['ocupados']
            
            # Visitantes activos
            self.cursor.execute("SELECT COUNT(*) as count FROM registros_visitantes WHERE hora_salida IS NULL")
            result = self.cursor.fetchone()
            stats['visitantes']['activos'] = result['count'] if result else 0
            
            # Ingresos por tipo
            self.cursor.execute("""
                SELECT COALESCE(SUM(rg.valor_pagado), 0) as total
                FROM registros_visitantes rg
                JOIN parqueaderos p ON rg.parqueadero_id = p.id
                WHERE p.residente_id IS NULL
            """)
            result = self.cursor.fetchone()
            stats['visitantes']['ingresos'] = float(result['total']) if result else 0
            
            self.cursor.execute("""
                SELECT COALESCE(SUM(rg.valor_pagado), 0) as total
                FROM registros_visitantes rg
                JOIN parqueaderos p ON rg.parqueadero_id = p.id
                WHERE p.residente_id IS NOT NULL
            """)
            result = self.cursor.fetchone()
            stats['residentes']['ingresos'] = float(result['total']) if result else 0
            
            return stats
            
        except Exception as e:
            print(f"Error obteniendo estadísticas por tipo: {e}")
            return stats
    
    def cerrar(self):
        """Cierra la conexión a la base de datos"""
        try:
            if self.cursor:
                self.cursor.close()
            if self.connection:
                self.connection.close()
                print("🔌 Conexión a PostgreSQL cerrada")
        except Exception as e:
            print(f"Error cerrando conexión: {e}")

# =============================================================================
# SISTEMA PRINCIPAL
# =============================================================================

class SistemaControlAccesoPostgreSQL:
    def __init__(self, db_config=None):
        """
        Inicializa el sistema con base de datos PostgreSQL
        db_config: configuración de conexión
        """
        self.db = None
        self.db_config = db_config or {}
        self.usar_datos_memoria = False
        self.datos_memoria = self.inicializar_datos_memoria()
        
        # Intentar conectar a PostgreSQL
        print("\n" + "="*60)
        print("CONECTANDO A POSTGRESQL")
        print("="*60)
        print(f"Host: {self.db_config.get('host', 'localhost')}")
        print(f"Database: {self.db_config.get('database', 'control_acceso')}")
        print(f"User: {self.db_config.get('user', 'postgres')}")
        print("="*60)
        
        self.db = PostgreSQLManager(self.db_config)
        
        if self.db and self.db.conectado:
            print("✅ Usando base de datos PostgreSQL")
            self.usar_datos_memoria = False
        else:
            print("⚠️ Usando datos en memoria como fallback")
            self.usar_datos_memoria = True
            self.db = None
        
        # Crear ventana principal
        self.crear_interfaz()
    
    def inicializar_datos_memoria(self):
        """Inicializa datos en memoria como fallback"""
        return {
            'residentes': {
                'ABC123': {'nombre': 'Juan Pérez', 'parqueadero': 1, 'estado': 'libre', 'apartamento': '101'},
                'DEF456': {'nombre': 'María Gómez', 'parqueadero': 2, 'estado': 'libre', 'apartamento': '202'},
                'GHI789': {'nombre': 'Carlos López', 'parqueadero': 3, 'estado': 'libre', 'apartamento': '303'},
                'JKL012': {'nombre': 'Ana Martínez', 'parqueadero': 4, 'estado': 'libre', 'apartamento': '404'},
                'MNO345': {'nombre': 'Pedro Sánchez', 'parqueadero': 5, 'estado': 'libre', 'apartamento': '505'},
            },
            'visitantes_activos': {},
            'historial_visitantes': [],
            'parqueaderos_visitantes': [6, 7, 8, 9, 10],
            'total_parqueaderos_visitantes': 5
        }
    
    def crear_interfaz(self):
        """Crea la interfaz gráfica con tkinter - ESTILO MEJORADO"""
        self.ventana = tk.Tk()
        self.ventana.title("🚗 Sistema de Control de Acceso Vehicular - PostgreSQL")
        self.ventana.geometry("1200x700")
        self.ventana.configure(bg='#f5f5f5')
        
        # Configurar estilos modernos
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colores del tema moderno
        color_primario = '#2c3e50'      # Azul oscuro
        color_secundario = '#34495e'     # Azul grisáceo
        color_acento = '#3498db'         # Azul brillante
        color_exito = '#27ae60'          # Verde
        color_advertencia = '#f39c12'    # Naranja
        color_peligro = '#e74c3c'        # Rojo
        color_fondo = '#f5f5f5'           # Gris muy claro
        
        # ========== MENÚ SUPERIOR DESTACADO ==========
        menubar = tk.Menu(self.ventana, bg=color_primario, fg='white', 
                          activebackground=color_acento, activeforeground='white',
                          font=('Arial', 10, 'bold'))
        self.ventana.config(menu=menubar)
        
        # Menú Archivo
        file_menu = tk.Menu(menubar, tearoff=0, bg=color_secundario, fg='white',
                           activebackground=color_acento, activeforeground='white')
        menubar.add_cascade(label="📁 Archivo", menu=file_menu, background=color_primario)
        file_menu.add_command(label="⚙️ Configuración", command=self.mostrar_configuracion)
        file_menu.add_separator()
        file_menu.add_command(label="🚪 Salir", command=self.ventana.quit)
        
        # Menú Parqueaderos
        parking_menu = tk.Menu(menubar, tearoff=0, bg=color_secundario, fg='white',
                              activebackground=color_acento, activeforeground='white')
        menubar.add_cascade(label="🅿️ Parqueaderos", menu=parking_menu)
        parking_menu.add_command(label="📊 Ver Estado", command=self.mostrar_estado_parqueaderos)
        parking_menu.add_command(label="📋 Ver Historial", command=self.mostrar_historial)
        
        # Menú Reportes
        reportes_menu = tk.Menu(menubar, tearoff=0, bg=color_secundario, fg='white',
                               activebackground=color_acento, activeforeground='white')
        menubar.add_cascade(label="📈 Reportes", menu=reportes_menu)
        reportes_menu.add_command(label="💰 Reporte de Ingresos", command=self.mostrar_reporte_ingresos)
        reportes_menu.add_command(label="📊 Estadísticas", command=self.mostrar_estadisticas_detalladas)
        
        # Menú Ayuda
        ayuda_menu = tk.Menu(menubar, tearoff=0, bg=color_secundario, fg='white',
                            activebackground=color_acento, activeforeground='white')
        menubar.add_cascade(label="❓ Ayuda", menu=ayuda_menu)
        ayuda_menu.add_command(label="📖 Manual de Usuario", command=self.mostrar_manual)
        ayuda_menu.add_command(label="ℹ️ Acerca de", command=self.mostrar_acerca_de)
        
        # ========== BARRA SUPERIOR CON TÍTULO ==========
        header_frame = tk.Frame(self.ventana, bg=color_primario, height=100)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        # Barra decorativa superior
        top_bar = tk.Frame(header_frame, bg=color_peligro, height=4)
        top_bar.pack(fill='x')
        
        # Contenedor del título y estado
        title_container = tk.Frame(header_frame, bg=color_primario)
        title_container.pack(expand=True, fill='both', padx=20)
        
        # Título principal
        title_label = tk.Label(title_container, 
                              text="🚗 SISTEMA DE CONTROL DE ACCESO VEHICULAR",
                              font=('Arial', 18, 'bold'),
                              bg=color_primario,
                              fg='white')
        title_label.pack(pady=(10, 5))
        
        # Subtítulo con estado de BD
        db_status = "PostgreSQL" if not self.usar_datos_memoria else "Memoria (Fallback)"
        db_color = color_exito if not self.usar_datos_memoria else color_advertencia
        subtitle_frame = tk.Frame(title_container, bg=color_primario)
        subtitle_frame.pack()
        
        tk.Label(subtitle_frame, text="Conjunto Residencial 'Los Alamos'", 
                font=('Arial', 11), bg=color_primario, fg='#bdc3c7').pack(side='left', padx=5)
        
        tk.Label(subtitle_frame, text="|", font=('Arial', 11), 
                bg=color_primario, fg='#bdc3c7').pack(side='left', padx=5)
        
        tk.Label(subtitle_frame, text=f"Modo: ", font=('Arial', 11, 'bold'), 
                bg=color_primario, fg='white').pack(side='left')
        
        tk.Label(subtitle_frame, text=db_status, font=('Arial', 11, 'bold'), 
                bg=db_color, fg='white', padx=8, pady=2).pack(side='left')
        
        # ========== FRAME DE BÚSQUEDA Y ACCIONES ==========
        self.crear_frame_busqueda_mejorado(color_primario, color_acento, color_exito, 
                                           color_advertencia, color_peligro, color_fondo)
        
        # ========== CONTENEDOR PRINCIPAL ==========
        main_container = tk.Frame(self.ventana, bg=color_fondo)
        main_container.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Panel de resultados (ocupa la mayor parte) - CON COLORES MEJORADOS
        self.crear_panel_resultados(main_container)
        
        # ========== FOOTER CON ESTADÍSTICAS (PARTE INFERIOR) ==========
        self.crear_footer_estadisticas(color_primario, color_exito, color_peligro, 
                                       color_advertencia, color_acento)
        
        # Actualizar estadísticas cada 2 segundos
        self.actualizar_estadisticas()
    
    def crear_frame_busqueda_mejorado(self, color_primario, color_acento, color_exito, 
                                      color_advertencia, color_peligro, color_fondo):
        """Crea el frame de búsqueda mejorado con botones de acción"""
        
        # Frame principal de búsqueda
        busqueda_frame = tk.Frame(self.ventana, bg='white', relief='solid', bd=1)
        busqueda_frame.pack(fill='x', padx=20, pady=(10, 0))
        
        # Contenedor con padding
        contenedor = tk.Frame(busqueda_frame, bg='white')
        contenedor.pack(fill='both', expand=True, padx=20, pady=15)
        
        # Título de la sección
        tk.Label(contenedor, text="🔍 BÚSQUEDA DE VEHÍCULOS", 
                font=('Arial', 12, 'bold'), bg='white', fg=color_primario).pack(anchor='w', pady=(0, 10))
        
        # Fila de entrada de placa
        entrada_frame = tk.Frame(contenedor, bg='white')
        entrada_frame.pack(fill='x', pady=5)
        
        tk.Label(entrada_frame, text="PLACA:", font=('Arial', 10, 'bold'), 
                bg='white', fg=color_primario).pack(side='left', padx=(0, 10))
        
        self.entry_placa = tk.Entry(entrada_frame, font=('Arial', 12, 'bold'), 
                                   width=15, relief='solid', bd=2, bg='#f8f9fa', fg=color_primario)
        self.entry_placa.pack(side='left', padx=5)
        self.entry_placa.bind('<Return>', lambda e: self.buscar_placa_entrada())
        
        btn_buscar = tk.Button(entrada_frame, text="🔍 Buscar", 
                              command=self.buscar_placa_entrada,
                              bg=color_acento, fg='white', font=('Arial', 9, 'bold'),
                              relief='flat', bd=0, padx=15, pady=5,
                              activebackground='#2980b9', cursor='hand2')
        btn_buscar.pack(side='left', padx=5)
        
        btn_limpiar = tk.Button(entrada_frame, text="🗑️ Limpiar", 
                               command=lambda: self.entry_placa.delete(0, tk.END),
                               bg=color_peligro, fg='white', font=('Arial', 9, 'bold'),
                               relief='flat', bd=0, padx=15, pady=5,
                               activebackground='#c0392b', cursor='hand2')
        btn_limpiar.pack(side='left', padx=5)
        
        # Separador
        ttk.Separator(contenedor, orient='horizontal').pack(fill='x', pady=10)
        
        # Panel de botones de acción (DESTACADO)
        acciones_frame = tk.Frame(contenedor, bg='white')
        acciones_frame.pack(fill='x', pady=5)
        
        tk.Label(acciones_frame, text="ACCIONES:", font=('Arial', 10, 'bold'), 
                bg='white', fg=color_primario).pack(side='left', padx=(0, 15))
        
        # Botones con iconos y colores
        btn_residente_entrada = tk.Button(acciones_frame, text="👤 ENTRADA RESIDENTE", 
                                         command=self.registrar_entrada_residente,
                                         bg=color_acento, fg='white', font=('Arial', 9, 'bold'),
                                         relief='flat', bd=0, padx=12, pady=5,
                                         activebackground='#2980b9', cursor='hand2')
        btn_residente_entrada.pack(side='left', padx=2)
        
        btn_residente_salida = tk.Button(acciones_frame, text="👤 SALIDA RESIDENTE", 
                                        command=self.registrar_salida_residente,
                                        bg='#7f8c8d', fg='white', font=('Arial', 9, 'bold'),
                                        relief='flat', bd=0, padx=12, pady=5,
                                        activebackground='#6c7a7d', cursor='hand2')
        btn_residente_salida.pack(side='left', padx=2)
        
        btn_visitante_entrada = tk.Button(acciones_frame, text="👥 ENTRADA VISITANTE", 
                                         command=self.registrar_entrada_visitante,
                                         bg=color_exito, fg='white', font=('Arial', 9, 'bold'),
                                         relief='flat', bd=0, padx=12, pady=5,
                                         activebackground='#229954', cursor='hand2')
        btn_visitante_entrada.pack(side='left', padx=2)
        
        btn_visitante_liquidar = tk.Button(acciones_frame, text="💰 LIQUIDAR VISITANTE", 
                                          command=self.abrir_ventana_liquidar,
                                          bg=color_advertencia, fg='white', font=('Arial', 9, 'bold'),
                                          relief='flat', bd=0, padx=12, pady=5,
                                          activebackground='#e67e22', cursor='hand2')
        btn_visitante_liquidar.pack(side='left', padx=2)
        
        btn_ver_parqueaderos = tk.Button(acciones_frame, text="📊 VER PARQUEADEROS", 
                                        command=self.mostrar_estado_parqueaderos,
                                        bg='#9b59b6', fg='white', font=('Arial', 9, 'bold'),
                                        relief='flat', bd=0, padx=12, pady=5,
                                        activebackground='#8e44ad', cursor='hand2')
        btn_ver_parqueaderos.pack(side='left', padx=2)
    
    def crear_panel_resultados(self, parent):
        """Crea el panel de resultados con mejor contraste y formato"""
        
        # Frame para resultados
        resultados_frame = tk.Frame(parent, bg='white', relief='solid', bd=2)
        resultados_frame.pack(fill='both', expand=True)
        
        # Título del panel con mejor contraste
        titulo_frame = tk.Frame(resultados_frame, bg='#2c3e50', height=40)
        titulo_frame.pack(fill='x')
        titulo_frame.pack_propagate(False)
        
        tk.Label(titulo_frame, text="📋 RESULTADO DE BÚSQUEDA", 
                font=('Arial', 12, 'bold'), bg='#2c3e50', fg='white',
                pady=10).pack(expand=True)
        
        # Panel de resultado con mejor contraste
        self.panel_resultado_placa = tk.Frame(
            resultados_frame, 
            bg='#ffffff',  # Blanco puro para mejor contraste
            relief='sunken', 
            bd=2
        )
        self.panel_resultado_placa.pack(fill='both', expand=True, padx=15, pady=15)
        
        self.label_resultado_placa = tk.Label(
            self.panel_resultado_placa, 
            text="📝 Ingrese una placa y presione 'Buscar'", 
            font=('Arial', 14), 
            bg='#ffffff', 
            fg='#34495e',  # Azul grisáceo oscuro para mejor contraste
            justify='center',
            wraplength=500
        )
        self.label_resultado_placa.pack(expand=True, padx=20, pady=20)
    
    def crear_footer_estadisticas(self, color_primario, color_exito, color_peligro, 
                                  color_advertencia, color_acento):
        """Crea el footer con estadísticas en la parte inferior"""
        
        footer_frame = tk.Frame(self.ventana, bg=color_primario, relief='raised', bd=2, height=120)
        footer_frame.pack(fill='x', side='bottom')
        footer_frame.pack_propagate(False)
        
        # Barra decorativa superior
        top_line = tk.Frame(footer_frame, bg=color_advertencia, height=3)
        top_line.pack(fill='x')
        
        # Título del footer
        titulo_footer = tk.Label(footer_frame,
                                text="📊 ESTADÍSTICAS EN TIEMPO REAL",
                                font=('Arial', 11, 'bold'),
                                bg=color_primario,
                                fg='white')
        titulo_footer.pack(pady=5)
        
        # Contenedor de estadísticas
        stats_container = tk.Frame(footer_frame, bg=color_primario)
        stats_container.pack(fill='both', expand=True, padx=20, pady=5)
        
        self.footer_labels = {}
        
        # Estadísticas en fila
        stats_data = [
            ('total_parq', '🅿️ TOTAL', '#3498db'),
            ('disponibles', '🟢 LIBRES', color_exito),
            ('ocupados', '🔴 OCUPADOS', color_peligro),
            ('visitantes', '👥 VISITANTES', '#9b59b6'),
            ('recaudo', '💰 RECAUDO HOY', color_advertencia)
        ]
        
        for i, (key, text, color) in enumerate(stats_data):
            # Card de estadística
            card = tk.Frame(stats_container, bg=color, relief='ridge', bd=2)
            card.pack(side='left', fill='both', expand=True, padx=5, pady=3)
            
            # Título
            tk.Label(card, text=text, font=('Arial', 9, 'bold'), 
                    bg=color, fg='white', pady=2).pack(fill='x')
            
            # Valor
            self.footer_labels[key] = tk.Label(card, text="0", 
                                              font=('Arial', 14, 'bold'), 
                                              bg=color, fg='white', pady=5)
            self.footer_labels[key].pack(fill='x')
        
        # Copyright
        copyright_label = tk.Label(footer_frame,
                                  text="© 2024 Sistema Control Vehicular | Versión 2.0 PostgreSQL",
                                  font=('Arial', 8),
                                  bg=color_primario,
                                  fg='#95a5a6')
        copyright_label.pack(pady=2)
    
    def buscar_placa_entrada(self):
        """Busca una placa en el sistema y muestra el resultado con colores MEJORADOS"""
        placa = self.entry_placa.get().upper().strip()
        
        if not placa:
            self.label_resultado_placa.config(
                text="⚠️ POR FAVOR INGRESE UNA PLACA", 
                fg='#c0392b',  # Rojo más oscuro para mejor contraste
                font=('Arial', 14, 'bold')
            )
            self.panel_resultado_placa.config(bg='#fdedec')  # Rojo muy claro
            return
        
        try:
            if self.usar_datos_memoria:
                # Buscar en datos de memoria
                if placa in self.datos_memoria['residentes']:
                    residente = self.datos_memoria['residentes'][placa]
                    estado_visual = "🟢 LIBRE" if residente['estado'].lower() == 'libre' else "🔴 OCUPADO"
                    texto = (f"👨‍💼 RESIDENTE IDENTIFICADO\n\n"
                            f"┌─────────────────────────┐\n"
                            f"│ Nombre: {residente['nombre']:<20} │\n"
                            f"│ Apartamento: {residente['apartamento']:<14} │\n"
                            f"│ Parqueadero: {residente['parqueadero']:<14} │\n"
                            f"│ Estado: {estado_visual:<18} │\n"
                            f"└─────────────────────────┘")
                    self.label_resultado_placa.config(
                        text=texto, 
                        fg='#1e3c2c',  # Verde oscuro para mejor contraste
                        font=('Courier', 12, 'bold'),  # Fuente monoespaciada para mejor formato
                        justify='left'
                    )
                    self.panel_resultado_placa.config(bg='#d4edda')  # Verde muy claro
                else:
                    # Verificar si es visitante activo
                    if placa in self.datos_memoria['visitantes_activos']:
                        datos = self.datos_memoria['visitantes_activos'][placa]
                        tiempo = datetime.now() - datos['hora_entrada']
                        horas = tiempo.total_seconds() / 3600
                        texto = (f"👥 VISITANTE ACTIVO\n\n"
                                f"┌─────────────────────────┐\n"
                                f"│ Placa: {placa:<21} │\n"
                                f"│ Parqueadero: {datos['parqueadero']:<15} │\n"
                                f"│ Tiempo: {horas:.1f} horas{' ':<9} │\n"
                                f"└─────────────────────────┘")
                    else:
                        texto = (f"👥 VISITANTE NO REGISTRADO\n\n"
                                f"┌─────────────────────────┐\n"
                                f"│ Placa: {placa:<21} │\n"
                                f"│ Acción: Use 'ENTRADA'    │\n"
                                f"└─────────────────────────┘")
                    
                    self.label_resultado_placa.config(
                        text=texto, 
                        fg='#7b4a1e',  # Marrón oscuro para mejor contraste
                        font=('Courier', 12, 'bold'),
                        justify='left'
                    )
                    self.panel_resultado_placa.config(bg='#fff3cd')  # Amarillo claro
            else:
                # Buscar en PostgreSQL
                if self.db and self.db.conectado:
                    residente = self.db.verificar_placa_residente(placa)
                    
                    if residente:
                        estado_color_texto = '#1e3c2c' if residente['estado'] == 'LIBRE' else '#7a1f1f'
                        texto = (f"👨‍💼 RESIDENTE IDENTIFICADO\n\n"
                                f"┌─────────────────────────┐\n"
                                f"│ Nombre: {residente['nombre']:<20} │\n"
                                f"│ Apartamento: {residente['apartamento']:<14} │\n"
                                f"│ Parqueadero: {residente['parqueadero']:<14} │\n"
                                f"│ Estado: {residente['estado']:<20} │\n"
                                f"└─────────────────────────┘")
                        self.label_resultado_placa.config(
                            text=texto, 
                            fg=estado_color_texto,
                            font=('Courier', 12, 'bold'),
                            justify='left'
                        )
                        self.panel_resultado_placa.config(
                            bg='#d4edda' if residente['estado'] == 'LIBRE' else '#f8d7da'
                        )
                    else:
                        # Verificar si es visitante activo
                        visitante = self.db.obtener_visitante_activo_por_placa(placa)
                        if visitante:
                            hora_entrada = visitante['hora_entrada']
                            if hasattr(hora_entrada, 'strftime'):
                                hora_str = hora_entrada.strftime('%H:%M:%S')
                            else:
                                hora_str = str(hora_entrada)
                            
                            texto = (f"👥 VISITANTE ACTIVO\n\n"
                                    f"┌─────────────────────────┐\n"
                                    f"│ Placa: {placa:<21} │\n"
                                    f"│ Parqueadero: {visitante['parqueadero']:<15} │\n"
                                    f"│ Entrada: {hora_str:<19} │\n"
                                    f"└─────────────────────────┘")
                        else:
                            texto = (f"👥 VISITANTE NO REGISTRADO\n\n"
                                    f"┌─────────────────────────┐\n"
                                    f"│ Placa: {placa:<21} │\n"
                                    f"│ Acción: Use 'ENTRADA'    │\n"
                                    f"└─────────────────────────┘")
                        
                        self.label_resultado_placa.config(
                            text=texto, 
                            fg='#7b4a1e',
                            font=('Courier', 12, 'bold'),
                            justify='left'
                        )
                        self.panel_resultado_placa.config(bg='#fff3cd')
                else:
                    self.label_resultado_placa.config(
                        text="❌ ERROR DE CONEXIÓN\n\nNo hay conexión a la base de datos", 
                        fg='#7a1f1f',
                        font=('Arial', 14, 'bold'),
                        justify='center'
                    )
                    self.panel_resultado_placa.config(bg='#f8d7da')
        except Exception as e:
            self.label_resultado_placa.config(
                text=f"❌ ERROR\n\n{str(e)}", 
                fg='#7a1f1f',
                font=('Arial', 12, 'bold'),
                justify='center'
            )
            self.panel_resultado_placa.config(bg='#f8d7da')
    
    def registrar_entrada_residente(self):
        """Registra la entrada de un residente (sin pago)"""
        placa = self.entry_placa.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        try:
            if self.usar_datos_memoria:
                # Modo memoria
                if placa not in self.datos_memoria['residentes']:
                    messagebox.showerror("Error", f"❌ La placa {placa} no corresponde a un residente registrado")
                    return
                
                residente = self.datos_memoria['residentes'][placa]
                if residente['estado'].lower() == 'ocupado':
                    messagebox.showwarning("Advertencia", f"❌ El residente {residente['nombre']} ya tiene su parqueadero ocupado.")
                    return
                
                residente['estado'] = 'ocupado'
                messagebox.showinfo("Éxito", f"✅ ENTRADA RESIDENTE registrada:\n{residente['nombre']}\nParqueadero: {residente['parqueadero']}")
                
            else:
                # Modo PostgreSQL
                if not (self.db and self.db.conectado):
                    messagebox.showerror("Error", "Sin conexión a la base de datos")
                    return
                
                residente = self.db.verificar_placa_residente(placa)
                if not residente:
                    messagebox.showerror("Error", f"❌ La placa {placa} no corresponde a un residente registrado")
                    return
                
                if residente['estado'] == 'OCUPADO':
                    messagebox.showwarning("Advertencia", f"❌ El residente ya tiene su parqueadero ocupado.")
                    return
                
                if self.db.marcar_parqueadero_ocupado(residente['parqueadero']):
                    messagebox.showinfo("Éxito", f"✅ ENTRADA RESIDENTE registrada:\n{residente['nombre']}\nParqueadero: {residente['parqueadero']}")
                else:
                    messagebox.showerror("Error", "❌ Error actualizando estado del parqueadero")
                    return
            
            # Limpiar y actualizar
            self.entry_placa.delete(0, tk.END)
            self.label_resultado_placa.config(text="📝 Ingrese una placa y presione 'Buscar'", fg='#34495e', bg='#ffffff', font=('Arial', 14))
            self.panel_resultado_placa.config(bg='#ffffff')
            self.actualizar_estadisticas()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al registrar entrada: {str(e)}")
    
    def registrar_entrada_visitante(self):
        """Registra la entrada de un visitante (asigna parqueadero)"""
        placa = self.entry_placa.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        try:
            if self.usar_datos_memoria:
                # Modo memoria
                if placa in self.datos_memoria['residentes']:
                    messagebox.showwarning("Advertencia", "❌ Esta placa pertenece a un residente. Use 'ENTRADA RESIDENTE'")
                    return
                
                if placa in self.datos_memoria['visitantes_activos']:
                    messagebox.showwarning("Advertencia", f"❌ El visitante con placa {placa} ya se encuentra dentro.")
                    return
                
                if not self.datos_memoria['parqueaderos_visitantes']:
                    messagebox.showwarning("Advertencia", "❌ No hay parqueaderos disponibles para visitantes")
                    return
                
                hora_entrada = datetime.now()
                parqueadero = self.datos_memoria['parqueaderos_visitantes'][0]
                self.datos_memoria['visitantes_activos'][placa] = {
                    'hora_entrada': hora_entrada,
                    'parqueadero': parqueadero
                }
                self.datos_memoria['parqueaderos_visitantes'].remove(parqueadero)
                
                messagebox.showinfo("Éxito", f"✅ ENTRADA VISITANTE registrada:\nPlaca: {placa}\nParqueadero: {parqueadero}")
                
            else:
                # Modo PostgreSQL
                if not (self.db and self.db.conectado):
                    messagebox.showerror("Error", "Sin conexión a la base de datos")
                    return
                
                # Verificar si es residente
                residente = self.db.verificar_placa_residente(placa)
                if residente:
                    messagebox.showwarning("Advertencia", "❌ Esta placa pertenece a un residente. Use 'ENTRADA RESIDENTE'")
                    return
                
                # Verificar si ya está activo
                visitante_activo = self.db.obtener_visitante_activo_por_placa(placa)
                if visitante_activo:
                    messagebox.showwarning("Advertencia", f"❌ El visitante con placa {placa} ya se encuentra dentro.")
                    return
                
                # Obtener parqueadero libre
                parq_libres = self.db.obtener_parqueaderos_libres_visitantes()
                if not parq_libres:
                    messagebox.showwarning("Advertencia", "❌ No hay parqueaderos disponibles para visitantes")
                    return
                
                registro_id = self.db.registrar_entrada_visitante(placa, parq_libres[0]['id'])
                if registro_id:
                    messagebox.showinfo("Éxito", f"✅ ENTRADA VISITANTE registrada:\nPlaca: {placa}\nParqueadero: {parq_libres[0]['numero']}")
                else:
                    messagebox.showerror("Error", "❌ Error registrando entrada")
                    return
            
            # Limpiar y actualizar
            self.entry_placa.delete(0, tk.END)
            self.label_resultado_placa.config(text="📝 Ingrese una placa y presione 'Buscar'", fg='#34495e', bg='#ffffff', font=('Arial', 14))
            self.panel_resultado_placa.config(bg='#ffffff')
            self.actualizar_estadisticas()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al registrar entrada: {str(e)}")
    
    def registrar_salida_residente(self):
        """Registra la salida de un residente (sin pago)"""
        placa = self.entry_placa.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        try:
            if self.usar_datos_memoria:
                # Modo memoria
                if placa not in self.datos_memoria['residentes']:
                    messagebox.showerror("Error", f"❌ La placa {placa} no corresponde a un residente registrado")
                    return
                
                residente = self.datos_memoria['residentes'][placa]
                if residente['estado'].lower() == 'libre':
                    messagebox.showwarning("Advertencia", f"❌ El residente {residente['nombre']} no tiene su parqueadero ocupado.")
                    return
                
                residente['estado'] = 'libre'
                messagebox.showinfo("Éxito", f"✅ SALIDA RESIDENTE registrada:\n{residente['nombre']}\nParqueadero liberado")
                
            else:
                # Modo PostgreSQL
                if not (self.db and self.db.conectado):
                    messagebox.showerror("Error", "Sin conexión a la base de datos")
                    return
                
                residente = self.db.verificar_placa_residente(placa)
                if not residente:
                    messagebox.showerror("Error", f"❌ La placa {placa} no corresponde a un residente registrado")
                    return
                
                if residente['estado'] == 'LIBRE':
                    messagebox.showwarning("Advertencia", f"❌ El residente no tiene su parqueadero ocupado.")
                    return
                
                if self.db.marcar_parqueadero_libre(residente['parqueadero']):
                    messagebox.showinfo("Éxito", f"✅ SALIDA RESIDENTE registrada:\n{residente['nombre']}\nParqueadero liberado")
                else:
                    messagebox.showerror("Error", "❌ Error actualizando estado del parqueadero")
                    return
            
            # Limpiar y actualizar
            self.entry_placa.delete(0, tk.END)
            self.label_resultado_placa.config(text="📝 Ingrese una placa y presione 'Buscar'", fg='#34495e', bg='#ffffff', font=('Arial', 14))
            self.panel_resultado_placa.config(bg='#ffffff')
            self.actualizar_estadisticas()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al registrar salida: {str(e)}")
    
    def abrir_ventana_liquidar(self):
        """Abre ventana para liquidar pago de visitante (SALIDA CON PAGO) - CORREGIDA"""
        placa_inicial = self.entry_placa.get().upper().strip()
        
        ventana_liq = tk.Toplevel(self.ventana)
        ventana_liq.title("💰 Liquidar Pago de Visitante")
        ventana_liq.geometry("600x550")
        ventana_liq.resizable(False, False)
        ventana_liq.configure(bg='#f5f5f5')
        
        ventana_liq.transient(self.ventana)
        ventana_liq.grab_set()
        
        # Encabezado con gradiente
        header = tk.Frame(ventana_liq, bg='#16a085', height=70)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(header, text="💰 LIQUIDAR PAGO DE VISITANTE", 
                font=('Arial', 16, 'bold'), bg='#16a085', fg='white').pack(pady=20)
        
        # Frame principal
        main_frame = tk.Frame(ventana_liq, bg='#f5f5f5')
        main_frame.pack(fill='both', expand=True, padx=25, pady=20)
        
        # Campo placa
        tk.Label(main_frame, text="Placa del Visitante:", font=('Arial', 11, 'bold'),
                bg='#f5f5f5', fg='#2c3e50').pack(anchor='w', pady=(0, 5))
        
        entry_frame = tk.Frame(main_frame, bg='#f5f5f5')
        entry_frame.pack(fill='x', pady=(0, 15))
        
        entry_placa_liq = tk.Entry(entry_frame, font=('Arial', 14, 'bold'), 
                                   width=15, relief='solid', bd=2, bg='white',
                                   fg='#2c3e50', justify='center')
        entry_placa_liq.pack(side='left')
        
        if placa_inicial:
            entry_placa_liq.insert(0, placa_inicial)
        entry_placa_liq.focus()
        
        # Frame de información calculada
        info_frame = tk.Frame(main_frame, bg='white', relief='solid', bd=2)
        info_frame.pack(fill='x', pady=(0, 20))
        
        # Título del info frame
        tk.Label(info_frame, text="📊 CÁLCULO DE TARIFA", font=('Arial', 11, 'bold'),
                bg='#f39c12', fg='white', padx=15, pady=8).pack(fill='x')
        
        # Contenido del info frame
        content_frame = tk.Frame(info_frame, bg='white', padx=20, pady=15)
        content_frame.pack(fill='x')
        
        # Labels para mostrar la información
        label_calculo_tiempo = tk.Label(content_frame, text="⏱️ Tiempo: --",
                                        font=('Arial', 11), bg='white', fg='#2c3e50',
                                        anchor='w')
        label_calculo_tiempo.pack(fill='x', pady=3)
        
        label_calculo_tarifa = tk.Label(content_frame, text="💵 Valor a pagar: --",
                                        font=('Arial', 14, 'bold'), bg='white', fg='#27ae60',
                                        anchor='w')
        label_calculo_tarifa.pack(fill='x', pady=3)
        
        label_calculo_tipo = tk.Label(content_frame, text="📌 Tipo de tarifa: --",
                                      font=('Arial', 11), bg='white', fg='#2c3e50',
                                      anchor='w')
        label_calculo_tipo.pack(fill='x', pady=3)
        
        label_hora_entrada = tk.Label(content_frame, text="🕐 Hora entrada: --",
                                      font=('Arial', 10), bg='white', fg='#7f8c8d',
                                      anchor='w')
        label_hora_entrada.pack(fill='x', pady=3)
        
        # Variable para guardar datos del visitante
        datos_visitante = {'id': None, 'parqueadero_id': None, 'placa': '', 'parqueadero': None}
        tarifa_calculada = {'valor': 0}
        
        def calcular_tarifa():
            """Calcula la tarifa según tiempo estacionado"""
            placa = entry_placa_liq.get().upper().strip()
            
            if not placa:
                label_calculo_tiempo.config(text="⏱️ Tiempo: --")
                label_calculo_tarifa.config(text="💵 Valor a pagar: --")
                label_calculo_tipo.config(text="📌 Tipo de tarifa: --")
                label_hora_entrada.config(text="🕐 Hora entrada: --")
                datos_visitante['id'] = None
                datos_visitante['parqueadero_id'] = None
                datos_visitante['parqueadero'] = None
                return
            
            if self.usar_datos_memoria:
                if placa in self.datos_memoria['visitantes_activos']:
                    hora_salida = datetime.now()
                    hora_entrada = self.datos_memoria['visitantes_activos'][placa]['hora_entrada']
                    parqueadero = self.datos_memoria['visitantes_activos'][placa]['parqueadero']
                    
                    datos_visitante['placa'] = placa
                    datos_visitante['parqueadero'] = parqueadero
                    datos_visitante['id'] = placa  # Usamos la placa como ID en modo memoria
                    
                    tiempo = hora_salida - hora_entrada
                    horas = tiempo.total_seconds() / 3600
                    
                    # Mostrar hora de entrada
                    label_hora_entrada.config(text=f"🕐 Hora entrada: {hora_entrada.strftime('%H:%M:%S')}")
                    
                    if horas <= 5:
                        cobro = int(np.ceil(horas)) * 1000
                        tipo = "Tarifa por hora ($1,000/hora)"
                    else:
                        cobro = 10000
                        tipo = "Tarifa plena ($10,000)"
                    
                    tarifa_calculada['valor'] = cobro
                    
                    label_calculo_tiempo.config(text=f"⏱️ Tiempo estacionado: {horas:.2f} horas")
                    label_calculo_tarifa.config(text=f"💵 VALOR A PAGAR: ${cobro:,} COP")
                    label_calculo_tipo.config(text=f"📌 {tipo}")
                else:
                    label_calculo_tiempo.config(text="⏱️ Tiempo: --")
                    label_calculo_tarifa.config(text="💵 VALOR A PAGAR: $0 COP")
                    label_calculo_tipo.config(text="📌 ❌ Placa no encontrada o no es visitante activo")
                    label_hora_entrada.config(text="🕐 Hora entrada: --")
                    tarifa_calculada['valor'] = 0
                    datos_visitante['id'] = None
                    datos_visitante['parqueadero'] = None
            else:
                if self.db and self.db.conectado:
                    visitante = self.db.obtener_visitante_activo_por_placa(placa)
                    if visitante:
                        hora_entrada = visitante['hora_entrada']
                        
                        if isinstance(hora_entrada, str):
                            try:
                                hora_entrada = datetime.fromisoformat(hora_entrada.replace('Z', '+00:00'))
                            except:
                                hora_entrada = datetime.strptime(hora_entrada, '%Y-%m-%d %H:%M:%S')
                        
                        if hasattr(hora_entrada, 'tzinfo') and hora_entrada.tzinfo is not None:
                            hora_entrada = hora_entrada.replace(tzinfo=None)
                        
                        datos_visitante['id'] = visitante['id']
                        datos_visitante['parqueadero_id'] = visitante['parqueadero_id']
                        datos_visitante['placa'] = placa
                        
                        # Mostrar hora de entrada
                        if hasattr(hora_entrada, 'strftime'):
                            label_hora_entrada.config(text=f"🕐 Hora entrada: {hora_entrada.strftime('%H:%M:%S')}")
                        else:
                            label_hora_entrada.config(text=f"🕐 Hora entrada: {str(hora_entrada)}")
                        
                        hora_salida = datetime.now()
                        tiempo = hora_salida - hora_entrada
                        horas = tiempo.total_seconds() / 3600
                        
                        if horas <= 5:
                            cobro = int(np.ceil(horas)) * 1000
                            tipo = "Tarifa por hora ($1,000/hora)"
                        else:
                            cobro = 10000
                            tipo = "Tarifa plena ($10,000)"
                        
                        tarifa_calculada['valor'] = cobro
                        
                        label_calculo_tiempo.config(text=f"⏱️ Tiempo estacionado: {horas:.2f} horas")
                        label_calculo_tarifa.config(text=f"💵 VALOR A PAGAR: ${cobro:,} COP")
                        label_calculo_tipo.config(text=f"📌 {tipo}")
                    else:
                        label_calculo_tiempo.config(text="⏱️ Tiempo: --")
                        label_calculo_tarifa.config(text="💵 VALOR A PAGAR: $0 COP")
                        label_calculo_tipo.config(text="📌 ❌ Placa no encontrada o no es visitante activo")
                        label_hora_entrada.config(text="🕐 Hora entrada: --")
                        tarifa_calculada['valor'] = 0
                        datos_visitante['id'] = None
                        datos_visitante['parqueadero_id'] = None
        
        # Bind para calcular cuando se ingresa placa
        entry_placa_liq.bind('<KeyRelease>', lambda e: calcular_tarifa())
        
        # Si ya había una placa, calcular automáticamente
        if placa_inicial:
            ventana_liq.after(100, calcular_tarifa)
        
        # Frame de botones
        btn_frame = tk.Frame(main_frame, bg='#f5f5f5')
        btn_frame.pack(fill='x', pady=20)
        
        def liquidar_confirmar():
            placa = entry_placa_liq.get().upper().strip()
            tarifa = tarifa_calculada['valor']
            
            if not placa:
                messagebox.showwarning("Advertencia", "❌ Ingrese una placa")
                return
            
            if tarifa == 0 or datos_visitante['id'] is None:
                messagebox.showerror("Error", "❌ Placa no válida o no es un visitante activo")
                return
            
            # Confirmar el cobro
            if not messagebox.askyesno("Confirmar Pago", f"¿Cobrar ${tarifa:,} COP al visitante {placa}?"):
                return
            
            if self.usar_datos_memoria:
                if placa in self.datos_memoria['visitantes_activos']:
                    hora_salida = datetime.now()
                    hora_entrada = self.datos_memoria['visitantes_activos'][placa]['hora_entrada']
                    parqueadero = self.datos_memoria['visitantes_activos'][placa]['parqueadero']
                    
                    tiempo = hora_salida - hora_entrada
                    horas = tiempo.total_seconds() / 3600
                    
                    # Registrar en historial
                    self.datos_memoria['historial_visitantes'].append({
                        'placa': placa,
                        'hora_entrada': hora_entrada,
                        'hora_salida': hora_salida,
                        'horas': round(horas, 2),
                        'cobro': tarifa,
                        'tipo': 'Liquidado'
                    })
                    
                    # Devolver parqueadero
                    self.datos_memoria['parqueaderos_visitantes'].append(parqueadero)
                    del self.datos_memoria['visitantes_activos'][placa]
                    
                    messagebox.showinfo("✅ Cobro Exitoso", 
                                      f"Placa: {placa}\nCobro: ${tarifa:,} COP\n✅ Salida registrada")
                    ventana_liq.destroy()
                else:
                    messagebox.showerror("Error", f"❌ Visitante {placa} ya no está activo")
                    return
            else:
                if self.db and self.db.conectado:
                    # Verificar que tenemos los datos necesarios
                    if datos_visitante['id'] is None or datos_visitante['parqueadero_id'] is None:
                        messagebox.showerror("Error", "❌ Datos del visitante incompletos")
                        return
                    
                    resultado = self.db.registrar_salida_visitante(
                        datos_visitante['id'], 
                        datos_visitante['parqueadero_id']
                    )
                    
                    if resultado:
                        messagebox.showinfo("✅ Cobro Exitoso", 
                                          f"Placa: {placa}\n"
                                          f"Tiempo: {resultado['total_horas']:.2f} horas\n"
                                          f"Cobro: ${resultado['valor_pagado']:,.0f} COP\n"
                                          f"✅ Salida registrada")
                        ventana_liq.destroy()
                    else:
                        messagebox.showerror("Error", "❌ Error registrando salida")
                        return
                else:
                    messagebox.showerror("Error", "❌ Sin conexión a la base de datos")
                    return
            
            # Actualizar vistas después de cerrar
            self.actualizar_estadisticas()
            self.entry_placa.delete(0, tk.END)
            self.label_resultado_placa.config(text="📝 Ingrese una placa y presione 'Buscar'", fg='#34495e', bg='#ffffff', font=('Arial', 14))
            self.panel_resultado_placa.config(bg='#ffffff')
        
        btn_liquidar = tk.Button(btn_frame, text="✅ CONFIRMAR PAGO Y SALIDA", 
                                 command=liquidar_confirmar,
                                 bg='#16a085', fg='white', font=('Arial', 11, 'bold'),
                                 relief='flat', bd=0, padx=20, pady=12,
                                 activebackground='#138d75', cursor='hand2')
        btn_liquidar.pack(fill='x', pady=(0, 10))
        
        btn_cancelar = tk.Button(btn_frame, text="❌ Cancelar", 
                                 command=ventana_liq.destroy,
                                 bg='#e74c3c', fg='white', font=('Arial', 10),
                                 relief='flat', bd=0, padx=20, pady=10,
                                 activebackground='#c0392b', cursor='hand2')
        btn_cancelar.pack(fill='x')
    
    def mostrar_estado_parqueaderos(self):
        """Muestra ventana con estado de todos los parqueaderos"""
        ventana_estado = tk.Toplevel(self.ventana)
        ventana_estado.title("📊 Estado de Parqueaderos")
        ventana_estado.geometry("700x600")
        ventana_estado.resizable(True, True)
        ventana_estado.configure(bg='#f5f5f5')
        
        ventana_estado.transient(self.ventana)
        ventana_estado.grab_set()
        
        header = tk.Frame(ventana_estado, bg='#9b59b6', height=60)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text="📊 ESTADO DE TODOS LOS PARQUEADEROS", 
                font=('Arial', 16, 'bold'), bg='#9b59b6', fg='white').pack(pady=15)
        
        canvas_frame = tk.Frame(ventana_estado, bg='#f5f5f5')
        canvas_frame.pack(fill='both', expand=True, padx=20, pady=15)
        
        canvas = tk.Canvas(canvas_frame, bg='white', relief='solid', bd=1)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='white')
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        if self.usar_datos_memoria:
            total_parq_res = len(self.datos_memoria['residentes'])
            total_parq_vis = self.datos_memoria.get('total_parqueaderos_visitantes', 5)
            
            # Mostrar residentes
            lbl_res_header = tk.Label(scrollable_frame, text="👨‍💼 PARQUEADEROS RESIDENTES", 
                                     font=('Arial', 12, 'bold'), bg='#3498db', fg='white',
                                     padx=15, pady=10)
            lbl_res_header.pack(fill='x', pady=(0, 10))
            
            for placa, datos in self.datos_memoria['residentes'].items():
                estado_color = '#27ae60' if datos['estado'].lower() == 'libre' else '#e74c3c'
                estado_texto = "🟢 LIBRE" if datos['estado'].lower() == 'libre' else "🔴 OCUPADO"
                
                card = tk.Frame(scrollable_frame, bg=estado_color, relief='solid', bd=2)
                card.pack(fill='x', pady=5, padx=10)
                
                info_text = (f"Parqueadero #{datos['parqueadero']} | {estado_texto} | "
                            f"Residente: {datos['nombre']} (Apto {datos['apartamento']}) | Placa: {placa}")
                
                lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                              bg=estado_color, fg='white', anchor='w', padx=15, pady=10)
                lbl.pack(fill='x')
            
            # Mostrar visitantes
            lbl_vis_header = tk.Label(scrollable_frame, text="👥 PARQUEADEROS VISITANTES", 
                                     font=('Arial', 12, 'bold'), bg='#9b59b6', fg='white',
                                     padx=15, pady=10)
            lbl_vis_header.pack(fill='x', pady=(15, 10))
            
            for placa, datos in self.datos_memoria['visitantes_activos'].items():
                tiempo = datetime.now() - datos['hora_entrada']
                horas = tiempo.total_seconds() / 3600
                
                card = tk.Frame(scrollable_frame, bg='#f39c12', relief='solid', bd=2)
                card.pack(fill='x', pady=5, padx=10)
                
                info_text = (f"Parqueadero #{datos['parqueadero']} | 🔴 OCUPADO | "
                            f"Placa: {placa} | Tiempo: {horas:.1f}h")
                
                lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                              bg='#f39c12', fg='white', anchor='w', padx=15, pady=10)
                lbl.pack(fill='x')
            
            for parq_num in self.datos_memoria['parqueaderos_visitantes']:
                card = tk.Frame(scrollable_frame, bg='#27ae60', relief='solid', bd=2)
                card.pack(fill='x', pady=5, padx=10)
                
                info_text = f"Parqueadero #{parq_num} | 🟢 LIBRE (disponible)"
                
                lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                              bg='#27ae60', fg='white', anchor='w', padx=15, pady=10)
                lbl.pack(fill='x')
        else:
            if self.db and self.db.conectado:
                parqueaderos = self.db.obtener_estado_parqueaderos()
                
                for p in parqueaderos:
                    estado_color = '#27ae60' if p['estado'] == 'LIBRE' else '#e74c3c'
                    estado_texto = "🟢 LIBRE" if p['estado'] == 'LIBRE' else "🔴 OCUPADO"
                    
                    card = tk.Frame(scrollable_frame, bg=estado_color, relief='solid', bd=2)
                    card.pack(fill='x', pady=5, padx=10)
                    
                    residente = p['residente'] if p['residente'] else "-"
                    apartamento = p['apartamento'] if p['apartamento'] else "-"
                    placa = p['placa'] if p['placa'] else "-"
                    
                    info_text = (f"Parqueadero #{p['numero']} | {estado_texto} | "
                                f"Residente: {residente} (Apto {apartamento}) | Placa: {placa}")
                    
                    lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                                  bg=estado_color, fg='white', anchor='w', padx=15, pady=10)
                    lbl.pack(fill='x')
    
    def mostrar_configuracion(self):
        """Muestra ventana de configuración"""
        messagebox.showinfo("Configuración", "Ventana de configuración en desarrollo")
    
    def mostrar_historial(self):
        """Muestra el historial de visitantes"""
        messagebox.showinfo("Historial", "Ventana de historial en desarrollo")
    
    def mostrar_reporte_ingresos(self):
        """Muestra reporte de ingresos"""
        messagebox.showinfo("Reporte de Ingresos", "Ventana de reportes en desarrollo")
    
    def mostrar_estadisticas_detalladas(self):
        """Muestra estadísticas detalladas"""
        messagebox.showinfo("Estadísticas", "Ventana de estadísticas en desarrollo")
    
    def mostrar_manual(self):
        """Muestra el manual de usuario"""
        messagebox.showinfo("Manual de Usuario", 
                           "Manual de uso:\n\n"
                           "1. Ingrese la placa en el campo superior\n"
                           "2. Presione 'Buscar' para verificar\n"
                           "3. Use los botones de acción según corresponda\n"
                           "4. Las estadísticas se actualizan automáticamente")
    
    def mostrar_acerca_de(self):
        """Muestra información acerca de la aplicación"""
        messagebox.showinfo("Acerca de", 
                           "🚗 Sistema de Control de Acceso Vehicular\n"
                           "Versión 2.0 PostgreSQL\n\n"
                           "© 2024 Conjunto Residencial 'Los Alamos'\n"
                           "Desarrollado con Python y Tkinter")
    
    def actualizar_estadisticas(self):
        """Actualiza las estadísticas en tiempo real"""
        if self.usar_datos_memoria:
            total_residentes = len(self.datos_memoria['residentes'])
            total_parqueaderos_visitantes = self.datos_memoria.get('total_parqueaderos_visitantes', 5)
            
            ocupados_residentes = sum(1 for r in self.datos_memoria['residentes'].values() if r['estado'] == 'ocupado')
            libres_residentes = total_residentes - ocupados_residentes
            
            ocupados_visitantes = len(self.datos_memoria['visitantes_activos'])
            libres_visitantes = total_parqueaderos_visitantes - ocupados_visitantes
            
            total = total_residentes + total_parqueaderos_visitantes
            total_historial = sum(r['cobro'] for r in self.datos_memoria['historial_visitantes'])
            
            libres_totales = libres_residentes + libres_visitantes
            self.footer_labels['total_parq'].config(text=str(total))
            self.footer_labels['disponibles'].config(text=str(libres_totales))
            self.footer_labels['ocupados'].config(text=str(ocupados_residentes + ocupados_visitantes))
            self.footer_labels['visitantes'].config(text=str(total_parqueaderos_visitantes))
            self.footer_labels['recaudo'].config(text=f"${total_historial:,.0f}")
        else:
            if self.db and self.db.conectado:
                stats = self.db.obtener_estadisticas()
                
                total_parq = stats['total_parqueaderos']
                ocupados = stats['ocupados']
                libres = total_parq - ocupados
                visitantes_activos = stats['visitantes_activos']
                recaudo_hoy = stats['recaudado_hoy']
                
                self.footer_labels['total_parq'].config(text=str(total_parq))
                self.footer_labels['disponibles'].config(text=str(libres))
                self.footer_labels['ocupados'].config(text=str(ocupados))
                self.footer_labels['visitantes'].config(text=str(visitantes_activos))
                self.footer_labels['recaudo'].config(text=f"${recaudo_hoy:,.0f}")
        
        self.ventana.after(2000, self.actualizar_estadisticas)
    
    def ejecutar(self):
        """Ejecuta la aplicación"""
        self.ventana.mainloop()
        
        if self.db:
            self.db.cerrar()

# =============================================================================
# FUNCIÓN PRINCIPAL
# =============================================================================

def main():
    """Función principal para ejecutar la aplicación"""
    print("="*70)
    print("🚗 SISTEMA DE CONTROL DE ACCESO VEHICULAR - VERSIÓN POSTGRESQL")
    print("Conjunto Residencial 'Los Alamos'")
    print("="*70)
    
    print("\nConfiguración de conexión PostgreSQL:")
    print("(Presione Enter para usar valores por defecto)")
    
    try:
        host = input("Host [localhost]: ") or "localhost"
        database = input("Database [control_acceso]: ") or "control_acceso"
        user = input("User [postgres]: ") or "postgres"
        password = input("Password: ")
        
        try:
            port = int(input("Port [5432]: ") or "5432")
        except:
            port = 5432
        
        db_config = {
            'host': host,
            'database': database,
            'user': user,
            'password': password,
            'port': port
        }
        
        print("\n" + "="*70)
        print("INICIANDO APLICACIÓN...")
        print("="*70)
        
        app = SistemaControlAccesoPostgreSQL(db_config)
        app.ejecutar()
        
    except KeyboardInterrupt:
        print("\n\n👋 Aplicación terminada por el usuario")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPresione Enter para salir...")

if __name__ == "__main__":
    main()