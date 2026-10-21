"""Exam Studio: course-grounded practice with browser-local saved attempts."""
from __future__ import annotations

import gzip
import html
import io
import json
import os
from pathlib import Path
import random
import time
import uuid
import zipfile

import pandas as pd
import streamlit as st
import streamlit.components.v2 as components

from exam_core import (
    check, elapsed, export_attempt, import_attempt, new_attempt, now, pause,
    portable, submit, touch, validate_attempt,
)
from ai_tutor import ask, DEFAULT_MODEL, PROMPT_VERSION, TutorError

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title="Exam Studio · Practice with purpose", page_icon="✳", layout="wide")
st.html("<style>" + (ROOT / "assets/style.css").read_text(encoding="utf-8") + "</style>")


@st.cache_data
def catalog():
    return json.loads((ROOT / "data/catalog.json").read_text(encoding="utf-8"))


CAT = catalog()
QUESTIONS = {q["id"]: q for q in CAT["questions"]}
EXAMS = {e["id"]: e for e in CAT["exams"]}
DATASETS = CAT["datasets"]


@st.cache_data
def dataset_bytes(key):
    d = DATASETS[key]
    raw = (ROOT / "data" / d["file"]).read_bytes()
    return gzip.decompress(raw) if d.get("compressed") else raw


@st.cache_data
def bundle(keys):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for key in keys:
            archive.writestr(DATASETS[key]["download_name"], dataset_bytes(key))
    return out.getvalue()


vault = components.component(
    "exam_studio_vault",
    html='<div id="vault-status" role="status" style="font:12px sans-serif;color:#5d7169;padding:6px 0"></div>',
    js=(ROOT / "assets/vault.js").read_text(encoding="utf-8"),
)
timer = components.component(
    "exam_studio_timer",
    html='<div style="background:#e5eee7;border-radius:12px;padding:16px 20px"><div id="clock" style="font:600 30px monospace;color:#164b40"></div><div id="clock-caption" style="font:12px sans-serif;color:#45665b;margin-top:5px"></div></div>',
    js=(ROOT / "assets/timer.js").read_text(encoding="utf-8"),
)

