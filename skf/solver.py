"""Gemeinsame Hilfsfunktionen für den CP-SAT-Solver (Google OR-Tools)."""
from __future__ import annotations

from dataclasses import dataclass

from ortools.sat.python import cp_model


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
            for n in list(kern):  # verkleinern: Gruppe weglassen, wenn es ohne sie unlösbar bleibt
                if len(kern) > 1:
                    rest = [k for k in kern if k != n]
                    kleiner = unloesbar(rest, max(1.0, zeitlimit / 10))
                    if kleiner is not None:
                        kern = kleiner
            return kern
        finally:
            self.model.clear_assumptions()
            self._setze((1, 1))


def loese_mit_regeln(model: cp_model.CpModel, regeln: Regeln, schritt: str, zeitlimit: float,
                     threads: int = 8) -> tuple[cp_model.CpSolver, Loesungsinfo]:
    """Wie ``loese``, erklärt aber eine Unlösbarkeit mit den beteiligten Regelgruppen."""
    regeln._setze((1, 1))
    try:
        return loese(model, schritt, zeitlimit, threads)
    except KeineLoesung as fehler:
        if "nachweislich" not in str(fehler):
            raise
        kern = regeln.konflikt(min(30.0, max(5.0, zeitlimit)))
        if not kern:
            raise
        raise KeineLoesung(f"{schritt}: nachweislich keine Lösung möglich. Diese Regeln widersprechen sich: "
                           + "; ".join(kern) + ". Mindestens eine davon lockern.", kern) from None
