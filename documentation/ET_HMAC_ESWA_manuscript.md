# Executable Semantic Contracts for Selective LLM Invocation in Agent-Based Simulation

## Abstract

Large-language-model-driven agent-based simulation can represent heterogeneous cognition, but unconditional semantic deliberation increases computational demand and response variability. We present an executable semantic-contract architecture, implemented as ET-HMAC, that allocates semantic computation across repeated household decisions. Persistent agents combine attributes, dynamic state, beliefs, goals, bounded memory, and visible network evidence. A deterministic table supplies a base action; an object–relation–event–evidence contract defines legal actions, temporal visibility, and five semantic exceptions. Hard-risk events enter full semantic deliberation (L2) directly, while a compact judgment/event verifier (JEV) screens the remaining ambiguity band. A valid selected L2 decision is final. Following development on 4,400 records, the frozen architecture was evaluated on an independent 1,020-record holdout containing natural snapshots, controlled stress cases, and synthetic policy out-of-distribution (OOD) cases. Agreement with separately executed full L2 was 97.75% (95% cluster-bootstrap interval: 96.83–98.67%), while token use decreased by 68.36% (63.19–73.61%) and L2 was invoked for 24.80% of opportunities. Natural and stress records achieved complete agreement. Policy-OOD records required universal L2 use, provided no token saving, and yielded 88.50% agreement between independent executions. Of the 23 OOD disagreements, 21 involved asymmetric evidence-reference validation and two involved different valid L2 actions. The results define a resource-saving regime under a shared finite-exception contract and expose its OOD boundary. They evaluate a decision layer for simulation, not prediction of observed household choices or equivalence of closed-loop market trajectories.

**Keywords:** large language model agent; agent-based modelling; ontology; selective deliberation; semantic routing; policy simulation

## 1. Introduction

Agent-based modelling (ABM) is useful when policy outcomes emerge from heterogeneous actors, interactions, feedback, and adaptation rather than from a representative decision maker. Large language models (LLMs) broaden the behavioural vocabulary of agents by interpreting natural-language policies, conflicting evidence, and socially transmitted information. Generative-agent systems and LLM-based social simulations illustrate this potential [1–4]. Their computational structure, however, creates a scaling problem: if every agent invokes full semantic reasoning in every round and scenario, service demand grows approximately with the product of population size, simulation horizon, experimental repetitions, and scenario count.

Replacing every LLM decision with a fixed rule is not a satisfactory solution. Rules are inexpensive and auditable but become brittle when eligibility, policy validity, household objectives, network messages, and market states interact. Conversely, unconditional LLM use is costly, stochastic, and difficult to audit. Model-routing studies show that queries can be assigned selectively to models of different capability and cost [5–8], while selective prediction formalises the option to abstain or defer uncertain cases [9]. These approaches usually route independent queries. An ABM decision is different: it belongs to a persistent agent, is constrained by legal actions and time-valid evidence, and may modify later state and social context.

The central question is therefore not simply whether an LLM can imitate a household decision. It is how to allocate semantic computation across repeated, stateful opportunities without destroying the behavioural contract of the simulation. Three requirements must be satisfied simultaneously. First, all paths must interpret household attributes, policy evidence, social relations, and event time consistently. Second, expensive deliberation must be concentrated on cases in which it is plausibly useful. Third, a routed L2 response must not be silently overwritten merely because it differs from the fast decision; otherwise the experiment does not measure the contribution of deeper deliberation.

We address this problem through an executable semantic-contract architecture, implemented in the ET-HMAC system. The machine-readable contract defines objects, relations, evidence states, action legality, event predicates, and temporal boundaries. A deterministic decision table proposes a fast action. Hard-guard predicates identify zero matching-market inventory, a recent failed action, a compound evidence conflict, or a matching ambiguous policy relation. Such cases enter L2 directly. A compact judgment/event verifier (JEV) screens only the remaining coarse candidates. Both selective and full L2 use the same base action and finite semantic-exception contract; separate responses provide the operational comparison. If a selected L2 response satisfies that contract, its action is final. ET-HMAC is used as a system identifier rather than as a claim that these components constitute a new general-purpose routing algorithm.

This study makes three contributions.

1. It specifies an executable semantic contract for persistent household agents, combining stable attributes, dynamic state, beliefs, goals, bounded memory, network information, legal actions, evidence provenance, and transition responsibilities.
2. It defines a contract-constrained, hard-guard-first execution policy with explicit decision authority and safety invariants: unavoidable exceptions bypass JEV, valid selected L2 outputs are authoritative, and invalid outputs cannot enter the simulation state.
3. It evaluates agreement, risk coverage, token use, and latency jointly on a frozen holdout, and reports both the resource-saving regime and the policy-OOD failure boundary, including a record-level decomposition of all 23 disagreements.

The evaluation addresses three questions: whether guarded selective execution preserves the shared semantic contract, where routing saves resources, and which failure modes persist when every case already receives L2. Model-reference agreement is the relevant outcome because subsequent observed household choices are unavailable.

