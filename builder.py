import re
import time
import requests
import concurrent.futures
from functools import lru_cache
from bs4 import BeautifulSoup
from urllib.parse import quote

# ==========================================
# 1. FUNZIONI DI UTILITÀ (CONVERSIONE TITOLI)
# ==========================================

def convert_roman_to_arabic(title):
    """
    Cerca numeri romani (I, II... X) isolati nel titolo e li converte in arabi.
    Es: "Lupin III" -> "Lupin 3", "Overlord IV" -> "Overlord 4"
    """
    if not title:
        return ""

    # Mappa limitata ai numeri comuni negli anime (1-10)
    roman_map = {
        'I': '1', 'II': '2', 'III': '3', 'IV': '4', 'V': '5',
        'VI': '6', 'VII': '7', 'VIII': '8', 'IX': '9', 'X': '10'
    }

    # Regex che cerca solo parole intere (\b) per non rompere parole come "CIVIL"
    pattern = r'\b(' + '|'.join(roman_map.keys()) + r')\b'

    def replace(match):
        return roman_map[match.group(0)]

    # Esegui sostituzione
    new_title = re.sub(pattern, replace, title)
    return new_title.strip()

# ==========================================
# 2. GESTIONE API KITSU
# ==========================================

def search_kitsu_id(query):
    """
    Cerca un anime su Kitsu API e restituisce ID e Poster.
    """
    if not query:
        return None, None

    url = f"https://kitsu.io/api/edge/anime?filter[text]={quote(query)}"
    headers = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json"
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data['data']:
                anime = data['data'][0] # Prendi il primo risultato
                kitsu_id = f"kitsu:{anime['id']}"
                
                # Cerca il poster migliore disponibile
                attributes = anime.get('attributes', {})
                poster_img = attributes.get('posterImage', {})
                # Fallback tra le varie dimensioni
                poster_url = poster_img.get('medium') or poster_img.get('original') or poster_img.get('small')
                
                return kitsu_id, poster_url
    except Exception as e:
        print(f"Errore connessione Kitsu per '{query}': {e}")
    
    return None, None

# Cache LRU: Se cerchiamo "One Piece" 10 volte, Kitsu viene chiamata solo la prima volta.
@lru_cache(maxsize=128)
def cached_kitsu_search(title):
    return search_kitsu_id(title)

# ==========================================
# 3. ELABORAZIONE PARALLELA
# ==========================================

def process_single_item(item):
    """
    Funzione eseguita dai Worker (Thread).
    Estrae dati HTML, converte titolo, cerca su Kitsu.
    """
    try:
        # --- Estrazione Dati HTML ---
        title_tag = item.select_one('.name')
        if not title_tag: return None
        
        english_title = title_tag.get_text(strip=True) # Titolo visibile
        japanese_title = title_tag.get("data-jtitle")  # Titolo originale (spesso presente nel DOM)
        
        ep_tag = item.select_one('.ep')
        episode = ep_tag.get_text(strip=True) if ep_tag else "?"
        
        img_tag = item.select_one('img')
        original_poster = img_tag['src'] if img_tag else ""

        # --- Strategia di Ricerca ---
        
        # 1. Definizione Titolo Primario (preferiamo il giapponese se c'è)
        raw_primary = japanese_title if japanese_title else english_title
        
        # 2. Conversione Numeri Romani (Lupin III -> Lupin 3)
        search_title = convert_roman_to_arabic(raw_primary)

        # 3. Primo tentativo di ricerca
        kitsu_id, kitsu_poster = cached_kitsu_search(search_title)

        # 4. Fallback: Se fallisce e abbiamo convertito il titolo, riproviamo con l'originale
        if not kitsu_id and search_title != raw_primary:
            # print(f"Fallback su originale: {raw_primary}")
            kitsu_id, kitsu_poster = cached_kitsu_search(raw_primary)

        # 5. Fallback 2: Se fallisce col giapponese, proviamo l'inglese (e viceversa)
        if not kitsu_id and japanese_title and english_title:
            english_converted = convert_roman_to_arabic(english_title)
            # Evitiamo di ricercare se è uguale a quanto già cercato
            if english_converted != search_title and english_converted != raw_primary:
                # print(f"Fallback su inglese: {english_converted}")
                kitsu_id, kitsu_poster = cached_kitsu_search(english_converted)

        if not kitsu_id:
            # Se dopo tutti i tentativi non troviamo nulla, saltiamo
            return None

        # --- Costruzione Meta ---
        final_poster = kitsu_poster if kitsu_poster else original_poster
        
        return {
            "id": kitsu_id,
            "type": "series",
            "name": raw_primary, # Mostriamo il titolo originale all'utente
            "poster": final_poster,
            "description": f"Nuovo episodio: {episode}",
            "posterShape": "poster"
        }

    except Exception as e:
        print(f"Errore elaborazione item: {e}")
        return None

# ==========================================
# 4. FUNZIONE PRINCIPALE (MAIN)
# ==========================================

def get_stremio_catalogue():
    UPDATED_URL = "https://www.animeworld.so/updated" # O il tuo URL target
    
    # Assumiamo che 'scraper' sia definito nel tuo codice globale (es. cloudscraper)
    # Se non hai cloudscraper, usa requests:
    scraper = requests.Session() 
    scraper.headers.update({'User-Agent': 'Mozilla/5.0'})

    try:
        print("Scaricando la pagina aggiornamenti...")
        response = scraper.get(UPDATED_URL)
        
        if response.status_code != 200:
            print(f"Errore download pagina: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('.film-list .item')
        
        unique_metas = {} # Dizionario per mantenere l'ordine e unicità
        
        print(f"Trovati {len(items)} anime. Avvio ricerca metadati in parallelo...")

        # ThreadPoolExecutor: Esegue 5 ricerche contemporaneamente invece di 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = executor.map(process_single_item, items)

        # Raccogli i risultati validi
        for res in results:
            if res and res['id'] not in unique_metas:
                unique_metas[res['id']] = res

        print(f"Processo completato. Restituiti {len(unique_metas)} elementi.")
        return list(unique_metas.values())

    except Exception as e:
        print(f"Errore critico nel catalogo: {e}")
        return []

# Esempio di avvio (da rimuovere quando integri nell'addon)
if __name__ == "__main__":
    catalogo = get_stremio_catalogue()
    for anime in catalogo:
        print(f"- {anime['name']} ({anime['id']})")