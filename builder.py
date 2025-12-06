import re
import time
import json
import os
import requests
import concurrent.futures
import shutil
from functools import lru_cache
from bs4 import BeautifulSoup
from urllib.parse import quote
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# CONFIGURAZIONE
# ==========================================
BASE_URL_IMAGES = "https://raw.githubusercontent.com/olivavincenzo/stremio-anime-addon/refs/heads/main/catalog/images/"
IMAGES_DIR = "catalog/images"
OUTPUT_FILE = "catalog/series/animeworld_updated.json"

# Percorso assoluto per evitare dubbi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(BASE_DIR, "catalog", "Roboto-Bold.ttf")

# ==========================================
# 1. PREPARAZIONE AMBIENTE (FONT E CARTELLE)
# ==========================================

def prepare_environment():
    """
    Crea le cartelle necessarie e scarica il font PRIMA di avviare i thread.
    """
    # 1. Crea cartella catalog se non esiste
    catalog_dir = os.path.join(BASE_DIR, "catalog")
    if not os.path.exists(catalog_dir):
        os.makedirs(catalog_dir)
        print(f"Creata cartella: {catalog_dir}")

    # 2. Pulizia Immagini
    if os.path.exists(IMAGES_DIR):
        print(f"Pulizia della cartella immagini: {IMAGES_DIR}...")
        for filename in os.listdir(IMAGES_DIR):
            file_path = os.path.join(IMAGES_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                pass
    else:
        os.makedirs(IMAGES_DIR)

    # 3. Download Font (Sincrono, bloccante)
    if not os.path.exists(FONT_PATH) or os.path.getsize(FONT_PATH) == 0:
        print("Scaricamento font Roboto-Bold...")
        font_url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
        try:
            r = requests.get(font_url, allow_redirects=True)
            with open(FONT_PATH, 'wb') as f:
                f.write(r.content)
            print("Font scaricato con successo.")
        except Exception as e:
            print(f"ERRORE CRITICO download font: {e}")

# ==========================================
# 2. FUNZIONI DI UTILITÀ
# ==========================================

def convert_roman_to_arabic(title):
    if not title: return ""
    roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5', 'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10'}
    pattern = r'\b(' + '|'.join(roman_map.keys()) + r')\b'
    def replace(match): return roman_map[match.group(0)]
    return re.sub(pattern, replace, title).strip()

# ==========================================
# 3. GESTIONE IMMAGINI (Pillow)
# ==========================================

def add_episode_badge(image_url, episode_text, file_name):
    try:
        local_path = os.path.join(IMAGES_DIR, file_name)
        
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200:
            return image_url 

        img = Image.open(BytesIO(response.content)).convert("RGBA")
        width, height = img.size
        
        # --- CARICAMENTO FONT ---
        # Impostiamo la grandezza al 25% dell'altezza (molto grande)
        font_size = int(height * 0.05) 
        
        font = None
        try:
            font = ImageFont.truetype(FONT_PATH, font_size)
        except Exception as e:
            print(f"Errore caricamento font {FONT_PATH}: {e}")
            font = ImageFont.load_default() # Fallback solo se proprio il file è rotto

        text = episode_text
        # text = f"EP {episode_text}" # Decommenta se vuoi "EP 12"
        
        draw = ImageDraw.Draw(img)
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_w = right - left
        text_h = bottom - top
        
        # Padding
        padding_x = 25
        padding_y = 15
        margin_right = 15
        margin_bottom = 15

        x2 = width - margin_right
        y2 = height - margin_bottom
        x1 = x2 - text_w - (padding_x * 2)
        y1 = y2 - text_h - (padding_y * 2)

        # Sfondo nero
        overlay = Image.new('RGBA', img.size, (0,0,0,0))
        draw_overlay = ImageDraw.Draw(overlay)
        # Raggio della curvatura (più alto = più tondo)
        radius = 20 

        # Usa rounded_rectangle invece di rectangle
        draw_overlay.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=(0, 0, 0, 200))
        
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)
        
        # Testo bianco centrato
        text_x = x1 + padding_x
        text_y = y1 + padding_y - (top * 0.15)
        
        draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))

        img.convert("RGB").save(local_path, "JPEG", quality=95)

        return f"{BASE_URL_IMAGES}{file_name}"

    except Exception as e:
        print(f"Errore immagine {file_name}: {e}")
        return image_url

