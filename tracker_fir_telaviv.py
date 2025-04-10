import pandas as pd
from shapely.geometry import Point, Polygon
import folium
import os
import time
from datetime import datetime, timezone
import logging
import requests
from email.message import EmailMessage
import smtplib
import math

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# === CONFIGURATION ===
os.makedirs("data_israel", exist_ok=True)

CONFIG = {
    "pause_seconds": 120,
}

EMAIL_SENDER = "surveillance.irak@gmail.com"
EMAIL_PASSWORD = "hwlw yhfj orih leqr"
EMAIL_RECEIVER = "surveillance.irak@gmail.com"

# === LISTE DES VOLS À SURVEILLER ===
WATCHED_CALLSIGNS = [
    "AFR966", "AFR963", "AFR564", "AFR565",
    "DLH686", "DLH690", "DLH687", "DLH691", "DLH8351", "DLH681", "DLH683", "DLH8290", "DLH8350", "DLH680", "DLH682",
    "BAW404", "BAW405",
    "SWR252B", "SWR253", "ELY011", "ELY222", "MEA262", "MEA305", "MEA307", "MEA212", "MEA230", "MEA218", "MEA252", "MEA403", 
    "MEA321", "MEA323", "MEA214" , "MEA202", "MEA204" ,"MEA261", "MEA304", "MEA306", "MEA211", "MEA229", "MEA217", "MEA251", "MEA402",
    "MEA404", "MEA201", "MEA203", "ELY322", "ELY224", "ELY320", "ELY324", "ELY326", "ELY328", "ELY321", "ELY223", "ELY221", "ELY319", "ELY323",
    "ELY327", "ELY325"

]

# === ÉQUIVALENCE IATA → ICAO ===
prefix_mapping = {
    "AF": "AFR",
    "LH": "DLH",
    "BA": "BAW",
    "LX": "SWR",
    "LY": "ELY",
    "ME": "MEA"
}

def normalize_callsign(callsign):
    callsign = callsign.replace(" ", "").upper()
    for short, full in prefix_mapping.items():
        if callsign.startswith(short) and full + callsign[len(short):] in WATCHED_CALLSIGNS:
            return full + callsign[len(short):]
    return callsign

# === POLYGONE FIR ISRAËL / LIBAN ===
FIR_ISRAEL_POLYGON = [
    (29.497947360303073, 34.908275156555334), (31.329339969530665, 34.21029232109166),
    (31.589425393121473, 34.49072634540431), (31.941503679570886, 34.70830143972506),
    (32.407662626316295, 34.86889040267292), (32.832098274924775, 34.95898469078031),
    (32.80534795225661, 35.02976129808468), (32.89820828718409, 35.08499128329095),
    (33.11633622431158, 35.11017639210564), (33.89469885466238, 35.477228929423035),
    (33.97481232004101, 35.640242505346464), (34.16384450844703, 35.63354392435795),
    (34.45060453318487, 35.81360332859384), (34.53582087990101, 35.99181517063113),
    (34.647970885362014, 35.98338458549688), (34.63533472514111, 36.45464286637119),
    (34.50155447983009, 36.332752308772), (34.50157134832996, 36.43621800908463),
    (34.210287180919465, 36.614254701912415), (34.04072878028593, 36.4804417133731),
    (34.06037427475475, 36.41248533984168), (33.913324049795264, 36.27071188120212),
    (33.853336869797474, 36.38716438201038), (33.81916676830849, 36.38271224285734),
    (33.81485224403829, 36.06755999175235), (33.6409668597107, 35.9408903716712),
    (33.58065705743239, 36.056989815843), (33.522434307886, 36.01832269359028),
    (33.51875716539536, 35.94550403158806), (33.46863669975288, 35.95027840716412),
    (33.33186017517281, 35.791603708095806), (33.238350365084756, 35.62268474841963),
    (33.28530541438188, 35.56949380529451), (31.76427808144338, 35.5692469481142),
    (31.242125340800044, 35.39618915868624), (31.150855011741584, 35.449423272509904),
    (29.543104601511573, 34.978934170293), (29.49676762753704, 34.90813906153173)
]

israel_polygon = Polygon([(lon, lat) for lat, lon in FIR_ISRAEL_POLYGON])
buffer_polygon = israel_polygon.buffer(200 / 111)
# === EXTENSION PERSONNALISÉE DE LA ZONE ===
EXTENDED_AREA_COORDS = [
    (31.339812351430325, 34.20634481895593),
    (33.58318872508595, 28.535817148342147),
    (36.753542633847744, 30.60478325597461),
    (34.63987835805429, 35.99056253743524),
    (31.339812351430325, 34.20634481895593)
]
custom_extension = Polygon([(lon, lat) for lat, lon in EXTENDED_AREA_COORDS])

