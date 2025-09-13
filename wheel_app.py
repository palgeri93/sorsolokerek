
import io
import os
import time
import random
import base64
import wave
from typing import List, Optional

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import streamlit.components.v1 as components

st.set_page_config(page_title="Sorsolókerék – Excel munkalapokkal", layout="centered")
st.title("🎡 Sorsolókerék – Excelből, munkalapok szerint")

st.write(
    "Tölts fel egy **.xlsx** fájlt több munkalappal. "
    "A gombok **pontosan** a munkalapok nevét viselik; a megnyomott gombnak megfelelő listából sorsol."
)

# ---------- Hang generálás (WAV) ----------
def _tone_wav_bytes(freq: float, duration_s: float, volume: float = 0.2, sr: int = 44100) -> bytes:
    t = np.linspace(0, duration_s, int(sr * duration_s), False)
    samples = (np.sin(2 * np.pi * freq * t) * (32767 * volume)).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())
    return buf.getvalue()

# rövid "pörgés" hang (loop-olható), és hosszabb "ding" nyeréskor
SPIN_WAV = _tone_wav_bytes(freq=520, duration_s=0.12, volume=0.15)
WIN_WAV  = _tone_wav_bytes(freq=880, duration_s=0.35, volume=0.25)

def play_audio_bytes(sound_bytes: bytes, loop: bool = False):
    """Beágyazott <audio> HTML autoplay-jel; a visszaadott komponens azonnal lejátszik a kattintás után."""
    b64 = base64.b64encode(sound_bytes).decode('ascii')
    loop_attr = " loop" if loop else ""
    html = f"""
    <audio autoplay{loop_attr} style="display:none">
        <source src="data:audio/wav;base64,{b64}" type="audio/wav">
    </audio>
    """
    components.html(html, height=0)

# ---------- Excel segédfüggvények ----------
def make_sample_workbook_bytes() -> bytes:
    """Minta Excel fájl több munkalappal, az egyik lapon súlyokkal."""
    df_a = pd.DataFrame({"Név": ["Anna","Bence","Csilla","Dávid","Emese","Feri"]})
    df_b = pd.DataFrame({
        "Név": ["Gabi","Hanna","Ivett","József","Kata","László"],
        "Súly": [1, 2, 1, 3, 1, 1],  # példasúlyok
    })
    df_c = pd.DataFrame({"Név": ["Máté","Nóra","Olívia","Péter","Réka","Sára"]})
    df_d = pd.DataFrame({"Név": ["Tamás","Ubul","Vera","Zita"]})
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_a.to_excel(writer, sheet_name="Osztály A", index=False)
        df_b.to_excel(writer, sheet_name="Osztály B", index=False)
        df_c.to_excel(writer, sheet_name="Osztály C", index=False)
        df_d.to_excel(writer, sheet_name="Osztály D", index=False)
    buf.seek(0)
    return buf.read()

def read_sheet_names(xls_bytes: bytes) -> List[str]:
    xls = pd.ExcelFile(io.BytesIO(xls_bytes))
    return xls.sheet_names

def read_sheet_dataframe(xls_bytes: bytes, sheet_name: str) -> pd.DataFrame:
    """Beolvassa az egész munkalapot; 'Név' oszlop kötelező (ha nincs, az első oszlopot tekinti névnek).
    Opcionális 'Súly' / 'Weight' oszlopot is kezeli."""
    df = pd.read_excel(io.BytesIO(xls_bytes), sheet_name=sheet_name)
    # Név oszlop
    name_candidates = ["Név","Nev","név","name","Name"]
    name_col = next((c for c in name_candidates if c in df.columns), df.columns[0])
    df = df.rename(columns={name_col: "Név"})
    # Súly oszlop
    weight_col = next((c for c in ["Súly","súly","suly","Weight","weight"] if c in df.columns), None)
    if weight_col is not None:
        df = df.rename(columns={weight_col: "Súly"})
        df["Súly"] = pd.to_numeric(df["Súly"], errors="coerce").fillna(1.0).clip(lower=0.0)
    else:
        df["Súly"] = 1.0

    # tisztítás
    df["Név"] = df["Név"].astype(str).str.strip()
    df = df.replace({"Név": {"": pd.NA}}).dropna(subset=["Név"]).drop_duplicates(subset=["Név"]).reset_index(drop=True)
    return df[["Név","Súly"]]

