# quicksave_mod.py — Sims 4 Quick Save Mod
# Appuyez sur F5 pour sauvegarder instantanément la partie.
#
# Installation :
#   Copiez ce fichier dans :
#   Documents\Electronic Arts\The Sims 4\Mods\
#   (ou dans un sous-dossier direct de Mods\)
#
#   Activez les mods de script dans :
#   Options du jeu → Autres → Activer les mods de script
#
# Touche par défaut : F5
# Changez SAVE_KEY ci-dessous pour utiliser une autre touche.
# Codes VK courants : F5=0x74  F8=0x77  F9=0x78  F10=0x79

import threading
import time
import ctypes

import services
import sims4.log

# ─── Configuration ────────────────────────────────────────────────────────────

SAVE_KEY       = 0x74   # F5
CHECK_INTERVAL = 0.15   # secondes entre chaque vérification de touche
SAVE_COOLDOWN  = 3.0    # secondes minimum entre deux sauvegardes

# ─── Logger ───────────────────────────────────────────────────────────────────

logger = sims4.log.Logger('QuickSave', default_owner='QuickSaveMod')

# ─── État interne ─────────────────────────────────────────────────────────────

_stop_event    = threading.Event()
_prev_pressed  = False
_last_save_at  = 0.0

# ─── Vérification de l'état du jeu ────────────────────────────────────────────

def _game_is_ready():
    """Retourne True uniquement si une zone jouable est bien active."""
    try:
        zone = services.current_zone()
        if zone is None:
            return False
        # Refuser si la zone est encore en chargement ou en train de se fermer
        for attr in ('is_zone_running', 'is_fully_loaded', 'is_active'):
            val = getattr(zone, attr, None)
            if val is not None:
                return bool(val)
        # Aucun attribut de statut trouvé : on accepte si la zone existe
        return True
    except Exception:
        return False

# ─── Détection de touche ──────────────────────────────────────────────────────

def _is_key_down(vk_code):
    """Lit l'état d'une touche via l'API Windows (GetAsyncKeyState)."""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False

# ─── Sauvegarde ───────────────────────────────────────────────────────────────

def _try_save_via_persistence():
    """
    Méthode principale : imite exactement la sauvegarde normale du jeu.
    Récupère le slot actif puis appelle save_using() avec ses données.
    """
    ps = services.get_persistence_service()
    if ps is None:
        raise RuntimeError('persistence_service introuvable')

    # Récupérer l'identifiant du slot de sauvegarde actif
    slot_id = None
    for attr in ('primary_save_slot', 'current_slot_id', '_save_slot_id', 'save_slot_id'):
        val = getattr(ps, attr, None)
        if val is not None:
            slot_id = val
            break

    # Récupérer les données du slot (proto buffer) si possible
    save_slot_data = None
    if slot_id is not None:
        for method in ('get_save_slot_proto_buff', 'get_slot_proto', 'get_save_slot_data'):
            fn = getattr(ps, method, None)
            if fn is not None:
                try:
                    save_slot_data = fn(slot_id)
                except Exception:
                    pass
                break

    # Appel de la sauvegarde
    ps.save_using(save_slot_data=save_slot_data, slot_id=slot_id)


def _try_save_via_client():
    """
    Méthode de secours : passe par le client (équivalent du bouton Enregistrer
    dans le menu du jeu).
    """
    client_manager = services.client_manager()
    if client_manager is None:
        raise RuntimeError('client_manager introuvable')
    client = client_manager.get_first_client()
    if client is None:
        raise RuntimeError('aucun client actif')

    # Le nom de la méthode varie légèrement selon la version du jeu
    for method in ('save_game', 'save', 'trigger_save'):
        fn = getattr(client, method, None)
        if fn is not None:
            fn()
            return
    raise RuntimeError('aucune méthode de sauvegarde sur le client')


def _do_save():
    """
    Tente de sauvegarder en chaînant les méthodes disponibles.
    Retourne True si la sauvegarde a réussi.
    """
    global _last_save_at

    # Cooldown : éviter les sauvegardes en rafale
    now = time.time()
    if now - _last_save_at < SAVE_COOLDOWN:
        return False

    if not _game_is_ready():
        logger.info('QuickSave: zone non prête, sauvegarde ignorée.')
        return False

    # Méthode 1 – persistence_service (la plus proche du comportement natif)
    try:
        _try_save_via_persistence()
        _last_save_at = time.time()
        logger.info('QuickSave: partie sauvegardée.')
        return True
    except Exception as e:
        logger.error('QuickSave (méthode 1) échouée : {}'.format(e))

    # Méthode 2 – client
    try:
        _try_save_via_client()
        _last_save_at = time.time()
        logger.info('QuickSave: partie sauvegardée (via client).')
        return True
    except Exception as e:
        logger.error('QuickSave (méthode 2) échouée : {}'.format(e))

    logger.error('QuickSave: toutes les méthodes ont échoué.')
    return False

# ─── Thread de surveillance ───────────────────────────────────────────────────

def _monitor_loop():
    global _prev_pressed
    logger.info('QuickSave: démarré. Appuyez sur F5 pour sauvegarder.')

    while not _stop_event.is_set():
        try:
            pressed = _is_key_down(SAVE_KEY)
            # Front montant uniquement (évite la répétition si la touche reste enfoncée)
            if pressed and not _prev_pressed:
                _do_save()
            _prev_pressed = pressed
        except Exception as e:
            logger.error('QuickSave erreur de boucle : {}'.format(e))

        time.sleep(CHECK_INTERVAL)

# ─── Démarrage ────────────────────────────────────────────────────────────────

_monitor_thread = threading.Thread(
    target=_monitor_loop,
    name='QuickSave_Monitor',
    daemon=True,
)
_monitor_thread.start()
