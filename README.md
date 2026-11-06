# CamHub — gestion centralisée de caméras IP (lab)

Mini-VMS web pour centraliser des caméras IP sur un réseau : inventaire, statut, mosaïque live, plein écran, captures, découverte réseau.

## Installation (Windows)

1. **Python 3.10+** : https://www.python.org/downloads/ — coche bien **« Add python.exe to PATH »**.
2. **ffmpeg** (indispensable pour la vidéo) : dans un terminal, `winget install Gyan.FFmpeg`, puis ferme et rouvre le terminal.
3. Double-clique sur **`lancer.bat`**.
4. Ouvre **http://localhost:8080** et choisis ton mot de passe admin.

Sous Linux : `chmod +x lancer.sh && ./lancer.sh`.

Depuis un autre appareil du réseau (téléphone, autre PC) : `http://<ip-du-pc>:8080`.
Si Windows demande l'autorisation du pare-feu, accepte pour les **réseaux privés** uniquement.

## Premiers pas

1. **Sans matériel** : « + Ajouter une caméra » → type « Caméra de démo » pour voir l'interface tourner.
2. **Branche une caméra** sur le switch PoE, puis le switch sur ta box (ou sur le PC).
3. **Scanner le réseau** → « Lancer la découverte » (ONVIF). Si une caméra annonce une IP d'un autre sous-réseau
   (ex. Hikvision 192.168.1.64, Dahua 192.168.1.108 après reset), change son IP avec SADP / ConfigTool
   ou sa page web pour la mettre dans le réseau de ta box.
4. Clique sur **Ajouter**, renseigne l'utilisateur / mot de passe de la caméra. Les chemins RTSP sont pré-remplis selon la marque.
5. Pas d'image ? Teste l'URL RTSP dans **VLC** (Média → Ouvrir un flux réseau) : si VLC n'y arrive pas, c'est
   le chemin, les identifiants ou le RTSP désactivé dans la caméra.

## Comment ça marche

- Un **seul process ffmpeg par caméra et par qualité**, partagé entre tous les spectateurs. Il est coupé tout seul
  20 s après que plus personne ne regarde.
- La mosaïque utilise le **flux secondaire** (basse résolution), le plein écran le **flux principal** (HD).
- Le statut en ligne / hors ligne = test de connexion TCP sur le port RTSP, toutes les 10 s.
- Données dans `data/` : `camhub.db` (SQLite), `config.json` (mot de passe admin haché), `captures/`.

## Sécurité (à garder en tête)

- Les mots de passe des caméras sont stockés **en clair** dans `data/camhub.db` (ffmpeg en a besoin) → protège ce dossier.
- Serveur web de développement Flask, en HTTP : **réseau local uniquement**, ne jamais l'exposer sur Internet
  (pas de redirection de port sur la box). Pour l'accès à distance → VPN (WireGuard).
- Bonne pratique « client » : caméras dans un VLAN dédié, sans accès Internet, mot de passe unique par caméra.

## Pistes pour la suite

- Enregistrement continu / sur détection (segments ffmpeg + rétention 30 jours)
- Détection IA de personnes / véhicules (Frigate ou YOLO) + notifications téléphone
- Comptes utilisateurs avec droits (admin / lecture seule)
- Supervision des switchs PoE (SNMP : port, consommation, redémarrage d'une caméra à distance)
- Export de la fiche d'installation (plan d'adressage, VLAN, ports) en PDF pour le client
