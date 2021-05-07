# triaging guidlines

I'm about to go through and groom issues and our project board, so I'm going
to dump my thoughts and links here

#### Ensure WG label

All relevant issues should have `wg/k8s-infra` label

- Issues in k8s.io should have wg/k8s-infra label
  - https://github.com/kubernetes/k8s.io/issues?q=is%3Aissue+is%3Aopen+-label%3Awg%2Fk8s-infra
- Lower priority: ensure relevant issues in other repos have wg/k8s-infra label
  - kubernetes/community
  - kubernetes/release
  - kubernetes/sig-release
  - kubernetes/sig-testing
  - kubernetes/test-infra

#### Ensure priority

- priority/critical-urgent: someone should be working on this right now
- priority/important-soon: we're aiming for this release cycle
- priority/important-longterm: this may take multiple release cycles to land
- priority/backlog: nice to have
- priority/awaiting-more-evidence: need proof that this is worth doing

#### Levels of focus

1. on the board, not in to-triage, with a priority, in the current milestone, kubernetes/k8s.io
1. on the board, not in to-triage, with a priority, in the current milestone
1. on the board, not in to-triage, with a priority
1. on the board, not in to-triage
1. on the board, in to-triage
1. not on the board
1. no wg/k8s-infra label


### Reasons to not add to the board

- it's a PR or something else; the board is for issues only
- it doesn't require action on the part of the WG

### Triaging

- ensure wg/k8s-infra label for k8s.io issues
  - https://github.com/kubernetes/k8s.io/issues?q=is%3Aissue+is%3Aopen+-label%3Awg%2Fk8s-infra
- stuff in previous milestone
  - https://github.com/issues?q=is%3Aissue+is%3Aopen+label%3Awg%2Fk8s-infra+milestone%3Av1.21+sort%3Aupdated-desc+
  - if not prioritized, do so
  - add to v1.22 if we might want to do it, e.g.
    - part of umbrella issue to migrate projects involved in kubernetes ci
    - low hanging / not-blocked migration issues
  - if not on board, and wg action is required, add to board
- Stuff in previous milestone
  - Carry forward if still relevant
  - Clear milestone if not
  

Links:
- [Repo: kubernetes/k8s.io][kubernetes/k8s.io]
- [Project Board: wg-k8s-infra][wg-k8s-infra-board]
- current milestone: v1.22

Queries
- [Open Issues in k8s.io][k8sio-issues]
  - Board
    - [(not on board)][issues-off-board]
    - [(on board)][issues-on-board]
  - Milestone
    - [Open Issues (not in v1.22)][issues-not-v1.22]
    - [Open Issues (in v1.22)][issues-in-v1.22]
    - [Open Issues (in v1.21)][issues-in-v1.21]
    - [Open Issues (no milestone)][issues-no-milestone]
  - Labels
    - [Open Issues (not wg/k8s-infra)][issues-no-wg-label]
- [Open Issues with wg/k8s-infra][wg-k8s-infra-issues]
- [Open Issues with wg/k8s-infra][wg-k8s-infra-issues]


[kubernetes/k8s.io]: https://github.com/kubernetes/k8s.io
[wg-k8s-infra-board]: https://github.com/orgs/kubernetes/projects/6

<!-- queries -->
[k8sio-issues-no-wg-label]: https://github.com/issues?q=is%3Aissue+is%3Aopen+repo%3Akubernetes%2Fk8s.io+-label%3Awg%2Fk8s-infra+sort%3Aupdated-desc+

[wg-k8s-infra-issues]: https://github.com/issues?q=is%3Aissue+is%3Aopen+label%3Awg%2Fk8s-infra+sort%3Aupdated-desc+

[issues]: https://github.com/issues?q=repo%3Akubernetes%2Fk8s.io+is%3Aissue+is%3Aopen+sort%3Aupdated-desc
[issues-off-board]: https://github.com/issues?q=repo%3Akubernetes%2Fk8s.io+is%3Aissue+is%3Aopen+sort%3Aupdated-desc+-project%3Akubernetes%2F6
[issues-on-board]: https://github.com/issues?q=repo%3Akubernetes%2Fk8s.io+is%3Aissue+is%3Aopen+sort%3Aupdated-desc+project%3Akubernetes%2F6
[issues-not-v1.22]: https://github.com/issues?q=repo%3Akubernetes%2Fk8s.io+is%3Aissue+is%3Aopen+sort%3Aupdated-desc+-milestone%3Av1.22
[issues-in-v1.22]: https://github.com/issues?q=repo%3Akubernetes%2Fk8s.io+is%3Aissue+is%3Aopen+sort%3Aupdated-desc+milestone%3Av1.22
[issues-in-v1.21]: https://github.com/issues?q=repo%3Akubernetes%2Fk8s.io+is%3Aissue+is%3Aopen+sort%3Aupdated-desc+milestone%3Av1.21
[issues-no-milestone]: https://github.com/issues?q=repo%3Akubernetes%2Fk8s.io+is%3Aissue+is%3Aopen+sort%3Aupdated-desc+milestone%3Anone
