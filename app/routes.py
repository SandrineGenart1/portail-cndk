import csv
import io

from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file
from werkzeug.datastructures import ImmutableMultiDict
from sqlalchemy import func, case

from app.extensions import db
from app.models import (
    ParentEleve, Eleve, Activite, ActiviteEleve, PaiementActivite
)
from app.qr_service import generer_qr_code_base64, generer_qr_code_png

main = Blueprint("main", __name__)


# ─────────────────────────────────────────────────────────────
# TABLEAU DE BORD ADMIN
# ─────────────────────────────────────────────────────────────

@main.route("/admin")
def admin_dashboard():
    """Tableau de bord avec statistiques globales."""

    nb_activites_ouvertes = (
        db.session.query(func.count(Activite.id))
        .filter(Activite.statut == "ouvert")
        .scalar()
    )

    nb_en_attente = (
        db.session.query(func.count(ActiviteEleve.id))
        .filter(ActiviteEleve.statut == "en_attente")
        .scalar()
    )

    row = (
        db.session.query(
            func.count(PaiementActivite.id),
            func.coalesce(func.sum(PaiementActivite.montant), 0)
        )
        .filter(PaiementActivite.statut == "paye")
        .filter(
            func.date_trunc("month", PaiementActivite.paye_le)
            == func.date_trunc("month", func.now())
        )
        .first()
    )

    stats = {
        "nb_activites_ouvertes": nb_activites_ouvertes,
        "nb_en_attente": nb_en_attente,
        "nb_payes": row[0],
        "montant_encaisse": f"{float(row[1]):.2f}",
    }

    return render_template(
        "admin_dashboard.html",
        stats=stats,
        role="admin",
        active="dashboard",
        current_user_name="Administrateur (test)"
    )


# ─────────────────────────────────────────────────────────────
# ESPACE PARENT
# ─────────────────────────────────────────────────────────────

@main.route("/")
def index():
    """Liste des activités liées aux enfants du parent connecté."""

    parent_id = 1  # TODO : flask_login.current_user.id

    lignes = (
        ActiviteEleve.query
        .join(Eleve, ActiviteEleve.eleve_id == Eleve.id)
        .join(Activite, ActiviteEleve.activite_id == Activite.id)
        .join(ParentEleve, ParentEleve.eleve_id == Eleve.id)
        .filter(ParentEleve.parent_id == parent_id)
        .order_by(Eleve.nom, Eleve.prenom)
        .all()
    )

    return render_template(
        "index.html",
        lignes=lignes,
        role="parent",
        active="accueil",
        current_user_name="Parent (test)"
    )


# ─────────────────────────────────────────────────────────────
# QR CODE — PAIEMENT PAR VIREMENT
# ─────────────────────────────────────────────────────────────

@main.route("/mon-qrcode/<int:activite_eleve_id>")
def mon_qrcode(activite_eleve_id):
    """
    Page QR code EPC + instructions de virement pour le parent.
    Remplace l'ancienne page confirmation_paiement.
    """

    parent_id = 1  # TODO : flask_login.current_user.id

    # Sécurité : vérification que l'activité appartient à un enfant du parent
    ae = (
        ActiviteEleve.query
        .join(Eleve, ActiviteEleve.eleve_id == Eleve.id)
        .join(ParentEleve, ParentEleve.eleve_id == Eleve.id)
        .filter(ActiviteEleve.id == activite_eleve_id)
        .filter(ParentEleve.parent_id == parent_id)
        .first()
    )

    if ae is None:
        flash("Activité introuvable ou accès non autorisé.", "erreur")
        return redirect(url_for("main.index"))

    if ae.statut == "paye":
        flash("Cette activité est déjà payée.", "info")
        return redirect(url_for("main.index"))

    # Génération du QR code en base64 pour affichage inline dans le template
    qr_b64, reference = generer_qr_code_base64(
        activite_id=ae.activite_id,
        eleve_id=ae.eleve_id,
        montant=float(ae.montant_attendu),
        description=ae.activite.titre
    )

    return render_template(
        "mon_qrcode.html",
        ae=ae,
        qr_b64=qr_b64,
        reference=reference,
        role="parent",
        active="accueil",
        current_user_name="Parent (test)"
    )