# Nouvelle zone tampon élargie
full_buffer = buffer_polygon.union(custom_extension)
recent_positions = {}
tracked_flights = {}
log_folder = "logs_israel_alerts"
os.makedirs(log_folder, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def send_email_alert(subject, content):
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg.set_content(content)
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
            smtp.send_message(msg)
        logging.info("📧 Mail envoyé avec succès.")
    except Exception as e:
        logging.error(f"❌ Erreur envoi mail : {e}")

def calculate_bearing(coord1, coord2):
    lat1, lon1 = map(math.radians, coord1)
    lat2, lon2 = map(math.radians, coord2)
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360

def detect_activity():
    url = "https://opensky-network.org/api/states/all"
    now = datetime.now(timezone.utc)

    try:
        response = requests.get(url, timeout=10, verify=False)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logging.error(f"API error: {e}")
        return

    positions_today = []

    for state in data.get("states", []):
        raw_callsign = (state[1] or "").strip().replace(" ", "")
        lat, lon = state[6], state[5]
        baro_alt = state[7]
        velocity = state[9]
        on_ground = state[8]

        if None in (lat, lon):
            continue

        callsign = normalize_callsign(raw_callsign)
        if callsign not in WATCHED_CALLSIGNS:
            continue

        point = Point(lon, lat)
        inside = israel_polygon.contains(point)
        near = full_buffer.contains(point)

        flight = tracked_flights.setdefault(callsign, {
            "entered_buffer": False,
            "entered_fir": False,
            "exited_buffer": False,
            "landed": False,
            "departed": False,
            "appeared_on_ground_in_fir": False,
            "turn_alert_sent": False,
            "positions": [],
            "last_turn_check": None
        })

        flight["positions"].append((lat, lon, now))
        if len(flight["positions"]) > 5:
            flight["positions"] = flight["positions"][-5:]

        if flight["landed"]:
            continue  # ne plus rien enregistrer après atterrissage

        # 1. Apparition au sol dans la FIR
        if not flight["entered_buffer"] and on_ground and inside and not flight["appeared_on_ground_in_fir"]:
            flight["appeared_on_ground_in_fir"] = True
            message = f"✅ {callsign} est apparu au sol dans la FIR"
            logging.info(message)
            with open("data_israel/log_messages.txt", "a", encoding="utf-8") as log:
                log.write(f"{now.isoformat()} - {message}\n")

        # 2. Entrée dans la zone tampon
        if not flight["entered_buffer"] and near and not flight["appeared_on_ground_in_fir"]:
            flight["entered_buffer"] = True
            message = f"✅ {callsign} est entré dans la zone tampon"
            logging.info(message)
            with open("data_israel/log_messages.txt", "a", encoding="utf-8") as log:
                log.write(f"{now.isoformat()} - {message}\n")

        # 3. Entrée dans la FIR après tampon
        if flight["entered_buffer"] and inside and not flight["entered_fir"]:
            flight["entered_fir"] = True
            message = f"✅ {callsign} est entré dans la FIR"
            logging.info(message)
            with open("data_israel/log_messages.txt", "a", encoding="utf-8") as log:
                log.write(f"{now.isoformat()} - {message}\n")

        # 4. Atterrissage
        if inside and flight["entered_fir"] and not flight["landed"] and not flight["appeared_on_ground_in_fir"]:
            if velocity is not None and velocity < 100 and baro_alt is not None and baro_alt < 1500:
                flight["landed"] = True
                message = f"🛬 {callsign} a atterri en Israël ou Liban"
                logging.info(message)
                with open("data_israel/log_messages.txt", "a", encoding="utf-8") as log:
                    log.write(f"{now.isoformat()} - {message}\n")
                continue

        # 5. Décollage après apparition au sol
        if flight["appeared_on_ground_in_fir"] and not inside and not flight["departed"]:
            if baro_alt and baro_alt > 1500 and velocity and velocity > 150:
                flight["departed"] = True
                message = f"🛫 {callsign} a décollé depuis Israël / Liban"
                logging.info(message)
                with open("data_israel/log_messages.txt", "a", encoding="utf-8") as log:
                    log.write(f"{now.isoformat()} - {message}\n")

        # 6. QRF / demi-tour détecté
        if flight["entered_buffer"] and not flight["turn_alert_sent"]:
            if flight["last_turn_check"] is None or (now - flight["last_turn_check"]).total_seconds() > 600:
                recent_positions = [pos for pos in flight["positions"] if (now - pos[2]).total_seconds() <= 600]
                if len(recent_positions) >= 3:
                    b1 = calculate_bearing(recent_positions[-3][:2], recent_positions[-2][:2])
                    b2 = calculate_bearing(recent_positions[-2][:2], recent_positions[-1][:2])
                    delta = abs(b2 - b1)
                    delta = min(delta, 360 - delta)

                    if delta > 180:
                        flight["turn_alert_sent"] = True
                        flight["last_turn_check"] = now
                        message = f"🚨 DEMI-TOUR détecté pour {callsign}"
                        logging.warning(message)
                        with open("data_israel/log_messages.txt", "a", encoding="utf-8") as log:
                            log.write(f"{now.isoformat()} - {message}\n")
                        send_email_alert(
                            f"🚨 Demi-tour - {callsign} (Zone ISR/LBN)",
                            f"🚨 DEMI-TOUR détecté !\nVol : {callsign}\nChangement de cap : {int(delta)}°\nHeure UTC : {now.strftime('%Y-%m-%d %H:%M:%S')}"
                        )

        # 7. Sortie de la zone tampon
        if flight["entered_buffer"] and not near and not flight["exited_buffer"] and not flight["landed"]:
            flight["exited_buffer"] = True
            message = f"🚪 {callsign} a quitté la zone tampon"
            logging.info(message)
            with open("data_israel/log_messages.txt", "a", encoding="utf-8") as log:
                log.write(f"{now.isoformat()} - {message}\n")


        positions_today.append({"callsign": callsign, "lat": lat, "lon": lon})

    if positions_today:
        pd.DataFrame(positions_today).to_csv("data_israel/positions_actuelles.csv", index=False)

    with open("data_israel/last_update.txt", "w", encoding="utf-8") as f:
        f.write(now.isoformat())


def enregistrer_tableau():
    import csv
    from datetime import date

    today = date.today().isoformat()
    filename_daily = "data_israel/vols_detectes.csv"
    filename_archive = f"data_israel/historique_vols_{today}.csv"

    headers = ["Vol", "Entré tampon", "Entré FIR", "Atterri", "Demi-tour", "Décollé"]

    rows = []
    for vol, info in tracked_flights.items():
        row = [
            vol,
            "Oui" if info.get("entered_buffer") else "Non",
            "Oui" if info.get("entered_fir") else "Non",
            "Oui" if info.get("landed") else "Non",
            "Oui" if info.get("turn_alert_sent") else "Non",
            "Oui" if info.get("departed") else "Non"
        ]
        rows.append(row)

    # Sauvegarde actuelle
    with open(filename_daily, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    # Archive quotidienne (une fois par jour)
    if not os.path.exists(filename_archive):
        with open(filename_archive, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerows(rows)


def generer_carte_fir():
    m = folium.Map(location=[32.0, 35.0], zoom_start=6)

    # Polygone FIR
    folium.Polygon(
        locations=FIR_ISRAEL_POLYGON,
        color='green', weight=2, fill=True, fill_opacity=0.1,
        popup="Zone FIR Israël / Liban"
    ).add_to(m)

    # Zone tampon + extension fusionnée
    folium.GeoJson(
        data=full_buffer.__geo_interface__,
        name="Buffer zone étendue",
        style_function=lambda x: {
            'fillColor': 'blue',
            'color': 'blue',
            'weight': 1,
            'fillOpacity': 0.1
        }
    ).add_to(m)

    # Zone personnalisée rouge (facultatif / debug visuel)
    from shapely.geometry import mapping
    folium.GeoJson(
        data=mapping(custom_extension),
        name="Zone personnalisée",
        style_function=lambda x: {
            'fillColor': 'red',
            'color': 'red',
            'weight': 2,
            'fillOpacity': 0.3
        }
    ).add_to(m)

    folium.LayerControl().add_to(m)
    m.save("data_israel/map_fir.html")
    logging.info("🗺️ Carte de la zone Israël / Liban générée.")

if __name__ == "__main__":
    logging.info("📡 Surveillance Israël / Liban démarrée")
    generer_carte_fir()
    try:
        while True:
            detect_activity()
            enregistrer_tableau()
            logging.info("⏳ Pause...")
            time.sleep(CONFIG["pause_seconds"])

    except KeyboardInterrupt:
        logging.info("🛑 Surveillance interrompue par l'utilisateur.")
        if os.path.exists("data_israel/surveillance_started.flag"):
            os.remove("data_israel/surveillance_started.flag")

# Rendre accessible à Streamlit (pas indenté !)
FIR_ISRAEL_POLYGON = FIR_ISRAEL_POLYGON
full_buffer = full_buffer
generer_carte_fir = generer_carte_fir
send_email_alert = send_email_alert









