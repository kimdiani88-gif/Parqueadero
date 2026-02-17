# -*- coding: utf-8 -*-
"""Sistema de Control de Acceso Vehicular - Versión PostgreSQL Corregida"""

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

# Configurar pytesseract (ajustar ruta según tu instalación)
if os.name == 'nt':  # Windows
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
else:  # Linux/Mac
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'

# =============================================================================
# GESTOR DE BASE DE DATOS POSTGRESQL CORREGIDO
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
        
        # Configuración por defecto - CORREGIDO: 'localhost' en lugar de 'local'
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
        """Crea la estructura de la base de datos según init.sql"""
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
                    
                    NEW.valor_pagado := NEW.total_horas * 1000;
                    
                    IF NEW.total_horas > 5 THEN
                        NEW.valor_pagado := NEW.valor_pagado + 10000;
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
    
    # ============= CONSULTAS DEL ARCHIVO QUERYS.SQL =============
    
    def verificar_placa_residente(self, placa):
        """
        Verifica si una placa es de residente
        Consulta del archivo querys.sql
        """
        if not self.verificar_conexion():
            return None
        
        try:
            query = """
                SELECT r.nombre, p.numero AS parqueadero, p.estado
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
        """
        Registra entrada de visitante
        Basado en la consulta del archivo querys.sql
        """
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
        """
        Registra salida de visitante
        Basado en la consulta del archivo querys.sql
        """
        if not self.verificar_conexion():
            return None
        
        try:
            # Actualizar hora de salida (el trigger calculará automáticamente)
            self.cursor.execute("""
                UPDATE registros_visitantes
                SET hora_salida = CURRENT_TIMESTAMP
                WHERE id = %s
                RETURNING total_horas, valor_pagado
            """, (registro_id,))
            
            resultado = self.cursor.fetchone()
            
            # Liberar parqueadero
            self.cursor.execute("""
                UPDATE parqueaderos
                SET estado = 'LIBRE'
                WHERE id = %s
            """, (parqueadero_id,))
            
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
        """Marca un parqueadero como OCUPADO"""
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
        """Marca un parqueadero como LIBRE"""
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
        """Obtiene estadísticas separadas por tipo de parqueadero (Residentes vs Visitantes)"""
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
            # PARQUEADEROS DE RESIDENTES (con residente_id)
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE residente_id IS NOT NULL")
            result = self.cursor.fetchone()
            stats['residentes']['total'] = result['count'] if result else 0
            
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE residente_id IS NOT NULL AND estado = 'OCUPADO'")
            result = self.cursor.fetchone()
            stats['residentes']['ocupados'] = result['count'] if result else 0
            
            stats['residentes']['libres'] = stats['residentes']['total'] - stats['residentes']['ocupados']
            
            # PARQUEADEROS DE VISITANTES (sin residente_id)
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE residente_id IS NULL")
            result = self.cursor.fetchone()
            stats['visitantes']['total'] = result['count'] if result else 0
            
            self.cursor.execute("SELECT COUNT(*) as count FROM parqueaderos WHERE residente_id IS NULL AND estado = 'OCUPADO'")
            result = self.cursor.fetchone()
            stats['visitantes']['ocupados'] = result['count'] if result else 0
            
            stats['visitantes']['libres'] = stats['visitantes']['total'] - stats['visitantes']['ocupados']
            
            # Visitantes activos (registros sin hora_salida)
            self.cursor.execute("SELECT COUNT(*) as count FROM registros_visitantes WHERE hora_salida IS NULL")
            result = self.cursor.fetchone()
            stats['visitantes']['activos'] = result['count'] if result else 0
            
            # Ingresos por tipo de parqueadero
            # Visitantes activos en parqueaderos de visitantes
            self.cursor.execute("""
                SELECT COALESCE(SUM(rg.valor_pagado), 0) as total
                FROM registros_visitantes rg
                JOIN parqueaderos p ON rg.parqueadero_id = p.id
                WHERE p.residente_id IS NULL
            """)
            result = self.cursor.fetchone()
            stats['visitantes']['ingresos'] = float(result['total']) if result else 0
            
            # Residentes que pagaron (si aplica)
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
# SISTEMA PRINCIPAL CON POSTGRESQL CORREGIDO
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
            'total_parqueaderos_visitantes': 5  # Total fijo de parqueaderos de visitantes
        }
    
    def crear_interfaz(self):
        """Crea la interfaz gráfica con tkinter"""
        self.ventana = tk.Tk()
        self.ventana.title("🚗 Sistema de Control de Acceso Vehicular - PostgreSQL")
        self.ventana.geometry("1400x1000")
        self.ventana.configure(bg='#ecf0f1')
        
        # Configurar estilos profesionales
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colores del tema
        color_primario = '#2c3e50'
        color_secundario = '#34495e'
        color_acento = '#3498db'
        color_fondo = '#ecf0f1'
        
        # Estilos para Notebook
        style.configure('TNotebook', background=color_fondo, borderwidth=0)
        style.configure('TNotebook.Tab', padding=[20, 10], font=('Arial', 10, 'bold'))
        style.map('TNotebook.Tab',
                  background=[('selected', color_acento)],
                  foreground=[('selected', 'white')])
        
        # Estilos para Frame
        style.configure('Title.TLabel', font=('Arial', 12, 'bold'), background=color_fondo)
        style.configure('Header.TLabel', font=('Arial', 16, 'bold'), background=color_primario, foreground='white')
        
        # Menú superior
        self.crear_menu_superior()
        
        # Header mejorado con gradiente visual
        header_frame = tk.Frame(self.ventana, bg=color_primario, height=110)
        header_frame.pack(fill='x')
        header_frame.pack_propagate(False)
        
        # Línea decorativa
        top_bar = tk.Frame(header_frame, bg='#e74c3c', height=4)
        top_bar.pack(fill='x')
        
        db_status = "PostgreSQL" if not self.usar_datos_memoria else "Memoria (Fallback)"
        header_label = tk.Label(header_frame, 
                                text=f"🚗 SISTEMA DE CONTROL DE ACCESO VEHICULAR",
                                font=('Arial', 16, 'bold'),
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
        
        # Frame de estadísticas mejorado - PRIMERO para máxima visibilidad
        self.crear_frame_estadisticas()
        
        # Notebook desactivado - Solo mostrar estadísticas
        # self.notebook = ttk.Notebook(self.ventana)
        # self.notebook.pack(fill='both', expand=True, padx=0, pady=0)
        
        # Crear pestañas desactivadas - Solo mostrar estadísticas
        # self.crear_pestana_entrada()
        # self.crear_pestana_salida()
        # self.crear_pestana_estado()
        # self.crear_pestana_visitantes()
        # self.crear_pestana_historial()
        # self.crear_pestana_consultas()
        
        # Footer con resumen detallado mejorado
        footer_frame = tk.Frame(self.ventana, bg=color_primario, relief='raised', bd=3, height=130)
        footer_frame.pack(fill='x', side='bottom', padx=0, pady=0)
        footer_frame.pack_propagate(False)
        
        # Línea superior del footer
        line_top = tk.Frame(footer_frame, bg='#e74c3c', height=3)
        line_top.pack(fill='x')
        
        # Título del resumen
        titulo_footer = tk.Label(footer_frame,
                                text="📊 RESUMEN DEL DÍA",
                                font=('Arial', 11, 'bold'),
                                bg=color_primario,
                                fg='#ecf0f1')
        titulo_footer.pack(pady=4)
        
        # Frame para los números con efecto de tarjetas
        numeros_frame = tk.Frame(footer_frame, bg=color_primario)
        numeros_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Crear labels para el resumen con diseño mejorado
        self.footer_labels = {}
        resumen_data = [
            ('total_parq', '🅿️ TOTAL', '#3498db'),
            ('disponibles', '🟢 LIBRES', '#27ae60'),
            ('ocupados', '🔴 OCUPADOS', '#e74c3c'),
            ('visitantes', '👥 VISITANTES', '#9b59b6'),
            ('recaudo', '💰 RECAUDO', '#f39c12')
        ]
        
        for i, (key, text, color) in enumerate(resumen_data):
            # Tarjeta de estadística
            card = tk.Frame(numeros_frame, bg=color, relief='raised', bd=2)
            card.pack(side='left', fill='both', expand=True, padx=4, pady=3)
            
            # Label de descripción con background
            desc_label = tk.Label(card, text=text, font=('Arial', 9, 'bold'), 
                                 bg=color, fg='white')
            desc_label.pack(pady=3)
            
            # Label del número
            self.footer_labels[key] = tk.Label(card, text="0", 
                                              font=('Arial', 15, 'bold'), 
                                              bg=color, 
                                              fg='white')
            self.footer_labels[key].pack(pady=2)
        
        # Línea de copyright
        copyright_label = tk.Label(footer_frame,
                                  text="© 2024 Sistema Control Vehicular | versión 2.0 PostgreSQL",
                                  font=('Arial', 8),
                                  bg=color_primario,
                                  fg='#95a5a6')
        copyright_label.pack(pady=2)
        
        # Cargar datos iniciales - Deshabilitado para modo de solo estadísticas
        # self.actualizar_lista_parqueaderos()
        # self.actualizar_todas_tablas()
        
        # Actualizar estadísticas cada segundo
        self.actualizar_estadisticas()
    
    def crear_menu_superior(self):
        """Crea el menú superior simplificado"""
        menubar = tk.Menu(self.ventana)
        self.ventana.config(menu=menubar)
        
        # Menú Archivo (simplificado)
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Archivo", menu=file_menu)
        # file_menu.add_command(label="Exportar Historial a CSV", command=self.exportar_historial)
        # file_menu.add_command(label="Ver Consultas SQL", command=self.mostrar_consultas_sql)
        # file_menu.add_separator()
        file_menu.add_command(label="Salir", command=self.ventana.quit)
    
    def crear_pestana_entrada(self):
        """Crea pestaña de registro de entrada"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🚗 Registrar Entrada")
        
        # Formulario con diseño mejorado
        form_frame = tk.Frame(frame, bg='#ecf0f1')
        form_frame.pack(padx=20, pady=20, fill='both', expand=True)
        
        # Contenedor principal con bordes redondeados (simulados)
        main_card = tk.Frame(form_frame, bg='white', relief='flat', bd=0)
        main_card.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Encabezado de la tarjeta
        card_header = tk.Frame(main_card, bg='#3498db', height=50)
        card_header.pack(fill='x')
        card_header.pack_propagate(False)
        
        tk.Label(card_header, text="📝 Registro de Entrada de Vehículo",
                font=('Arial', 13, 'bold'), bg='#3498db', fg='white').pack(pady=10)
        
        # Contenido de la tarjeta
        content_frame = tk.Frame(main_card, bg='white')
        content_frame.pack(fill='both', expand=True, padx=20, pady=15)
        
        # Campo placa
        tk.Label(content_frame, text="Número de Placa:", font=('Arial', 10, 'bold'), 
                bg='white', fg='#2c3e50').pack(pady=8, anchor='w')
        self.entry_placa_entrada = tk.Entry(content_frame, font=('Arial', 12), width=25,
                                           relief='solid', bd=1, bg='#f8f9fa', fg='#2c3e50')
        self.entry_placa_entrada.pack(pady=5, fill='x')
        self.entry_placa_entrada.bind('<FocusIn>', lambda e: self.entry_placa_entrada.config(bg='white'))
        self.entry_placa_entrada.bind('<FocusOut>', lambda e: self.entry_placa_entrada.config(bg='#f8f9fa'))
        
        # Botón verificar mejorado
        btn_verificar = tk.Button(content_frame, text="✓ Verificar si es Residente",
                                  command=self.verificar_placa,
                                  bg='#3498db', fg='white', font=('Arial', 10, 'bold'),
                                  relief='flat', bd=0, padx=15, pady=8,
                                  activebackground='#2980b9', activeforeground='white')
        btn_verificar.pack(pady=10, fill='x')
        
        # Panel visual de clasificación de la placa
        tk.Label(content_frame, text="Clasificación de Placa:", font=('Arial', 10, 'bold'), 
                bg='white', fg='#2c3e50').pack(pady=(15,5), anchor='w')
        
        # Contenedor de estado visual
        estado_visual_frame = tk.Frame(content_frame, bg='white')
        estado_visual_frame.pack(pady=5, fill='x')
        
        # Panel RESIDENTE
        self.panel_residente = tk.Frame(estado_visual_frame, bg='#d5f4e6', relief='solid', bd=2)
        self.panel_residente.pack(side='left', fill='both', expand=True, padx=5)
        tk.Label(self.panel_residente, text="👨‍💼 RESIDENTE", font=('Arial', 11, 'bold'), 
                bg='#27ae60', fg='white', relief='flat').pack(fill='x', pady=5)
        self.label_residente_info = tk.Label(self.panel_residente, text="N/A", 
                                            font=('Arial', 9), bg='#d5f4e6', fg='#27ae60')
        self.label_residente_info.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Panel VISITANTE
        self.panel_visitante = tk.Frame(estado_visual_frame, bg='#fdeaa8', relief='solid', bd=2)
        self.panel_visitante.pack(side='left', fill='both', expand=True, padx=5)
        tk.Label(self.panel_visitante, text="👥 VISITANTE", font=('Arial', 11, 'bold'), 
                bg='#f39c12', fg='white', relief='flat').pack(fill='x', pady=5)
        self.label_visitante_info = tk.Label(self.panel_visitante, text="N/A", 
                                            font=('Arial', 9), bg='#fdeaa8', fg='#e67e22')
        self.label_visitante_info.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Separador
        sep = tk.Frame(content_frame, bg='#ecf0f1', height=2)
        sep.pack(fill='x', pady=15)
        
        tk.Label(content_frame, text="Seleccionar Parqueadero para Visitante:", 
                font=('Arial', 10, 'bold'), bg='white', fg='#2c3e50').pack(pady=8, anchor='w')
        
        # Combobox mejorado
        self.parqueadero_var = tk.StringVar()
        self.parqueadero_combo = ttk.Combobox(content_frame, textvariable=self.parqueadero_var, 
                                             width=25, font=('Arial', 11), state='readonly')
        self.parqueadero_combo.pack(pady=5, fill='x')
        
        # Botón actualizar parqueaderos
        btn_actualizar_parq = tk.Button(content_frame, text="🔄 Actualizar Parqueaderos",
                                        command=self.actualizar_lista_parqueaderos,
                                        bg='#9b59b6', fg='white', font=('Arial', 10, 'bold'),
                                        relief='flat', bd=0, padx=15, pady=8,
                                        activebackground='#8e44ad', activeforeground='white')
        btn_actualizar_parq.pack(pady=10, fill='x')
        
        # Botón de registro principal
        btn_entrada = tk.Button(content_frame, text="✓ REGISTRAR ENTRADA",
                                command=self.registrar_entrada_gui,
                                bg='#27ae60', fg='white', font=('Arial', 12, 'bold'),
                                relief='flat', bd=0, padx=20, pady=12,
                                activebackground='#229954', activeforeground='white')
        btn_entrada.pack(pady=15, fill='x')
        
        # Área de resultados entrada
        tk.Label(content_frame, text="Estado:", font=('Arial', 9), 
                bg='white', fg='#7f8c8d').pack(pady=(10,5), anchor='w')
        self.resultado_entrada = tk.Text(content_frame, height=4, width=50, 
                                        font=('Arial', 10), relief='solid', bd=1,
                                        bg='#f0f8f5', fg='#27ae60')
        self.resultado_entrada.pack(pady=5, fill='both', expand=True)
    
    def crear_pestana_salida(self):
        """Crea pestaña de registro de salida"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🚪 Registrar Salida")
        
        # Formulario con diseño mejorado
        form_frame = tk.Frame(frame, bg='#ecf0f1')
        form_frame.pack(padx=20, pady=20, fill='both', expand=True)
        
        # Contenedor principal con bordes
        main_card = tk.Frame(form_frame, bg='white', relief='flat', bd=0)
        main_card.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Encabezado de la tarjeta
        card_header = tk.Frame(main_card, bg='#f39c12', height=50)
        card_header.pack(fill='x')
        card_header.pack_propagate(False)
        
        tk.Label(card_header, text="🚗 Registro de Salida de Vehículo",
                font=('Arial', 13, 'bold'), bg='#f39c12', fg='white').pack(pady=10)
        
        # Contenido de la tarjeta
        content_frame = tk.Frame(main_card, bg='white')
        content_frame.pack(fill='both', expand=True, padx=20, pady=15)
        
        # Campo placa con búsqueda
        tk.Label(content_frame, text="Número de Placa:", font=('Arial', 10, 'bold'), 
                bg='white', fg='#2c3e50').pack(pady=8, anchor='w')
        
        # Frame para placa y botón de búsqueda
        placa_frame = tk.Frame(content_frame, bg='white')
        placa_frame.pack(pady=5, fill='x')
        
        self.entry_placa_salida = tk.Entry(placa_frame, font=('Arial', 12), width=25,
                                          relief='solid', bd=1, bg='#f8f9fa', fg='#2c3e50')
        self.entry_placa_salida.pack(side='left', fill='both', expand=True, padx=(0, 5))
        self.entry_placa_salida.bind('<FocusIn>', lambda e: self.entry_placa_salida.config(bg='white'))
        self.entry_placa_salida.bind('<FocusOut>', lambda e: self.entry_placa_salida.config(bg='#f8f9fa'))
        
        btn_buscar_placa = tk.Button(placa_frame, text="🔍 Buscar",
                                     command=self.buscar_vehiculo_salida,
                                     bg='#3498db', fg='white', font=('Arial', 9, 'bold'),
                                     relief='flat', bd=0, padx=10, pady=5,
                                     activebackground='#2980b9', activeforeground='white')
        btn_buscar_placa.pack(side='right', padx=2)
        
        # Panel de información de tarifa
        tk.Label(content_frame, text="Información de Tarifa:", font=('Arial', 10, 'bold'), 
                bg='white', fg='#2c3e50').pack(pady=(15,5), anchor='w')
        
        tarifa_visual_frame = tk.Frame(content_frame, bg='white')
        tarifa_visual_frame.pack(pady=5, fill='x')
        
        # Panel RESIDENTE (sin tarifa)
        self.panel_salida_residente = tk.Frame(tarifa_visual_frame, bg='#d5f4e6', relief='solid', bd=2)
        self.panel_salida_residente.pack(side='left', fill='both', expand=True, padx=5)
        tk.Label(self.panel_salida_residente, text="👨‍💼 RESIDENTE", font=('Arial', 11, 'bold'), 
                bg='#27ae60', fg='white', relief='flat').pack(fill='x', pady=5)
        self.label_salida_residente = tk.Label(self.panel_salida_residente, text="Sin tarifa\n(Acceso gratuito)", 
                                              font=('Arial', 9), bg='#d5f4e6', fg='#27ae60')
        self.label_salida_residente.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Panel VISITANTE (con tarifa)
        self.panel_salida_visitante = tk.Frame(tarifa_visual_frame, bg='#fdeaa8', relief='solid', bd=2)
        self.panel_salida_visitante.pack(side='left', fill='both', expand=True, padx=5)
        tk.Label(self.panel_salida_visitante, text="👥 VISITANTE", font=('Arial', 11, 'bold'), 
                bg='#f39c12', fg='white', relief='flat').pack(fill='x', pady=5)
        self.label_salida_visitante = tk.Label(self.panel_salida_visitante, text="N/A", 
                                              font=('Arial', 9), bg='#fdeaa8', fg='#e67e22')
        self.label_salida_visitante.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Campo para tarifa a cobrar
        tk.Label(content_frame, text="Tarifa a Cobrar ($):", font=('Arial', 10, 'bold'), 
                bg='white', fg='#2c3e50').pack(pady=(15,5), anchor='w')
        
        tarifa_frame = tk.Frame(content_frame, bg='white')
        tarifa_frame.pack(pady=5, fill='x')
        
        self.entry_tarifa_salida = tk.Entry(tarifa_frame, font=('Arial', 12), width=20,
                                            relief='solid', bd=1, bg='#f8f9fa', fg='#2c3e50')
        self.entry_tarifa_salida.pack(side='left', fill='both', expand=True, padx=(0, 5))
        self.entry_tarifa_salida.bind('<FocusIn>', lambda e: self.entry_tarifa_salida.config(bg='white'))
        self.entry_tarifa_salida.bind('<FocusOut>', lambda e: self.entry_tarifa_salida.config(bg='#f8f9fa'))
        
        tk.Label(tarifa_frame, text="COP", font=('Arial', 11, 'bold'), 
                bg='white', fg='#2c3e50').pack(side='left', padx=5)
        
        # Frame para botones de acciones
        botones_frame = tk.Frame(content_frame, bg='white')
        botones_frame.pack(pady=15, fill='x')
        
        # Botón de liquidar y registrar salida (principal - más visible)
        btn_liquidar = tk.Button(botones_frame, text="💰 LIQUIDAR Y REGISTRAR SALIDA",
                                 command=self.liquidar_y_registrar_salida,
                                 bg='#16a085', fg='white', font=('Arial', 12, 'bold'),
                                 relief='flat', bd=0, padx=20, pady=12,
                                 activebackground='#138d75', activeforeground='white')
        btn_liquidar.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        # Botón de registrar salida (secundario)
        btn_salida = tk.Button(botones_frame, text="✓ REGISTRAR SALIDA",
                               command=self.registrar_salida_gui,
                               bg='#f39c12', fg='white', font=('Arial', 11, 'bold'),
                               relief='flat', bd=0, padx=15, pady=10,
                               activebackground='#e67e22', activeforeground='white')
        btn_salida.pack(side='left', fill='both', expand=True, padx=(5, 0))
        
        # Área de resultados
        tk.Label(content_frame, text="Detalles de Salida:", font=('Arial', 9), 
                bg='white', fg='#7f8c8d').pack(pady=(10,5), anchor='w')
        self.resultado_salida = tk.Text(content_frame, height=8, width=50, 
                                       font=('Arial', 10), relief='solid', bd=1,
                                       bg='#fef5e7', fg='#2c3e50')
        self.resultado_salida.pack(pady=5, fill='both', expand=True)
    
    def crear_pestana_estado(self):
        """Crea pestaña de estado de parqueaderos"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📊 Estado Parqueaderos")
        
        # Frame superior con título
        title_frame = tk.Frame(frame, bg='#34495e', height=50)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="📋 Estado de Parqueaderos | Todos los Datos",
                font=('Arial', 12, 'bold'), bg='#34495e', fg='white').pack(pady=10)
        
        # Crear treeview para mostrar estado con estilos
        columns = ('N°', 'Estado', 'Residente', 'Apartamento', 'Placa')
        self.tree_estado = ttk.Treeview(frame, columns=columns, show='headings', height=20)
        
        # Definir estilos para el treeview
        style = ttk.Style()
        style.configure('Treeview', rowheight=28, font=('Arial', 10))
        style.configure('Treeview.Heading', font=('Arial', 10, 'bold'))
        
        # Definir encabezados con anchos más grandes
        column_widths = [60, 120, 200, 120, 150]
        for col, width in zip(columns, column_widths):
            self.tree_estado.heading(col, text=col)
            self.tree_estado.column(col, width=width)
        
        # Scrollbars
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_estado.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree_estado.xview)
        self.tree_estado.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree_estado.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Frame para botones
        btn_frame = tk.Frame(frame, bg='#ecf0f1', height=60)
        btn_frame.pack(fill='x', side='bottom')
        btn_frame.pack_propagate(False)
        
        # Botón actualizar mejorado
        btn_actualizar = tk.Button(btn_frame, text="🔄 Actualizar Estado",
                                   command=self.actualizar_tabla_estado,
                                   bg='#3498db', fg='white', font=('Arial', 10, 'bold'),
                                   relief='flat', bd=0, padx=20, pady=10,
                                   activebackground='#2980b9', activeforeground='white')
        btn_actualizar.pack(pady=10)
    
    def crear_pestana_visitantes(self):
        """Crea pestaña de visitantes activos con diseño mejorado"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="👥 Visitantes Activos")
        
        # Frame superior con título
        title_frame = tk.Frame(frame, bg='#9b59b6', height=50)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="📋 Visitantes en Tiempo Real | Vehículos Activos",
                font=('Arial', 12, 'bold'), bg='#9b59b6', fg='white').pack(pady=10)
        
        # Crear treeview para visitantes activos
        columns = ('Placa', 'Hora Entrada', 'Parqueadero', 'Tiempo')
        self.tree_visitantes = ttk.Treeview(frame, columns=columns, show='headings', height=20)
        
        # Estilos para treeview
        style = ttk.Style()
        style.configure('Treeview', rowheight=28, font=('Arial', 10))
        style.configure('Treeview.Heading', font=('Arial', 10, 'bold'))
        
        # Definir anchos de columnas
        column_widths = [150, 180, 150, 120]
        for col, width in zip(columns, column_widths):
            self.tree_visitantes.heading(col, text=col)
            self.tree_visitantes.column(col, width=width)
        
        # Scrollbars
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_visitantes.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree_visitantes.xview)
        self.tree_visitantes.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree_visitantes.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Frame para botones
        btn_frame = tk.Frame(frame, bg='#ecf0f1', height=60)
        btn_frame.pack(fill='x', side='bottom')
        btn_frame.pack_propagate(False)
        
        # Botón actualizar mejorado
        btn_actualizar = tk.Button(btn_frame, text="🔄 Actualizar Lista",
                                   command=self.actualizar_tabla_visitantes,
                                   bg='#9b59b6', fg='white', font=('Arial', 10, 'bold'),
                                   relief='flat', bd=0, padx=20, pady=10,
                                   activebackground='#8e44ad', activeforeground='white')
        btn_actualizar.pack(pady=10)
    
    def crear_pestana_historial(self):
        """Crea pestaña de historial con diseño mejorado"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📜 Historial")
        
        # Frame superior con título
        title_frame = tk.Frame(frame, bg='#16a085', height=50)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="📋 Historial de Transacciones | Todas las Entradas y Salidas",
                font=('Arial', 12, 'bold'), bg='#16a085', fg='white').pack(pady=10)
        
        # Crear treeview para historial
        columns = ('ID', 'Placa', 'Entrada', 'Salida', 'Parq', 'Horas', 'Valor')
        self.tree_historial = ttk.Treeview(frame, columns=columns, show='headings', height=20)
        
        # Estilos para treeview
        style = ttk.Style()
        style.configure('Treeview', rowheight=28, font=('Arial', 10))
        style.configure('Treeview.Heading', font=('Arial', 10, 'bold'))
        
        # Definir anchos de columnas
        column_widths = [50, 120, 180, 180, 80, 90, 130]
        for col, width in zip(columns, column_widths):
            self.tree_historial.heading(col, text=col)
            self.tree_historial.column(col, width=width)
        
        # Scrollbars
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree_historial.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.tree_historial.xview)
        self.tree_historial.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree_historial.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')
        
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        
        # Frame para totales y botones
        footer_frame = tk.Frame(frame, bg='#ecf0f1', height=70)
        footer_frame.pack(fill='x', side='bottom')
        footer_frame.pack_propagate(False)
        
        self.total_recaudado_label = tk.Label(footer_frame, text="💰 Total Recaudado: $0 COP",
                                              font=('Arial', 12, 'bold'),
                                              bg='#f39c12', fg='white',
                                              padx=20, pady=10, relief='raised', bd=2)
        self.total_recaudado_label.pack(side='left', padx=10, pady=10)
        
        # Botones
        btn_actualizar = tk.Button(footer_frame, text="🔄 Actualizar",
                                   command=self.actualizar_tabla_historial,
                                   bg='#16a085', fg='white', font=('Arial', 10, 'bold'),
                                   relief='flat', bd=0, padx=20, pady=8,
                                   activebackground='#138d75', activeforeground='white')
        btn_actualizar.pack(side='right', padx=10, pady=10)
    
    def crear_pestana_consultas(self):
        """Crea pestaña para mostrar las consultas del archivo querys.sql con diseño mejorado"""
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📝 Consultas SQL")
        
        # Frame superior con título
        title_frame = tk.Frame(frame, bg='#34495e', height=50)
        title_frame.pack(fill='x')
        title_frame.pack_propagate(False)
        
        tk.Label(title_frame, text="💾 Consultas SQL | Base de Datos PostgreSQL",
                font=('Arial', 12, 'bold'), bg='#34495e', fg='white').pack(pady=10)
        
        # Frame para mostrar las consultas con mejor diseño
        queries_frame = tk.Frame(frame, bg='#ecf0f1')
        queries_frame.pack(padx=10, pady=10, fill='both', expand=True)
        
        # Texto con las consultas
        consultas_text = tk.Text(queries_frame, height=20, width=80, font=('Courier', 11),
                                relief='solid', bd=1, bg='#f8f9fa', fg='#2c3e50',
                                insertbackground='#3498db')
        consultas_text.pack(padx=10, pady=10, fill='both', expand=True)
        
        # Insertar las consultas del archivo
        consultas = """-- ═══════════════════════════════════════════════════════════════════════════
-- CONSULTAS CLAVE DEL SISTEMA DE CONTROL DE ACCESO VEHICULAR
-- ═══════════════════════════════════════════════════════════════════════════

-- 1️⃣  VERIFICAR SI LA PLACA ES RESIDENTE
SELECT r.nombre, p.numero AS parqueadero, p.estado
FROM placas pl
JOIN residentes r ON pl.residente_id = r.id
JOIN parqueaderos p ON p.residente_id = r.id
WHERE pl.placa = 'ABC123';

-- 2️⃣  REGISTRAR ENTRADA DE VISITANTE
INSERT INTO registros_visitantes (placa, parqueadero_id)
VALUES ('XYZ789', 3);

UPDATE parqueaderos
SET estado = 'OCUPADO'
WHERE id = 3;

-- 3️⃣  REGISTRAR SALIDA DE VISITANTE
UPDATE registros_visitantes
SET hora_salida = CURRENT_TIMESTAMP
WHERE id = 1;

UPDATE parqueaderos
SET estado = 'LIBRE'
WHERE id = 3;

-- 4️⃣  ESTATÍSTICAS GENERALES
SELECT COUNT(*) as total_parqueaderos FROM parqueaderos;
SELECT COUNT(*) as ocupados FROM parqueaderos WHERE estado = 'OCUPADO';

-- 5️⃣  HISTORIAL DE VISITANTES
SELECT placa, hora_entrada, hora_salida, total_horas, valor_pagado
FROM registros_visitantes
ORDER BY hora_entrada DESC;"""
        
        consultas_text.insert('1.0', consultas)
        consultas_text.config(state='disabled')
    
    def crear_frame_busqueda_placa(self):
        """Crea frame de búsqueda y registro de placa en la parte superior"""
        # Frame principal para búsqueda
        busqueda_frame = tk.Frame(self.ventana, bg='#ecf0f1', relief='raised', bd=2, height=180)
        busqueda_frame.pack(fill='x', padx=0, pady=0)
        busqueda_frame.pack_propagate(False)
        
        # Contenedor con padding
        contenedor = tk.Frame(busqueda_frame, bg='#ecf0f1')
        contenedor.pack(fill='both', expand=True, padx=15, pady=12)
        
        # Título
        titulo = tk.Label(contenedor, text="🔍 INGRESE PLACA DEL VEHÍCULO - ENTRADA/SALIDA", 
                         font=('Arial', 12, 'bold'), bg='#ecf0f1', fg='#2c3e50')
        titulo.pack(anchor='w', pady=(0, 8))
        
        # Frame para entrada y botón
        entrada_frame = tk.Frame(contenedor, bg='#ecf0f1')
        entrada_frame.pack(fill='x', pady=5)
        
        # Campo de entrada de placa
        tk.Label(entrada_frame, text="Placa:", font=('Arial', 10, 'bold'), 
                bg='#ecf0f1', fg='#2c3e50').pack(side='left', padx=(0, 10))
        
        self.entry_placa = tk.Entry(entrada_frame, font=('Arial', 13, 'bold'), 
                                    width=12, relief='solid', bd=2, 
                                    bg='white', fg='#2c3e50')
        self.entry_placa.pack(side='left', padx=5)
        self.entry_placa.bind('<Return>', lambda e: self.buscar_placa_entrada())
        self.entry_placa.bind('<FocusIn>', lambda e: self.entry_placa.config(bg='#fff9e6'))
        self.entry_placa.bind('<FocusOut>', lambda e: self.entry_placa.config(bg='white'))
        
        # Botón buscar
        btn_buscar = tk.Button(entrada_frame, text="🔍 Buscar", 
                              command=self.buscar_placa_entrada,
                              bg='#3498db', fg='white', font=('Arial', 10, 'bold'),
                              relief='flat', bd=0, padx=15, pady=5,
                              activebackground='#2980b9')
        btn_buscar.pack(side='left', padx=5)
        
        # Botón registrar entrada
        btn_registrar = tk.Button(entrada_frame, text="✅ REGISTRAR ENTRADA", 
                                 command=self.registrar_entrada_rapida,
                                 bg='#27ae60', fg='white', font=('Arial', 10, 'bold'),
                                 relief='flat', bd=0, padx=15, pady=5,
                                 activebackground='#229954')
        btn_registrar.pack(side='left', padx=5)
        
        # Botón limpiar
        btn_limpiar = tk.Button(entrada_frame, text="🗑️ Limpiar", 
                               command=lambda: self.entry_placa.delete(0, tk.END),
                               bg='#e74c3c', fg='white', font=('Arial', 10, 'bold'),
                               relief='flat', bd=0, padx=15, pady=5,
                               activebackground='#c0392b')
        btn_limpiar.pack(side='left', padx=5)
        
        # Frame de botones secundarios (adicionales)
        botones_secundarios_frame = tk.Frame(contenedor, bg='#ecf0f1')
        botones_secundarios_frame.pack(fill='x', pady=5)
        
        # Botón liquidar salida
        btn_liquidar_rapido = tk.Button(botones_secundarios_frame, text="💰 LIQUIDAR SALIDA", 
                                        command=self.abrir_ventana_liquidar,
                                        bg='#16a085', fg='white', font=('Arial', 10, 'bold'),
                                        relief='flat', bd=0, padx=15, pady=5,
                                        activebackground='#138d75')
        btn_liquidar_rapido.pack(side='left', padx=5)
        
        # Botón ver parqueaderos
        btn_ver_parqueaderos = tk.Button(botones_secundarios_frame, text="📊 VER PARQUEADEROS", 
                                         command=self.mostrar_estado_parqueaderos,
                                         bg='#8e44ad', fg='white', font=('Arial', 10, 'bold'),
                                         relief='flat', bd=0, padx=15, pady=5,
                                         activebackground='#7d3c98')
        btn_ver_parqueaderos.pack(side='left', padx=5)
        
        # Frame de resultado MEJORADO
        resultado_frame = tk.Frame(contenedor, bg='#ecf0f1')
        resultado_frame.pack(fill='x', pady=8)
        
        # Panel visual grande de resultado
        self.panel_resultado_placa = tk.Frame(resultado_frame, bg='#ecf0f1', relief='solid', bd=2)
        self.panel_resultado_placa.pack(fill='both', expand=True)
        
        # Información del resultado
        self.label_resultado_placa = tk.Label(self.panel_resultado_placa, 
                                             text="📝 Ingrese una placa y presione Buscar", 
                                             font=('Arial', 11, 'bold'), bg='#ecf0f1', 
                                             fg='#7f8c8d', relief='flat', bd=0, padx=15, pady=10)
        self.label_resultado_placa.pack(fill='both', expand=True)

    
    def buscar_placa_entrada(self):
        """Busca una placa en el sistema"""
        placa = self.entry_placa.get().upper().strip()
        
        if not placa:
            self.label_resultado_placa.config(text="⚠️ Por favor ingrese una placa", fg='#e74c3c')
            self.panel_resultado_placa.config(bg='#fadbd8')
            return
        
        try:
            if self.usar_datos_memoria:
                # Buscar en datos de memoria - LA PLACA ES LA CLAVE
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
                    texto = (f"👥 VISITANTE (NO REGISTRADO)\n"
                            f"Placa: {placa}\n"
                            f"Tipo: VISITANTE\n"
                            f"Acción: Presione REGISTRAR ENTRADA para ingresar")
                    self.label_resultado_placa.config(text=texto, fg='white')
                    self.panel_resultado_placa.config(bg='#f39c12')
            else:
                # Buscar en PostgreSQL
                if self.db and self.db.conectado:
                    self.db.cursor.execute(
                        "SELECT r.nombre, r.apartamento FROM placas p "
                        "JOIN residentes r ON p.residente_id = r.id "
                        "WHERE UPPER(p.placa) = %s",
                        (placa,)
                    )
                    resultado = self.db.cursor.fetchone()
                    
                    if resultado:
                        texto = (f"👨‍💼 RESIDENTE IDENTIFICADO\n"
                                f"Nombre: {resultado['nombre']}\n"
                                f"Apartamento: {resultado['apartamento']}\n"
                                f"Acción: Presione REGISTRAR ENTRADA para ingresar")
                        self.label_resultado_placa.config(text=texto, fg='white')
                        self.panel_resultado_placa.config(bg='#27ae60')
                    else:
                        texto = (f"👥 VISITANTE (NO REGISTRADO)\n"
                                f"Placa: {placa}\n"
                                f"Tipo: VISITANTE\n"
                                f"Acción: Presione REGISTRAR ENTRADA para ingresar")
                        self.label_resultado_placa.config(text=texto, fg='white')
                        self.panel_resultado_placa.config(bg='#f39c12')
                else:
                    self.label_resultado_placa.config(text="❌ Error: Sin conexión a base de datos", fg='#e74c3c')
                    self.panel_resultado_placa.config(bg='#fadbd8')
        except Exception as e:
            self.label_resultado_placa.config(text=f"❌ Error en búsqueda: {str(e)}", fg='#e74c3c')
            self.panel_resultado_placa.config(bg='#fadbd8')
    
    def registrar_entrada_rapida(self):
        """Registra la entrada del vehículo rápidamente"""
        placa = self.entry_placa.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        try:
            if self.usar_datos_memoria:
                # Registrar en memoria - Differenciando entre RESIDENTE y VISITANTE
                if placa in self.datos_memoria['residentes']:
                    # ES RESIDENTE - Actualizar estado a ocupado
                    residente = self.datos_memoria['residentes'][placa]
                    residente['estado'] = 'ocupado'
                    self.datos_memoria['historial_visitantes'].append({
                        'placa': placa,
                        'hora_entrada': datetime.now(),
                        'hora_salida': None,
                        'cobro': 0,
                        'tipo': 'RESIDENTE'
                    })
                    messagebox.showinfo("Éxito", f"✅ RESIDENTE ingresado:\n{residente['nombre']}\nParqueadero: {residente['parqueadero']}")
                    
                    # Actualizar panel con confirmación
                    self.label_resultado_placa.config(
                        text=(f"✅ ENTRADA REGISTRADA\n"
                              f"Tipo: RESIDENTE\n"
                              f"{residente['nombre']}\n"
                              f"Parqueadero: {residente['parqueadero']}"), 
                        fg='white'
                    )
                    self.panel_resultado_placa.config(bg='#16a085')
                else:
                    # ES VISITANTE - Agregar a visitantes activos
                    hora_entrada = datetime.now()
                    # Usar primer parqueadero disponible
                    if self.datos_memoria['parqueaderos_visitantes']:
                        parqueadero = self.datos_memoria['parqueaderos_visitantes'][0]
                        self.datos_memoria['visitantes_activos'][placa] = {
                            'hora_entrada': hora_entrada,
                            'parqueadero': parqueadero
                        }
                        self.datos_memoria['parqueaderos_visitantes'].remove(parqueadero)
                        self.datos_memoria['historial_visitantes'].append({
                            'placa': placa,
                            'hora_entrada': hora_entrada,
                            'hora_salida': None,
                            'cobro': 0,
                            'tipo': 'VISITANTE'
                        })
                        messagebox.showinfo("Éxito", f"✅ VISITANTE ingresado:\nPlaca: {placa}\nParqueadero: {parqueadero}")
                        
                        # Actualizar panel con confirmación
                        self.label_resultado_placa.config(
                            text=(f"✅ ENTRADA REGISTRADA\n"
                                  f"Tipo: VISITANTE\n"
                                  f"Placa: {placa}\n"
                                  f"Parqueadero: {parqueadero}"), 
                            fg='white'
                        )
                        self.panel_resultado_placa.config(bg='#16a085')
                    else:
                        messagebox.showwarning("Advertencia", "❌ No hay parqueaderos disponibles para visitantes")
                        return
                
                self.entry_placa.delete(0, tk.END)
                self.label_resultado_placa.config(text="Ingrese una placa para buscar...", 
                                                 fg='#7f8c8d', bg='#ecf0f1')
                # Actualizar estadísticas inmediatamente
                self.actualizar_estadisticas()
            else:
                # Registrar en PostgreSQL
                if self.db and self.db.conectado:
                    hora_entrada = datetime.now()
                    
                    # Verificar si es residente
                    self.db.cursor.execute(
                        "SELECT r.id FROM placas p "
                        "JOIN residentes r ON p.residente_id = r.id "
                        "WHERE UPPER(p.placa) = %s",
                        (placa,)
                    )
                    residente = self.db.cursor.fetchone()
                    
                    if residente:
                        # Es residente - registrar en registro_residentes
                        self.db.cursor.execute(
                            "INSERT INTO registro_residentes (residente_id, hora_entrada) "
                            "VALUES (%s, %s) RETURNING id",
                            (residente['id'], hora_entrada)
                        )
                        self.db.connection.commit()
                        messagebox.showinfo("Éxito", f"✅ Entrada registrada para RESIDENTE:\nPlaca: {placa}")
                    else:
                        # Es visitante - registrar en registro_visitantes
                        self.db.cursor.execute(
                            "INSERT INTO registros_visitantes (placa, hora_entrada) "
                            "VALUES (%s, %s) RETURNING id",
                            (placa, hora_entrada)
                        )
                        self.db.connection.commit()
                        messagebox.showinfo("Éxito", f"✅ Entrada registrada para VISITANTE:\nPlaca: {placa}")
                    
                    self.entry_placa.delete(0, tk.END)
                    self.label_resultado_placa.config(text="Ingrese una placa para buscar...", 
                                                     fg='#7f8c8d', bg='#ecf0f1')
                    # Actualizar estadísticas inmediatamente
                    self.actualizar_estadisticas()
                else:
                    messagebox.showerror("Error", "Sin conexión a la base de datos")
        except Exception as e:
            messagebox.showerror("Error", f"Error al registrar entrada: {str(e)}")
    
    def abrir_ventana_liquidar(self):
        """Abre ventana rápida para liquidar pago a visitante con cálculo automático"""
        ventana_liq = tk.Toplevel(self.ventana)
        ventana_liq.title("💰 Liquidar Pago de Visitante")
        ventana_liq.geometry("550x400")
        ventana_liq.resizable(False, False)
        ventana_liq.configure(bg='#ecf0f1')
        
        # Centrar ventana
        ventana_liq.transient(self.ventana)
        ventana_liq.grab_set()
        
        # Encabezado
        header = tk.Frame(ventana_liq, bg='#16a085', height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text="💰 LIQUIDAR PAGO", font=('Arial', 14, 'bold'), 
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
        entry_placa_liq.focus()
        
        # Frame de información calculada
        info_frame = tk.Frame(main_frame, bg='#fdeaa8', relief='solid', bd=2)
        info_frame.pack(fill='x', pady=(0, 15))
        
        tk.Label(info_frame, text="📊 CÁLCULO DE TARIFA", font=('Arial', 10, 'bold'),
                bg='#f39c12', fg='white', padx=10, pady=5).pack(fill='x')
        
        self.label_calculo_tiempo = tk.Label(info_frame, text="⏱️ Tiempo: --",
                                            font=('Arial', 10), bg='#fdeaa8', fg='#2c3e50',
                                            anchor='w', padx=15, pady=5)
        self.label_calculo_tiempo.pack(fill='x')
        
        self.label_calculo_tarifa = tk.Label(info_frame, text="💵 Tarifa: --",
                                            font=('Arial', 11, 'bold'), bg='#fdeaa8', fg='#27ae60',
                                            anchor='w', padx=15, pady=5)
        self.label_calculo_tarifa.pack(fill='x')
        
        self.label_calculo_tipo = tk.Label(info_frame, text="📌 Tipo: --",
                                          font=('Arial', 10), bg='#fdeaa8', fg='#2c3e50',
                                          anchor='w', padx=15, pady=(5, 10))
        self.label_calculo_tipo.pack(fill='x')
        
        # Variable para guardar la tarifa calculada
        tarifa_calculada = {'valor': 0}
        
        def calcular_tarifa():
            """Calcula la tarifa según tiempo estacionado"""
            placa = entry_placa_liq.get().upper().strip()
            
            if not placa:
                self.label_calculo_tiempo.config(text="⏱️ Tiempo: --")
                self.label_calculo_tarifa.config(text="💵 Tarifa: --")
                self.label_calculo_tipo.config(text="📌 Tipo: --")
                return
            
            if self.usar_datos_memoria:
                if placa in self.datos_memoria['visitantes_activos']:
                    hora_salida = datetime.now()
                    hora_entrada = self.datos_memoria['visitantes_activos'][placa]['hora_entrada']
                    
                    tiempo = hora_salida - hora_entrada
                    horas = tiempo.total_seconds() / 3600
                    
                    # Calcular tarifa
                    if horas <= 5:
                        cobro = int(np.ceil(horas)) * 1000
                        tipo = "Tarifa por hora"
                    else:
                        cobro = 10000
                        tipo = "Tarifa plena"
                    
                    tarifa_calculada['valor'] = cobro
                    
                    # Actualizar labels
                    self.label_calculo_tiempo.config(text=f"⏱️ Tiempo: {horas:.2f} horas")
                    self.label_calculo_tarifa.config(text=f"💵 Tarifa: ${cobro:,} COP")
                    self.label_calculo_tipo.config(text=f"📌 Tipo: {tipo}")
                else:
                    self.label_calculo_tiempo.config(text="⏱️ Tiempo: ❌ Placa no encontrada")
                    self.label_calculo_tarifa.config(text="💵 Tarifa: $0")
                    self.label_calculo_tipo.config(text="📌 Tipo: Error")
                    tarifa_calculada['valor'] = 0
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
                        
                        hora_salida = datetime.now()
                        tiempo = hora_salida - hora_entrada
                        horas = tiempo.total_seconds() / 3600
                        
                        if horas <= 5:
                            cobro = int(np.ceil(horas)) * 1000
                            tipo = "Tarifa por hora"
                        else:
                            cobro = 10000
                            tipo = "Tarifa plena"
                        
                        tarifa_calculada['valor'] = cobro
                        
                        self.label_calculo_tiempo.config(text=f"⏱️ Tiempo: {horas:.2f} horas")
                        self.label_calculo_tarifa.config(text=f"💵 Tarifa: ${cobro:,} COP")
                        self.label_calculo_tipo.config(text=f"📌 Tipo: {tipo}")
                    else:
                        self.label_calculo_tiempo.config(text="⏱️ Tiempo: ❌ Placa no encontrada")
                        self.label_calculo_tarifa.config(text="💵 Tarifa: $0")
                        self.label_calculo_tipo.config(text="📌 Tipo: Error")
                        tarifa_calculada['valor'] = 0
        
        # Bind para calcular cuando se ingresa placa
        entry_placa_liq.bind('<KeyRelease>', lambda e: calcular_tarifa())
        
        # Frame de botones
        btn_frame = tk.Frame(main_frame, bg='#ecf0f1')
        btn_frame.pack(fill='x', pady=10)
        
        def liquidar_confirmar():
            placa = entry_placa_liq.get().upper().strip()
            tarifa = tarifa_calculada['valor']
            
            if not placa:
                messagebox.showwarning("Advertencia", "❌ Ingrese una placa")
                return
            
            if tarifa == 0:
                messagebox.showerror("Error", "❌ Placa no válida o no encontrada")
                return
            
            if self.usar_datos_memoria:
                if placa in self.datos_memoria['visitantes_activos']:
                    # Proceder con liquidación
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
                    
                    # Actualizar vistas
                    self.actualizar_lista_parqueaderos()
                    self.actualizar_todas_tablas()
                    self.actualizar_estadisticas()
                    
                    messagebox.showinfo("✅ Cobro Exitoso", 
                                      f"Placa: {placa}\nCobro: ${tarifa:,} COP\n✅ Salida registrada")
                    ventana_liq.destroy()
                else:
                    messagebox.showerror("Error", f"❌ Visitante {placa} no está registrado")
            else:
                if self.db and self.db.conectado:
                    visitante = self.db.obtener_visitante_activo_por_placa(placa)
                    if visitante:
                        self.db.registrar_salida_visitante(visitante['id'], visitante['parqueadero_id'])
                        self.actualizar_lista_parqueaderos()
                        self.actualizar_todas_tablas()
                        self.actualizar_estadisticas()
                        messagebox.showinfo("✅ Cobro Exitoso", 
                                          f"Placa: {placa}\nCobro: ${tarifa:,} COP")
                        ventana_liq.destroy()
                    else:
                        messagebox.showerror("Error", f"❌ Visitante {placa} no registrado")
        
        btn_liquidar = tk.Button(btn_frame, text="✅ LIQUIDAR Y REGISTRAR SALIDA", 
                                 command=liquidar_confirmar,
                                 bg='#16a085', fg='white', font=('Arial', 11, 'bold'),
                                 relief='flat', bd=0, padx=20, pady=8,
                                 activebackground='#138d75')
        btn_liquidar.pack(side='left', fill='both', expand=True, padx=(0, 5))
        
        btn_cancelar = tk.Button(btn_frame, text="❌ Cancelar", 
                                 command=ventana_liq.destroy,
                                 bg='#e74c3c', fg='white', font=('Arial', 11, 'bold'),
                                 relief='flat', bd=0, padx=20, pady=8,
                                 activebackground='#c0392b')
        btn_cancelar.pack(side='left', fill='both', expand=True, padx=(5, 0))
    
    def mostrar_estado_parqueaderos(self):
        """Muestra ventana con estado de todos los parqueaderos numerados"""
        ventana_estado = tk.Toplevel(self.ventana)
        ventana_estado.title("📊 Estado de Parqueaderos")
        ventana_estado.geometry("700x600")
        ventana_estado.resizable(True, True)
        ventana_estado.configure(bg='#ecf0f1')
        
        # Centrar ventana
        ventana_estado.transient(self.ventana)
        ventana_estado.grab_set()
        
        # Encabezado
        header = tk.Frame(ventana_estado, bg='#8e44ad', height=50)
        header.pack(fill='x')
        header.pack_propagate(False)
        tk.Label(header, text="📊 ESTADO DE TODOS LOS PARQUEADEROS", font=('Arial', 14, 'bold'), 
                bg='#8e44ad', fg='white').pack(pady=10)
        
        # Frame con scroll
        canvas_frame = tk.Frame(ventana_estado, bg='#ecf0f1')
        canvas_frame.pack(fill='both', expand=True, padx=20, pady=15)
        
        # Canvas con scrollbar
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
            total_parq = total_parq_res + total_parq_vis
            
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
            
            # Visitantes ocupados
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
            
            # Visitantes disponibles
            for parq_num in self.datos_memoria['parqueaderos_visitantes']:
                card = tk.Frame(scrollable_frame, bg='#27ae60', relief='solid', bd=2)
                card.pack(fill='x', pady=5, padx=5)
                
                info_text = f"Parqueadero #{parq_num} | 🟢 LIBRE (disponible para visitante)"
                
                lbl = tk.Label(card, text=info_text, font=('Arial', 10), 
                              bg='#27ae60', fg='white', anchor='w', justify='left', padx=10, pady=8)
                lbl.pack(fill='x')
        else:
            # Modo PostgreSQL
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
        """Crea frame con estadísticas en tiempo real por tipo de parqueadero mejorado"""
        self.stats_frame = tk.Frame(self.ventana, bg='#2c3e50', relief='ridge', bd=3)
        self.stats_frame.pack(fill='x', padx=0, pady=0)
        
        # CONTENEDOR PRINCIPAL CON FONDO
        main_container = tk.Frame(self.stats_frame, bg='#34495e')
        main_container.pack(fill='x', padx=0, pady=0)
        
        # SECCIÓN DE RESIDENTES CON DISEÑO MEJORADO
        residentes_container = tk.Frame(main_container, bg='#34495e')
        residentes_container.pack(fill='x', padx=15, pady=12)
        
        residentes_label = tk.Label(residentes_container, text="👨‍💼 PARQUEADEROS RESIDENTES", 
                                     font=('Arial', 12, 'bold'), bg='#3498db', fg='white',
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
            
            label_titulo = tk.Label(card, text=text, font=('Arial', 10, 'bold'), bg=color, fg='white', pady=3)
            label_titulo.pack(fill='x')
            
            self.stats_labels[key] = tk.Label(card, text="0", font=('Arial', 16, 'bold'), 
                                             bg=color, fg='white', pady=5)
            self.stats_labels[key].pack(fill='x')
        
        # SECCIÓN DE VISITANTES
        visitantes_container = tk.Frame(main_container, bg='#34495e')
        visitantes_container.pack(fill='x', padx=15, pady=(0, 12))
        
        visitantes_label = tk.Label(visitantes_container, text="👥 PARQUEADEROS VISITANTES", 
                                    font=('Arial', 12, 'bold'), bg='#9b59b6', fg='white',
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
            
            label_titulo = tk.Label(card, text=text, font=('Arial', 10, 'bold'), bg=color, fg='white', pady=3)
            label_titulo.pack(fill='x')
            
            self.stats_labels[key] = tk.Label(card, text="0", font=('Arial', 16, 'bold'), 
                                             bg=color, fg='white', pady=5)
            self.stats_labels[key].pack(fill='x')
        
        # SECCIÓN DE TOTALES
        totales_container = tk.Frame(main_container, bg='#34495e')
        totales_container.pack(fill='x', padx=15, pady=(0, 12))
        
        totales_label = tk.Label(totales_container, text="📊 RESUMEN GENERAL", 
                                font=('Arial', 12, 'bold'), bg='#2c3e50', fg='white',
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
            
            label_titulo = tk.Label(card, text=text, font=('Arial', 10, 'bold'), bg=color, fg='white', pady=3)
            label_titulo.pack(fill='x')
            
            self.stats_labels[key] = tk.Label(card, text="0", font=('Arial', 16, 'bold'), 
                                             bg=color, fg='white', pady=5)
            self.stats_labels[key].pack(fill='x')
        
        # ===== SECCIÓN DE VEHÍCULOS ACTIVOS =====
        activos_container = tk.Frame(main_container, bg='#34495e')
        activos_container.pack(fill='x', padx=15, pady=(0, 12))
        
        activos_label = tk.Label(activos_container, text="🚗 VEHÍCULOS EN PARQUEADERO AHORA", 
                                font=('Arial', 12, 'bold'), bg='#34495e', fg='white',
                                relief='flat', bd=0, padx=10, pady=8)
        activos_label.pack(fill='x', padx=0, pady=(0, 8))
        
        # Frame para mostrar residentes ocupados
        residentes_activos_frame = tk.Frame(main_container, bg='#27ae60', relief='solid', bd=1)
        residentes_activos_frame.pack(fill='x', padx=15, pady=(0, 6))
        
        tk.Label(residentes_activos_frame, text="👨‍💼 RESIDENTES EN PARQUEADERO", 
                font=('Arial', 10, 'bold'), bg='#27ae60', fg='white', padx=10, pady=5).pack(fill='x')
        
        self.label_residentes_activos = tk.Label(residentes_activos_frame, text="• Ninguno", 
                                                 font=('Arial', 9), bg='#d5f4e6', fg='#27ae60', 
                                                 justify='left', padx=15, pady=8, relief='flat')
        self.label_residentes_activos.pack(fill='both', expand=True, padx=5, pady=5)
        
        # Frame para mostrar visitantes ocupados
        visitantes_activos_frame = tk.Frame(main_container, bg='#f39c12', relief='solid', bd=1)
        visitantes_activos_frame.pack(fill='x', padx=15, pady=(0, 12))
        
        tk.Label(visitantes_activos_frame, text="👥 VISITANTES EN PARQUEADERO", 
                font=('Arial', 10, 'bold'), bg='#f39c12', fg='white', padx=10, pady=5).pack(fill='x')
        
        self.label_visitantes_activos = tk.Label(visitantes_activos_frame, text="• Ninguno", 
                                                 font=('Arial', 9), bg='#fdeaa8', fg='#e67e22', 
                                                 justify='left', padx=15, pady=8, relief='flat')
        self.label_visitantes_activos.pack(fill='both', expand=True, padx=5, pady=5)
    
    # ============= FUNCIONES DE LA INTERFAZ =============
    
    def verificar_placa(self):
        """Verifica si una placa es de residente o visitante"""
        placa = self.entry_placa_entrada.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        # Resetear paneles
        self.label_residente_info.config(text="N/A", fg='#27ae60')
        self.label_visitante_info.config(text="N/A", fg='#e67e22')
        self.panel_residente.config(bg='#d5f4e6')
        self.panel_visitante.config(bg='#fdeaa8')
        
        es_residente = False
        
        if self.usar_datos_memoria:
            # Modo memoria
            if placa in self.datos_memoria['residentes']:
                res = self.datos_memoria['residentes'][placa]
                texto_residente = (f"✓ VERIFICADO\n"
                                 f"{res['nombre']}\n"
                                 f"Parq: {res['parqueadero']}\n"
                                 f"{res['estado'].upper()}")
                self.label_residente_info.config(text=texto_residente, fg='white')
                self.panel_residente.config(bg='#27ae60')
                es_residente = True
            else:
                self.label_visitante_info.config(text="✓ SIN REGISTRO\n(Ingrese como visitante)", fg='white')
                self.panel_visitante.config(bg='#f39c12')
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                resultado = self.db.verificar_placa_residente(placa)
                
                if resultado:
                    texto_residente = (f"✓ VERIFICADO\n"
                                     f"{resultado['nombre']}\n"
                                     f"Parq: {resultado['parqueadero']}\n"
                                     f"{resultado['estado']}")
                    self.label_residente_info.config(text=texto_residente, fg='white')
                    self.panel_residente.config(bg='#27ae60')
                    es_residente = True
                else:
                    self.label_visitante_info.config(text="✓ SIN REGISTRO\n(Ingrese como visitante)", fg='white')
                    self.panel_visitante.config(bg='#f39c12')
            else:
                messagebox.showerror("Error", "❌ No hay conexión a la base de datos")
                return
        
        # Actualizar lista de parqueaderos disponibles
        self.actualizar_lista_parqueaderos()
        
        # Habilitar o deshabilitar campos según sea residente o visitante
        if es_residente:
            self.parqueadero_combo.config(state='disabled')
            self.parqueadero_var.set("")
        else:
            self.parqueadero_combo.config(state='readonly')
    
    def actualizar_lista_parqueaderos(self):
        """Actualiza la lista de parqueaderos disponibles para visitantes"""
        disponibles = []
        
        if self.usar_datos_memoria:
            # Modo memoria
            disponibles = [str(p) for p in self.datos_memoria['parqueaderos_visitantes']]
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                parqueaderos = self.db.obtener_parqueaderos_libres_visitantes()
                disponibles = [str(p['numero']) for p in parqueaderos]
        
        self.parqueadero_combo['values'] = disponibles
        if disponibles:
            self.parqueadero_var.set(disponibles[0])
    
    def registrar_entrada_gui(self):
        """Maneja el registro de entrada desde la GUI"""
        placa = self.entry_placa_entrada.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        resultado = ""
        
        if self.usar_datos_memoria:
            # Modo memoria
            if placa in self.datos_memoria['residentes']:
                if self.datos_memoria['residentes'][placa]['estado'] == 'libre':
                    self.datos_memoria['residentes'][placa]['estado'] = 'ocupado'
                    resultado = f"✅ Acceso permitido - Residente {self.datos_memoria['residentes'][placa]['nombre']}"
                else:
                    resultado = f"⚠️ El residente ya tiene su parqueadero ocupado"
            else:
                if placa not in self.datos_memoria['visitantes_activos']:
                    if not self.parqueadero_var.get():
                        resultado = "❌ No hay parqueaderos disponibles para visitantes"
                    else:
                        parqueadero = int(self.parqueadero_var.get())
                        hora_entrada = datetime.now()
                        self.datos_memoria['visitantes_activos'][placa] = {
                            'hora_entrada': hora_entrada,
                            'parqueadero': parqueadero
                        }
                        if parqueadero in self.datos_memoria['parqueaderos_visitantes']:
                            self.datos_memoria['parqueaderos_visitantes'].remove(parqueadero)
                        resultado = f"✅ Acceso permitido - Visitante {placa} - Parqueadero {parqueadero}"
                else:
                    resultado = f"⚠️ El visitante ya se encuentra dentro"
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                residente = self.db.verificar_placa_residente(placa)
                
                if residente:
                    # Es residente
                    if residente['estado'] == 'LIBRE':
                        # Actualizar el estado del parqueadero del residente a OCUPADO
                        if self.db.marcar_parqueadero_ocupado(residente['parqueadero']):
                            resultado = f"✅ Acceso permitido - Residente {residente['nombre']} - Parqueadero {residente['parqueadero']}"
                        else:
                            resultado = f"❌ Error actualizando estado del parqueadero"
                    else:
                        resultado = f"⚠️ El residente ya tiene su parqueadero ocupado"
                else:
                    # Es visitante
                    if not self.parqueadero_var.get():
                        resultado = "❌ No hay parqueaderos disponibles para visitantes"
                    else:
                        parqueadero_num = int(self.parqueadero_var.get())
                        
                        # Obtener ID del parqueadero
                        parqueaderos = self.db.obtener_parqueaderos_libres_visitantes()
                        parqueadero_id = None
                        for p in parqueaderos:
                            if p['numero'] == parqueadero_num:
                                parqueadero_id = p['id']
                                break
                        
                        if parqueadero_id:
                            registro_id = self.db.registrar_entrada_visitante(placa, parqueadero_id)
                            if registro_id:
                                resultado = f"✅ Acceso permitido - Visitante {placa} - Parqueadero {parqueadero_num}"
                            else:
                                resultado = "❌ Error registrando entrada"
                        else:
                            resultado = "❌ Error seleccionando parqueadero"
            else:
                resultado = "❌ Error: No hay conexión a la base de datos"
        
        self.resultado_entrada.delete(1.0, tk.END)
        self.resultado_entrada.insert(tk.END, resultado)
        
        # Actualizar todas las vistas
        self.actualizar_lista_parqueaderos()
        self.actualizar_todas_tablas()
        self.actualizar_estadisticas()  # Actualizar estadísticas inmediatamente
        
        # Limpiar campo
        self.entry_placa_entrada.delete(0, tk.END)
    
    def buscar_tarifa_salida(self):
        """Busca y muestra la tarifa a pagar para la salida"""
        placa = self.entry_placa_salida.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        # Resetear paneles
        self.label_salida_residente.config(text="Sin tarifa\n(Acceso gratuito)", fg='#27ae60')
        self.label_salida_visitante.config(text="N/A", fg='#e67e22')
        self.panel_salida_residente.config(bg='#d5f4e6')
        self.panel_salida_visitante.config(bg='#fdeaa8')
        
        es_residente = False
        
        if self.usar_datos_memoria:
            # Modo memoria
            if placa in self.datos_memoria['residentes']:
                self.label_salida_residente.config(text="✓ Sin tarifa\n(Acceso gratuito)", fg='white')
                self.panel_salida_residente.config(bg='#27ae60')
                es_residente = True
            elif placa in self.datos_memoria['visitantes_activos']:
                hora_salida = datetime.now()
                hora_entrada = self.datos_memoria['visitantes_activos'][placa]['hora_entrada']
                
                tiempo = hora_salida - hora_entrada
                horas = tiempo.total_seconds() / 3600
                
                if horas <= 5:
                    cobro = int(np.ceil(horas)) * 1000
                    tipo = "Tarifa por hora"
                else:
                    cobro = 10000
                    tipo = "Tarifa plena"
                
                texto_visitante = (f"⏱️ Tiempo: {horas:.2f} hrs\n"
                                 f"💵 {tipo}\n"
                                 f"💰 Total: ${cobro:,}")
                self.label_salida_visitante.config(text=texto_visitante, fg='white')
                self.panel_salida_visitante.config(bg='#f39c12')
            else:
                self.label_salida_visitante.config(text="❌ Placa no registrada", fg='white')
                self.panel_salida_visitante.config(bg='#e74c3c')
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                residente = self.db.verificar_placa_residente(placa)
                
                if residente:
                    self.label_salida_residente.config(text="✓ Sin tarifa\n(Acceso gratuito)", fg='white')
                    self.panel_salida_residente.config(bg='#27ae60')
                    es_residente = True
                else:
                    # Es visitante - buscar información
                    visitante = self.db.obtener_visitante_activo_por_placa(placa)
                    
                    if visitante:
                        # Calcular tarifa
                        hora_entrada_str = visitante['hora_entrada']
                        
                        # Convertir a datetime si es string
                        if isinstance(hora_entrada_str, str):
                            try:
                                hora_entrada = datetime.fromisoformat(hora_entrada_str.replace('Z', '+00:00'))
                            except:
                                hora_entrada = datetime.strptime(hora_entrada_str, '%Y-%m-%d %H:%M:%S')
                        else:
                            hora_entrada = hora_entrada_str
                        
                        # Hacer naive si es aware
                        if hora_entrada.tzinfo is not None:
                            hora_entrada = hora_entrada.replace(tzinfo=None)
                        
                        hora_salida = datetime.now()
                        tiempo = hora_salida - hora_entrada
                        horas = tiempo.total_seconds() / 3600
                        
                        if horas <= 5:
                            cobro = int(np.ceil(horas)) * 1000
                            tipo = "Tarifa por hora"
                        else:
                            cobro = 10000
                            tipo = "Tarifa plena"
                        
                        texto_visitante = (f"⏱️ Tiempo: {horas:.2f} hrs\n"
                                         f"💵 {tipo}\n"
                                         f"💰 Total: ${cobro:,}")
                        self.label_salida_visitante.config(text=texto_visitante, fg='white')
                        self.panel_salida_visitante.config(bg='#f39c12')
                    else:
                        self.label_salida_visitante.config(text="❌ Placa no registrada", fg='white')
                        self.panel_salida_visitante.config(bg='#e74c3c')
            else:
                messagebox.showerror("Error", "❌ No hay conexión a la base de datos")
    
    def buscar_vehiculo_salida(self):
        """Busca el vehículo por placa y llena automáticamente la tarifa a cobrar"""
        placa = self.entry_placa_salida.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        # Resetear campos
        self.label_salida_residente.config(text="Sin tarifa\n(Acceso gratuito)", fg='#27ae60')
        self.label_salida_visitante.config(text="N/A", fg='#e67e22')
        self.panel_salida_residente.config(bg='#d5f4e6')
        self.panel_salida_visitante.config(bg='#fdeaa8')
        self.entry_tarifa_salida.delete(0, tk.END)
        
        if self.usar_datos_memoria:
            # Modo memoria
            if placa in self.datos_memoria['residentes']:
                self.label_salida_residente.config(text="✓ Sin tarifa\n(Acceso gratuito)", fg='white')
                self.panel_salida_residente.config(bg='#27ae60')
                self.entry_tarifa_salida.delete(0, tk.END)
                self.entry_tarifa_salida.insert(0, "0")
                messagebox.showinfo("Información", f"✓ Residente encontrado: {self.datos_memoria['residentes'][placa]['nombre']}\nAcceso gratuito")
            elif placa in self.datos_memoria['visitantes_activos']:
                hora_salida = datetime.now()
                hora_entrada = self.datos_memoria['visitantes_activos'][placa]['hora_entrada']
                
                tiempo = hora_salida - hora_entrada
                horas = tiempo.total_seconds() / 3600
                
                if horas <= 5:
                    cobro = int(np.ceil(horas)) * 1000
                    tipo = "Tarifa por hora"
                else:
                    cobro = 10000
                    tipo = "Tarifa plena"
                
                texto_visitante = (f"⏱️ Tiempo: {horas:.2f} hrs\n"
                                 f"💵 {tipo}\n"
                                 f"💰 Total: ${cobro:,}")
                self.label_salida_visitante.config(text=texto_visitante, fg='white')
                self.panel_salida_visitante.config(bg='#f39c12')
                self.entry_tarifa_salida.delete(0, tk.END)
                self.entry_tarifa_salida.insert(0, str(cobro))
                messagebox.showinfo("Información", f"✓ Visitante encontrado\nTarifa a cobrar: ${cobro:,} COP")
            else:
                self.label_salida_visitante.config(text="❌ Placa no registrada", fg='white')
                self.panel_salida_visitante.config(bg='#e74c3c')
                messagebox.showerror("Error", f"❌ Vehículo con placa {placa} no registrado en el sistema")
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                residente = self.db.verificar_placa_residente(placa)
                
                if residente:
                    self.label_salida_residente.config(text="✓ Sin tarifa\n(Acceso gratuito)", fg='white')
                    self.panel_salida_residente.config(bg='#27ae60')
                    self.entry_tarifa_salida.delete(0, tk.END)
                    self.entry_tarifa_salida.insert(0, "0")
                    messagebox.showinfo("Información", f"✓ Residente encontrado: {residente['nombre']}\nAcceso gratuito")
                else:
                    # Es visitante - buscar información
                    visitante = self.db.obtener_visitante_activo_por_placa(placa)
                    
                    if visitante:
                        # Calcular tarifa
                        hora_entrada_str = visitante['hora_entrada']
                        
                        # Convertir a datetime si es string
                        if isinstance(hora_entrada_str, str):
                            try:
                                hora_entrada = datetime.fromisoformat(hora_entrada_str.replace('Z', '+00:00'))
                            except:
                                hora_entrada = datetime.strptime(hora_entrada_str, '%Y-%m-%d %H:%M:%S')
                        else:
                            hora_entrada = hora_entrada_str
                        
                        # Hacer naive si es aware
                        if hora_entrada.tzinfo is not None:
                            hora_entrada = hora_entrada.replace(tzinfo=None)
                        
                        hora_salida = datetime.now()
                        tiempo = hora_salida - hora_entrada
                        horas = tiempo.total_seconds() / 3600
                        
                        if horas <= 5:
                            cobro = int(np.ceil(horas)) * 1000
                            tipo = "Tarifa por hora"
                        else:
                            cobro = 10000
                            tipo = "Tarifa plena"
                        
                        texto_visitante = (f"⏱️ Tiempo: {horas:.2f} hrs\n"
                                         f"💵 {tipo}\n"
                                         f"💰 Total: ${cobro:,}")
                        self.label_salida_visitante.config(text=texto_visitante, fg='white')
                        self.panel_salida_visitante.config(bg='#f39c12')
                        self.entry_tarifa_salida.delete(0, tk.END)
                        self.entry_tarifa_salida.insert(0, str(cobro))
                        messagebox.showinfo("Información", f"✓ Visitante encontrado\nTarifa a cobrar: ${cobro:,} COP")
                    else:
                        self.label_salida_visitante.config(text="❌ Placa no registrada", fg='white')
                        self.panel_salida_visitante.config(bg='#e74c3c')
                        messagebox.showerror("Error", f"❌ Vehículo con placa {placa} no registrado en el sistema")
            else:
                messagebox.showerror("Error", "❌ No hay conexión a la base de datos")
    
    def liquidar_y_registrar_salida(self):
        """Liquida el pago del visitante y registra la salida (acción final de cobro)"""
        placa = self.entry_placa_salida.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        # Verificar que sea visitante y tenga tarifa
        tarifa_str = self.entry_tarifa_salida.get().strip()
        if not tarifa_str:
            messagebox.showwarning("Advertencia", "Por favor ingrese la tarifa a cobrar")
            return
        
        try:
            cobro = int(tarifa_str)
        except ValueError:
            messagebox.showerror("Error", "La tarifa debe ser un número válido")
            return
        
        resultado = ""
        
        if self.usar_datos_memoria:
            # Modo memoria
            if placa in self.datos_memoria['residentes']:
                # NO se puede liquidar residente (acceso gratuito)
                messagebox.showwarning("Aviso", "❌ Los residentes no requieren liquidación (acceso gratuito)")
                return
            elif placa in self.datos_memoria['visitantes_activos']:
                # Visitante - proceder a cobro
                hora_salida = datetime.now()
                hora_entrada = self.datos_memoria['visitantes_activos'][placa]['hora_entrada']
                parqueadero = self.datos_memoria['visitantes_activos'][placa]['parqueadero']
                
                tiempo = hora_salida - hora_entrada
                horas = tiempo.total_seconds() / 3600
                
                if horas <= 5:
                    cobro_calculado = int(np.ceil(horas)) * 1000
                    tipo = "Tarifa por hora"
                else:
                    cobro_calculado = 10000
                    tipo = "Tarifa plena"
                
                # Registrar en historial con el cobro liquidado
                self.datos_memoria['historial_visitantes'].append({
                    'placa': placa,
                    'hora_entrada': hora_entrada,
                    'hora_salida': hora_salida,
                    'horas': round(horas, 2),
                    'cobro': cobro,  # Cobro liquidado (lo que realmente se cobró)
                    'tipo': tipo
                })
                
                # Devolver parqueadero
                self.datos_memoria['parqueaderos_visitantes'].append(parqueadero)
                del self.datos_memoria['visitantes_activos'][placa]
                
                # Mensaje de confirmación con recibo
                recibo = (f"═══════════════════════════════════════════\n"
                         f"          ✅ LIQUIDACIÓN COMPLETADA\n"
                         f"═══════════════════════════════════════════\n"
                         f"\n"
                         f"Placa: {placa}\n"
                         f"Hora entrada: {hora_entrada.strftime('%Y-%m-%d %H:%M:%S')}\n"
                         f"Hora salida: {hora_salida.strftime('%Y-%m-%d %H:%M:%S')}\n"
                         f"Tiempo estacionado: {horas:.2f} horas\n"
                         f"Parqueadero: {parqueadero}\n"
                         f"\n"
                         f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                         f"Tarifa calculada: ${cobro_calculado:,} ({tipo})\n"
                         f"Tarifa pagada: ${cobro:,} COP\n"
                         f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                         f"\n"
                         f"✅ Salida registrada y cobro liquidado\n"
                         f"═══════════════════════════════════════════")
                
                self.resultado_salida.delete(1.0, tk.END)
                self.resultado_salida.insert(tk.END, recibo)
                
                messagebox.showinfo("Cob Exitoso", f"✅ PAGO LIQUIDADO\n\nVisitante: {placa}\nCobro: ${cobro:,} COP")
            else:
                messagebox.showerror("Error", f"❌ Placa {placa} no registrada en el sistema")
                return
        else:
            # Modo PostgreSQL - similar lógica
            if self.db and self.db.conectado:
                residente = self.db.verificar_placa_residente(placa)
                
                if residente:
                    messagebox.showwarning("Aviso", "❌ Los residentes no requieren liquidación (acceso gratuito)")
                    return
                else:
                    visitante = self.db.obtener_visitante_activo_por_placa(placa)
                    
                    if visitante:
                        resultado_pago = self.db.registrar_salida_visitante(
                            visitante['id'], 
                            visitante['parqueadero_id']
                        )
                        
                        if resultado_pago:
                            recibo = (f"═══════════════════════════════════════════\n"
                                     f"          ✅ LIQUIDACIÓN COMPLETADA\n"
                                     f"═══════════════════════════════════════════\n"
                                     f"\n"
                                     f"Placa: {placa}\n"
                                     f"Tiempo estacionado: {resultado_pago['total_horas']:.2f} horas\n"
                                     f"\n"
                                     f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                     f"Cobro liquidado: ${cobro:,} COP\n"
                                     f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                                     f"\n"
                                     f"✅ Salida registrada y cobro liquidado\n"
                                     f"═══════════════════════════════════════════")
                            
                            self.resultado_salida.delete(1.0, tk.END)
                            self.resultado_salida.insert(tk.END, recibo)
                            messagebox.showinfo("Cobro Exitoso", f"✅ PAGO LIQUIDADO\n\nPlaca: {placa}\nCobro: ${cobro:,} COP")
                        else:
                            messagebox.showerror("Error", "❌ Error registrando salida")
                    else:
                        messagebox.showerror("Error", f"❌ Placa {placa} no registrada")
            else:
                messagebox.showerror("Error", "❌ No hay conexión a la base de datos")
                return
        
        # Actualizar todas las vistas tras cobro exitoso
        self.actualizar_lista_parqueaderos()
        self.actualizar_todas_tablas()
        self.actualizar_estadisticas()
        
        # Limpiar campos
        self.entry_placa_salida.delete(0, tk.END)
        self.entry_tarifa_salida.delete(0, tk.END)
    
    def registrar_salida_gui(self):
        """Maneja el registro de salida desde la GUI"""
        placa = self.entry_placa_salida.get().upper().strip()
        
        if not placa:
            messagebox.showwarning("Advertencia", "Por favor ingrese una placa")
            return
        
        # Verificar que la tarifa esté ingresada
        tarifa_str = self.entry_tarifa_salida.get().strip()
        if not tarifa_str:
            messagebox.showwarning("Advertencia", "Por favor ingrese la tarifa a cobrar")
            return
        
        try:
            cobro_manual = int(tarifa_str)
        except ValueError:
            messagebox.showerror("Error", "La tarifa debe ser un número válido")
            return
        
        resultado = ""
        
        if self.usar_datos_memoria:
            # Modo memoria
            if placa in self.datos_memoria['residentes']:
                self.datos_memoria['residentes'][placa]['estado'] = 'libre'
                resultado = f"✅ Salida registrada - Residente {self.datos_memoria['residentes'][placa]['nombre']}"
            elif placa in self.datos_memoria['visitantes_activos']:
                hora_salida = datetime.now()
                hora_entrada = self.datos_memoria['visitantes_activos'][placa]['hora_entrada']
                parqueadero = self.datos_memoria['visitantes_activos'][placa]['parqueadero']
                
                tiempo = hora_salida - hora_entrada
                horas = tiempo.total_seconds() / 3600
                
                if horas <= 5:
                    cobro_calculado = int(np.ceil(horas)) * 1000
                    tipo = "Tarifa por hora"
                else:
                    cobro_calculado = 10000
                    tipo = "Tarifa plena"
                
                # Usar tarifa manual si es diferente
                cobro = cobro_manual
                
                # Registrar en historial
                self.datos_memoria['historial_visitantes'].append({
                    'placa': placa,
                    'hora_entrada': hora_entrada,
                    'hora_salida': hora_salida,
                    'horas': round(horas, 2),
                    'cobro': cobro,
                    'tipo': tipo
                })
                
                # Devolver parqueadero
                self.datos_memoria['parqueaderos_visitantes'].append(parqueadero)
                del self.datos_memoria['visitantes_activos'][placa]
                
                resultado = (f"✅ Salida registrada - Visitante {placa}\n"
                           f"⏱️ Tiempo: {horas:.2f} horas\n"
                           f"💰 {tipo}\n"
                           f"💵 Total: ${cobro:,} COP")
            else:
                resultado = f"❌ Vehículo con placa {placa} no registrado"
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                residente = self.db.verificar_placa_residente(placa)
                
                if residente:
                    # Es residente - marcar parqueadero como LIBRE
                    if self.db.marcar_parqueadero_libre(residente['parqueadero']):
                        resultado = f"✅ Salida registrada - Residente {residente['nombre']} - Parqueadero {residente['parqueadero']} liberado"
                    else:
                        resultado = f"❌ Error actualizando estado del parqueadero"
                else:
                    # Es visitante
                    visitante = self.db.obtener_visitante_activo_por_placa(placa)
                    
                    if visitante:
                        resultado_pago = self.db.registrar_salida_visitante(
                            visitante['id'], 
                            visitante['parqueadero_id']
                        )
                        
                        if resultado_pago:
                            resultado = (f"✅ Salida registrada - Visitante {placa}\n"
                                       f"⏱️ Tiempo: {resultado_pago['total_horas']:.2f} horas\n"
                                       f"💵 Total registrado: ${cobro_manual:,} COP")
                        else:
                            resultado = "❌ Error registrando salida"
                    else:
                        resultado = f"❌ Vehículo con placa {placa} no registrado"
            else:
                resultado = "❌ Error: No hay conexión a la base de datos"
        
        self.resultado_salida.delete(1.0, tk.END)
        self.resultado_salida.insert(tk.END, resultado)
        
        # Actualizar todas las vistas
        self.actualizar_lista_parqueaderos()
        self.actualizar_todas_tablas()
        self.actualizar_estadisticas()  # Actualizar estadísticas inmediatamente
        
        # Limpiar campos
        self.entry_placa_salida.delete(0, tk.END)
        self.entry_tarifa_salida.delete(0, tk.END)
    
    def actualizar_tabla_estado(self):
        """Actualiza la tabla de estado de parqueaderos"""
        # Limpiar tabla
        for row in self.tree_estado.get_children():
            self.tree_estado.delete(row)
        
        if self.usar_datos_memoria:
            # Modo memoria
            for placa, datos in self.datos_memoria['residentes'].items():
                estado = "🔴 OCUPADO" if datos['estado'] == 'ocupado' else "🟢 LIBRE"
                self.tree_estado.insert('', 'end', values=(
                    f"{datos['parqueadero']}",
                    estado,
                    datos['nombre'],
                    datos['apartamento'],
                    placa
                ))
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                parqueaderos = self.db.obtener_estado_parqueaderos()
                
                for p in parqueaderos:
                    estado = "🔴 OCUPADO" if p['estado'] == 'OCUPADO' else "🟢 LIBRE"
                    residente = p['residente'] if p['residente'] else "-"
                    apartamento = p['apartamento'] if p['apartamento'] else "-"
                    placa = p['placa'] if p['placa'] else "-"
                    
                    self.tree_estado.insert('', 'end', values=(
                        p['numero'],
                        estado,
                        residente,
                        apartamento,
                        placa
                    ))
    
    def actualizar_tabla_visitantes(self):
        """Actualiza la tabla de visitantes activos"""
        # Limpiar tabla
        for row in self.tree_visitantes.get_children():
            self.tree_visitantes.delete(row)
        
        if self.usar_datos_memoria:
            # Modo memoria
            for placa, datos in self.datos_memoria['visitantes_activos'].items():
                tiempo = datetime.now() - datos['hora_entrada']
                horas = tiempo.total_seconds() / 3600
                
                self.tree_visitantes.insert('', 'end', values=(
                    placa,
                    datos['hora_entrada'].strftime('%H:%M:%S'),
                    f"P-{datos['parqueadero']}",
                    f"{horas:.1f} h"
                ))
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                visitantes = self.db.obtener_visitantes_activos()
                
                for v in visitantes:
                    # Manejar hora_entrada que puede venir como datetime o string
                    if isinstance(v['hora_entrada'], str):
                        # Si viene como string, convertir a datetime
                        try:
                            hora_entrada = datetime.fromisoformat(v['hora_entrada'].replace('Z', '+00:00'))
                        except:
                            hora_entrada = datetime.strptime(v['hora_entrada'], '%Y-%m-%d %H:%M:%S')
                    else:
                        hora_entrada = v['hora_entrada']
                    
                    tiempo = datetime.now(hora_entrada.tzinfo) - hora_entrada if hora_entrada.tzinfo else datetime.now() - hora_entrada
                    horas = tiempo.total_seconds() / 3600
                    
                    self.tree_visitantes.insert('', 'end', values=(
                        v['placa'],
                        hora_entrada.strftime('%H:%M:%S'),
                        f"P-{v['parqueadero']}",
                        f"{horas:.1f} h"
                    ))
    
    def actualizar_tabla_historial(self):
        """Actualiza la tabla de historial con toda la información"""
        # Limpiar tabla
        for row in self.tree_historial.get_children():
            self.tree_historial.delete(row)
        
        total = 0
        
        if self.usar_datos_memoria:
            # Modo memoria
            for idx, reg in enumerate(self.datos_memoria['historial_visitantes'], 1):
                self.tree_historial.insert('', 'end', values=(
                    str(idx),
                    reg['placa'],
                    reg['hora_entrada'].strftime('%Y-%m-%d %H:%M:%S'),
                    reg['hora_salida'].strftime('%Y-%m-%d %H:%M:%S'),
                    '-',
                    f"{reg['horas']:.2f}",
                    f"${reg['cobro']:,.0f}"
                ))
                total += reg['cobro']
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                historial = self.db.obtener_historial_visitantes(100)
                
                for reg in historial:
                    # Manejar diferentes formatos de datetime
                    if isinstance(reg['hora_entrada'], str):
                        try:
                            hora_entrada = datetime.fromisoformat(reg['hora_entrada'].replace('Z', '+00:00'))
                        except:
                            hora_entrada = datetime.strptime(reg['hora_entrada'], '%Y-%m-%d %H:%M:%S')
                    else:
                        hora_entrada = reg['hora_entrada']
                    
                    if reg['hora_salida']:
                        if isinstance(reg['hora_salida'], str):
                            try:
                                hora_salida = datetime.fromisoformat(reg['hora_salida'].replace('Z', '+00:00'))
                            except:
                                hora_salida = datetime.strptime(reg['hora_salida'], '%Y-%m-%d %H:%M:%S')
                        else:
                            hora_salida = reg['hora_salida']
                        hora_salida_str = hora_salida.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        hora_salida_str = '-'
                    
                    self.tree_historial.insert('', 'end', values=(
                        reg['id'],
                        reg['placa'],
                        hora_entrada.strftime('%Y-%m-%d %H:%M:%S'),
                        hora_salida_str,
                        f"P-{reg['parqueadero']}",
                        f"{reg['total_horas']:.2f}" if reg['total_horas'] else '-',
                        f"${reg['valor_pagado']:,.0f}" if reg['valor_pagado'] else '$0'
                    ))
                    if reg['valor_pagado']:
                        total += float(reg['valor_pagado'])
        
        self.total_recaudado_label.config(text=f"💰 Total Recaudado: ${total:,.0f} COP")
    
    def actualizar_estadisticas(self):
        """Actualiza las estadísticas en tiempo real por tipo de parqueadero"""
        if self.usar_datos_memoria:
            # Modo memoria
            total_residentes = len(self.datos_memoria['residentes'])
            # Total de parqueaderos de visitantes debe ser CONSTANTE (libres + ocupados)
            total_parqueaderos_visitantes = self.datos_memoria.get('total_parqueaderos_visitantes', 5)
            
            ocupados_residentes = sum(1 for r in self.datos_memoria['residentes'].values() if r['estado'] == 'ocupado')
            libres_residentes = total_residentes - ocupados_residentes
            
            # Visitantes
            ocupados_visitantes = len(self.datos_memoria['visitantes_activos'])
            libres_visitantes = total_parqueaderos_visitantes - ocupados_visitantes
            
            total = total_residentes + total_parqueaderos_visitantes
            total_historial = sum(r['cobro'] for r in self.datos_memoria['historial_visitantes'])
            
            # Actualizar labels de residentes
            self.stats_labels['residentes_total'].config(text=str(total_residentes))
            self.stats_labels['residentes_ocupados'].config(text=str(ocupados_residentes))
            self.stats_labels['residentes_libres'].config(text=str(libres_residentes))
            self.stats_labels['residentes_ingresos'].config(text="$0")
            
            # Actualizar labels de visitantes
            self.stats_labels['visitantes_total'].config(text=str(total_parqueaderos_visitantes))
            self.stats_labels['visitantes_ocupados'].config(text=str(ocupados_visitantes))
            self.stats_labels['visitantes_libres'].config(text=str(libres_visitantes))
            self.stats_labels['visitantes_activos'].config(text=str(ocupados_visitantes))
            
            # Actualizar totales
            self.stats_labels['total_parqueaderos'].config(text=str(total))
            self.stats_labels['total_ocupados'].config(text=str(ocupados_residentes + ocupados_visitantes))
            self.stats_labels['visitantes_ingresos'].config(text=f"${total_historial:,.0f}")
            
            # Actualizar footer
            libres_totales = libres_residentes + libres_visitantes
            self.footer_labels['total_parq'].config(text=str(total))
            self.footer_labels['disponibles'].config(text=str(libres_totales))
            self.footer_labels['ocupados'].config(text=str(ocupados_residentes + ocupados_visitantes))
            self.footer_labels['visitantes'].config(text=str(total_parqueaderos_visitantes))
            self.footer_labels['recaudo'].config(text=f"${total_historial:,.0f}")
            
            # ACTUALIZAR LISTADO DE VEHÍCULOS ACTIVOS
            # Residentes ocupados
            residentes_ocupados = [
                f"• {placa}: {datos['nombre']} (Apto {datos['apartamento']}) - Parqueadero {datos['parqueadero']}"
                for placa, datos in self.datos_memoria['residentes'].items() 
                if datos['estado'].lower() == 'ocupado'
            ]
            
            if residentes_ocupados:
                self.label_residentes_activos.config(text='\n'.join(residentes_ocupados))
            else:
                self.label_residentes_activos.config(text="• Ninguno")
            
            # Visitantes ocupados
            visitantes_ocupados = [
                f"• {placa} - Parqueadero {datos['parqueadero']}"
                for placa, datos in self.datos_memoria['visitantes_activos'].items()
            ]
            
            if visitantes_ocupados:
                self.label_visitantes_activos.config(text='\n'.join(visitantes_ocupados))
            else:
                self.label_visitantes_activos.config(text="• Ninguno")
        else:
            # Modo PostgreSQL
            if self.db and self.db.conectado:
                stats = self.db.obtener_estadisticas_por_tipo()
                
                # Residentes
                res_stats = stats['residentes']
                self.stats_labels['residentes_total'].config(text=str(res_stats['total']))
                self.stats_labels['residentes_ocupados'].config(text=str(res_stats['ocupados']))
                self.stats_labels['residentes_libres'].config(text=str(res_stats['libres']))
                self.stats_labels['residentes_ingresos'].config(text=f"${res_stats['ingresos']:,.0f}")
                
                # Visitantes
                vis_stats = stats['visitantes']
                self.stats_labels['visitantes_total'].config(text=str(vis_stats['total']))
                self.stats_labels['visitantes_ocupados'].config(text=str(vis_stats['ocupados']))
                self.stats_labels['visitantes_libres'].config(text=str(vis_stats['libres']))
                self.stats_labels['visitantes_activos'].config(text=str(vis_stats['activos']))
                
                # Totales
                total_parqueaderos = res_stats['total'] + vis_stats['total']
                total_ocupados = res_stats['ocupados'] + vis_stats['ocupados']
                total_libres = res_stats['libres'] + vis_stats['libres']
                self.stats_labels['total_parqueaderos'].config(text=str(total_parqueaderos))
                self.stats_labels['total_ocupados'].config(text=str(total_ocupados))
                self.stats_labels['visitantes_ingresos'].config(text=f"${vis_stats['ingresos']:,.0f}")
                
                # Obtener recaudo del día desde la base de datos
                general_stats = self.db.obtener_estadisticas()
                recaudo_hoy = general_stats['recaudado_hoy']
                
                # Actualizar footer
                self.footer_labels['total_parq'].config(text=str(total_parqueaderos))
                self.footer_labels['disponibles'].config(text=str(total_libres))
                self.footer_labels['ocupados'].config(text=str(total_ocupados))
                self.footer_labels['visitantes'].config(text=str(vis_stats['total']))
                self.footer_labels['recaudo'].config(text=f"${recaudo_hoy:,.0f}")
        
        # Actualizar cada 2 segundos
        self.ventana.after(2000, self.actualizar_estadisticas)
    
    def actualizar_todas_tablas(self):
        """Actualiza todas las tablas"""
        self.actualizar_tabla_estado()
        self.actualizar_tabla_visitantes()
        self.actualizar_tabla_historial()
    
    def exportar_historial(self):
        """Exporta el historial a CSV"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
        )
        
        if filename:
            if self.usar_datos_memoria:
                df = pd.DataFrame(self.datos_memoria['historial_visitantes'])
                df.to_csv(filename, index=False)
                messagebox.showinfo("Éxito", f"Historial exportado a: {filename}")
            else:
                if self.db and self.db.conectado:
                    historial = self.db.obtener_historial_visitantes(1000)
                    df = pd.DataFrame(historial)
                    df.to_csv(filename, index=False)
                    messagebox.showinfo("Éxito", f"Historial exportado a: {filename}")
    
    def mostrar_consultas_sql(self):
        """Muestra las consultas del archivo querys.sql"""
        messagebox.showinfo("Consultas SQL", 
                           "Las consultas están disponibles en la pestaña 'Consultas SQL'")
    
    def ejecutar(self):
        """Ejecuta la aplicación"""
        # Iniciar loop principal
        self.ventana.mainloop()
        
        # Cerrar conexión a la base de datos al salir
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
        # Solicitar configuración de PostgreSQL
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
        
        # Crear y ejecutar la aplicación
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