@main.route("/qrcode-image/<int:activite_eleve_id>")
def qrcode_image(activite_eleve_id):
    """
    Retourne l'image PNG du QR code pour téléchargement direct.
    Utilisé par le bouton "Télécharger" dans mon_qrcode.html.
    """

    parent_id = 1  # TODO : flask_login.current_user.id

    ae = (
        ActiviteEleve.query
        .join(Eleve, ActiviteEleve.eleve_id == Eleve.id)
        .join(ParentEleve, ParentEleve.eleve_id == Eleve.id)
        .filter(ActiviteEleve.id == activite_eleve_id)
        .filter(ParentEleve.parent_id == parent_id)
        .first()
    )

    if ae is None:
        return "Non autorisé", 403

    png_bytes, _ = generer_qr_code_png(
        activite_id=ae.activite_id,
        eleve_id=ae.eleve_id,
        montant=float(ae.montant_attendu),
        description=ae.activite.titre
    )

    return send_file(
        io.BytesIO(png_bytes),
        mimetype="image/png",
        download_name=f"paiement_{activite_eleve_id}.png"
    )


# ─────────────────────────────────────────────────────────────
# BACK-OFFICE ADMIN — PAIEMENTS
# ─────────────────────────────────────────────────────────────

@main.route("/admin/paiements")
def admin_paiements():
    """Liste de toutes les activités-élèves avec leur statut de paiement."""

    lignes = (
        ActiviteEleve.query
        .join(Eleve, ActiviteEleve.eleve_id == Eleve.id)
        .join(Activite, ActiviteEleve.activite_id == Activite.id)
        .order_by(ActiviteEleve.statut, Eleve.nom, Eleve.prenom)
        .all()
    )

    return render_template(
        "admin_paiements.html",
        lignes=lignes,
        role="admin",
        active="paiements",
        current_user_name="Administrateur (test)"
    )


@main.route("/admin/marquer-paye/<int:activite_eleve_id>", methods=["POST"])
def admin_marquer_paye(activite_eleve_id):
    """Valide manuellement un virement bancaire reçu par le secrétariat."""

    ligne = ActiviteEleve.query.get(activite_eleve_id)

    if ligne is None:
        flash("Activité introuvable.", "erreur")
        return redirect(url_for("main.admin_paiements"))

    if ligne.statut == "paye":
        flash("Cette activité est déjà marquée comme payée.", "info")
        return redirect(url_for("main.admin_paiements"))

    paiement = PaiementActivite(
        activite_eleve_id=ligne.id,
        montant=ligne.montant_attendu,
        statut="paye",
        mode_paiement="virement",
        ref_transaction=f"VIR-{ligne.id}",
        paye_le=db.func.now()
    )
    db.session.add(paiement)
    ligne.statut = "paye"
    db.session.commit()

    flash("Virement validé et paiement enregistré.", "succes")
    return redirect(url_for("main.admin_paiements"))


# ─────────────────────────────────────────────────────────────
# BACK-OFFICE ADMIN — ACTIVITÉS
# ─────────────────────────────────────────────────────────────

@main.route("/admin/activites")
def admin_activites():
    """Liste des activités avec comptage des paiements reçus."""

    activites = (
        db.session.query(
            Activite.id,
            Activite.titre,
            Activite.montant,
            Activite.date_limite_paiement,
            Activite.statut,
            func.count(ActiviteEleve.id).label("nb_total"),
            func.count(
                case((ActiviteEleve.statut == "paye", 1))
            ).label("nb_payes")
        )
        .outerjoin(ActiviteEleve, ActiviteEleve.activite_id == Activite.id)
        .group_by(Activite.id)
        .order_by(Activite.date_limite_paiement.desc())
        .all()
    )

    return render_template(
        "admin_activites.html",
        activites=activites,
        role="admin",
        active="activites",
        current_user_name="Administrateur (test)"
    )


