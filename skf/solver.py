# SPDX-License-Identifier: LicenseRef-Proprietary
# Copyright (c) 2026 Outthinkx for Communities. Alle Rechte vorbehalten.
"""Gemeinsame Hilfsfunktionen für den CP-SAT-Solver (Google OR-Tools)."""
from __future__ import annotations

import time
from dataclasses import dataclass

try:
    from ortools.sat.python import cp_model
except ImportError:  # Browser-Version (Pyodide): kein OR-Tools – gerechnet wird auf dem Server (skf.fernrechnen)
    cp_model = None


@dataclass
class Loesungsinfo:
    schritt: str
    status: str
    zielwert: float
    schranke: float
    sekunden: float

    @property
    def optimal(self) -> bool:
        return self.status == "OPTIMAL"

    def __str__(self) -> str:
        luecke = ""
        if self.zielwert and not self.optimal:
            luecke = f", max. {100 * (self.zielwert - self.schranke) / abs(self.zielwert):.1f}% vom Optimum"
        return f"{self.schritt}: {self.status} (Kosten {self.zielwert:.0f}{luecke}, {self.sekunden:.1f}s)"


class KeineLoesung(RuntimeError):
    def __init__(self, text: str, konflikt: list[str] | None = None):
        super().__init__(text)
        self.konflikt = konflikt or []


def loese(model: cp_model.CpModel, schritt: str, zeitlimit: float,
          threads: int = 8) -> tuple[cp_model.CpSolver, Loesungsinfo]:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = zeitlimit
    solver.parameters.num_workers = threads
    status = solver.solve(model)
    name = solver.status_name(status)
    if status == cp_model.INFEASIBLE:
        raise KeineLoesung(f"{schritt}: nachweislich keine Lösung möglich. "
                           "Randbedingungen lockern (Räume, Pensen, Verfügbarkeiten, Klassengrössen).")
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise KeineLoesung(f"{schritt}: innerhalb von {zeitlimit:.0f}s keine Lösung gefunden ({name}) – "
                           "Zeitlimit erhöhen (-t) oder Randbedingungen lockern.")
    info = Loesungsinfo(schritt, name, solver.objective_value, solver.best_objective_bound,
                        solver.wall_time)
    return solver, info


def _lockerbar(name: str) -> int:
    """Wie gut sich eine Regel in der Praxis anpassen lässt (höher = eher anpassbar)."""
    for i, wort in enumerate(("eine Lektion pro Zeitfenster", "keine Lücken", "Blockzeiten", "parallel",
                              "pro Tag", "Mindestgrösse", "Höchstgrösse", "Kapazität", "Anzahl Räume", "IS",
                              "Schulweg", "Geschwister", "Pensum", "Verfügbarkeit")):
        if wort in name:
            return i
    return 5


class Regeln:
    """Benannte Gruppen harter Regeln für die Konfliktanalyse.

    Jede Regelgruppe erhält ein Literal; Nebenbedingungen werden mit ``nur_wenn``
    daran gebunden. Im Normalbetrieb sind alle Literale fest auf 1. Ist das Modell
    unlösbar, wird es mit den Literalen als Annahmen erneut gelöst; CP-SAT liefert
    dann eine Menge von Regelgruppen, die sich widersprechen, die anschliessend
    durch Weglassen einzelner Gruppen verkleinert wird.
    """

    def __init__(self, model: cp_model.CpModel):
        self.model = model
        self.literale: dict[str, cp_model.IntVar] = {}

    def lit(self, name: str) -> cp_model.IntVar:
        if name not in self.literale:
            self.literale[name] = self.model.new_bool_var(f"regel:{name}")
        return self.literale[name]

    def nur_wenn(self, constraint, name: str):
        return constraint.only_enforce_if(self.lit(name))

    def _setze(self, wert: tuple[int, int]) -> None:
        for lit in self.literale.values():
            dom = self.model.proto.variables[lit.index].domain
            dom[0], dom[1] = wert

    def konflikt(self, zeitlimit: float = 20) -> list[str]:
        """Möglichst kleine Menge sich widersprechender Regelgruppen."""
        if not self.literale:
            return []
        self._setze((0, 1))
        namen = list(self.literale)

        def unloesbar(auswahl: list[str], sekunden: float) -> list[str] | None:
            self.model.clear_assumptions()
            self.model.add_assumptions([self.literale[n] for n in auswahl])
            solver = cp_model.CpSolver()
            solver.parameters.max_time_in_seconds = sekunden
            solver.parameters.num_workers = 1
            if solver.solve(self.model) != cp_model.INFEASIBLE:
                return None
            kern = {self.model.proto.variables[i].name.removeprefix("regel:")
                    for i in solver.sufficient_assumptions_for_infeasibility()}
            return [n for n in auswahl if n in kern] or auswahl

        try:
            kern = unloesbar(namen, zeitlimit)
            if kern is None:
                return []
            ende = time.time() + zeitlimit  # Verkleinern mit festem Zeitbudget
            for n in sorted(kern, key=_lockerbar):  # strukturelle Regeln zuerst weglassen
                if len(kern) <= 1 or time.time() > ende:
                    break
                if n in kern:
                    kleiner = unloesbar([k for k in kern if k != n], max(0.5, min(3.0, ende - time.time())))
                    if kleiner is not None:
                        kern = kleiner
            return sorted(kern, key=lambda n: -_lockerbar(n))
        finally:
            self.model.clear_assumptions()
            self._setze((1, 1))


def _zusammenfassen(kern: list[str]) -> str:
    """Grosse Konfliktmengen nach Art der Regel bündeln, anpassbare Regeln zuerst."""
    arten: dict[str, list[str]] = {}
    for n in kern:
        if n.startswith("Verfügbarkeit "):
            arten.setdefault("Verfügbarkeit", []).append(n.removeprefix("Verfügbarkeit "))
        elif n.startswith("Blockzeiten "):
            arten.setdefault("Blockzeiten", []).append(n.removeprefix("Blockzeiten ").split(" am ")[0])
        elif ": " in n:
            arten.setdefault(n.split(": ", 1)[1], []).append(n.split(": ", 1)[0])
        else:
            arten.setdefault(n, [])
    teile = []
    for art, wer in sorted(arten.items(), key=lambda t: -_lockerbar(t[0])):
        wer = list(dict.fromkeys(wer))
        teile.append(f"{art} ({len(wer)}: {', '.join(wer[:6])}{' …' if len(wer) > 6 else ''})" if wer else art)
    return "; ".join(teile)


def loese_mit_regeln(model: cp_model.CpModel, regeln: Regeln, schritt: str, zeitlimit: float,
                     threads: int = 8) -> tuple[cp_model.CpSolver, Loesungsinfo]:
    """Wie ``loese``, erklärt aber eine Unlösbarkeit mit den beteiligten Regelgruppen."""
    regeln._setze((1, 1))
    try:
        return loese(model, schritt, zeitlimit, threads)
    except KeineLoesung as fehler:
        if "nachweislich" not in str(fehler):
            raise
        kern = regeln.konflikt(min(20.0, max(5.0, zeitlimit / 2)))
        if not kern:
            raise
        gezeigt = "; ".join(kern) if len(kern) <= 10 else _zusammenfassen(kern)
        raise KeineLoesung(f"{schritt}: nachweislich keine Lösung möglich. Diese Regeln widersprechen sich "
                           f"(zusammen mit festen Vorgaben wie Räumen und Stundentafel): {gezeigt}. "
                           "Mindestens eine davon lockern.", kern) from None
