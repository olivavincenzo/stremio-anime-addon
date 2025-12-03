import cloudscraper
from bs4 import BeautifulSoup
import json
import os
import requests
import time
import re

# URL base
BASE_URL = "https://www.animeworld.ac"
UPDATED_URL = f"{BASE_URL}/updated"

# --- FUNZIONE PER CERCARE SU KITSU ---
def search_kitsu_id(title):
    try:
        # Pulizia del titolo per la ricerca
        # Rimuoviamo (ITA), (SUB ITA), [Uncensored], ecc.
        clean_title = re.sub(r'\s*\(.*?\)', '', title)
        clean_title = re.sub(r'\s*\[.*?\]', '', clean_title).strip()
        
        # API di Kitsu
        url = "https://kitsu.io/api/edge/anime"
        params = {
            "filter[text]": clean_title,
            "page[limit]": 1  # Ci basta il primo risultato
        }
        
        # User agent per non essere bloccati
        headers = {
            "Accept": "application/vnd.api+json",
            "Content-Type": "application/vnd.api+json"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if data['data']:
                anime = data['data'][0]
                kitsu_id = anime['id']
                
                # Cerchiamo l'immagine poster
                attributes = anime.get('attributes', {})
                poster_img = attributes.get('posterImage', {})
                # Kitsu ha varie dimensioni, prendiamo 'small' o 'medium' o 'original'
                poster = poster_img.get('small') or poster_img.get('original')
                
                print(f"   MATCH KITSU: {clean_title} -> ID: {kitsu_id}")
                return f"kitsu:{kitsu_id}", poster
    except Exception as e:
        print(f"   Errore ricerca Kitsu per '{title}': {e}")
    
    return None, None

def scrape_anime_updated():
    print("Inizio scraping da AnimeWorld...")
    scraper = cloudscraper.create_scraper()
    
    try:
        response = scraper.get(UPDATED_URL)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        items = soup.select('.film-list .item')
        
        stremio_metas = []
        seen_ids = set() # Per evitare duplicati

        print(f"Trovati {len(items)} elementi. Cerco gli ID su Kitsu...")

        for item in items:
            try:
                # Titolo
                title_tag = item.select_one('.name')
                title = title_tag.get_text(strip=True) if title_tag else "Sconosciuto"
                
                # Episodio
                ep_tag = item.select_one('.ep')
                episode = ep_tag.get_text(strip=True) if ep_tag else ""
                
                # Fallback immagine originale
                img_tag = item.select_one('img')
                original_poster = img_tag['src'] if img_tag else ""

                # --- RICERCA SU KITSU ---
                kitsu_id, kitsu_poster = search_kitsu_id(title)

                if not kitsu_id:
                    print(f"   SKIP: Nessun ID Kitsu trovato per '{title}'")
                    continue
                
                # Evitiamo duplicati (es. se AW mette ep 11 e ep 12 dello stesso anime)
                if kitsu_id in seen_ids:
                    continue
                seen_ids.add(kitsu_id)

                # Usiamo il poster di Kitsu se disponibile, è più "pulito"
                final_poster = kitsu_poster if kitsu_poster else original_poster

                meta = {
                    "id": kitsu_id,       # Esempio: "kitsu:12345"
                    "type": "series",     # Kitsu gestisce quasi tutto come series o movie
                    "name": title,
                    "poster": final_poster,
                    "description": f"Nuovo episodio: {episode} su AnimeWorld.",
                    "posterShape": "poster",
                }
                
                stremio_metas.append(meta)
                
                # Importante: Kitsu ha rate limit, facciamo una piccola pausa
                time.sleep(0.3)

            except Exception as e:
                print(f"Errore elemento: {e}")
                continue

        return stremio_metas

    except Exception as e:
        print(f"Errore critico: {e}")
        return []

def generate_stremio_files(metas):
    # 1. MANIFEST
    manifest = {
        "id": "community.animeworld.kitsu.updated",
        "version": "1.0.3",
        "name": "AnimeWorld Novità (Kitsu)",
        "description": "Ultimi episodi usando metadati Kitsu (compatibile con Torrentio)",
        "resources": ["catalog"], 
        "types": ["series", "movie", "anime"], # Aggiungiamo 'anime' per sicurezza
        "catalogs": [
            {
                "type": "series",
                "id": "animeworld_kitsu_updated",
                "name": "AnimeWorld Novità",
                "extra": [{"name": "search", "isRequired": False}]
            }
        ]
    }

    with open("manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
    print("✅ manifest.json generato.")

    # 2. CATALOGO
    output_dir = "catalog/series"
    os.makedirs(output_dir, exist_ok=True)

    catalog_data = {"metas": metas}

    with open(f"{output_dir}/animeworld_updated.json", "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, indent=4)
    print(f"✅ Catalogo generato con {len(metas)} anime.")

if __name__ == "__main__":
    anime_data = scrape_anime_updated()
    
    if anime_data:
        generate_stremio_files(anime_data)
    else:
        print("Nessun dato trovato.")