@main.route("/admin/activites/nouvelle", methods=["GET", "POST"])
def admin_nouvelle_activite():
    """
    GET  : formulaire de création d'activité
    POST : crée l'activité et affecte les élèves des classes sélectionnées
    """

    classes_dispo = [
        row[0]
        for row in (
            db.session.query(Eleve.classe)
            .filter(Eleve.actif == True)
            .distinct()
            .order_by(Eleve.classe)
            .all()
        )
    ]

    if request.method == "POST":
        titre          = request.form.get("titre", "").strip()
        description    = request.form.get("description", "").strip() or None
        montant_str    = request.form.get("montant", "").strip()
        date_limite    = request.form.get("date_limite_paiement", "").strip()
        obligatoire    = request.form.get("obligatoire") == "on"
        classes_cibles = request.form.getlist("classes")

        # ── Validation ──────────────────────────────────────────
        erreurs = []
        if not titre:
            erreurs.append("Le titre est obligatoire.")
        if not montant_str:
            erreurs.append("Le montant est obligatoire.")
        else:
            try:
                montant = float(montant_str)
                if montant <= 0:
                    erreurs.append("Le montant doit être positif.")
            except ValueError:
                erreurs.append("Le montant doit être un nombre.")
        if not date_limite:
            erreurs.append("La date limite est obligatoire.")
        if not classes_cibles:
            erreurs.append("Sélectionnez au moins une classe.")

        if erreurs:
            for e in erreurs:
                flash(e, "erreur")
            return render_template(
                "admin_nouvelle_activite.html",
                classes_dispo=classes_dispo,
                form_data=request.form,
                role="admin",
                active="nouvelle_activite",
                current_user_name="Administrateur (test)"
            )

        # ── Création de l'activité ───────────────────────────────
        activite = Activite(
            titre=titre,
            description=description,
            montant=montant,
            date_limite_paiement=date_limite,
            obligatoire=obligatoire,
            statut="ouvert"
        )
        db.session.add(activite)
        db.session.flush()  # récupère l'id sans commit

        # ── Affectation aux élèves des classes choisies ──────────
        eleves = (
            Eleve.query
            .filter(Eleve.classe.in_(classes_cibles))
            .filter(Eleve.actif == True)
            .all()
        )

        nb_affectes = 0
        for eleve in eleves:
            existe = ActiviteEleve.query.filter_by(
                activite_id=activite.id,
                eleve_id=eleve.id
            ).first()
            if not existe:
                ae = ActiviteEleve(
                    activite_id=activite.id,
                    eleve_id=eleve.id,
                    montant_attendu=montant,
                    statut="en_attente"
                )
                db.session.add(ae)
                nb_affectes += 1

        db.session.commit()

        flash(
            f"Activité « {titre} » créée et affectée à "
            f"{nb_affectes} élève(s) dans les classes : "
            f"{', '.join(classes_cibles)}.",
            "succes"
        )
        return redirect(url_for("main.admin_activites"))

    # GET
    return render_template(
        "admin_nouvelle_activite.html",
        classes_dispo=classes_dispo,
        form_data=ImmutableMultiDict(),
        role="admin",
        active="nouvelle_activite",
        current_user_name="Administrateur (test)"
    )


# ─────────────────────────────────────────────────────────────
# IMPORT CSV ÉLÈVES
# ─────────────────────────────────────────────────────────────

