# 💰 Configuración de Tarifas - Sistema de Parqueaderos

## Fórmula de Cálculo Implementada

### Tarifa para Visitantes

**Regla 1: Tarifa por Hora (hasta 5 horas)**
```
Cobro = TECHO(horas) × $1.000
```

**Regla 2: Tarifa Plena (más de 5 horas)**
```
Cobro = $10.000 (fijo)
```

---

## Ejemplos de Cálculo

| Tiempo Estacionado | Cálculo | Tarifa |
|---|---|---|
| 15 minutos (0.25h) | TECHO(0.25) × 1000 | **$1.000** |
| 30 minutos (0.50h) | TECHO(0.50) × 1000 | **$1.000** |
| 1 hora | TECHO(1.0) × 1000 | **$1.000** |
| 1.5 horas | TECHO(1.5) × 1000 | **$2.000** |
| 2 horas | TECHO(2.0) × 1000 | **$2.000** |
| 2.5 horas | TECHO(2.5) × 1000 | **$3.000** |
| 3 horas | TECHO(3.0) × 1000 | **$3.000** |
| 4 horas | TECHO(4.0) × 1000 | **$4.000** |
| 4.5 horas | TECHO(4.5) × 1000 | **$5.000** |
| 5 horas | TECHO(5.0) × 1000 | **$5.000** |
| 5.1 horas | > 5 horas | **$10.000** ⚠️ |
| 6 horas | > 5 horas | **$10.000** ⚠️ |
| 10 horas | > 5 horas | **$10.000** ⚠️ |
| 24 horas | > 5 horas | **$10.000** ⚠️ |

---

## Características del Sistema

### 📋 Residentes
- **Tarifa:** GRATUITO (Acceso libre)
- **Nota:** No se cobra a residentes

### 👥 Visitantes
- **Tarifa:** Según tiempo estacionado (fórmula arriba)
- **Mínimo:** $1.000 (cualquier tiempo)
- **Máximo:** $10.000 (tarifa plena a partir de 5+ horas)

---

## Funciones de Liquidación

### 1️⃣ Botón "LIQUIDAR SALIDA" (Rápido)
```
Ubicación: Frame de búsqueda de placa (segunda fila)
Acción:
  1. Ingresa placa → Sistema busca visitante
  2. Calcula tiempo automáticamente
  3. Muestra tarifa estimada
  4. Presiona "LIQUIDAR Y REGISTRAR SALIDA"
  5. Cobra y cierra sesión
```

**Pantalla de cálculo:**
```
════════════════════════════════════════════════
                  💰 LIQUIDAR PAGO
════════════════════════════════════════════════
Placa del Visitante: [XYZ789          ]

📊 CÁLCULO DE TARIFA
───────────────────────────────────────────────
⏱️ Tiempo: 2.45 horas
💵 Tarifa: $3.000 COP
📌 Tipo: Tarifa por hora
───────────────────────────────────────────────

[✅ LIQUIDAR Y REGISTRAR SALIDA] [❌ Cancelar]
════════════════════════════════════════════════
```

### 2️⃣ Función `buscar_vehiculo_salida()`
```
Ubicación: Pestaña "Registrar Salida" (cuando existe)
Acción:
  1. Busca placa en el sistema
  2. Calcula tiempo y muestra tarifa
  3. Permite ajustar tarifa si es necesario
  4. Botón LIQUIDAR Y REGISTRAR SALIDA
```

---

## Código Implementado

### En `abrir_ventana_liquidar()`
```python
# Cálculo automático al ingresar placa
if horas <= 5:
    cobro = int(np.ceil(horas)) * 1000
    tipo = "Tarifa por hora"
else:
    cobro = 10000
    tipo = "Tarifa plena"

# Muestra en labels:
# ⏱️ Tiempo: {horas:.2f} horas
# 💵 Tarifa: ${cobro:,} COP
# 📌 Tipo: {tipo}
```

### En `buscar_vehiculo_salida()`
```python
# Misma fórmula para consistencia
if horas <= 5:
    cobro = int(np.ceil(horas)) * 1000
    tipo = "Tarifa por hora"
else:
    cobro = 10000
    tipo = "Tarifa plena"
```

---

## Flujo de Liquidación (Visitante)

```
┌─────────────────────┐
│ Visitante Entra     │
│ Placa: XYZ789       │
│ Hora: 14:00         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Se asigna           │
│ Parqueadero #6      │
│ Entrada: 14:00      │
└──────────┬──────────┘
           │
    (tiempo pasa)
           │
           ▼
┌─────────────────────┐
│ Click: LIQUIDAR     │
│ Ingresa placa XYZ   │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────┐
│ Sistema calcula:             │
│ • Hora salida: 16:45         │
│ • Tiempo: 2:45 h (2.75h)     │
│ • Tarifa: CEIL(2.75)×1000    │
│ • Cobro: $3.000 COP          │
└──────────┬───────────────────┘
           │
           ▼
┌──────────────────────────────┐
│ CONFIRMA LIQUIDACIÓN         │
│ • Registro en historial      │
│ • Parqueadero 6 → LIBRE      │
│ • Cobro registrado: $3.000   │
│ • Estadísticas actualizadas  │
└──────────────────────────────┘
```

---

## Test de Validación

Ejecutar para verificar:
```bash
python test_tarifa_calculo.py
```

**Resultado esperado:** ✅ TODOS LOS TESTS PASARON

---

## Notas Importantes

⚠️ **Tarifa Plena:**
- Se activa a partir de **5+ horas** (5.1 horas en adelante)
- Máximo fijo: **$10.000** COP

✅ **Cálculo Automático:**
- El sistema calcula automáticamente al buscar placa
- Muestra estimación antes de cobrar
- Usuario puede confirmar o ajustar

✅ **Historial:**
- Cada liquidación se registra con:
  - Placa
  - Hora entrada/salida
  - Tiempo estacionado
  - Cobro realizado
  - Tipo de tarifa

---

**Versión:** 2.2 | **Fecha:** 17/02/2026 | **Estado:** ✅ Implementado y Probado
