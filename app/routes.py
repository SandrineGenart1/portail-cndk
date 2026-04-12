from app.models import ParentEleve, Eleve, Activite, ActiviteEleve
from flask import Blueprint, render_template, redirect, url_for, flash, request
from werkzeug.datastructures import ImmutableMultiDict
from app.db import get_db_connection

main = Blueprint("main", __name__)
@main.route("/admin")
def admin_dashboard():
    """Tableau de bord admin avec statistiques rapides."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Activités ouvertes
        cur.execute("SELECT COUNT(*) FROM activites WHERE statut = 'ouvert';")
        nb_activites_ouvertes = cur.fetchone()[0]

        # Paiements en attente ce mois
        cur.execute("SELECT COUNT(*) FROM activites_eleves WHERE statut = 'en_attente';")
        nb_en_attente = cur.fetchone()[0]

        # Paiements reçus ce mois
        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(montant), 0)
            FROM paiements_activites
            WHERE statut = 'paye'
              AND date_trunc('month', paye_le) = date_trunc('month', NOW());
        """)
        row = cur.fetchone()
        nb_payes = row[0]
        montant_encaisse = float(row[1])

    finally:
        cur.close()
        conn.close()

    stats = {
        "nb_activites_ouvertes": nb_activites_ouvertes,
        "nb_en_attente": nb_en_attente,
        "nb_payes": nb_payes,
        "montant_encaisse": f"{montant_encaisse:.2f}",
    }

    return render_template("admin_dashboard.html", stats=stats, role="admin", active="dashboard", current_user_name="Administrateur (test)")




# ─────────────────────────────────────────────────────────────
# ESPACE PARENT
# ─────────────────────────────────────────────────────────────

@main.route("/")
def index():
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

    return render_template("index.html", lignes=lignes)


@main.route("/confirmation-paiement/<int:activite_eleve_id>")
def confirmation_paiement(activite_eleve_id):
    parent_id = 1  # TODO : flask_login

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Sécurité : on vérifie que cet activite_eleve_id appartient
        # bien à un enfant du parent connecté
        cur.execute("""
            SELECT ae.id, ae.montant_attendu, ae.statut,
                   e.prenom, e.nom, a.titre
            FROM activites_eleves ae
            JOIN eleves e ON ae.eleve_id = e.id
            JOIN activites a ON ae.activite_id = a.id
            JOIN parents_eleves pe ON pe.eleve_id = e.id
            WHERE ae.id = %s AND pe.parent_id = %s
        """, (activite_eleve_id, parent_id))

        ligne = cur.fetchone()

        if ligne is None:
            flash("Activité introuvable ou accès non autorisé.", "erreur")
            return redirect(url_for("main.index"))

        if ligne[2] == "paye":
            flash("Cette activité est déjà payée.", "info")
            return redirect(url_for("main.index"))

    finally:
        cur.close()
        conn.close()

    return render_template("confirmation_paiement.html", ligne=ligne, role="parent", active="", current_user_name="Parent (test)")


@main.route("/payer-en-ligne/<int:activite_eleve_id>", methods=["POST"])
def payer_en_ligne(activite_eleve_id):
    parent_id = 1  # TODO : flask_login

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Sécurité : même vérification que pour la confirmation
        cur.execute("""
            SELECT ae.montant_attendu, ae.statut
            FROM activites_eleves ae
            JOIN eleves e ON ae.eleve_id = e.id
            JOIN parents_eleves pe ON pe.eleve_id = e.id
            WHERE ae.id = %s AND pe.parent_id = %s
        """, (activite_eleve_id, parent_id))

        resultat = cur.fetchone()

        if resultat is None:
            flash("Activité introuvable ou accès non autorisé.", "erreur")
            return redirect(url_for("main.index"))

        montant, statut = resultat

        if statut == "paye":
            flash("Déjà payé.", "info")
            return redirect(url_for("main.index"))

        # Simulation paiement (→ remplacer par Mollie ici)
        cur.execute("""
            INSERT INTO paiements_activites
            (activite_eleve_id, montant, statut, mode_paiement, ref_transaction, paye_le)
            VALUES (%s, %s, 'paye', 'test', %s, NOW())
        """, (activite_eleve_id, montant, f"TEST-{activite_eleve_id}"))

        cur.execute("""
            UPDATE activites_eleves SET statut = 'paye' WHERE id = %s
        """, (activite_eleve_id,))

        conn.commit()
        flash("Paiement effectué avec succès !", "succes")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("main.index"))


# ─────────────────────────────────────────────────────────────
# BACK-OFFICE ADMIN
# ─────────────────────────────────────────────────────────────

@main.route("/admin/paiements")
def admin_paiements():
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                ae.id,
                e.prenom,
                e.nom,
                a.titre,
                ae.montant_attendu,
                ae.statut
            FROM activites_eleves ae
            JOIN eleves e ON ae.eleve_id = e.id
            JOIN activites a ON ae.activite_id = a.id
            ORDER BY ae.statut, e.nom, e.prenom;
        """)
        lignes = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    return render_template("admin_paiements.html", lignes=lignes, role="admin", active="paiements", current_user_name="Administrateur (test)")


@main.route("/admin/marquer-paye/<int:activite_eleve_id>", methods=["POST"])
def admin_marquer_paye(activite_eleve_id):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT montant_attendu, statut FROM activites_eleves WHERE id = %s
        """, (activite_eleve_id,))
        resultat = cur.fetchone()

        if resultat is None:
            flash("Activité introuvable.", "erreur")
            return redirect(url_for("main.admin_paiements"))

        montant, statut = resultat

        if statut == "paye":
            flash("Cette activité est déjà marquée comme payée.", "info")
            return redirect(url_for("main.admin_paiements"))

        cur.execute("""
            INSERT INTO paiements_activites
            (activite_eleve_id, montant, statut, mode_paiement, ref_transaction, paye_le)
            VALUES (%s, %s, 'paye', 'manuel', %s, NOW())
        """, (activite_eleve_id, montant, f"MANUEL-{activite_eleve_id}"))

        cur.execute("""
            UPDATE activites_eleves SET statut = 'paye' WHERE id = %s
        """, (activite_eleve_id,))

        conn.commit()
        flash("Paiement marqué comme payé par la comptabilité.", "succes")

    finally:
        cur.close()
        conn.close()

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
