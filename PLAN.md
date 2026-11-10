# Seelice v2 — Plan de réalisation

> Statut : **validé le 10/11/2026.** Suivi de l'avancement dans `docs/AVANCEMENT.md`.
> Ce dépôt est public : ce document ne contient volontairement ni adresse IP, ni firmware, ni détail du réseau de l'un de nous. Ces informations restent dans des fichiers locaux non versionnés (`.env`, dossier `local/`).

## 1. Objectif

Un site web unique pour voir en direct nos caméras IP, à plusieurs comptes, avec des droits stricts : chaque utilisateur ne voit que ses caméras, l'administrateur voit tout. Le serveur est un PC portable sous Windows, allumé en permanence. La V1 vise les Hanwha Wisenet QND-6082R et reste ouverte aux autres marques.

## 2. Décisions de cadrage

| Sujet | Décision | Pourquoi |
|---|---|---|
| Code existant (Flask, branche `main`) | Réécriture sur la branche `v2`. `main` n'est pas touchée. | Multi-comptes, chiffrement des mots de passe caméra et WebRTC demandent de reprendre la base. Les idées de la V1 (préréglages par marque, découverte ONVIF, mur d'écrans) sont reprises. |
| Fichiers Flask sur `v2` | Déplacés dans `legacy/` au jalon 1, pas supprimés. | On garde la référence sous la main. Suppression plus tard, sur accord des deux. |
| Suivi | Un push sur `v2` à chaque jalon validé, avec `docs/AVANCEMENT.md` mis à jour. | Référencer et expliquer l'avancement. |
| Invitations | Lien à usage unique que l'admin copie et envoie lui-même. Pas d'e-mail en V1. | Évite de configurer un serveur d'envoi. |
| TOTP | Obligatoire pour les comptes admin dès la V1, avec codes de secours. | Le compte admin voit toutes les caméras. |
| Accès extérieur | Rien d'exposé pendant les jalons 1 à 7. Choix au jalon 8 (voir §9). | Décision à conséquences, à prendre avec le site fonctionnel sous les yeux. |

