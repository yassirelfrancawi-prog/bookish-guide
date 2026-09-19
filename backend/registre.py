"""Registre des templates : (clé) → PDF source, carte de champs, mapper moteur→champs.

Pour ajouter un template : déposer son PDF échantillon, déclarer ses repères
(texte à localiser + alignement [+ mode]) et un mapper qui transforme le Resultat
du moteur + les lignes + l'identité en valeurs de champs.
"""
import calendar
from dataclasses import dataclass, field
from pathlib import Path

from decimal import Decimal as D

from composer import _d
from formats import eur_be
from overlay import Champ, carte_depuis_echantillon

RACINE = Path(__file__).resolve().parent.parent / "bordelpdf"


@dataclass
class Template:
    nom: str
    pdf: Path
    reperes: dict          # {champ_logique: (texte, align[, mode])}
    mapper: object = None  # callable(resultat, identite, lignes) -> {champ: str}  (pipeline Cat/Ligne)
    mapper_config: object = None  # callable(fiche_composer, cfg) -> {champ: str}  (pipeline composer)
    periode: object = None  # callable(annee, mois) -> {champ: str} (pour le multi-mois)
    page_index: int = 0    # page où se trouve le décompte (0 par défaut)
    employeur_fixe: dict = field(default_factory=dict)  # info affichée au front : « employeur baked into PDF »
    supporte_atn: bool = False  # le sample du PDF contient-il des lignes ATN remplissables ?
    supporte_cheques_repas: bool = False
    supporte_fpe: bool = False
    pages_a_garder: list = None  # indices des pages à conserver (None = toutes). Les autres pages
                                  # (suite/planning/courrier) sont SUPPRIMÉES pour ne pas afficher
                                  # de données résiduelles du sample (matricule/nom d'origine).
    _champs: list = field(default=None, init=False, repr=False)

    def champs(self) -> list[Champ]:
        if self._champs is None:
            self._champs = carte_depuis_echantillon(str(self.pdf), self.reperes, self.page_index)
        return self._champs


def _periode_sdworx(annee: int, mois: int) -> dict:
    dernier = calendar.monthrange(annee, mois)[1]
    return {"periode_debut": f"01/{mois:02d}/{annee}", "periode_fin": f"{dernier:02d}/{mois:02d}/{annee}"}


def _periode_cpas(annee: int, mois: int) -> dict:
    return {"periode": f"Période : {mois:02d}/{annee}"}


def _periode_securex(annee: int, mois: int) -> dict:
    # Format Securex : un seul span « 01.MM.AAAA-DD.MM.AAAA ».
    dernier = calendar.monthrange(annee, mois)[1]
    return {"periode": f"01.{mois:02d}.{annee}-{dernier:02d}.{mois:02d}.{annee}"}


# Repères SD Worx — page 1. Lignes localisées par leur DESCRIPTION (mode « ligne »).
_REPERES_SDWORX = {
    # Identité (à neutraliser/remplacer)
    "nom": ("KASHOURA", "left"),
    "niss": ("800407", "left"),
    "adresse_rue": ("GEORGES", "left"),
    "adresse_ville": ("4020", "left"),
    "periode_debut": ("01/03/2026", "left", "sous"),
    "periode_fin": ("31/03/2026", "left", "sous"),
    "date_calcul": ("30/03/2026", "left", "sous"),
    "iban": ("BE05", "left"),
    # Données personnelles (libellé : valeur sur la même rangée)
    "etat_civil": ("État civil:", "left", "apres"),
    "personnes_charge": ("Personnes à charge:", "left", "apres"),
    "statut_contrat": ("Statut:", "left", "apres"),
    "fonction": ("Fonction:", "left", "apres"),
    # Données du contrat (libellé unique → valeur de la rangée, alignée à gauche)
    "num_travailleur": ("Numéro travailleur", "left", "ligne"),
    "num_gps": ("Numéro GPS", "left", "ligne"),
    "fonction": ("Fonction", "left", "ligne"),
    "date_entree": ("Date d'entrée", "left", "ligne"),
    "date_anciennete": ("Date d'ancienneté", "left", "ligne"),
    "cp": ("Commission paritaire", "left", "ligne"),
    # Sous-totaux + bases dérivées
    "salaire_base": ("2.963,81", "left", "sous"),
    "montant_brut": ("2.967,84", "right"),
    "base_onss": ("2.967,84", "left", "sous"),
    "imposable": ("2.757,19", "right"),
    "base_prec": ("2.757,19", "left", "sous"),
    "salaire_net": ("2.508,94", "right"),
    "montant_net": ("montant net", "right", "ligne"),
    # Montants des lignes (libellé de rangée → valeur, colonne montants à droite)
    "l_1011": ("salaire brut", "right", "ligne"),
    "l_17C1": ("supplément direct 50%", "right", "ligne"),
    "l_1723": ("extra-légal", "right", "ligne"),
    "l_2500": ("(onss)", "right", "ligne"),
    "l_2506": ("bonus de travail supplémentaire", "right", "ligne"),
    "l_2509": ("bonus à l'emploi", "right", "ligne"),
    "l_3500": ("précompte sur rémunérations", "right", "ligne"),
    "l_3700": ("diminution de précompte", "right", "ligne"),
    "l_3702": ("bonus de travail fiscal", "right", "ligne"),
    "l_3704": ("bonus de travail fiscal supplémentaire", "right", "ligne"),
    "l_3010": ("abonnement social", "right", "ligne"),
    "l_3101": ("indemnité de vêtements", "right", "ligne"),
    "l_3650": ("cotisation spéciale", "right", "ligne"),
    "l_3970": ("chèques repas", "right", "ligne"),
    # Lignes à effacer pour cohérence avec les entrées Certifio :
    "l_3802": ("acompte", "right", "ligne"),
    "total_verse": ("versé au compte IBAN", "right", "ligne"),
    # Résidus identité sample (KASHOURA / IBAN BE05 / matricule 3253124) à effacer :
    "verse_label": ("versé au compte IBAN:", "left", "sous"),
    "bic": ("BIC: BBRUBEBB", "left"),
    "matricule_haut": ("1AL1388 / 3253124", "left"),
    "matricule_bas": ("1AL1388-3253124-30/03/2026", "left"),
    "pagination": ("1/3", "left", "sous"),
}


