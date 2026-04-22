# app/forms.py
# Définition des formulaires WTForms pour la validation des données
# et la protection CSRF des formulaires POST.

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, DateField, BooleanField
from wtforms.validators import DataRequired, NumberRange, ValidationError
from datetime import date


class ActiviteForm(FlaskForm):
    """Formulaire de création d'une activité scolaire."""

    titre = StringField("Titre", validators=[
        DataRequired(message="Le titre est obligatoire.")
    ])

    description = TextAreaField("Description")  # Optionnel, pas de validator

    montant = DecimalField("Montant", validators=[
        DataRequired(message="Le montant est obligatoire."),
        NumberRange(min=0.01, message="Le montant doit être positif.")
    ])

    date_limite_paiement = DateField("Date limite", validators=[
        DataRequired(message="La date limite est obligatoire.")
    ])

    obligatoire = BooleanField("Obligatoire")  # Case à cocher, toujours valide

    def validate_date_limite_paiement(self, field):
        """Validation personnalisée : la date ne peut pas être dans le passé."""
        if field.data and field.data < date.today():
            raise ValidationError("La date limite ne peut pas être dans le passé.")