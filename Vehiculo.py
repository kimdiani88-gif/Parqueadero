# -*- coding: utf-8 -*-
"""Sistema de Control de Acceso Vehicular - PostgreSQL (CORREGIDO: Liquidación funcional)"""

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
        """Crea la interfaz gráfica con tkinter"""
        self.ventana = tk.Tk()
        self.ventana.title("🚗 Sistema de Control de Acceso Vehicular - PostgreSQL")
        self.ventana.geometry("1200x800")
        try:
            self.ventana.tk.call('tk', 'scaling', 0.9)
        except Exception:
            pass
        self.ventana.configure(bg='#ecf0f1')
        
        # Configurar estilos
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colores del tema
        color_primario = '#2c3e50'
        color_secundario = '#34495e'
        color_acento = '#3498db'
        color_fondo = '#ecf0f1'
        
        # Estilos
        style.configure('TNotebook', background=color_fondo, borderwidth=0)
        style.configure('TNotebook.Tab', padding=[20, 10], font=('Arial', 10, 'bold'))
        style.map('TNotebook.Tab',
                  background=[('selected', color_acento)],
                  foreground=[('selected', 'white')])
        
        style.configure('Title.TLabel', font=('Arial', 12, 'bold'), background=color_fondo)
        style.configure('Header.TLabel', font=('Arial', 16, 'bold'), background=color_primario, foreground='white')
        
        # Menú superior
        self.crear_menu_superior()
        
        # Header
        header_frame = tk.Frame(self.ventana, bg=color_primario, height=110)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        top_bar = tk.Frame(header_frame, bg='#e74c3c', height=4)
        top_bar.pack(fill='x')
        
        db_status = "PostgreSQL" if not self.usar_datos_memoria else "Memoria (Fallback)"
        header_label = tk.Label(header_frame, 
                    text=f"🚗 SISTEMA DE CONTROL DE ACCESO VEHICULAR",
                    font=('Arial', 14, 'bold'),
                    bg=color_primario,
                    fg='white')
        header_label.pack(pady=8)
        
        subtitle_label = tk.Label(header_frame,
                                  text=f"Modo: {db_status} | Conjunto Residencial 'Los Alamos'",
                                  font=('Arial', 10),
                                  bg=color_primario,
                                  fg='#ecf0f1')
        subtitle_label.pack(pady=3)
        
        # ===== FRAME DE BÚSQUEDA DE PLACA =====
        self.crear_frame_busqueda_placa()
        
        # Frame de estadísticas
        self.crear_frame_estadisticas()
        
        # Footer
        footer_frame = tk.Frame(self.ventana, bg=color_primario, relief='raised', bd=3, height=130)
        footer_frame.pack(fill='x', side='bottom', padx=0, pady=0)
        footer_frame.pack_propagate(False)
        
        line_top = tk.Frame(footer_frame, bg='#e74c3c', height=3)
        line_top.pack(fill='x')
        
        titulo_footer = tk.Label(footer_frame,
                                text="📊 RESUMEN DEL DÍA",
                                font=('Arial', 11, 'bold'),
                                bg=color_primario,
                                fg='#ecf0f1')
        titulo_footer.pack(pady=4)
        
        numeros_frame = tk.Frame(footer_frame, bg=color_primario)
        numeros_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        self.footer_labels = {}
        resumen_data = [
            ('total_parq', '🅿️ TOTAL', '#3498db'),
            ('disponibles', '🟢 LIBRES', '#27ae60'),
            ('ocupados', '🔴 OCUPADOS', '#e74c3c'),
            ('visitantes', '👥 VISITANTES', '#9b59b6'),
            ('recaudo', '💰 RECAUDO', '#f39c12')
        ]
        
        for i, (key, text, color) in enumerate(resumen_data):
            card = tk.Frame(numeros_frame, bg=color, relief='raised', bd=2)
            card.pack(side='left', fill='both', expand=True, padx=4, pady=3)
            
            desc_label = tk.Label(card, text=text, font=('Arial', 9, 'bold'), 
                                 bg=color, fg='white')
            desc_label.pack(pady=3)
            
            self.footer_labels[key] = tk.Label(card, text="0", 
                                              font=('Arial', 12, 'bold'), 
                                              bg=color, 
                                              fg='white')
            self.footer_labels[key].pack(pady=2)
        
        copyright_label = tk.Label(footer_frame,
                                  text="© 2024 Sistema Control Vehicular | versión 2.0 PostgreSQL",
                                  font=('Arial', 8),
                                  bg=color_primario,
                                  fg='#95a5a6')
        copyright_label.pack(pady=2)
        
        # Actualizar estadísticas cada segundo
        self.actualizar_estadisticas()
    
    def crear_menu_superior(self):
        """Crea el menú superior simplificado"""
        menubar = tk.Menu(self.ventana)
        self.ventana.config(menu=menubar)
        
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Archivo", menu=file_menu)
        file_menu.add_command(label="Salir", command=self.ventana.quit)
    
    def crear_frame_busqueda_placa(self):
        """Crea frame de búsqueda y registro de placa en la parte superior"""
        busqueda_frame = tk.Frame(self.ventana, bg='#ecf0f1', relief='raised', bd=2, height=200)
        busqueda_frame.pack(fill='x', padx=0, pady=0)
        busqueda_frame.pack_propagate(False)
        
        contenedor = tk.Frame(busqueda_frame, bg='#ecf0f1')
        contenedor.pack(fill='both', expand=True, padx=15, pady=12)
        
        titulo = tk.Label(contenedor, text="🔍 INGRESE PLACA DEL VEHÍCULO", 
                         font=('Arial', 12, 'bold'), bg='#ecf0f1', fg='#2c3e50')
        titulo.pack(anchor='w', pady=(0, 8))
        
        # Frame para entrada y botones principales
        entrada_frame = tk.Frame(contenedor, bg='#ecf0f1')
        entrada_frame.pack(fill='x', pady=5)
        
        tk.Label(entrada_frame, text="Placa:", font=('Arial', 10, 'bold'), 
                bg='#ecf0f1', fg='#2c3e50').pack(side='left', padx=(0, 10))
        
        self.entry_placa = tk.Entry(entrada_frame, font=('Arial', 11, 'bold'), 
                        width=12, relief='solid', bd=2, 
                        bg='white', fg='#2c3e50')
        self.entry_placa.pack(side='left', padx=5)
        self.entry_placa.bind('<Return>', lambda e: self.buscar_placa_entrada())
        
        btn_buscar = tk.Button(entrada_frame, text="🔍 Buscar", 
                      command=self.buscar_placa_entrada,
                      bg='#3498db', fg='white', font=('Arial', 9, 'bold'),
                      relief='flat', bd=0, padx=12, pady=4,
                      activebackground='#2980b9')
        btn_buscar.pack(side='left', padx=5)
        
        btn_limpiar = tk.Button(entrada_frame, text="🗑️ Limpiar", 
                       command=lambda: self.entry_placa.delete(0, tk.END),
                       bg='#e74c3c', fg='white', font=('Arial', 9, 'bold'),
                       relief='flat', bd=0, padx=12, pady=4,
                       activebackground='#c0392b')
        btn_limpiar.pack(side='left', padx=5)
        
        # Frame de botones de acción (SEPARADOS POR TIPO)
        botones_accion_frame = tk.Frame(contenedor, bg='#ecf0f1')
        botones_accion_frame.pack(fill='x', pady=8)
        
        tk.Label(botones_accion_frame, text="ACCIONES:", font=('Arial', 9, 'bold'), 
                bg='#ecf0f1', fg='#2c3e50').pack(side='left', padx=(0, 15))
        
        # Botón para RESIDENTES (entrada)
        btn_entrada_residente = tk.Button(botones_accion_frame, text="👨‍💼 ENTRADA RESIDENTE", 
                         command=self.registrar_entrada_residente,
                         bg='#27ae60', fg='white', font=('Arial', 9, 'bold'),
                         relief='flat', bd=0, padx=12, pady=4,
                         activebackground='#229954')
        btn_entrada_residente.pack(side='left', padx=5)
        
        # Botón para VISITANTES (entrada)
        btn_entrada_visitante = tk.Button(botones_accion_frame, text="👥 ENTRADA VISITANTE", 
                         command=self.registrar_entrada_visitante,
                         bg='#f39c12', fg='white', font=('Arial', 9, 'bold'),
                         relief='flat', bd=0, padx=12, pady=4,
                         activebackground='#e67e22')
        btn_entrada_visitante.pack(side='left', padx=5)
        
        # Botón para LIQUIDAR VISITANTE (SALIDA CON PAGO)
        btn_liquidar = tk.Button(botones_accion_frame, text="💰 LIQUIDAR VISITANTE", 
                        command=self.abrir_ventana_liquidar,
                        bg='#16a085', fg='white', font=('Arial', 9, 'bold'),
                        relief='flat', bd=0, padx=12, pady=4,
                        activebackground='#138d75')
        btn_liquidar.pack(side='left', padx=5)
        
        # Botón para SALIDA DE RESIDENTE (sin pago)
        btn_salida_residente = tk.Button(botones_accion_frame, text="🚪 SALIDA RESIDENTE", 
                         command=self.registrar_salida_residente,
                         bg='#3498db', fg='white', font=('Arial', 9, 'bold'),
                         relief='flat', bd=0, padx=12, pady=4,
                         activebackground='#2980b9')
        btn_salida_residente.pack(side='left', padx=5)
        
        # Botón ver parqueaderos
        btn_ver_parqueaderos = tk.Button(botones_accion_frame, text="📊 VER PARQUEADEROS", 
                         command=self.mostrar_estado_parqueaderos,
                         bg='#8e44ad', fg='white', font=('Arial', 9, 'bold'),
                         relief='flat', bd=0, padx=12, pady=4,
                         activebackground='#7d3c98')
        btn_ver_parqueaderos.pack(side='left', padx=5)
        
        # Frame de resultado MEJORADO
        resultado_frame = tk.Frame(contenedor, bg='#ecf0f1')
        resultado_frame.pack(fill='x', pady=8)
        
        self.panel_resultado_placa = tk.Frame(resultado_frame, bg='#ecf0f1', relief='solid', bd=2)
        self.panel_resultado_placa.pack(fill='both', expand=True)
        
        self.label_resultado_placa = tk.Label(self.panel_resultado_placa, 
                                             text="📝 Ingrese una placa y presione Buscar", 
                                             font=('Arial', 11, 'bold'), bg='#ecf0f1', 
                                             fg='#7f8c8d', relief='flat', bd=0, padx=15, pady=10)
        self.label_resultado_placa.pack(fill='both', expand=True)
    
    def buscar_placa_entrada(self):
        """Busca una placa en el sistema y muestra el resultado con colores"""
        placa = self.entry_placa.get().upper().strip()
        
        if not placa:
            self.label_resultado_placa.config(text="⚠️ Por favor ingrese una placa", fg='#e74c3c')
            self.panel_resultado_placa.config(bg='#fadbd8')
            return
        
        try:
            if self.usar_datos_memoria:
                # Buscar en datos de memoria
                if placa in self.datos_memoria['residentes']:
                    residente = self.datos_memoria['residentes'][placa]
                    estado_visual = "🟢 LIBRE" if residente['estado'].lower() == 'libre' else "🔴 OCUPADO"
                    texto = (f"👨‍💼 RESIDENTE IDENTIFICADO\n"
                            f"Nombre: {residente['nombre']}\n"
                            f"Apartamento: {residente['apartamento']}\n"
                            f"Parqueadero: {residente['parqueadero']}\n"
                            f"Estado: {estado_visual}")
                    self.label_resultado_placa.config(text=texto, fg='white')
                    self.panel_resultado_placa.config(bg='#27ae60')
                else:
                    # Verificar si es visitante activo
                    if placa in self.datos_memoria['visitantes_activos']:
                        datos = self.datos_memoria['visitantes_activos'][placa]
                        tiempo = datetime.now() - datos['hora_entrada']
                        horas = tiempo.total_seconds() / 3600
                        texto = (f"👥 VISITANTE ACTIVO\n"
                                f"Placa: {placa}\n"
                                f"Parqueadero: {datos['parqueadero']}\n"
                                f"Tiempo: {horas:.1f} horas")
                    else:
                        texto = (f"👥 VISITANTE (NO REGISTRADO)\n"
                                f"Placa: {placa}\n"
                                f"Acción: Use 'ENTRADA VISITANTE' para ingresar")
                    
                    self.label_resultado_placa.config(text=texto, fg='white')
                    self.panel_resultado_placa.config(bg='#f39c12')
            else:
                # Buscar en PostgreSQL
                if self.db and self.db.conectado:
                    residente = self.db.verificar_placa_residente(placa)
                    
                    if residente:
                        texto = (f"👨‍💼 RESIDENTE IDENTIFICADO\n"
                                f"Nombre: {residente['nombre']}\n"
                                f"Apartamento: {residente['apartamento']}\n"
                                f"Parqueadero: {residente['parqueadero']}\n"
                                f"Estado: {residente['estado']}")
                        self.label_resultado_placa.config(text=texto, fg='white')
                        self.panel_resultado_placa.config(bg='#27ae60')
                    else:
                        # Verificar si es visitante activo
                        visitante = self.db.obtener_visitante_activo_por_placa(placa)
                        if visitante:
                            texto = (f"👥 VISITANTE ACTIVO\n"
                                    f"Placa: {placa}\n"
                                    f"Parqueadero: {visitante['parqueadero']}\n"
                                    f"Hora entrada: {visitante['hora_entrada'].strftime('%H:%M') if hasattr(visitante['hora_entrada'], 'strftime') else visitante['hora_entrada']}")
                        else:
                            texto = (f"👥 VISITANTE (NO REGISTRADO)\n"
                                    f"Placa: {placa}\n"
                                    f"Acción: Use 'ENTRADA VISITANTE' para ingresar")
                        
                        self.label_resultado_placa.config(text=texto, fg='white')
                        self.panel_resultado_placa.config(bg='#f39c12')
                else:
                    self.label_resultado_placa.config(text="❌ Error: Sin conexión a base de datos", fg='#e74c3c')
                    self.panel_resultado_placa.config(bg='#fadbd8')
        except Exception as e:
            self.label_resultado_placa.config(text=f"❌ Error en búsqueda: {str(e)}", fg='#e74c3c')
            self.panel_resultado_placa.config(bg='#fadbd8')
    
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
            self.label_resultado_placa.config(text="Ingrese una placa para buscar...", fg='#7f8c8d', bg='#ecf0f1')
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
            self.label_resultado_placa.config(text="Ingrese una placa para buscar...", fg='#7f8c8d', bg='#ecf0f1')
            self.actualizar_estadisticas()
            self.actualizar_lista_parqueaderos()
            
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
            self.label_resultado_placa.config(text="Ingrese una placa para buscar...", fg='#7f8c8d', bg='#ecf0f1')
            self.actualizar_estadisticas()
            
        except Exception as e:
            messagebox.showerror("Error", f"Error al registrar salida: {str(e)}")
    
    def abrir_ventana_liquidar(self):
        """Abre ventana para liquidar pago de visitante (SALIDA CON PAGO)"""
        placa_inicial = self.entry_placa.get().upper().strip()
        
        ventana_liq = tk.Toplevel(self.ventana)
        ventana_liq.title("💰 Liquidar Pago de Visitante")
        ventana_liq.geometry("550x450")
        ventana_liq.resizable(False, False)
        ventana_liq.configure(bg='#ecf0f1')
        
        ventana_liq.transient(self.ventana)
        ventana_liq.grab_set()
        
        # Encabezado
        header = tk.Frame(ventana_liq, bg='#16a085', height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text="💰 LIQUIDAR PAGO DE VISITANTE", font=('Arial', 14, 'bold'), 
                bg='#16a085', fg='white').pack(pady=10)
        
        # Frame principal
        main_frame = tk.Frame(ventana_liq, bg='#ecf0f1')
        main_frame.pack(fill='both', expand=True, padx=20, pady=15)
        
        # Campo placa
        tk.Label(main_frame, text="Placa del Visitante:", font=('Arial', 10, 'bold'),
                bg='#ecf0f1', fg='#2c3e50').pack(anchor='w', pady=(0, 5))
        entry_placa_liq = tk.Entry(main_frame, font=('Arial', 12), width=20,
                                   relief='solid', bd=2, bg='white')
        entry_placa_liq.pack(fill='x', pady=(0, 15))
        if placa_inicial:
            entry_placa_liq.insert(0, placa_inicial)
        entry_placa_liq.focus()
        
        # Frame de información calculada
        info_frame = tk.Frame(main_frame, bg='#fdeaa8', relief='solid', bd=2)
        info_frame.pack(fill='x', pady=(0, 15))
        
        tk.Label(info_frame, text="📊 CÁLCULO DE TARIFA", font=('Arial', 10, 'bold'),
                bg='#f39c12', fg='white', padx=10, pady=5).pack(fill='x')
        
        label_calculo_tiempo = tk.Label(info_frame, text="⏱️ Tiempo: --",
                                            font=('Arial', 10), bg='#fdeaa8', fg='#2c3e50',
                                            anchor='w', padx=15, pady=5)
        label_calculo_tiempo.pack(fill='x')
        
        label_calculo_tarifa = tk.Label(info_frame, text="💵 Tarifa: --",
                                            font=('Arial', 11, 'bold'), bg='#fdeaa8', fg='#27ae60',
                                            anchor='w', padx=15, pady=5)
        label_calculo_tarifa.pack(fill='x')
        
        label_calculo_tipo = tk.Label(info_frame, text="📌 Tipo: --",
                                          font=('Arial', 10), bg='#fdeaa8', fg='#2c3e50',
                                          anchor='w', padx=15, pady=(5, 10))
        label_calculo_tipo.pack(fill='x')
        
        # Variable para guardar datos del visitante
        datos_visitante = {'id': None, 'parqueadero_id': None, 'placa': ''}
        tarifa_calculada = {'valor': 0}
        
        def calcular_tarifa():
            """Calcula la tarifa según tiempo estacionado"""
            placa = entry_placa_liq.get().upper().strip()
            
            if not placa:
                label_calculo_tiempo.config(text="⏱️ Tiempo: --")
                label_calculo_tarifa.config(text="💵 Tarifa: --")
                label_calculo_tipo.config(text="📌 Tipo: --")
                datos_visitante['id'] = None
                return
            
            if self.usar_datos_memoria:
                if placa in self.datos_memoria['visitantes_activos']:
                    hora_salida = datetime.now()
                    hora_entrada = self.datos_memoria['visitantes_activos'][placa]['hora_entrada']
                    parqueadero = self.datos_memoria['visitantes_activos'][placa]['parqueadero']
                    
                    datos_visitante['placa'] = placa
                    datos_visitante['parqueadero'] = parqueadero
                    
                    tiempo = hora_salida - hora_entrada
                    horas = tiempo.total_seconds() / 3600
                    
                    if horas <= 5:
                        cobro = int(np.ceil(horas)) * 1000
                        tipo = "Tarifa por hora ($1000/hora)"
                    else:
                        cobro = 10000
                        tipo = "Tarifa plena ($10000)"
                    
                    tarifa_calculada['valor'] = cobro
                    
                    label_calculo_tiempo.config(text=f"⏱️ Tiempo: {horas:.2f} horas")
                    label_calculo_tarifa.config(text=f"💵 Tarifa: ${cobro:,} COP")
                    label_calculo_tipo.config(text=f"📌 Tipo: {tipo}")
                else:
                    label_calculo_tiempo.config(text="⏱️ Tiempo: ❌ Placa no encontrada o no es visitante activo")
                    label_calculo_tarifa.config(text="💵 Tarifa: $0")
                    label_calculo_tipo.config(text="📌 Tipo: Error")
                    tarifa_calculada['valor'] = 0
                    datos_visitante['id'] = None
            else:
                if self.db and self.db.conectado:
                    visitante = self.db.obtener_visitante_activo_por_placa(placa)
                    if visitante:
                        hora_entrada_str = visitante['hora_entrada']
                        
                        if isinstance(hora_entrada_str, str):
                            try:
                                hora_entrada = datetime.fromisoformat(hora_entrada_str.replace('Z', '+00:00'))
                            except:
                                hora_entrada = datetime.strptime(hora_entrada_str, '%Y-%m-%d %H:%M:%S')
                        else:
                            hora_entrada = hora_entrada_str
                        
                        if hora_entrada.tzinfo is not None:
                            hora_entrada = hora_entrada.replace(tzinfo=None)
                        
                        datos_visitante['id'] = visitante['id']
                        datos_visitante['parqueadero_id'] = visitante['parqueadero_id']
                        datos_visitante['placa'] = placa
                        
                        hora_salida = datetime.now()
                        tiempo = hora_salida - hora_entrada
                        horas = tiempo.total_seconds() / 3600
                        
                        if horas <= 5:
                            cobro = int(np.ceil(horas)) * 1000
                            tipo = "Tarifa por hora ($1000/hora)"
                        else:
                            cobro = 10000
                            tipo = "Tarifa plena ($10000)"
                        
                        tarifa_calculada['valor'] = cobro
                        
                        label_calculo_tiempo.config(text=f"⏱️ Tiempo: {horas:.2f} horas")
                        label_calculo_tarifa.config(text=f"💵 Tarifa: ${cobro:,} COP")
                        label_calculo_tipo.config(text=f"📌 Tipo: {tipo}")
                    else:
                        label_calculo_tiempo.config(text="⏱️ Tiempo: ❌ Placa no encontrada o no es visitante activo")
                        label_calculo_tarifa.config(text="💵 Tarifa: $0")
                        label_calculo_tipo.config(text="📌 Tipo: Error")
                        tarifa_calculada['valor'] = 0
                        datos_visitante['id'] = None
        
        # Bind para calcular cuando se ingresa placa
        entry_placa_liq.bind('<KeyRelease>', lambda e: calcular_tarifa())
        
        # Si ya había una placa, calcular automáticamente
        if placa_inicial:
            ventana_liq.after(100, calcular_tarifa)
        
        # Frame de botones
        btn_frame = tk.Frame(main_frame, bg='#ecf0f1')
        btn_frame.pack(fill='x', pady=10)
        
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
                    resultado = self.db.registrar_salida_visitante(
                        datos_visitante['id'], 
                        datos_visitante['parqueadero_id']
                    )
                    
                    if resultado:
                        messagebox.showinfo("✅ Cobro Exitoso", 
                                          f"Placa: {placa}\nCobro: ${resultado['valor_pagado']:,.0f} COP\n✅ Salida registrada")
                        ventana_liq.destroy()
                    else:
                        messagebox.showerror("Error", "❌ Error registrando salida")
                        return
            
            # Actualizar vistas después de cerrar
            self.actualizar_estadisticas()
            self.actualizar_lista_parqueaderos()
            self.entry_placa.delete(0, tk.END)
            self.label_resultado_placa.config(text="Ingrese una placa para buscar...", fg='#7f8c8d', bg='#ecf0f1')
        
        btn_liquidar = tk.Button(btn_frame, text="✅ CONFIRMAR PAGO Y REGISTRAR SALIDA", 
                                 command=liquidar_confirmar,
                                 bg='#16a085', fg='white', font=('Arial', 10, 'bold'),
                                 relief='flat', bd=0, padx=20, pady=10,
                                 activebackground='#138d75')
        btn_liquidar.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        btn_cancelar = tk.Button(btn_frame, text="❌ Cancelar", 
                                 command=ventana_liq.destroy,
                                 bg='#e74c3c', fg='white', font=('Arial', 10, 'bold'),
                                 relief='flat', bd=0, padx=20, pady=10,
                                 activebackground='#c0392b')
        btn_cancelar.pack(side='left', fill='both', expand=True, padx=(5, 0))
    
    def mostrar_estado_parqueaderos(self):
        """Muestra ventana con estado de todos los parqueaderos"""
        ventana_estado = tk.Toplevel(self.ventana)
        ventana_estado.title("📊 Estado de Parqueaderos")
        ventana_estado.geometry("700x600")
        ventana_estado.resizable(True, True)
        ventana_estado.configure(bg='#ecf0f1')
        
        ventana_estado.transient(self.ventana)
        ventana_estado.grab_set()
        
        header = tk.Frame(ventana_estado, bg='#8e44ad', height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text="📊 ESTADO DE TODOS LOS PARQUEADEROS", font=('Arial', 14, 'bold'), 
                bg='#8e44ad', fg='white').pack(pady=10)
        
        canvas_frame = tk.Frame(ventana_estado, bg='#ecf0f1')
        canvas_frame.pack(fill='both', expand=True, padx=20, pady=15)
        
        canvas = tk.Canvas(canvas_frame, bg='#fff', relief='solid', bd=1)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg='#fff')
        
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
                                     font=('Arial', 11, 'bold'), bg='#3498db', fg='white',
                                     padx=10, pady=8, relief='flat')
            lbl_res_header.pack(fill='x', pady=(0, 10))
            
            for placa, datos in self.datos_memoria['residentes'].items():
                estado_color = '#27ae60' if datos['estado'].lower() == 'libre' else '#e74c3c'
                estado_texto = "🟢 LIBRE" if datos['estado'].lower() == 'libre' else "🔴 OCUPADO"
                
                card = tk.Frame(scrollable_frame, bg=estado_color, relief='solid', bd=2)
                card.pack(fill='x', pady=5, padx=5)
                
                info_text = (f"Parqueadero #{datos['parqueadero']} | {estado_texto} | "
                            f"Residente: {datos['nombre']} (Apto {datos['apartamento']}) | Placa: {placa}")
                
                lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                              bg=estado_color, fg='white', anchor='w', justify='left', padx=10, pady=8)
                lbl.pack(fill='x')
            
            # Mostrar visitantes
            lbl_vis_header = tk.Label(scrollable_frame, text="👥 PARQUEADEROS VISITANTES", 
                                     font=('Arial', 11, 'bold'), bg='#9b59b6', fg='white',
                                     padx=10, pady=8, relief='flat')
            lbl_vis_header.pack(fill='x', pady=(15, 10))
            
            for placa, datos in self.datos_memoria['visitantes_activos'].items():
                tiempo = datetime.now() - datos['hora_entrada']
                horas = tiempo.total_seconds() / 3600
                
                card = tk.Frame(scrollable_frame, bg='#f39c12', relief='solid', bd=2)
                card.pack(fill='x', pady=5, padx=5)
                
                info_text = (f"Parqueadero #{datos['parqueadero']} | 🔴 OCUPADO (visitante) | "
                            f"Placa: {placa} | Tiempo: {horas:.1f}h")
                
                lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                              bg='#f39c12', fg='white', anchor='w', justify='left', padx=10, pady=8)
                lbl.pack(fill='x')
            
            for parq_num in self.datos_memoria['parqueaderos_visitantes']:
                card = tk.Frame(scrollable_frame, bg='#27ae60', relief='solid', bd=2)
                card.pack(fill='x', pady=5, padx=5)
                
                info_text = f"Parqueadero #{parq_num} | 🟢 LIBRE (disponible para visitante)"
                
                lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                              bg='#27ae60', fg='white', anchor='w', justify='left', padx=10, pady=8)
                lbl.pack(fill='x')
        else:
            if self.db and self.db.conectado:
                parqueaderos = self.db.obtener_estado_parqueaderos()
                
                for p in parqueaderos:
                    estado_color = '#27ae60' if p['estado'] == 'LIBRE' else '#e74c3c'
                    estado_texto = "🟢 LIBRE" if p['estado'] == 'LIBRE' else "🔴 OCUPADO"
                    
                    card = tk.Frame(scrollable_frame, bg=estado_color, relief='solid', bd=2)
                    card.pack(fill='x', pady=5, padx=5)
                    
                    residente = p['residente'] if p['residente'] else "-"
                    apartamento = p['apartamento'] if p['apartamento'] else "-"
                    placa = p['placa'] if p['placa'] else "-"
                    
                    info_text = (f"Parqueadero #{p['numero']} | {estado_texto} | "
                                f"Residente: {residente} (Apto {apartamento}) | Placa: {placa}")
                    
                    lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                                  bg=estado_color, fg='white', anchor='w', justify='left', padx=10, pady=8)
                    lbl.pack(fill='x')
    
    def crear_frame_estadisticas(self):
        """Crea frame con estadísticas en tiempo real por tipo de parqueadero"""
        self.stats_frame = tk.Frame(self.ventana, bg='#2c3e50', relief='ridge', bd=3)
        self.stats_frame.pack(fill='x', padx=0, pady=0)
        
        main_container = tk.Frame(self.stats_frame, bg='#34495e')
        main_container.pack(fill='x', padx=0, pady=0)
        
        # SECCIÓN DE RESIDENTES
        residentes_container = tk.Frame(main_container, bg='#34495e')
        residentes_container.pack(fill='x', padx=15, pady=12)
        
        residentes_label = tk.Label(residentes_container, text="👨‍💼 PARQUEADEROS RESIDENTES", 
                         font=('Arial', 11, 'bold'), bg='#3498db', fg='white',
                         relief='flat', bd=0, padx=10, pady=8)
        residentes_label.pack(fill='x', padx=0, pady=(0, 8))
        
        self.stats_labels = {}
        residentes_data = [
            ('residentes_total', '🅿️ Total', '#3498db'),
            ('residentes_ocupados', '🔴 Ocupados', '#e74c3c'),
            ('residentes_libres', '🟢 Libres', '#27ae60'),
            ('residentes_ingresos', '💵 Ingresos', '#16a085')
        ]
        
        residentes_row = tk.Frame(main_container, bg='#34495e')
        residentes_row.pack(fill='x', padx=15, pady=(0, 12))
        
        for i, (key, text, color) in enumerate(residentes_data):
            card = tk.Frame(residentes_row, bg=color, relief='raised', bd=2)
            card.pack(side='left', fill='both', expand=True, padx=6, pady=3)
            
            label_titulo = tk.Label(card, text=text, font=('Arial', 9, 'bold'), bg=color, fg='white', pady=3)
            label_titulo.pack(fill='x')
            
            self.stats_labels[key] = tk.Label(card, text="0", font=('Arial', 12, 'bold'), 
                                             bg=color, fg='white', pady=5)
            self.stats_labels[key].pack(fill='x')
        
        # SECCIÓN DE VISITANTES
        visitantes_container = tk.Frame(main_container, bg='#34495e')
        visitantes_container.pack(fill='x', padx=15, pady=(0, 12))
        
        visitantes_label = tk.Label(visitantes_container, text="👥 PARQUEADEROS VISITANTES", 
                        font=('Arial', 11, 'bold'), bg='#9b59b6', fg='white',
                        relief='flat', bd=0, padx=10, pady=8)
        visitantes_label.pack(fill='x', padx=0, pady=(0, 8))
        
        visitantes_data = [
            ('visitantes_total', '🅿️ Total', '#9b59b6'),
            ('visitantes_ocupados', '🔴 Ocupados', '#e74c3c'),
            ('visitantes_libres', '🟢 Libres', '#27ae60'),
            ('visitantes_activos', '⏱️ Activos', '#f39c12')
        ]
        
        visitantes_row = tk.Frame(main_container, bg='#34495e')
        visitantes_row.pack(fill='x', padx=15, pady=(0, 12))
        
        for i, (key, text, color) in enumerate(visitantes_data):
            card = tk.Frame(visitantes_row, bg=color, relief='raised', bd=2)
            card.pack(side='left', fill='both', expand=True, padx=6, pady=3)
            
            label_titulo = tk.Label(card, text=text, font=('Arial', 9, 'bold'), bg=color, fg='white', pady=3)
            label_titulo.pack(fill='x')
            
            self.stats_labels[key] = tk.Label(card, text="0", font=('Arial', 12, 'bold'), 
                                             bg=color, fg='white', pady=5)
            self.stats_labels[key].pack(fill='x')
        
        # SECCIÓN DE TOTALES
        totales_container = tk.Frame(main_container, bg='#34495e')
        totales_container.pack(fill='x', padx=15, pady=(0, 12))
        
        totales_label = tk.Label(totales_container, text="📊 RESUMEN GENERAL", 
                    font=('Arial', 11, 'bold'), bg='#2c3e50', fg='white',
                    relief='flat', bd=0, padx=10, pady=8)
        totales_label.pack(fill='x', padx=0, pady=(0, 8))
        
        totales_data = [
            ('total_parqueaderos', '🅿️ TOTAL', '#2c3e50'),
            ('total_ocupados', '🔴 OCUPADOS', '#34495e'),
            ('visitantes_ingresos', '💰 RECAUDO', '#1abc9c'),
        ]
        
        totales_row = tk.Frame(main_container, bg='#34495e')
        totales_row.pack(fill='x', padx=15, pady=(0, 12))
        
        for i, (key, text, color) in enumerate(totales_data):
            card = tk.Frame(totales_row, bg=color, relief='raised', bd=2)
            card.pack(side='left', fill='both', expand=True, padx=6, pady=3)
            
            label_titulo = tk.Label(card, text=text, font=('Arial', 9, 'bold'), bg=color, fg='white', pady=3)
            label_titulo.pack(fill='x')
            
            self.stats_labels[key] = tk.Label(card, text="0", font=('Arial', 12, 'bold'), 
                                             bg=color, fg='white', pady=5)
            self.stats_labels[key].pack(fill='x')
        
        # SECCIÓN DE VEHÍCULOS ACTIVOS
        activos_container = tk.Frame(main_container, bg='#34495e')
        activos_container.pack(fill='x', padx=15, pady=(0, 12))
        
        activos_label = tk.Label(activos_container, text="🚗 VEHÍCULOS EN PARQUEADERO AHORA", 
                    font=('Arial', 11, 'bold'), bg='#34495e', fg='white',
                    relief='flat', bd=0, padx=10, pady=8)
        activos_label.pack(fill='x', padx=0, pady=(0, 8))
        
        residentes_activos_frame = tk.Frame(main_container, bg='#27ae60', relief='solid', bd=1)
        residentes_activos_frame.pack(fill='x', padx=15, pady=(0, 6))
        
        tk.Label(residentes_activos_frame, text="👨‍💼 RESIDENTES EN PARQUEADERO", 
            font=('Arial', 9, 'bold'), bg='#27ae60', fg='white', padx=10, pady=5).pack(fill='x')

        self.label_residentes_activos = tk.Label(residentes_activos_frame, text="• Ninguno", 
                             font=('Arial', 8), bg='#d5f4e6', fg='#27ae60', 
                             justify='left', padx=15, pady=6, relief='flat')
        self.label_residentes_activos.pack(fill='both', expand=True, padx=5, pady=5)
        
        visitantes_activos_frame = tk.Frame(main_container, bg='#f39c12', relief='solid', bd=1)
        visitantes_activos_frame.pack(fill='x', padx=15, pady=(0, 12))
        
        tk.Label(visitantes_activos_frame, text="👥 VISITANTES EN PARQUEADERO", 
            font=('Arial', 9, 'bold'), bg='#f39c12', fg='white', padx=10, pady=5).pack(fill='x')

        self.label_visitantes_activos = tk.Label(visitantes_activos_frame, text="• Ninguno", 
                             font=('Arial', 8), bg='#fdeaa8', fg='#e67e22', 
                             justify='left', padx=15, pady=6, relief='flat')
        self.label_visitantes_activos.pack(fill='both', expand=True, padx=5, pady=5)
    
    def actualizar_lista_parqueaderos(self):
        """Actualiza la lista de parqueaderos disponibles para visitantes"""
        if self.usar_datos_memoria:
            disponibles = [str(p) for p in self.datos_memoria['parqueaderos_visitantes']]
        else:
            if self.db and self.db.conectado:
                parqueaderos = self.db.obtener_parqueaderos_libres_visitantes()
                disponibles = [str(p['numero']) for p in parqueaderos]
    
    def actualizar_estadisticas(self):
        """Actualiza las estadísticas en tiempo real por tipo de parqueadero"""
        if self.usar_datos_memoria:
            total_residentes = len(self.datos_memoria['residentes'])
            total_parqueaderos_visitantes = self.datos_memoria.get('total_parqueaderos_visitantes', 5)
            
            ocupados_residentes = sum(1 for r in self.datos_memoria['residentes'].values() if r['estado'] == 'ocupado')
            libres_residentes = total_residentes - ocupados_residentes
            
            ocupados_visitantes = len(self.datos_memoria['visitantes_activos'])
            libres_visitantes = total_parqueaderos_visitantes - ocupados_visitantes
            
            total = total_residentes + total_parqueaderos_visitantes
            total_historial = sum(r['cobro'] for r in self.datos_memoria['historial_visitantes'])
            
            self.stats_labels['residentes_total'].config(text=str(total_residentes))
            self.stats_labels['residentes_ocupados'].config(text=str(ocupados_residentes))
            self.stats_labels['residentes_libres'].config(text=str(libres_residentes))
            self.stats_labels['residentes_ingresos'].config(text="$0")
            
            self.stats_labels['visitantes_total'].config(text=str(total_parqueaderos_visitantes))
            self.stats_labels['visitantes_ocupados'].config(text=str(ocupados_visitantes))
            self.stats_labels['visitantes_libres'].config(text=str(libres_visitantes))
            self.stats_labels['visitantes_activos'].config(text=str(ocupados_visitantes))
            
            self.stats_labels['total_parqueaderos'].config(text=str(total))
            self.stats_labels['total_ocupados'].config(text=str(ocupados_residentes + ocupados_visitantes))
            self.stats_labels['visitantes_ingresos'].config(text=f"${total_historial:,.0f}")
            
            libres_totales = libres_residentes + libres_visitantes
            self.footer_labels['total_parq'].config(text=str(total))
            self.footer_labels['disponibles'].config(text=str(libres_totales))
            self.footer_labels['ocupados'].config(text=str(ocupados_residentes + ocupados_visitantes))
            self.footer_labels['visitantes'].config(text=str(total_parqueaderos_visitantes))
            self.footer_labels['recaudo'].config(text=f"${total_historial:,.0f}")
            
            residentes_ocupados = [
                f"• {placa}: {datos['nombre']} (Apto {datos['apartamento']}) - Parqueadero {datos['parqueadero']}"
                for placa, datos in self.datos_memoria['residentes'].items() 
                if datos['estado'].lower() == 'ocupado'
            ]
            
            if residentes_ocupados:
                self.label_residentes_activos.config(text='\n'.join(residentes_ocupados))
            else:
                self.label_residentes_activos.config(text="• Ninguno")
            
            visitantes_ocupados = [
                f"• {placa} - Parqueadero {datos['parqueadero']}"
                for placa, datos in self.datos_memoria['visitantes_activos'].items()
            ]
            
            if visitantes_ocupados:
                self.label_visitantes_activos.config(text='\n'.join(visitantes_ocupados))
            else:
                self.label_visitantes_activos.config(text="• Ninguno")
        else:
            if self.db and self.db.conectado:
                stats = self.db.obtener_estadisticas_por_tipo()
                
                res_stats = stats['residentes']
                self.stats_labels['residentes_total'].config(text=str(res_stats['total']))
                self.stats_labels['residentes_ocupados'].config(text=str(res_stats['ocupados']))
                self.stats_labels['residentes_libres'].config(text=str(res_stats['libres']))
                self.stats_labels['residentes_ingresos'].config(text=f"${res_stats['ingresos']:,.0f}")
                
                vis_stats = stats['visitantes']
                self.stats_labels['visitantes_total'].config(text=str(vis_stats['total']))
                self.stats_labels['visitantes_ocupados'].config(text=str(vis_stats['ocupados']))
                self.stats_labels['visitantes_libres'].config(text=str(vis_stats['libres']))
                self.stats_labels['visitantes_activos'].config(text=str(vis_stats['activos']))
                
                total_parqueaderos = res_stats['total'] + vis_stats['total']
                total_ocupados = res_stats['ocupados'] + vis_stats['ocupados']
                total_libres = res_stats['libres'] + vis_stats['libres']
                self.stats_labels['total_parqueaderos'].config(text=str(total_parqueaderos))
                self.stats_labels['total_ocupados'].config(text=str(total_ocupados))
                self.stats_labels['visitantes_ingresos'].config(text=f"${vis_stats['ingresos']:,.0f}")
                
                general_stats = self.db.obtener_estadisticas()
                recaudo_hoy = general_stats['recaudado_hoy']
                
                self.footer_labels['total_parq'].config(text=str(total_parqueaderos))
                self.footer_labels['disponibles'].config(text=str(total_libres))
                self.footer_labels['ocupados'].config(text=str(total_ocupados))
                self.footer_labels['visitantes'].config(text=str(vis_stats['total']))
                self.footer_labels['recaudo'].config(text=f"${recaudo_hoy:,.0f}")
                
                visitantes_activos = self.db.obtener_visitantes_activos()
                if visitantes_activos:
                    self.label_visitantes_activos.config(
                        text='\n'.join([f"• {v['placa']} - P-{v['parqueadero']}" for v in visitantes_activos])
                    )
                else:
                    self.label_visitantes_activos.config(text="• Ninguno")
        
        self.ventana.after(2000, self.actualizar_estadisticas)
    
    def actualizar_todas_tablas(self):
        """Actualiza todas las tablas"""
        pass
    
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