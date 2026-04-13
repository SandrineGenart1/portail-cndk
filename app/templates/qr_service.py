"""
qr_service.py — Génération de QR codes EPC (virement bancaire)
---------------------------------------------------------------
Le format EPC (European Payments Council) est le standard européen
reconnu par toutes les apps bancaires belges :
BNP Paribas Fortis, ING, KBC, Belfius, Argenta, Fintro, Hello Bank...

Le parent scanne le QR code avec son app bancaire et le virement
est pré-rempli automatiquement (IBAN, montant, communication).

Référence standard : https://www.europeanpaymentscouncil.eu/
"""

import qrcode
import qrcode.constants
import io
import base64
import re
from decimal import Decimal


# ── Configuration de l'école ────────────────────────────────────────────────
# À déplacer dans config.py / .env en production

ECOLE_NOM          = "Collège de Kain ASBL"
ECOLE_IBAN         = "BE00 0000 0000 0000"   # ← Remplacer par le vrai IBAN
ECOLE_BIC          = "GEBABEBB"              # ← BIC de la banque (optionnel EPC v2)


# ── Génération de la référence structurée ───────────────────────────────────

def generer_reference(activite_id: int, eleve_id: int) -> str:
    """
    Génère une communication structurée belge au format +++XXX/XXXX/XXXXX+++
    Basée sur l'activité et l'élève, avec chiffre de contrôle modulo 97.

    Exemple : +++001/0042/00013+++
    """
    # Base numérique : activite_id (3 chiffres) + eleve_id (4 chiffres)
    base = f"{activite_id:03d}{eleve_id:04d}"

    # Chiffre de contrôle modulo 97 (norme belge)
    # Le reste de la division par 97 donne 2 chiffres de contrôle
    # Si le reste est 0, on utilise 97
    reste = int(base) % 97
    if reste == 0:
        reste = 97

    reference = f"{activite_id:03d}/{eleve_id:04d}/{reste:05d}"
    return f"+++{reference}+++"


def reference_vers_texte(reference: str) -> str:
    """Retire les +++ pour affichage : +++001/0042/00013+++ → 001/0042/00013"""
    return reference.replace("+", "")


# ── Construction du payload EPC ─────────────────────────────────────────────

def construire_payload_epc(
    montant: float,
    reference: str,
    description: str = ""
) -> str:
    """
    Construit le payload texte au format EPC QR Code Version 2.
    
    Structure (une ligne par champ, ordre strict) :
        BCD           ← Service Tag
        002           ← Version
        1             ← Character set (UTF-8)
        SCT           ← Identification (SEPA Credit Transfer)
        BIC           ← BIC bénéficiaire (optionnel v2)
        Nom           ← Nom bénéficiaire (max 70 car.)
        IBAN          ← IBAN bénéficiaire (sans espaces)
        EUR0.00       ← Montant (EUR + valeur sans virgule ni espace)
                      ← Purpose (vide)
        Référence     ← Communication structurée OU
                      ← Remittance information (texte libre)
        Description   ← Info affichée dans l'app (max 70 car.)
    """
    # Nettoyage de l'IBAN (supprimer espaces)
    iban_propre = ECOLE_IBAN.replace(" ", "")

    # Montant au format EPC : EUR suivi du montant avec point décimal
    # Ex : 12.50 → "EUR12.50", 5.00 → "EUR5.00"
    montant_decimal = Decimal(str(montant)).quantize(Decimal("0.01"))
    montant_epc = f"EUR{montant_decimal}"

    # Description tronquée à 70 caractères
    desc = description[:70] if description else ""

    payload = "\n".join([
        "BCD",           # Service Tag
        "002",           # Version EPC
        "1",             # UTF-8
        "SCT",           # SEPA Credit Transfer
        ECOLE_BIC,       # BIC (optionnel mais recommandé)
        ECOLE_NOM[:70],  # Nom bénéficiaire
        iban_propre,     # IBAN sans espaces
        montant_epc,     # Montant
        "",              # Purpose (vide)
        reference,       # Communication structurée
        desc,            # Remittance info / description affichée
    ])

    return payload


# ── Génération du QR code ───────────────────────────────────────────────────

def generer_qr_code_png(
    activite_id: int,
    eleve_id: int,
    montant: float,
    description: str = ""
) -> tuple[bytes, str]:
    """
    Génère un QR code EPC et retourne :
    - les bytes PNG du QR code
    - la référence structurée générée

    Utilisation dans une route Flask :
        png_bytes, reference = generer_qr_code_png(1, 42, 12.50, "Voyage Paris")
        return send_file(io.BytesIO(png_bytes), mimetype='image/png')
    """
    reference = generer_reference(activite_id, eleve_id)
    payload   = construire_payload_epc(montant, reference, description)

    qr = qrcode.QRCode(
        version=None,           # Taille calculée automatiquement
        error_correction=qrcode.constants.ERROR_CORRECT_M,  # ~15% correction
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    png_bytes = buffer.getvalue()

    return png_bytes, reference


def generer_qr_code_base64(
    activite_id: int,
    eleve_id: int,
    montant: float,
    description: str = ""
) -> tuple[str, str]:
    """
    Génère un QR code EPC et retourne :
    - une chaîne base64 utilisable directement dans un <img src="data:...">
    - la référence structurée générée

    Utilisation dans un template Jinja2 :
        <img src="data:image/png;base64,{{ qr_b64 }}">
    """
    png_bytes, reference = generer_qr_code_png(
        activite_id, eleve_id, montant, description
    )
    b64 = base64.b64encode(png_bytes).decode("utf-8")
    return b64, reference
