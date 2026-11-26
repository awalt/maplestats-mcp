### Changed

- The discovery benchmark's committed record (`tests/discovery_benchmark/baseline.json`)
  is re-recorded on the merged code (502 tools): search MRR 0.783, R@1 0.68, R@5 0.92,
  French R@5 0.96; plan R@5 0.88. These figures are in-sample: the tool descriptions
  were reworded by measuring ranks on the same 129 questions, with no held-out set, so
  they likely overstate what new questions would show.
