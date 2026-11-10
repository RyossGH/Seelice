# Avancement de Seelice v2

Ce fichier est mis à jour à chaque jalon validé. Le détail de chaque jalon est dans [`PLAN.md`](../PLAN.md).

| N° | Jalon | État |
|---|---|---|
| 0 | Cadrage et plan | ✅ validé le 10/11/2026 |
| 1 | Squelette du projet et outillage | ✅ validé le 10/11/2026 |
| 2 | Connexion, sessions, premier admin, TOTP | à faire |
| 3 | Comptes, invitations, rôles, audit | à faire |
| 4 | Caméras, pilotes, test de connexion, simulateur | à faire |
| 5 | Direct vidéo, mur de caméras, capture | à faire |
| 6 | Essai sur une vraie caméra | à faire |
| 7 | Services Windows, sauvegardes, supervision | à faire |
| 8 | Accès extérieur et durcissement | à faire |

## Jalon 0 — Cadrage et plan (10/11/2026)

**Ce qui a été fait**

- Lecture du cahier des charges et de la version Flask existante (branche `main`).
- Rédaction de `PLAN.md` : architecture, arborescence, modèle de données, routes de l'API, jalons.
- Création de la branche `v2`. La branche `main` n'est pas modifiée.

**Décisions prises**

- Réécriture en Node.js / TypeScript sur `v2`. Le code Flask sera déplacé dans `legacy/` au jalon 1, sans suppression.
- Vidéo en WebRTC avec repli MSE. Seul le port média de go2rtc est joignable, son API et son RTSP restent sur `127.0.0.1`.
- Invitations par lien copié par l'admin, sans e-mail.
- Double authentification TOTP obligatoire pour les admins dès la V1.

**Points ouverts**

- Hypothèses à confirmer : développement sur le PC actuel, deux spectateurs extérieurs, moins de 10 caméras.
- Caméras du collègue : chez l'un ou reliées par VPN, à décider avant le jalon 6.
- Accès extérieur : à décider au jalon 8.
- Le dépôt est public : aucun détail de réseau privé ne doit y être poussé.

**Comment vérifier** : lire `PLAN.md`. Aucun code n'existe encore.

## Jalon 1 — Squelette du projet et outillage (10/11/2026)

**Ce qui a été fait**

- La version Flask est déplacée dans `legacy/`, sans modification ni suppression.
- Le projet est organisé en trois parties : `apps/server` (Fastify), `apps/web` (React, Vite, Tailwind CSS) et `packages/shared` (schémas Zod communs).
- Le serveur répond sur `GET /api/healthz` et sert la page de l'interface. Il écoute sur `127.0.0.1:8080` par défaut.
- La configuration est lue depuis `.env` et validée au démarrage. `.env.example` documente les réglages.
- Outillage : TypeScript strict, ESLint, Prettier, Vitest, versions verrouillées dans `package-lock.json`.
- Nouveau `README.md` pour la branche `v2`.

**Choix technique à connaître**

- Le serveur lance directement les fichiers TypeScript avec Node.js 24, sans étape de compilation. TypeScript ne sert qu'à vérifier le typage.

**Comment vérifier**

- `npm install`, puis `npm run check` : mise en forme, lint, typage, 9 tests et construction de l'interface passent.
- `npm run start`, puis ouvrir http://localhost:8080 : la page affiche « Seelice » et « Serveur en ligne ».

**Points ouverts**

- Sur Windows, un premier `npm install` peut oublier un binaire (bug connu de npm). Si les tests refusent de démarrer, supprimer `node_modules` et relancer `npm install`.
- Pas encore de test de l'interface dans un navigateur (Playwright) : prévu avec les premiers parcours, au jalon 2.
