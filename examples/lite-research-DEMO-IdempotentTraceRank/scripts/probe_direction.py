#!/usr/bin/env python3
"""L0.2 direction probe: for real idempotents A (A^2 = A), does tr(A) = rank(A)?

Genuinely tries to break the claim:
  (a) random orthogonal projections P = Q Q^T,
  (b) random OBLIQUE idempotents P = B (C B)^{-1} C (non-symmetric, can be
      badly conditioned),
  (c) exact planted degenerate cases,
  (d) a counterexample hunt: perturb an idempotent, project back to the
      idempotent manifold via Newton iteration and via eigendecomposition
      with adversarially rounded spectra, then recheck tr vs rank.

Caveat: this probe is over the REALS only. Over F_p the statement fails as
stated (trace is mod p), so all evidence here bears on the R/char-0 claim.
"""

import numpy as np

rng = np.random.default_rng(20260819)

IDEM_TOL = 1e-8      # acceptance threshold for ||P^2 - P||
RESULTS = []          # (kind, n, k, idem_err, trace, rank, dev)


def num_rank(P):
    """SVD-based numerical rank with a standard relative tolerance."""
    s = np.linalg.svd(P, compute_uv=False)
    if s.size == 0:
        return 0
    tol = max(P.shape) * np.finfo(float).eps * s[0]
    # idempotents have singular values >= 1 or ~0; a mild absolute floor
    tol = max(tol, 1e-7)
    return int(np.sum(s > tol))


def record(kind, P, n, k):
    err = np.linalg.norm(P @ P - P)
    if err > IDEM_TOL:
        return False
    t = np.trace(P)
    r = num_rank(P)
    RESULTS.append((kind, n, k, err, t, r, abs(t - r)))
    return True


# ---------------------------------------------------------------- (a)+(b)
def gen_orthogonal(n, k):
    M = rng.standard_normal((n, max(k, 1)))[:, :k] if k > 0 else np.zeros((n, 0))
    if k == 0:
        return np.zeros((n, n))
    Q, _ = np.linalg.qr(M)
    Q = Q[:, :k]
    return Q @ Q.T


def gen_oblique(n, k, cond_cap=1e6):
    """P = B (C B)^{-1} C, retrying while CB is ill-conditioned.
    Occasionally push toward high (but sub-cap) condition number to stress-test."""
    if k == 0:
        return np.zeros((n, n))
    for _ in range(200):
        B = rng.standard_normal((n, k))
        C = rng.standard_normal((k, n))
        # sometimes make C nearly orthogonal to B's range -> highly oblique
        if rng.random() < 0.3:
            C = C + rng.random() * 50.0 * rng.standard_normal((k, n))
        CB = C @ B
        if np.linalg.cond(CB) < cond_cap:
            return B @ np.linalg.solve(CB, C)
    raise RuntimeError("could not generate well-conditioned oblique idempotent")


counts = {"orthogonal": 0, "oblique": 0}
rejected = 0
TARGET_PER_KIND = 100
while counts["orthogonal"] < TARGET_PER_KIND or counts["oblique"] < TARGET_PER_KIND:
    n = int(rng.integers(1, 9))          # n in 1..8
    k = int(rng.integers(0, n + 1))      # rank 0..n inclusive
    if counts["orthogonal"] < TARGET_PER_KIND:
        if record("orthogonal", gen_orthogonal(n, k), n, k):
            counts["orthogonal"] += 1
        else:
            rejected += 1
    if counts["oblique"] < TARGET_PER_KIND:
        if record("oblique", gen_oblique(n, k), n, k):
            counts["oblique"] += 1
        else:
            rejected += 1

# ---------------------------------------------------------------- (c)
degenerate = []
# n = 0: conceptually tr = 0 = rank; numpy handles the empty matrix directly.
P0 = np.zeros((0, 0))
degenerate.append(("n=0 empty", 0.0, 0, True))
for name, A in [
    ("A = 0 (4x4)", np.zeros((4, 4))),
    ("A = I (5x5)", np.eye(5)),
    ("A = [[1,1],[0,0]]", np.array([[1.0, 1.0], [0.0, 0.0]])),
    ("A = [[0,1],[0,1]]", np.array([[0.0, 1.0], [0.0, 1.0]])),
]:
    assert np.allclose(A @ A, A), name + " is not idempotent"
    t, r = np.trace(A), num_rank(A)
    degenerate.append((name, t, r, abs(t - r) < 1e-12))

# ---------------------------------------------------------------- (d)
# Counterexample hunt: perturb idempotents off-manifold, project BACK to the
# idempotent variety two ways, then look for tr != rank.
hunt_results = []

