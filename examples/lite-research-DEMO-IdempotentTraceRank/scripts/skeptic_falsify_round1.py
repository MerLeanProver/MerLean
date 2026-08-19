import numpy as np
rng = np.random.default_rng(0)

def rank_np(M, tol=1e-9):
    if 0 in M.shape: return 0
    return int((np.linalg.svd(M, compute_uv=False) > tol).sum())

print("=== T1: oblique idempotents, full S3->S15 chain replayed numerically ===")
bad = 0
for trial in range(400):
    n = int(rng.integers(1, 9))
    r = int(rng.integers(0, n+1))
    S = rng.normal(size=(n,n))
    while abs(np.linalg.det(S)) < 1e-6:
        S = rng.normal(size=(n,n))
    D = np.diag([1.0]*r + [0.0]*(n-r))
    A = S @ D @ np.linalg.inv(S)
    assert np.allclose(A@A, A, atol=1e-7), "not idempotent"
    ra = rank_np(A)
    if ra != r: bad += 1; print("  rank mismatch", n, r, ra)
    if abs(np.trace(A) - r) > 1e-7: bad += 1; print("  TRACE FAIL", n, r, np.trace(A))
    sym = np.allclose(A, A.T, atol=1e-8)
    # S3: B = basis of col A via SVD, C = coordinates
    if r == 0:
        continue
    U,s,Vt = np.linalg.svd(A)
    B = U[:, :r]                      # cols form a basis of col A
    C = np.linalg.lstsq(B, A, rcond=None)[0]   # r x n coordinate matrix
    if not np.allclose(B@C, A, atol=1e-7): bad+=1; print("  S3 FAIL A=BC")
    if rank_np(B) != r: bad+=1; print("  S3 FAIL rank B")
    if rank_np(C) != r: bad+=1; print("  S4 FAIL rank C")           # S4
    if not np.allclose(A@B, B, atol=1e-7): bad+=1; print("  S10 FAIL AB=B")   # S9->S10
    if not np.allclose(B@(C@B), B, atol=1e-7): bad+=1; print("  S11 FAIL")
    if not np.allclose(C@B, np.eye(r), atol=1e-7): bad+=1; print("  S12 FAIL CB=I_r", n,r,sym)
    if abs(np.trace(A) - np.trace(C@B)) > 1e-7: bad+=1; print("  S13/S15 FAIL")
print("  failures:", bad)

print("=== T1b: same but with a DELIBERATELY oblique (non-symmetric) A only ===")
cnt=0; bad=0
while cnt < 200:
    n = int(rng.integers(2, 7)); r = int(rng.integers(1, n))
    S = rng.normal(size=(n,n))
    if abs(np.linalg.det(S)) < 1e-6: continue
    A = S @ np.diag([1.0]*r+[0.0]*(n-r)) @ np.linalg.inv(S)
    if np.allclose(A, A.T, atol=1e-6): continue
    cnt+=1
    U,s,Vt = np.linalg.svd(A); B = U[:,:r]; C = np.linalg.lstsq(B, A, rcond=None)[0]
    if not np.allclose(C@B, np.eye(r), atol=1e-7): bad+=1
    if abs(np.trace(A)-r) > 1e-7: bad+=1
print("  oblique samples:", cnt, "failures:", bad)

print("=== T2: S13 double-sum identity on random rectangular pairs (incl. degenerate) ===")
bad=0
for _ in range(500):
    n = int(rng.integers(0, 8)); r = int(rng.integers(0, 8))
    B = rng.normal(size=(n,r)); C = rng.normal(size=(r,n))
    t1 = np.trace(B@C) if n>0 else 0.0
    t2 = np.trace(C@B) if r>0 else 0.0
    if abs(t1-t2) > 1e-8*(1+abs(t1)): bad+=1; print("  S13 FAIL", n, r, t1, t2)
print("  failures:", bad)

print("=== T3: S9 is load-bearing — drop A^2=A, does CB=I_r survive? ===")
viol=0
for _ in range(200):
    n=5; r=3
    A = rng.normal(size=(n,n)) @ np.diag([1,1,1,0,0]) @ rng.normal(size=(n,n))
    rr = rank_np(A)
    U,s,Vt = np.linalg.svd(A); B=U[:,:rr]; C=np.linalg.lstsq(B,A,rcond=None)[0]
    if not np.allclose(C@B, np.eye(rr), atol=1e-6): viol+=1
print("  non-idempotent CB!=I_r in", viol, "/200  (expect ~200 => S9 essential)")

print("=== T4: char p counterexample to the INTEGER reading (S17 trap) ===")
for p in (2,3,5,7):
    # A = I_p over F_p : idempotent, rank p, trace = p mod p = 0
    print(f"  F_{p}: A=I_{p}, A^2=A, rank={p}, tr={p%p} (field elt) -> integer reading fails")

print("=== T5: n=0 edge ===")
A = np.zeros((0,0)); print("  tr:", A.trace(), " rank:", rank_np(A))
