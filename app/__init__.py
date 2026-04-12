# classe Flask qui permet de créer une application web
from flask import Flask

# On importe la configuration définie dans config.py
from config import Config

# On importe l'instance SQLAlchemy (notre "outil" pour accéder à la base de données)
from app.extensions import db


# Cette fonction va créer et configurer l'application Flask
# C'est le point d'entrée de notre application
def create_app():

    # Création de l'application Flask
    # __name__ permet à Flask de savoir où se trouvent les fichiers (templates, static, etc.)
    app = Flask(__name__)

    # On applique la configuration définie dans config.py
    # Cela inclut :
    # - la connexion à la base de données
    # - la clé secrète
    # - les variables liées à Mollie
    app.config.from_object(Config)

    # On initialise SQLAlchemy avec notre application Flask
    # Cela permet à SQLAlchemy de :
    # - se connecter à la base de données
    # - utiliser la configuration (URI, etc.)
    # - être utilisé dans tout le projet (modèles, routes...)
    db.init_app(app)

    # On importe les routes (les pages du site)
    # Important : on importe ici pour éviter des problèmes de dépendances circulaires
    from app.routes import main

    # On enregistre ces routes dans l'application
    # Blueprint = permet de structurer l'application en modules (plus propre)
    app.register_blueprint(main)

    # On retourne l'application configurée
    # Elle sera utilisée par run.py pour démarrer le serveur
    return app