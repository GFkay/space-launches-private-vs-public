"""
Script de collecte brute — API Launch Library 2 (thespacedevs.com)
====================================================================

Étape 1 du pipeline de données (voir data pipeline du cours DALAS) :
- Interroge l'API pour un ou plusieurs endpoints (launches, agencies, pads, launcher_configs)
- Respecte la limite de 15 requêtes/heure (tier gratuit non-authentifié)
- Sauvegarde CHAQUE page brute telle quelle (aucune transformation) dans data/raw/<endpoint>/
- Reprend automatiquement là où il s'était arrêté en cas d'interruption (checkpoint)
- Ne modifie jamais les fichiers déjà écrits : la donnée brute est en lecture seule

Usage :
    python collect_launch_library.py --endpoint launches
    python collect_launch_library.py --endpoint agencies pads launcher_configs
    python collect_launch_library.py --endpoint launches --count-only   # juste connaître le volume, 1 seule requête
    python collect_launch_library.py --endpoint launches --delay 5      # à utiliser seulement si vous avez une clé API avec un quota plus élevé

Dépendances : requests (pip install requests)
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

BASE_URL = "https://ll.thespacedevs.com/2.0.0"

# Nom logique -> chemin de l'endpoint sur l'API
ENDPOINTS: dict[str, str] = {
    "launches": "/launch/",
    "agencies": "/agencies/",
    "pads": "/pad/",
    "launcher_configs": "/config/launcher/",
}

PAGE_SIZE = 100  # maximum autorisé par l'API
# 15 requêtes/heure -> 1 requête toutes les 240s pour rester large sous la limite
DEFAULT_DELAY_SECONDS = 245

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Fonctions de collecte
# --------------------------------------------------------------------------

def fetch_page(endpoint_path: str, offset: int, limit: int = PAGE_SIZE) -> dict:
    """Récupère une page de résultats depuis l'API, avec gestion des erreurs 429/5xx."""
    url = f"{BASE_URL}{endpoint_path}"
    params = {"limit": limit, "offset": offset}

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, params=params, timeout=60)
        except requests.exceptions.RequestException as exc:
            # Timeout, connexion coupée, DNS, wifi instable, etc. : on réessaie avec backoff
            wait_seconds = min(30 * attempt, 180)
            logger.warning(
                "Erreur réseau (%s) — nouvelle tentative dans %ss (essai %s/%s)",
                exc.__class__.__name__, wait_seconds, attempt, max_attempts,
            )
            time.sleep(wait_seconds)
            continue

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            # Rate limit dépassé : on respecte l'en-tête Retry-After si présent
            retry_after = int(response.headers.get("Retry-After", 300))
            logger.warning(
                "429 Too Many Requests — attente de %ss avant nouvelle tentative (essai %s/%s)",
                retry_after, attempt, max_attempts,
            )
            time.sleep(retry_after)
            continue

        if response.status_code >= 500:
            # Erreur serveur temporaire : on réessaie aussi
            wait_seconds = min(30 * attempt, 180)
            logger.warning(
                "Erreur serveur %s — nouvelle tentative dans %ss (essai %s/%s)",
                response.status_code, wait_seconds, attempt, max_attempts,
            )
            time.sleep(wait_seconds)
            continue

        logger.error("Erreur HTTP %s pour %s (offset=%s)", response.status_code, url, offset)
        response.raise_for_status()

    raise RuntimeError(f"Échec après {max_attempts} tentatives pour offset={offset} sur {endpoint_path}")


def load_checkpoint(checkpoint_path: Path) -> dict:
    if checkpoint_path.exists():
        return json.loads(checkpoint_path.read_text(encoding="utf-8"))
    return {"next_offset": 0, "done": False, "total_count": None}


def save_checkpoint(checkpoint_path: Path, checkpoint: dict) -> None:
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def collect_endpoint(
    endpoint_name: str,
    delay_seconds: int = DEFAULT_DELAY_SECONDS,
    count_only: bool = False,
) -> None:
    """Collecte l'intégralité d'un endpoint, page par page, avec reprise sur checkpoint."""
    endpoint_path = ENDPOINTS[endpoint_name]
    output_dir = DATA_DIR / endpoint_name
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "_checkpoint.json"

    checkpoint = load_checkpoint(checkpoint_path)

    if checkpoint["done"] and not count_only:
        logger.info("Endpoint '%s' déjà entièrement collecté (voir checkpoint). Rien à faire.", endpoint_name)
        return

    offset = checkpoint["next_offset"]
    total_count = checkpoint["total_count"]

    while True:
        logger.info("Collecte '%s' — offset=%s", endpoint_name, offset)
        page = fetch_page(endpoint_path, offset)

        if total_count is None:
            total_count = page["count"]
            checkpoint["total_count"] = total_count
            logger.info("Volume total détecté pour '%s' : %s éléments", endpoint_name, total_count)

        if count_only:
            logger.info("Mode --count-only : arrêt après la première requête.")
            return

        # Sauvegarde de la page brute, non modifiée, horodatée pour la reproductibilité
        page_file = output_dir / f"page_offset_{offset:06d}.json"
        record = {
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_url": f"{BASE_URL}{endpoint_path}",
            "offset": offset,
            "limit": PAGE_SIZE,
            "raw_response": page,
        }
        page_file.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        offset += PAGE_SIZE
        checkpoint["next_offset"] = offset
        save_checkpoint(checkpoint_path, checkpoint)

        if page["next"] is None:
            checkpoint["done"] = True
            save_checkpoint(checkpoint_path, checkpoint)
            logger.info("Collecte de '%s' terminée : %s éléments récupérés.", endpoint_name, total_count)
            break

        logger.info("Pause de %ss avant la prochaine requête (limite API : 15/heure)...", delay_seconds)
        time.sleep(delay_seconds)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Collecte brute — API Launch Library 2")
    parser.add_argument(
        "--endpoint",
        nargs="+",
        choices=list(ENDPOINTS.keys()),
        required=True,
        help="Un ou plusieurs endpoints à collecter",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=DEFAULT_DELAY_SECONDS,
        help="Délai en secondes entre deux requêtes (par défaut 245s pour rester sous 15/h)",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Ne fait qu'une seule requête pour afficher le volume total disponible",
    )
    args = parser.parse_args()

    try:
        for endpoint_name in args.endpoint:
            collect_endpoint(endpoint_name, delay_seconds=args.delay, count_only=args.count_only)
    except (RuntimeError, KeyboardInterrupt) as exc:
        logger.warning(
            "Arrêt du script (%s). Aucune donnée perdue : relance exactement la même "
            "commande pour reprendre automatiquement là où tu t'es arrêté.",
            exc.__class__.__name__,
        )


if __name__ == "__main__":
    main()