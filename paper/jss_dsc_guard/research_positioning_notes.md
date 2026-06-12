# Research Positioning Notes for the JSS Revision

This note records the current positioning decisions for the DSC-Guard revision.
It is intended to guide edits to the Introduction, Scope, Related Work, and Threats to Validity sections.

## 1. JSS vs IST

The current work is a better fit for **Journal of Systems and Software (JSS)** than **Information and Software Technology (IST)**.

JSS is a natural target because the paper is primarily a software-system and tool paper:

- it designs and implements DSC-Guard as a detection/replay system;
- it combines source analysis, log binding, K-style replay, and evidence reports;
- it evaluates the tool on real EVM lending incidents and a benign dataset;
- it reports system-style metrics: recall, precision floor, lead time, actor localization, ablation, and artifact reproducibility.

IST is still possible, but it would require a different framing:

- emphasize how the method improves smart-contract auditing, oracle-integration testing, incident response, or software maintenance practice;
- add stronger practitioner workflow evidence;
- focus less on the detection system itself and more on software-engineering process improvement.

Recommended submission target:

> Submit the current system/evaluation-oriented version to JSS. Treat IST as a backup only if the paper is rewritten around auditing or development practice.

## 2. Scope: Narrow but Defensible

The revised scope is:

> **Price-oracle consumption failures in EVM lending protocols.**

This is narrower than the rejected paper's "general decentralized oracle network attack detection" framing, but it is more defensible.

The old scope invited obvious reviewer objections:

- only one major LUNA incident was evaluated;
- DeFi oracle attacks include DEX price manipulation, flash loans, sandwich attacks, liquidity depletion, MEV, bridge oracles, randomness oracles, and more;
- a generic DON detection claim would require far broader evidence.

The new scope is a software-integration failure class:

```text
asset -> oracle/feed -> normalized price -> collateral value -> borrow/liquidation decision
```

The three sub-classes map to the three main semantics of this pipeline:

| Sub-class | Semantic mismatch | Example cases |
|---|---|---|
| Feed-binding failure | Asset identity mismatch | Ploutos |
| Price-composition / price-semantics failure | Transformation mismatch | Moonwell cbETH, Moonwell wrsETH, Blueberry |
| Freshness-handling failure | Temporal validity mismatch | Venus LUNA, Blizz LUNA |

Recommended phrasing:

> We intentionally study a bounded failure class rather than all oracle attacks. This narrower scope is not a limitation of relevance, but a condition for precise semantic modeling: EVM lending protocols share a common price-consumption pipeline from oracle data to collateral valuation, borrow capacity, and liquidation eligibility.

Avoid phrasing the dataset as "only six cases." Instead:

> The six incidents are empirical instances of a recurring oracle-consumption failure class, and the benign dataset plus broad oracle-scope analysis define the detection boundary.

## 3. Do Not Claim "First Oracle Attack Detector"

DSC-Guard is **not** the first oracle attack detection work and should not be described that way.

Existing related work includes:

- VeriOracle: source-level detection of unexpected price feeds in smart contracts.
- DeFiRanger: transaction-level detection of DeFi price manipulation attacks.
- DeFiScope: LLM-based detection of DeFi price manipulation attacks in standard and custom price models.
- Other price oracle manipulation and DeFi exploit detection work.

Safe novelty claim:

> To our knowledge, DSC-Guard is the first log-semantics replay framework for detecting price-oracle consumption failures in EVM lending protocols.

Alternative:

> DSC-Guard is not another general price-manipulation detector. It targets a complementary consumer-side failure class: lending protocols consume oracle data with incorrect identity, transformation, or freshness semantics.

Avoid:

```text
DSC-Guard is the first system for detecting oracle attacks.
DSC-Guard detects decentralized oracle attacks in general.
DSC-Guard prevents price oracle manipulation attacks.
```

## 4. Difference from Price Oracle Manipulation Research