defaults = {
    "session_id": str(uuid.uuid4()), "loaded": False, "attempts": {},
    "base_revisions": {}, "active": None, "page": "Practice",
    "operation": None, "processed_event": None, "save_status": "Loading saved attempts…",
    "storage_error": None, "view_epoch": 0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v
ss = st.session_state


def queue_save(attempt):
    snapshot = portable(attempt)
    ss.attempts[attempt["id"]] = snapshot
    ss.operation = {"id": str(uuid.uuid4()), "attempt": snapshot,
                    "base_revision": ss.base_revisions.get(attempt["id"], 0)}
    ss.save_status = "Saving in this browser…"


def storage():
    result = vault(
        data={"phase": "ready" if ss.loaded else "load", "session": ss.session_id,
              "operation": ss.operation, "status": ss.save_status},
        key="vault", on_event_change=lambda: None,
    )
    event = result.get("event")
    if event and event.get("id") != ss.processed_event:
        ss.processed_event = event.get("id")
        if event["type"] == "loaded":
            failed = 0
            for raw in event["attempts"]:
                try:
                    attempt = validate_attempt(raw)
                    ss.attempts[attempt["id"]] = attempt
                    ss.base_revisions[attempt["id"]] = attempt["revision"]
                except ValueError:
                    failed += 1
            ss.loaded = True
            ss.save_status = f"{len(ss.attempts)} saved attempt(s) available in this browser."
            if failed:
                ss.storage_error = f"{failed} incompatible saved record(s) were left untouched."
        elif event["type"] == "saved":
            attempt = event["attempt"]
            ss.base_revisions[attempt["id"]] = attempt["revision"]
            if ss.operation and ss.operation["id"] == event["id"]:
                ss.operation = None
            ss.save_status = "Saved in this browser · " + attempt["updated_at"].replace("T", " ").replace("+00:00", " UTC")
            ss.storage_error = None
        elif event["type"] == "error":
            ss.loaded = True
            ss.storage_error = event["message"]
            ss.save_status = "Not saved in this browser — download a backup."
            ss.operation = None
        st.rerun()


def go(page):
    if ss.active:
        pause(ss.active)
        touch(ss.active)
        queue_save(ss.active)
    ss.page = page


def start(exam, mode):
    if ss.active:
        pause(ss.active)
        touch(ss.active)
        queue_save(ss.active)
    ss.active = new_attempt(exam, [QUESTIONS[q] for q in exam["questions"]], mode)
    ss.page = "Workspace"
    ss.view_epoch += 1
    queue_save(ss.active)
    st.rerun()


def response_edit(qid, answer_key, method_key):
    a = ss.active
    response = a["responses"].setdefault(qid, {"answer": "", "method": "", "history": []})
    response["answer"] = ss.get(answer_key, response["answer"])
    response["method"] = ss.get(method_key, response["method"])
    touch(a)
    queue_save(a)


def note_edit(key):
    ss.active["notes"] = ss[key]
    touch(ss.active)
    queue_save(ss.active)


def ai_draft_edit(qid, keys):
    response = ss.active["responses"][qid]
    response["ai_draft"] = {field: ss.get(key, "") for field, key in keys.items()}
    touch(ss.active)
    queue_save(ss.active)


def ai_settings():
    try:
        return (st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", "")),
                st.secrets.get("GEMINI_MODEL", os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)))
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return os.environ.get("GEMINI_API_KEY", ""), os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def ai_help(a, q, response, can_review):
    with st.expander("Get help from AI"):
        st.caption(f'Help context · Current question {q["id"]} · {q["title"]}')
        if not can_review:
            st.info("AI help unlocks after finishing in Exam mode. Use Practice mode for help as you go.")
            return
        history = response.setdefault("ai_history", [])
        for turn in history:
            with st.chat_message(turn["role"]):
                st.markdown(turn["content"])
        draft = response.get("ai_draft", {})
        keys = {field: f'ai_{field}_{a["id"]}_{q["id"]}_{ss.view_epoch}' for field in ("working", "output", "request")}
        for field, key in keys.items():
            if key not in ss:
                ss[key] = draft.get(field, response["method"] if field == "working" else response["answer"] if field == "output" else "")
        st.text_area("What I currently have", key=keys["working"], max_chars=6000, height=100,
                     on_change=ai_draft_edit, args=(q["id"], keys),
                     placeholder="Paste your formula, query or explain what you have tried.")
        st.text_area("The output I’m getting (optional)", key=keys["output"], max_chars=6000, height=80,
                     on_change=ai_draft_edit, args=(q["id"], keys))
        st.text_area("What would you like help with?", key=keys["request"], max_chars=3000, height=80,
                     on_change=ai_draft_edit, args=(q["id"], keys),
                     placeholder="You can also ask a follow-up about the previous reply.")
        api_key, model = ai_settings()
        if not api_key:
            st.info("AI help is ready to connect. Add GEMINI_API_KEY in the app’s Streamlit Secrets to enable replies. Your draft is still saved.")
        st.caption(f"Powered by Gemini · {model}. Ask AI sends this question, dataset structure, your text and recent conversation turns to Google. Guidance can be mistaken; verify it against your data.")
        send_col, clear_col = st.columns(2)
        if send_col.button("Ask AI", key="ask_"+q["id"], type="primary",
                           disabled=not api_key or not (ss[keys["working"]].strip() or ss[keys["request"]].strip())):
            try:
                if time.monotonic() - ss.get("last_ai_request", -100) < 5:
                    raise TutorError("Please wait a few seconds before another request. Your text is kept.")
                ss.last_ai_request = time.monotonic()
                with st.spinner("Gemini is thinking about your current question…"):
                    reply, message = ask(q, [DATASETS[k] for k in q["datasets"] if k in DATASETS],
                                         history[response.get("ai_context_start", 0):],
                                         ss[keys["working"]], ss[keys["output"]], ss[keys["request"]],
                                         api_key, model)
                history.extend([
                    {"role": "user", "content": message, "at": now()},
                    {"role": "assistant", "content": reply, "at": now(), "model": model, "prompt_version": PROMPT_VERSION},
                ])
                removed = max(0, len(history)-100)
                response["ai_history"] = history[-100:]
                response["ai_context_start"] = max(0, response.get("ai_context_start", 0)-removed)
                response.pop("ai_error", None)
                touch(a); queue_save(a); st.rerun()
            except TutorError as exc:
                response["ai_error"] = str(exc)
                touch(a); queue_save(a); st.rerun()
        if clear_col.button("Start a fresh conversation", key="clear_ai_"+q["id"], disabled=not history):
            # Retain existing guidance in the saved attempt; only reset the next request's context.
            response["ai_context_start"] = len(history)
            touch(a); queue_save(a)
            st.toast("The next request starts fresh. Previous guidance remains saved above.")
        if response.get("ai_error"):
            st.error(response["ai_error"])


