# On importe la fonction create_app définie dans le fichier __init__.py du dossier app
from app import create_app

# On importe l'objet db (SQLAlchemy)
from app.extensions import db

# On crée l'application Flask
app = create_app()



# Cette condition vérifie si ce fichier est exécuté directement
if __name__ == "__main__":

    # On démarre le serveur web Flask
    app.run(debug=True)