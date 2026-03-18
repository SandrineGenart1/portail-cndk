from flask import Blueprint
from app.db import get_db_connection

main = Blueprint("main", __name__)

@main.route("/")
def index():
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT current_database(), current_user;")
        result = cur.fetchone()

        cur.close()
        conn.close()

        return f"Connexion réussie à la base : {result[0]} avec l'utilisateur : {result[1]}"

    except Exception as e:
        return f"Erreur de connexion : {e}"