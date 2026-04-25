from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Instance SQLAlchemy — gère la connexion à PostgreSQL
db = SQLAlchemy()

# Instance LoginManager — gère les sessions utilisateurs
# Configuré dans create_app() via login_manager.init_app(app)
login_manager = LoginManager()

# Page de redirection si l'utilisateur n'est pas connecté
# Pointe vers la route de login qu'on va créer
login_manager.login_view = "main.login"

# Message affiché quand on redirige vers le login
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "erreur"