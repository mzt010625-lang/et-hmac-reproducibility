# Ontology-Guided Selective Deliberation for Resource-Efficient Large-Language-Model-Driven Agent-Based Simulation

_Anonymized manuscript. Author information and acknowledgements are provided in a separate title-page file._

## Abstract

Large-language-model-driven agent-based models can represent heterogeneous cognition and policy interpretation, but full semantic deliberation at every simulation step is expensive and can amplify stochastic inconsistency. We present ET-HMAC, an ontology-guided selective-deliberation architecture for household policy simulation. Each household has stable attributes, dynamic state, beliefs, goals, bounded memory, and network evidence. An executable object–relation–event–evidence contract checks legal actions and non-deferrable semantic risks. Hard-risk events bypass the lightweight judgment and verification module (JEV) and enter full semantic deliberation (L2) directly; JEV evaluates only non-hard ambiguous candidates, and valid L2 outputs remain authoritative. We evaluate the frozen architecture on 4,400 development records and a separate 1,020-record holdout containing longitudinal natural snapshots, controlled stress cases, and synthetic policy out-of-distribution (OOD) cases. On the holdout, the hybrid system matched an independently executed full-L2 reference on 97.75% of records (balanced agreement 96.48%; macro-F1 96.70%) while reducing tokens by 68.36% and invoking L2 for 24.80% of opportunities. A blinded review by two domain experts covered 500 frozen cases; the adjudicated expert consensus matched the full-L2 reference in all cases. Natural and stress records reached 100% reference agreement, whereas policy OOD records reached 88.50% agreement and required L2 universally. A four-round replay preserved action sequences for 100 households, but it was not action-conditioned and no observed household choices were available. The results support selective semantic computation while separating model-reference agreement and expert face validity from behavioural validity.

**Keywords:** large language model agent; agent-based modelling; ontology; selective deliberation; semantic routing; policy simulation

## 1. Introduction

Agent-based modelling (ABM) is useful when policy outcomes emerge from heterogeneous actors, interactions, feedback, and adaptation rather than from a representative decision maker. Large language models (LLMs) broaden the behavioural vocabulary of agents by interpreting natural-language policies, conflicting evidence, and socially transmitted information. Generative-agent systems and LLM-based social simulations illustrate this potential [1–4]. Their computational structure, however, creates a scaling problem: if every agent invokes full semantic reasoning in every round and scenario, service demand grows approximately with the product of population size, simulation horizon, experimental repetitions, and scenario count.

Replacing every LLM decision with a fixed rule is not a satisfactory solution. Rules are inexpensive and auditable but become brittle when eligibility, policy validity, household objectives, network messages, and market states interact. Conversely, unconditional LLM use is costly, stochastic, and difficult to audit. Model-routing studies show that queries can be assigned selectively to models of different capability and cost [5–8], while selective prediction formalises the option to abstain or defer uncertain cases [9]. These approaches usually route independent queries. An ABM decision is different: it belongs to a persistent agent, is constrained by legal actions and time-valid evidence, and may modify later state and social context.

The central question is therefore not simply whether an LLM can imitate a household decision. It is how to allocate semantic computation across repeated, stateful opportunities without destroying the behavioural contract of the simulation. Three requirements must be satisfied simultaneously. First, all paths must interpret household attributes, policy evidence, social relations, and event time consistently. Second, expensive deliberation must be concentrated on cases in which it is plausibly useful. Third, a routed L2 response must not be silently overwritten merely because it differs from the fast decision; otherwise the experiment does not measure the contribution of deeper deliberation.

We address this problem through an ontology-guided event-triggered hybrid architecture. The ontology is operational rather than decorative: it defines machine-readable objects, relations, evidence states, action legality, event types, and temporal boundaries. A transparent prior proposes a fast action. Non-deferrable ontology conflicts and policy OOD events enter L2 directly. Only non-hard ambiguous cases are examined by a compact judgment and verification module (JEV), which estimates whether semantic escalation is warranted. If L2 returns a valid and executable response, its action is final.

This study makes four contributions.

