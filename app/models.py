from app.extensions import db
from sqlalchemy.dialects.postgresql import ARRAY

#______Classe UtilisateurParent_____________
class UtilisateurParent(db.Model):
    __tablename__ = "utilisateurs_parents"

    id = db.Column(db.Integer, primary_key=True)
    prenom = db.Column(db.String(50), nullable=False)
    nom = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    actif = db.Column(db.Boolean, nullable=False, default=True)
    consentement_rgpd = db.Column(db.Boolean, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    liens_eleves = db.relationship(
        "ParentEleve",
        back_populates="parent",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<UtilisateurParent {self.prenom} {self.nom}>"

#______Classe UtilisateurStaff_____________
class UtilisateurStaff(db.Model):
    __tablename__ = "utilisateurs_staff"

    id = db.Column(db.Integer, primary_key=True)
    prenom = db.Column(db.String(50), nullable=False)
    nom = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    role = db.Column(db.String(30), nullable=False)
    actif = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    activites_creees = db.relationship("Activite", back_populates="createur")

    def __repr__(self):
        return f"<UtilisateurStaff {self.prenom} {self.nom} ({self.role})>"

#______Classe Eleve_____________
class Eleve(db.Model):
    __tablename__ = "eleves"

    __table_args__ = (
        db.UniqueConstraint("prenom", "nom", "classe", "annee_scolaire", name="uq_eleve_identite_scolaire"),
    )

    id = db.Column(db.Integer, primary_key=True)
    prenom = db.Column(db.String(50), nullable=False)
    nom = db.Column(db.String(50), nullable=False)
    classe = db.Column(db.String(10), nullable=False)
    option = db.Column(db.String(50))
    annee_scolaire = db.Column(db.String(20), nullable=False)
    actif = db.Column(db.Boolean, nullable=False, default=True)

    liens_parents = db.relationship(
        "ParentEleve",
        back_populates="eleve",
        cascade="all, delete-orphan"
    )

    activites_affectees = db.relationship(
        "ActiviteEleve",
        back_populates="eleve",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Eleve {self.prenom} {self.nom} ({self.classe})>"

#______Classe ParentEleve_____________
class ParentEleve(db.Model):
    __tablename__ = "parents_eleves"

    parent_id = db.Column(
        db.Integer,
        db.ForeignKey("utilisateurs_parents.id", ondelete="CASCADE"),
        primary_key=True
    )
    eleve_id = db.Column(
        db.Integer,
        db.ForeignKey("eleves.id", ondelete="CASCADE"),
        primary_key=True
    )
    relation = db.Column(db.String(30))

    parent = db.relationship("UtilisateurParent", back_populates="liens_eleves")
    eleve = db.relationship("Eleve", back_populates="liens_parents")

    def __repr__(self):
        return f"<ParentEleve parent={self.parent_id} eleve={self.eleve_id}>"

#______Classe Activités_____________
class Activite(db.Model):
    __tablename__ = "activites"

    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    montant = db.Column(db.Numeric(8, 2), nullable=False)
    date_limite_paiement = db.Column(db.Date, nullable=False)
    obligatoire = db.Column(db.Boolean, nullable=False, default=False)
    statut = db.Column(db.String(20), nullable=False, default="ouvert")
    created_by = db.Column(db.Integer, db.ForeignKey("utilisateurs_staff.id"))
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())
    options_cibles = db.Column(ARRAY(db.String))

    createur = db.relationship("UtilisateurStaff", back_populates="activites_creees")

    affectations = db.relationship(
        "ActiviteEleve",
        back_populates="activite",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Activite {self.titre}>"


class ActiviteEleve(db.Model):
    __tablename__ = "activites_eleves"

    id = db.Column(db.Integer, primary_key=True)
    activite_id = db.Column(
        db.Integer,
        db.ForeignKey("activites.id", ondelete="CASCADE"),
        nullable=False
    )
    eleve_id = db.Column(
        db.Integer,
        db.ForeignKey("eleves.id", ondelete="CASCADE"),
        nullable=False
    )
    montant_attendu = db.Column(db.Numeric(8, 2), nullable=False)
    statut = db.Column(db.String(20), nullable=False, default="en_attente")
    assigned_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    __table_args__ = (
        db.UniqueConstraint("activite_id", "eleve_id", name="uq_activite_eleve"),
    )

    activite = db.relationship("Activite", back_populates="affectations")
    eleve = db.relationship("Eleve", back_populates="activites_affectees")
    paiements = db.relationship(
        "PaiementActivite",
        back_populates="activite_eleve",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<ActiviteEleve activite={self.activite_id} eleve={self.eleve_id}>"


class PaiementActivite(db.Model):
    __tablename__ = "paiements_activites"

    id = db.Column(db.Integer, primary_key=True)
    activite_eleve_id = db.Column(
        db.Integer,
        db.ForeignKey("activites_eleves.id", ondelete="CASCADE"),
        nullable=False
    )
    montant = db.Column(db.Numeric(8, 2), nullable=False)
    statut = db.Column(db.String(20), nullable=False)
    mode_paiement = db.Column(db.String(30))
    ref_transaction = db.Column(db.String(100), unique=True)
    paye_le = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now())

    activite_eleve = db.relationship("ActiviteEleve", back_populates="paiements")

    def __repr__(self):
        return f"<PaiementActivite id={self.id} statut={self.statut}>"