# ---------- Kerék rajzolás/animáció ----------
def draw_wheel(names: List[str], startangle: float = 0.0, highlight_index: Optional[int] = None):
    n = len(names)
    if n == 0:
        st.warning("Nincsenek nevek ezen a munkalapon.")
        return

    sizes = [1] * n  # egyenlő szeletek a megjelenítéshez (a húzás súlyozott lehet külön)
    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, _ = ax.pie(
        sizes,
        labels=names,
        startangle=startangle,
        counterclock=True,
        wedgeprops={"linewidth": 1},
        textprops={"fontsize": 10},
    )

    if highlight_index is not None and 0 <= highlight_index < n:
        wedges[highlight_index].set_linewidth(3)

    # Mutató (felül, 90 foknál)
    ax.annotate("", xy=(0, 1.15), xytext=(0, 0.9), arrowprops=dict(arrowstyle="-|>", lw=2), ha="center")
    ax.set_aspect("equal")
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

def spin_animation(names: List[str], target_index: int, duration_s: float = 3.0, turns: int = 5):
    n = len(names)
    deg = 360.0 / n
    final_startangle = 90.0 - (target_index * deg + deg / 2.0)
    total_rotation = final_startangle + 360.0 * turns

    frames = max(int(duration_s * 30), 30)  # kb. 30 FPS
    sleep_dt = duration_s / frames
    placeholder = st.empty()

    for f in range(frames):
        t = (f + 1) / frames
        ease = 1 - (1 - t) ** 3  # cubic ease-out
        angle = ease * total_rotation
        with placeholder.container():
            draw_wheel(names, startangle=angle)
        time.sleep(sleep_dt)

    with placeholder.container():
        draw_wheel(names, startangle=total_rotation, highlight_index=target_index)

def weighted_choice(names: List[str], weights: List[float]) -> int:
    w = np.array(weights, dtype=float)
    w = np.clip(w, 0, None)
    if w.sum() <= 0:
        return random.randrange(len(names))
    probs = w / w.sum()
    return int(np.random.choice(len(names), p=probs))

# ---------- Oldalsáv: forrás és beállítások ----------
with st.sidebar:
    st.header("Forrásfájl")
    source = st.radio("Válaszd ki a forrást:", ["Feltöltött Excel", "Mintafájl"], index=0, horizontal=True)
    xls_bytes = None

    if source == "Feltöltött Excel":
        uploaded = st.file_uploader("Excel feltöltése (.xlsx)", type=["xlsx"])
        if uploaded is not None:
            xls_bytes = uploaded.read()
        else:
            default_path = "/mnt/data/sample_names.xlsx"
            if os.path.exists(default_path):
                with open(default_path, "rb") as f:
                    xls_bytes = f.read()
                st.caption("Helyi fájl észlelve: /mnt/data/sample_names.xlsx")
            else:
                st.info("Tölts fel egy Excel fájlt, vagy válaszd a Mintafájlt!")
    else:
        xls_bytes = make_sample_workbook_bytes()
        st.caption("Mintafájl betöltve: Osztály A / B / C / D (B lapon 'Súly').")

    st.header("Beállítások")
    remove_winner = st.checkbox("Nyertes eltávolítása ebből a körből", value=True)
    use_weights = st.checkbox("Súlyozott sorsolás (Súly/Weight oszlop)", value=True)
    duration = st.slider("Pörgetés hossza (mp)", min_value=1.0, max_value=8.0, value=3.0, step=0.5)
    turns = st.slider("Teljes körök száma", min_value=3, max_value=10, value=5, step=1)

    st.header("Hang effektek")
    audio_enabled = st.toggle("Hang engedélyezése", value=True)
    audio_spin_loop = st.checkbox("Pörgés közben loop", value=False, help="Rövid 'búgó' hang ismétlése pörgés alatt.")
    audio_win_ding = st.checkbox("Ding a nyertesnél", value=True)

if xls_bytes is None:
    st.stop()

# ---------- Munkalapok ----------
sheet_names = read_sheet_names(xls_bytes)
if len(sheet_names) == 0:
    st.error("A fájl nem tartalmaz munkalapokat.")
    st.stop()

st.subheader("Munkalapok")
chosen = st.session_state.get("chosen_sheet")

cols_per_row = 4
rows = (len(sheet_names) + cols_per_row - 1) // cols_per_row
for r in range(rows):
    cols = st.columns(cols_per_row)
    for c in range(cols_per_row):
        i = r * cols_per_row + c
        if i >= len(sheet_names):
            break
        sheet = sheet_names[i]
        if cols[c].button(sheet, key=f"btn_{sheet}"):
            st.session_state["chosen_sheet"] = sheet
            chosen = sheet