1. It specifies a persistent household-agent contract combining stable attributes, dynamic state, beliefs, goals, bounded memory, network information, and explicit transition responsibilities.
2. It introduces a hard-guard-first selective-deliberation policy that avoids spending JEV tokens on cases already known to require L2.
3. It establishes an auditable evaluation protocol that separates full-L2 agreement, observed behaviour, expert judgment, token use, latency, and closed-loop software verification.
4. It reports both positive and negative evidence: strong quality–token trade-offs on natural and stress records, but marked instability and no token benefit under policy OOD.

The paper deliberately uses *agreement* rather than *accuracy* when the reference is another execution of the same model family. This distinction is central to the interpretation of the results.

[[FIGURE:fig01_et_hmac_architecture.png|Figure 1. ET-HMAC architecture. Persistent household cognition and ontology-governed evidence feed CPU routing signals. Low-risk cases use the fast action, non-hard ambiguous cases are verified by JEV, and hard semantic events bypass JEV and enter L2. Fast and L2 outputs pass frozen runtime validation before state transition; a valid L2 decision is final.]]

## 2. Related work

### 2.1 LLM-driven agents and social simulation

Generative Agents showed how memory, reflection, and planning can produce coherent interactive behaviour [1]. Concordia provided a configurable framework for grounding generative agents in social and physical environments [2]. LLMs have also been used to reproduce responses from human studies and to generate synthetic human samples [3,10]. These systems motivate richer behavioural agents, but they also raise questions about reproducibility, construct validity, and the difference between linguistic plausibility and real behaviour.

ABM verification and validation research has long distinguished implementation correctness, structural realism, empirical calibration, and output validation [11–14]. The ODD protocol improves model transparency [11], while simulation-validation work warns that apparently reasonable trajectories may result from artefacts or untested assumptions [12–14]. Accordingly, the present work treats L2 alignment, expert review, and observed behaviour as different evidence layers.

### 2.2 Selective computation and model routing

FrugalGPT combines model cascades to reduce cost [5]. RouteLLM, RouterBench, Hybrid LLM, AutoMix, and MixLLM study learned, benchmarked, or dynamic quality–cost routing among language models [6–8,15,25]. More recent work also treats routing as a safety boundary or decomposes model selection from request routing [26,27]. SelectiveNet addresses prediction with a reject option [9]. These studies establish that expensive computation need not be universal. Our setting does not propose another general-purpose query router. It adds persistent agent state, policy validity, bounded memory, legal action constraints, executable ontology conflicts, and the requirement that valid deep decisions be authoritative across repeated simulation opportunities.

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

restricted by tenure and objective feasibility.

A fast policy returns \(a^f_{i,t}\). A deep policy returns \(a^d_{i,t}\) if invoked. Let \(H_{i,t}\) be a frozen hard-guard event, \(C_{i,t}\) a non-hard coarse candidate, and \(J_{i,t}\) the binary JEV decision. The deployed route is

\[
r_{i,t}=H_{i,t}\lor[(1-H_{i,t})C_{i,t}J_{i,t}].
\]

This ordering is computationally important: hard-guard records bypass JEV. The final action is

\[
a^{final}_{i,t}=\begin{cases}
a^d_{i,t}, & r_{i,t}=1\land V(a^d_{i,t})=1,\\
a^f_{i,t}, & r_{i,t}=0\land V(a^f_{i,t})=1,\\
\pi_{fail}(x_{i,t}), & r_{i,t}=1\land V(a^d_{i,t})=0,
\end{cases}
\]

where \(V\) checks schema, action legality, evidence time, and execution constraints. A disagreement between L2 and the fast path is not an error. Once a valid L2 decision exists, it cannot be replaced by L1 or JEV.

For an operational reference \(Y_i\), the ideal value of escalation under loss \(\ell\) is

\[
g_i=\mathbb E[\ell(a_i^f,Y_i)-\ell(a_i^d,Y_i)\mid z_i],
\]

where \(z_i\) contains only pre-call features. A budgeted router selects positive expected gains subject to

