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
    pass


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
