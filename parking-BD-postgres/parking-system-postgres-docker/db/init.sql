-- Crea  tablas

CREATE TABLE residentes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apartamento VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE parqueaderos (
    id SERIAL PRIMARY KEY,
    numero INTEGER UNIQUE NOT NULL,
    estado VARCHAR(10) CHECK (estado IN ('LIBRE','OCUPADO')) DEFAULT 'LIBRE',
    residente_id INTEGER UNIQUE,
    FOREIGN KEY (residente_id) REFERENCES residentes(id)
);

CREATE TABLE placas (
    id SERIAL PRIMARY KEY,
    residente_id INTEGER NOT NULL,
    placa VARCHAR(10) UNIQUE NOT NULL,
    FOREIGN KEY (residente_id) REFERENCES residentes(id) ON DELETE CASCADE
);

CREATE TABLE registros_visitantes (
    id SERIAL PRIMARY KEY,
    placa VARCHAR(10) NOT NULL,
    parqueadero_id INTEGER NOT NULL,
    hora_entrada TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    hora_salida TIMESTAMP,
    total_horas NUMERIC(5,2),
    valor_pagado NUMERIC(10,2),
    FOREIGN KEY (parqueadero_id) REFERENCES parqueaderos(id)
);

-- Función para calcular el pago

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

-- Trigger

CREATE TRIGGER trigger_calculo_pago
BEFORE UPDATE ON registros_visitantes
FOR EACH ROW
WHEN (NEW.hora_salida IS NOT NULL)
EXECUTE FUNCTION calcular_pago();