# --- Répères SD Worx B B PHARMA (fiche DIRIGEANT) ---------------------------
# Layout SD Worx mais profil dirigeant : code 1010 (rémunération brute dirigeant),
# pas d'ONSS, cotisations INASTI en ligne 2240, ATN (Porsche, téléphone, logement,
# internet) en imposable puis re-déduits du net. Sample : Boulal Nassima.
_REPERES_SDWORX_BBPHARMA = {
    # Identité (anchors sur les valeurs uniques du sample)
    "nom": ("Boulal", "left"),
    "niss": ("78102742882", "left"),
    "adresse_rue": ("Kuikenstraat", "left"),
    "adresse_ville": ("1620 Drogenbos", "left"),
    "periode_debut": ("01/01/2026", "left", "sous"),
    "periode_fin": ("31/01/2026", "left", "sous"),
    "date_calcul": ("28/01/2026", "left", "sous"),
    # Données personnelles
    "etat_civil": ("État civil:", "left", "apres"),
    "personnes_charge": ("Personnes à charge:", "left", "apres"),
    # Sous-totaux et lignes clés (libellé en mode ligne → distingue le « Net » de la
    # table du « € 2069.27 » bas de page qui partagent la même valeur dans le sample).
    "imposable": ("Imposable", "right", "ligne"),
    "salaire_net": ("Net", "right", "ligne"),
    "l_1010": ("Rémunération brute", "right", "ligne"),
    "l_3500": ("Précompte professionnel", "right", "ligne"),
    # Lignes ATN/cotisations imposable (ancres par libellé en mode « ligne » : la
    # première occurrence du libellé est dans la section imposable, la deuxième
    # dans la section net — on prend la première).
    "l_atn1_imp": ("Téléphonie (Téléphone)", "right", "ligne"),
    "l_atn2_imp": ("Habitation (Logement)", "right", "ligne"),
    "l_atn3_imp": ("Internet (Internet)", "right", "ligne"),
    "l_atn4_imp": ("Cotisations sociales", "right", "ligne"),
    "l_atn5_imp": ("Voiture de société", "right", "ligne"),
    # Libellés « Voiture de société (Porsche) » du sample : on les remplace par défaut
    # par « Voiture de société » seul (sinon le modèle Porsche de Boulal reste affiché).
    "l_voiture_libelle_imp": ("Voiture de société (Porsche)", "left", "sous", "top"),
    "l_voiture_libelle_net": ("Voiture de société (Porsche)", "left", "sous", "bottom"),
    "info_cheques": ("Nombre de chèques-repas : 20", "left", "sous"),
    # Lignes ATN/cotisations net (déductions, signe inclus pour les distinguer)
    "l_atn1_net": ("-7.00", "right"),
    "l_atn2_net": ("-128.98", "right"),
    "l_atn3_net": ("-5.00", "right"),
    "l_atn4_net": ("-543.84", "right"),
    "l_atn5_net": ("-273.14", "right"),
    "l_3970": ("-21.80", "right"),
    "l_3330": ("250.00", "right"),
    # Total final « € 2069.27 » : ancré par le « € » qui le précède
    "total_final": ("€", "right", "apres"),
    "footer_ref": ("1BB2807-138482-28/01/2026", "left", "sous"),
}


def _mapper_sdworx(resultat, identite: dict, lignes) -> dict:
    """Resultat + lignes + identité → valeurs des champs SD Worx (bases dérivées incluses)."""
    valeurs = {
        "montant_brut": eur_be(resultat.montant_brut),
        "base_onss": eur_be(resultat.montant_brut),   # ONSS calculé sur le brut
        "imposable": eur_be(resultat.imposable),
        "base_prec": eur_be(resultat.imposable),       # précompte calculé sur l'imposable
        "salaire_net": eur_be(resultat.salaire_net),
        "montant_net": eur_be(resultat.montant_net),
    }
    for l in lignes:                                   # chaque ligne → son champ par code
        valeurs[f"l_{l.code}"] = eur_be(l.montant)
    valeurs.update(identite or {})                     # nom, adresse, iban… passés tels quels
    return valeurs


# Repères CPAS Verviers — layout public différent, polices Arial embarquées.
# Spécimen à 0,00 → on localise par libellé (mode « apres ») et par texte embarqué.
_REPERES_CPAS = {
    "matricule": ("Matricule", "left", "apres"),
    "registre_national": ("N° registre national", "left", "apres"),
    "situation_fiscale": ("Situation fiscale", "left", "apres"),
    "entre_le": ("01/10/2016", "left", "sous"),
    "nom": ("BOUHAMID", "left"),
    "adresse_rue": ("Princes", "left"),
    "adresse_ville": ("4800 Verviers", "left"),
    "periode": ("Période", "left"),  # span combiné « Période : MM/AAAA » → valeur complète
    "index": ("Index", "left", "apres"),
    "brut_total": ("1 - Brut total", "left", "apres"),
    # Ligne résumé : valeurs EN DESSOUS des libellés
    "resume_brut": ("Brut total (1)", "left", "dessous"),
    "resume_cotsoc": ("Cot.Soc", "left", "dessous"),
    "resume_precompte": ("Précompte (4)", "left", "dessous"),
    "net_paye": ("Net payé", "left", "dessous"),
    # Dates en haut à droite (sample 02/2024 BOUHAMID) : libellé inclus dans le span,
    # on overlay tout le span pour rester cohérent avec la période choisie.
    "date_emission": ("Date : 23/03/2026", "left"),
    "paie_du": ("Paie du 27/02/2024", "left"),
    "exploit_de": ("Expl. de 02/2024", "left"),
    # Résidus BOUHAMID à effacer (libellé inclus dans le span) :
    "cie_assurances": ("Cie d'assurances : ETHIAS", "left"),
    "fonction_cpas": ("Aide-soignant(e) - D2 - Tripartite", "left"),
    "paie_du_avec_heure": ("Paie du 27/02/2024 16:08", "left"),
    "fonction_code_cpas": ("Fonction 04", "left", "sous"),
    "anciennete_pecuniaire": ("Ancienneté pécuniaire : 0 an(s) 8 mois", "left", "sous"),
    "conjoint_info": ((55.80, 157.48, 226.99, 166.46), "left", "zone"),
    "traitement_ligne": ("Traitement, salaire, appointements (fonction 04)", "left", "sous"),
    "calendrier_mois": ((34.20, 236.46, 59.19, 244.23), "left", "zone"),
    "cal_jour_29": ((510.84, 236.46, 518.54, 244.23), "left", "zone"),
    "cal_jour_30": ((526.68, 236.46, 534.38, 244.23), "left", "zone"),
    "cal_jour_31": ((542.40, 236.46, 550.10, 244.23), "left", "zone"),
    "cal_cyc_contr_values": ((66.80, 247.62, 506.00, 255.39), "left", "zone"),
    "cal_cyc_hab_values": ((66.80, 257.34, 506.00, 265.11), "left", "zone"),
    "cal_n10_code": ("N10(1)", "left", "sous"),
    "cal_n10_values": ((56.00, 267.06, 506.00, 274.83), "left", "zone"),
    "cal_preste_flag": ((56.00, 276.78, 60.50, 284.55), "left", "zone"),
    "barcode_data": ("8550_8443_1769_202402", "left", "sous"),
    "barcode_central": ((222.00, 708.00, 358.00, 772.00), "left", "zone"),
    "barcode_bas_gauche": ((19.00, 803.00, 143.00, 829.00), "left", "zone"),
    "pagination_haut": ("1 - 1/1 - 1/3", "left", "sous"),
    "pagination_bas": ("Page 1 / 3", "left", "sous"),
}


