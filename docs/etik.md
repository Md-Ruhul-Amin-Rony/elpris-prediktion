# Ethics exercise, Tuesday 15/9, about 11:30–12:00

Copied from `uppgifter/Tisdag_15_9_etik_arbetsblad.md` in the course repo on 15/9 and translated to English. Facts about sources, licences, personal data and the database are in `docs/governance.md`; we link there instead of repeating them.

Fill this in as a group. It prepares the ethics part of Thursday's group presentation.

When formulating an ethical question or problem, it helps to think about three things:

- Is a **person** affected?
- What is the **consequence**?
- What is the **mechanism**, that is, what causes the person to be affected?

---

## Question 1 — What data do you have today, will new data be added, and does the data concern specific persons?

Start with the system you have today:

- [x] Training data: what is in it, and is any of it about specific persons?
- [x] Database: what is stored in Neon, who is responsible for it, and when will it be deleted after the course?
- [x] Your own repo and secrets: is anything personal committed anywhere?
- [x] Future API: when you publish the prediction service, what will you log about each request? Who needs access to that information and how long will it be kept?

### Answer

#### Training data

The model is trained on `feat__daily`: one row per day for price area SE3 with the day-ahead mean price and daily temperature and wind at SMHI station 97400 Stockholm-Bromma. The two sources are SMHI weather observations and elprisetjustnu.se prices. Neither describes a person: the observations describe the air at one public station, and the prices are market prices for a whole bidding zone. See `docs/governance.md`, section "Personal data".

#### Database

Neon Postgres, one project owned by David and shared with the team. Tables: `raw__elpris`, `raw__weather`, `silver__elpris`, `silver__weather`, `feat__daily`. Raw payloads are stored unchanged; the silver and feature tables are derived from them. David is responsible for the project as its owner. Our proposal is that he deletes it when the course ends; nothing in it exists only there, both sources can be fetched again. The final decision is taken in Sprint 3, see Decision 9 #71 and `docs/governance.md`, section "After the course".

#### Repository and secrets

Nothing personal is committed. The only personal data around the project are our GitHub accounts in the commit history, the normal public record of a repository. `DATABASE_URL` and `HF_TOKEN` are secrets, not personal data; they live in `.env` files that are ignored by git and in GitHub Actions secrets. The repository is private. The two csv.gz snapshots in `data/` are public-source data, see question 2.

#### Future API

We have no public API yet. When we publish one, the request logs are the first place personal data can appear: an IP address with a timestamp is personal data under GDPR. The team decided the following on 15/9, following lecture 10.1:

| Point | Decision |
|---|---|
| Purpose | Debugging and monitoring of the service, nothing else |
| What we log per call | Timestamp, endpoint, status code, response time, model version. No IP address, or only that a request was made |
| Who needs access | The team members who operate the service |
| Retention | 30 days, then deleted automatically |
| Responsibility | The person who deploys the service names themself as responsible in `docs/governance.md` |

#### Which rules apply

GDPR applies only if a future service or its logs process personal data; the training data does not. The EU AI Act works with risk levels: an electricity-price forecast that gives information and takes no decision about a person is not a high-risk system. Transparency: we tell users that the number is a model prediction and show the error next to it, as the model card already does.

---

## Question 2 — What are you allowed to do with the data you have fetched?

For the standard project you use the sources below (the other projects have their own):