[[FIGURE:fig01_et_hmac_architecture.png|Figure 1. Executable semantic-contract architecture. (a) Persistent household state and visible evidence share a typed contract. (b) The frozen execution sequence applies the fast prior, routes hard exceptions directly to L2, uses JEV only within the remaining ambiguity band, validates every output, and commits a valid selected L2 action as final before the environment updates state.]]

## 2. Related work

### 2.1 LLM-driven agents and social simulation

Generative Agents showed how memory, reflection, and planning can produce coherent interactive behaviour [1]. Concordia provided a configurable framework for grounding generative agents in social and physical environments [2]. LLMs have also been used to reproduce responses from human studies and to generate synthetic human samples [3,10]. These systems motivate richer behavioural agents, but they also raise questions about reproducibility, construct validity, and the difference between linguistic plausibility and real behaviour.

ABM verification and validation research has long distinguished implementation correctness, structural realism, empirical calibration, and output validation [11–14]. The ODD protocol improves model transparency [11], while simulation-validation work warns that apparently reasonable trajectories may result from artefacts or untested assumptions [12–14]. Accordingly, the present work separates software verification and model-reference agreement from validation against observed behaviour.

### 2.2 Selective computation and model routing

FrugalGPT combines model cascades to reduce cost [5]. RouteLLM, RouterBench, Hybrid LLM, AutoMix, and MixLLM study learned, benchmarked, or dynamic quality–cost routing among language models [6–8,15,25]. Firewall Routing uses blocking to avoid unproductive escalation of difficult queries, while Select-then-Route introduces taxonomy-guided selection and routing [26,27]. SelectiveNet addresses prediction with a reject option [9]. These studies establish that expensive computation need not be universal. Our setting does not propose another general-purpose query router. It adds persistent agent state, policy validity, bounded memory, legal action constraints, executable ontology conflicts, and the requirement that valid deep decisions be authoritative across repeated simulation opportunities.

### 2.3 Event-triggered systems and executable semantics

Event-triggered control executes communication or control only when a state-dependent condition is satisfied [16–18]. We use the event-triggered principle as a computational allocation mechanism rather than as a stability theorem: policy changes, evidence conflicts, legal-action changes, multistep dependencies, and OOD combinations trigger different computational paths.

Ontologies provide explicit concepts, relations, and constraints [19–21]. In the proposed system, the ontology is implemented as a state and evidence contract with queryable event flags and legality checks. This is narrower than a complete OWL knowledge base but stronger than calling a JSON payload an ontology: the contract directly determines routing, validation, and permissible state transitions.

### 2.4 Heterogeneous execution

CPU–accelerator orchestration and memory-aware LLM serving can improve throughput and resource use [22–24]. Our contribution is not a new GPU kernel or serving engine. Instead, we reduce requests reaching the semantic accelerator and retain ontology, rule, event, and guard computation on CPU. Because the external API does not expose server-side accelerator telemetry, we report request tokens, client-side path latency, and local CPU throughput without claiming GPU-energy reductions.

## 3. Problem formulation

For household \(i\) at time \(t\), define

\[
x_{i,t}=(q_i,s_{i,t},b_{i,t},g_i,m_{i,t},n_{i,t},e_t),
\]

where \(q_i\) contains stable attributes, \(s_{i,t}\) dynamic state, \(b_{i,t}\) beliefs, \(g_i\) goals, \(m_{i,t}\) bounded memory, \(n_{i,t}\) visible network information, and \(e_t\) policy and market evidence. The legal action set is

\[
\mathcal A=\{\text{stay},\text{wait},\text{search-buy},\text{search-jeonse},
\text{search-monthly-rent},\text{list-for-sale},\text{list-for-rent}\},
\]

restricted to a household-specific feasible subset by tenure and objective constraints. Jeonse denotes the Korean deposit-based rental arrangement. The decision unit is always a household, including a household that supplies accommodation through a listing action.

A fast policy returns \(a^f_{i,t}\). A deep policy returns \(a^d_{i,t}\) if invoked. Let \(H_{i,t}\) be a frozen hard-guard event, \(C_{i,t}\) a non-hard coarse candidate, and \(J_{i,t}\) the binary JEV decision. The deployed route is

\[
r_{i,t}=H_{i,t}\lor[(1-H_{i,t})C_{i,t}J_{i,t}].
\]

This ordering is computationally important: hard-guard records bypass JEV. The final action is

\[
a^{final}_{i,t}=\begin{cases}
a^d_{i,t}, & r_{i,t}=1\land V(a^d_{i,t})=1,\\
a^f_{i,t}, & r_{i,t}=0\land V(a^f_{i,t})=1,\\
\pi_{fail}(x_{i,t}), & \text{otherwise},
\end{cases}
\]

where \(V\) checks schema, legal actions, directly cited evidence, the applicable policy relation, and the finite-exception conditions. Input assembly enforces the evidence cutoff before the call. An invalid response is handled by the frozen retry or base-action fail-safe and retained in the ledger. A valid semantic exception may change the base action; disagreement alone is never a rejection criterion.