# Repères Securex — billet de paie (page 2). Layout inversé / SD Worx :
# code | jours | heures | coeff | MONTANT | libellé → mode « avant » pour les
# montants (valeur À GAUCHE du libellé). Page 1 = couverture, ignorée.
_REPERES_SECUREX = {
    # Période salariale (un seul span unique au format « 01.MM.AAAA-DD.MM.AAAA »)
    "periode": ("01.12.2023-31.12.2023", "left"),
    # Identité salarié (en haut à droite) — un grand rect englobant « Madame + nom »
    # pour éviter le décalage visuel (DUPONT alignait sur le E de Liège).
    "nom_complet_haut": ("Madame KARAKAYA REMZIYE", "left", "sous"),
    "prenom_residu": ("REMZIYE", "left"),  # span d'origine REMZIYE seul, à effacer
    "adresse_rue": ("RUE DU PARADIS 116", "left", "sous"),
    "adresse_ville": ("4800 VERVIERS", "left", "sous", "bottom"),
    "naissance": ("02.01.1983", "left"),
    "registre_national": ("830102-312-20", "left", "sous"),
    # Résidus admin/contractuels du sample Remziye à effacer
    "date_emission_haut": ("22/12/2023", "left"),
    "bce_employeur": ("0779470422", "left"),
    "ref_calcul": ("1231222-094111", "left"),
    "dernier_traitement": ("22.12.2023-10.31.24", "left"),
    "date_en_service": ("En service", "left", "apres"),
    "date_anc_firme": ("Anc. firme", "left", "apres"),
    "date_anc_secteur": ("Anc. secteur", "left", "apres"),
    # Tableau « Charges fiscales » au milieu : valeurs à overlay selon la situation
    "enfants_normales": ("Enfants", "left", "apres"),
    "enfants_handicapes": ("Enfants", "left", "apres", "last"),
    "conjoint_normales": ("Conjoint", "left", "apres"),
    "conjoint_handicapes": ("Conjoint", "left", "apres", "last"),
    "cp_code": ("121.000", "left"),
    "cp_desc": ("Entreprise de nettoyage et de désinfection", "left", "sous"),
    "qualif_prof_code": ("Catégorie 1 A", "left", "sous"),
    "qualif_prof_desc": ("Catégorie 1 A - Nettoyage habituel", "left", "sous"),
    "fonction_securex": ("NETTOYAGE CAT", "left", "sous"),
    # Statut (grille du milieu, spans Courier)
    "statut": ("Ouvrier", "left"),
    "etat_civil": ("Marié(e)", "left"),
    # Rémunération de base (libellé À GAUCHE → valeur à droite)
    "remuneration_base": ("Rémunération de base", "right", "apres"),
    # Table montants : libellé À DROITE → montant en mode « avant ».
    # Le mode utilise search_for → ancres multi-mot OK ; mots intermédiaires (« Jour »
    # avant « férié ») et décorations « ** » sont neutralisés.
    "l_brut_total": ("Total brut soumis ONSS", "right", "avant"),
    "l_onss_perso": ("Retenue ONSS personnelle", "right", "avant"),
    "l_bonus_emploi": ("Bonus à l'emploi", "right", "avant"),
    "l_imposable": ("Imposable", "right", "avant"),
    "l_precompte": ("Précompte professionnel", "right", "avant"),
    "l_jour_ferie": ("Jour férié", "right", "avant"),
    "l_frais_vetements": ("Frais forf", "right", "avant"),
    "l_rgpt": ("Indemnité R.G.P.T", "right", "avant"),
    "l_net_payer": ("Net à payer", "right", "avant"),
    "l_brut_onss_108": ("Brut ONSS 108", "right", "avant"),
    "l_onss_patronale": ("Cotisation ONSS patronale", "right", "avant"),
    # Ligne 000 (Rémunération CAT) du décompte : ancrée par la valeur unique du sample.
    "l_table_remu": ("153,46", "right"),
    # « ** Net » (sous-total avant indemnités) et « A payer par l'employeur » (doublon
    # du net à payer) : ancrés par leur libellé unique sur la fiche.
    "l_table_net": ("** Net", "right", "avant"),
    "l_net_employeur": ("A payer par", "right", "avant"),
    "nom_paiement": ("KARAKAYA REMZIYE", "left", "sous", "bottom"),
    # Résidus de lignes détail du sample quand le composer ne fournit pas ces lignes.
    "l_table_remu_code": ((49.44, 416.84, 65.28, 427.83), "left", "zone"),
    "l_table_remu_jours": ((86.40, 416.84, 91.68, 427.83), "left", "zone"),
    "l_table_remu_heures": ((118.08, 416.84, 139.20, 427.83), "left", "zone"),
    "l_table_remu_label": ("Rémunération", "left", "sous", "bottom"),
    "l_jour_ferie_code": ((49.44, 425.72, 65.28, 436.71), "left", "zone"),
    "l_jour_ferie_jours": ((86.40, 425.72, 91.68, 436.71), "left", "zone"),
    "l_jour_ferie_heures": ((118.08, 425.72, 139.20, 436.71), "left", "zone"),
    "l_jour_ferie_label": ("Jour férié", "left", "sous"),
    "l_frais_vetements_code": ((49.44, 487.88, 65.28, 498.87), "left", "zone"),
    "l_frais_vetements_nombre": ((133.92, 487.88, 139.20, 498.87), "left", "zone"),
    "l_frais_vetements_valeur": ((165.60, 487.88, 197.28, 498.87), "left", "zone"),
    "l_frais_vetements_label": ("Frais forf.vetements.de trav.(nor. lég. sér.)", "left", "sous"),
    "l_rgpt_code": ((49.44, 496.76, 65.28, 507.75), "left", "zone"),
    "l_rgpt_nombre": ((133.92, 496.76, 139.20, 507.75), "left", "zone"),
    "l_rgpt_valeur": ((165.60, 496.76, 197.28, 507.75), "left", "zone"),
    "l_rgpt_label": ("Indemnité R.G.P.T.", "left", "sous"),
}


TEMPLATES: dict[str, Template] = {
    "sdworx_be": Template(
        nom="SD Worx — Belgique (employée Lidl)",
        pdf=RACINE / "07e98009254f46a00224b7194c27d978000c63ad 5.pdf",
        reperes=_REPERES_SDWORX,
        mapper=_mapper_sdworx,
        mapper_config=None,   # défini ci-dessous
        periode=_periode_sdworx,
        employeur_fixe={"nom": "LIDL BELGIUM GMBH & CO. KG", "ville": "9820 Merelbeke-Melle"},
        supporte_cheques_repas=True,
        pages_a_garder=[0],  # pages 2-3 = doc parasite (autre matricule, autre date)
    ),
    "cpas_verviers": Template(
        nom="CPAS Verviers — fiche de rémunérations (public)",
        pdf=RACINE / "BOUHAMID Halima 02 2024.pdf",
        reperes=_REPERES_CPAS,
        mapper=None,
        mapper_config=None,   # défini ci-dessous
        periode=_periode_cpas,
        employeur_fixe={"nom": "C.P.A.S. DE VERVIERS", "ville": "4800 Verviers"},
        pages_a_garder=[0],  # pages 2-3 = calendrier détaillé toujours au nom BOUHAMID
    ),
    "sdworx_bbpharma": Template(
        nom="SD Worx — Belgique (dirigeant B B Pharma)",
        pdf=RACINE / "1bb2807-20260128-fiche-de-paie-0000002-2_compress.pdf",
        reperes=_REPERES_SDWORX_BBPHARMA,
        mapper=None,
        mapper_config=None,   # défini ci-dessous
        periode=_periode_sdworx,
        employeur_fixe={"nom": "B B PHARMA SRL", "ville": "1650 Beersel"},
        supporte_atn=True,   # le sample a téléphone, logement, internet, voiture
        supporte_cheques_repas=True,
        supporte_fpe=True,
    ),
    "securex_be": Template(
        nom="Securex — Belgique (ouvrier, billet de paie)",
        pdf=RACINE / "remziye fiche de salaire.pdf",
        reperes=_REPERES_SECUREX,
        mapper=None,
        mapper_config=None,   # défini ci-dessous (post-déclaration pour éviter forward-ref)
        periode=_periode_securex,
        page_index=1,
        employeur_fixe={"nom": "SRL CAKIL CLEAN", "ville": "4800 Verviers"},
        pages_a_garder=[1],  # page 1 = courrier d'envoi Securex (MME CAKIL TUGBA), à supprimer
    ),
}


def _signe(montant: D, prefixe_positif: str = "") -> str:
    """Format Securex : montants signés avec préfixe « + » / « - » selon le signe."""
    if montant > 0:
        return f"{prefixe_positif}{eur_be(montant)}"
    if montant < 0:
        return f"-{eur_be(-montant)}"
    return "0,00"


def _periode_securex_depuis_cfg(periode: dict) -> str:
    """Format Securex : « DD.MM.AAAA-DD.MM.AAAA » depuis les dates DD/MM/AAAA du cfg."""
    debut = (periode.get("debut") or "").replace("/", ".")
    fin = (periode.get("fin") or "").replace("/", ".")
    return f"{debut}-{fin}" if debut and fin else ""


