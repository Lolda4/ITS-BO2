"""
PluginLoader – Auto-discovery UC pluginů z plugins/ složky.

Při startu automaticky prohledá složku a načte všechny třídy dědící
BaseUseCase. Přidat nový UC = vytvořit jeden soubor v plugins/.
Odebrat = smazat soubor.

Plugin loader zachytává výjimky per-plugin při registraci.
Chybný plugin = disabled s chybovou zprávou v /api/v1/system/status.
Ostatní UC fungují dál.
"""

import importlib
import inspect
import logging
import os
import sys
from typing import Optional

from core.base_uc import BaseUseCase, UCProfile

logger = logging.getLogger("itsbo.core.plugin_loader")


class PluginLoader:
    """
    Auto-discovery a registrace UC pluginů.

    Prohledá plugins/ složku, importuje .py moduly (kromě __init__.py),
    a zaregistruje všechny třídy dědící BaseUseCase.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, BaseUseCase] = {}  # uc_id → instance
        self._errors: dict[str, str] = {}            # uc_id nebo filename → error message
        self._loaded: bool = False

    def load(self, plugins_dir: str = "plugins") -> None:
        """
        Objeví a načte všechny UC pluginy z dané složky.

        Zachytává výjimky per-plugin: chybný plugin = disabled
        s error zprávou, ostatní fungují dál.

        Args:
            plugins_dir: cesta ke složce s pluginy (relativní k CWD).
        """
        self._plugins = {}
        self._errors = {}

        if not os.path.isdir(plugins_dir):
            logger.warning("Plugins directory '%s' not found", plugins_dir)
            self._loaded = True
            return

        # Přidej plugins_dir do sys.path pokud tam není
        abs_dir = os.path.abspath(plugins_dir)
        parent_dir = os.path.dirname(abs_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        for filename in sorted(os.listdir(plugins_dir)):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            module_name = f"plugins.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)
                self._discover_plugins_in_module(module, filename)
            except Exception as e:
                error_msg = f"Failed to import {module_name}: {e}"
                logger.error(error_msg)
                self._errors[filename] = error_msg

        self._loaded = True
        logger.info(
            "PluginLoader: %d plugins loaded, %d errors",
            len(self._plugins), len(self._errors),
        )

    def _discover_plugins_in_module(self, module, filename: str) -> None:
        """Najde a zaregistruje třídy dědící BaseUseCase v daném modulu."""
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseUseCase)
                and obj is not BaseUseCase
                and obj.__module__ == module.__name__
            ):
                try:
                    instance = obj()
                    profile = instance.profile()
                    uc_id = profile.id

                    if uc_id in self._plugins:
                        logger.warning(
                            "Duplicate UC ID '%s' from %s (already loaded from %s)",
                            uc_id, filename, type(self._plugins[uc_id]).__name__,
                        )
                        continue

                    self._plugins[uc_id] = instance
                    logger.info(
                        "Loaded plugin: %s (%s) from %s",
                        uc_id, profile.name, filename,
                    )
                except Exception as e:
                    error_msg = f"Failed to instantiate {name} from {filename}: {e}"
                    logger.error(error_msg)
                    self._errors[f"{filename}:{name}"] = error_msg

    def get_plugin(self, uc_id: str) -> Optional[BaseUseCase]:
        """
        Vrátí instanci pluginu pro dané uc_id.

        Args:
            uc_id: identifikátor UC (např. "UC-A").

        Returns:
            BaseUseCase instance nebo None pokud plugin neexistuje/je chybný.
        """
        return self._plugins.get(uc_id)

    def get_profiles(self) -> list[dict]:
        """
        Vrátí seznam profilů všech aktivních pluginů.

        Konvertuje UCProfile dataclass na dict pro JSON serializaci.

        Returns:
            list[dict]: profily všech funkčních UC pluginů.
        """
        profiles = []
        for uc_id, plugin in sorted(self._plugins.items()):
            p = plugin.profile()
            profiles.append({
                "id": p.id,
                "name": p.name,
                "standard_ref": p.standard_ref,
                "description": p.description,
                "communication_pattern": p.communication_pattern,
                "ul_transport": p.ul_transport,
                "dl_transport": p.dl_transport,
                "thresholds": dict(p.thresholds),  # ensure serializable copy
                "default_params": dict(p.default_params),
                "baseline_required": p.baseline_required,
                "min_repetitions": p.min_repetitions,
                "default_duration_s": p.default_duration_s,
            })
        return profiles

    def get_status(self) -> dict:
        """
        Vrátí status plugin loaderu pro /api/v1/system/status.

        Returns:
            dict: {"loaded": [...], "errors": {...}}
        """
        return {
            "loaded": [
                {"uc_id": uid, "name": p.profile().name}
                for uid, p in sorted(self._plugins.items())
            ],
            "errors": dict(self._errors),
        }

    @property
    def available_uc_ids(self) -> list[str]:
        """Seznam dostupných UC ID."""
        return sorted(self._plugins.keys())