The paper should clearly separate **price oracle manipulation** from **oracle-consumption failure**.

| Dimension | Price oracle manipulation research | DSC-Guard |
|---|---|---|
| Main problem | Attacker manipulates market price or pricing state | Protocol consumes oracle data incorrectly |
| Typical mechanisms | Flash loans, swaps, liquidity changes, sandwiching, TWAP/spot manipulation | Wrong feed binding, wrong composition formula, stale/lower-bound feed consumption |
| Where the failure occurs | Market side or transaction price model | Consumer protocol's oracle integration |
| Core evidence | Transaction path, token balance changes, DEX/pool state | Oracle/config logs, wrapper semantics, lending supply/borrow/liquidation logs |
| Technical approach | Transaction-level semantic recovery, price deviation, transfer graph, LLM/model reasoning | Source-derived log semantics, evidence closure, K-style replay constraints |
| Typical output | Suspicious price manipulation transactions | Constraint violation, early evidence log, actor candidates, impact transactions |

Recommended wording:

> Existing price-manipulation detectors focus on how attackers distort prices through transactions, token balances, or market mechanisms. DSC-Guard studies a complementary layer: how lending protocols consume oracle information. In our cases, the external oracle may be functioning as designed, but the protocol's integration semantics are wrong.

## 5. Difference from DeFiScope

Relevant paper:

> DeFiScope: Detecting Various DeFi Price Manipulations with LLM Reasoning, arXiv:2502.11521, ASE 2025.

DeFiScope should be treated as a strong related work, not as something to dismiss.
Its scope is broader in DeFi price manipulation:

- it detects DeFi price manipulation attacks in standard and custom price models;
- it uses LLM reasoning to abstract price calculation from source code;
- it uses high-level DeFi operations recovered from low-level transaction data;
- it evaluates on a broad set of real-world attacks and suspicious/benign transactions.

DSC-Guard is different:

- it does not attempt to infer arbitrary market-side price movement;
- it focuses on EVM lending oracle-consumption failures;
- it uses logs and receipts as the replay substrate;
- it checks deterministic oracle-consumption constraints;
- it reports log-level evidence, early boundary evidence, and actor localization.

Recommended Related Work paragraph:

> DeFiScope uses LLM reasoning to infer price models from smart-contract source code and detect DeFi price manipulation attacks from transaction-level token-balance changes. Its scope is broader than ours in market-side price manipulation and custom price models. DSC-Guard is complementary: it does not attempt to infer arbitrary price movement caused by swaps or liquidity changes. Instead, it targets consumer-side oracle-integration failures in EVM lending protocols, where logs expose an oracle boundary, a protocol-side consumption error, and downstream borrow or liquidation impact. This distinction allows DSC-Guard to provide replayable log-level evidence, early oracle-boundary warnings, and actor localization for identity, composition, and freshness violations.

Recommended Introduction sentence:

> Recent work such as DeFiScope shows that LLMs can detect diverse DeFi price manipulations by reasoning about custom price models and token-balance changes. We study a different layer of the problem: not how an attacker manipulates a market price, but how a lending protocol consumes oracle information incorrectly.

## 6. Paper Claim Boundaries

The paper should consistently use conservative claims:

Use:

- price-oracle consumption failures;
- EVM lending protocols;
- consumer-side oracle integration failures;
- log-semantics replay;
- Slither-derived semantic IR plus K-style replay constraints;
- bounded historical read-only detection and evidence reconstruction.

Avoid:

- general DON attack detection;
- first oracle attack detector;
- complete EVM verification;
- universal DeFi oracle attack detection;
- prevention or production monitoring guarantees;
- legal/off-chain attacker attribution.

Recommended one-sentence positioning:

> DSC-Guard is a log-semantics replay tool for a bounded but recurring DeFi software failure class: EVM lending protocols consuming price-oracle data with incorrect identity, transformation, or freshness semantics.