The guard-first order has a direct computational justification. For any fixed JEV outcome, \(H\lor(CJ)=H\lor[(1-H)CJ]\). Bypassing JEV when \(H=1\) therefore leaves the selected route unchanged. Under an identical downstream L2 response and validation rule, it also leaves the final action unchanged. It removes exactly the JEV cost previously paid on those hard-guard cases. This is a pointwise property of the execution graph, not a guarantee that two fresh stochastic L2 calls return the same action.

Let \(q\) be the JEV invocation fraction, \(r\) the L2 fraction, \(\bar c_J\) the mean cost per JEV request, \(\bar c_D\) the mean selected-L2 cost, and \(\bar c_F\) the mean full-reference cost. Ignoring retries for this explanatory decomposition, the token ratio is

\[
\rho_T=\frac{q\bar c_J+r\bar c_D}{\bar c_F}.
\]

The equation shows why a low L2 rate alone is insufficient: frequent verifier calls can consume the avoided deliberation cost. It also predicts the policy-OOD boundary when \(r=1\), \(q=0\), and selected and reference L2 costs are similar.

The implementation follows a fixed seven-step algorithm. First, assemble the time-valid state package and legal-action mask. Second, compute the deterministic base action. Third, evaluate the hard-guard predicates. Fourth, send hard-guard cases directly to L2. Fifth, for a non-hard coarse candidate only, invoke JEV and enter L2 when it recommends escalation; otherwise retain the base action. Sixth, validate the selected action against schema, legality, evidence provenance, policy applicability, and the temporal cutoff. Seventh, commit the valid action and let the environment produce outcomes and the next state. This sequence is deterministic except for JEV and L2 service responses.

Three invariants delimit the guarantee. The legality invariant prevents an action outside the household-specific feasible set from being committed. The temporal invariant prevents evidence that becomes visible after round \(t\) from affecting \(a_{i,t}\). The authority invariant ensures that a valid selected L2 action is not rejected merely because it differs from the base action. Zero false negatives are claimed only for the enumerated hard-exception set under a complete and correct contract. Missing, incorrectly typed, or previously unseen relations fall outside that closed-world guarantee and must be handled as OOD, validation failure, or an explicit schema migration.

## 4. Method

### 4.1 Persistent household agent

Stable attributes include age, household size, income, tenure, dwelling type, lifecycle stage, improvement goal, loss aversion, risk perception, residential attachment, policy-trust tendency, and peer sensitivity. Dynamic state contains liquid assets, liquidity pressure, satisfaction, regret, current tenure, and simulation round.

Beliefs represent subjective price growth, policy eligibility, affordability, policy duration, channel-specific trust, action success probabilities, and uncertainty. Goals distribute importance across housing adequacy, financial security, mobility, family stability, and policy opportunity. Memory stores time-stamped evidence, action outcomes, market observations, and social observations. It is limited to 12 items and ranked by time decay and credibility; full histories are not sent to the model.

The intended transition is

\[
a_{i,t}=\pi(x_{i,t}),\quad o_{i,t}=\mathcal E(a_{i,t},x_t),\quad
x_{i,t+1}=F(x_{i,t},a_{i,t},o_{i,t}).
\]

The environment, rather than the LLM, determines execution success, market feedback, and social observations. The transition function updates assets, tenure, satisfaction, regret, empirical action-success beliefs, channel trust, and bounded memory.

### 4.2 Executable ontology contract

The ontology contract contains four top-level categories.

- **Objects:** households, policies, market segments, evidence sources, and actions.
- **Relations:** eligibility, ownership, source-of, visible-to, connected-to, contradicts, and depends-on.
- **Events:** state change, policy validity change, evidence conflict, legal-action change, multistep dependency, network dependency, and unseen policy combination.
- **Evidence:** source, channel, reliability, visible-from round, expiry round, policy validity state, and provenance.

Rules query these fields and generate auditable reason codes. The hard guard is activated by the predefined exception predicates described below, including matching ambiguous policy relations and compound evidence conflicts. It is not a general-purpose detector of unseen distributions. It does not predict the final behaviour; it determines that the contract requires semantic review.

### 4.3 Transparent fast prior

The evaluated fast policy is an ordered, deterministic decision table. It selects the first feasible action whose condition holds. A sale listing has priority when liquidity pressure is at least 0.68, or when expected price growth is at most −0.04 and the improvement goal is at least 0.35. A rental listing follows when residential attachment is at least 0.45 or the financial-security goal is at least 0.28. A purchase search requires affordability belief of at least 0.72, liquidity pressure of at most 0.45, and risk perception of at most 0.65. Jeonse search requires affordability belief of at least 0.50 and non-negative financial-security plus family-stability goals minus mobility and policy-opportunity goals. Monthly-rental search follows when liquidity pressure is at least 0.55, affordability belief is at most 0.40, or the mobility goal is at least 0.23. If none applies, multistep dependency with a positive conflict count selects waiting when legal; otherwise the policy retains residence when legal and waits as the final feasible alternative.

