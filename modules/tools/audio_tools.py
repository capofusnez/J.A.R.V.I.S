try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

class AudioTools:
    def _get_volume_interface(self):
        if not PYCAW_AVAILABLE:
            return None
        try:
            devices = AudioUtilities.GetSpeakers()
            if hasattr(devices, "Activate"):
                interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            else:
                interface = devices.EndpointVolume
            return interface.QueryInterface(IAudioEndpointVolume) if hasattr(interface, "QueryInterface") else interface
        except Exception:
            try:
                devices = AudioUtilities.GetSpeakers()
                return devices.EndpointVolume
            except Exception:
                return None

    def set_volume(self, level: int) -> str:
        if not PYCAW_AVAILABLE:
            return "Controllo audio non disponibile."
        try:
            volume = self._get_volume_interface()
            if not volume:
                return "Impossibile accedere al dispositivo audio."
            level = max(0, min(100, level))
            volume.SetMasterVolumeLevelScalar(level / 100.0, None)
            return f"Volume impostato al {level}%."
        except Exception as e:
            return f"Errore volume: {e}"

    def set_volume_relative(self, delta: int) -> str:
        if not PYCAW_AVAILABLE:
            return "Controllo audio non disponibile."
        try:
            volume = self._get_volume_interface()
            if not volume:
                return "Impossibile accedere al dispositivo audio."
            current_pct = int(round(volume.GetMasterVolumeLevelScalar() * 100))
            new_pct = max(0, min(100, current_pct + delta))
            volume.SetMasterVolumeLevelScalar(new_pct / 100.0, None)
            return f"Volume portato al {new_pct}%."
        except Exception as e:
            return f"Errore nel regolare il volume: {e}"

    def set_mute(self, mute: bool) -> str:
        if not PYCAW_AVAILABLE:
            return "Controllo audio non disponibile."
        try:
            volume = self._get_volume_interface()
            if not volume:
                return "Impossibile accedere al dispositivo audio."
            volume.SetMute(1 if mute else 0, None)
            return "Audio disattivato." if mute else "Audio riattivato."
        except Exception as e:
            return f"Errore muto: {e}"