> - **[SMHI Open Data](https://www.smhi.se/data/om-smhis-data/villkor-for-anvandning):** CC BY 4.0. Name SMHI as the source and describe your processing of the data.
> - **[elprisetjustnu.se](https://www.elprisetjustnu.se/elpris-api)**: the API is described as open and free without a formal licence. Briefly document what the page says now and when you read it.

For each data source, write down:

- Source
- Licence
- Do you need to credit the source?
- May you republish raw data?
- Where and when you read the terms

Does your current solution comply with the terms?

Also check what applies to any terms or limits on API use. When you call APIs you use someone else's infrastructure, and sometimes they have rules about that.

### Answer

Details and links are in `docs/governance.md`, section "Sources and terms". Both terms pages were read on 15 September 2026.

| | SMHI, weather observations | elprisetjustnu.se, day-ahead prices |
|---|---|---|
| Source | SMHI metobs API, station 97400 Stockholm-Bromma, temperature and wind | elprisetjustnu.se API, prices from ENTSO-E in EUR converted to SEK |
| Licence | CC BY 4.0 | No formal licence. The page says the API is open and free, for anyone, for anything |
| Must we credit the source? | Yes, and say if the data was changed | Requested when the data is used publicly. We credit the site in `docs/governance.md` and in the model card |
| May we republish raw data? | Yes. The page allows copying, distribution and adaptations, also commercially, with attribution | Not addressed on the page |
| Where and when we read the terms | smhi.se, terms page, 15 September 2026 | elprisetjustnu.se/elpris-api, 15 September 2026 |
| API limits | Only documented APIs, no mass downloads, use caching, shared bandwidth | None stated |
| What we do | One call per parameter per run, once a day; the history was fetched once per station, parameter and period | One call per day and price area |

Does our current solution comply? Yes. We use documented APIs, call each source once a day, name both sources, and say which values are our own: daily means, minima and maxima. We keep two snapshots of raw data in the repository, `data/historik_vader.csv.gz` and `data/historik_elpris.csv.gz`. SMHI allows that with attribution. For elprisetjustnu.se the page says nothing about republishing; the repository is private today, so the snapshot is not published. If the repository becomes public we ask the site or remove the price snapshot.

---

## Question 3 — Who is affected by your predictions?

Describe a specific person and how they can be affected.

- Who gains from a correct forecast? What can they do that others cannot?
- Who cannot act on the prediction at all, and why?
- Is an error of, say, 30% an equally large problem for both groups?
- Will your system put more or less responsibility on specific groups?
- How much responsibility do you have to tell about the model's limitations? Is it ethical to ask people to use a model with a negative R² value?

### Answer

Our electricity price predictions could affect different groups in different ways.

#### Who can benefit?

Households with flexible electricity consumption can benefit from an accurate prediction. For example, they can change when they use the washing machine, dryer or dishwasher, or when they charge an electric vehicle. If the prediction is correct, they may be able to move some of their consumption to cheaper periods and save money.

Electric vehicle owners and small businesses could also use the prediction to plan when they consume electricity.

#### Who may benefit less?

People with lower incomes may have fewer possibilities to act on the prediction. They may not have an electric car, home battery or smart devices that allow them to move their electricity consumption to cheaper periods.

Some people also cannot easily change when they use electricity because of their work, family situation or other needs. This means that the same prediction does not necessarily benefit everyone equally.

#### What happens if the prediction is wrong?

An inaccurate prediction could cause a household to move its electricity consumption to a period that is actually more expensive. For a small business, it could increase operating costs.

The consequences could become more serious if the prediction is used by an automated system. For example, if an automated heating system reduces heating based on an incorrect price prediction, older people or people vulnerable to cold temperatures could be affected.

Therefore, a 30% prediction error does not necessarily have the same consequence for every user.

#### Person, mechanism and consequence

One example is a household that uses our prediction to decide when to consume electricity.

- **Person:** A household using the electricity price prediction.
- **Mechanism:** The household changes its electricity consumption based on the predicted price.
- **Consequence:** If the prediction is correct, the household may save money. If it is wrong, the household may move its consumption to a more expensive period and pay more.

#### Our responsibility

We have a responsibility to communicate the limitations of the model and make it clear that a prediction is not a guaranteed future electricity price.

The model should be evaluated against simple baselines and its performance should be communicated clearly. If a model has poor performance, for example a negative R² or does not perform better than a simple baseline, it should not be presented as a reliable basis for important decisions.

---

## Question 4 — Does anything change if the system is scaled up, sold or automated?

Choose one of these three changes (scaling up, sale, automation).

**If the system were sold.** What would a paying customer demand or be entitled to that they do not have now? For example guarantees about accuracy, availability, information when the system is down, and so on? What happens if the predictions are completely wrong?

**If the system were scaled up a lot.** If your predictions were followed by hundreds of thousands of households, they would change electricity consumption, which could affect the price. What happens to the predictions then?

**If the solution were automated.** A number on a web page is a kind of advice or information. But what happens if the system were connected to a heating system in many homes? Then a prediction can lead to a decision to turn on the heating. Who is responsible when the heating does not come on during a cold night? Under what circumstances would you be comfortable standing behind such a system?

### Answer

We chose automation.

Today, our system only provides an electricity price prediction as information. The user can see the prediction and decide whether or not to act on it. This means that a human is still responsible for the final decision.

This changes if the prediction is connected directly to an automated system. For example, our prediction could be connected to a heating system that automatically reduces heating when electricity prices are predicted to be high.

#### What could go wrong?

The model could make an incorrect prediction, the input data could be wrong or missing, or part of the data pipeline could fail.

If the heating system automatically acts on this information, a wrong prediction could cause the heating to be reduced unnecessarily. This could make a home uncomfortably or even dangerously cold, especially for older people or people who are vulnerable to cold temperatures.

#### Person, mechanism and consequence

- **Person:** A resident whose heating is controlled automatically.
- **Mechanism:** Our electricity price prediction is used by an automated system to decide when to reduce heating.
- **Consequence:** An incorrect prediction could cause the heating to be reduced at the wrong time, affecting the resident's comfort or safety.

#### Responsibility

Automation increases the responsibility of the system because the prediction can cause an action without a person checking it first.

Before we would be comfortable supporting this kind of system, we would require:

- safety limits, for example a minimum allowed indoor temperature;
- monitoring to detect problems with the model, data or pipeline;
- fallback behaviour if data or predictions are unavailable or unreliable;
- a way for the user to override the automated decision;
- clear information about the limitations of the prediction;
- clear responsibility between the model provider and the organisation operating the heating system.

An electricity price prediction should never override basic safety requirements.

---

## Before lunch

- [ ] The worksheet is filled in and committed.
- [ ] **One** of the four questions is chosen as the question you present on Thursday for 2–3 minutes.
- [ ] Everyone in the group has read all answers: any of you can get the question on Thursday.

Chosen question for Thursday: _(fill in)_
