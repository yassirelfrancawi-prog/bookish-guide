# Certifio

WebApp Telegram qui génère des **fiches de paie PDF au millimètre** à partir de
modèles réels, en remplaçant uniquement le contenu (identité, montants).

## Principe

```
Front (Telegram UI)  →  API FastAPI  →  overlay sur le PDF original  →  PDF
                                     ↘ (moteur de calcul BE, optionnel)
```

Deux techniques de rendu :

- **Overlay (principal)** — on garde le PDF original comme fond (décor intact =
  fidélité au millimètre par construction) et on tamponne les nouvelles valeurs
  aux positions/police exactes. Un seul moteur générique ; **chaque modèle = une
  carte de champs** (`backend/registre.py`).
- **HTML/CSS → WeasyPrint (plan B)** — reconstruction, pour les cas sans original.

## Lancer en local

```bash
# 1. backend (port 8077)
cd backend
../.venv/bin/uvicorn api:app --reload --port 8077

# 2. front (port 5173, proxy /api → 8077)
cd frontend
npm install        # première fois
npm run dev
```

Puis ouvrir http://localhost:5173/. Sans `BOT_TOKEN`, l'API renvoie le PDF en
téléchargement ; avec, le bot le poste dans le chat (après validation `initData`).

## API

| Endpoint | Rôle |
|----------|------|
| `GET /api/templates` | liste les modèles et leurs champs |
| `POST /api/generer-overlay` | `{template, valeurs}` → PDF au millimètre |
| `POST /api/fiche` | `{template, lignes, identite}` → moteur puis overlay (SD Worx) |
| `POST /api/generer` | rendu HTML/CSS (plan B) |

## Structure (`backend/`)

| Fichier | Rôle |
|---------|------|
| `moteur_be.py` | calcul brut→net belge (assemblage + ONSS + bonus de base) |
| `baremes_be.py` | barèmes officiels sourcés (ONSS, bonus, précompte, CSSS) |
| `overlay.py` | moteur d'overlay + carte de champs semi-auto (5 modes de localisation) |
| `fonts.py` | police : embarquée → fallback complet si glyphe manquant |
| `registre.py` | modèles : PDF + carte de champs + mapper moteur→champs |
| `rendu_pdf.py` | rendu HTML/CSS (plan B) + gabarit Jinja2 |
| `api.py` | endpoints FastAPI |

Modèles cartographiés : **SD Worx (Belgique, employé)**, **CPAS Verviers (public)**.

## État

- ✅ Moteur BE validé au centime sur fiche réelle (net 2.508,94).
- ✅ Calculé de source officielle : ONSS 13,07 %, bonus à l'emploi de base.
- ✅ 2 modèles rendus au millimètre, identité pilotée par données.
- ✅ Fallback de police (glyphe manquant du sous-ensemble embarqué).
- ⛔ **Bloqué (réforme De Wever 2026 non publiée)** : valeur réformée de la quotité
  exemptée (précompte) et renforcement du bonus à l'emploi → traités en entrées,
  prêts à brancher dès publication (paramètres déjà câblés).

## À faire

- Déposer `Arimo-Regular.ttf` + `Tinos-Regular.ttf` dans `backend/fonts/` (fallback
  portable ; sinon repli sur la police système en dev).
- Mapper CPAS (structure publique ≠ moteur BE).
- `BOT_TOKEN` + hébergement HTTPS pour tourner dans le vrai Telegram.
- Étendre aux modèles France / Suisse (= nouvelles cartes de champs).
