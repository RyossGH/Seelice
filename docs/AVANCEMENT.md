# Avancement de Seelice v2

Ce fichier est mis à jour à chaque jalon validé. Le détail de chaque jalon est dans [`PLAN.md`](../PLAN.md).

| N° | Jalon | État |
|---|---|---|
| 0 | Cadrage et plan | ✅ validé le 10/11/2026 |
| 1 | Squelette du projet et outillage | à faire |
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
