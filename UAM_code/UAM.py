import pandas as pd
from collections import defaultdict
from gurobipy import Model, GRB, quicksum

t_tw = 5.0
t_tl = 2.5
u = 30

A = ["taxi", "private_car", "bus", "bike", "walking"]
E = A.copy()

EPS_NET = 0.0
TOPK_PER_P = 30

TIME_LIMIT_SEC = 1800
MIPFOCUS = 2
HEURISTICS = 0.2
CUTS = 3
PRESOLVE = 2
NODEFILE_GB = 1.0
METHOD_ROOT_LP = 1
CONCURRENT_MIP = 1
THREADS = 8


def strip_cols(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = df.columns.str.strip()
    return df


df_P = strip_cols(pd.read_excel(r"OD_flows.xlsx"))
df_P['FID_OD'] = df_P['FID_OD'].astype(int)
P = df_P['FID_OD'].tolist()

origin_by_p = df_P.set_index('FID_OD')['origin'].astype(int).to_dict()
dest_by_p   = df_P.set_index('FID_OD')['destination'].astype(int).to_dict()
gamma_p     = df_P.set_index('FID_OD')['value_time_min'].astype(float).to_dict()
t_p_ground  = df_P.set_index('FID_OD')['travel_time'].astype(float).to_dict()
c_p_ground  = df_P.set_index('FID_OD')['travel_cost'].astype(float).to_dict()
users_p     = df_P.set_index('FID_OD')['user_count'].astype(float).to_dict()

df_M = strip_cols(pd.read_excel(r"candidate_site.xlsx"))
df_M['FID'] = df_M['FID'].astype(int)
M = df_M['FID'].tolist()

df_dist = strip_cols(pd.read_excel(r"between_candidate_sites.xlsx"))
df_dist['FID_O'] = df_dist['FID_O'].astype(int)
df_dist['FID_D'] = df_dist['FID_D'].astype(int)
df_dist = df_dist[df_dist['FID_O'] != df_dist['FID_D']].copy()

c_kd = {(int(r['FID_O']), int(r['FID_D'])): float(r['cost']) for _, r in df_dist.iterrows()}
t_kd = {(int(r['FID_O']), int(r['FID_D'])): float(r['time_min']) for _, r in df_dist.iterrows()}
arcs = list(c_kd.keys())

df_access = strip_cols(pd.read_excel(r"cost_from_origin_to_site.xlsx"))
mode_time_col = {m: f"{m}_time" for m in A}
mode_cost_col = {m: f"{m}_cost" for m in A}

t_ak_p, c_ak_p = {}, {}
for p in P:
    ori = origin_by_p[p]
    sub = df_access[df_access['origin_FID'] == ori]
    if sub.empty:
        continue
    for _, row in sub.iterrows():
        k = int(row['candidate_site_FID'])
        for a in A:
            t_ak_p[(p, a, k)] = float(row[mode_time_col[a]])
            c_ak_p[(p, a, k)] = float(row[mode_cost_col[a]])

df_egress = strip_cols(pd.read_excel(r"cost_from_site_to_destination.xlsx"))
t_ed_p, c_ed_p = {}, {}
for p in P:
    dst = dest_by_p[p]
    sub = df_egress[df_egress['destination_FID'] == dst]
    if sub.empty:
        continue
    for _, row in sub.iterrows():
        d = int(row['candidate_site_FID'])
        for e in E:
            t_ed_p[(p, e, d)] = float(row[mode_time_col[e]])
            c_ed_p[(p, e, d)] = float(row[mode_cost_col[e]])

cand_records = []
for p in P:
    for (k, d) in arcs:
        has_access = any((p, a, k) in t_ak_p for a in A)
        has_egress = any((p, e, d) in t_ed_p for e in E)
        if not (has_access and has_egress):
            continue
        delta = (t_p_ground[p] * gamma_p[p] + c_p_ground[p]) - ((t_kd[(k, d)] + t_tw + t_tl) * gamma_p[p] + c_kd[(k, d)])
        min_acc = min((t_ak_p[(p, a, k)] * gamma_p[p] + c_ak_p[(p, a, k)]) for a in A if (p, a, k) in t_ak_p)
        min_egr = min((t_ed_p[(p, e, d)] * gamma_p[p] + c_ed_p[(p, e, d)]) for e in E if (p, e, d) in t_ed_p)
        net_person = delta - min_acc - min_egr
        if net_person > EPS_NET:
            cand_records.append((p, k, d, net_person, net_person * users_p[p]))

if TOPK_PER_P and TOPK_PER_P > 0:
    by_p = defaultdict(list)
    for p, k, d, nv_person, nv_weighted in cand_records:
        by_p[p].append((nv_weighted, k, d, nv_person))
    candidate_pkd = []
    for p, lst in by_p.items():
        lst.sort(reverse=True)
        for _, k, d, _ in lst[:TOPK_PER_P]:
            candidate_pkd.append((p, k, d))
else:
    candidate_pkd = [(p, k, d) for (p, k, d, _, _) in cand_records]

cand_by_p = defaultdict(list)
out_by_pk = defaultdict(list)
in_by_pk = defaultdict(list)
valid_pk = set()
valid_pd = set()

for (p, k, d) in candidate_pkd:
    cand_by_p[p].append((k, d))
    out_by_pk[(p, k)].append(d)
    in_by_pk[(p, d)].append(k)
    valid_pk.add((p, k))
    valid_pd.add((p, d))

g_keys = [(p, a, k) for (p, a, k) in t_ak_p.keys() if (p, k) in valid_pk]
h_keys = [(p, e, d) for (p, e, d) in t_ed_p.keys() if (p, d) in valid_pd]

model = Model("UAM_P2_weighted")
model.setParam("OutputFlag", 1)
model.setParam("TimeLimit", TIME_LIMIT_SEC)
model.setParam("MIPFocus", MIPFOCUS)
model.setParam("Heuristics", HEURISTICS)
model.setParam("Cuts", CUTS)
model.setParam("Presolve", PRESOLVE)
model.setParam("NodefileStart", NODEFILE_GB)
model.setParam("Method", METHOD_ROOT_LP)
model.setParam("ConcurrentMIP", CONCURRENT_MIP)
model.setParam("Threads", THREADS)

y = model.addVars(M, vtype=GRB.BINARY, name="y")
x = model.addVars(candidate_pkd, vtype=GRB.BINARY, name="x")
g = model.addVars(g_keys, vtype=GRB.BINARY, name="g")
h = model.addVars(h_keys, vtype=GRB.BINARY, name="h")

obj_flight = quicksum(
    users_p[p] * (
        (t_p_ground[p] * gamma_p[p] + c_p_ground[p]) - ((t_kd[(k, d)] + t_tw + t_tl) * gamma_p[p] + c_kd[(k, d)])
    ) * x[p, k, d]
    for (p, k, d) in candidate_pkd
)
obj_access = quicksum(
    users_p[p] * (t_ak_p[(p, a, k)] * gamma_p[p] + c_ak_p[(p, a, k)]) * g[p, a, k]
    for (p, a, k) in g_keys
)
obj_egress = quicksum(
    users_p[p] * (t_ed_p[(p, e, d)] * gamma_p[p] + c_ed_p[(p, e, d)]) * h[p, e, d]
    for (p, e, d) in h_keys
)
model.setObjective(obj_flight - obj_access - obj_egress, GRB.MAXIMIZE)

model.addConstr(quicksum(y[k] for k in M) == u, name="station_count")

for p in P:
    model.addConstr(quicksum(x[p, k, d] for (k, d) in cand_by_p[p]) <= 1, name=f"one_path_{p}")

for p in P:
    for k in M:
        if (p, k) in out_by_pk or (p, k) in in_by_pk:
            lhs = quicksum(x[p, k, d] for d in out_by_pk.get((p, k), [])) + quicksum(x[p, i, k] for i in in_by_pk.get((p, k), []))
            model.addConstr(lhs <= y[k], name=f"link_p{p}_k{k}")

for p in P:
    lhs = quicksum(x[p, k, d] for (k, d) in cand_by_p[p])
    rhs_g = quicksum(g[p, a, k] for (pp, a, k) in g_keys if pp == p)
    rhs_h = quicksum(h[p, e, d] for (pp, e, d) in h_keys if pp == p)
    model.addConstr(lhs == rhs_g, name=f"path_eq_access_{p}")
    model.addConstr(lhs == rhs_h, name=f"path_eq_egress_{p}")

for (p, k, d) in candidate_pkd:
    rhs = quicksum(g[p, a, k] for a in A if (p, a, k) in g_keys) + quicksum(h[p, e, d] for e in E if (p, e, d) in h_keys)
    model.addConstr(2 * x[p, k, d] <= rhs, name=f"continuity_p{p}_k{k}_d{d}")

model.optimize()

status = model.Status
if status not in (GRB.OPTIMAL, GRB.TIME_LIMIT, GRB.INTERRUPTED):
    print(f"\n[Solve finished] Status code: {status}")
    if status == GRB.INFEASIBLE:
        print("Model infeasible: check access/egress coverage, pruning threshold, TOPK, or u.")
    raise SystemExit
if model.SolCount == 0:
    print("\nNo feasible solution found.")
    raise SystemExit

print("\n1) Selected stations")
built = [k for k in M if y[k].X > 0.5]
if built:
    for k in sorted(built):
        print(f"  Station {k}")
else:
    print("  (None)")

print("\n2) UAM trips (access/egress modes + per-trip net savings)")

print("\n2) UAM trips (access/egress modes + time details + per-trip net savings)")
uam_trips = []
seen = set()

rows = []

for (p, k, d) in candidate_pkd:
    if (p, k, d) in seen:
        continue
    if x[p, k, d].X > 0.5:
        seen.add((p, k, d))

        a_star = next((a for a in A if (p, a, k) in g and g[p, a, k].X > 0.5), None)
        e_star = next((e for e in E if (p, e, d) in h and h[p, e, d].X > 0.5), None)

        t_air_only   = t_kd[(k, d)]
        t_air_total  = t_air_only + t_tw + t_tl
        t_access     = t_ak_p[(p, a_star, k)] if a_star is not None else 0.0
        t_egress     = t_ed_p[(p, e_star, d)] if e_star is not None else 0.0
        t_uam_total  = t_access + t_air_total + t_egress

        delta_f = (t_p_ground[p] * gamma_p[p] + c_p_ground[p]) - ((t_air_only + t_tw + t_tl) * gamma_p[p] + c_kd[(k, d)])
        acc_cost = (t_access * gamma_p[p] + c_ak_p[(p, a_star, k)]) if a_star is not None else 0.0
        egr_cost = (t_egress * gamma_p[p] + c_ed_p[(p, e_star, d)]) if e_star is not None else 0.0
        net_per_cap = delta_f - acc_cost - egr_cost
        net_total   = net_per_cap * users_p[p]

        a_txt = a_star if a_star is not None else "None"
        e_txt = e_star if e_star is not None else "None"

        print(
            f"  Trip {p}: {k} → {d} | "
            f"Access={a_txt}({t_access:.1f} min), "
            f"Egress={e_txt}({t_egress:.1f} min), "
            f"Flight={t_air_only:.1f} + {t_tw:.1f} + {t_tl:.1f} = {t_air_total:.1f} min, "
            f"Total UAM time={t_uam_total:.1f} min, "
            f"UAM net savings={net_total:.2f} yuan"
        )

        uam_trips.append((p, k, d))

        rows.append({
            "Trip ID (FID_OD)": p,
            "Origin station k": k,
            "Destination station d": d,
            "Access mode": a_txt,
            "Access time_min": t_access,
            "Egress mode": e_txt,
            "Flight time": t_air_total,
            "Total UAM time": t_uam_total,
            "Number of users": users_p[p],
            "UAM net savings_total yuan": net_total
        })

flight_saving = sum(
    users_p[p] * (
        (t_p_ground[p] * gamma_p[p] + c_p_ground[p]) - ((t_kd[(k, d)] + t_tw + t_tl) * gamma_p[p] + c_kd[(k, d)])
    )
    for (p, k, d) in uam_trips
)
access_cost = sum(
    users_p[p] * (t_ak_p[(p, a, k)] * gamma_p[p] + c_ak_p[(p, a, k)])
    for (p, a, k) in g_keys
    if (p, a, k) in g and g[p, a, k].X > 0.5
)
egress_cost = sum(
    users_p[p] * (t_ed_p[(p, e, d)] * gamma_p[p] + c_ed_p[(p, e, d)])
    for (p, e, d) in h_keys
    if (p, e, d) in h and h[p, e, d].X > 0.5
)
net_saving = flight_saving - access_cost - egress_cost

print("\n3) Cost/benefit breakdown (weighted)")
print(f"   Flight substitution savings (ground - air) : {flight_saving:.2f}")
print(f"   Access connection cost                     : {access_cost:.2f}")
print(f"   Egress connection cost                     : {egress_cost:.2f}")
print(f"   UAM net savings (total)                    : {net_saving:.2f}")

served_trips = len(uam_trips)
total_trips = len(P)
served_users = sum(users_p[p] for (p, _, _) in uam_trips)
total_users = sum(users_p[p] for p in P)

print("\n4) Coverage")
print(f"   Served trips / Total trips : {served_trips} / {total_trips}"
      f"  ({(served_trips / total_trips * 100 if total_trips > 0 else 0):.1f}%)")
print(f"   Served users / Total users : {served_users:.1f} / {total_users:.1f}"
      f"  ({(served_users / total_users * 100 if total_users > 0 else 0):.1f}%)")