def newton_project(X, iters=60):
    """Newton/heron-style iteration X <- 3X^2 - 2X^3 converges to an idempotent
    (spectral projection of eigenvalues near 1) when X starts near the variety."""
    for _ in range(iters):
        X = 3.0 * (X @ X) - 2.0 * (X @ X @ X)
        if np.linalg.norm(X @ X - X) < 1e-14:
            break
    return X

hunt_count = 0
hunt_max_dev = 0.0
for trial in range(300):
    n = int(rng.integers(2, 9))
    k = int(rng.integers(1, n))
    base = gen_oblique(n, k) if rng.random() < 0.5 else gen_orthogonal(n, k)
    eps = 10.0 ** rng.uniform(-6, -0.8)          # perturbation size up to ~0.16
    X = base + eps * rng.standard_normal((n, n))

    if trial % 2 == 0:
        P = newton_project(X)
        method = "newton"
    else:
        # eigendecomposition route: round eigenvalues ADVERSARIALLY (threshold
        # drawn at random, not at 1/2) then rebuild -- tries to plant weird ranks
        w, V = np.linalg.eig(X)
        thresh = rng.uniform(0.2, 0.8)
        w_r = (w.real > thresh).astype(float)
        try:
            P = (V @ np.diag(w_r) @ np.linalg.inv(V)).real
        except np.linalg.LinAlgError:
            continue
        method = "eig-round"

    if not np.all(np.isfinite(P)):
        continue                                  # Newton diverged
    err = np.linalg.norm(P @ P - P)
    if err > IDEM_TOL:
        continue                                  # projection failed; not an idempotent
    try:
        t, r = np.trace(P), num_rank(P)
    except np.linalg.LinAlgError:
        continue
    dev = abs(t - r)
    hunt_count += 1
    hunt_max_dev = max(hunt_max_dev, dev)
    if dev > 1e-4:
        hunt_results.append((method, n, t, r, dev))

# ---------------------------------------------------------------- summary
print("=" * 72)
print("DIRECTION PROBE: tr(A) = rank(A) for real idempotents A^2 = A")
print("=" * 72)

max_dev = {"orthogonal": 0.0, "oblique": 0.0}
max_err = {"orthogonal": 0.0, "oblique": 0.0}
for kind, n, k, err, t, r, dev in RESULTS:
    max_dev[kind] = max(max_dev[kind], dev)
    max_err[kind] = max(max_err[kind], err)

print(f"\n[1] Random idempotents ({len(RESULTS)} accepted, {rejected} rejected "
      f"for ||P^2-P|| > {IDEM_TOL:g}):")
print(f"{'kind':<12}{'count':>6}{'max ||P^2-P||':>16}{'max |tr-rank|':>16}  status")
overall_ok = True
for kind in ("orthogonal", "oblique"):
    ok = max_dev[kind] < 1e-6
    overall_ok &= ok
    print(f"{kind:<12}{counts[kind]:>6}{max_err[kind]:>16.2e}{max_dev[kind]:>16.2e}"
          f"  {'PASS' if ok else 'FAIL'}")

print("\n[2] Planted degenerate cases (exact):")
for name, t, r, ok in degenerate:
    overall_ok &= ok
    print(f"  {name:<22} trace={t:<6g} rank={r:<3d} {'PASS' if ok else 'FAIL'}")

print(f"\n[3] Counterexample hunt: 300 perturb-and-reproject trials, "
      f"{hunt_count} yielded valid idempotents")
print(f"  methods: Newton iteration (3X^2-2X^3) + eigendecomposition with "
      f"adversarial thresholds in [0.2, 0.8]")
print(f"  max |tr - rank| over hunt: {hunt_max_dev:.2e}")
if hunt_results:
    overall_ok = False
    print("  CANDIDATE COUNTEREXAMPLES:")
    for method, n, t, r, dev in hunt_results:
        print(f"    {method} n={n}: trace={t}, rank={r}, dev={dev:.3e}")
else:
    print("  no candidate counterexamples  PASS")

grand_max = max(max_dev["orthogonal"], max_dev["oblique"], hunt_max_dev,
                max(abs(t - r) for _, t, r, _ in degenerate) if degenerate else 0.0)
print("\n" + "=" * 72)
print(f"MAX |tr - rank| OVER ALL INSTANCES: {grand_max:.3e}")
print(f"VERDICT: {'SUPPORTIVE of tr = rank (over R)' if overall_ok else 'COUNTEREXAMPLE CANDIDATE FOUND'}")
print("CAVEAT: probe is over R only; over F_p the identity holds only mod p "
      "(e.g. I_p over F_p has rank p, trace 0).")
print("=" * 72)
