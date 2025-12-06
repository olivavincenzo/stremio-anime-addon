import re
import time
import json
import os
import requests
import concurrent.futures
from functools import lru_cache
from bs4 import BeautifulSoup
from urllib.parse import quote
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont  # <--- NUOVI IMPORT

# ==========================================
# CONFIGURAZIONE
# ==========================================
# L'URL base dove saranno ospitate le tue immagini generate.
# Se stai testando in locale con un server python (python -m http.server), potrebbe essere:
# "http://127.0.0.1:8000/catalog/images/"
# Se carichi su un server, metti il dominio corretto.
BASE_URL_IMAGES = "http://tuo-dominio.com/catalog/images/" 
IMAGES_DIR = "catalog/images"

# ==========================================
# 1. FUNZIONI DI UTILITÀ
# ==========================================

def convert_roman_to_arabic(title):
    if not title: return ""
    roman_map = {'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5', 'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10'}
    pattern = r'\b(' + '|'.join(roman_map.keys()) + r')\b'
    def replace(match): return roman_map[match.group(0)]
    return re.sub(pattern, replace, title).strip()

# ==========================================
# 2. GESTIONE IMMAGINI (Pillow)
# ==========================================

def add_episode_badge(image_url, episode_text, file_name):
    """
    Scarica l'immagine, aggiunge l'episodio in basso a destra e la salva.
    Restituisce l'URL pubblico della nuova immagine.
    """
    try:
        # Assicuriamoci che la cartella esista
        if not os.path.exists(IMAGES_DIR):
            os.makedirs(IMAGES_DIR)

        local_path = os.path.join(IMAGES_DIR, file_name)
        
        # Se l'immagine esiste già (cache semplice), non la ricreiamo per risparmiare tempo
        # (Rimuovi questo check se vuoi aggiornare sempre l'immagine)
        if os.path.exists(local_path):
             return f"{BASE_URL_IMAGES}{file_name}"

        # Scarica l'immagine originale
        response = requests.get(image_url, timeout=5)
        if response.status_code != 200:
            return image_url # Fallback all'originale se fallisce il download

        img = Image.open(BytesIO(response.content)).convert("RGBA")
        width, height = img.size
        draw = ImageDraw.Draw(img)

        # --- Configurazione Font ---
        # Cerchiamo di usare un font standard, altrimenti quello di default (che è piccolo)
        try:
            # Prova Arial su Windows o DejaVuSans su Linux
            font_size = int(height * 0.10) # Il testo è il 10% dell'altezza immagine
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            try:
                font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
            except IOError:
                font = ImageFont.load_default()

        text = f"EP {episode_text}"
        
        # Calcola dimensioni del testo usando getbbox
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        text_w = right - left
        text_h = bottom - top
        
        # Margini
        padding_x = 10
        padding_y = 5
        margin_right = 10
        margin_bottom = 10

        # Coordinate del box di sfondo (In basso a destra)
        x2 = width - margin_right
        y2 = height - margin_bottom
        x1 = x2 - text_w - (padding_x * 2)
        y1 = y2 - text_h - (padding_y * 2)

        # Disegna sfondo semi-trasparente scuro
        # ImageDraw non supporta alpha diretta su RGB, usiamo un layer separato
        overlay = Image.new('RGBA', img.size, (0,0,0,0))
        draw_overlay = ImageDraw.Draw(overlay)
        draw_overlay.rectangle([x1, y1, x2, y2], fill=(0, 0, 0, 200)) # Nero con opacità
        
        # Unisci overlay
        img = Image.alpha_composite(img, overlay)
        
        # Disegna il testo (Bianco)
        draw = ImageDraw.Draw(img)
        # Centrare il testo nel rettangolo
        text_x = x1 + padding_x
        text_y = y1 + padding_y - (top * 0.2) # Aggiustamento fine per l'altezza
        
        draw.text((text_x, text_y), text, font=font, fill=(255, 255, 255, 255))

        # Salva l'immagine come JPG (convertendo da RGBA a RGB)
        img.convert("RGB").save(local_path, "JPEG", quality=85)

        return f"{BASE_URL_IMAGES}{file_name}"

    except Exception as e:
        print(f"Errore generazione immagine per {file_name}: {e}")
        return image_url # Fallback all'originale

# ==========================================
# 3. GESTIONE API KITSU
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
        print(f"Errore Kitsu: {e}")
    return None, None

@lru_cache(maxsize=128)
def cached_kitsu_search(title):
    return search_kitsu_id(title)

# ==========================================
# 4. ELABORAZIONE WORKER
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
        
        # --- GENERAZIONE POSTER MODIFICATO ---
        # Creiamo un nome file univoco basato sull'ID e l'episodio
        image_filename = f"{kitsu_id.replace(':', '_')}_ep{episode}.jpg"
        
        # Chiamiamo la funzione che edita l'immagine
        final_poster_url = add_episode_badge(base_poster, episode, image_filename)

        return {
            "id": kitsu_id,
            "type": "series",
            "name": raw_primary, # Titolo pulito, senza numero episodio
            "poster": final_poster_url, # URL della TUA immagine modificata
            "description": f"Nuovo episodio: {episode}",
            "posterShape": "poster"
        }
    except Exception as e:
        # print(f"Errore item: {e}") 
        return None

# ==========================================
# 5. FUNZIONE PRINCIPALE
# ==========================================

def update_animeworld_catalog():
    UPDATED_URL = "https://www.animeworld.so/updated"
    OUTPUT_FILE = "catalog/series/animeworld_updated.json"
    
    scraper = requests.Session()
    scraper.headers.update({'User-Agent': 'Mozilla/5.0'})

    try:
        print("Scaricando la pagina aggiornamenti...")
        response = scraper.get(UPDATED_URL)
        if response.status_code != 200:
            return

        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('.film-list .item')
        unique_metas = {}
        
        print(f"Trovati {len(items)} anime. Elaborazione e modifica immagini in corso...")

        # Riduciamo i workers perché l'elaborazione immagini è pesante per la CPU
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