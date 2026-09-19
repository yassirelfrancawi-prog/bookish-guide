// Client API : liste des templates + génération overlay (au millimètre).

export interface Templates {
  [cle: string]: {
    nom: string;
    champs: string[];
    supporte_composer?: boolean;
    supporte_atn?: boolean;
    supporte_cheques_repas?: boolean;
    supporte_fpe?: boolean;
    employeur_fixe?: Record<string, string>;
  };
}

export interface Resultat {
  blob?: Blob; // PDF (mode local sans bot)
  message?: string; // réponse JSON (ex. envoyé dans le chat)
}

export async function listerTemplates(): Promise<Templates> {
  const r = await fetch("/api/templates");
  if (!r.ok) throw new Error(`Erreur ${r.status}`);
  return r.json();
}

export async function genererOverlay(
  template: string,
  valeurs: Record<string, string>,
): Promise<Resultat> {
  const initData = window.Telegram?.WebApp?.initData || undefined;
  const r = await fetch("/api/generer-overlay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template, valeurs, init_data: initData }),
  });
  if (!r.ok) throw new Error(`Erreur ${r.status} : ${await r.text()}`);
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/pdf")) return { blob: await r.blob() };
  return { message: JSON.stringify(await r.json()) };
}

// Génère une fiche depuis des entrées simples : le précompte est CALCULÉ côté serveur.
export async function genererConfig(cfg: Record<string, unknown>): Promise<Resultat> {
  const initData = window.Telegram?.WebApp?.initData || undefined;
  const r = await fetch("/api/fiche-config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...cfg, init_data: initData }),
  });
  if (!r.ok) throw new Error(`Erreur ${r.status} : ${await r.text()}`);
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/pdf")) return { blob: await r.blob() };
  return { message: JSON.stringify(await r.json()) };
}

// Génère une fiche au visuel d'un template (composer → mapper → overlay PDF).
export async function genererFicheOverlay(
  template: string,
  cfg: Record<string, unknown>,
): Promise<Resultat> {
  const initData = window.Telegram?.WebApp?.initData || undefined;
  const r = await fetch("/api/fiche-overlay", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...cfg, template, init_data: initData }),
  });
  if (!r.ok) throw new Error(`Erreur ${r.status} : ${await r.text()}`);
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/pdf")) return { blob: await r.blob() };
  return { message: JSON.stringify(await r.json()) };
}

// 3 fiches (mois + 2 précédents) → ZIP en local, ou envoi des 3 PDF dans le chat Telegram.
// `bruts` permet de saisir un salaire différent par mois ([m-2, m-1, m]).
export async function genererTroisMoisConfig(
  template: string,
  annee: number,
  mois: number,
  cfg: Record<string, unknown>,
  bruts?: string[],
): Promise<Resultat> {
  const initData = window.Telegram?.WebApp?.initData || undefined;
  const r = await fetch("/api/fiche-overlay-3mois", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...cfg, template, annee, mois, bruts, init_data: initData }),
  });
  if (!r.ok) throw new Error(`Erreur ${r.status} : ${await r.text()}`);
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/zip")) return { blob: await r.blob() };
  return { message: JSON.stringify(await r.json()) };
}

// Génère une fiche configurable (moteur HTML flexible) à partir d'un modèle complet.
export async function genererGenerique(fiche: Record<string, unknown>): Promise<Resultat> {
  const initData = window.Telegram?.WebApp?.initData || undefined;
  const r = await fetch("/api/fiche-generique", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...fiche, init_data: initData }),
  });
  if (!r.ok) throw new Error(`Erreur ${r.status} : ${await r.text()}`);
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/pdf")) return { blob: await r.blob() };
  return { message: JSON.stringify(await r.json()) };
}

// Génère 3 fiches : le mois choisi + les 2 précédents (ex. mai → mars, avril, mai).
export async function genererTroisMois(
  template: string,
  valeurs: Record<string, string>,
  annee: number,
  mois: number,
): Promise<Resultat> {
  const initData = window.Telegram?.WebApp?.initData || undefined;
  const r = await fetch("/api/fiche-3mois", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ template, valeurs, annee, mois, init_data: initData }),
  });
  if (!r.ok) throw new Error(`Erreur ${r.status} : ${await r.text()}`);
  const ct = r.headers.get("content-type") || "";
  if (ct.includes("application/zip")) return { blob: await r.blob() };
  return { message: JSON.stringify(await r.json()) };
}