def _mapper_securex_config(fiche: dict, cfg: dict) -> dict:
    """Composer output + cfg → valeurs des champs Securex.

    Seuls les champs effectivement remplis sont retournés ; les autres gardent leur
    valeur d'origine sur le PDF (pixel-perfect par construction).
    """
    c = fiche["calculs"]
    sit = cfg["situation"]
    nom_complet = (cfg["salarie"].get("nom") or "").strip().split(maxsplit=1)
    nom_famille = nom_complet[0].upper() if nom_complet else ""
    prenom = nom_complet[1].upper() if len(nom_complet) > 1 else ""

    brut_total = D(c["brut_total"])
    onss_perso = D(c["onss_perso"])
    bonus = D(c["bonus_social"])
    imposable = D(c["imposable"])
    precompte = D(c["precompte_net"])
    net_payer = imposable - precompte
    brut_onss_108 = brut_total * D("1.08") if sit.get("ouvrier") else brut_total

    statut = ("Dirigeant" if sit.get("dirigeant")
              else "Ouvrier" if sit.get("ouvrier") else "Employé")
    enfants = max(int(sit.get("enfants", 0) or 0), 0)
    marie = (cfg["perso"].get("etat_civil") or "") != "Isolé(e)"

    # Civilité : pour l'instant fixée à « Madame » (sample) ; à dériver d'un champ
    # genre dans le cfg quand on ajoutera l'input à Certifio.
    nom_affiche = f"Madame {nom_famille} {prenom}".strip()
    valeurs = {
        "periode": _periode_securex_depuis_cfg(cfg["periode"]),
        "nom_complet_haut": nom_affiche,
        "prenom_residu": "",  # le span REMZIYE est couvert par nom_complet_haut ; on s'assure du blanc
        "adresse_rue": cfg["salarie"].get("adresse", "").upper(),
        "adresse_ville": cfg["salarie"].get("cp_ville", "").upper(),
        "nom_paiement": f"{nom_famille} {prenom}".strip(),
        "registre_national": cfg["perso"].get("niss", ""),
        "etat_civil": cfg["perso"].get("etat_civil", ""),
        "statut": statut,
        # Tableau charges fiscales : valeurs à overlay selon la situation.
        # Format 2 chiffres pour Enfants (matche le span sample « 00 »), 1 chiffre
        # pour Conjoint (matche « 0 »).
        "enfants_normales": f"{enfants:02d}",
        "enfants_handicapes": "00",
        "conjoint_normales": "1" if marie else "0",
        "conjoint_handicapes": "0",
        "remuneration_base": eur_be(brut_total),
        "l_brut_total": eur_be(brut_total),
        "l_onss_perso": _signe(-onss_perso),
        "l_bonus_emploi": _signe(bonus, prefixe_positif="+") if bonus > 0 else "",
        "l_imposable": eur_be(imposable),
        "l_precompte": _signe(-precompte),
        "l_net_payer": eur_be(net_payer),
        "l_table_net": eur_be(net_payer),       # ligne « ** Net » = imposable - précompte
        "l_net_employeur": eur_be(net_payer),   # ligne « A payer par l'employeur » (doublon)
        "l_brut_onss_108": eur_be(brut_onss_108),
        # Lignes de la fiche d'origine non maîtrisées par le composer : effacées
        # pour rester cohérent avec les entrées Certifio.
        "l_table_remu": "",        # ligne 000 (Rémunération CAT)
        "l_jour_ferie": "",        # ligne 220 (Jour férié)
        "l_frais_vetements": "",   # ligne 062 (frais forfaitaires vêtements)
        "l_rgpt": "",              # ligne 815 (indemnité R.G.P.T.)
        "l_onss_patronale": "",    # cotisation ONSS patronale non calculée
        "l_table_remu_code": "",
        "l_table_remu_jours": "",
        "l_table_remu_heures": "",
        "l_table_remu_label": "",
        "l_jour_ferie_code": "",
        "l_jour_ferie_jours": "",
        "l_jour_ferie_heures": "",
        "l_jour_ferie_label": "",
        "l_frais_vetements_code": "",
        "l_frais_vetements_nombre": "",
        "l_frais_vetements_valeur": "",
        "l_frais_vetements_label": "",
        "l_rgpt_code": "",
        "l_rgpt_nombre": "",
        "l_rgpt_valeur": "",
        "l_rgpt_label": "",
        # Résidus admin/contractuels Remziye (dates anciennes, N° BCE, références
        # internes, CP nettoyage, fonction NETTOYAGE CAT…) : tous effacés pour ne
        # pas mélanger des données du sample avec le salarié saisi.
        "date_emission_haut": "",
        "bce_employeur": "",
        "ref_calcul": "",
        "dernier_traitement": "",
        "date_en_service": "",
        "date_anc_firme": "",
        "date_anc_secteur": "",
        "cp_code": "",
        "cp_desc": "",
        "qualif_prof_code": "",
        "qualif_prof_desc": "",
        "fonction_securex": "",
    }
    return valeurs


# --- Mapper SD Worx (depuis composer) ---------------------------------------
# Le composer fournit brut/ONSS/bonus/imposable/précompte. Les lignes que le
# composer ne calcule pas (suppléments, réductions PP, CSSS, chèques-repas, etc.)
# sont MISES À VIDE pour ne pas afficher les valeurs d'origine de la fiche
# (KASHOURA) qui contrediraient le brut saisi — cohérence stricte.
_LIGNES_SDWORX_NON_CALCULEES = [
    "l_17C1", "l_1723", "l_2506", "l_3700", "l_3704",
    "l_3010", "l_3101", "l_3650", "l_3802",
]


def _libelle_charges(enfants: int) -> str:
    if enfants <= 0:
        return "aucune"
    return f"{enfants} enfant(s)"


def _libelle_statut(sit: dict) -> str:
    if sit.get("dirigeant"):
        return "dirigeant d'entreprise"
    if sit.get("ouvrier"):
        return "ouvrier(ère)"
    return "employé(e)"


def _mapper_sdworx_config(fiche: dict, cfg: dict) -> dict:
    c = fiche["calculs"]
    sit = cfg["situation"]
    brut = D(c["brut_total"])
    onss = D(c["onss_perso"])
    bonus = D(c["bonus_social"])
    imposable = D(c["imposable"])
    precompte_brut = D(c["precompte_brut"])
    reduction_precompte = D(c["reduction_precompte"])
    precompte_net = D(c["precompte_net"])
    cheques_repas = max(_d(cfg.get("cheques_repas", "")), D("0"))
    salaire_net = imposable - precompte_net - cheques_repas

    valeurs = {
        "nom": (cfg["salarie"].get("nom") or "").upper(),
        "niss": cfg["perso"].get("niss", ""),
        "adresse_rue": cfg["salarie"].get("adresse", ""),
        "adresse_ville": cfg["salarie"].get("cp_ville", ""),
        "iban": "",  # IBAN KASHOURA effacé (sample privé)
        "verse_label": "",
        "bic": "",   # BIC KASHOURA effacé
        "matricule_haut": "",  # « 1AL1388 / 3253124 » : matricule KASHOURA en haut
        "matricule_bas": "",   # idem en pied de page
        "pagination": "1/1",
        "periode_debut": cfg["periode"].get("debut", ""),
        "periode_fin": cfg["periode"].get("fin", ""),
        "date_calcul": cfg["periode"].get("calcul", ""),
        "etat_civil": cfg["perso"].get("etat_civil", ""),
        "personnes_charge": _libelle_charges(int(sit.get("enfants", 0) or 0)),
        "statut_contrat": _libelle_statut(sit),
        "fonction": cfg["perso"].get("fonction", "") or "—",
        # Données du contrat : effacer les valeurs sample KASHOURA pour ne pas mélanger
        # son matricule/n° GPS/dates avec le salarié saisi par Certifio.
        "num_travailleur": "",
        "num_gps": "",
        "date_entree": "",
        "date_anciennete": "",
        "cp": "",
        "salaire_base": eur_be(brut),
        "montant_brut": eur_be(brut),
        "base_onss": eur_be(brut),
        "imposable": eur_be(imposable),
        "base_prec": eur_be(imposable),
        "salaire_net": eur_be(salaire_net),
        "montant_net": eur_be(salaire_net),
        "total_verse": eur_be(salaire_net),       # ligne « versé au compte IBAN: €X »
        "l_1011": eur_be(brut),
        "l_2500": _signe(-onss),
        "l_2509": _signe(bonus, prefixe_positif="+") if bonus > 0 else "",
        "l_3500": _signe(-precompte_brut) if precompte_brut > 0 else "",
        "l_3702": _signe(reduction_precompte, prefixe_positif="+") if reduction_precompte > 0 else "",
        "l_3970": _signe(-cheques_repas) if cheques_repas > 0 else "",
    }
    # Effacement des lignes non calculées pour rester cohérent avec les entrées.
    valeurs.update({nom: "" for nom in _LIGNES_SDWORX_NON_CALCULEES})
    return valeurs


