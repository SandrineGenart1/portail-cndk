from flask import Blueprint, render_template, redirect, url_for, flash
from app.db import get_db_connection

main = Blueprint("main", __name__)


@main.route("/")
def index():
    parent_id = 1  # simulation utilisateur connecté

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
            FROM parents_eleves pe
            JOIN eleves e ON pe.eleve_id = e.id
            JOIN activites_eleves ae ON ae.eleve_id = e.id
            JOIN activites a ON ae.activite_id = a.id
            WHERE pe.parent_id = %s
            ORDER BY e.nom, e.prenom;
        """, (parent_id,))
        lignes = cur.fetchall()

    finally:
        cur.close()
        conn.close()

    return render_template("index.html", lignes=lignes)


@main.route("/confirmation-paiement/<int:activite_eleve_id>")
def confirmation_paiement(activite_eleve_id):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT ae.id, ae.montant_attendu, ae.statut,
                   e.prenom, e.nom, a.titre
            FROM activites_eleves ae
            JOIN eleves e ON ae.eleve_id = e.id
            JOIN activites a ON ae.activite_id = a.id
            WHERE ae.id = %s
        """, (activite_eleve_id,))

        ligne = cur.fetchone()

        if ligne is None:
            flash("Activité introuvable.", "erreur")
            return redirect(url_for("main.index"))

        if ligne[2] == "paye":
            flash("Cette activité est déjà payée.", "info")
            return redirect(url_for("main.index"))

    finally:
        cur.close()
        conn.close()

    return render_template("confirmation_paiement.html", ligne=ligne)

@main.route("/payer-en-ligne/<int:activite_eleve_id>", methods=["POST"])
def payer_en_ligne(activite_eleve_id):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT montant_attendu, statut
            FROM activites_eleves
            WHERE id = %s
        """, (activite_eleve_id,))

        resultat = cur.fetchone()

        if resultat is None:
            flash("Activité introuvable.", "erreur")
            return redirect(url_for("main.index"))

        montant = resultat[0]
        statut = resultat[1]

        if statut == "paye":
            flash("Déjà payé.", "info")
            return redirect(url_for("main.index"))

        # Simulation paiement (plus tard → Mollie ici)
        cur.execute("""
            INSERT INTO paiements_activites
            (activite_eleve_id, montant, statut, mode_paiement, ref_transaction, paye_le)
            VALUES (%s, %s, 'paye', 'test', %s, NOW())
        """, (activite_eleve_id, montant, f"TEST-{activite_eleve_id}"))

        cur.execute("""
            UPDATE activites_eleves
            SET statut = 'paye'
            WHERE id = %s
        """, (activite_eleve_id,))

        conn.commit()

        flash("Paiement effectué avec succès !", "succes")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("main.index"))


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

    return render_template("admin_paiements.html", lignes=lignes)


@main.route("/admin/marquer-paye/<int:activite_eleve_id>", methods=["POST"])
def admin_marquer_paye(activite_eleve_id):
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT montant_attendu, statut
            FROM activites_eleves
            WHERE id = %s
        """, (activite_eleve_id,))
        resultat = cur.fetchone()

        if resultat is None:
            flash("Activité introuvable.", "erreur")
            return redirect(url_for("main.admin_paiements"))

        montant = resultat[0]
        statut = resultat[1]

        if statut == "paye":
            flash("Cette activité est déjà marquée comme payée.", "info")
            return redirect(url_for("main.admin_paiements"))

        cur.execute("""
            INSERT INTO paiements_activites
            (activite_eleve_id, montant, statut, mode_paiement, ref_transaction, paye_le)
            VALUES (%s, %s, 'paye', 'manuel', %s, NOW())
        """, (activite_eleve_id, montant, f"MANUEL-{activite_eleve_id}"))

        cur.execute("""
            UPDATE activites_eleves
            SET statut = 'paye'
            WHERE id = %s
        """, (activite_eleve_id,))

        conn.commit()
        flash("Paiement marqué comme payé par la comptabilité.", "succes")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for("main.admin_paiements"))


@main.route("/webhook/mollie", methods=["POST"])
def mollie_webhook():
    return "Webhook reçu", 200