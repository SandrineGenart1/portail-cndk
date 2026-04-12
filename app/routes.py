from app.extensions import db
from app.models import ParentEleve, Eleve, Activite, ActiviteEleve, PaiementActivite
from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.datastructures import ImmutableMultiDict
from app.db import get_db_connection

main = Blueprint("main", __name__)
@main.route("/admin")
def admin_dashboard():
    """
    Affiche le tableau de bord administrateur avec quelques statistiques globales.
    Les calculs sont réalisés avec SQLAlchemy au lieu de requêtes SQL brutes.
    """

    # Calcule le nombre d'activités dont le statut est "ouvert"
    nb_activites_ouvertes = (
        db.session.query(db.func.count(Activite.id))
        .filter(Activite.statut == "ouvert")
        .scalar()
    )

    # Calcule le nombre de paiements encore en attente
    # dans la table activites_eleves
    nb_en_attente = (
        db.session.query(db.func.count(ActiviteEleve.id))
        .filter(ActiviteEleve.statut == "en_attente")
        .scalar()
    )

    # Calcule :
    # - le nombre de paiements reçus ce mois-ci
    # - le montant total encaissé ce mois-ci
    row = (
        db.session.query(
            db.func.count(PaiementActivite.id),
            db.func.coalesce(db.func.sum(PaiementActivite.montant), 0)
        )
        .filter(PaiementActivite.statut == "paye")
        .filter(
            db.func.date_trunc("month", PaiementActivite.paye_le)
            == db.func.date_trunc("month", db.func.now())
        )
        .first()
    )

    # Récupération des résultats de la requête
    nb_payes = row[0]
    montant_encaisse = float(row[1])

    # Construction du dictionnaire envoyé au template
    stats = {
        "nb_activites_ouvertes": nb_activites_ouvertes,
        "nb_en_attente": nb_en_attente,
        "nb_payes": nb_payes,
        "montant_encaisse": f"{montant_encaisse:.2f}",
    }

    # Affichage du tableau de bord administrateur
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
    """
    Affiche la liste des activités liées aux enfants du parent connecté.
    """

    parent_id = 1  # simulation utilisateur connecté

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

# Confirmation-paeiment 
@main.route("/confirmation-paiement/<int:activite_eleve_id>")
def confirmation_paiement(activite_eleve_id):
    """
    Affiche la page de confirmation avant paiement.
    Vérifie que l'activité demandée appartient bien à un enfant du parent connecté.
    """

    parent_id = 1  # simulation parent connecté

    ligne = (
        ActiviteEleve.query
        .join(Eleve, ActiviteEleve.eleve_id == Eleve.id)
        .join(Activite, ActiviteEleve.activite_id == Activite.id)
        .join(ParentEleve, ParentEleve.eleve_id == Eleve.id)
        .filter(ActiviteEleve.id == activite_eleve_id)
        .filter(ParentEleve.parent_id == parent_id)
        .first()
    )

    if ligne is None:
        flash("Activité introuvable ou accès non autorisé.", "erreur")
        return redirect(url_for("main.index"))

    if ligne.statut == "paye":
        flash("Cette activité est déjà payée.", "info")
        return redirect(url_for("main.index"))

    return render_template(
        "confirmation_paiement.html",
        ligne=ligne,
        role="parent",
        active="",
        current_user_name="Parent (test)"
    )

#Payer en ligne

