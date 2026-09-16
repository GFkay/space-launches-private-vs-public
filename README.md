# 🚀 Le privé a-t-il rendu l'espace plus accessible ?

Projet réalisé dans le cadre du cours **DALAS** (Data Science, Learning and ApplicationS) — Sorbonne Université.

## Question de recherche

> Le secteur privé (SpaceX, Blue Origin, Rocket Lab...) a-t-il rendu l'accès à l'espace plus fiable et plus fréquent que les agences publiques historiques (NASA, Roscosmos, CNES...) ?

## Sources de données

- **[Launch Library 2 API](https://ll.thespacedevs.com/)** — historique complet des lancements orbitaux (~6000 lancements), agences, sites de lancement, configurations de fusées
- **Wikipédia** — enrichissement : coût par lancement (infobox des pages fusées), dates-repères (premiers atterrissages réussis, jalons technologiques)

## Pipeline de données

| Étape | Script | Description |
|---|---|---|
| 1 | `scripts/01_collect_launch_library.py` | Collecte brute via l'API (raw, jamais modifié) |
| 2 | `scripts/02_merge_sources.py` | Fusion launches / agencies / pads / launcher_configs |
| 3 | `scripts/03_clean.py` | Nettoyage (valeurs manquantes, statuts ambigus, doublons) |
| 4 | `scripts/04_enrich_external.py` | Ajout coûts + dates-repères externes |
| 5 | `scripts/05_compute_metrics.py` | Calcul des métriques maison (taux de succès, fréquence, réutilisation) |

Chaque étape lit la sortie de la précédente et écrit une nouvelle version — les données brutes ne sont jamais modifiées (`data/raw/` en lecture seule).

## Structure du projet

```
data/          raw → interim → processed (voir pipeline ci-dessus)
scripts/       un script par étape, exécutables dans l'ordre
notebooks/     exploration (EDA), non destiné à la production
dashboard/     application Streamlit (TME6)
reports/       livrables du cours (TME4, rapport visuel, rapport technique)
tests/         tests unitaires sur les fonctions de nettoyage/métriques
```

## Installation

```bash
pip install -r requirements.txt
```

## Reproduire le pipeline

```bash
python scripts/01_collect_launch_library.py --endpoint launches agencies pads launcher_configs
python scripts/02_merge_sources.py
python scripts/03_clean.py
python scripts/04_enrich_external.py
python scripts/05_compute_metrics.py
```

## Auteur

Klay — M2, projet individuel DALAS
