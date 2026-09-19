// Config de la fiche + construction du payload pour /api/fiche-config (précompte CALCULÉ).

export interface ATN {
  actif: boolean;
  montant: string;
}

export interface Config {
  empNom: string;
  empAdresse: string;
  empCpVille: string;
  nom: string;
  adresse: string;
  cpVille: string;
  niss: string;
  etatCivil: string;
  conjointRevenus: boolean; // conjoint a des revenus propres ? (si marié)
  enfants: string; // enfants dont la réduction est prise sur CETTE fiche
  statut: string;
  caisse: string;
  periodeDebut: string;
  periodeFin: string;
  dateCalcul: string;
  brut: string;
  brutMoisMoins1: string; // mode 3 mois : brut du mois précédent
  brutMoisMoins2: string; // mode 3 mois : brut du mois encore avant
  cotisations: string;
  chequesRepas: string;
  fpe: string;
  voitureModele: string; // marque/modèle (remplace « Porsche » par défaut sur BB Pharma)
  voiture: ATN;
  telephone: ATN;
  logement: ATN;
  internet: ATN;
}

export const DEFAUTS: Config = {
  empNom: "",
  empAdresse: "",
  empCpVille: "",
  nom: "",
  adresse: "",
  cpVille: "",
  niss: "",
  etatCivil: "Isolé(e)",
  conjointRevenus: true,
  enfants: "0",
  statut: "Employé(e)",
  caisse: "",
  periodeDebut: "01/01/2026",
  periodeFin: "31/01/2026",
  dateCalcul: "28/01/2026",
  brut: "",
  brutMoisMoins1: "",
  brutMoisMoins2: "",
  cotisations: "",
  chequesRepas: "",
  fpe: "",
  voitureModele: "",
  voiture: { actif: false, montant: "" },
  telephone: { actif: false, montant: "" },
  logement: { actif: false, montant: "" },
  internet: { actif: false, montant: "" },
};

export function construireConfig(c: Config): Record<string, unknown> {
  const atn = [
    { code: "2251", desc: "Voiture de société", ...c.voiture },
    { code: "1601", desc: "Téléphonie (Téléphone)", ...c.telephone },
    { code: "1606", desc: "Habitation (Logement)", ...c.logement },
    { code: "1607", desc: "Internet (Internet)", ...c.internet },
  ]
    .filter((x) => x.actif && x.montant.trim())
    .map((x) => ({ code: x.code, desc: x.desc, montant: x.montant }));

  const marie = c.etatCivil !== "Isolé(e)";

  return {
    employeur: { nom: c.empNom, adresse: c.empAdresse, cp_ville: c.empCpVille },
    periode: { debut: c.periodeDebut, fin: c.periodeFin, calcul: c.dateCalcul },
    perso: { niss: c.niss, etat_civil: c.etatCivil, caisse: c.caisse },
    salarie: { nom: c.nom, adresse: c.adresse, cp_ville: c.cpVille },
    situation: {
      dirigeant: c.statut === "Dirigeant d'entreprise",
      ouvrier: c.statut === "Ouvrier(ère)",
      conjoint_sans_revenus: marie && !c.conjointRevenus,
      enfants: parseInt(c.enfants || "0", 10),
    },
    brut: c.brut,
    cotisations: c.cotisations,
    atn,
    voiture_modele: c.voitureModele,
    cheques_repas: c.chequesRepas,
    fpe: c.fpe,
  };
}

// Trois bruts [m-2, m-1, m] : si vide, fallback sur le brut courant.
export function bruts3Mois(c: Config): string[] {
  return [
    (c.brutMoisMoins2 || "").trim() || c.brut,
    (c.brutMoisMoins1 || "").trim() || c.brut,
    c.brut,
  ];
}