# --- Mapper CPAS Verviers (depuis composer) ---------------------------------
def _periode_cpas_depuis_cfg(periode: dict) -> str:
    """Format CPAS : « Période : MM/AAAA » depuis la date de début DD/MM/AAAA."""
    parts = (periode.get("debut") or "").split("/")
    return f"Période : {parts[1]}/{parts[2]}" if len(parts) == 3 else ""


def _mapper_cpas_config(fiche: dict, cfg: dict) -> dict:
    c = fiche["calculs"]
    brut = D(c["brut_total"])
    onss = D(c["onss_perso"])
    bonus = D(c["bonus_social"])
    precompte = D(c["precompte_net"])
    imposable = D(c["imposable"])
    net = imposable - precompte
    cot_soc_nette = max(onss - bonus, D("0"))

    periode = cfg["periode"]
    parts_debut = (periode.get("debut") or "").split("/")
    mois_annee = f"{parts_debut[1]}/{parts_debut[2]}" if len(parts_debut) == 3 else ""
    annee = int(parts_debut[2]) if len(parts_debut) == 3 and parts_debut[2].isdigit() else 2026
    mois = int(parts_debut[1]) if len(parts_debut) == 3 and parts_debut[1].isdigit() else 1
    dernier = calendar.monthrange(annee, mois)[1]

    return {
        "nom": (cfg["salarie"].get("nom") or "").upper(),
        "adresse_rue": cfg["salarie"].get("adresse", ""),
        "adresse_ville": cfg["salarie"].get("cp_ville", ""),
        "registre_national": cfg["perso"].get("niss", ""),
        "situation_fiscale": cfg["perso"].get("etat_civil", ""),
        "periode": _periode_cpas_depuis_cfg(periode),
        "brut_total": eur_be(brut),
        "resume_brut": eur_be(brut),
        "resume_cotsoc": eur_be(cot_soc_nette),
        "resume_precompte": eur_be(precompte),
        "net_paye": eur_be(net),
        # Dates haut-droit : on garde le format « libellé valeur » d'origine.
        "date_emission": f"Date : {periode.get('calcul', '')}" if periode.get("calcul") else "",
        "paie_du": f"Paie du {periode.get('fin', '')}" if periode.get("fin") else "",
        "exploit_de": f"Expl. de {mois_annee}" if mois_annee else "",
        # Résidus BOUHAMID (matricule, date d'entrée, Cie assurances, fonction) : effacés
        # pour ne pas mélanger l'identité du sample avec le salarié saisi.
        "matricule": "",
        "entre_le": "",
        "index": "",
        "cie_assurances": "",
        "fonction_cpas": "",
        "paie_du_avec_heure": "",
        "fonction_code_cpas": "",
        "anciennete_pecuniaire": "",
        "conjoint_info": "",
        "traitement_ligne": "Traitement, salaire, appointements",
        "calendrier_mois": mois_annee,
        "cal_jour_29": "29" if dernier >= 29 else "",
        "cal_jour_30": "30" if dernier >= 30 else "",
        "cal_jour_31": "31" if dernier >= 31 else "",
        "cal_cyc_contr_values": "",
        "cal_cyc_hab_values": "",
        "cal_n10_code": "",
        "cal_n10_values": "",
        "cal_preste_flag": "",
        "barcode_data": "",
        "barcode_central": "",
        "barcode_bas_gauche": "",
        "pagination_haut": "1 - 1/1 - 1/1",
        "pagination_bas": "Page 1 / 1",
    }


# --- Mapper SD Worx B B PHARMA (composer dirigeant) -------------------------
_LIGNES_BBPHARMA_ATN = [
    "l_atn1_imp", "l_atn2_imp", "l_atn3_imp", "l_atn4_imp", "l_atn5_imp",
    "l_atn1_net", "l_atn2_net", "l_atn3_net", "l_atn4_net", "l_atn5_net",
    "l_3970", "l_3330",
]
# Code Certifio (du composer.atn) → (champ imposable, champ net) du template BB PHARMA.
_BBPHARMA_ATN_PAR_CODE = {
    "1601": ("l_atn1_imp", "l_atn1_net"),
    "1606": ("l_atn2_imp", "l_atn2_net"),
    "1607": ("l_atn3_imp", "l_atn3_net"),
    "2240": ("l_atn4_imp", "l_atn4_net"),
    "2251": ("l_atn5_imp", "l_atn5_net"),
}


def _mapper_sdworx_bbpharma_config(fiche: dict, cfg: dict) -> dict:
    c = fiche["calculs"]
    sit = cfg["situation"]
    brut_nominal = _d(cfg.get("brut", "0"))    # ligne 1010 = brut sans ATN
    imposable = D(c["imposable"])              # brut + ATN
    precompte = D(c["precompte_net"])
    salaire_net = D(c["net_a_payer"])
    cheques_repas = max(_d(cfg.get("cheques_repas", "")), D("0"))
    fpe = max(_d(cfg.get("fpe", "")), D("0"))

    valeurs = {
        "nom": (cfg["salarie"].get("nom") or "").title(),
        "niss": cfg["perso"].get("niss", ""),
        "adresse_rue": cfg["salarie"].get("adresse", ""),
        "adresse_ville": cfg["salarie"].get("cp_ville", ""),
        "periode_debut": cfg["periode"].get("debut", ""),
        "periode_fin": cfg["periode"].get("fin", ""),
        "date_calcul": cfg["periode"].get("calcul", ""),
        "etat_civil": cfg["perso"].get("etat_civil", ""),
        "personnes_charge": _libelle_charges(int(sit.get("enfants", 0) or 0)),
        "imposable": eur_be(imposable),
        "salaire_net": eur_be(salaire_net),
        "total_final": " " + eur_be(salaire_net),
        "l_1010": eur_be(brut_nominal),
        "l_3500": _signe(-precompte) if precompte > 0 else "",
        "info_cheques": "",
        "footer_ref": "",
    }
    # Effacement par défaut des lignes ATN du sample.
    valeurs.update({nom: "" for nom in _LIGNES_BBPHARMA_ATN})
    valeurs["l_3970"] = _signe(-cheques_repas) if cheques_repas > 0 else ""
    valeurs["l_3330"] = eur_be(fpe) if fpe > 0 else ""

    # Libellé voiture : « Voiture de société (Porsche) » → modèle optionnel saisi
    # ou neutre. Évite d'afficher la Porsche de Boulal par défaut.
    modele_voiture = (cfg.get("voiture_modele") or "").strip()
    libelle_voiture = f"Voiture de société ({modele_voiture})" if modele_voiture else "Voiture de société"
    valeurs["l_voiture_libelle_imp"] = libelle_voiture
    valeurs["l_voiture_libelle_net"] = libelle_voiture

    # Re-remplissage des lignes ATN saisies (mapping code Certifio → champ template).
    for a in cfg.get("atn", []):
        code = str(a.get("code", ""))
        montant_str = str(a.get("montant", "")).strip().replace(",", ".")
        if not montant_str or code not in _BBPHARMA_ATN_PAR_CODE:
            continue
        montant = D(montant_str)
        if montant == 0:
            continue
        imp_field, net_field = _BBPHARMA_ATN_PAR_CODE[code]
        valeurs[imp_field] = eur_be(montant)
        valeurs[net_field] = _signe(-montant)
    return valeurs