These thresholds are modelling assumptions frozen before holdout execution. They define the common prior used by both experimental paths. The reported experiment does not fit a utility model or establish that these thresholds describe empirically optimal household behaviour.

### 4.4 JEV for non-hard ambiguity

The coarse screen admits near-zero matching-market inventory, zero inventory in a different market, a single conflict combined with multistep dependency, and near-matching ambiguous policy applicability. JEV receives compact household, state, belief and goal fields, the verified base action, legal actions, the last three relevant memory items, policy applicability relations, ontology counts, and matching visible evidence. It returns an escalation probability, a binary recommendation, confidence, at most three evidence identifiers, and one reason code. The binary recommendation must equal whether the reported probability is at least 0.5. These self-reported probabilities are not treated as calibrated error probabilities.

JEV cannot change the household action. Its output determines only whether a remaining candidate receives L2. Hard-guard cases bypass it, and records outside the coarse candidate set retain the base action. This ordering confines semantic verification cost to an explicit ambiguity band.

### 4.5 L2 semantic exception handling

L2 is a semantic exception reviewer operating on the verified base action and a richer representation of visible evidence. Its system prompt specifies role, information boundary, household cognition, identity/context and rule/semantic checks, decision order, overriding conditions, update responsibilities, and a strict JSON schema. Its user prompt contains three blocks: verified base action, agent state, and event context. The full-reference call uses exactly this contract on every record.

Five exception types can override the prior in a prescribed order: zero inventory in the market corresponding to the selected demand-side search; a recent failed execution of that same action; an evidenced policy block; an evidenced policy enablement; and multistep dependency with at least two missing-evidence, evidence-conflict or rule-conflict flags in total. The first, second and fifth exceptions select waiting when legal. Policy exceptions must cite an operational official source and a matching machine-readable relation specifying the permitted candidate action. A supply-side listing is not blocked merely because demand-side inventory is zero. When no exception holds, L2 must retain the base action.

L2 is permitted to retain or override the fast action. Its response is rejected only for schema failure, an illegal action, temporal leakage, or another frozen execution violation. Semantic disagreement never causes fallback to the fast path.

### 4.6 Hardware mapping

Objects, relationships, event extraction, the decision table, hard guards, content hashes, and runtime validation execute on CPU. JEV and L2 use a remote model service whose accelerator implementation is not exposed. In a local deployment, that interface can map to GPU or NPU inference. Stable prompt prefixes, repeated snapshots and state deltas offer additional caching and serialisation options, but the API experiment sends the frozen request payloads and does not measure delta transmission, dynamic batching or accelerator-memory savings. Measured token avoidance and local CPU throughput are reported separately from these deployment possibilities.

## 5. Experimental design

### 5.1 Data and evidence boundary

Household profiles are synthetic population records constrained by official distributions. Latent traits are modelling assumptions. Policy and market packets are time-valid simulation inputs. No previous method action or target action was imported into the input. Consequently, the experiment evaluates architecture-level agreement and robustness, not prediction of observed household choices.

The development experiment contained 4,400 records: 2,000 four-round natural snapshots, 1,400 controlled stress records, and 1,000 synthetic policy-OOD records. The guard-first execution order was then frozen and tested on an independent holdout of 1,020 records from 100 previously unexposed households: 400 natural snapshots, 420 stress records across seven conditions, and 200 policy-OOD records across five conditions. Natural records retain the synthetic population distribution; stress records alter controlled evidence conditions; policy-OOD records introduce synthetic applicability combinations outside the development setting. Stress and OOD records are paired within households, so statistical resampling uses household clusters. The hard guard reads applicability relations and evidence, not the evaluation cohort label.

### 5.2 Baselines and reference

The principal operational reference is a fresh full-L2 call for every record. Hybrid-L2 responses were executed separately and were not reused as reference outputs. Both receive the same CPU-verified base action and finite-exception contract; response isolation does not imply independent decision rules. This comparison measures preservation of unconditional contract-constrained semantic review. It does not compare against an unconstrained LLM household model or provide labels for observed behaviour.

The analysis separates the transparent prior, hard-guard selection, incremental JEV selection, hybrid final decision, and full-L2 reference. Fixed and counterfactual routes over frozen responses are exploratory because their outcomes were already visible when the route-order comparison was constructed.

All holdout semantic requests used the DeepSeek official API model identifier `deepseek-flash`, temperature 0, and disabled thinking mode. Output ceilings were 4,096 tokens for JEV and 16,384 for L2; actual provider-reported usage determines cost. Requests used JSON-object output, a 300-second timeout and at most three configured transport attempts. The provider does not supply a separately frozen model-weight artifact, so the request identifier, configuration and receipts define the reproducible service specification. Temperature 0 does not guarantee identical responses.

### 5.3 Metrics

For reference action \(y_i\) and hybrid action \(\hat y_i\), record-level agreement is

\[
A=N^{-1}\sum_i\mathbf 1(\hat y_i=y_i).
\]