def show_feedback(record):
    method = st.success if record["status"] == "match" else st.info if record["status"] == "review" else st.warning
    method(record["message"])


def paginate(items, page_size, key, filters, label):
    filter_key = key + "_filters"
    if ss.get(filter_key) != filters:
        ss[key] = 0
        ss[filter_key] = filters
    page_count = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(ss.get(key, 0), page_count - 1))
    ss[key] = page
    first = page * page_size
    visible = items[first:first + page_size]
    back, count, next_page = st.columns([1, 4, 1])
    if back.button("Back", key=key + "_back", disabled=page == 0, use_container_width=True):
        ss[key] = page - 1
        st.rerun()
    count.caption(f"Showing {first + 1 if visible else 0}–{first + len(visible)} of {len(items)} {label} · {len(visible)} shown · Page {page + 1} of {page_count}")
    if next_page.button("Next", key=key + "_next", disabled=page >= page_count - 1, use_container_width=True):
        ss[key] = page + 1
        st.rerun()
    return visible


def practice():
    st.markdown('<div class="eyebrow">Data analytics in accounting</div>', unsafe_allow_html=True)
    st.title("A little practice. A lot more confidence.")
    st.markdown('<div class="hero"><h2>Your next exam starts here.</h2><p>Work with the course datasets, check your results, and pick up where you left off. A thoughtful practice space for Excel, SQL and regression interpretation.</p></div>', unsafe_allow_html=True)
    cols = st.columns(3)
    cols[0].metric("Course-based questions", len(QUESTIONS))
    cols[1].metric("Curated practice exams", len(EXAMS))
    cols[2].metric("Your saved attempts", len(ss.attempts))
    st.write("")
    st.subheader("Choose your practice")
    subject = st.segmented_control("Exam type", ["All", "Manipulation", "Interpretation"], default="All")
    st.caption("Check your answers as you go. Manipulation exams: 8 minutes. Interpretation exams: 5 minutes.")
    options = [e for e in CAT["exams"] if subject in (None, "All", e["subject"])]
    if st.button("Choose an exam for me", icon=":material/shuffle:", disabled=not ss.loaded):
        previous = ss.active["exam_id"] if ss.active else None
        choices = [e for e in options if e["id"] != previous] or options
        start(random.choice(choices), "Practice")
    visible = paginate(options, 8, "exam_page", subject, "exams")
    for offset in range(0, len(visible), 2):
        columns = st.columns(2)
        for col, exam in zip(columns, visible[offset:offset+2]):
            with col, st.container(border=True):
                st.markdown(f'<span class="badge">{exam["subject"]}</span><span class="badge">{exam["minutes"]} min</span>', unsafe_allow_html=True)
                st.subheader(exam["title"])
                st.write(exam["description"])
                st.caption(f'{len(exam["questions"])} questions · {exam["id"]}')
                if st.button("Start this exam", key="start_"+exam["id"], use_container_width=True, disabled=not ss.loaded):
                    start(exam, "Practice")
    st.caption("These are independently authored practice exams based on the supplied cases. They are not an official or exhaustive exam bank.")


