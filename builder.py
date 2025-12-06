import re
import time
import json  # <--- NECESSARIO PER SALVARE
import os    # <--- NECESSARIO PER I PERCORSI
import requests
import concurrent.futures
from functools import lru_cache
from bs4 import BeautifulSoup
from urllib.parse import quote

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
# 2. GESTIONE API KITSU
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
# 3. ELABORAZIONE WORKER
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

        final_poster = kitsu_poster if kitsu_poster else original_poster
        
        return {
            "id": kitsu_id,
            "type": "series",
            "name": f"{raw_primary} - {episode}",
            "poster": final_poster,
            "description": f"Nuovo episodio: {episode}",
            "posterShape": "poster"
        }
    except Exception:
        return None

# ==========================================
# 4. FUNZIONE PRINCIPALE E SALVATAGGIO
# ==========================================

def update_animeworld_catalog():
    UPDATED_URL = "https://www.animeworld.so/updated"
    # Definisci qui il percorso dove vuoi salvare il file
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
        
        print(f"Trovati {len(items)} anime. Elaborazione in corso...")

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(process_single_item, items)

        for res in results:
            if res and res['id'] not in unique_metas:
                unique_metas[res['id']] = res

        metas_list = list(unique_metas.values())

        # --- BLOCCO DI SALVATAGGIO JSON ---
        
        # 1. Crea la cartella se non esiste
        output_dir = os.path.dirname(OUTPUT_FILE)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"Creata cartella: {output_dir}")

        # 2. Struttura Stremio Catalog (opzionale, ma consigliata)
        # Stremio si aspetta spesso un oggetto { "metas": [...] }
        json_output = {
            "metas": metas_list
        }

        # 3. Scrivi su file
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(json_output, f, ensure_ascii=False, indent=4)

        print(f"SUCCESSO! Salvati {len(metas_list)} elementi in '{OUTPUT_FILE}'")
        return metas_list

    except Exception as e:
        print(f"Errore critico: {e}")
        return []

if __name__ == "__main__":
    update_animeworld_catalog()