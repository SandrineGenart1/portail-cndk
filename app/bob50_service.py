"""
bob50_service.py — Génération des fichiers DBF pour import dans Bob50
─────────────────────────────────────────────────────────────────────
Bob50 attend deux fichiers DBF pour chaque import de factures :

  HFac.dbf  →  En-têtes de factures (1 ligne par paiement)
               Contient : journal, date, compte client, montant,
               communication structurée

  Lfac.dbf  →  Lignes comptables (1 ligne par écriture)
               Contient : journal, compte comptable, montant,
               sens débit/crédit, description

Ces deux fichiers sont générés ensemble et téléchargés dans un ZIP.

Installation requise :
    pip install dbf

Usage dans routes.py :
    from app.bob50_service import generer_fichiers_bob50
    zip_bytes = generer_fichiers_bob50(paiements)
    return send_file(
        io.BytesIO(zip_bytes),
        mimetype='application/zip',
        download_name='export_bob50.zip'
    )
"""

import io
import os
import tempfile
import zipfile
from datetime import datetime

import dbf

# ── Configuration Bob50 ─────────────────────────────────────
# À déplacer dans config.py / .env en production

BOB50_JOURNAL       = "VEN"     # Code du journal (à confirmer avec la comptabilité)
BOB50_COMPTE_DEFAUT = "701003"  # Compte comptable produit par défaut


# ── Définition des champs ────────────────────────────────────
# Tous les champs sont de type C (Character) longueur 40,
# exactement comme dans les fichiers modèles fournis par l'école.

CHAMPS_HFAC = (
    "TDBK C(40); TFYEAR C(40); TYEAR C(40); TMONTH C(40); "
    "TDOCNO C(40); TDOCDATE C(40); TTYPCIE C(40); TCOMPAN C(40); "
    "TDUEDATE C(40); TDUECAT C(40); TDISRATE C(40); TDISAMOUNT C(40); "
    "TDISDELAY C(40); TDISDATE C(40); TCURRENCY C(40); TCURRATE C(40); "
    "TCURAMN C(40); TAMOUNT C(40); TREMINT C(40); TREMEXT C(40); "
    "TMATCHNO C(40); TINTMODE C(40); TISBLOCKED C(40); TINVVCS C(40)"
)

CHAMPS_LFAC = (
    "TDBK C(40); TFYEAR C(40); TYEAR C(40); TMONTH C(40); "
    "TDOCNO C(40); TDOCLINE C(40); TTYPELINE C(40); TACTTYPE C(40); "
    "TACCOUNT C(40); TMATCHNO C(40); TCURAMN C(40); TAMOUNT C(40); "
    "TCBVAT C(40); TBASVAT C(40); TVCTOTAMN C(40); TVATTOTAMN C(40); "
    "TCURVATAMN C(40); TVATAMN C(40); TVCDBLAMN C(40); TVATDBLAMN C(40); "
    "TBASLSTAMN C(40); TVSTORED C(40); TDC C(40); TREM C(40); "
    "COST_REP C(40); COST_CRIT1 C(40); COST_CRIT2 C(40); COST_CRIT3 C(40); "
    "COST_CRIT4 C(40); COST_CRIT5 C(40); COST_CRIT6 C(40); COST_CRIT7 C(40); "
    "COST_CRIT8 C(40); COST_CRIT9 C(40); COST_CRITA C(40); "
    "TFREEINFO1 C(40); TFREEINFO2 C(40); TDOCDATE C(40); "
    "COST_1 C(40); COST_2 C(40); COST_3 C(40); COST_4 C(40)"
)


# ── Fonction principale ──────────────────────────────────────

def generer_fichiers_bob50(paiements):
    """
    Génère HFac.dbf + Lfac.dbf et les retourne dans un ZIP (bytes).

    Paramètre :
        paiements : liste d'objets PaiementActivite (SQLAlchemy)
                    avec les relations activite_eleve.activite
                    et activite_eleve.eleve.liens_parents chargées

    Retourne :
        bytes : contenu du fichier ZIP prêt à télécharger
    """

    with tempfile.TemporaryDirectory() as tmpdir:

        chemin_hfac = os.path.join(tmpdir, "HFac.dbf")
        chemin_lfac = os.path.join(tmpdir, "Lfac.dbf")

        _ecrire_hfac(paiements, chemin_hfac)
        _ecrire_lfac(paiements, chemin_lfac)

        # Mise en ZIP en mémoire
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(chemin_hfac, "HFac.dbf")
            zf.write(chemin_lfac, "Lfac.dbf")

        return zip_buffer.getvalue()


# ── Génération de HFac.dbf ───────────────────────────────────

