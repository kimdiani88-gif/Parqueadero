from sqlalchemy import create_engine

DATABASE_URL = "postgresql://parking_user:parking_pass@localhost:5432/parking_db"

engine = create_engine(DATABASE_URL)

with engine.connect() as connection:
    result = connection.execute("SELECT * FROM parqueaderos;")
    for row in result:
        print(row)