def bank():
    st.markdown('<div class="eyebrow">Build one skill at a time</div>', unsafe_allow_html=True)
    st.title("Question library")
    c1,c2,c3 = st.columns([1,1.4,2])
    subject = c1.selectbox("Subject", ["All","Excel","SQL","Interpretation"])
    skills = sorted({q["skill"] for q in QUESTIONS.values() if subject=="All" or q["subject"]==subject})
    skill = c2.selectbox("Skill", ["All",*skills])
    term = c3.text_input("Search", placeholder="Try: payroll, lookup, game day…")
    matches = [q for q in QUESTIONS.values() if (subject=="All" or q["subject"]==subject)
               and (skill=="All" or q["skill"]==skill)
               and term.casefold() in (q["title"]+" "+q["prompt"]+" "+q["source"]).casefold()]
    st.caption(f"{len(matches)} questions")
    if not matches:
        st.info("No questions match. Try another skill or a shorter search.")
    visible = paginate(matches, 12, "question_page", (subject, skill, term), "questions")
    for q in visible:
        with st.container(border=True):
            a,b = st.columns([5,1])
            a.markdown(f'**{q["id"]} · {q["title"]}**')
            a.caption(q["subject"]+" · "+q["skill"]+" · "+("Self-review" if q["kind"]=="explain" else "Result checker"))
            if b.button("Practise",key="single_"+q["id"],disabled=not ss.loaded):
                start({"id":"single-"+q["id"],"title":q["title"],"questions":[q["id"]],"minutes":5 if q["subject"]=="Interpretation" else 8},"Practice")
            with st.expander("Task and course reference"):
                st.write(q["prompt"])
                st.caption(q["source"])