@main.route("/payer-en-ligne/<int:activite_eleve_id>", methods=["POST"])
def payer_en_ligne(activite_eleve_id):
    """
    Traite le paiement en ligne d'une activité.
    Vérifie que l'activité appartient bien à un enfant du parent connecté,
    empêche le double paiement, puis enregistre le paiement.
    """

    parent_id = 1  # simulation du parent connecté

    # Recherche de l'activité liée à un élève appartenant au parent connecté
    ligne = (
        ActiviteEleve.query
        .join(Eleve, ActiviteEleve.eleve_id == Eleve.id)
        .join(ParentEleve, ParentEleve.eleve_id == Eleve.id)
        .filter(ActiviteEleve.id == activite_eleve_id)
        .filter(ParentEleve.parent_id == parent_id)
        .first()
    )

    # Vérifie que l'activité existe bien et qu'elle appartient au bon parent
    if ligne is None:
        flash("Activité introuvable ou accès non autorisé.", "erreur")
        return redirect(url_for("main.index"))

    # Empêche un double paiement
    if ligne.statut == "paye":
        flash("Cette activité est déjà payée.", "info")
        return redirect(url_for("main.index"))

    # Création d'un paiement de test
    paiement = PaiementActivite(
        activite_eleve_id=ligne.id,
        montant=ligne.montant_attendu,
        statut="paye",
        mode_paiement="test",
        ref_transaction=f"TEST-{ligne.id}",
        paye_le=db.func.now()
    )

    # Ajout du paiement dans la session SQLAlchemy
    db.session.add(paiement)

    # Mise à jour du statut de l'activité élève
    ligne.statut = "paye"

    # Validation des changements dans la base
    db.session.commit()

    flash("Paiement effectué avec succès !", "succes")
    return redirect(url_for("main.index"))

# ─────────────────────────────────────────────────────────────
# BACK-OFFICE ADMIN
# ─────────────────────────────────────────────────────────────

@main.route("/admin/paiements")
def admin_paiements():
    """
    Affiche la liste des paiements avec SQLAlchemy.
    """

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

#_____________Route admin_marquer_paye_____________________
@main.route("/admin/marquer-paye/<int:activite_eleve_id>", methods=["POST"])
def admin_marquer_paye(activite_eleve_id):
    """
    Marque une activité élève comme payée depuis le back-office comptabilité.
    Crée aussi une ligne dans la table des paiements.
    """

    # Recherche de la ligne activite_eleve correspondant à l'identifiant reçu
    ligne = ActiviteEleve.query.get(activite_eleve_id)

    # Vérifie que la ligne existe bien
    if ligne is None:
        flash("Activité introuvable.", "erreur")
        return redirect(url_for("main.admin_paiements"))

    # Empêche de marquer deux fois la même activité comme payée
    if ligne.statut == "paye":
        flash("Cette activité est déjà marquée comme payée.", "info")
        return redirect(url_for("main.admin_paiements"))

    # Création d'un enregistrement dans la table paiements_activites
    paiement = PaiementActivite(
        activite_eleve_id=ligne.id,
        montant=ligne.montant_attendu,
        statut="paye",
        mode_paiement="manuel",
        ref_transaction=f"MANUEL-{ligne.id}",
        paye_le=db.func.now()
    )

    # Ajout du paiement dans la session SQLAlchemy
    db.session.add(paiement)

    # Mise à jour du statut dans activites_eleves
    ligne.statut = "paye"

    # Validation des changements en base de données
    db.session.commit()

    flash("Paiement marqué comme payé par la comptabilité.", "succes")
    return redirect(url_for("main.admin_paiements"))

# ─────────────────────────────────────────────────────────────
# CRÉATION D'ACTIVITÉS ET AFFECTATION AUX CLASSES
# ─────────────────────────────────────────────────────────────

@main.route("/admin/activites")
def admin_activites():
    """Liste toutes les activités existantes avec leur taux de paiement."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                a.id,
                a.titre,
                a.montant,
                a.date_limite_paiement,
                a.statut,
                COUNT(ae.id)                                      AS nb_total,
                COUNT(ae.id) FILTER (WHERE ae.statut = 'paye')   AS nb_payes
            FROM activites a
            LEFT JOIN activites_eleves ae ON ae.activite_id = a.id
            GROUP BY a.id
            ORDER BY a.date_limite_paiement DESC;
        """)
        activites = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    return render_template("admin_activites.html", activites=activites, role="admin", active="activites", current_user_name="Administrateur (test)")


