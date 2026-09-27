# finlit

A voice-first financial literacy app for savings, insurance and investing, aimed
at people who are comfortable with money in their own language but not with
banking vocabulary or percentages.

## Running it

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

Then open the address Streamlit prints, normally <http://localhost:8502>.

To run the tests:

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## What it does

Three tabs, one per topic:

- **Savings** — future value of a balance plus monthly deposits, a goal
  calculator that works backwards to the deposit you need, an emergency fund
  target, and a chart of the projected balance.
- **Insurance** — compares policies, works out what a policy pays on a claim
  after the excess, and shows the claim payout per month of premium.
- **Investing** — a risk note for a chosen split of holdings.

Every screen has a reading level, and a language selector. The reading level
changes the wording, not the arithmetic: at **Simple** the jargon is replaced
with everyday words, percentages become counts out of a hundred, and the
arithmetic is hidden. At **Detailed** the working is shown.

## Voice

Speech uses the browser's own Web Speech API through `st.iframe`, so there is
no API key, no account, no audio sent to a server, and nothing to install. It
works best in Chrome or Edge.

Recognised speech stays in the browser: an embedded widget cannot hand a value
back to the Python session, so the **Copy** button puts the transcript on the
clipboard and there is always a normal text box to type or paste into. Every
feature works without a microphone.

## Languages

English, Shona, Ndebele, Tonga, Chichewa and Lozi, with per-language numbers,
currencies, literacy levels, jargon glosses and speech locales.

**The lesson content is currently English only.** The other five languages fall
back to English and the interface says so. The interface labels and terminology
glosses exist in all six but are drafts.

Do not put this in front of users in Shona, Ndebele, Tonga, Chichewa or Lozi
until it has been through a native speaker and a financial professional. See
`docs/TRANSLATION_REVIEW.md` for what is outstanding. The fallback is
deliberate: an invented translation reads as fluent and teaches something
wrong, which is worse than an honest gap.

## Numbers

All arithmetic is `Decimal`, and widgets convert to it on the way in. A float
never reaches a calculation.

Interest is compounded per period rather than per year, because the frequency
changes the answer and people assume it does not. Finer compounding always
earns more, and there is a test pinning that ordering.

The example rate is 8% and is a teaching figure, not anybody's actual offer.

## Layout

| Path | What is in it |
| --- | --- |
| `app.py` | The Streamlit interface. |
| `finlit/languages.py` | Language registry, currencies, speech locales, detection. |
| `finlit/numbers.py` | Parsing and formatting numbers, money and durations. |
| `finlit/literacy.py` | Reading levels, jargon glosses, rate simplification. |
| `finlit/content.py` | Lessons and questions, and the coverage report. |
| `finlit/engines.py` | Savings, insurance and investing calculations. |
| `finlit/speech/browser.py` | The browser microphone and speaker. |
| `docs/TRANSLATION_REVIEW.md` | What still needs a native speaker. |

## What is not built

Cloud speech services and local Whisper. The browser path is the one that
matters for this audience: it needs no key, no account and no install.
