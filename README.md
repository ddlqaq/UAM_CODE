# UAM Siting & Access/Egress Optimization

This repository contains an integer programming model for **Urban Air Mobility (UAM) vertiport siting with integrated access/egress mode choice**. Using OD trips as demand, the model compares the **generalized travel cost** of ground-only travel vs. UAM (inter-site flight + access/egress). Given a build budget (number of vertiports), it selects a subset of candidate sites and assigns UAM paths to OD flows to **maximize total user net savings** (ground cost − UAM cost).

---

## Key Features

- Reads multi-source inputs (OD table, candidate sites, inter-site flight time/cost, access O→site and egress site→D by mode).
- Builds feasible triplets `(p, k, d)` per OD and prunes by **per-capita net gain** and **user-weighted net gain** (Top-K per OD).
- Mixed-integer formulation:
  - Variables: site build `y_k`, path choice `x_{p,k,d}`, access mode `g_{p,a,k}`, egress mode `h_{p,e,d}`.
  - Objective: maximize user-weighted net savings.
  - Constraints: site count, one path per OD, site–path linkage, access/egress consistency, continuity.
- Outputs: selected vertiports, chosen UAM trips with access/egress modes and time breakdown, cost/benefit decomposition, coverage stats.

---

## Directory Layout
UAM_code/
├─ UAM.py
├─ OD_flows.xlsx
├─ candidate_site.xlsx
├─ between_candidate_sites.xlsx
├─ cost_from_origin_to_site.xlsx
└─ cost_from_site_to_destination.xlsx

---

## Required Inputs (place in the same folder)

| File | Required Columns |
|---|---|
| `OD_flows.xlsx` | `FID_OD, origin, destination, value_time_min, travel_time, travel_cost, user_count` |
| `candidate_site.xlsx` | `FID` |
| `between_candidate_sites.xlsx` | `FID_O, FID_D, time_min, cost` |
| `cost_from_origin_to_site.xlsx` | `origin_FID, candidate_site_FID, {mode}_time, {mode}_cost` |
| `cost_from_site_to_destination.xlsx` | `destination_FID, candidate_site_FID, {mode}_time, {mode}_cost` |

> `{mode} ∈ {taxi, private_car, bus, bike, walking}` (column names must match exactly).

---

## Core Parameters

- `u`: number of vertiports to build (e.g., `u = 30`)
- `A / E`: access/egress mode sets
- `t_tw`, `t_tl`: fixed turnaround / takeoff–landing time (minutes)
- `EPS_NET`, `TOPK_PER_P`: pruning threshold and Top-K per OD
- Gurobi settings: `TimeLimit`, `MIPFocus`, `Heuristics`, `Cuts`, `Presolve`, `Threads`, etc.

---

## Environment & Installation

- Python 3.8+
- Packages: `pandas`, `gurobipy` (Gurobi must be installed and licensed)

```bash
pip install pandas gurobipy


