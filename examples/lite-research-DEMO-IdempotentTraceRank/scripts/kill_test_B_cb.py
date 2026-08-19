import numpy as np
rng = np.random.default_rng(0)

def rank_factor(A, tol=1e-9):
    # B = basis of col(A) via pivoted QR (no eigen/spectral info used)
    Q, R, piv = __import__('scipy.linalg', fromlist=['qr']).qr(A, pivoting=True)
    r = int(np.sum(np.abs(np.diag(R)) > tol*max(1.0, abs(R[0,0]))))
    B = A[:, piv[:r]]                      # r independent columns of A
    C, *_ = np.linalg.lstsq(B, A, rcond=None)  # A = B C  (exact since cols of B span col A)
    return B, C, r

worst_cb = worst_fac = worst_AB = 0.0
worst_tr = 0.0
for trial in range(400):
    n = rng.integers(1, 9)
    r = rng.integers(0, n+1)
    if r == 0:
        A = np.zeros((n, n))
    else:
        while True:
            X = rng.normal(size=(n, r)); Y = rng.normal(size=(r, n))
            M = Y @ X
            if abs(np.linalg.det(M)) > 1e-6: break
        A = X @ np.linalg.inv(M) @ Y      # idempotent by construction, oblique, no diagonalization used
    assert np.max(np.abs(A@A - A)) < 1e-8
    B, C, rr = rank_factor(A)
    worst_fac = max(worst_fac, np.max(np.abs(B@C - A)) if rr>0 else np.max(np.abs(A)))
    if rr > 0:
        worst_cb = max(worst_cb, np.max(np.abs(C@B - np.eye(rr))))   # KEY intermediate claim
        worst_AB = max(worst_AB, np.max(np.abs(A@B - B)))            # A acts as identity on col(A)
    worst_tr = max(worst_tr, abs(np.trace(A) - rr))
print("max |BC-A| =", worst_fac)
print("max |CB-I_r| =", worst_cb)
print("max |AB-B|  =", worst_AB)
print("max |tr-r|  =", worst_tr)