# ==========================================
# 4. GESTIONE API KITSU
# ==========================================

def search_kitsu_id(query):
    if not query: return None, None
    url = f"https://kitsu.io/api/edge/anime?filter[text]={quote(query)}"
    headers = {"Accept": "application/vnd.api+json", "Content-Type": "application/vnd.api+json"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data['data']:
                anime = data['data'][0]
                kitsu_id = f"kitsu:{anime['id']}"
                attr = anime.get('attributes', {})
                poster_img = attr.get('posterImage', {})
                poster_url = poster_img.get('medium') or poster_img.get('original')
                return kitsu_id, poster_url
    except Exception as e:
        pass
    return None, None

@lru_cache(maxsize=128)
def cached_kitsu_search(title):
    return search_kitsu_id(title)

# ==========================================
# 5. ELABORAZIONE WORKER
# ==========================================

def process_single_item(item):
    try:
        title_tag = item.select_one('.name')
        if not title_tag: return None
        
        english_title = title_tag.get_text(strip=True)
        japanese_title = title_tag.get("data-jtitle")
        ep_tag = item.select_one('.ep')
        episode = ep_tag.get_text(strip=True) if ep_tag else "?"
        img_tag = item.select_one('img')
        original_poster = img_tag['src'] if img_tag else ""

        raw_primary = japanese_title if japanese_title else english_title
        search_title = convert_roman_to_arabic(raw_primary)

        kitsu_id, kitsu_poster = cached_kitsu_search(search_title)

        if not kitsu_id and search_title != raw_primary:
            kitsu_id, kitsu_poster = cached_kitsu_search(raw_primary)

        if not kitsu_id and japanese_title and english_title:
            english_converted = convert_roman_to_arabic(english_title)
            if english_converted != search_title:
                kitsu_id, kitsu_poster = cached_kitsu_search(english_converted)

        if not kitsu_id: return None

        base_poster = kitsu_poster if kitsu_poster else original_poster
        
        episode_text = episode.replace(" ", "_")
        image_filename = f"{kitsu_id.replace(':', '_')}_{episode_text}.jpg"
        
        final_poster_url = add_episode_badge(base_poster, episode, image_filename)

        return {
            "id": kitsu_id,
            "type": "series",
            "name": raw_primary,
            "poster": final_poster_url,
            "description": f"Nuovo episodio: {episode}",
            "posterShape": "poster"
        }
    except Exception:
        return None

# ==========================================
# 6. FUNZIONE PRINCIPALE
# ==========================================

def update_animeworld_catalog():
    UPDATED_URL = "https://www.animeworld.so/updated"
    
    # --- STEP CRUCIALE: PREPARAZIONE SINCROMA ---
    prepare_environment()
    
    scraper = requests.Session()
    scraper.headers.update({'User-Agent': 'Mozilla/5.0'})

    try:
        print("Scaricando la pagina aggiornamenti...")
        response = scraper.get(UPDATED_URL)
        if response.status_code != 200:
            print(f"Errore connessione: {response.status_code}")
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('.film-list .item')
        unique_metas = {}
        
        print(f"Trovati {len(items)} anime. Inizio elaborazione...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            results = executor.map(process_single_item, items)

        for res in results:
            if res and res['id'] not in unique_metas:
                unique_metas[res['id']] = res

        metas_list = list(unique_metas.values())
        
        output_dir = os.path.dirname(OUTPUT_FILE)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        json_output = {"metas": metas_list}

        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, ensure_ascii=False, indent=4)

        print(f"SUCCESSO! Salvati {len(metas_list)} elementi.")
        return metas_list

    except Exception as e:
        print(f"Errore critico: {e}")
        return []

if __name__ == "__main__":
    update_animeworld_catalog()