@main.route("/admin/eleves/importer", methods=["GET", "POST"])
def admin_importer_eleves():
    """
    Import CSV des élèves en début d'année scolaire.
    Format attendu : prenom,nom,classe,option,annee_scolaire
    """

    ctx = {
        "role": "admin",
        "active": "import_eleves",
        "current_user_name": "Administrateur (test)"
    }

    if request.method == "GET":
        return render_template("admin_importer_eleves.html", **ctx)

    fichier = request.files.get("fichier_csv")

    if not fichier or fichier.filename == "":
        flash("Aucun fichier sélectionné.", "erreur")
        return render_template("admin_importer_eleves.html", **ctx)

    if not fichier.filename.lower().endswith(".csv"):
        flash("Le fichier doit être au format .csv", "erreur")
        return render_template("admin_importer_eleves.html", **ctx)

    try:
        contenu = fichier.read().decode("utf-8-sig")
        lecteur = csv.DictReader(io.StringIO(contenu))

        colonnes_requises = {"prenom", "nom", "classe", "annee_scolaire"}
        if not colonnes_requises.issubset(set(lecteur.fieldnames or [])):
            manquantes = colonnes_requises - set(lecteur.fieldnames or [])
            flash(
                f"Colonnes manquantes : {', '.join(manquantes)}. "
                "Colonnes attendues : prenom, nom, classe, option, annee_scolaire",
                "erreur"
            )
            return render_template("admin_importer_eleves.html", **ctx)

        lignes = list(lecteur)

    except UnicodeDecodeError:
        flash(
            "Erreur d'encodage. Enregistrez le fichier en UTF-8 "
            "(Excel : Enregistrer sous → CSV UTF-8).",
            "erreur"
        )
        return render_template("admin_importer_eleves.html", **ctx)

    if not lignes:
        flash("Le fichier CSV est vide.", "erreur")
        return render_template("admin_importer_eleves.html", **ctx)

    # ── Import via SQLAlchemy ────────────────────────────────────
    nb_inseres    = 0
    nb_mis_a_jour = 0
    nb_erreurs    = 0
    erreurs_detail = []

    try:
        for i, ligne in enumerate(lignes, start=2):
            prenom         = ligne.get("prenom", "").strip()
            nom            = ligne.get("nom", "").strip()
            classe         = ligne.get("classe", "").strip()
            option         = ligne.get("option", "").strip() or None
            annee_scolaire = ligne.get("annee_scolaire", "").strip()

            if not all([prenom, nom, classe, annee_scolaire]):
                nb_erreurs += 1
                erreurs_detail.append(
                    f"Ligne {i} ignorée — champs obligatoires manquants : "
                    f"{prenom!r}, {nom!r}, {classe!r}, {annee_scolaire!r}"
                )
                continue

            eleve = Eleve.query.filter_by(
                prenom=prenom,
                nom=nom,
                classe=classe,
                annee_scolaire=annee_scolaire
            ).first()

            if eleve is None:
                eleve = Eleve(
                    prenom=prenom,
                    nom=nom,
                    classe=classe,
                    option=option,
                    annee_scolaire=annee_scolaire,
                    actif=True
                )
                db.session.add(eleve)
                nb_inseres += 1
            else:
                eleve.option = option
                eleve.actif = True
                nb_mis_a_jour += 1

        db.session.commit()

    except Exception as e:
        db.session.rollback()
        flash(f"Erreur lors de l'import : {str(e)}", "erreur")
        return render_template("admin_importer_eleves.html", **ctx)

    if nb_inseres > 0 or nb_mis_a_jour > 0:
        flash(
            f"Import terminé : {nb_inseres} élève(s) ajouté(s), "
            f"{nb_mis_a_jour} élève(s) mis à jour.",
            "succes"
        )
    if nb_erreurs > 0:
        flash(f"{nb_erreurs} ligne(s) ignorée(s).", "erreur")
        for detail in erreurs_detail[:5]:
            flash(detail, "erreur")

    return redirect(url_for("main.admin_importer_eleves"))
