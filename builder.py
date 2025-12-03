import cloudscraper
from bs4 import BeautifulSoup
import json
import os
import requests
import time
from difflib import SequenceMatcher

# URL base
BASE_URL = "https://www.animeworld.ac"
UPDATED_URL = f"{BASE_URL}/updated"

# Funzione per cercare l'ID su Cinemeta (IMDb ID)
def search_cinemeta_id(title):
    try:
        # Puliamo il titolo da eventuali scritte come (ITA) o (SUB ITA) per la ricerca
        clean_title = title.replace("(ITA)", "").replace("(SUB ITA)", "").strip()
        
        # API di Cinemeta per cercare serie
        url = f"https://v3-cinemeta.strem.io/catalog/series/top.json?search={clean_title}"
        response = requests.get(url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            metas = data.get('metas', [])
            
            if metas:
                # Restituisce l'ID del primo risultato (il più probabile)
                # Es. "tt1234567"
                found_id = metas[0]['id']
                print(f"   MATCH: {clean_title} -> {found_id}")
                return found_id, metas[0]['poster']
    except Exception as e:
        print(f"   Errore ricerca Cinemeta: {e}")
    
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

        print(f"Trovati {len(items)} elementi. Cerco gli ID corretti (può richiedere tempo)...")

        for item in items:
            try:
                # Titolo
                title_tag = item.select_one('.name')
                title = title_tag.get_text(strip=True) if title_tag else "Sconosciuto"
                
                # Episodio
                ep_tag = item.select_one('.ep')
                episode = ep_tag.get_text(strip=True) if ep_tag else ""
                
                # Immagine originale (fallback)
                img_tag = item.select_one('img')
                original_poster = img_tag['src'] if img_tag else ""

                # --- STEP CRUCIALE: TROVARE L'ID COMPATIBILE CON TORRENTIO ---
                real_id, cinemeta_poster = search_cinemeta_id(title)

                # Se non troviamo l'ID IMDb, saltiamo l'anime (o Torrentio non funzionerebbe comunque)
                # Oppure potremmo usare un ID finto, ma non avrebbe stream.
                if not real_id:
                    print(f"   SKIP: Nessun ID trovato per '{title}'")
                    continue
                
                # Usiamo il poster di Cinemeta se c'è (è di qualità migliore), altrimenti quello di AW
                final_poster = cinemeta_poster if cinemeta_poster else original_poster

                meta = {
                    "id": real_id,  # Ora è un ID tipo 'tt12345'
                    "type": "series",
                    "name": title,
                    "poster": final_poster,
                    "description": f"Nuovo episodio: {episode} su AnimeWorld.",
                    "posterShape": "poster",
                }
                
                # Controllo duplicati (a volte AW mette lo stesso anime due volte)
                if not any(m['id'] == real_id for m in stremio_metas):
                    stremio_metas.append(meta)
                
                # Pausa per non intasare le API
                time.sleep(0.2) 

            except Exception as e:
                print(f"Errore: {e}")
                continue

        return stremio_metas

    except Exception as e:
        print(f"Errore critico: {e}")
        return []

def generate_stremio_files(metas):
    # 1. MANIFEST
    # Nota: Rimuoviamo 'meta' dalle resources perché ora usiamo ID standard (tt...),
    # quindi Stremio userà i metadati di Cinemeta automaticamente!
    manifest = {
        "id": "community.animeworld.updated",
        "version": "1.0.2",
        "name": "AnimeWorld Novità",
        "description": "Lista ultimi episodi. Compatibile con Torrentio.",
        "resources": ["catalog"], 
        "types": ["series", "movie"],
        "catalogs": [
            {
                "type": "series",
                "id": "animeworld_updated",
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