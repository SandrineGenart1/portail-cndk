import csv
import io
import os

from app.bob50_service import generer_fichiers_bob50
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, Response

from werkzeug.datastructures import ImmutableMultiDict
from sqlalchemy import func, case

from app.extensions import db
from app.models import (
    ParentEleve, Eleve, Activite, ActiviteEleve, PaiementActivite
)
from app.qr_service import generer_qr_code_base64, generer_qr_code_png

from app.forms import ActiviteForm    # Formulaire WTForms pour la création d'activité

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
        ecole_nom=os.getenv("NOM_BENEFICIAIRE", ""),
        ecole_iban=os.getenv("IBAN", ""),
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
    GET  : affiche le formulaire de création d'activité
    POST : valide via WTForms, crée l'activité et affecte les élèves
    """

    # Récupération des classes actives pour les cases à cocher
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

    form = ActiviteForm()

    if form.validate_on_submit():
        # Récupération des classes cochées (pas géré par WTForms car liste dynamique)
        classes_cibles = request.form.getlist("classes")

        if not classes_cibles:
            flash("Sélectionnez au moins une classe.", "erreur")
            return render_template(
                "admin_nouvelle_activite.html",
                classes_dispo=classes_dispo,
                form=form,
                role="admin",
                active="nouvelle_activite",
                current_user_name="Administrateur (test)"
            )

        # Création de l'activité avec les données validées par WTForms
        activite = Activite(
            titre=form.titre.data,
            description=form.description.data or None,
            montant=form.montant.data,
            date_limite_paiement=form.date_limite_paiement.data,
            obligatoire=form.obligatoire.data,
            statut="ouvert"
        )
        db.session.add(activite)
        db.session.flush()  # Récupère l'id sans commit

        # Affectation aux élèves des classes sélectionnées
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
                    montant_attendu=form.montant.data,
                    statut="en_attente"
                )
                db.session.add(ae)
                nb_affectes += 1

        db.session.commit()

        flash(
            f"Activité « {form.titre.data} » créée et affectée à "
            f"{nb_affectes} élève(s) dans les classes : "
            f"{', '.join(classes_cibles)}.",
            "succes"
        )
        return redirect(url_for("main.admin_activites"))

    # GET ou formulaire invalide : affichage du formulaire
    return render_template(
        "admin_nouvelle_activite.html",
        classes_dispo=classes_dispo,
        form=form,
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
            option          = ligne.get("option", "").strip() or None
            annee_scolaire  = ligne.get("annee_scolaire", "").strip()
            matricule_fase  = ligne.get("matricule_fase", "").strip() or None

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
                    matricule_fase=matricule_fase,
                    actif=True
                )
                db.session.add(eleve)
                nb_inseres += 1
            else:
                eleve.option = option
                eleve.actif = True
                eleve.matricule_fase = matricule_fase
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
# ─────────────────────────────────────────────────────────────
# EXPORT PAIEMENTS — À ajouter dans routes.py
# ─────────────────────────────────────────────────────────────
# Ajouter en haut de routes.py si pas déjà présent :
#   import csv
#   import io
#   from datetime import datetime
#   from flask import Response


@main.route("/admin/export")
def admin_export():
    """
    Page d'export : affiche les filtres et un aperçu des résultats.
    Les filtres sont passés via les paramètres GET de l'URL.
    """

    # ── Récupération des filtres depuis l'URL ────────────────
    activite_id  = request.args.get("activite_id", "")
    classe       = request.args.get("classe", "")
    statut       = request.args.get("statut", "paye")   # défaut : payés
    date_debut   = request.args.get("date_debut", "")
    date_fin     = request.args.get("date_fin", "")

    filtres = {
        "activite_id": activite_id,
        "classe":      classe,
        "statut":      statut,
        "date_debut":  date_debut,
        "date_fin":    date_fin,
    }

    # ── Données pour les menus déroulants ────────────────────
    activites_dispo = (
        Activite.query
        .order_by(Activite.date_limite_paiement.desc())
        .all()
    )

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

    # ── Construction de la requête avec les filtres ──────────
    lignes = _construire_requete_export(
        activite_id, classe, statut, date_debut, date_fin
    )

    return render_template(
        "admin_export.html",
        lignes=lignes,
        activites_dispo=activites_dispo,
        classes_dispo=classes_dispo,
        filtres=filtres,
        role="admin",
        active="export",
        current_user_name="Administrateur (test)"
    )


@main.route("/admin/export/csv")
def admin_export_csv():
    """
    Génère et télécharge directement le fichier CSV.
    Utilise les mêmes filtres que la page d'aperçu.
    """

    activite_id  = request.args.get("activite_id", "")
    classe       = request.args.get("classe", "")
    statut       = request.args.get("statut", "paye")
    date_debut   = request.args.get("date_debut", "")
    date_fin     = request.args.get("date_fin", "")

    lignes = _construire_requete_export(
        activite_id, classe, statut, date_debut, date_fin
    )

    # ── Génération du CSV en mémoire ─────────────────────────
    output = io.StringIO()
    writer = csv.writer(output, delimiter=",", quoting=csv.QUOTE_MINIMAL)

    # En-tête
    writer.writerow([
        "activite",
        "classe",
        "nom_eleve",
        "prenom_eleve",
        "option",
        "statut",
        "montant",
        "reference",
        "date_validation",
        "mode_paiement",
    ])

    # Données
    for l in lignes:
        # Récupère le paiement validé s'il existe
        paiement = l.paiements[0] if l.paiements else None

        writer.writerow([
            l.activite.titre,
            l.eleve.classe,
            l.eleve.nom,
            l.eleve.prenom,
            l.eleve.option or "",
            l.statut,
            str(l.montant_attendu),
            paiement.ref_transaction if paiement else "",
            paiement.paye_le.strftime("%d/%m/%Y %H:%M") if (paiement and paiement.paye_le) else "",
            paiement.mode_paiement if paiement else "",
        ])

    # ── Nom du fichier avec date du jour ─────────────────────
    nom_fichier = f"paiements_cndk_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    # ── Réponse HTTP avec le fichier CSV ─────────────────────
    # BOM UTF-8 (\ufeff) pour que Excel ouvre correctement le fichier
    csv_bytes = "\ufeff" + output.getvalue()

    return Response(
        csv_bytes,
        mimetype="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={nom_fichier}"
        }
    )


def _construire_requete_export(activite_id, classe, statut, date_debut, date_fin):
    """
    Fonction interne partagée par admin_export et admin_export_csv.
    Construit la requête SQLAlchemy selon les filtres reçus.
    Tri : activité → classe → nom élève → prénom élève
    """

    query = (
        ActiviteEleve.query
        .join(Eleve, ActiviteEleve.eleve_id == Eleve.id)
        .join(Activite, ActiviteEleve.activite_id == Activite.id)
    )

    # Filtre par activité
    if activite_id:
        query = query.filter(ActiviteEleve.activite_id == int(activite_id))

    # Filtre par classe
    if classe:
        query = query.filter(Eleve.classe == classe)

    # Filtre par statut
    if statut == "paye":
        query = query.filter(ActiviteEleve.statut == "paye")
    elif statut == "en_attente":
        query = query.filter(ActiviteEleve.statut == "en_attente")
    # "tous" → pas de filtre statut

    # Filtre par période (date de validation)
    if date_debut or date_fin:
        # On joint les paiements pour filtrer sur paye_le
        query = query.outerjoin(
            PaiementActivite,
            PaiementActivite.activite_eleve_id == ActiviteEleve.id
        )
        if date_debut:
            query = query.filter(
                db.or_(
                    PaiementActivite.paye_le >= date_debut,
                    ActiviteEleve.statut == "en_attente"  # inclut les non payés
                )
            )
        if date_fin:
            query = query.filter(
                db.or_(
                    PaiementActivite.paye_le <= date_fin + " 23:59:59",
                    ActiviteEleve.statut == "en_attente"
                )
            )

    # Tri : activité → classe → nom → prénom
    query = query.order_by(
        Activite.titre,
        Eleve.classe,
        Eleve.nom,
        Eleve.prenom
    )

    return query.all()


# ─────────────────────────────────────────────────────────────
# EXPORT BOB50 — À ajouter dans routes.py
# ─────────────────────────────────────────────────────────────
# Ajouter en haut de routes.py :
#   from app.bob50_service import generer_fichiers_bob50
#   from datetime import datetime
# ─────────────────────────────────────────────────────────────


@main.route("/admin/export/bob50")
def admin_export_bob50():
    """
    Génère et télécharge un ZIP contenant HFac.dbf + Lfac.dbf
    pour import dans Bob50.

    Seuls les paiements VALIDÉS (statut = "paye") et
    NON ENCORE EXPORTÉS (bob50_exported_at IS NULL) sont inclus.

    Après génération, bob50_exported_at est rempli sur chaque
    paiement pour éviter les doublons lors du prochain export.
    """

    # ── Récupération des paiements à exporter ────────────────
    # On joint ActiviteEleve, Eleve et Activite pour que le service
    # puisse accéder à toutes les données nécessaires
    paiements = (
        PaiementActivite.query
        .join(ActiviteEleve, PaiementActivite.activite_eleve_id == ActiviteEleve.id)
        .join(Eleve,         ActiviteEleve.eleve_id == Eleve.id)
        .join(Activite,      ActiviteEleve.activite_id == Activite.id)
        .filter(PaiementActivite.statut == "paye")
        .filter(PaiementActivite.bob50_exported_at == None)  # pas encore exportés
        .order_by(Activite.titre, Eleve.classe, Eleve.nom, Eleve.prenom)
        .all()
    )

    if not paiements:
        flash("Aucun paiement à exporter (tous déjà exportés ou aucun paiement validé).", "info")
        return redirect(url_for("main.admin_export"))

    # ── Génération des fichiers DBF ──────────────────────────
    zip_bytes = generer_fichiers_bob50(paiements)

    # ── Marquage des paiements comme exportés ────────────────
    # On remplit bob50_exported_at pour ne pas les réexporter
    maintenant = datetime.now()
    for p in paiements:
        p.bob50_exported_at = maintenant
    db.session.commit()

    # ── Nom du fichier ZIP avec date du jour ─────────────────
    nom_fichier = f"bob50_{maintenant.strftime('%Y%m%d_%H%M')}.zip"

    flash(f"{len(paiements)} paiement(s) exporté(s) vers Bob50.", "succes")

    return send_file(
        io.BytesIO(zip_bytes),
        mimetype="application/zip",
        download_name=nom_fichier,
        as_attachment=True
    )
