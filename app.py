
"""finlit-voice-agents - the Streamlit app.

Run it with::

    streamlit run app.py

Everything that computes lives in :mod:`finlit.engines`, :mod:`finlit.numbers`
and :mod:`finlit.literacy`. This file only moves values between the widgets and
those functions, which is deliberate: a financial figure that is only reachable
by starting a web server cannot be tested by hand, and the numbers are the part
that has to be right.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Dict, Tuple

import streamlit as st

# The finlit package lives beside this file, so the folder has to be deployed
# with it. A bare "No module named 'finlit'" says nothing useful about that,
# which is the one thing someone hitting it on a fresh deploy needs to know.
try:
    from finlit import DOMAINS, __version__, content, engines, languages, literacy
    from finlit.numbers import format_money, money
    from finlit.speech import render_speech_panel
except ModuleNotFoundError as error:
    if error.name != "finlit":
        raise
    st.error(
        "The finlit package could not be found.\n\n"
        f"Looking in: `{Path(__file__).parent}`\n\n"
        "Deploy the whole project, not just app.py. The `finlit/` folder has "
        "to be next to `app.py` in the repository. It should contain "
        "`__init__.py`, `content.py`, `engines.py`, `languages.py`, "
        "`literacy.py`, `numbers.py` and a `speech/` folder."
    )
    st.stop()

st.set_page_config(
    page_title="Finlit Voice Agents",
    page_icon="💰",
    layout="centered",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

#: Keys this app stores in ``st.session_state``. Named constants so a typo is a
#: NameError at import rather than a silently fresh widget on every rerun.
_TRANSCRIPT = "transcript"
_TIER = "tier"
_LANGUAGE = "language"
_DOMAIN = "domain"
_LESSON = "lesson"
_ANSWERED = "answered"
_PLAN = "plan"


def _initialise_state() -> None:
    """Seed session state on the first run.

    Streamlit reruns the whole script on every interaction, so anything not in
    session state is rebuilt from scratch each time and a user's transcript or
    answered questions silently disappear.
    """
    defaults = {
        _TRANSCRIPT: "",
        _TIER: "basic",
        _LANGUAGE: languages.DEFAULT_LANGUAGE,
        _DOMAIN: DOMAINS[0],
        _ANSWERED: {},
        _PLAN: None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)
    st.session_state.setdefault(_LESSON, None)


_initialise_state()

# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

#: Languages offered in the picker, in the order they appear on the flag.
_LANGUAGE_ORDER = ("en", "sn", "nd", "to", "ny", "lo")

_DOMAIN_LABELS = {
    "en": {
        "savings": "Saving money",
        "insurance": "Insurance",
        "investing": "Investing",
    },
    "sn": {"savings": "Kuchengeta mari", "insurance": "Inshurensi", "investing": "Kudyanda"},
    "nd": {"savings": "Ukugcinela imali", "insurance": "Inshurensi", "investing": "Ukuthengisa"},
    "to": {"savings": "Kuongola bwama", "insurance": "Inshurensi", "investing": "Kudyanda"},
    "ny": {"savings": "Kukwedza ntchito", "insurance": "Ntchito yainshurensi", "investing": "Kukwedza"},
    "lo": {"savings": "Kuongola boli", "insurance": "Nopolisa", "investing": "Kuongola"},
}


def _domain_label(domain: str, code: str) -> str:
    """Domain name in the selected language, falling back to the key.

    The tab labels are the one piece of UI text with no lesson to fall back to,
    so they carry their own small table rather than reaching into
    :mod:`finlit.content`.
    """
    return _DOMAIN_LABELS.get(code, {}).get(domain, domain.title())


def _sidebar() -> str:
    """Render the sidebar and return the chosen language code."""
    with st.sidebar:
        st.markdown("### Finlit Voice Agents")
        st.caption(
            "Explain, calculate and track savings, insurance and investing, "
            "in your own language."
        )

        st.markdown("#### Language")
        chosen = st.selectbox(
            "Language",
            options=list(_LANGUAGE_ORDER),
            index=_LANGUAGE_ORDER.index(st.session_state[_LANGUAGE]),
            format_func=lambda code: f"{languages.get_language(code).native_name}"
            f"  ({languages.get_language(code).english_name})",
            label_visibility="collapsed",
            key="language_picker",
        )
        st.session_state[_LANGUAGE] = chosen
        language = languages.get_language(chosen)

        if not content.is_translated(chosen):
            gaps = len(content.coverage_report().get(chosen, []))
            st.warning(
                f"The lessons are not yet written in {language.native_name}. "
                f"{gaps} sections are still English. The calculators work in "
                f"{language.native_name} and the numbers are read in "
                f"{language.native_name}.",
                icon="⚠️",
            )

        st.markdown("#### Reading level")
        tier_codes = literacy.tier_codes()
        tier = st.radio(
            "How much detail",
            options=tier_codes,
            index=tier_codes.index(st.session_state[_TIER]),
            format_func=lambda code: literacy.get_tier(code).label,
            label_visibility="collapsed",
            key="reading_level",
        )
        st.session_state[_TIER] = tier
        st.caption(literacy.get_tier(tier).description)

        st.markdown("---")
        st.caption(
            "Nothing here is financial advice. Figures are illustrations, not "
            "offers, and the rates used are not anyone's actual rate."
        )
        st.caption(f"Version {__version__}")
    return chosen


# ---------------------------------------------------------------------------
# Voice panel
# ---------------------------------------------------------------------------

def _read_aloud_text(domain: str, code: str) -> str:
    """The text the Read aloud button should read: the current lesson.

    It is the adapted lesson, not the raw one, so at the Simple reading level
    the spoken text is the short one. Falls back to the raw body if the lesson
    is not the one currently selected.
    """
    lesson_id = st.session_state.get(_LESSON)
    body = ""
    try:
        body = content.lesson_body(content.get_lesson(lesson_id), code)
    except (KeyError, TypeError):
        pass
    if not body:
        lessons = content.lessons_for_domain(domain)
        if lessons:
            body = content.lesson_body(lessons[0], code)
    if not body:
        return ""
    adapted, _ = literacy.adapt_text(body, st.session_state[_TIER], code)
    return adapted


def _voice_panel(code: str, say: str) -> None:
    """Microphone and speaker controls for the selected language.

    `say` is the current page text, so the Read aloud button has something real
    to read. The typed box below is always present and is the fallback when the
    microphone is unavailable or the user does not want to speak.
    """
    language = languages.get_language(code)
    locales: Tuple[Tuple[str, str], ...] = (
        (f"{language.native_name} ({language.bcp47})", language.bcp47),
    )
    st.subheader("Voice")
    st.caption(
        "The microphone uses your browser. Nothing is sent to this app's "
        "server - the audio stays in the browser. It works best in Chrome or "
        "Edge. Everything also works by typing."
    )
    typed = st.text_area(
        "Type here (or paste what the microphone heard)",
        key=_TRANSCRIPT,
        height=90,
        placeholder="Anything you would like to read, ask, or explain.",
    )
    if typed:
        st.session_state[_TRANSCRIPT] = typed
    render_speech_panel(locale=language.bcp47, locales=locales, say=say)


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------

def _lessons_tab(domain: str, code: str) -> None:
    """Lesson browser for one domain, with the reading level applied.

    The domain is a parameter rather than read from session state because this
    runs once per tab. Reading a single global value made all three tabs show
    the selected topic's lesson, and gave the three copies of the lesson
    selectbox identical auto-generated IDs, which Streamlit rejects as a
    duplicate element. Keys are therefore namespaced by domain.
    """
    lessons = content.lessons_for_domain(domain)
    if not lessons:
        st.info("No lessons for this topic yet.")
        return

    ids = [lesson.id for lesson in lessons]
    current = st.session_state.get(_LESSON)
    index = ids.index(current) if current in ids else 0

    choice = st.selectbox(
        "Lesson",
        options=ids,
        index=index,
        format_func=lambda lesson_id: content.lesson_title(
            content.get_lesson(lesson_id), code
        ),
        key=f"lesson_{domain}",
    )
    st.session_state[_LESSON] = choice
    lesson = content.get_lesson(choice)

    st.markdown(f"### {content.lesson_title(lesson, code)}")

    body = content.lesson_body(lesson, code)
    adapted, gaps = literacy.adapt_text(body, st.session_state[_TIER], code)
    st.markdown(adapted)

    takeaways = content.lesson_takeaways(lesson, code)
    if takeaways:
        st.markdown("**Remember**")
        for point in takeaways:
            st.markdown(f"- {point}")

    if gaps:
        st.caption(
            "No plain-language wording is available yet for: "
            + ", ".join(gaps)
            + ". A native speaker still needs to write these."
        )

    _check_understanding(domain, code)


def _check_understanding(domain: str, code: str) -> None:
    """One question on the topic, with the explanation after answering.

    Placed after the lesson rather than before the calculators on purpose: the
    question checks that the explanation landed, so it cannot do that job
    before the explanation has been read.
    """
    questions = content.questions_for_domain(domain)
    if not questions:
        return
    question = questions[0]

    st.markdown("---")
    with st.expander("Check what you took from this"):
        st.markdown(content.question_prompt(question, code))
        choices = content.question_choices(question, code)
        picked = st.radio(
            "Choose one",
            options=list(range(len(choices))),
            format_func=lambda i: choices[i],
            key=f"q_{question.id}",
        )
        if st.button("Check", key=f"check_{question.id}"):
            st.session_state[_ANSWERED][question.id] = picked

        answered = st.session_state[_ANSWERED].get(question.id)
        if answered is not None:
            if answered == question.correct_index:
                st.success(content.question_explain(question, code))
            else:
                st.error("Not quite.")
                st.info(content.question_explain(question, code))


# ---------------------------------------------------------------------------
# Savings calculator
# ---------------------------------------------------------------------------

# Paired (engine key, label) rather than a bare list of labels, so the label the
# user clicks is turned into an engine key by position instead of by string
# matching. Several languages reuse the same word for different intervals, and
# "monthly" versus a translated label is exactly the kind of mapping that
# silently selects the wrong interest frequency.
_COMPOUNDING: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "en": (
        ("monthly", "monthly"),
        ("quarterly", "quarterly"),
        ("annually", "annually"),
        ("daily", "daily"),
        ("continuous", "continuous"),
    ),
    "sn": (
        ("monthly", "mwedzi"),
        ("quarterly", "chitatu"),
        ("annually", "mwaka"),
        ("daily", "zuva"),
        ("continuous", "hazvana"),
    ),
    "nd": (
        ("monthly", "ngenyanga"),
        ("quarterly", "kotanga"),
        ("annually", "onyaka"),
        ("daily", "usuku"),
        ("continuous", "aphuzu"),
    ),
    "to": (
        ("monthly", "mwedzi"),
        ("quarterly", "chitatu"),
        ("annually", "mwaka"),
        ("daily", "zuva"),
        ("continuous", "mavula"),
    ),
    "ny": (
        ("monthly", "mwezi"),
        ("quarterly", "chitatu"),
        ("annually", "chaka"),
        ("daily", "tsiku"),
        ("continuous", "nzima"),
    ),
    # Lozi labels are not written yet, so it reuses the English set. Listed as a
    # review gap rather than guessed at.
    "lo": (
        ("monthly", "monthly"),
        ("quarterly", "quarterly"),
        ("annually", "annually"),
        ("daily", "daily"),
        ("continuous", "continuous"),
    ),
}


def _frequency_choices(code: str) -> Tuple[Tuple[str, str], ...]:
    """(engine key, label) pairs for the compounding dropdown."""
    return _COMPOUNDING.get(code, _COMPOUNDING["en"])


def _savings_tab(code: str) -> None:
    """Projection and goal calculator."""
    language = languages.get_language(code)
    st.markdown(f"### {content.localized({'en': 'Savings calculator'}, code)}")
    st.caption(
        "This illustration uses a rate of "
        f"{content.EXAMPLE_RATE * 100:.0f}% a year, which is a teaching figure "
        "and not anybody's actual offer. Replace it with your own rate if you "
        "have one."
    )

    col_a, col_b, col_c = st.columns(3)
    # Widgets take int or float, never Decimal. Streamlit's own type check
    # rejects anything that is not numbers.Integral or float, so passing Decimal
    # raises StreamlitMixedNumericTypesError when the script runs, not on import.
    #
    # That is fine, and is why the conversion happens here rather than in the
    # engines: a widget is a typed text field, and Decimal(str(value)) keeps a
    # float from ever reaching the arithmetic.
    balance = money(
        col_a.number_input(
            "Money you already have",
            min_value=0.0,
            max_value=1_000_000_000.0,
            value=5000.0,
            step=100.0,
            format="%.2f",
        )
    )
    contribution = money(
        col_b.number_input(
            "Add each month",
            min_value=0.0,
            max_value=10_000_000.0,
            value=200.0,
            step=10.0,
            format="%.2f",
        )
    )
    years = Decimal(
        str(
            col_c.number_input(
                "Years",
                min_value=0.5,
                max_value=float(engines.MAX_DURATION_MONTHS / 12),
                value=3.0,
                step=1.0,
            )
        )
    )

    choices = _frequency_choices(code)
    frequency = st.selectbox(
        "Interest is added",
        options=list(range(len(choices))),
        index=0,
        format_func=lambda i: choices[i][1],
    )

    inputs = engines.ProjectionInputs(
        balance=balance,
        contribution=contribution,
        years=Decimal(str(years)),
        annual_rate=content.EXAMPLE_RATE,
        compounding=choices[frequency][0],
    )
    problems = inputs.validate()
    if problems:
        for problem in problems:
            st.error(_problem_text(problem, code))
        return

    projection = engines.project_savings(
        inputs.balance,
        inputs.contribution,
        inputs.years,
        inputs.annual_rate,
        inputs.compounding,
    )

    st.markdown("---")
    left, middle, right = st.columns(3)
    left.metric(
        "You would have", format_money(projection.balance, code)
    )
    middle.metric("You put in", format_money(projection.contributed, code))
    right.metric("Growth", format_money(projection.interest, code))

    st.markdown("**Spoken**")
    summary = engines.describe_projection(projection, code)
    st.write(summary)
    st.caption("The same sentence is available to the voice panel below.")

    doubling = projection.doubling_month()
    if doubling:
        st.info(
            f"Your growth passes everything you put in after "
            f"{doubling // 12} years and {doubling % 12} months. Before that, "
            f"most of the balance is your own money."
        )
    else:
        st.info(
            f"At this rate, growth does not catch up with what you put in "
            f"within {int(projection.years)} years. That is normal, and it is "
            f"not a sign the plan is wrong."
        )

    if projection.schedule:
        st.markdown("**Balance over time**")
        st.line_chart(
            {
                "Balance": list(projection.schedule),
                "You put in": list(projection.contribution_schedule),
            }
        )
        st.caption(
            f"Currency shown is {language.native_name} default: "
            f"{language.currency_symbol} ({language.currency}). It is a display "
            f"choice only - change it below if it is wrong for you."
        )

    st.markdown("---")
    st.markdown("#### Working backwards")
    st.caption(
        "Enter a goal and this works out what you would need to add each month."
    )
    goal = money(
        st.number_input(
            "Goal",
            min_value=0.0,
            max_value=1_000_000_000.0,
            value=20000.0,
            step=500.0,
            format="%.2f",
        )
    )
    required = engines.needed_contribution(
        goal,
        inputs.years,
        inputs.annual_rate,
        inputs.compounding,
        inputs.balance,
    )
    st.metric("Add each month to reach it", format_money(required, code))
    if required <= projection.contributed - inputs.balance:
        st.success("Your current monthly amount already reaches this goal.")
    else:
        st.warning(
            f"You would need {format_money(required, code)} a month, which is "
            f"more than the {format_money(contribution, code)} set above."
        )


_PROBLEM_TEXT = {
    "balance_negative": "Money you already have cannot be negative.",
    "contribution_negative": "A monthly amount cannot be negative.",
    "horizon_zero": "Choose how many years to save for.",
    "horizon_too_long": "That is longer than this calculator will project.",
    "rate_out_of_range": "That rate looks wrong. Enter it as a decimal, such as 0.07 for 7%.",
    "compounding_unknown": "That interest frequency is not one this calculator knows.",
}


def _problem_text(code: str, language: str) -> str:
    """Message for an invalid input.

    English only, and says so in the sidebar: these are input errors rather
    than lesson content, and a wrong translation of "that rate looks wrong" is
    a worse outcome than an English one in a field the user can see.
    """
    return _PROBLEM_TEXT.get(code, "Check the numbers above.")


# ---------------------------------------------------------------------------
# Insurance tab
# ---------------------------------------------------------------------------

def _insurance_tab(code: str) -> None:
    """Claim calculator for one policy."""
    st.markdown("#### What a policy would pay")
    st.caption(
        "Work out what you would keep and what you would pay yourself."
    )
    col_a, col_b, col_c, col_d = st.columns(4)
    premium = money(
        col_a.number_input(
            "Premium each month", min_value=0.0, max_value=1_000_000.0,
            value=150.0, step=10.0, format="%.2f",
        )
    )
    cover = money(
        col_b.number_input(
            "Amount covered", min_value=0.0, max_value=1_000_000_000.0,
            value=25000.0, step=1000.0, format="%.2f",
        )
    )
    excess = money(
        col_c.number_input(
            "Excess you pay first", min_value=0.0, max_value=1_000_000.0,
            value=500.0, step=50.0, format="%.2f",
        )
    )
    loss = money(
        col_d.number_input(
            "Value of the loss", min_value=0.0, max_value=1_000_000_000.0,
            value=8000.0, step=500.0, format="%.2f",
        )
    )

    policy = engines.InsuranceComparison(
        name="your policy",
        monthly_premium=money(premium),
        sum_insured=money(cover),
        excess=money(excess),
    )
    insurer, user = policy.claim_payout(money(loss))
    a, b = st.columns(2)
    a.metric("The policy pays", format_money(insurer, code))
    b.metric("You pay", format_money(user, code))

    if user == money(loss):
        st.warning(
            "This loss is smaller than your excess, so the policy pays nothing "
            "on it. That is what the excess means."
        )
    elif insurer == money(cover):
        st.warning(
            "The loss is larger than the amount covered, so the policy pays out "
            "up to its limit and you carry the rest."
        )
    st.caption(
        "This ignores what the policy does not cover, waiting periods, and "
        "whether a claim would be accepted at all. Those exclusions are usually "
        "longer than the cover itself."
    )


# ---------------------------------------------------------------------------
# Investing tab
# ---------------------------------------------------------------------------

def _investing_tab(code: str) -> None:
    """Concentration check for a set of holdings."""
    st.markdown("#### How spread out is this?")
    st.caption(
        "Add what share of the money is in each thing. This is about "
        "concentration, not about whether a choice is right for you."
    )
    rows = st.data_editor(
        [{"Holding": "Holding 1", "Share": 60.0}, {"Holding": "Holding 2", "Share": 40.0}],
        num_rows="dynamic",
        column_config={"Share": st.column_config.NumberColumn("Share (%)", min_value=0.0)},
        hide_index=True,
        width="stretch",
        key="allocation",
    )
    weights = {
        str(row.get("Holding") or f"Holding {i + 1}"): Decimal(str(row.get("Share") or 0))
        for i, row in enumerate(rows)
    }
    weights = {name: share for name, share in weights.items() if share > 0}
    if not weights:
        st.info("Add at least one holding with a share above zero.")
        return

    largest, notes = engines.allocation_risk(weights)
    st.metric("Largest single share", f"{largest * 100:.0f}%")
    for note in notes:
        st.info(content.localized(note.text, code))


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

def main() -> None:
    """Render the app."""
    code = _sidebar()

    st.markdown("## What would you like to do?")
    domain = st.radio(
        "Topic",
        options=list(DOMAINS),
        index=list(DOMAINS).index(st.session_state[_DOMAIN]),
        format_func=lambda value: _domain_label(value, code),
        horizontal=True,
    )
    st.session_state[_DOMAIN] = domain

    tabs = st.tabs(
        [
            f"{_domain_label(DOMAINS[0], code)}",
            f"{_domain_label(DOMAINS[1], code)}",
            f"{_domain_label(DOMAINS[2], code)}",
        ]
    )
    with tabs[0]:
        _lessons_tab(DOMAINS[0], code)
        _savings_tab(code)
    with tabs[1]:
        _lessons_tab(DOMAINS[1], code)
        _insurance_tab(code)
    with tabs[2]:
        _lessons_tab(DOMAINS[2], code)
        _investing_tab(code)

    st.markdown("---")
    with st.expander("Voice input and output"):
        _voice_panel(code, say=_read_aloud_text(DOMAINS[0], code))
    st.caption(
        "The microphone is the browser's own. Audio is not sent to this app. "
        "Type anywhere instead if you prefer - everything works the same way."
    )


if __name__ == "__main__":
    # Streamlit executes the script with __name__ set to "__main__", so this
    # still runs in the app. The guard is what lets tests/test_app.py import
    # the helpers below without rendering the whole interface.
    main()
