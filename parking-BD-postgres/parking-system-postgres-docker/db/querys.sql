--Consultas Clave del Sistema

-- verifica si la placa es residente 

SELECT r.nombre, p.numero AS parqueadero, pr.estado
FROM placas pl
JOIN residentes r ON pl.residente_id = r.id
JOIN parqueaderos p ON p.residente_id = r.id
JOIN parqueaderos pr ON pr.id = p.id
WHERE pl.placa = 'ABC123';



--registra entrada de visitante 

INSERT INTO registros_visitantes (placa, parqueadero_id)
VALUES ('XYZ789', 3);

UPDATE parqueaderos
SET estado = 'OCUPADO'
WHERE id = 3;


--registra salida de visitante 

UPDATE registros_visitantes
SET hora_salida = CURRENT_TIMESTAMP
WHERE id = 1;

UPDATE parqueaderos
SET estado = 'LIBRE'
WHERE id = 3;