Balanced agreement averages class recalls, and macro-F1 averages class-wise F1. Route recall is the fraction of fast/full disagreements sent to L2. Token saving is

\[
S_T=1-\frac{T_{JEV}+T_{selected\ L2}+T_{retry}}{T_{full\ L2}}.
\]

The token ledger counts input and output tokens for all paid attempts without double-counting retries. The CPU prior uses no service tokens. We also report L2 invocation rate and the P95 of per-record receipt durations: JEV plus selected-L2 duration for the hybrid, and full-L2 duration for the reference. Records with no semantic call contribute zero to this receipt measure; it excludes local preprocessing and does not represent end-to-end simulation latency. Ninety-five-percent intervals use 2,000 household-cluster bootstrap replicates. Cohort-level results accompany the pooled estimate because overall savings depend on the benchmark mixture.

### 5.4 Reproducibility controls

Inputs, prompts, schemas, route equations, thresholds, seeds, manifests, request/response receipts, parsers, and metrics are frozen with SHA-256 hashes. Every semantic call records its provider response, token usage, elapsed time, retry state, and parsed result. API keys are excluded from experimental artifacts. Target-action keys and future evidence are audited before calls.

## 6. Results

### 6.1 Execution order and verification overhead

Across 4,400 development records, verifier-first execution reached 97.14% overall agreement with full L2, saved 46.80% of tokens, and routed 34.07% of records to L2. Natural and stress subsets achieved 100% agreement with token savings of 75.16% and 70.56%. Every policy-OOD case activated the hard guard and entered L2, but verifier-first execution incurred 1.03 million JEV tokens on those cases. Separate L2 executions agreed on 87.40% of OOD actions.

A frozen-response counterfactual preserved every selected route and downstream action while increasing token saving to 59.38% by bypassing JEV on hard-guard cases. This exploratory result is consistent with the route-equivalence identity in Section 3. The guard-first order was subsequently evaluated on the independent holdout. Its higher pooled saving also reflects a different cohort mixture and cannot be attributed to execution order alone.

### 6.2 Independent holdout

Table 1 reports the independent holdout results. The hybrid architecture matched the separately executed full-L2 reference on 997 of 1,020 records (97.75%). Household-cluster bootstrap intervals were 96.83–98.67% for agreement, 93.49–98.24% for balanced agreement, and 93.90–98.28% for macro-F1. Total token use fell from 2,750,418 to 870,253, a saving of 68.36% (cluster-bootstrap interval 63.19–73.61%). Of the hybrid tokens, 147,061 were consumed by JEV and 723,192 by selected L2. Figure 2 separates this request-cost ledger from the three agreement metrics.

[[FIGURE:fig02_quality_resource_tradeoff.png|Figure 2. Independent holdout resource–quality result. (a) Full-L2 tokens compared with the hybrid token ledger, separated into JEV and selected-L2 components. (b) Agreement, balanced agreement, and macro-F1 against separately executed full L2; error bars show 95% household-cluster bootstrap intervals. These are model-reference metrics, not observed-choice accuracy.]]

**Table 1. Independent holdout model-reference agreement and resource use.**

