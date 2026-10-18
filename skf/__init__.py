# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Luca De Simoni. Alle Rechte vorbehalten.
"""stunden-klassen-fitter: Klassenbildung und Stundenplan als exakte Optimierung."""
from .daten import lade_kinder, lade_schule
from .klassen import teile_ein
from .lehrauftrag import verteile_lehrauftraege
from .stundenplan import erstelle_stundenplan
from . import verlauf  # noqa: E402

__all__ = ["lade_schule", "lade_kinder", "teile_ein", "verteile_lehrauftraege", "erstelle_stundenplan", "verlauf"]