# Branchement des mappers après déclaration des templates (évite forward-ref).
TEMPLATES["securex_be"].mapper_config = _mapper_securex_config
TEMPLATES["sdworx_be"].mapper_config = _mapper_sdworx_config
TEMPLATES["cpas_verviers"].mapper_config = _mapper_cpas_config
TEMPLATES["sdworx_bbpharma"].mapper_config = _mapper_sdworx_bbpharma_config


# ──────────────────────────────────────────────────────────────────────────────
# Helpers communs
# ──────────────────────────────────────────────────────────────────────────────

def _periode_mm_aaaa(annee: int, mois: int) -> str:
    return f"{mois:02d}/{annee}"


def _periode_debut_fin(annee: int, mois: int) -> tuple[str, str]:
    dernier = calendar.monthrange(annee, mois)[1]
    return f"01/{mois:02d}/{annee}", f"{dernier:02d}/{mois:02d}/{annee}"


def _periode_debut_fin_tiret(annee: int, mois: int) -> tuple[str, str]:
    dernier = calendar.monthrange(annee, mois)[1]
    return f"01-{mois:02d}-{annee}", f"{dernier:02d}-{mois:02d}-{annee}"


def _mois_texte(mois: int) -> str:
    mois_fr = ["janvier","février","mars","avril","mai","juin",
               "juillet","août","septembre","octobre","novembre","décembre"]
    return mois_fr[mois - 1]


# ──────────────────────────────────────────────────────────────────────────────
# 1. HSP — Human Social Process (CLAES FISH SPRL)
# ──────────────────────────────────────────────────────────────────────────────

_REPERES_HSP = {
    # Identité salarié
    "nom":             ("Fraihi Yasmina",        "left"),
    "adresse_rue":     ("Tulpenlaan",             "left"),
    "adresse_ville":   ("1500 Halle",             "left"),
    "niss":            ("97.06.21 362-20",         "left"),
    # Période
    "periode_debut":   ("01-07-2025",             "left", "sous"),
    "periode_fin":     ("31-07-2025",             "left", "sous"),
    # Données perso (libellé → valeur à droite)
    "etat_civil":      ("Etat civil:",            "left", "apres"),
    # Montants
    "brut_onss":       ("3.020,28",               "right"),
    "onss_perso":      ("-426,33",                "right"),
    "imposable":       ("2.593,95",               "right"),
    "precompte":       ("-437,58",                "right"),
    "salaire_net":     ("2.549,25",               "right"),
    "net_decompte":    ("2.549,25",               "right"),   # page 2 décompte
    "a_payer":         ("2.549,25",               "right"),
}


def _periode_hsp(annee: int, mois: int) -> dict:
    debut, fin = _periode_debut_fin_tiret(annee, mois)
    return {"periode_debut": debut, "periode_fin": fin}


