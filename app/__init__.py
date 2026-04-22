# classe Flask qui permet de créer une application web
from flask import Flask

# On importe la configuration définie dans config.py
from config import Config

# On importe l'instance SQLAlchemy (notre "outil" pour accéder à la base de données)
from app.extensions import db

# On importe la classe Migrate depuis la bibliothèque flask_migrate.
# Flask-Migrate est une extension qui ajoute la commande "flask db" au terminal.
# Sans cet import, la commande "flask db migrate" n'existe pas
# et Flask ne sait pas gérer les changements de structure de la base de données
from flask_migrate import Migrate



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

   # On crée une instance de Migrate en lui passant deux paramètres :
#   - app : l'application Flask (pour qu'il sache dans quel projet il travaille)
#   - db  : l'instance SQLAlchemy (pour qu'il puisse lire les modèles
#            et comparer avec la base de données réelle)
#
# Concrètement, cette ligne fait trois choses :
#   1. Active la commande "flask db" dans le terminal
#   2. Relie Flask-Migrate à aux modèles SQLAlchemy (models.py)
#   3. Relie Flask-Migrate à la base de données PostgreSQL
#
# Sans cette ligne, même si flask_migrate est installé,
# la commande "flask db" reste introuvable.
    Migrate(app, db)

    # On importe les routes (les pages du site)
    # Important : on importe ici pour éviter des problèmes de dépendances circulaires
    from app.routes import main

    # On enregistre ces routes dans l'application
    # Blueprint = permet de structurer l'application en modules (plus propre)
    app.register_blueprint(main)

    # On retourne l'application configurée
    # Elle sera utilisée par run.py pour démarrer le serveur
    return app