# Seelice *(prononcez « silice »)*

Seelice centralise des caméras IP dans un seul site web, à plusieurs comptes : chaque utilisateur voit ses caméras, l'administrateur voit tout.

> **Branche `v2` : réécriture en cours.** La première version (Python / Flask) reste disponible sur la branche `main` et, pour référence, dans le dossier [`legacy/`](legacy/).

- Le plan complet : [`PLAN.md`](PLAN.md)
- Où on en est : [`docs/AVANCEMENT.md`](docs/AVANCEMENT.md)

## Démarrer en développement

Prérequis : [Node.js 24](https://nodejs.org/) ou plus récent.

```bash
npm install        # installe les dépendances
npm run build      # construit l'interface web
npm run start      # lance le serveur sur http://localhost:8080
```

Par défaut, le serveur n'écoute que sur ce PC (`127.0.0.1`). Pour changer l'adresse ou le port, copie `.env.example` en `.env` et modifie-le. Le fichier `.env` n'est jamais envoyé sur Git.

Pour travailler sur l'interface avec rechargement automatique, lance dans deux terminaux :

```bash
npm run dev        # serveur, redémarre à chaque modification
npm run dev:web    # interface sur http://localhost:5173
```

## Vérifier le code

```bash
npm run check
```

Cette commande enchaîne la mise en forme (Prettier), le lint (ESLint), le typage (TypeScript), les tests (Vitest) et la construction de l'interface. Elle doit passer avant chaque commit.

## Organisation du dépôt

| Dossier | Contenu |
|---|---|
| `apps/server` | Serveur (Fastify, TypeScript) |
| `apps/web` | Interface (React, Vite, Tailwind CSS) |
| `packages/shared` | Schémas et types partagés entre le serveur et l'interface |
| `docs` | Documentation et suivi de l'avancement |
| `legacy` | Première version en Python / Flask, conservée pour référence |
