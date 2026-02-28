"""
QuickSave - Mod Sims 4
======================
Sauvegarde la partie en appuyant sur une touche.

Touche par défaut : F5
Alternative : tapez "quicksave" dans la console de triche (Ctrl+Maj+C)

Installation :
  Copiez QuickSave.py dans :
    Documents/Electronic Arts/The Sims 4/Mods/

  Activez les mods de script dans :
    Options du jeu → Autres → Activer les mods de script

Changer la touche :
  Modifiez la valeur de QUICKSAVE_KEY_VK ci-dessous.
  Codes courants (Windows Virtual Key) :
    F5  = 0x74  (défaut)
    F6  = 0x75
    F7  = 0x76
    F8  = 0x77
    F9  = 0x78
    F10 = 0x79
"""

import sims4
import sims4.commands
import services
import traceback
import time

# ============================================================
# Configuration — modifiez ici pour changer la touche
# ============================================================

QUICKSAVE_KEY_VK = 0x74   # F5 par défaut
CHECK_INTERVAL   = 0.15   # Intervalle de vérification en secondes
SAVE_COOLDOWN    = 3.0    # Délai minimum entre deux sauvegardes (secondes)

# ============================================================

# Chargement de l'API Windows pour la détection de touches
_user32 = None
try:
    import ctypes
    _user32 = ctypes.windll.user32
    sims4.log.info('QuickSave', 'API clavier chargée avec succès.')
except Exception:
    sims4.log.warn(
        'QuickSave',
        'Impossible de charger ctypes — la touche de raccourci est désactivée. '
        'Utilisez la commande "quicksave" dans la console de triche.'
    )


def _is_key_down(vk_code):
    """Retourne True si la touche est actuellement enfoncée."""
    if _user32 is None:
        return False
    try:
        return bool(_user32.GetAsyncKeyState(vk_code) & 0x8000)
    except Exception:
        return False


# ---- État interne ----
_prev_key_state   = False   # État de la touche lors du dernier cycle
_last_poll_time   = 0.0     # Horodatage du dernier sondage
_last_save_time   = 0.0     # Horodatage de la dernière sauvegarde
_save_in_progress = False   # Verrou anti-double sauvegarde


def _game_is_ready():
    """Retourne True uniquement si une zone jouable est bien active."""
    try:
        zone = services.current_zone()
        if zone is None:
            return False
        # Vérifier les attributs de statut selon la version du jeu
        for attr in ('is_zone_running', 'is_fully_loaded', 'is_active'):
            val = getattr(zone, attr, None)
            if val is not None:
                return bool(val)
        return True  # Zone présente mais sans attribut de statut connu
    except Exception:
        return False


def _perform_save(source='hotkey'):
    """Déclenche une sauvegarde du jeu avec plusieurs méthodes en fallback."""
    global _save_in_progress, _last_save_time

    if _save_in_progress:
        sims4.log.warn('QuickSave', 'Sauvegarde déjà en cours, requête ignorée.')
        return

    # Cooldown anti-rafale
    if time.time() - _last_save_time < SAVE_COOLDOWN:
        return

    if not _game_is_ready():
        sims4.log.warn('QuickSave', 'Zone non prête — sauvegarde ignorée.')
        return

    _save_in_progress = True
    try:
        saved = False

        # Méthode 1 — persistence_service (comportement natif du jeu)
        try:
            ps = services.get_persistence_service()
            if ps is not None:
                ps.save_using(
                    ps.save_game_gen,
                    None,                   # slot_id None = emplacement en cours
                    send_save_success=True, # Affiche la notification native du jeu
                    auto_save=False
                )
                saved = True
        except Exception:
            sims4.log.warn('QuickSave', 'Méthode 1 échouée :\n' + traceback.format_exc())

        # Méthode 2 — client (bouton Enregistrer du menu)
        if not saved:
            try:
                client_mgr = services.client_manager()
                if client_mgr is not None:
                    client = client_mgr.get_first_client()
                    if client is not None:
                        for method_name in ('save_game', 'save', 'trigger_save'):
                            fn = getattr(client, method_name, None)
                            if fn is not None:
                                fn()
                                saved = True
                                break
            except Exception:
                sims4.log.warn('QuickSave', 'Méthode 2 échouée :\n' + traceback.format_exc())

        if saved:
            _last_save_time = time.time()
            sims4.log.info('QuickSave', 'Partie sauvegardée (via {}).'.format(source))
        else:
            sims4.log.error('QuickSave', 'Toutes les méthodes de sauvegarde ont échoué.')

    except Exception:
        sims4.log.exception('QuickSave', 'Erreur inattendue :\n' + traceback.format_exc())
    finally:
        _save_in_progress = False


def _poll_hotkey():
    """Vérifie périodiquement si la touche de raccourci est appuyée."""
    global _prev_key_state, _last_poll_time

    now = time.time()
    if now - _last_poll_time < CHECK_INTERVAL:
        return
    _last_poll_time = now

    current = _is_key_down(QUICKSAVE_KEY_VK)

    # Déclenchement sur le front montant (appui, pas maintien)
    if current and not _prev_key_state:
        _perform_save(source='touche')

    _prev_key_state = current


# ---- Accrochage sur la boucle de mise à jour de la zone ----
from zone import Zone
from sims4.utils import inject


@inject(Zone, 'update')
def _zone_update(original, self, *args, **kwargs):
    """Intercepte la mise à jour de zone pour sonder la touche."""
    result = original(self, *args, **kwargs)
    try:
        _poll_hotkey()
    except Exception:
        pass  # Ne jamais interrompre la boucle principale du jeu
    return result


# ---- Réinitialisation de l'état à la fin de chaque zone ----
@inject(Zone, 'on_loading_screen_animation_finished')
def _zone_loaded(original, self, *args, **kwargs):
    """Réinitialise l'état du mod à chaque chargement de zone."""
    global _prev_key_state, _save_in_progress
    _prev_key_state   = False
    _save_in_progress = False
    return original(self, *args, **kwargs)


# ---- Commande de console de triche ----
@sims4.commands.Command('quicksave', command_type=sims4.commands.CommandType.Live)
def cmd_quicksave(_connection=None):
    """Sauvegarde via la console de triche (Ctrl+Maj+C > quicksave)."""
    output = sims4.commands.CheatOutput(_connection)
    try:
        _perform_save(source='console')
        output('[QuickSave] Partie sauvegardée !')
    except Exception as e:
        output('[QuickSave] Erreur : ' + str(e))


# Message de confirmation au chargement du mod
sims4.log.info(
    'QuickSave',
    'Mod chargé ! Raccourci : F{} | Console de triche : "quicksave"'.format(
        QUICKSAVE_KEY_VK - 0x6F
    )
)