if not chosen and len(sheet_names) > 0:
    chosen = sheet_names[0]
    st.session_state["chosen_sheet"] = chosen

st.success(f"Kiválasztott munkalap: **{chosen}**")

# ---------- Névlista és pörgetés ----------
df_sheet = read_sheet_dataframe(xls_bytes, chosen)
names_all = df_sheet["Név"].tolist()
weights_all = df_sheet["Súly"].tolist()

if "winners_by_sheet" not in st.session_state:
    st.session_state["winners_by_sheet"] = {}
if chosen not in st.session_state["winners_by_sheet"]:
    st.session_state["winners_by_sheet"][chosen] = []
previous_winners = st.session_state["winners_by_sheet"][chosen]

if "log_by_sheet" not in st.session_state:
    st.session_state["log_by_sheet"] = {}
if chosen not in st.session_state["log_by_sheet"]:
    st.session_state["log_by_sheet"][chosen] = []

# Szűrés körön belül
if remove_winner and previous_winners:
    filtered = [(n, w) for n, w in zip(names_all, weights_all) if n not in previous_winners]
    names = [n for n, _ in filtered]
    weights = [w for _, w in filtered]
else:
    names = names_all
    weights = weights_all

if len(names) == 0:
    st.warning("Mindenki nyert ebben a körben. Nyomd meg az **Új kör indítása** gombot az alábbiakban.")
    names = names_all
    weights = weights_all

with st.expander("Névlista (aktuális)", expanded=False):
    st.write(pd.DataFrame({"Név": names, "Súly (aktuális)": weights}))

st.divider()
st.subheader("Pörgetés")

col_spin, col_reset, col_clearlog = st.columns([2,1,1])
with col_spin:
    spin = st.button("🎯 Pörgesd meg a kereket!", type="primary")
with col_reset:
    reset_round = st.button("🔄 Új kör indítása (csak ennél a lapnál)")
with col_clearlog:
    clear_log = st.button("🧹 Napló törlése (csak ennél a lapnál)")

if reset_round:
    st.session_state["winners_by_sheet"][chosen] = []
    st.success("Új kör kezdve: a korábbi nyertesek ismét részt vesznek.")

if clear_log:
    st.session_state["log_by_sheet"][chosen] = []
    st.success("A nyertes napló törölve ennél a munkalapnál.")

# Hang helyfoglalók (így tudjuk külön indítani/megállítani a loop-ot)
audio_spin_placeholder = st.empty()
audio_win_placeholder = st.empty()

if spin:
    if len(names) < 1:
        st.error("Nincs elérhető név a sorsoláshoz.")
    else:
        # Start loop hang
        if audio_enabled and audio_spin_loop:
            with audio_spin_placeholder:
                play_audio_bytes(SPIN_WAV, loop=True)

        # cél index kiválasztása (súlyozás opcionális)
        if use_weights and any(w > 0 for w in weights):
            target_index = weighted_choice(names, weights)
        else:
            target_index = random.randrange(len(names))

        spin_animation(names, target_index=target_index, duration_s=duration, turns=turns)

        # Stop loop (= felülírjuk az üres placeholderrel)
        audio_spin_placeholder.empty()

        winner = names[target_index]
        st.markdown(f"## ✅ Nyertes: **{winner}**")

        if audio_enabled and audio_win_ding:
            with audio_win_placeholder:
                play_audio_bytes(WIN_WAV, loop=False)

        if remove_winner and winner not in st.session_state["winners_by_sheet"][chosen]:
            st.session_state["winners_by_sheet"][chosen].append(winner)

        st.session_state["log_by_sheet"][chosen].append({
            "Időpont": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Munkalap": chosen,
            "Nyertes": winner
        })

# Napló megjelenítés + export
st.divider()
st.subheader("Nyeremény napló")
log_df = pd.DataFrame(st.session_state["log_by_sheet"][chosen], columns=["Időpont","Munkalap","Nyertes"])
if log_df.empty:
    st.info("Még nincs bejegyzés.")
else:
    st.dataframe(log_df, use_container_width=True)
    csv = log_df.to_csv(index=False).encode("utf-8")
    st.download_button("Napló letöltése (CSV)", data=csv, file_name=f"nyertes_naplo_{chosen}.csv", mime="text/csv")