@main.route("/admin/activites/nouvelle", methods=["GET", "POST"])
def admin_nouvelle_activite():
    """
    GET  : affiche le formulaire de création
    POST : crée l'activité et affecte les élèves des classes choisies
    """
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # On récupère la liste des classes disponibles pour la liste déroulante
        cur.execute("""
            SELECT DISTINCT classe FROM eleves WHERE actif = TRUE ORDER BY classe;
        """)
        classes_dispo = [row[0] for row in cur.fetchall()]

        if request.method == "POST":
            titre         = request.form.get("titre", "").strip()
            description   = request.form.get("description", "").strip()
            montant       = request.form.get("montant", "").strip()
            date_limite   = request.form.get("date_limite_paiement", "").strip()
            obligatoire   = request.form.get("obligatoire") == "on"
            # getlist récupère toutes les cases cochées nommées "classes"
            classes_cibles = request.form.getlist("classes")

            # ── Validation basique ──────────────────────────────
            erreurs = []
            if not titre:
                erreurs.append("Le titre est obligatoire.")
            if not montant:
                erreurs.append("Le montant est obligatoire.")
            else:
                try:
                    montant = float(montant)
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
                    role="admin", active="nouvelle_activite", current_user_name="Administrateur (test)"
                )

            # ── Insertion de l'activité ──────────────────────────
            cur.execute("""
                INSERT INTO activites
                    (titre, description, montant, date_limite_paiement,
                     classes_cibles, obligatoire, statut)
                VALUES (%s, %s, %s, %s, %s, %s, 'ouvert')
                RETURNING id;
            """, (titre, description, montant, date_limite,
                  classes_cibles, obligatoire))

            activite_id = cur.fetchone()[0]

            # ── Récupération des élèves des classes choisies ─────
            # On utilise ANY(%s) avec un tableau Python → PostgreSQL
            cur.execute("""
                SELECT id FROM eleves
                WHERE classe = ANY(%s) AND actif = TRUE;
            """, (classes_cibles,))
            eleves = cur.fetchall()

            # ── Création d'une ligne activites_eleves par élève ──
            nb_affectes = 0
            for (eleve_id,) in eleves:
                cur.execute("""
                    INSERT INTO activites_eleves
                        (activite_id, eleve_id, montant_attendu, statut)
                    VALUES (%s, %s, %s, 'en_attente')
                    ON CONFLICT (activite_id, eleve_id) DO NOTHING;
                """, (activite_id, eleve_id, montant))
                nb_affectes += 1

            conn.commit()

            flash(
                f"Activité « {titre} » créée et affectée à "
                f"{nb_affectes} élève(s) dans les classes : "
                f"{', '.join(classes_cibles)}.",
                "succes"
            )
            return redirect(url_for("main.admin_activites"))

    finally:
        cur.close()
        conn.close()

    # GET : affichage du formulaire vide
    return render_template(
        "admin_nouvelle_activite.html",
        classes_dispo=classes_dispo,
        form_data=ImmutableMultiDict(),
        role="admin", active="nouvelle_activite", current_user_name="Administrateur (test)"
    )


# ─────────────────────────────────────────────────────────────
# IMPORT CSV ÉLÈVES
# ─────────────────────────────────────────────────────────────