\[
C_{base}+\sum_i r_i\widehat c_i\le B.
\]

The current JEV is a semantic event verifier rather than a learned estimate of \(g_i\); this distinction motivates the calibration analysis and future work.

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

Rules query these fields and generate auditable reason codes. The hard guard is activated by predefined non-deferrable conditions, including unseen policy combinations and strong ontology conflicts. It does not predict the final behaviour; it only determines that the fast path is insufficient.

### 4.3 Transparent fast prior

The fast policy calculates a goal-conditioned expected utility for every legal action. It combines affordability, liquidity, ownership, family stability, residential attachment, improvement demand, and policy opportunity. Illegal actions receive no score. The returned object contains the selected action, score margin, reason codes, and difficult-case flags. This prior is deterministic and auditable.

### 4.4 JEV for non-hard ambiguity

JEV receives the persistent agent state, the transparent prior and its margin, visible event evidence, and ontology features. It returns only an escalation probability, a binary route recommendation, a confidence value, evidence identifiers, and a reason code. It does not replace the household action and is not called when the hard guard already requires L2. This restriction prevents a lightweight model call from becoming an obligatory overhead on every decision.

### 4.5 L2 semantic exception handling

L2 receives the same behavioural contract but a richer evidence representation. The system prompt specifies role, information boundary, stable and dynamic cognition, goals, bounded memory, identity/context and rule/semantic checks, decision order, prior-overriding conditions, state-update responsibilities, and a strict JSON schema. The user prompt contains the household state, rule prior, policy and market evidence, social-network information, ontology relations, and legal actions.

L2 is permitted to retain or override the fast action. Its response is rejected only for schema failure, an illegal action, temporal leakage, or another frozen execution violation. Semantic disagreement never causes fallback to the fast path.

### 4.6 Hardware mapping

Objects, relationships, event extraction, deterministic utility, hard guards, content hashes, and runtime validation execute on CPU. JEV and L2 are accelerator-side semantic services. Stable prompt prefixes and unchanged state fragments are cacheable; only state deltas need to be serialised each round. The design can support dynamic batching, but the present experiment does not claim server-side batching results because the remote service exposes no scheduler telemetry.

## 5. Experimental design

### 5.1 Data and evidence boundary

Household profiles are synthetic population records constrained by official distributions. Latent traits are modelling assumptions. Policy and market packets are time-valid simulation inputs. No previous method action or target action was imported into the input. Consequently, the experiment evaluates architecture-level agreement and robustness, not prediction of observed household choices.

The Stage 9 development experiment contained 4,400 records: 2,000 four-round natural snapshots, 1,400 controlled stress records, and 1,000 synthetic policy-OOD records. After diagnosing the unnecessary JEV overhead on hard-guard events, the execution order was frozen and tested on a new Stage 9D holdout of 1,020 records from 100 previously unexposed households: 400 natural snapshots, 420 stress records across seven conditions, and 200 policy-OOD records across five conditions. Stress and OOD records are paired within households; statistical resampling therefore uses household clusters.

### 5.2 Baselines and reference

The principal operational reference is a fresh full-L2 call for every record. Hybrid-L2 responses were executed separately and were not reused as reference outputs. The full-L2 call uses the same model family and behavioural contract but not the fast action as a target label. This reference measures semantic preservation relative to unconditional deliberation. It is not an expert label or observed behaviour.

We compare the transparent fast prior, hard-guard routing, JEV-assisted routing, the hybrid final decision, and full L2. The Stage 9B analysis also replays fixed and counterfactual routes over frozen potential outcomes; these analyses are labelled exploratory because the original results were already visible.

### 5.3 Metrics

For reference action \(y_i\) and hybrid action \(\hat y_i\), record-level agreement is

\[
A=N^{-1}\sum_i\mathbf 1(\hat y_i=y_i).
\]

Balanced agreement averages class recalls, and macro-F1 averages class-wise F1. Route recall is the fraction of fast/full disagreements sent to L2. Token saving is

\[
S_T=1-\frac{T_{JEV}+T_{selected\ L2}+T_{retry}}{T_{full\ L2}}.
\]

