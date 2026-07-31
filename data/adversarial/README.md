# Sealed adversarial set

This directory is **sealed** until final evaluation.

It is built in bucket 11, **before** the three-arm results are known. That
ordering is the blinding claim: the set cannot have been tuned to flatter a
result that did not exist yet when it was written.

Two mechanisms substantiate the claim, and both depend on this directory being
left alone:

1. **Commit dates.** Do not rewrite history that touches this path. The commit
   that seals the set is the evidence.
2. **CI.** `.github/workflows/ci.yml` fails any push that modifies this path,
   except on a branch explicitly named `unseal-final-eval`. `make freeze-check`
   runs the same check locally.

If you need to look at a case in here before final evaluation, the answer is
no — that is the whole point of the directory.
