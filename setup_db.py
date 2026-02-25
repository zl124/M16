import sqlite3
import json
import os
from pyproj import Transformer

def setup_database():
    db_path = os.path.join(os.path.dirname(__file__), "geo_db.sqlite3")
    json_path = os.path.join(os.path.dirname(__file__), "data", "a.json")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. Create Tables
    print("Creating tables...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pontos_recolha (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            morada TEXT NOT NULL,
            horario TEXT,
            tipo_recolha TEXT,
            link TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            imagem TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'client',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 2. Import JSON Data
    if os.path.exists(json_path):
        print(f"Importing data from {json_path}...")
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        
        transformer = Transformer.from_crs("epsg:20790", "epsg:4326")

        count = 0
        for item in data:
            nome = item.get("TPRS_DESC", "Ponto de Recolha")
            morada = f"{item.get('TOP_MOD_1', '')}, {item.get('PRSL_LOCAL', '')}".strip(", ")
            tipo = item.get("TPRS_DESC", "")
            
            x = item.get("PRSL_X")
            y = item.get("PRSL_Y")

            if x is not None and y is not None:
                # Convert coordinates
                lat, lon = transformer.transform(x, y)
                
                cursor.execute("""
                    INSERT INTO pontos_recolha (nome, morada, tipo_recolha, latitude, longitude)
                    VALUES (?, ?, ?, ?, ?)
                """, (nome, morada, tipo, lat, lon))
                count += 1

        print(f"Imported {count} points.")
    else:
        print("JSON file not found.")

    conn.commit()
    conn.close()
    print("Database setup complete.")

if __name__ == "__main__":
    setup_database()