We report L2 invocation rate and P50/P95 receipt latency. Ninety-five-percent intervals use 2,000 household-cluster bootstrap replicates. Internal development targets guided engineering but are not journal acceptance criteria and are not used as inferential hypotheses.

### 5.4 Reproducibility controls

Inputs, prompts, schemas, route equations, thresholds, seeds, manifests, request/response receipts, parsers, and metrics are frozen with SHA-256 hashes. Every semantic call records its provider response, token usage, elapsed time, retry state, and parsed result. API keys are not stored. Target-action keys and future evidence are audited before calls.

### 5.5 Blinded expert review

Two domain experts independently reviewed a frozen 500-case pack comprising 150 natural, 175 stress, and 175 policy-OOD records. The review material contained only pre-decision household state, beliefs, goals, bounded memory, policy, market and network evidence, ontology relations, and legal actions; it did not expose L1, JEV, L2, routing, scores, or target actions. The adjudicated expert consensus action matched the full-L2 reference in 500 of 500 cases. We treat this result as expert face-validity evidence for the operational reference, not as observed household-behaviour accuracy.

## 6. Results

### 6.1 Stage 9 development result and architectural correction

Across 4,400 development records, the original system reached 97.14% overall agreement with full L2 but saved only 46.80% of tokens and routed 34.07% of records to L2. Natural and stress subsets achieved 100% agreement with token savings of 75.16% and 70.56%. Every policy-OOD case activated the hard guard and entered L2, yet JEV was still called first. This produced an unnecessary 1.03 million JEV tokens, and two independent L2 executions agreed on only 87.40% of OOD actions.

A frozen-receipt counterfactual showed that allowing hard guards to bypass JEV would preserve all routes and actions while increasing token saving to 59.38%. This was exploratory. The revised execution order was therefore frozen and evaluated on the independent Stage 9D holdout.

### 6.2 Independent holdout

Table 1 reports Stage 9D results. The hybrid architecture matched the independently executed full-L2 reference on 97.75% of all records. Household-cluster bootstrap intervals were 96.83–98.67% for agreement, 93.49–98.24% for balanced agreement, and 93.90–98.28% for macro-F1. Total token use fell from 2,750,418 to 870,253, a saving of 68.36% (cluster-bootstrap interval 63.19–73.61%).

[[FIGURE:fig02_quality_resource_tradeoff.png|Figure 2. Overall quality–resource trade-off on the independent holdout. Agreement is computed against separately executed full L2; expert consensus is face-validity evidence rather than observed household-choice accuracy.]]

**Table 1. Independent Stage 9D model-reference agreement and resource use.**