def workspace():
    a=ss.active
    if not a:
        st.info("Choose an exam or resume a saved attempt to begin.")
        return
    st.markdown('<div class="eyebrow">'+html.escape(a["mode"])+' workspace</div>',unsafe_allow_html=True)
    st.title(a["title"])
    if a["status"]=="completed":
        st.success("Attempt completed. Review your answers and feedback below, or reopen it to make revisions.")
    answered=sum(bool(r.get("answer","").strip()) for r in a["responses"].values())
    st.progress(answered/len(a["questions"]),text=f'{answered} of {len(a["questions"])} questions have an answer')
    st.caption("EXAM QUESTIONS · Select any question to jump to it. ✓ = checked output matches · ● = answer entered")
    for offset in range(0, len(a["questions"]), 6):
        navigation = st.columns(min(6, len(a["questions"])-offset))
        for col, index in zip(navigation, range(offset, min(offset+6, len(a["questions"])))):
            question = a["questions"][index]
            record = a["responses"].get(question["id"], {})
            matches = (record.get("history") and record["history"][-1]["status"] == "match"
                       and record["history"][-1]["answer"] == record.get("answer"))
            marker = " ✓" if matches else " ●" if record.get("answer", "").strip() else ""
            if col.button(f'{index+1:02d} · {question["subject"]}{marker}',
                          key=f'nav_{a["id"]}_{index}',
                          help=question["id"]+" · "+question["title"],
                          type="primary" if index==a["position"] else "secondary",
                          use_container_width=True):
                a["position"]=index;ss.view_epoch+=1;touch(a);queue_save(a);st.rerun()
    main, side = st.columns([3,1],gap="large")
    with side:
        timer(data={"elapsed":elapsed(a),"duration":a["duration"],"running":a["running_since"] is not None},key="clock")
        t1,t2=st.columns(2)
        if t1.button("Pause" if a["running_since"] is not None else "Start timer",disabled=a["status"]=="completed",use_container_width=True):
            if a["running_since"] is None:
                a["running_since"]=time.time()
            else:
                pause(a)
            touch(a);queue_save(a);st.rerun()
        if t2.button("Reset timer",use_container_width=True):
            a["elapsed"]=0.0;a["running_since"]=None
            touch(a);queue_save(a);st.rerun()
        st.caption("Save & leave pauses the clock. Restored attempts open paused; time away is excluded.")
        keys=tuple(sorted({d for q in a["questions"] for d in q["datasets"] if d in DATASETS}))
        with st.expander("Exam files",expanded=True):
            if keys:
                st.download_button("Download all files",bundle(keys),file_name=a["exam_id"]+"-files.zip",mime="application/zip",use_container_width=True)
            for key in keys:
                d=DATASETS[key]
                st.download_button(d["label"],dataset_bytes(key),file_name=d["download_name"],key="file_"+key)
                if d.get("note"):
                    st.caption(d["note"])
        if st.button("Save & leave",use_container_width=True):
            pause(a);touch(a);queue_save(a);ss.page="Saved attempts";st.rerun()
        st.download_button("Download attempt backup",export_attempt(a),file_name=f'exam-studio-{a["id"]}.json',mime="application/json",use_container_width=True)
        st.caption("Backups include questions, answers, notes and feedback—not your external Excel or SQL files.")
    with main:
        q=a["questions"][a["position"]]
        st.caption(f'Question {a["position"]+1} of {len(a["questions"])} · {q["id"]} · '+q["subject"]+" / "+q["skill"])
        st.subheader(q["title"])
        st.write(q["prompt"])
        with st.expander("Course reference"):
            st.write(q["source"])
            st.caption("This attempt retains a snapshot of its questions and reference answers.")
        response=a["responses"].setdefault(q["id"],{"answer":"","method":"","history":[]})
        prefix=f'{a["id"]}_{q["id"]}_{ss.view_epoch}'
        ak,mk="answer_"+prefix,"method_"+prefix
        if ak not in ss:ss[ak]=response["answer"]
        if mk not in ss:ss[mk]=response["method"]
        if q["kind"]=="table":
            st.caption("Paste a table copied from Excel or CSV, including headers: "+", ".join(q["columns"])+". Decimal dots recommended; text values are case-sensitive.")
        elif q["kind"]=="number":
            st.caption(f'Enter only a number. Accepted numeric tolerance: ±{q.get("tolerance",0.01):g}.')
        st.text_area("Your result" if q["kind"]!="explain" else "Your explanation",height=150,key=ak,
            max_chars=20000,on_change=response_edit,args=(q["id"],ak,mk),disabled=a["status"]=="completed")
        st.text_area("Your method or working notes",height=100,key=mk,max_chars=20000,
            on_change=response_edit,args=(q["id"],ak,mk),disabled=a["status"]=="completed",
            placeholder="Keep the formula, query or reasoning you used.")
        st.caption("Edits save when you leave the field. Check the browser-save status before closing.")
        can_review=a["mode"]=="Practice" or a["status"]=="completed"
        b1,b2=st.columns(2)
        if b1.button("Review explanation" if q["kind"]=="explain" else "Check my result",type="primary",disabled=not can_review or not response["answer"].strip(),use_container_width=True):
            submit(a,q,response["answer"],response["method"]);queue_save(a);st.rerun()
        if b2.button("Save current work",use_container_width=True):
            touch(a);queue_save(a);st.rerun()
        if not can_review:st.info("Exam mode: feedback, hints and solutions unlock when you finish the attempt.")
        if response["history"] and can_review:
            latest=response["history"][-1]
            if latest["answer"]==response["answer"]:
                show_feedback(latest)
            else:st.info("Your answer has changed since the last check. Check it again for updated feedback.")
        ai_help(a, q, response, can_review)
        if can_review:
            if q["kind"]=="explain":
                with st.expander("Self-review checklist",expanded=bool(response["history"])):
                    for point in q["rubric"]:st.markdown("- "+point)
            with st.expander("A hint, if you need one"):
                st.write(q["hint"])
            with st.expander("Reveal a worked approach"):
                st.caption("Try the task first. A matching output alone does not validate your method.")
                if q["subject"]=="SQL" and q["kind"]!="explain":st.code(q["solution"],language="sql")
                else:st.write(q["solution"])
                if q["kind"]=="table":st.dataframe(pd.DataFrame(q["answer"],columns=q["columns"]),hide_index=True,use_container_width=True)
                elif q["kind"]=="number":st.write("Reference result:",q["answer"])
        if response["history"]:
            with st.expander(f'Previous checks ({len(response["history"])})'):
                for record in reversed(response["history"]):
                    st.caption(record["at"].replace("T"," "))
                    st.text(record["answer"])
                    show_feedback(record)
                    if record["method"]:st.text(record["method"])
        n1,n2=st.columns(2)
        if n1.button("← Previous",disabled=a["position"]==0,use_container_width=True):
            a["position"]-=1;ss.view_epoch+=1;touch(a);queue_save(a);st.rerun()
        if n2.button("Next →",disabled=a["position"]==len(a["questions"])-1,use_container_width=True):
            a["position"]+=1;ss.view_epoch+=1;touch(a);queue_save(a);st.rerun()
    with st.expander("Reflection for next time"):
        nk=f'notes_{a["id"]}_{ss.view_epoch}'
        if nk not in ss:ss[nk]=a["notes"]
        st.text_area("What will you try differently?",key=nk,max_chars=20000,on_change=note_edit,args=(nk,))
    if a["status"]=="completed":
        if st.button("Reopen this attempt to revise"):
            a["status"]="in_progress";touch(a);queue_save(a);st.rerun()
    else:
        if answered<len(a["questions"]):st.caption(f'{len(a["questions"])-answered} unanswered question(s) will remain available for later revision.')
        if st.button("Finish attempt & review",type="primary"):
            pause(a);a["status"]="completed"
            for question in a["questions"]:
                r=a["responses"].get(question["id"])
                if r and r["answer"].strip() and (not r["history"] or r["history"][-1]["answer"]!=r["answer"]):
                    submit(a,question,r["answer"],r["method"])
            touch(a);queue_save(a);st.rerun()