@main.route("/admin/eleves/importer", methods=["GET", "POST"])
def admin_importer_eleves():
    """
    GET  : affiche le formulaire d'import CSV
    POST : traite le fichier CSV et insère / met à jour les élèves

    Format CSV attendu (avec en-tête) :
        prenom,nom,classe,option,annee_scolaire
        Marie,Dupont,3A,Latin,2025-2026
        Paul,Martin,3B,,2025-2026        ← option vide = NULL
    """
    if request.method == "GET":
        return render_template("admin_importer_eleves.html", role="admin", active="import_eleves", current_user_name="Administrateur (test)")

    # ── Vérification du fichier uploadé ─────────────────────────
    fichier = request.files.get("fichier_csv")

    if not fichier or fichier.filename == "":
        flash("Aucun fichier sélectionné.", "erreur")
        return render_template("admin_importer_eleves.html", role="admin", active="import_eleves", current_user_name="Administrateur (test)")

    if not fichier.filename.lower().endswith(".csv"):
        flash("Le fichier doit être au format .csv", "erreur")
        return render_template("admin_importer_eleves.html", role="admin", active="import_eleves", current_user_name="Administrateur (test)")

    # ── Lecture du CSV ───────────────────────────────────────────
    import csv
    import io

    try:
        contenu = fichier.read().decode("utf-8-sig")  # utf-8-sig gère le BOM Excel
        lecteur = csv.DictReader(io.StringIO(contenu))

        # Vérification des colonnes obligatoires
        colonnes_requises = {"prenom", "nom", "classe", "annee_scolaire"}
        if not colonnes_requises.issubset(set(lecteur.fieldnames or [])):
            manquantes = colonnes_requises - set(lecteur.fieldnames or [])
            flash(
                f"Colonnes manquantes dans le CSV : {', '.join(manquantes)}. "
                f"Colonnes attendues : prenom, nom, classe, option, annee_scolaire",
                "erreur"
            )
            return render_template("admin_importer_eleves.html", role="admin", active="import_eleves", current_user_name="Administrateur (test)")

        lignes = list(lecteur)

    except UnicodeDecodeError:
        flash(
            "Erreur d'encodage. Enregistrez votre fichier en UTF-8 "
            "(dans Excel : Enregistrer sous → CSV UTF-8).",
            "erreur"
        )
        return render_template("admin_importer_eleves.html", role="admin", active="import_eleves", current_user_name="Administrateur (test)")

    if not lignes:
        flash("Le fichier CSV est vide (aucune ligne de données).", "erreur")
        return render_template("admin_importer_eleves.html", role="admin", active="import_eleves", current_user_name="Administrateur (test)")

    # ── Import en base ───────────────────────────────────────────
    conn = get_db_connection()
    cur = conn.cursor()

    nb_inseres  = 0
    nb_mis_a_jour = 0
    nb_erreurs  = 0
    erreurs_detail = []

    try:
        for i, ligne in enumerate(lignes, start=2):  # start=2 car ligne 1 = en-tête
            prenom        = ligne.get("prenom", "").strip()
            nom           = ligne.get("nom", "").strip()
            classe        = ligne.get("classe", "").strip()
            option        = ligne.get("option", "").strip() or None  # vide → NULL
            annee_scolaire = ligne.get("annee_scolaire", "").strip()

            # Validation de la ligne
            if not prenom or not nom or not classe or not annee_scolaire:
                nb_erreurs += 1
                erreurs_detail.append(
                    f"Ligne {i} ignorée : prenom, nom, classe et annee_scolaire "
                    f"sont obligatoires (trouvé : {prenom!r}, {nom!r}, {classe!r}, {annee_scolaire!r})"
                )
                continue

            # INSERT ... ON CONFLICT : si l'élève existe déjà (même nom/classe/année)
            # on met à jour son option et on le réactive si nécessaire
            cur.execute("""
                INSERT INTO eleves (prenom, nom, classe, option, annee_scolaire, actif)
                VALUES (%s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (prenom, nom, classe, annee_scolaire)
                DO UPDATE SET
                    option = EXCLUDED.option,
                    actif  = TRUE
                RETURNING (xmax = 0) AS est_insertion;
            """, (prenom, nom, classe, option, annee_scolaire))

            # xmax = 0 → INSERT (nouvelle ligne), xmax != 0 → UPDATE
            est_insertion = cur.fetchone()[0]
            if est_insertion:
                nb_inseres += 1
            else:
                nb_mis_a_jour += 1

        conn.commit()

    except Exception as e:
        conn.rollback()
        flash(f"Erreur lors de l'import : {str(e)}", "erreur")
        return render_template("admin_importer_eleves.html", role="admin", active="import_eleves", current_user_name="Administrateur (test)")

    finally:
        cur.close()
        conn.close()

    # ── Message de résultat ──────────────────────────────────────
    if nb_inseres > 0 or nb_mis_a_jour > 0:
        flash(
            f"Import terminé : {nb_inseres} élève(s) ajouté(s), "
            f"{nb_mis_a_jour} élève(s) mis à jour.",
            "succes"
        )

    if nb_erreurs > 0:
        flash(
            f"{nb_erreurs} ligne(s) ignorée(s) pour données manquantes.",
            "erreur"
        )
        for detail in erreurs_detail[:5]:  # max 5 détails affichés
            flash(detail, "erreur")

    return redirect(url_for("main.admin_importer_eleves"))


# ─────────────────────────────────────────────────────────────
# WEBHOOK MOLLIE
# ─────────────────────────────────────────────────────────────

@main.route("/webhook/mollie", methods=["POST"])
def mollie_webhook():
    return "Webhook reçu", 200
