# On importe la fonction create_app définie dans le fichier __init__.py du dossier app
# Cette fonction sert à créer et configurer l'application Flask
from app import create_app

# On crée l'application Flask en appelant la fonction create_app
app = create_app()

# Cette condition vérifie si ce fichier est exécuté directement
# (et pas simplement importé par un autre fichier)
if __name__ == "__main__":

    # On démarre le serveur web Flask
    # debug=True permet de voir les erreurs dans le navigateur et recharge automatiquement le serveur
    app.run(debug=True)