| Cohort | N | Agreement | Balanced agreement | Macro-F1 | L2 rate | Token saving | Hybrid/full P95 (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Natural longitudinal snapshots | 400 | 100.00% | 100.00% | 100.00% | 4.75% | 88.82% | 1.92 / 2.10 |
| Controlled stress | 420 | 100.00% | 100.00% | 100.00% | 8.10% | 84.53% | 1.98 / 2.18 |
| Synthetic policy OOD | 200 | 88.50% | 87.17% | 85.47% | 100.00% | −0.02% | 2.28 / 2.35 |
| Overall | 1,020 | 97.75% | 96.48% | 96.70% | 24.80% | 68.36% | 2.16 / 2.20 |

[[FIGURE:fig03_cohort_quality_routing.png|Figure 3. Cohort-level agreement, token saving, and L2 invocation. Natural and stress records retain the full-L2 reference with large savings, whereas policy-OOD cases require universal L2 invocation and provide no token benefit.]]

There were 252 hard-guard records, 160 JEV calls, and 253 L2 calls. Thus only one non-hard record was escalated by JEV beyond the hard-guard set. Route recall for fast/full disagreements was 100%, but route precision was 36.76%, indicating conservative over-routing. No valid selected L2 output was overwritten by the fast path.

### 6.3 OOD failure boundary

All policy-OOD records required L2 under the frozen ontology contract. Because JEV was bypassed, the hybrid and full paths had nearly identical token demand. Nevertheless, their independently sampled L2 outputs disagreed on 11.50% of OOD records. This cannot be repaired by a router: the two endpoints execute the same semantic role, yet stochastic or underdetermined cases produce different actions. Treating one run as ground truth would therefore convert model instability into apparent hybrid error.

The OOD result has two implications. First, the architecture should report a set-valued or distributional decision for genuinely underdetermined policy combinations, or request external adjudication. Second, semantic self-consistency and external behavioural validity must be evaluated separately from token reduction.

### 6.4 Expert face-validity result

The two-expert blinded review produced an adjudicated consensus consistent with the full-L2 action on all 500 frozen cases. This supports using full L2 as an operational semantic reference for the present architecture comparison. It does not establish predictive validity for real households because the review evaluates decision plausibility and evidence consistency rather than observed subsequent choices.

### 6.5 Longitudinal replay and transition audit

For the 100-household, four-round natural holdout, the hybrid and full-L2 action sequences matched exactly for every household. The action-distribution Jensen–Shannon divergence and transition-distribution total-variation distance were both zero. Memory respected the time boundary and remained within the frozen window.

However, later Stage 9D snapshots were not regenerated from the method-specific previous action; the records contained no executed-action outcome memory. We therefore call this a longitudinal replay, not an action-conditioned ABM validation. Separately, ten deterministic four-round software runs verified that action execution changed every household state, wrote action outcomes to bounded memory, updated beliefs and source trust, and advanced the environment. This validates implementation plumbing but not behavioural realism.

### 6.6 Local deployment measurements

On the local test machine, the CPU path comprising the transparent prior, hard guard, and coarse event filter processed approximately 140,974 opportunities per second, with a P95 of a few microseconds per opportunity. A deterministic repeated-replay cache reached 95% hits after its first pass; this is a controlled cache benchmark rather than a production hit rate.

Observed remote receipt latency changed much less than token use. Hybrid P95 was 2.16 s versus 2.20 s for full L2, an improvement of about 2.0%. Network and service variance dominate these single-request measurements. No server-side GPU memory, utilisation, batch queue, or energy data were available.

## 7. Discussion

### 7.1 What creates the resource saving?

The main saving is architectural exclusion, not a cheaper imitation of every L2 call. Most natural and stress opportunities are resolved by the transparent prior. Hard semantic events are detected locally and sent directly to L2. JEV is reserved for a narrow ambiguity band and therefore does not become a universal second model call. This differs from two-LLM cascades that query a lightweight model for every item.

### 7.2 Role of the ontology

The ontology contract creates three operational benefits. It makes legal actions and temporal evidence boundaries explicit; it converts semantic risks into auditable event codes; and it provides a shared state representation for the fast prior, JEV, L2, and the environment. The experiment does not establish general-purpose ontological reasoning. Its claim is narrower: a machine-readable domain contract can organise selective computation and protect simulation semantics.

### 7.3 Why valid L2 must be final

An earlier implementation rejected an L2 action when it differed from L1. That rule makes deeper deliberation incapable of contributing precisely where it matters. The corrected contract rejects L2 only for frozen runtime violations. Stage 9D recorded zero valid-L2 overwrites. This invariant is both an algorithmic requirement and an audit item.

### 7.4 Evidence limitations

The strongest current evidence concerns preservation of a full-L2 operational reference, agreement with the completed expert face-validity review, and service-token reduction. It does not establish that either method predicts real households. The household population is synthetic and distribution-constrained; latent traits and some cognition parameters are assumptions. Expert consensus evaluates plausibility and evidence consistency but cannot substitute for observed household choices. The available four-round replay is not a fully action-conditioned market experiment. Finally, the same model family supplies hybrid L2 and reference L2, so their agreement is not cross-model independence.

These limitations affect journal positioning. The architecture and audit protocol support an expert-system contribution, while the absence of completed external validation weakens broad behavioural claims. A simulation-methods journal would additionally expect formal closed-loop worlds, output calibration against empirical aggregates, and multi-world uncertainty analysis.

## 8. Conclusion

ET-HMAC combines persistent household agents, an executable ontology contract, transparent fast decisions, selective JEV escalation, authoritative L2 deliberation, and auditable state transitions. The hard-guard-first execution order is essential: it avoids paying JEV cost when ontology events already require L2. On an independent 1,020-record holdout, the architecture retained 97.75% agreement with separate full-L2 execution while saving 68.36% of tokens and invoking L2 on 24.80% of opportunities. Natural and stress records achieved complete agreement with large savings; policy-OOD records exposed a qualitatively different regime in which L2 is unavoidable and repeated L2 calls are themselves unstable.

The findings support selective deliberation as a practical resource-control layer for LLM-driven ABM, but they do not convert model agreement or expert face validity into observed behavioural accuracy. The next empirical priority is not further prompt tuning on the current holdout. It is matching aggregate trajectories to observed housing statistics and running action-conditioned multi-world experiments under frozen policies.

## Data and code availability

The project stores frozen configuration, prompts, schemas, token ledgers, latency observations, parsers, metrics, and SHA-256 manifests. A de-identified public reproducibility repository containing the synthetic inputs, parsed decisions, routing ledgers, source code, tests, and expert-review completion summary has been prepared; its final GitHub URL will be inserted after upload. API credentials and private endpoints are excluded. Raw provider requests and responses are retained locally and are not redistributed where service terms or privacy controls do not permit it.

## Declaration of generative AI and AI-assisted technologies in the manuscript preparation process

During the preparation of this work, the author used OpenAI Codex to assist with code review, analysis scripting, manuscript organization, and language editing. After using this tool, the author reviewed and edited the content as needed and takes full responsibility for the content of the publication. DeepSeek was used as an experimental model in the research process; its role, inputs, outputs, and evaluation boundary are described in the Methods.

## Conflict of interest

The author declares no conflict of interest.

## References

[1] J.S. Park, J.C. O'Brien, C.J. Cai, et al., Generative agents: Interactive simulacra of human behavior, in: Proceedings of UIST 2023, ACM, 2023, pp. 1–22. https://doi.org/10.1145/3586183.3606763.

[2] A.S. Vezhnevets, J.P. Agapiou, A. Aharon, et al., Generative agent-based modeling with actions grounded in physical, social, or digital space using Concordia, arXiv:2312.03664, 2023. https://doi.org/10.48550/arXiv.2312.03664.

[3] G.V. Aher, R.I. Arriaga, A.T. Kalai, Using large language models to simulate multiple humans and replicate human subject studies, in: Proceedings of ICML 2023, PMLR 202, 2023, pp. 337–371.

[4] J. Piao, Y. Yan, J. Zhang, et al., AgentSociety: Large-scale simulation of LLM-driven generative agents advances understanding of human behaviors and society, arXiv:2502.08691, 2025. https://doi.org/10.48550/arXiv.2502.08691.

[5] L. Chen, M. Zaharia, J. Zou, FrugalGPT: How to use large language models while reducing cost and improving performance, arXiv:2305.05176, 2023. https://doi.org/10.48550/arXiv.2305.05176.

[6] I. Ong, A. Almahairi, V. Wu, et al., RouteLLM: Learning to route LLMs with preference data, arXiv:2406.18665, 2024. https://doi.org/10.48550/arXiv.2406.18665.

[7] Q.J. Hu, J. Bieker, X. Li, et al., RouterBench: A benchmark for multi-LLM routing system, arXiv:2403.12031, 2024. https://doi.org/10.48550/arXiv.2403.12031.

[8] D. Ding, A. Mallick, C. Wang, et al., Hybrid LLM: Cost-efficient and quality-aware query routing, arXiv:2404.14618, 2024. https://doi.org/10.48550/arXiv.2404.14618.

[9] Y. Geifman, R. El-Yaniv, SelectiveNet: A deep neural network with an integrated reject option, in: Proceedings of ICML 2019, PMLR 97, 2019, pp. 2151–2159.

[10] L.P. Argyle, E.C. Busby, N. Fulda, et al., Out of one, many: Using language models to simulate human samples, Political Analysis 31 (3) (2023) 337–351. https://doi.org/10.1017/pan.2023.2.

[11] V. Grimm, S.F. Railsback, C.E. Vincenot, et al., The ODD protocol for describing agent-based and other simulation models: A second update to improve clarity, replication, and structural realism, Journal of Artificial Societies and Social Simulation 23 (2) (2020). https://doi.org/10.18564/jasss.4259.

[12] P. Windrum, G. Fagiolo, A. Moneta, Empirical validation of agent-based models: Alternatives and prospects, Journal of Artificial Societies and Social Simulation 10 (2) (2007) 8.

[13] J.M. Galán, L.R. Izquierdo, S.S. Izquierdo, et al., Errors and artefacts in agent-based modelling, Journal of Artificial Societies and Social Simulation 12 (1) (2009) 1.

[14] R.G. Sargent, Verification and validation of simulation models, Journal of Simulation 7 (1) (2013) 12–24. https://doi.org/10.1057/jos.2012.20.

[15] P. Aggarwal, A. Madaan, A. Anand, et al., AutoMix: Automatically mixing language models, Advances in Neural Information Processing Systems 37 (2024) 131000–131034.

[16] W.P.M.H. Heemels, K.H. Johansson, P. Tabuada, An introduction to event-triggered and self-triggered control, in: 2012 IEEE 51st Conference on Decision and Control, IEEE, 2012, pp. 3270–3285. https://doi.org/10.1109/CDC.2012.6425820.

[17] P. Tabuada, Event-triggered real-time scheduling of stabilizing control tasks, IEEE Transactions on Automatic Control 52 (9) (2007) 1680–1685. https://doi.org/10.1109/TAC.2007.904277.

[18] M. Miskowicz, Send-on-delta concept: An event-based data reporting strategy, Sensors 6 (1) (2006) 49–63. https://doi.org/10.3390/s6010049.

[19] T.R. Gruber, A translation approach to portable ontology specifications, Knowledge Acquisition 5 (2) (1993) 199–220. https://doi.org/10.1006/knac.1993.1008.

[20] N.F. Noy, D.L. McGuinness, Ontology Development 101: A Guide to Creating Your First Ontology, Stanford Knowledge Systems Laboratory, 2001.

[21] W3C OWL Working Group, OWL 2 Web Ontology Language Document Overview, second ed., W3C Recommendation, 2012. https://www.w3.org/TR/owl2-overview/.

[22] S. Mittal, J.S. Vetter, A survey of CPU–GPU heterogeneous computing techniques, ACM Computing Surveys 47 (4) (2015) 69:1–69:35. https://doi.org/10.1145/2788396.

[23] G.I. Yu, J.S. Jeong, G.W. Kim, et al., Orca: A distributed serving system for Transformer-based generative models, in: 16th USENIX Symposium on Operating Systems Design and Implementation, 2022, pp. 521–538.

[24] W. Kwon, Z. Li, S. Zhuang, et al., Efficient memory management for large language model serving with PagedAttention, in: Proceedings of SOSP 2023, ACM, 2023. https://doi.org/10.1145/3600006.3613165.

[25] X. Wang, S. Song, T. Qi, F. Meng, et al., MixLLM: Dynamic routing in mixed large language models, in: Proceedings of NAACL 2025, Association for Computational Linguistics, 2025, pp. 10912–10922. https://doi.org/10.18653/v1/2025.naacl-long.545.

[26] R. Peng, A. Jimenez, H. Shen, et al., Firewall routing: Toward risk-aware routing for large language models, in: Proceedings of EMNLP 2025, Association for Computational Linguistics, 2025, pp. 6529–6554. https://doi.org/10.18653/v1/2025.emnlp-main.331.

[27] S. Shah, K. Shridhar, Select-then-route: A modular framework for large language model routing, in: Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing: Industry Track, Association for Computational Linguistics, 2025, pp. 425–441. https://doi.org/10.18653/v1/2025.emnlp-industry.28.
