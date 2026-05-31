# MonElec — Monitoring Électricité

Collecte les données de consommation électrique depuis l'API D2L Sicame (compteur communicant) et les visualise dans Grafana via InfluxDB.

## Architecture

```
D2L Sicame API  ──>  collector.py  ──>  InfluxDB 2.7  ──>  Grafana
                        │
                   systemd timer
                   (toutes les 30 min)
```

## Prérequis

- Python 3.13+
- Docker Compose (pour InfluxDB + Grafana)
- Un compte D2L Sicame

## Installation

```bash
# 1. Cloner le dépôt
git clone https://github.com/galettebretonne/MonElec.git
cd MonElec

# 2. Environnement virtuel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configurer les identifiants
cp .env.template .env
# Éditer .env avec vos identifiants D2L et votre token InfluxDB

# 4. Démarrer InfluxDB + Grafana
./run.sh docker-up

# 5. Premier import des données
./run.sh fetch
```

## Utilisation

### Récupération des données

```bash
./run.sh fetch          # Récupère les données → InfluxDB
./run.sh fetch-only     # Récupère les données → stdout uniquement
```

Un timer systemd (`infra/monelec-collector.{service,timer}`) peut être installé pour automatiser la collecte toutes les 30 minutes :

```bash
sudo cp infra/monelec-collector.* /etc/systemd/system/
sudo systemctl enable --now monelec-collector.timer
```

### Visualisation Grafana

Le dashboard est provisionné automatiquement dans `infra/grafana-provisioning/dashboards/electricite.json`.

Accès : http://localhost:3001 (admin / admin)

### Commandes

```bash
./run.sh docker-up      # Démarre InfluxDB + Grafana
./run.sh docker-down    # Arrête le stack
./run.sh docker-logs    # Suit les logs
./run.sh power          # Calcule la puissance instantanée
```

## Structure du projet

```
MonElec/
├── .env.template           # Configuration (identifiants, tokens)
├── run.sh                  # Script de lancement
├── src/
│   ├── collector.py        # Collecte depuis l'API D2L Sicame
│   ├── compute_power.py    # Calcule la puissance (W) depuis les index
│   ├── reverse_api.py      # Reverse-engineering de l'API
│   ├── extract_charts.py   # Extraction des données des graphiques
│   └── analyze_capture.py  # Analyse des requêtes capturées
├── infra/
│   ├── docker-compose.yml  # Stack InfluxDB 2.7 + Grafana
│   ├── grafana-provisioning/
│   │   ├── dashboards/     # Dashboard Grafana (suivi consommation)
│   │   └── datasources/    # Configuration datasource InfluxDB
│   ├── monelec-collector.service  # Service systemd
│   └── monelec-collector.timer    # Timer systemd (30 min)
└── data/                   # Données brutes (gitignoré)
```

## Dashboard Grafana

Le dashboard `electricite.json` propose :

- **Puissance** : consommation instantanée (W)
- **Aujourd'hui / Ce mois** : consommation cumulée (kWh)
- **Index total** : index cumulé du compteur
- **Consommation par jour / mois / année** : histogrammes empilés par tarif (Heures Creuses/Pleines, jours Bleu/Blanc/Rouge)
- **Tarif actif** : quel tarif Tempo est en cours
- **Coût estimé** : estimation mensuelle

## Licence

MIT