def saved():
    st.markdown('<div class="eyebrow">Your learning, kept together</div>',unsafe_allow_html=True)
    st.title("Saved attempts")
    st.write("Return to an unfinished exam or revisit the reasoning behind a previous answer.")
    st.caption("Saved on this browser and device. Clearing site data removes these copies; export a backup to move devices or keep an independent copy. Saved answers are sent to this app's server when opened, but are not written to a shared server database.")
    with st.expander("Restore an attempt from a backup"):
        file=st.file_uploader("Choose an Exam Studio JSON backup",type=["json"])
        if file is not None:
            try:
                restored=import_attempt(file.getvalue())
                missing={d for q in restored["questions"] for d in q["datasets"] if d not in DATASETS}
                st.write(restored["title"])
                if missing:st.warning("Some original datasets are not in this version. The saved answers and feedback can still be reviewed.")
                st.caption("Imported as a separate copy so an existing attempt is never overwritten.")
                if st.button("Restore as a new copy",disabled=not ss.loaded):
                    restored["id"]=str(uuid.uuid4());restored["title"]+=" · restored"
                    restored["revision"]=0;touch(restored)
                    ss.active=restored;ss.page="Workspace";ss.view_epoch+=1
                    queue_save(restored);st.rerun()
            except ValueError as exc:st.error(str(exc))
    attempts=sorted(ss.attempts.values(),key=lambda a:a["updated_at"],reverse=True)
    if not attempts:
        st.info("Your first saved attempt will appear here. Start an exam or restore a backup.")
    for a in attempts:
        with st.container(border=True):
            c1,c2=st.columns([4,1])
            c1.subheader(a["title"])
            count=sum(bool(r.get("answer","").strip()) for r in a["responses"].values())
            c1.caption(f'{a["status"].replace("_"," ").title()} · {count}/{len(a["questions"])} answered · {a["mode"]} · Last saved {a["updated_at"].replace("T"," ").replace("+00:00"," UTC")}')
            if c2.button("Review" if a["status"]=="completed" else "Resume",key="resume_"+a["id"],use_container_width=True):
                ss.active=validate_attempt(a);ss.page="Workspace";ss.view_epoch+=1;st.rerun()
            c2.download_button("Backup",export_attempt(a),file_name=f'exam-studio-{a["id"]}.json',mime="application/json",key="backup_"+a["id"],use_container_width=True)


