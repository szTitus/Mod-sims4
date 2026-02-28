"""
QuickSave - Mod Sims 4
======================
Sauvegarde la partie en appuyant sur une touche.

Touche par défaut : F5
Alternative : tapez "quicksave" dans la console de triche (Ctrl+Maj+C)

Installation :
  Copiez QuickSave.py dans :
    Documents/Electronic Arts/The Sims 4/Mods/

Changer la touche :
  Modifiez la valeur de QUICKSAVE_KEY_VK ci-dessous.
  Codes courants (Windows Virtual Key) :
    F5  = 0x74  (défaut)
    F6  = 0x75
    F7  = 0x76
    F9  = 0x78
    Orig/Home = 0x24
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
CHECK_INTERVAL   = 0.15   # Intervalle de vérification en secondes (0.15 = 150 ms)

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
_save_in_progress = False   # Verrou anti-double sauvegarde


def _perform_save(source='hotkey'):
    """Déclenche une sauvegarde du jeu."""
    global _save_in_progress

    if _save_in_progress:
        sims4.log.warn('QuickSave', 'Sauvegarde déjà en cours, requête ignorée.')
        return

    # Vérifie qu'une zone est bien active
    zone = services.current_zone()
    if zone is None:
        sims4.log.warn('QuickSave', 'Aucune zone active — sauvegarde impossible.')
        return

    try:
        _save_in_progress = True
        persistence_service = services.get_persistence_service()
        if persistence_service is None:
            sims4.log.warn('QuickSave', 'Service de persistance introuvable.')
            return

        # Sauvegarde dans l'emplacement courant
        persistence_service.save_using(
            persistence_service.save_game_gen,
            None,                   # slot_id None = emplacement en cours
            send_save_success=True, # Affiche la notification native du jeu
            auto_save=False
        )

        f_num = QUICKSAVE_KEY_VK - 0x6F  # Convertit le code VK en numéro Fn
        sims4.log.info(
            'QuickSave',
            'Partie sauvegardée via {} (F{}).'.format(source, f_num)
        )

    except Exception:
        sims4.log.exception('QuickSave', 'Erreur lors de la sauvegarde :\n' + traceback.format_exc())
    finally:
        _save_in_progress = False


def _poll_hotkey():
    """Vérifie périodiquement si la touche de raccourci est appuyée."""
    global _prev_key_state, _last_poll_time

    now = time.time()
    if now - _last_poll_time < CHECK_INTERVAL:
        return  # Pas encore le moment de vérifier
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
    'Mod chargé ! Raccourci : F{} | Console : "quicksave"'.format(
        QUICKSAVE_KEY_VK - 0x6F
    )
)
