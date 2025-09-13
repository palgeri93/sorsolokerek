
import io
import time
import random
from typing import List

import numpy as np
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

st.set_page_config(page_title="Sorsolókerék – Excel munkalapokkal", layout="centered")
st.title("🎡 Sorsolókerék – Excelből, munkalapok szerint")

st.write(
    "Tölts fel egy **.xlsx** fájlt több munkalappal. "
    "Az app a munkalapok neveiből **gombokat** készít; a megnyomott gombnak megfelelő listából sorsol."
)

# ---------- Segédfüggvények ----------
def make_sample_workbook_bytes() -> bytes:
    """Minta Excel fájl több munkalappal."""
    df_a = pd.DataFrame({"Név": ["Anna","Bence","Csilla","Dávid","Emese","Feri"]})
    df_b = pd.DataFrame({"Név": ["Gabi","Hanna","Ivett","József","Kata","László"]})
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

def read_sheet_names(xls_bytes: bytes):
    xls = pd.ExcelFile(io.BytesIO(xls_bytes))
    return xls.sheet_names

def read_names_from_sheet(xls_bytes: bytes, sheet_name: str):
    """Első nem üres oszlopot névlistának veszi."""
    df = pd.read_excel(io.BytesIO(xls_bytes), sheet_name=sheet_name)
    # Keressünk tipikus fejlécet, ha nincs, első oszlop
    candidates = ["Név","Nev","név","name","Name"]
    col = None
    for c in candidates:
        if c in df.columns:
            col = c
            break
    if col is None:
        col = df.columns[0]
    names = (
        df[col]
        .astype(str)
        .str.strip()
        .replace({"": pd.NA})
        .dropna()
        .drop_duplicates()
        .tolist()
    )
    return names

def draw_wheel(names, startangle: float = 0.0, highlight_index: int | None = None):
    """Egyszerű kerék matplotlib-pitével; highlight a nyertesre vastagabb élszegély."""
    n = len(names)
    if n == 0:
        st.warning("Nincsenek nevek ezen a munkalapon.")
        return

    sizes = [1] * n  # egyenlő szeletek
    fig, ax = plt.subplots(figsize=(6, 6))
    wedges, texts = ax.pie(
        sizes,
        labels=names,
        startangle=startangle,
        counterclock=True,
        wedgeprops={"linewidth": 1},
        textprops={"fontsize": 10},
    )

    # Kiemelés a nyertesnek
    if highlight_index is not None and 0 <= highlight_index < n:
        wedges[highlight_index].set_linewidth(3)

    # Mutató (felül, 90 foknál)
    ax.annotate(
        "",
        xy=(0, 1.15),
        xytext=(0, 0.9),
        arrowprops=dict(arrowstyle="-|>", lw=2),
        ha="center",
    )
    ax.set_aspect("equal")
    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

def spin_animation(names, target_index: int, duration_s: float = 3.0, turns: int = 5):
    """Valódi animáció: frame-enként újrarajzoljuk és sleep-eljük a UI frissüléséhez."""
    n = len(names)
    deg = 360.0 / n
    # Végső startangle, hogy a target közepe felül legyen (90°)
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

    # végállapot + highlight
    with placeholder.container():
        draw_wheel(names, startangle=total_rotation, highlight_index=target_index)

# ---------- Oldalsáv: fájl és opciók ----------
with st.sidebar:
    st.header("Beállítások")
    use_sample = st.toggle("Használj mintafájlt", value=True, help="Gyors kipróbáláshoz")
    uploaded = None
    xls_bytes = None

    if use_sample:
        xls_bytes = make_sample_workbook_bytes()
        st.caption("Mintafájl betöltve: Osztály A / B / C / D lapok.")
    else:
        uploaded = st.file_uploader("Excel feltöltése (.xlsx)", type=["xlsx"])
        if uploaded is not None:
            xls_bytes = uploaded.read()

    remove_winner = st.checkbox("Nyertes eltávolítása a listából", value=False, help="Sorsolás után törli a nevet ebből a munkalapból.")
    duration = st.slider("Pörgetés hossza (mp)", min_value=1.0, max_value=8.0, value=3.0, step=0.5)
    turns = st.slider("Teljes körök száma", min_value=3, max_value=10, value=5, step=1)

if xls_bytes is None:
    st.info("Kezdéshez tölts fel egy Excel fájlt, vagy kapcsold be a mintafájlt az oldalsávban.")
    st.stop()

# ---------- Munkalap-gombok (legalább 4 gomb) ----------
sheet_names = read_sheet_names(xls_bytes)
if len(sheet_names) == 0:
    st.error("A fájl nem tartalmaz munkalapokat.")
    st.stop()

st.subheader("Munkalapok")
min_buttons = 4
display_count = max(min_buttons, len(sheet_names))
cols_per_row = 4
rows = (display_count + cols_per_row - 1) // cols_per_row
chosen = st.session_state.get("chosen_sheet")

idx = 0
for r in range(rows):
    cols = st.columns(cols_per_row)
    for c in range(cols_per_row):
        if idx >= display_count:
            break
        if idx < len(sheet_names):
            sheet = sheet_names[idx]
            if cols[c].button(sheet, key=f"btn_{sheet}"):
                st.session_state["chosen_sheet"] = sheet
                chosen = sheet
        else:
            # Kitöltő, letiltott gomb, hogy legalább 4 legyen
            cols[c].button("—", key=f"btn_dummy_{idx}", disabled=True)
        idx += 1

if not chosen and len(sheet_names) > 0:
    st.info("Válassz egy munkalapot a fenti gombokkal!")
    st.stop()

st.success(f"Kiválasztott munkalap: **{chosen}**")

# ---------- Névlista és pörgetés ----------
names = read_names_from_sheet(xls_bytes, chosen)
if "names_by_sheet" not in st.session_state:
    st.session_state["names_by_sheet"] = {}
st.session_state["names_by_sheet"][chosen] = names

if len(names) == 0:
    st.warning("Ezen a munkalapon nem található név.")
    st.stop()

with st.expander("Névlista", expanded=False):
    st.write(pd.DataFrame({"Név": names}))

st.divider()
st.subheader("Pörgetés")

if st.button("🎯 Pörgesd meg a kereket!", type="primary"):
    # Cél index
    target_index = random.randrange(len(names))
    spin_animation(names, target_index=target_index, duration_s=duration, turns=turns)
    winner = names[target_index]
    st.markdown(f"## ✅ Nyertes: **{winner}**")

    if remove_winner:
        # Frissítsük a session-ben tárolt listát
        updated = [n for n in names if n != winner]
        st.session_state["names_by_sheet"][chosen] = updated

        # Írjunk vissza egy "munkamenet Excel"-t letöltéshez (opcionális)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            for sheet in sheet_names:
                data = st.session_state["names_by_sheet"].get(sheet, read_names_from_sheet(xls_bytes, sheet))
                pd.DataFrame({"Név": data}).to_excel(writer, sheet_name=sheet, index=False)
        buf.seek(0)
        st.download_button(
            "Frissített Excel letöltése",
            data=buf.read(),
            file_name="nevek_frissitve.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    # Statikus kerék megjelenítés elsőre
    draw_wheel(names, startangle=0.0)