def guide():
    st.markdown('<div class="eyebrow">A clear path through practice</div>',unsafe_allow_html=True)
    st.title("How it works")
    for title,body in [
        ("1 · Work in your own tools","Download the course files and solve the task in Excel or a SQLite editor. For regression, read the model supplied in the question."),
        ("2 · Check the result, explain the method","Paste a value or result table. Checks compare against fixed reference answers. Explanations use a checklist, not an automatic grade."),
        ("3 · Keep the useful part","Answers, method notes and feedback history save in your browser after edits reach the app. Save & leave also pauses the timer. Download a backup for another device."),
    ]:
        with st.container(border=True):st.subheader(title);st.write(body)
    st.subheader("What is in this release?")
    st.write(f'{len(QUESTIONS)} questions and {len(EXAMS)} exams cover film permits, messy employee codes, journal entries, payroll, songs, Chinook, movies, P-cards and restaurant regressions.')
    st.write("All tasks cite the supplied case material. SQL adaptations specify their output format. Restaurant coefficients are fitted to the supplied data; prediction scenarios are labelled. Optional Fiftyville and optional P-card tasks are excluded.")
    st.info("Result checking and authored hints work without an API key. Get help from AI uses Gemini 3.5 Flash-Lite when the app owner connects it. Each question keeps its own saved conversation.")
    st.subheader("A few useful boundaries")
    st.markdown("- Manipulation exams have an 8-minute timer; interpretation exams have a 5-minute timer. These practice exams are not an official exam bank.\n- A correct output does not establish that your method is correct.\n- Browser saving is not account-based sync. Back up important attempts.\n- Excel workbooks and SQL-editor files remain on your device; save them separately.\n- Imported backups are your own records, not verified credentials or grades.\n- AI guidance is saved with the attempt. The tutor receives up to the latest 12 conversation messages for the current question.")
    with st.expander("Dataset provenance"):
        for d in DATASETS.values():
            st.markdown("**"+d["label"]+"**")
            st.caption(d["source"])
            if d.get("note"):st.write(d["note"])


with st.sidebar:
    st.markdown("## ✳ Exam Studio")
    st.caption("PRACTICE WITH PURPOSE")
    st.write("")
    for label,icon in [("Practice",":material/space_dashboard:"),("Question library",":material/menu_book:"),("Saved attempts",":material/bookmark:"),("How it works",":material/info:")]:
        st.button(label,icon=icon,on_click=go,args=(label,),use_container_width=True,
                  type="primary" if ss.page==label else "secondary")
    if ss.active:
        st.divider()
        st.caption("CURRENT ATTEMPT")
        st.write(ss.active["title"])
        st.button("Back to workspace",on_click=go,args=("Workspace",),use_container_width=True)
    st.divider()
    st.caption("Excel · SQL · Interpretation")
    st.caption("Built around the supplied course cases.")

storage()
if ss.storage_error:st.warning(ss.storage_error)
pages={"Practice":practice,"Question library":bank,"Workspace":workspace,"Saved attempts":saved,"How it works":guide}
pages.get(ss.page,practice)()
st.markdown('<div class="footer">Exam Studio · Data Analytics in Accounting · Independent course-based practice</div>',unsafe_allow_html=True)
