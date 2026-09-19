"""Barèmes belges — données réglementaires isolées et sourcées.

Règle du projet : zéro chiffre inventé. Tout barème non sourcé reste à None
et le moteur traite la valeur correspondante comme une ENTRÉE fournie.
"""
from decimal import Decimal as D

# --- ONSS : cotisation personnelle travailleur (employé) ---------------------
# Source : socialsecurity.be (DmfA) — taux confirmé 2026.
ONSS_TAUX = D("0.1307")

# --- Bonus à l'emploi SOCIAL (réduction de l'ONSS personnel) -----------------
# Bonus de BASE = volet A + volet B. Salaire de référence S = salaire brut du mois
# à 100 %. Source : instructions administratives ONSS DmfA 2026.
WORK_BONUS_BAREMES = {
    # Fiche oracle SD Worx de mars 2026 : garde le calcul historique intact.
    "2026-03-01": {
        "employe": {
            "A": {"S0": D("2833.36"), "S1": D("3336.98"), "R": D("123.00"), "alpha": D("0.2442")},
            "B": {"S0": D("2218.73"), "S1": D("2833.36"), "R": D("165.87"), "alpha": D("0.2699")},
        },
        "ouvrier": {
            "A": {"S0": D("2833.36"), "S1": D("3336.98"), "R": D("132.84"), "alpha": D("0.2638")},
            "B": {"S0": D("2218.73"), "S1": D("2833.36"), "R": D("179.14"), "alpha": D("0.2915")},
        },
    },
    # Instructions ONSS : montants applicables à partir du 1er avril 2026.
    "2026-04-01": {
        "employe": {
            "A": {"S0": D("2880.32"), "S1": D("3336.98"), "R": D("125.04"), "alpha": D("0.2738")},
            "B": {"S0": D("2255.50"), "S1": D("2880.32"), "R": D("168.62"), "alpha": D("0.2699")},
        },
        "ouvrier": {
            "A": {"S0": D("2880.32"), "S1": D("3336.98"), "R": D("135.04"), "alpha": D("0.2957")},
            "B": {"S0": D("2255.50"), "S1": D("2880.32"), "R": D("182.11"), "alpha": D("0.2915")},
        },
    },
}

# Compatibilité avec le moteur de validation historique (mars 2026, employés).
WORK_BONUS_A = WORK_BONUS_BAREMES["2026-03-01"]["employe"]["A"]
WORK_BONUS_B = WORK_BONUS_BAREMES["2026-03-01"]["employe"]["B"]


def work_bonus_bareme(periode_debut: str = "", ouvrier: bool = False) -> dict:
    """Retourne le barème bonus emploi selon la date de début de période."""
    parts = (periode_debut or "").split("/")
    ymd = f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else "2026-03-01"
    cle = "2026-04-01" if ymd >= "2026-04-01" else "2026-03-01"
    statut = "ouvrier" if ouvrier else "employe"
    return WORK_BONUS_BAREMES[cle][statut]

# Bonus à l'emploi FISCAL = pourcentage du bonus social (réduit le précompte).
WORK_BONUS_FISCAL_PCT = {"A": D("0.3314"), "B": D("0.5254")}  # bas / très bas salaires

# RENFORCEMENT 2026 (« bonus de travail supplémentaire ») : NON SOURÇABLE.
# La législation 2026 n'est pas finalisée (cf. Liantis) → aucune source officielle
# ne publie sa formule. Sur la fiche réelle, base + renforcement = 177,25 € alors
# que le bonus de base seul = 90,16 €. Ce supplément reste donc une ENTRÉE fournie,
# à calculer dès que la méthodologie officielle sera publiée.
WORK_BONUS_RENFORCEMENT_2026 = None

# --- Précompte professionnel : barème de base (Annexe 1, formule-clé 2026) ---
# Source : SPF Finances, formule-clé ESS-SR/2025-0928, rémunérations payées à
# partir du 1er janvier 2026. Les +7 % d'additionnels communaux sont déjà intégrés.
# Tranches : (plafond, taux, impôt cumulé jusqu'au plafond précédent). None = dernière.
BAREME_BASE = [
    (D("16710"), D("0.2675"), D("0")),
    (D("29500"), D("0.4280"), D("4469.93")),
    (D("51050"), D("0.4815"), D("9944.05")),
    (None,       D("0.5350"), D("20320.38")),
]

# Frais professionnels forfaitaires (travailleurs salariés) : 30 % plafonnés à 6.070.
FRAIS_FORFAIT_TAUX = D("0.30")
FRAIS_FORFAIT_MAX = D("6070")
FRAIS_FORFAIT_SEUIL = D("20233.33")

# Impôt sur la quotité du revenu exemptée d'impôt (à déduire de l'impôt de base).
# Valeurs du 1er janvier 2026 (quotité = 11.170 €).
# ATTENTION : la fiche de mars 2026 applique la RÉFORME De Wever (exempt relevé,
# ~16.650 €), NON ENCORE PUBLIÉE par le SPF Finances (seule la version 1er janvier
# existe, et elle annonce p.4 être « adaptée en cours d'année 2026 »).
# => valeur réformée injectable en paramètre tant qu'elle n'est pas officielle.
IMPOT_EXEMPTE_ISOLE = D("2987.98")   # isolé ou conjoint avec revenus propres
IMPOT_EXEMPTE_MARIE = D("5975.96")   # conjoint sans revenus propres (2× l'exempt)

# --- Cotisation spéciale de sécurité sociale (CSSS) --------------------------
# Cotisation TRIMESTRIELLE (avances mensuelles, régularisation au 3e mois).
# Barème isolé (ou conjoint sans revenus propres), assis sur la rému TRIMESTRIELLE :
#   ≤ 3.285,28           → 0
#   3.285,29 – 5.836,13  → 27,90 (fixe)
#   5.836,14 – 6.570,54  → 7,6 % de l'excédent (max 55,80)
#   6.570,55 – 18.116,46 → 55,80 + 1,1 % de l'excédent (max 182,82)
#   > 18.116,47          → 182,82
# NON ENCODÉ comme calcul validé, pour deux raisons :
#   1) ces seuils sont ceux de 2022 (Securex) — à réindexer pour 2026 ;
#   2) la fiche de mars (mois 3) affiche 14,48 € qui est une RÉGULARISATION
#      trimestrielle (dépend des avances jan./fév.), non reproductible depuis
#      un seul mois. Le calcul régulier donnerait ~27 €/mois pour ce profil.
# => La CSSS reste une ENTRÉE fournie tant qu'on n'a pas les seuils 2026 + le
#    contexte trimestriel.
CSSS_BAREME = None
