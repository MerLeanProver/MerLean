"""Kill-test for route A (spectral): rank = geometric mult of 1 = algebraic mult of 1
on random oblique idempotents; control [[1,1],[0,1]] must FAIL alg=geo.
Falsifies route A's step 3/4 (diagonalizability, alg=geo) if any sample breaks."""
import numpy as np

rng = np.random.default_rng(7)
TOL = 1e-6
fails = 0
trials = 0
for _ in range(400):
    n = rng.integers(1, 9)
    r = rng.integers(0, n + 1)
    if r == 0:
        A = np.zeros((n, n))
    elif r == n:
        A = np.eye(n)
    else:
        for _retry in range(50):
            V = rng.standard_normal((n, r))
            W = rng.standard_normal((n, r))
            M = W.T @ V
            if np.linalg.cond(M) < 1e6:
                A = V @ np.linalg.solve(M, W.T)
                break
    if np.linalg.norm(A @ A - A) > 1e-8:
        continue
    trials += 1
    rank = np.linalg.matrix_rank(A, tol=TOL)
    geo = A.shape[0] - np.linalg.matrix_rank(A - np.eye(A.shape[0]), tol=TOL)
    alg = int(np.sum(np.abs(np.linalg.eigvals(A) - 1) < 1e-4))
    resid = np.linalg.norm((A - np.eye(A.shape[0])) @ A)
    if not (rank == geo == alg) or resid > 1e-8:
        fails += 1
        print(f"FAIL n={A.shape[0]} rank={rank} geo={geo} alg={alg} resid={resid:.2e}")

# Control: non-idempotent Jordan block must FAIL alg=geo (proves the test discriminates)
J = np.array([[1.0, 1.0], [0.0, 1.0]])
geoJ = 2 - np.linalg.matrix_rank(J - np.eye(2), tol=TOL)
algJ = int(np.sum(np.abs(np.linalg.eigvals(J) - 1) < 1e-4))
assert algJ > geoJ, "control failed to discriminate"

print(f"route-A kill-test: {trials} valid idempotents, {fails} failures; "
      f"control [[1,1],[0,1]]: alg={algJ} > geo={geoJ} as required")
print("VERDICT:", "SURVIVED" if fails == 0 else "KILLED")
