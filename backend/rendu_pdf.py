"""Rendu PDF d'une fiche de paie belge — flux complet : lignes → moteur → gabarit.

Les lignes du bulletin sont la source unique : le moteur les agrège et calcule
les sous-totaux (montant brut, imposable, salaire net, montant net), et le
gabarit affiche les lignes + ces sous-totaux calculés. Changer une ligne
d'entrée recalcule et met à jour le PDF automatiquement.

Données de l'oracle SD Worx mars 2026, identité NEUTRALISÉE (pas de PII réelle).
"""
from decimal import Decimal as D
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from moteur_be import Cat, Ligne, agreger, calculer
from formats import eur_be as fmt

TEMPLATES = Path(__file__).parent / "templates"


# Lignes du bulletin (entrées) — dans l'ordre d'affichage de la fiche.
LIGNES_ORACLE = [
    Ligne("1011", "salaire brut", D("2963.81"), Cat.BRUT),
    Ligne("17C1", "supplément direct 50%", D("1.07"), Cat.BRUT),
    Ligne("1723", "supplément direct extra-légal", D("2.96"), Cat.BRUT),
    Ligne("2500", "cotisation de sécurité sociale (onss)  (Base : 2.967,84)", D("-387.90"), Cat.ONSS),
    Ligne("2506", "bonus de travail supplémentaire", D("56.66"), Cat.BONUS),
    Ligne("2509", "bonus à l'emploi", D("120.59"), Cat.BONUS),
    Ligne("3500", "précompte sur rémunérations normales  (Base : 2.757,19)", D("-368.95"), Cat.PRECOMPTE),
    Ligne("3700", "diminution de précompte pour surtravail", D("1.24"), Cat.RED_PRECOMPTE),
    Ligne("3702", "bonus de travail fiscal", D("39.96"), Cat.RED_PRECOMPTE),
    Ligne("3704", "bonus de travail fiscal supplémentaire", D("29.77"), Cat.RED_PRECOMPTE),
    Ligne("3010", "abonnement social transport privé", D("65.83"), Cat.AVANTAGE),
    Ligne("3101", "indemnité de vêtements", D("18.00"), Cat.AVANTAGE),
    Ligne("3650", "cotisation spéciale de sécurité sociale", D("-14.48"), Cat.CSSS),
    Ligne("3970", "contribution person. chèques repas €1,09/chèque", D("-19.62"), Cat.CHEQUE),
    Ligne("3802", "acompte", D("-350.00"), Cat.ACOMPTE),
]

# Sections : (catégories, libellé du sous-total, attribut du Resultat, type d'affichage)
SECTIONS = [
    ([Cat.BRUT], "montant brut", "montant_brut", "subtotal"),
    ([Cat.ONSS, Cat.BONUS], "imposable", "imposable", "subtotal"),
    ([Cat.PRECOMPTE, Cat.RED_PRECOMPTE, Cat.AVANTAGE, Cat.CSSS, Cat.CHEQUE],
     "salaire net", "salaire_net", "subtotal"),
    ([Cat.ACOMPTE], "montant net", "montant_net", "final"),
]


def construire_lignes(lignes, resultat):
    """Interleave les lignes de détail et les sous-totaux calculés par le moteur."""
    out = []
    for cats, libelle, attr, type_ in SECTIONS:
        for l in lignes:
            if l.cat in cats:
                out.append({"code": l.code, "desc": l.desc, "montant": fmt(l.montant), "type": "detail"})
        out.append({"code": "", "desc": libelle, "montant": fmt(getattr(resultat, attr)), "type": type_})
    return out


# Identité par défaut (oracle, neutralisée). L'API peut surcharger chaque bloc.
IDENTITE_DEFAUT = {
    "employeur": {
        "nom": "EMPLOYEUR EXEMPLE SA", "adresse": "Rue de l'Exemple 90",
        "cp_ville": "9820 MERELBEKE-MELLE", "numero": "1AL0000",
    },
    "periode": {"debut": "01/03/2026", "fin": "31/03/2026", "calcul": "30/03/2026"},
    "perso": {"niss": "00.00.00-000.00", "etat_civil": "célibataire", "charges": "aucune"},
    "contrat": {
        "num_travailleur": "0000000", "statut": "employé(e)", "fonction": "caissière",
        "soumis": "à l'onss, au précompte professionnel",
        "date_entree": "12/06/2025", "cp": "202.001",
    },
    "salarie": {"nom": "NOM Prénom", "adresse": "Rue Exemple 1", "cp_ville": "4000 LIÈGE"},
    "verse": {"iban": "BE00 0000 0000 0000", "bic": "XXXXBEBB"},
    "pagination": "1AL0000/0000000   1/3",
}


def donnees(lignes=LIGNES_ORACLE, identite=None) -> dict:
    """Construit le dict du gabarit : identité (surchargeable) + calcul du moteur."""
    d = {**IDENTITE_DEFAUT, **(identite or {})}
    resultat = calculer(agreger(lignes))
    base = next(l.montant for l in lignes if l.cat == Cat.BRUT)
    d["base"] = fmt(base)
    d["lignes"] = construire_lignes(lignes, resultat)
    d["verse"] = {**d["verse"], "montant": fmt(resultat.montant_net)}
    return d


def rendre_bytes(donnees_dict) -> bytes:
    """Rend le gabarit en PDF (octets) — utilisé par l'API."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    html = env.get_template("fiche_be.html").render(**donnees_dict)
    return HTML(string=html).write_pdf()


def rendre(sortie="/tmp/fiche_be_rendu.pdf") -> str:
    with open(sortie, "wb") as f:
        f.write(rendre_bytes(donnees()))
    return sortie


if __name__ == "__main__":
    r = calculer(agreger(LIGNES_ORACLE))
    print(f"Moteur : brut {r.montant_brut} | imposable {r.imposable} | "
          f"net {r.salaire_net} | versé {r.montant_net}")
    print("PDF généré :", rendre())
