# Sudoku CTF

Challenge web CTF où les participants doivent résoudre 300 grilles de Sudoku par script pour reconstituer un flag.

---

## Table des matières

1. [Vue d'ensemble du challenge](#vue-densemble-du-challenge)
2. [Stack technique](#stack-technique)
3. [Déploiement](#déploiement)
4. [Configuration](#configuration)
5. [Vérifier que tout tourne](#vérifier-que-tout-tourne)
6. [Relancer / redémarrer](#relancer--redémarrer)
7. [Debugger](#debugger)
8. [Arrêter proprement](#arrêter-proprement)
9. [Endpoints API](#endpoints-api)
10. [Comment fonctionne le challenge](#comment-fonctionne-le-challenge)

---

## Vue d'ensemble du challenge

Les participants accèdent à une interface web et découvrent 300 grilles de Sudoku à résoudre en utilisant des jeux de symboles variés (chiffres, lettres grecques, symboles mathématiques…). Les deux premières grilles peuvent être résolues automatiquement via l'interface ; pour les suivantes, il faut écrire un solver.

Les puzzles 298, 299 et 300 sont spéciaux : la ligne centrale de chaque grille (ligne 4) encode une partie du flag. Après les avoir résolus, le participant reconstitue le flag et le soumet.

---

## Stack technique

| Composant | Technologie |
|-----------|-------------|
| Backend   | FastAPI + Uvicorn (port 8000 interne) |
| Proxy     | Nginx Alpine (port **8080** exposé) |
| Frontend  | SPA vanilla JS (ES6) |
| Orchestration | Docker Compose |

---

## Déploiement

### Prérequis

- Docker et Docker Compose installés
- Fichier `.env` présent à la racine du projet (voir [Configuration](#configuration))

### Lancer le challenge

```bash
cd sudoku-ctf
docker compose up --build -d
```

`--build` est nécessaire au premier lancement (et après toute modification du code ou du flag) car les 300 puzzles sont **générés à la compilation**. Le flag est embarqué dans les puzzles au moment du build.

L'application est ensuite accessible sur : **http://\<IP_serveur\>:8080**

### Durée du premier build

Le build prend ~2-3 minutes (génération de 300 grilles en parallèle).

---

## Configuration

### Fichier `.env`

À créer/modifier à la racine du projet. C'est le seul fichier à toucher pour changer le flag :

```env
FLAG=HSR{xxxxxx}
```

> **Important** : après tout changement du flag, il faut reconstruire l'image (`docker compose up --build -d`).  
> Le `.env` n'est pas censé être versionné (`.gitignore`), on pourra modifier le flag au besoin.
> Le flag doit avoir un taille de 27 max (tous les symbôles différents (répartis sur les 3 derniers sudoku) -> 3x9 )

### Paramètres dans `app/config.py`

| Paramètre | Valeur par défaut | Description |
|-----------|-------------------|-------------|
| `SESSION_TTL_SECONDS` | 3600 | Durée avant expiration d'une session inactive (secondes) |
| `MAX_SESSIONS` | 500 | Nombre max de sessions simultanées |
| `DEMO_LIMIT` | 2 | Nombre de puzzles où la résolution auto est disponible |

### Limites de débit (Nginx)

| Route | Limite |
|-------|--------|
| `/api/start` | 5 req/min par IP |
| `/api/puzzle/{id}/submit` | 20 req/s par IP |
| `/api/*` (global) | 30 req/s par IP |

---

## Vérifier que tout tourne

### Status des conteneurs

```bash
docker compose ps
```

Les deux conteneurs `nginx` et `app` doivent être à l'état `running` (healthy pour `app`).

### Health check de l'API

```bash
curl http://localhost:8080/api/status
```

Réponse attendue :
```json
{"status": "ok", "active_sessions": 0, "puzzles_loaded": 300}
```

### Logs en temps réel

```bash
# Tous les services
docker compose logs -f

# Backend seulement
docker compose logs -f app

# Nginx seulement
docker compose logs -f nginx
```

---

## Relancer / redémarrer

### Redémarrage simple (sans reconstruire)

À utiliser si le service plante ou après un reboot serveur :

```bash
docker compose restart
```

Ou service par service :

```bash
docker compose restart app
docker compose restart nginx
```

### Redémarrage complet avec rebuild

À utiliser après une modification du code ou du flag :

```bash
docker compose down
docker compose up --build -d
```

> Cela remet à zéro toutes les sessions en cours (stockées en mémoire).

### Après un reboot du serveur

Les conteneurs ont `restart: unless-stopped` — ils redémarrent automatiquement. Si ce n'est pas le cas :

```bash
cd sudoku-ctf
docker compose up -d
```

---

## Debugger

### Problème : le site est inaccessible

1. Vérifier que les conteneurs tournent : `docker compose ps`
2. Vérifier que le port 8080 est ouvert sur le pare-feu
3. Regarder les logs Nginx : `docker compose logs nginx`
4. Tester l'API directement (sans Nginx) :
   ```bash
   docker compose exec app curl http://localhost:8000/api/status
   ```

### Problème : l'API renvoie des erreurs 500

```bash
docker compose logs app --tail=100
```

Chercher les tracebacks Python dans la sortie.

### Problème : les puzzles ne chargent pas / flag incorrect

Le flag est embarqué dans les puzzles au build. Si le flag a changé ou si les puzzles sont corrompus :

```bash
docker compose down
docker compose up --build -d
```

### Problème : sessions qui n'expirent pas / mémoire qui monte

Les sessions expirent après 1h d'inactivité et un nettoyage automatique tourne toutes les 5 minutes. En cas de problème de mémoire, redémarrer le conteneur app suffit (les sessions sont en mémoire uniquement) :

```bash
docker compose restart app
```

### Accéder à un shell dans le conteneur

```bash
docker compose exec app bash
docker compose exec nginx sh
```

### Vérifier les ressources consommées

```bash
docker stats
```

Limites configurées : nginx 256 Mo RAM / 1 CPU, app 1 Go RAM / 4 CPU.

### Interface Swagger (debug API)

Disponible sur : **http://\<IP_serveur\>:8080/docs**

Permet de tester tous les endpoints manuellement sans client.

---

## Arrêter proprement

```bash
# Arrêter sans supprimer les conteneurs
docker compose stop

# Arrêter et supprimer les conteneurs (sessions perdues)
docker compose down

# Tout nettoyer (images incluses)
docker compose down --rmi local
```

---

## Endpoints API

| Méthode | Route | Description |
|---------|-------|-------------|
| `GET` | `/api/status` | Health check |
| `GET` | `/api/start` | Créer une session, retourne un token |
| `GET` | `/api/puzzle/{id}` | Récupérer la grille (header `X-Token` requis) |
| `GET` | `/api/puzzle/{id}/demo` | Résolution auto (2 premiers puzzles seulement) |
| `POST` | `/api/puzzle/{id}/submit` | Soumettre une solution |
| `POST` | `/api/flag` | Soumettre le flag reconstruit |
| `GET` | `/api/session` | État de la session courante |
| `GET` | `/api/log` | Journal des événements de la session |
| `GET` | `/api/symbols` | Jeux de symboles disponibles |

Toutes les routes sauf `/api/start`, `/api/status` et `/api/symbols` nécessitent le header `X-Token: <token>`.

---

## Comment fonctionne le challenge

1. Le participant démarre une session (`/api/start`) et récupère un token.
2. Il récupère et résout les 300 puzzles en boucle (en écrivant un solver après l'utilisation (ou non) des démo solver (max 2)).
3. Les puzzles 298, 299 et 300 ont leur ligne centrale (`solution[4]`) qui encode le flag (9 caractères par puzzle = 27 caractères au total).
4. Le participant concatène ces trois lignes pour former le flag et le soumet via `/api/flag`.
5. Si tous les puzzles sont résolus et le flag est correct, le challenge est validé.

**Durée typique** : quelques minutes avec un bon solver en Python.