def _mapper_hsp_config(fiche: dict, cfg: dict) -> dict:
    c = fiche["calculs"]
    brut   = D(c["brut_total"])
    onss   = D(c["onss_perso"])
    bonus  = D(c["bonus_social"])
    imp    = D(c["imposable"])
    prec   = D(c["precompte_net"])
    net    = imp - prec
    onss_net = onss - bonus

    debut, fin = _periode_debut_fin_tiret(
        int(cfg["periode"].get("annee", 2026)),
        int(cfg["periode"].get("mois", 1)),
    )
    return {
        "nom":           (cfg["salarie"].get("nom") or "").strip(),
        "adresse_rue":   cfg["salarie"].get("adresse", ""),
        "adresse_ville": cfg["salarie"].get("cp_ville", ""),
        "niss":          cfg["perso"].get("niss", ""),
        "etat_civil":    cfg["perso"].get("etat_civil", ""),
        "periode_debut": debut,
        "periode_fin":   fin,
        "brut_onss":     eur_be(brut),
        "onss_perso":    _signe(-onss_net),
        "imposable":     eur_be(imp),
        "precompte":     _signe(-prec),
        "salaire_net":   eur_be(net),
        "net_decompte":  eur_be(net),
        "a_payer":       eur_be(net),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 2. BOSA / SPF Justice
# ──────────────────────────────────────────────────────────────────────────────

_REPERES_BOSA = {
    # Page 1 — résumé
    "nom":             ("EL AKHSSASSI SHAYNES",  "left"),
    "adresse_rue":     ("Rue du Poncay 12",       "left"),
    "adresse_ville":   ("4020 BRESSOUX",          "left"),
    "niss":            ("07092729012",            "left"),
    "net_montant":     ("1.875,70",               "right"),   # grand chiffre page 1
    "periode_calcul":  ("08/2026",                "left", "apres"),
    # Page 2 — détail
    "brut_mensuel":    ("1.987,89",               "right"),
    "allocation_res":  ("89,21",                  "right"),
    "total_brut":      ("2.077,10",               "right"),
    "onss_total":      ("-334,65",                "right"),
    "bonus_bs":        ("80,08",                  "right"),
    "bonus_tbs":       ("53,17",                  "right"),
    "total_imposable": ("1.875,70",               "right"),
    "total_net":       ("1.875,70",               "right"),
}


def _periode_bosa(annee: int, mois: int) -> dict:
    return {"periode_calcul": f"{mois:02d}/{annee}"}


def _mapper_bosa_config(fiche: dict, cfg: dict) -> dict:
    c   = fiche["calculs"]
    brut = D(c["brut_total"])
    onss = D(c["onss_perso"])
    bon  = D(c["bonus_social"])
    imp  = D(c["imposable"])
    prec = D(c["precompte_net"])
    net  = imp - prec

    parts = (cfg["periode"].get("debut") or "").split("/")
    periode_str = f"{parts[1]}/{parts[2]}" if len(parts) == 3 else ""

    return {
        "nom":             (cfg["salarie"].get("nom") or "").upper(),
        "adresse_rue":     cfg["salarie"].get("adresse", ""),
        "adresse_ville":   cfg["salarie"].get("cp_ville", ""),
        "niss":            cfg["perso"].get("niss", ""),
        "net_montant":     eur_be(net),
        "periode_calcul":  periode_str,
        "brut_mensuel":    eur_be(brut),
        "allocation_res":  "0,00",
        "total_brut":      eur_be(brut),
        "onss_total":      _signe(-onss),
        "bonus_bs":        eur_be(bon * D("0.6")) if bon > 0 else "0,00",
        "bonus_tbs":       eur_be(bon * D("0.4")) if bon > 0 else "0,00",
        "total_imposable": eur_be(net),
        "total_net":       eur_be(net),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3. T.PALM — billet de paie construction
# ──────────────────────────────────────────────────────────────────────────────

_REPERES_TPALM = {
    "nom":          ("MECHBAL MOHAMED",   "left"),
    "adresse_rue":  ("Grand route 146",   "left"),
    "adresse_ville":("4690 BASSENGE",     "left"),
    "niss":         ("96052048395",       "left"),
    "periode":      ("01/06/2026",        "left", "sous"),
    "brut":         ("3866,73",           "right"),
    "onss":         ("545,81",            "right"),
    "imposable":    ("3320,92",           "right"),
    "precompte":    ("796,17",            "right"),
    "net":          ("2611,25",           "right"),
    "net_payer":    ("2611,25",           "right"),
}


def _periode_tpalm(annee: int, mois: int) -> dict:
    debut, fin = _periode_debut_fin(annee, mois)
    return {"periode": f"{debut} - {fin}"}


def _mapper_tpalm_config(fiche: dict, cfg: dict) -> dict:
    c    = fiche["calculs"]
    brut = D(c["brut_total"])
    onss = D(c["onss_perso"])
    bon  = D(c["bonus_social"])
    imp  = D(c["imposable"])
    prec = D(c["precompte_net"])
    net  = imp - prec
    onss_net = onss - bon

    debut = cfg["periode"].get("debut", "")
    fin   = cfg["periode"].get("fin", "")
    return {
        "nom":           (cfg["salarie"].get("nom") or "").upper(),
        "adresse_rue":   cfg["salarie"].get("adresse", ""),
        "adresse_ville": cfg["salarie"].get("cp_ville", ""),
        "niss":          cfg["perso"].get("niss", ""),
        "periode":       f"{debut} - {fin}",
        "brut":          eur_be(brut).replace(".", "").replace(",", ","),
        "onss":          eur_be(onss_net).replace(".", "").replace(",", ","),
        "imposable":     eur_be(imp).replace(".", "").replace(",", ","),
        "precompte":     eur_be(prec).replace(".", "").replace(",", ","),
        "net":           eur_be(net).replace(".", "").replace(",", ","),
        "net_payer":     eur_be(net).replace(".", "").replace(",", ","),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 4. UCM — Secrétariat social
# ──────────────────────────────────────────────────────────────────────────────

_REPERES_UCM = {
    "nom":              ("KOUATCHI Miyobor",    "left"),
    "adresse_rue":      ("RUE DU VALLON",       "left"),
    "adresse_ville":    ("4031 Angleur",         "left"),
    "niss":             ("04041940935",          "left"),
    "periode":          ("juin 2026",            "left", "apres"),
    "date_calcul":      ("09/07/2026",           "left", "apres"),
    "brut_onss":        ("3.219,75",             "right"),
    "onss_trav":        ("211,68",               "right"),
    "imposable":        ("3.008,07",             "right"),
    "precompte":        ("499,44",               "right"),
    "net_base":         ("2.508,63",             "right"),
    "net_payer":        ("2.924,65",             "right"),
}


def _periode_ucm(annee: int, mois: int) -> dict:
    return {"periode": f"{_mois_texte(mois)} {annee}"}


def _mapper_ucm_config(fiche: dict, cfg: dict) -> dict:
    c    = fiche["calculs"]
    brut = D(c["brut_total"])
    onss = D(c["onss_perso"])
    bon  = D(c["bonus_social"])
    imp  = D(c["imposable"])
    prec = D(c["precompte_net"])
    net  = imp - prec
    onss_net = onss - bon

    parts_debut = (cfg["periode"].get("debut") or "").split("/")
    mois_an = (f"{_mois_texte(int(parts_debut[1]))} {parts_debut[2]}"
               if len(parts_debut) == 3 else "")

    return {
        "nom":           (cfg["salarie"].get("nom") or "").upper(),
        "adresse_rue":   cfg["salarie"].get("adresse", "").upper(),
        "adresse_ville": cfg["salarie"].get("cp_ville", ""),
        "niss":          cfg["perso"].get("niss", ""),
        "periode":       mois_an,
        "date_calcul":   cfg["periode"].get("calcul", ""),
        "brut_onss":     eur_be(brut),
        "onss_trav":     eur_be(onss_net),
        "imposable":     eur_be(imp),
        "precompte":     eur_be(prec),
        "net_base":      eur_be(net),
        "net_payer":     eur_be(net),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 5. Partena Professional
# ──────────────────────────────────────────────────────────────────────────────

_REPERES_PARTENA = {
    "nom":              ("Cimen Mucahit",        "left"),
    "adresse_rue":      ("Rue Franchimont 20",   "left"),
    "adresse_ville":    ("4800 Verviers",         "left"),
    "niss":             ("86.07.11-527.28",       "left"),
    "periode_debut":    ("01/06/2026",            "left", "sous"),
    "periode_fin":      ("30/06/2026",            "left", "sous"),
    "date_etablie":     ("02/07/2026",            "left", "apres"),
    "brut_total":       ("2 367,82",              "right"),
    "onss_trav":        ("-334,23",               "right"),
    "red_onss":         ("196,01",                "right"),
    "cot_trav_total":   ("-138,22",               "right"),
    "imposable":        ("2 229,60",              "right"),
    "precompte":        ("-186,13",               "right"),
    "net_final":        ("2 328,82",              "right"),
}


def _periode_partena(annee: int, mois: int) -> dict:
    debut, fin = _periode_debut_fin(annee, mois)
    return {"periode_debut": debut, "periode_fin": fin}


def _mapper_partena_config(fiche: dict, cfg: dict) -> dict:
    c    = fiche["calculs"]
    brut = D(c["brut_total"])
    onss = D(c["onss_perso"])
    bon  = D(c["bonus_social"])
    imp  = D(c["imposable"])
    prec = D(c["precompte_net"])
    net  = imp - prec

    # Format Partena : espace comme séparateur de milliers, virgule décimale
    def eur_partena(v: D) -> str:
        s = eur_be(v)           # "2.328,82"
        return s.replace(".", " ")  # "2 328,82"

    return {
        "nom":            (cfg["salarie"].get("nom") or "").title(),
        "adresse_rue":    cfg["salarie"].get("adresse", ""),
        "adresse_ville":  cfg["salarie"].get("cp_ville", ""),
        "niss":           cfg["perso"].get("niss", ""),
        "periode_debut":  cfg["periode"].get("debut", ""),
        "periode_fin":    cfg["periode"].get("fin", ""),
        "date_etablie":   cfg["periode"].get("calcul", ""),
        "brut_total":     eur_partena(brut),
        "onss_trav":      _signe(-onss),
        "red_onss":       eur_partena(bon) if bon > 0 else "0,00",
        "cot_trav_total": _signe(-(onss - bon)),
        "imposable":      eur_partena(imp),
        "precompte":      _signe(-prec),
        "net_final":      eur_partena(net),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 6. TwinnTax — Dirigeant d'entreprise
# ──────────────────────────────────────────────────────────────────────────────

_REPERES_TWINNTAX = {
    "nom":              ("Kokou Kouatchi",        "left"),
    "adresse_rue":      ("Rue François Cloes 1",  "left"),
    "adresse_ville":    ("4420 SAINT-NICOLAS",    "left"),
    "niss":             ("79000090179",           "left"),
    "periode":          ("Aout 2026",             "left", "apres"),
    "date_calcul":      ("31/08/2026",            "left", "apres"),
    "salaire_brut":     ("+2.296,40",             "right"),
    "cotisations":      ("+477,61",               "right"),
    "precompte":        ("-406,40",               "right"),
    "atn_total":        ("-489,61",               "right"),
    "base_imposable":   ("2.786,01",              "right"),
    "cotisations_res":  ("477,61",                "right"),
    "precompte_res":    ("406,40",                "right"),
    "net_payer":        ("2.000,00",              "right"),
}


def _periode_twinntax(annee: int, mois: int) -> dict:
    return {"periode": f"{_mois_texte(mois).capitalize()} {annee}"}


def _mapper_twinntax_config(fiche: dict, cfg: dict) -> dict:
    c    = fiche["calculs"]
    brut = D(c["brut_total"])
    onss = D(c["onss_perso"])
    bon  = D(c["bonus_social"])
    imp  = D(c["imposable"])
    prec = D(c["precompte_net"])
    net  = D(c["net_a_payer"])
    onss_net = onss - bon

    # ATN éventuels
    atn_total = D("0")
    for a in cfg.get("atn", []):
        try:
            atn_total += D(str(a.get("montant", "0")).replace(",", "."))
        except Exception:
            pass

    parts_debut = (cfg["periode"].get("debut") or "").split("/")
    periode_str = ""
    if len(parts_debut) == 3:
        periode_str = f"{_mois_texte(int(parts_debut[1])).capitalize()} {parts_debut[2]}"

    return {
        "nom":             (cfg["salarie"].get("nom") or "").title(),
        "adresse_rue":     cfg["salarie"].get("adresse", ""),
        "adresse_ville":   cfg["salarie"].get("cp_ville", "").upper(),
        "niss":            cfg["perso"].get("niss", ""),
        "periode":         periode_str,
        "date_calcul":     cfg["periode"].get("calcul", ""),
        "salaire_brut":    "+" + eur_be(brut),
        "cotisations":     "+" + eur_be(onss_net),
        "precompte":       _signe(-prec),
        "atn_total":       _signe(-atn_total) if atn_total > 0 else "",
        "base_imposable":  eur_be(imp),
        "cotisations_res": eur_be(onss_net),
        "precompte_res":   eur_be(prec),
        "net_payer":       eur_be(net),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 7. Ville de Liège
# ──────────────────────────────────────────────────────────────────────────────

_REPERES_LIEGE = {
    "nom":              ("Mme PATRICIA GRIFNAIE", "left"),
    "adresse_rue":      ("rue Adolph Renson, 38", "left"),
    "adresse_ville":    ("4420 St-Nicolas",        "left"),
    "niss":             ("68100416846",            "left"),
    "mois_prestation":  ("07/2026",                "left", "apres"),
    "date_calcul":      ("07/2026",                "left", "sous"),
    "brut":             ("2.968,53",               "right"),
    "onss_perso":       ("-387,99",                "right"),
    "bonus_emploi":     ("100,89",                 "right"),
    "imposable":        ("2.681,43",               "right"),
    "precompte":        ("-425,23",                "right"),
    "cot_speciale":     ("-23,00",                 "right"),
    "salaire_net":      ("2.233,20",               "right"),
    "a_payer":          ("2.233,20",               "right"),
}


def _periode_liege(annee: int, mois: int) -> dict:
    return {"mois_prestation": f"{mois:02d}/{annee}", "date_calcul": f"{mois:02d}/{annee}"}


def _mapper_liege_config(fiche: dict, cfg: dict) -> dict:
    c    = fiche["calculs"]
    brut = D(c["brut_total"])
    onss = D(c["onss_perso"])
    bon  = D(c["bonus_social"])
    imp  = D(c["imposable"])
    prec = D(c["precompte_net"])
    net  = imp - prec
    onss_net = onss - bon

    parts_debut = (cfg["periode"].get("debut") or "").split("/")
    mm_aa = (f"{parts_debut[1]}/{parts_debut[2]}"
             if len(parts_debut) == 3 else "")

    return {
        "nom":             "Mme " + (cfg["salarie"].get("nom") or "").upper(),
        "adresse_rue":     cfg["salarie"].get("adresse", ""),
        "adresse_ville":   cfg["salarie"].get("cp_ville", ""),
        "niss":            cfg["perso"].get("niss", ""),
        "mois_prestation": mm_aa,
        "date_calcul":     mm_aa,
        "brut":            eur_be(brut),
        "onss_perso":      _signe(-onss_net),
        "bonus_emploi":    eur_be(bon) if bon > 0 else "0,00",
        "imposable":       eur_be(imp),
        "precompte":       _signe(-prec),
        "cot_speciale":    "-23,00",   # fixe Ville de Liège
        "salaire_net":     eur_be(net),
        "a_payer":         eur_be(net),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Ajout des templates dans le dict TEMPLATES
# (à coller après le bloc TEMPLATES existant, avant def get(...))
# ──────────────────────────────────────────────────────────────────────────────

TEMPLATES["hsp_be"] = Template(
    nom="HSP (Human Social Process) — CLAES FISH",
    pdf=RACINE / "hsp.pdf",
    reperes=_REPERES_HSP,
    mapper_config=None,  # branché ci-dessous
    periode=_periode_hsp,
    supporte_composer=True,
    employeur_fixe={"nom": "CLAES FISH SPRL", "ville": "1200 Woluwe-Saint-Lambert"},
    pages_a_garder=[0],
)

TEMPLATES["bosa_spf"] = Template(
    nom="BOSA / SPF — Fiche de traitement (public)",
    pdf=RACINE / "bosa_spf.pdf",
    reperes=_REPERES_BOSA,
    mapper_config=None,
    periode=_periode_bosa,
    supporte_composer=True,
    employeur_fixe={"nom": "SPF Justice", "ville": "1000 Bruxelles"},
    pages_a_garder=[0, 1],
)

TEMPLATES["tpalm_be"] = Template(
    nom="T.PALM — Billet de paie construction (Theux)",
    pdf=RACINE / "tpalm.pdf",
    reperes=_REPERES_TPALM,
    mapper_config=None,
    periode=_periode_tpalm,
    supporte_composer=True,
    employeur_fixe={"nom": "T.PALM", "ville": "4910 Theux"},
    pages_a_garder=[0],
)

TEMPLATES["ucm_be"] = Template(
    nom="UCM Secrétariat social — Ouvrier transport",
    pdf=RACINE / "ucm.pdf",
    reperes=_REPERES_UCM,
    mapper_config=None,
    periode=_periode_ucm,
    supporte_composer=True,
    employeur_fixe={"nom": "KOUATCHI TRANSPORT SRL", "ville": "4420 Saint-Nicolas"},
    pages_a_garder=[0],
)

TEMPLATES["partena_be"] = Template(
    nom="Partena Professional — Ouvrier transport (Liège)",
    pdf=RACINE / "partena.pdf",
    reperes=_REPERES_PARTENA,
    mapper_config=None,
    periode=_periode_partena,
    supporte_composer=True,
    employeur_fixe={"nom": "CLARAP TRANSPORT", "ville": "4000 Liège"},
    pages_a_garder=[0],
)

TEMPLATES["twinntax_be"] = Template(
    nom="TwinnTax — Dirigeant d'entreprise (Belgique)",
    pdf=RACINE / "twinntax.pdf",
    reperes=_REPERES_TWINNTAX,
    mapper_config=None,
    periode=_periode_twinntax,
    supporte_composer=True,
    supporte_atn=True,
    employeur_fixe={"nom": "KOUATCHI TRANSPORT", "ville": "4420 Saint-Nicolas"},
    pages_a_garder=[0],
)

TEMPLATES["liege_be"] = Template(
    nom="Ville de Liège — Fiche de paie (public contractuel)",
    pdf=RACINE / "liege.pdf",
    reperes=_REPERES_LIEGE,
    mapper_config=None,
    periode=_periode_liege,
    supporte_composer=True,
    employeur_fixe={"nom": "Ville de Liège", "ville": "4000 Liège"},
    pages_a_garder=[0],
)

# ── Branchement des mappers ────────────────────────────────────────────────────
TEMPLATES["hsp_be"].mapper_config      = _mapper_hsp_config
TEMPLATES["bosa_spf"].mapper_config    = _mapper_bosa_config
TEMPLATES["tpalm_be"].mapper_config    = _mapper_tpalm_config
TEMPLATES["ucm_be"].mapper_config      = _mapper_ucm_config
TEMPLATES["partena_be"].mapper_config  = _mapper_partena_config
TEMPLATES["twinntax_be"].mapper_config = _mapper_twinntax_config
TEMPLATES["liege_be"].mapper_config    = _mapper_liege_config

def get(cle: str) -> Template | None:
    return TEMPLATES.get(cle)
