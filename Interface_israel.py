import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime
from datetime import date
import os
import subprocess
from streamlit_autorefresh import st_autorefresh
import folium
from shapely.geometry import Point

# === IMPORT ZONE POLYGON ===
from tracker_fir_telaviv import FIR_ISRAEL_POLYGON, full_buffer, generer_carte_fir, send_email_alert

# === CONFIG PAGE ===
st.set_page_config(page_title="Surveillance Israël / Liban", layout="wide")
st_autorefresh(interval=2 * 60 * 1000, key="auto_refresh") 

# === LANCEMENT AUTOMATIQUE DU SCRIPT PRINCIPAL ===
flag_path = "data_israel/surveillance_started.flag"
script_path = "tracker_fir_telaviv.py"

import psutil

def is_script_running(script_name):
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline')
            if cmdline and isinstance(cmdline, list) and script_name in ' '.join(cmdline):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False

# Crée le flag si nécessaire
if not os.path.exists(flag_path):
    os.makedirs("data_israel", exist_ok=True)
    with open(flag_path, "w") as f:
        f.write("surveillance lancée")

# Lancement du script UNIQUEMENT s'il n'est pas déjà actif
if not is_script_running("tracker_fir_telaviv.py"):
    try:
        python_path = r"C:\Users\M445657\OneDrive - Air France KLM\Documents\Communication CCO\Projet couloir Irakien\.venv\Scripts\python.exe"
        subprocess.Popen([python_path, script_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
    except Exception as e:
        st.error(f"Erreur lancement script : {e}")
else:
    st.info("⏳ Le script de surveillance est déjà en cours.")


# === DERNIER UPDATE ===
def get_last_update():
    try:
        with open("data_israel/last_update.txt", "r") as f:
            dt = datetime.fromisoformat(f.read().strip())
            return dt.strftime("%d/%m/%Y %H:%M:%S")
    except:
        return "Non disponible"

# === TITRE ===
st.markdown("## 🛡️ Surveillance Zone Israël / Liban")
st.caption(f"🕓 Dernière mise à jour : {get_last_update()} UTC")

# === MISE EN PAGE ===
left_col, right_col = st.columns([2, 1])  # Carte | Messages

# === 🗺️ CARTE À GAUCHE ===
with left_col:
    st.markdown("### 🗺️ Carte des avions détectés")

    # Carte dynamique
    m = folium.Map(location=[32.0, 35.0], zoom_start=6)

    # Polygone FIR
    folium.Polygon(
        locations=FIR_ISRAEL_POLYGON,
        color='green', weight=2, fill=True, fill_opacity=0.1,
        popup="Zone Israël / Liban"
    ).add_to(m)

    # Zone tampon + extension fusionnée
    folium.GeoJson(
        data=full_buffer.__geo_interface__,
        name="Buffer zone",
        style_function=lambda x: {
            'fillColor': 'blue', 'color': 'blue', 'weight': 1, 'fillOpacity': 0.1
        }
    ).add_to(m)

    # Marqueurs avions
    try:
        df = pd.read_csv("data_israel/positions_actuelles.csv")
        for _, row in df.iterrows():
            point = Point(row["lon"], row["lat"])
            if full_buffer.contains(point):
                folium.Marker(
                    location=[row["lat"], row["lon"]],
                    popup=row["callsign"],
                    icon=folium.Icon(color="blue", icon="plane", prefix="fa")
                ).add_to(m)
    except FileNotFoundError:
        pass  # Aucun avion encore

    map_path = "data_israel/map_fir.html"
    m.save(map_path)

    if Path(map_path).exists():
        with open(map_path, "r", encoding="utf-8") as f:
            map_html = f.read()
        st.components.v1.html(map_html, height=450, scrolling=False)
    else:
        st.warning("Carte non disponible.")



# === 📰 JOURNAL D'ÉVÉNEMENTS À DROITE ===
with right_col:
    st.markdown("### 📢 Actualité Zone ISR-LBN")

    # 🔁 Nouveau bloc de nettoyage automatique
    from datetime import date
    log_path = "data_israel/log_messages.txt"
    log_reset_path = "data_israel/log_last_reset.txt"
    today_str = date.today().isoformat()

    if not os.path.exists(log_reset_path):
        with open(log_reset_path, "w") as f:
            f.write("")

    try:
        with open(log_reset_path, "r") as f:
            last_reset = f.read().strip()
    except:
        last_reset = ""

    if last_reset != today_str:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("")
        with open(log_reset_path, "w") as f:
            f.write(today_str)

    # 💬 Lecture des logs après nettoyage éventuel
    if Path(log_path).exists():
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-7:]
        for line in reversed(lines):
            emoji = "🔊"
            if "entré dans la zone" in line:
                emoji = "✅"
            elif "a quitté la zone" in line:
                emoji = "🚪"
            elif "atterri" in line:
                emoji = "🛬"
            elif "DEMI-TOUR" in line:
                emoji = "🚨"
            st.markdown(f"- {emoji} {line.strip()}")
    else:
        st.info("Aucun événement pour le moment.")


# === 📊 TABLEAU DES VOLS EN BAS ===
st.markdown("### 📊 Vols détectés aujourd'hui")
csv_path = "data_israel/vols_detectes.csv"
if Path(csv_path).exists():
    df = pd.read_csv(csv_path)

    # Extraire le code compagnie à partir des 3 premières lettres du callsign
    df["Compagnie"] = df["Vol"].str[:3]

    # Création du filtre multi-sélection
    compagnies = sorted(df["Compagnie"].unique())
    choix = st.multiselect("Filtrer par compagnie :", options=compagnies, default=compagnies)

    # Filtrage du tableau
    df_filtré = df[df["Compagnie"].isin(choix)]
    st.dataframe(df_filtré.drop(columns="Compagnie"), use_container_width=True)
else:
    st.info("Aucun vol détecté.")

# === 🔁 BOUTON DE TEST MANUEL ===
#st.markdown("### 🧪 Test manuel d’alerte")
#if st.button("🚨 Simuler une alerte DEMI-TOUR"):
    #test_callsign = "TEST999"
    #test_message = (
        #f"🚨 DEMO : Alerte DEMI-TOUR manuelle\n"
        #f"Vol : {test_callsign}\n"
        #f"Zone : Israël / Liban\n"
        #f"Changement de cap simulé : 180°\n"
        #f"Heure UTC : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
    #)
    #send_email_alert(f"🚨 DEMO - Demi-tour {test_callsign} (Zone ISR/LBN)", test_message)
    #st.success("✅ E-mail de test envoyé avec succès.")