def _ecrire_hfac(paiements, chemin):
    """
    1 ligne par paiement.
    Champs clés :
        TCOMPAN  → numéro compte client Bob50 du parent
        TAMOUNT  → montant du paiement
        TREMEXT  → communication structurée (***XXX/XXXX/XXXXX***)
        TINVVCS  → même communication sans formatage
        TDOCDATE → date du paiement (JJ/MM/AA)
    """

    table = dbf.Table(chemin, CHAMPS_HFAC, codepage="cp1252")
    table.open(dbf.READ_WRITE)

    for num, paiement in enumerate(paiements, start=1):

        ae       = paiement.activite_eleve
        eleve    = ae.eleve

        # Date, année, mois
        date_obj  = paiement.paye_le or datetime.now()
        annee     = str(date_obj.year)
        mois      = date_obj.strftime("%m")
        date_str  = date_obj.strftime("%d/%m/%y")   # format Bob50 : JJ/MM/AA

        # Compte client Bob50 du parent
        bob50_compte = _recuperer_bob50_compte(eleve)

        # Communication structurée
        ref_ext = paiement.ref_transaction or ""
        # Bob50 utilise *** au lieu de +++ dans TREMEXT
        ref_bob = ref_ext.replace("+++", "***")
        # TINVVCS = sans formatage ni séparateurs (ex : 003375591916)
        ref_vcs = ref_ext.replace("+++", "").replace("***", "").replace("/", "").replace("+", "").replace("*", "").strip()

        montant_str = _formater_montant(paiement.montant)

        # Référence interne (format observé dans les fichiers modèles)
        ref_int = f"{annee}{mois}-{date_obj.strftime('%d%m%y')}-{ae.id:06d}-{num:04d}"

        table.append({
            "TDBK":       BOB50_JOURNAL,
            "TFYEAR":     annee,
            "TYEAR":      annee,
            "TMONTH":     mois,
            "TDOCNO":     str(num),
            "TDOCDATE":   date_str,
            "TTYPCIE":    "C",          # C = Client
            "TCOMPAN":    bob50_compte,
            "TDUEDATE":   "",
            "TDUECAT":    "",
            "TDISRATE":   "",
            "TDISAMOUNT": "",
            "TDISDELAY":  "",
            "TDISDATE":   "",
            "TCURRENCY":  "",
            "TCURRATE":   "",
            "TCURAMN":    "",
            "TAMOUNT":    montant_str,
            "TREMINT":    ref_int,
            "TREMEXT":    ref_bob,
            "TMATCHNO":   "",
            "TINTMODE":   "S",          # S = standard
            "TISBLOCKED": "",
            "TINVVCS":    ref_vcs,
        })

    table.close()


# ── Génération de Lfac.dbf ───────────────────────────────────

def _ecrire_lfac(paiements, chemin):
    """
    1 ligne par paiement (même TDOCNO que dans HFac).
    Champs clés :
        TACCOUNT   → compte comptable de l'activité (ex : 701003)
        TAMOUNT    → montant
        TDC        → C = Crédit (recette pour l'école)
        TREM       → titre de l'activité (max 40 caractères)
        TBASVAT    → base TVA = montant (pas de TVA pour l'école)
        TVATTOTAMN → total TVA = 0
    """

    table = dbf.Table(chemin, CHAMPS_LFAC, codepage="cp1252")
    table.open(dbf.READ_WRITE)

    for num, paiement in enumerate(paiements, start=1):

        ae       = paiement.activite_eleve
        activite = ae.activite

        date_obj = paiement.paye_le or datetime.now()
        annee    = str(date_obj.year)
        mois     = date_obj.strftime("%m")

        # Compte comptable : celui de l'activité ou le défaut
        compte = activite.bob50_compte_comptable or BOB50_COMPTE_DEFAUT

        # Description tronquée à 40 caractères (limite du champ TREM)
        description = (activite.titre or "")[:40]

        montant_str = _formater_montant(paiement.montant)

        table.append({
            "TDBK":       BOB50_JOURNAL,
            "TFYEAR":     annee,
            "TYEAR":      annee,
            "TMONTH":     mois,
            "TDOCNO":     str(num),
            "TDOCLINE":   "1",
            "TTYPELINE":  "S",          # S = standard
            "TACTTYPE":   "A",          # A = compte général
            "TACCOUNT":   compte,
            "TMATCHNO":   "",
            "TCURAMN":    "",
            "TAMOUNT":    montant_str,
            "TCBVAT":     "",
            "TBASVAT":    montant_str,  # base TVA = montant (TVA = 0 pour l'école)
            "TVCTOTAMN":  "",
            "TVATTOTAMN": "0",          # total TVA = 0
            "TCURVATAMN": "",
            "TVATAMN":    "0",          # montant TVA = 0
            "TVCDBLAMN":  "",
            "TVATDBLAMN": "",
            "TBASLSTAMN": montant_str,  # base liste = montant
            "TVSTORED":   "",
            "TDC":        "C",          # C = Crédit (recette)
            "TREM":       description,
            "COST_REP":   "",
            "COST_CRIT1": "", "COST_CRIT2": "", "COST_CRIT3": "",
            "COST_CRIT4": "", "COST_CRIT5": "", "COST_CRIT6": "",
            "COST_CRIT7": "", "COST_CRIT8": "", "COST_CRIT9": "",
            "COST_CRITA": "",
            "TFREEINFO1": "", "TFREEINFO2": "",
            "TDOCDATE":   "",
            "COST_1": "", "COST_2": "", "COST_3": "", "COST_4": "",
        })

    table.close()


# ── Fonctions utilitaires ────────────────────────────────────

def _recuperer_bob50_compte(eleve):
    """
    Récupère le numéro de compte Bob50 du premier parent
    de l'élève qui en a un renseigné.
    Retourne "" si aucun parent n'a de bob50_compte.
    """
    for lien in eleve.liens_parents:
        parent = lien.parent
        if parent and parent.bob50_compte:
            return str(parent.bob50_compte)
    return ""


def _formater_montant(montant):
    """
    Formate un montant Numeric(8,2) en chaîne pour Bob50.
    Bob50 belge utilise la virgule comme séparateur décimal.

    Exemples :
        37.00  →  "37"
        12.50  →  "12,5"
        4.50   →  "4,5"
    """
    if montant is None:
        return "0"
    valeur = float(montant)
    if valeur == int(valeur):
        return str(int(valeur))
    return str(valeur).replace(".", ",")