| Cohort | N | Agreement | Balanced agreement | Macro-F1 | L2 rate | Token saving | Hybrid/full P95 (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Natural longitudinal snapshots | 400 | 100.00% | 100.00% | 100.00% | 4.75% | 88.82% | 1.92 / 2.10 |
| Controlled stress | 420 | 100.00% | 100.00% | 100.00% | 8.10% | 84.53% | 1.98 / 2.18 |
| Synthetic policy OOD | 200 | 88.50% | 87.17% | 85.47% | 100.00% | −0.02% | 2.28 / 2.35 |
| Overall | 1,020 | 97.75% | 96.48% | 96.70% | 24.80% | 68.36% | 2.16 / 2.20 |

[[FIGURE:fig03_cohort_quality_routing.png|Figure 3. Cohort-level operating regimes. Aligned panels report (a) agreement with the separately executed full-L2 reference, (b) token saving with a visible zero line, and (c) L2 invocation rate. Natural and stress records preserve the reference with large savings, whereas policy-OOD cases route universally to L2 and provide no token benefit.]]

There were 252 hard-guard records, 160 JEV calls, and 253 L2 calls. JEV rejected escalation on 159 of its 160 candidates and added one L2 call beyond the hard-guard set. Route recall for the 93 fast/full disagreements was 100%, while route precision was 36.76%. Thus 160 of the 253 selected cases retained the reference base action. This conservative allocation protects recall but limits claims about the verifier's incremental benefit. No valid selected L2 output was overwritten by the fast path. Figure 3 shows that these aggregate results combine sharply different cohort regimes.

### 6.3 OOD failure boundary

All policy-OOD records required L2 under the frozen semantic contract. Because JEV was bypassed, the hybrid and full paths had nearly identical token demand. Their independently executed paths disagreed on 23 of 200 OOD records (11.50%). Record-level inspection showed that 21 disagreements arose when one L2 response passed evidence-reference validation while the other cited identifiers outside the frozen whitelist and therefore fell back to the deterministic base action. The remaining two disagreements occurred between two valid L2 outputs. The most frequent action transitions were wait versus list-for-rent (four records), search-buy versus wait (two), search-monthly-rent versus stay (two), list-for-rent versus search-monthly-rent (two), search-jeonse versus search-buy (two), and wait versus stay (two); the other nine transition pairs occurred once each.

This decomposition localises the dominant OOD failure to evidence-grounding stability at the contract boundary rather than to routing: every affected record had already reached L2. Changing the allocation decision cannot resolve it. A single execution therefore supplies an operational reference rather than an error-free behavioural label.

The OOD result has two implications. First, the architecture should strengthen identifier canonicalisation and report a set-valued or distributional decision for genuinely underdetermined policy combinations. Second, reference self-consistency and external behavioural validity must be evaluated separately from token reduction.

### 6.4 Longitudinal replay and transition audit

For the 100-household, four-round natural holdout, the hybrid and full-L2 action sequences matched exactly for every household. The action-distribution Jensen–Shannon divergence and transition-distribution total-variation distance were both zero. Memory respected the time boundary and remained within the frozen window.

Later holdout snapshots were fixed independently of each method's preceding action and contained no executed-action outcome memory. The result therefore establishes longitudinal replay agreement, with no claim of equivalence between action-conditioned market trajectories. Separately, ten deterministic four-round software runs verified that action execution changed household state, wrote outcomes to bounded memory, updated beliefs and source trust, and advanced the environment. Those runs verify the transition implementation; they do not estimate behavioural validity.

### 6.5 Local deployment measurements

On the local test machine, the CPU path comprising the transparent prior, hard guard, and coarse event filter processed approximately 140,974 opportunities per second, with a P95 of a few microseconds per opportunity. A deterministic repeated-replay cache reached 95% hits after its first pass; this is a controlled cache benchmark rather than a production hit rate.

Observed remote receipt latency changed much less than token use. Hybrid P95 was 2.16 s versus 2.20 s for full L2, an improvement of about 2.0%. Network and service variance dominate these single-request measurements. No server-side GPU memory, utilisation, batch queue, or energy data were available.

## 7. Discussion

### 7.1 What creates the resource saving?

The dominant saving comes from resolving routine opportunities through the deterministic prior and admitting only evidence-linked exceptions to semantic processing. Hard events enter L2 directly, and JEV is restricted to an ambiguity band. On the holdout, 75.20% of opportunities avoided L2 and 84.31% avoided JEV. The resource ratio in Section 3 makes the residual verifier overhead explicit.

This experiment offers limited evidence that JEV itself is necessary. Its conditions overlap substantially with the executable hard guard, and only one additional record reached L2 through JEV. The measured advantage therefore belongs to the complete selective architecture under the finite-exception contract. Establishing a distinct JEV benefit would require a held-out set of ambiguities not already decidable from hard predicates, paired with a guard-only comparison at equal resource cost. The present results do not establish that marginal advantage.

### 7.2 Role of the ontology

The ontology contract creates three operational benefits. It makes legal actions and temporal evidence boundaries explicit; it converts semantic risks into auditable event codes; and it provides a shared state representation for the fast prior, JEV, L2, and the environment. The experiment does not establish general-purpose ontological reasoning. Its claim is narrower: a machine-readable domain contract can organise selective computation and protect simulation semantics.

### 7.3 Decision authority under a shared contract

Semantic escalation is useful only if a supported exception can alter the proposed action. ET-HMAC separates validity from agreement: an L2 action is accepted when it meets the frozen action, evidence and policy-applicability constraints, even when it differs from the prior. The holdout recorded zero valid-L2 overwrites. This invariant establishes decision authority within the shared contract, while the contract itself restricts the range of behaviours available to both reference and hybrid systems. High agreement under that shared structure should not be extrapolated to unrestricted generative agents.

### 7.4 Evidence limitations

The strongest current evidence concerns preservation of a full-L2 operational reference, complete recall of fast/full disagreements by the selected L2 set, and service-token reduction. It does not establish that either method predicts real households. The household population is synthetic and distribution-constrained; latent traits and some cognition parameters are assumptions. No observed household-choice labels are available. The available four-round replay is not a fully action-conditioned market experiment. Finally, the same model family supplies hybrid L2 and reference L2, so their agreement is not cross-model independence.

The scope of transfer is consequently limited. Distribution shifts in household traits, different policy ontologies, alternative providers, and open-ended actions may alter both coverage and cost. The controlled stress conditions test specified predicates rather than the complete range of social complexity. Fully action-conditioned multi-world experiments and calibration against observed aggregate housing outcomes are needed to assess how local decision differences propagate through a market.

## 8. Conclusion

ET-HMAC combines persistent household agents, an executable semantic contract, transparent fast decisions, selective JEV escalation, authoritative L2 deliberation, and auditable state transitions. The hard-guard-first execution order avoids paying JEV cost when contract events already require L2. On an independent 1,020-record holdout, the architecture retained 97.75% agreement with separate full-L2 execution while saving 68.36% of tokens and invoking L2 on 24.80% of opportunities. Natural and stress records achieved complete agreement with large savings. Policy-OOD records exposed a qualitatively different regime in which L2 is unavoidable, evidence-reference validation is the dominant disagreement source, and no token saving is available.

The findings support selective deliberation as a resource-control layer for contract-constrained LLM-driven ABM. The main contribution is an auditable allocation of rule execution, event verification and semantic exception handling, together with an explicit account of the conditions under which savings disappear. External behavioural validation, action-conditioned trajectory experiments and equal-cost verifier ablations remain necessary for broader claims.

## Data and code availability

The project stores frozen configuration, prompts, schemas, token ledgers, latency observations, parsers, metrics, and SHA-256 manifests. A de-identified public reproducibility repository containing the synthetic inputs, parsed decisions, routing ledgers, source code, tests, and editable figures is available at https://github.com/mzt010625-lang/et-hmac-reproducibility. API credentials and private endpoints are excluded. Raw provider requests and responses are retained locally and are not redistributed where service terms or privacy controls do not permit it.

## Declaration of generative AI and AI-assisted technologies in the manuscript preparation process

During the preparation of this work, the author used OpenAI Codex to assist with code review, analysis scripting, manuscript organization, and language editing. After using this tool, the author reviewed and edited the content as needed and takes full responsibility for the content of the publication. DeepSeek was used as an experimental model in the research process; its role, inputs, outputs, and evaluation boundary are described in the Methods.

## Conflict of interest

The author declares no conflict of interest.

## References

[1] Park, J. S., O'Brien, J., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023). Generative agents: Interactive simulacra of human behavior. In *Proceedings of the 36th Annual ACM Symposium on User Interface Software and Technology* (pp. 1–22). https://doi.org/10.1145/3586183.3606763

[2] Vezhnevets, A. S., Agapiou, J. P., Aharon, A., Ziv, R., Matyas, J., Duéñez-Guzmán, E. A., Cunningham, W. A., Osindero, S., Karmon, D., & Leibo, J. Z. (2023). *Generative agent-based modeling with actions grounded in physical, social, or digital space using Concordia*. arXiv. https://doi.org/10.48550/arXiv.2312.03664

[3] Aher, G. V., Arriaga, R. I., & Kalai, A. T. (2023). Using large language models to simulate multiple humans and replicate human subject studies. In *Proceedings of the 40th International Conference on Machine Learning* (Vol. 202) (pp. 337–371). https://proceedings.mlr.press/v202/aher23a.html

[4] Piao, J., Yan, Y., Zhang, J., Li, N., Yan, J., Lan, X., Lu, Z., Zheng, Z., Wang, J. Y., Zhou, D., Gao, C., Xu, F., Zhang, F., Rong, K., Su, J., & Li, Y. (2025). *AgentSociety: Large-scale simulation of LLM-driven generative agents advances understanding of human behaviors and society*. arXiv. https://doi.org/10.48550/arXiv.2502.08691

[5] Chen, L., Zaharia, M., & Zou, J. (2023). *FrugalGPT: How to use large language models while reducing cost and improving performance*. arXiv. https://doi.org/10.48550/arXiv.2305.05176

[6] Ong, I., Almahairi, A., Wu, V., Chiang, W.-L., Wu, T., Gonzalez, J. E., Kadous, M. W., & Stoica, I. (2024). *RouteLLM: Learning to route LLMs with preference data*. arXiv. https://doi.org/10.48550/arXiv.2406.18665

[7] Hu, Q. J., Bieker, J., Li, X., Jiang, N., Keigwin, B., Ranganath, G., Keutzer, K., & Upadhyay, S. K. (2024). *RouterBench: A benchmark for multi-LLM routing system*. arXiv. https://doi.org/10.48550/arXiv.2403.12031

[8] Ding, D., Mallick, A., Wang, C., Sim, R., Mukherjee, S., Ruhle, V., Lakshmanan, L. V. S., & Awadallah, A. H. (2024). *Hybrid LLM: Cost-efficient and quality-aware query routing*. arXiv. https://doi.org/10.48550/arXiv.2404.14618

[9] Geifman, Y., & El-Yaniv, R. (2019). SelectiveNet: A deep neural network with an integrated reject option. In *Proceedings of the 36th International Conference on Machine Learning* (Vol. 97) (pp. 2151–2159). https://proceedings.mlr.press/v97/geifman19a.html

[10] Argyle, L. P., Busby, E. C., Fulda, N., Gubler, J. R., Rytting, C., & Wingate, D. (2023). Out of one, many: Using language models to simulate human samples. *Political Analysis*, *31*(3), 337–351. https://doi.org/10.1017/pan.2023.2

[11] Grimm, V., Railsback, S. F., Vincenot, C. E., Berger, U., Gallagher, C., DeAngelis, D. L., Edmonds, B., Ge, J., Giske, J., Groeneveld, J., Johnston, A. S. A., Milles, A., Nabe-Nielsen, J., Polhill, J. G., Radchuk, V., Rohwäder, M.-S., Stillman, R. A., Thiele, J. C., & Ayllón, D. (2020). The ODD protocol for describing agent-based and other simulation models: A second update to improve clarity, replication, and structural realism. *Journal of Artificial Societies and Social Simulation*, *23*(2), Article 7. https://doi.org/10.18564/jasss.4259

[12] Windrum, P., Fagiolo, G., & Moneta, A. (2007). Empirical validation of agent-based models: Alternatives and prospects. *Journal of Artificial Societies and Social Simulation*, *10*(2), Article 8. https://www.jasss.org/10/2/8.html

[13] Galán, J. M., Izquierdo, L. R., Izquierdo, S. S., Santos, J. I., del Olmo, R., López-Paredes, A., & Edmonds, B. (2009). Errors and artefacts in agent-based modelling. *Journal of Artificial Societies and Social Simulation*, *12*(1), Article 1. https://www.jasss.org/12/1/1.html

[14] Sargent, R. G. (2013). Verification and validation of simulation models. *Journal of Simulation*, *7*(1), 12–24. https://doi.org/10.1057/jos.2012.20

[15] Aggarwal, P., Madaan, A., Anand, A., Potharaju, S. P., Mishra, S., Zhou, P., Gupta, A., Rajagopal, D., Kappaganthu, K., Yang, Y., Upadhyay, S., Faruqui, M., & Mausam (2024). AutoMix: Automatically mixing language models. In *Advances in Neural Information Processing Systems* (Vol. 37). https://proceedings.neurips.cc/paper_files/paper/2024/hash/ecda225cb187b40ea8edc1f46b03ffda-Abstract-Conference.html

[16] Heemels, W. P. M. H., Johansson, K. H., & Tabuada, P. (2012). An introduction to event-triggered and self-triggered control. In *2012 IEEE 51st IEEE Conference on Decision and Control (CDC)* (pp. 3270–3285). https://doi.org/10.1109/CDC.2012.6425820

[17] Tabuada, P. (2007). Event-triggered real-time scheduling of stabilizing control tasks. *IEEE Transactions on Automatic Control*, *52*(9), 1680–1685. https://doi.org/10.1109/TAC.2007.904277

[18] Miskowicz, M. (2006). Send-on-delta concept: An event-based data reporting strategy. *Sensors*, *6*(1), 49–63. https://doi.org/10.3390/s6010049

[19] Gruber, T. R. (1993). A translation approach to portable ontology specifications. *Knowledge Acquisition*, *5*(2), 199–220. https://doi.org/10.1006/knac.1993.1008

[20] Noy, N. F., & McGuinness, D. L. (2001). *Ontology development 101: A guide to creating your first ontology*. Stanford Knowledge Systems Laboratory. https://protege.stanford.edu/publications/ontology_development/ontology101-noy-mcguinness.html

[21] W3C OWL Working Group (2012). *OWL 2 web ontology language document overview (2nd ed.)*. World Wide Web Consortium. https://www.w3.org/TR/owl2-overview/

[22] Mittal, S., & Vetter, J. S. (2015). A survey of CPU–GPU heterogeneous computing techniques. *ACM Computing Surveys*, *47*(4), 1–35. https://doi.org/10.1145/2788396

[23] Yu, G.-I., Jeong, J. S., Kim, G.-W., Kim, S., & Chun, B.-G. (2022). Orca: A distributed serving system for Transformer-based generative models. In *16th USENIX Symposium on Operating Systems Design and Implementation* (pp. 521–538). https://www.usenix.org/conference/osdi22/presentation/yu

[24] Kwon, W., Li, Z., Zhuang, S., Sheng, Y., Zheng, L., Yu, C. H., Gonzalez, J., Zhang, H., & Stoica, I. (2023). Efficient memory management for large language model serving with PagedAttention. In *Proceedings of the 29th Symposium on Operating Systems Principles* (pp. 611–626). https://doi.org/10.1145/3600006.3613165

[25] Wang, X., Liu, Y., Cheng, W., Zhao, X., Chen, Z., Yu, W., Fu, Y., & Chen, H. (2025). MixLLM: Dynamic routing in mixed large language models. In *Proceedings of the 2025 Conference of the Nations of the Americas Chapter of the Association for Computational Linguistics: Human Language Technologies (Volume 1: Long Papers)* (pp. 10912–10922). https://doi.org/10.18653/v1/2025.naacl-long.545

[26] Peng, R., Zhou, Y., Lv, K., Gao, Y., Guo, Q., & Qiu, X. (2025). Firewall Routing: Blocking leads to better hybrid inference for LLMs. In *Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing* (pp. 6529–6554). https://doi.org/10.18653/v1/2025.emnlp-main.331

[27] Shah, S., & Shridhar, K. (2025). Select-then-Route: Taxonomy guided routing for LLMs. In *Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing: Industry Track* (pp. 425–441). https://doi.org/10.18653/v1/2025.emnlp-industry.28