**Hypothèses à confirmer** (je n'ai pas eu la réponse, je pars là-dessus) :

- le développement se fait sur le PC actuel (Node 24 déjà installé), le HP ne sert qu'à partir du jalon 7 ;
- seuls nous deux regardons depuis l'extérieur, donc 2 à 3 spectateurs simultanés au plus ;
- moins de 10 caméras au total en V1.

## 3. Architecture

```
Navigateur ──HTTPS/HTTP──▶ Backend Fastify (port 8080)
    │                         │  ├─ sert l'interface React (fichiers statiques)
    │                         │  ├─ API REST /api/* (sessions, droits, audit)
    │                         │  ├─ SQLite (fichier data/seelice.db)
    │                         │  └─ pilote go2rtc par son API, sur 127.0.0.1 uniquement
    │                         ▼
    │                     go2rtc (API et RTSP sur 127.0.0.1)
    │                         │
    └──── média WebRTC ───────┤
                              ▼
                        Caméras (RTSP, ONVIF, SUNAPI)
```

Principes :

- **Un seul point d'entrée** : le navigateur ne parle qu'au backend. L'API de go2rtc n'écoute que sur `127.0.0.1`.
- **Flux vidéo** : le navigateur envoie son offre WebRTC au backend, qui vérifie la session et les droits sur la caméra, puis la relaie à go2rtc. Les flux portent des noms opaques (UUID) que le navigateur ne choisit jamais.
- **Repli MSE** : si le WebRTC échoue (réseau filtré), la vidéo passe par un WebSocket relayé par le backend, avec le même contrôle de droits.
- **Codec** : chaque caméra expose un profil H.264 dédié au web. Pas de transcodage sur le serveur, le portable n'a pas la puissance pour ça.
- **Mur de caméras** : flux secondaire basse résolution (environ 0,5 Mbit/s par caméra). Plein écran : flux principal (2 à 4 Mbit/s).

### Point à trancher : le port média de go2rtc

Le critère « go2rtc n'est pas joignable depuis une autre machine » ne peut pas être tenu à 100 % avec du WebRTC : l'image circule directement entre le navigateur et go2rtc, donc son port média (8555) doit être joignable. Deux options :

| Option | Latence | Exposition de go2rtc |
|---|---|---|
| **A. WebRTC + repli MSE** (recommandée) | moins de 0,5 s | Port média 8555 seul. Il n'accepte que les sessions négociées par le backend (clés ICE et DTLS à usage unique). API et RTSP restent sur `127.0.0.1`. |
| B. MSE uniquement, tout relayé par le backend | environ 1 s | Aucune. |

Les deux tiennent l'objectif de moins de 2 secondes. Je pars sur A sauf avis contraire ; le critère d'acceptation devient « l'API et le RTSP de go2rtc ne sont pas joignables depuis une autre machine ».

## 4. Choix techniques

| Brique | Choix | Raison |
|---|---|---|
| Langage | TypeScript strict, Node.js 24 LTS | Un seul langage pour le serveur et l'interface. |
| Serveur | Fastify 5 + Zod | Rapide, validation des entrées par schéma. |
| Base | SQLite via `better-sqlite3` + Drizzle | Un fichier, sauvegarde simple, migrations versionnées. Drizzle plutôt que Prisma : pas de moteur binaire à part. |
| Mots de passe | Argon2id (`@node-rs/argon2`) | Binaire précompilé pour Windows, rien à compiler. |
| Interface | React 19, Vite, Tailwind CSS, TanStack Query | Interface en français. |
| Vidéo | go2rtc (binaire Windows) | RTSP vers WebRTC et MSE, piloté par API. |
| Services Windows | **WinSW** | Encore maintenu, configuration en XML versionnable, rotation des journaux intégrée. NSSM n'a plus de version depuis 2017. |
| Tests | Vitest, Playwright | Unitaires, intégration, bout en bout. |
| Qualité | ESLint, Prettier, `npm audit`, `package-lock.json` | Versions verrouillées. |

Docker n'est pas nécessaire : tout existe en binaire Windows natif.

## 5. Arborescence

```
seelice/
├─ apps/
│  ├─ server/                 Backend Fastify
│  │  ├─ src/
│  │  │  ├─ auth/             sessions, mots de passe, TOTP, invitations
│  │  │  ├─ users/            gestion des comptes (admin)
│  │  │  ├─ cameras/          CRUD, test de connexion, statut
│  │  │  ├─ drivers/          CameraDriver + hanwha-sunapi, onvif, rtsp-manual
│  │  │  ├─ streaming/        client go2rtc, signalisation WebRTC, relais MSE
│  │  │  ├─ audit/            journal d'audit
│  │  │  ├─ security/         CSRF, en-têtes, limitation de débit, anti-SSRF, chiffrement
│  │  │  ├─ db/               schéma Drizzle, migrations
│  │  │  └─ health/           santé du serveur
│  │  ├─ scripts/             create-admin, backup, restore
│  │  └─ test/                unitaires et intégration
│  └─ web/                    Interface React
│     └─ src/ (pages, composants, lecteur vidéo)
├─ packages/shared/           schémas Zod et types partagés serveur/interface
├─ tools/
│  ├─ camera-simulator/       fausse caméra RTSP pour le développement et les tests
│  └─ windows/                scripts d'installation et de désinstallation des services
├─ e2e/                       tests Playwright
├─ docs/                      ARCHITECTURE, SECURITE, AJOUTER-UNE-CAMERA, EXPLOITATION, AVANCEMENT
├─ legacy/                    ancienne version Flask, pour référence
├─ local/                     notes privées, non versionné
├─ .env.example
└─ PLAN.md
```

## 6. Modèle de données

| Table | Colonnes principales |
|---|---|
| `users` | `id` (UUID), `email` (unique), `display_name`, `password_hash`, `role` (`admin` ou `user`), `status` (`active`, `disabled`), `must_change_password`, `consent_at`, `totp_secret_enc`, `totp_enabled_at`, `failed_logins`, `locked_until`, `created_at` |
| `totp_recovery_codes` | `id`, `user_id`, `code_hash`, `used_at` |
| `invitations` | `id`, `token_hash`, `email`, `role`, `created_by`, `expires_at`, `used_at` |
| `sessions` | `id`, `token_hash`, `user_id`, `created_at`, `last_seen_at`, `expires_at`, `ip`, `user_agent` |
| `cameras` | `id` (UUID), `owner_id`, `name`, `location`, `driver`, `host`, `http_port`, `rtsp_port`, `username`, `password_enc`, `model`, `firmware`, `status`, `last_seen_at`, `created_at` |
| `camera_streams` | `id` (UUID, sert de nom de flux go2rtc), `camera_id`, `kind` (`main`, `sub`), `rtsp_path`, `codec`, `width`, `height` |
| `audit_log` | `id`, `at`, `actor_id`, `action`, `target_type`, `target_id`, `ip`, `details` (JSON, sans secret) |

Règles :

- les jetons de session et d'invitation ne sont stockés que sous forme de hachage ;
- `password_enc` et `totp_secret_enc` sont chiffrés en AES-256-GCM, avec une clé gardée dans un fichier hors de la base et hors de Git ;
- `audit_log` n'a aucune route de modification ni de suppression.

## 7. Routes de l'API

Toutes sous `/api`. Sauf mention contraire, une session valide est exigée. Les requêtes qui modifient quelque chose exigent en plus un jeton CSRF.

| Méthode et chemin | Rôle | Effet |
|---|---|---|
| `POST /auth/login` | public | Connexion, limitée en débit |
| `POST /auth/totp` | public (étape 2) | Vérifie le code TOTP ou un code de secours |
| `POST /auth/logout` | tous | Ferme la session |
| `GET /auth/me` | tous | Compte courant et jeton CSRF |
| `GET /invitations/:token` | public | Vérifie une invitation |
| `POST /invitations/:token/accept` | public | Crée le compte : mot de passe et consentement |
| `GET /account/sessions` | tous | Mes sessions actives |
| `DELETE /account/sessions/:id` | tous | Ferme une de mes sessions |
| `POST /account/sessions/revoke-all` | tous | Ferme toutes mes autres sessions |
| `POST /account/password` | tous | Change mon mot de passe |
| `POST /account/totp/setup`, `/enable`, `/disable` | tous | Gère ma double authentification |
| `GET /users` | admin | Liste des comptes |
| `POST /users/invitations` | admin | Crée un lien d'invitation |
| `PATCH /users/:id` | admin | Rôle, activation, désactivation |
| `POST /users/:id/reset-password` | admin | Mot de passe temporaire |
| `DELETE /users/:id` | admin | Supprime un compte |
| `GET /cameras` | tous | Mes caméras (toutes pour l'admin) |
| `POST /cameras/test` | tous | Teste une connexion sans enregistrer |
| `POST /cameras` | tous | Ajoute une caméra |
| `GET /cameras/:id` | propriétaire, admin | Détail, sans le mot de passe |
| `PATCH /cameras/:id` | propriétaire, admin | Modifie |
| `DELETE /cameras/:id` | propriétaire, admin | Supprime |
| `GET /cameras/:id/snapshot` | propriétaire, admin | Image JPEG |
| `POST /cameras/:id/streams/:kind/webrtc` | propriétaire, admin | Échange l'offre WebRTC |
| `GET /cameras/:id/streams/:kind/mse` (WebSocket) | propriétaire, admin | Repli MSE |
| `GET /audit` | admin | Journal d'audit, paginé |
| `GET /health` | admin | Services, caméras en ligne, disque, version |
| `GET /healthz` | public | Simple « ok » pour la supervision |

Une caméra qui n'appartient pas à l'utilisateur répond **404**, comme si elle n'existait pas.

## 8. Sécurité

Cible : OWASP ASVS niveau 2.

- **Mots de passe** : Argon2id, 12 caractères minimum, refus des mots de passe courants.
- **Sessions** : stockées côté serveur, cookie `HttpOnly`, `Secure`, `SameSite=Strict`, expiration après 30 minutes d'inactivité et 12 heures au total, nouvel identifiant à chaque connexion.
- **Connexion** : limitation de débit par adresse IP, verrouillage temporaire du compte après 5 échecs.
- **Navigateur** : jeton CSRF, CSP stricte, HSTS derrière HTTPS, `X-Content-Type-Options`, `Referrer-Policy`, CORS fermé.
- **Anti-SSRF** : l'adresse d'une caméra est résolue puis comparée à une liste de réseaux autorisés (`CAMERA_ALLOWED_NETWORKS`). Sont toujours refusés : `127.0.0.0/8`, les adresses de lien local et de métadonnées, et les adresses du serveur lui-même. La connexion se fait sur l'adresse vérifiée, pas sur le nom.
- **Secrets** : uniquement dans `.env` et dans le fichier de clé, jamais dans Git ni dans les journaux. Les journaux masquent les mots de passe et les URL RTSP.
- **go2rtc** : les flux sont créés à chaud par l'API. À vérifier au jalon 5 : que go2rtc n'écrit pas les mots de passe caméra sur le disque. Sinon, son fichier de configuration sera restreint au compte du service.
- **Sauvegardes** : copie quotidienne de la base et, à un autre endroit, de la clé de chiffrement. Restauration testée et documentée.

## 9. Options à choisir plus tard

### Caméras du collègue (à décider avant le jalon 6)

| Option | Avantages | Inconvénients |
|---|---|---|
| Toutes les caméras sur le réseau du serveur | Le plus simple et le plus fiable, latence minimale, un seul site à maintenir. | Les caméras ne filment plus chez le collègue. |
| Site distant relié par VPN (Tailscale en *subnet router*, ou WireGuard site à site) | Les caméras restent où elles sont utiles. | Un appareil allumé en permanence chez le collègue, dépendance à son débit montant, un réglage réseau de plus à maintenir. |

L'application fonctionne à l'identique dans les deux cas : une caméra est une adresse joignable depuis le serveur.

### Accès depuis l'extérieur (jalon 8)

| Option | Pour qui | Compromis |
|---|---|---|
| **Tailscale** (recommandée selon l'hypothèse « nous deux ») | Ceux qui installent Tailscale | Rien d'exposé sur Internet. Chaque spectateur doit installer l'application. |
| Cloudflare Tunnel | N'importe qui avec un compte Seelice | HTTPS public sans ouvrir de port, mais un nom de domaine à acheter, et le WebRTC demande un relais ou le repli MSE. |
| Redirection de port + Caddy | — | Déconseillée : expose directement le serveur. |

## 10. Jalons

Chaque jalon se termine par un résumé, les commandes de vérification, l'état des tests, puis un commit et un push sur `v2` **après validation**.

| N° | Contenu | Vérification |
|---|---|---|
| 0 | Ce plan | Validation du plan |
| 1 | Squelette du projet, outillage, `legacy/`, lint et tests lancés par une seule commande | `npm run check` passe, page d'accueil vide servie par le backend |
| 2 | Connexion, sessions, CSRF, limitation de débit, script `create-admin`, TOTP admin | Tests d'authentification, connexion complète dans le navigateur |
| 3 | Comptes, invitations, rôles, journal d'audit, page « Mon compte », page confidentialité | Parcours invitation de bout en bout, tests de droits |
| 4 | Modèle caméra, trois pilotes, test de connexion, anti-SSRF, chiffrement, simulateur | Ajout d'une caméra simulée, tests d'autorisation entre deux utilisateurs |
| 5 | go2rtc, direct WebRTC et repli MSE, mur de caméras, plein écran, capture, statut | Direct sur la caméra simulée, tests d'accès aux flux |
| 6 | Essai sur une vraie QND-6082R, profil H.264 web, procédure de préparation d'une caméra | Latence mesurée sous 2 s sur PC et téléphone |
| 7 | Services Windows sur le HP, sauvegardes, page de santé, réglages 24 h/24 | Le site revient seul après un redémarrage |
| 8 | Accès extérieur selon l'option choisie, durcissement, documentation finale | Critères d'acceptation de la V1 tous cochés |

Les jalons 1 à 5 ne demandent aucune action sur le matériel. À partir du jalon 6, chaque action sur une caméra, le HP ou le réseau est demandée une par une, au format « 🛑 ACTION REQUISE », et attend une réponse.

Seul besoin d'installation avant le jalon 6 : `ffmpeg` et `go2rtc` sur le PC de développement, pour le simulateur (jalons 4 et 5). Ils seront demandés le moment venu.
