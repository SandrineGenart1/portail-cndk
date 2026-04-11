import psycopg2
from flask import current_app

def get_db_connection():
    conn = psycopg2.connect(
        host=current_app.config["DB_HOST"],
        port=current_app.config["DB_PORT"],
        database=current_app.config["DB_NAME"],
        user=current_app.config["DB_USER"],
        password=current_app.config["DB_PASSWORD"]
    )
    return conn